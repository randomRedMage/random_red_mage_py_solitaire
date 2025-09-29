
# pyramid.py - Pyramid Solitaire scenes
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import pygame
from solitaire import common as C
from solitaire import mechanics as M
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help


_SAVE_FILENAME = "pyramid_save.json"


def _pyramid_dir() -> str:
    return C.project_saves_dir("pyramid")


def _pyramid_save_path() -> str:
    return os.path.join(_pyramid_dir(), _SAVE_FILENAME)


def _safe_write_json(path: str, data: Any) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _clear_saved_game() -> None:
    try:
        if os.path.isfile(_pyramid_save_path()):
            os.remove(_pyramid_save_path())
    except Exception:
        pass


def has_saved_game() -> bool:
    state = _safe_read_json(_pyramid_save_path())
    if not isinstance(state, dict):
        return False
    if state.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    state = _safe_read_json(_pyramid_save_path())
    if not isinstance(state, dict):
        return None
    if state.get("completed"):
        return None
    return state

# Helper value rules
def card_value(card: C.Card) -> int:
    return card.rank  # A=1, ..., J=11, Q=12, K=13

def is_king(card: C.Card) -> bool:
    return card.rank == 13

def pair_to_13(a: C.Card, b: C.Card) -> bool:
    return (card_value(a) + card_value(b)) == 13

class PyramidGameScene(C.Scene):
    def __init__(self, app, allowed_resets: Optional[int] = None, load_state: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        # 2D scroll offset to accommodate larger cards
        self.scroll_x: int = 0
        self.scroll_y: int = 0
        self.drag_pan = M.DragPanController()
        self._drag_vscroll = False
        self._drag_hscroll = False
        # Difficulty / resets
        self.allowed_resets: Optional[int] = allowed_resets  # None => unlimited
        self.resets_used: int = 0

        # Pyramid data (7 rows, triangle). Each entry is either a Card or None once removed.
        self.pyramid: List[List[Optional[C.Card]]] = []

        # Layout parameters (computed in compute_layout())
        self.pyr_top_y   = 120
        self.overlap_y   = int(C.CARD_H * 0.50)   # vertical distance between rows
        self.inner_gap_x = getattr(C, "CARD_GAP_X", max(10, C.CARD_W // 8))  # gap between cards in a row
        self.center_x    = C.SCREEN_W // 2

        # Piles (positions set in compute_layout())
        self.stock_pile = C.Pile(0, 0)
        self.waste_left = C.Pile(0, 0)
        self.waste_right= C.Pile(0, 0)

        # Undo support
        self.undo_mgr = C.UndoManager()

        # Toolbar (right-aligned)
        self.ui_helper = ModeUIHelper(self, game_id="pyramid")

        def _can_undo():
            return self.undo_mgr.can_undo()

        def save_and_exit() -> None:
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.new_game},
            restart_action={"on_click": self.restart_deal, "tooltip": "Restart current deal"},
            undo_action={"on_click": lambda: self.undo(), "enabled": _can_undo, "tooltip": "Undo last move"},
            hint_action={
                "on_click": lambda: self.show_hint(),
                "enabled": self.any_moves_available,
                "tooltip": "Highlight a possible move",
                "shortcut": pygame.K_h,
            },
            save_action=(
                "Save&Exit",
                {
                    "on_click": save_and_exit,
                    "tooltip": "Save game and return to menu",
                },
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        )

        # UI buttons
        self.b_menu: C.Button
        self.b_new: C.Button
        self.b_restart: C.Button

        # Selection state: ("pyr", r, i) or ("w1", 0, 0) or ("w2", 0, 0)
        self.sel_src: Optional[Tuple[str, int, int]] = None
        # Hint state
        self.hint_srcs: Optional[List[Tuple[str, int, int]]] = None
        self.hint_expires_at: int = 0

        self.message = ""

        # Layout depends on screen size: compute before first deal
        self.compute_layout()

        # Deal initial game
        self.initial_order: List[Tuple[int,int]] = []  # (suit, rank) for restart
        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal()
            # Initialize undo stack with starting state
            self.undo_mgr = C.UndoManager()
            self.push_undo()

        # Help overlay
        self.help = create_modal_help("pyramid")

    # ---------- Scrolling helpers ----------
    def _content_bottom_y(self) -> int:
        # Pyramid bottom
        pyr_bottom = self.pyr_top_y + 6 * self.overlap_y + C.CARD_H
        base_y = pyr_bottom + getattr(C, "CARD_GAP_Y", 26)
        piles_bottom = base_y + C.CARD_H
        return max(piles_bottom, pyr_bottom)

    def _content_bounds_x(self) -> tuple:
        # Compute left/right bounds considering widest pyramid row and piles span
        widest_row_w = C.CARD_W * 7 + self.inner_gap_x * 6
        left_pyr = self.center_x - widest_row_w // 2
        right_pyr = left_pyr + widest_row_w
        step_x = C.CARD_W + self.inner_gap_x
        group_w = step_x * 2 + C.CARD_W
        piles_left = self.center_x - group_w // 2
        piles_right = piles_left + group_w
        return min(left_pyr, piles_left), max(right_pyr, piles_right)

    def _clamp_scroll(self):
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        if self.scroll_y > 0:
            self.scroll_y = 0
        # Clamp X as well
        left, right = self._content_bounds_x()
        max_scroll_x = 20 - left
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        if self.scroll_x > max_scroll_x:
            self.scroll_x = max_scroll_x
        if self.scroll_x < min_scroll_x:
            self.scroll_x = min_scroll_x

    # ---------- Layout / Responsiveness ----------
    def compute_layout(self):
        self.center_x = C.SCREEN_W // 2

        # Start with preferred values
        top_bar_h = getattr(C, "TOP_BAR_H", 64)
        self.pyr_top_y = max(90, top_bar_h + 26)
        self.overlap_y = int(C.CARD_H * 0.50)
        self.inner_gap_x = getattr(C, "CARD_GAP_X", max(10, C.CARD_W // 8))

        # Compute needed total height for pyramid + piles + bottom margin
        def total_height(overlap_y: int) -> int:
            pyr_h = C.CARD_H + overlap_y * 6  # 7 rows
            gap_y = getattr(C, "CARD_GAP_Y", 26)
            piles_h = C.CARD_H
            return self.pyr_top_y + pyr_h + gap_y + piles_h + 20

        # If it doesn't fit, reduce overlap_y
        while total_height(self.overlap_y) > C.SCREEN_H and self.overlap_y > int(C.CARD_H * 0.30):
            self.overlap_y -= 2  # tighten rows a bit

        # Place piles under the pyramid
        last_row_y = self.pyr_top_y + 6 * self.overlap_y
        pyramid_bottom = last_row_y + C.CARD_H
        base_y = pyramid_bottom + getattr(C, "CARD_GAP_Y", 26)

        # Center the 3 piles group under the pyramid
        step_x = C.CARD_W + self.inner_gap_x
        group_w = step_x * 2 + C.CARD_W
        left_x = self.center_x - group_w // 2
        self.stock_pile.x, self.stock_pile.y = left_x, base_y
        self.waste_left.x, self.waste_left.y = left_x + step_x, base_y
        self.waste_right.x,self.waste_right.y= left_x + 2*step_x, base_y

        # Buttons now provided by toolbar (see __init__)

    # ---------- Lifecycle ----------
    def deal(self, preset_order: Optional[List[Tuple[int,int]]] = None):
        if preset_order is None:
            deck = C.make_deck(shuffle=True)
            # snapshot the original order (suit, rank) for "Restart Deal"
            self.initial_order = [(c.suit, c.rank) for c in deck]
        else:
            deck = [C.Card(s, r, False) for (s, r) in preset_order]

        # Build pyramid rows 0..6; all face-up
        self.pyramid = []
        k = 0
        for r in range(7):
            row = []
            for _ in range(r + 1):
                c = deck[k]; k += 1
                c.face_up = True
                row.append(c)
            self.pyramid.append(row)

        # Remaining cards -> stock (face down)
        self.stock_pile.cards = deck[k:]
        for c in self.stock_pile.cards:
            c.face_up = False

        self.waste_left.cards.clear()
        self.waste_right.cards.clear()
        self.sel_src = None
        self.message = ""
        self.resets_used = 0 if self.allowed_resets is not None else self.resets_used

    def new_game(self):
        _clear_saved_game()
        self.deal()
        self.undo_mgr = C.UndoManager()
        self.push_undo()

    def restart_deal(self):
        if self.initial_order:
            self.deal(self.initial_order[:])
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    def _state_dict(self) -> Dict[str, Any]:
        state = self.record_snapshot()
        state.update(
            {
                "scroll_x": self.scroll_x,
                "scroll_y": self.scroll_y,
                "allowed_resets": self.allowed_resets,
                "initial_order": getattr(self, "initial_order", []),
                "completed": all(card is None for row in self.pyramid for card in row),
            }
        )
        return state

    def _save_game(self, to_menu: bool = False) -> None:
        state = self._state_dict()
        _safe_write_json(_pyramid_save_path(), state)
        if to_menu:
            self.ui_helper.goto_main_menu()

    def _load_from_state(self, state: Dict[str, Any]) -> None:
        if not state:
            self.deal()
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            return
        self.restore_snapshot(state)
        self.scroll_x = state.get("scroll_x", 0)
        self.scroll_y = state.get("scroll_y", 0)
        self.allowed_resets = state.get("allowed_resets", self.allowed_resets)
        init = state.get("initial_order")
        if isinstance(init, list):
            self.initial_order = [(int(s), int(r)) for (s, r) in init]
        else:
            self.initial_order = []
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._clamp_scroll()

    # ---------- Undo helpers ----------
    def record_snapshot(self):
        return {
            "pyramid": [[(c.suit, c.rank, c.face_up) if c is not None else None for c in row] for row in self.pyramid],
            "stock": [(c.suit, c.rank, c.face_up) for c in self.stock_pile.cards],
            "waste_left": [(c.suit, c.rank, c.face_up) for c in self.waste_left.cards],
            "waste_right": [(c.suit, c.rank, c.face_up) for c in self.waste_right.cards],
            "resets_used": self.resets_used,
            "sel_src": self.sel_src,
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        pyr: List[List[Optional[C.Card]]] = []
        for row in snap["pyramid"]:
            new_row: List[Optional[C.Card]] = []
            for t in row:
                if t is None:
                    new_row.append(None)
                else:
                    s, r, f = t
                    new_row.append(C.Card(s, r, f))
            pyr.append(new_row)
        self.pyramid = pyr

        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        self.stock_pile.cards = mk(snap["stock"])
        self.waste_left.cards = mk(snap["waste_left"])
        self.waste_right.cards = mk(snap["waste_right"])
        self.resets_used = snap["resets_used"]
        self.sel_src = snap["sel_src"]
        self.message = snap["message"]

    def push_undo(self):
        snap = self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ---------- Hint ----------
    def show_hint(self):
        # Build list of selectable tops with their sources
        sources: List[Tuple[Tuple[str, int, int], C.Card]] = []
        # Free pyramid cards
        for r, row in enumerate(self.pyramid):
            for i, c in enumerate(row):
                if c and self.is_free(r, i):
                    sources.append((("pyr", r, i), c))
        # Waste tops
        if self.waste_left.cards:
            sources.append((("w1", 0, 0), self.waste_left.cards[-1]))
        if self.waste_right.cards:
            sources.append((("w2", 0, 0), self.waste_right.cards[-1]))

        # Prefer single-card king removal
        for src, card in sources:
            if is_king(card):
                self.hint_srcs = [src]
                self.hint_expires_at = pygame.time.get_ticks() + 2000
                return

        # Otherwise find any pair summing to 13
        n = len(sources)
        for i in range(n):
            for j in range(i+1, n):
                a_src, a = sources[i]
                b_src, b = sources[j]
                if pair_to_13(a, b):
                    self.hint_srcs = [a_src, b_src]
                    self.hint_expires_at = pygame.time.get_ticks() + 2000
                    return

    # ---------- Geometry ----------
    def pos_for(self, r: int, i: int) -> Tuple[int, int]:
        row_w = C.CARD_W * (r + 1) + self.inner_gap_x * r
        left  = self.center_x - row_w // 2
        x = left + i * (C.CARD_W + self.inner_gap_x)
        y = self.pyr_top_y + r * self.overlap_y
        return x, y

    def is_free(self, r: int, i: int) -> bool:
        if self.pyramid[r][i] is None:
            return False
        if r == 6:
            return True
        return (self.pyramid[r+1][i] is None) and (self.pyramid[r+1][i+1] is None)

    # ---------- Drawing ----------
    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Top bar text (drawn at end so content scrolls behind)
        resets_txt = "Resets: unlimited" if self.allowed_resets is None else f"Resets used: {self.resets_used}/{self.allowed_resets}"

        # Expire transient hint
        if self.hint_srcs and pygame.time.get_ticks() > self.hint_expires_at:
            self.hint_srcs = None

        # Message banner (win/lose)
        if self.message:
            msg = "You win!" if isinstance(self.message, str) and ("win" in self.message.lower()) else self.message
            t = C.FONT_TITLE.render(msg, True, C.GOLD)
            screen.blit(t, (C.SCREEN_W//2 - t.get_width()//2, 70))

        # Apply draw offset for piles and pyramid
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        # Draw pyramid
        for r, row in enumerate(self.pyramid):
            for i, card in enumerate(row):
                if card is None:
                    continue
                x, y = self.pos_for(r, i)
                rect = pygame.Rect(x + self.scroll_x, y + self.scroll_y, C.CARD_W, C.CARD_H)
                card.face_up = True
                surf = C.get_card_surface(card)
                screen.blit(surf, (x + self.scroll_x, y + self.scroll_y))

                if self.sel_src == ("pyr", r, i):
                    pygame.draw.rect(screen, C.GOLD, rect, 4, border_radius=C.CARD_RADIUS)
                # Hint highlight for pyramid cards
                if self.hint_srcs and ("pyr", r, i) in self.hint_srcs:
                    pygame.draw.rect(screen, C.BLUE, rect, 6, border_radius=C.CARD_RADIUS)

                if not self.is_free(r, i):
                    overlay = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
                    overlay.fill((0,0,0,90))
                    screen.blit(overlay, (x + self.scroll_x, y + self.scroll_y))

        # Draw piles
        self.stock_pile.draw(screen)
        self.waste_left.draw(screen)
        self.waste_right.draw(screen)

        # Resets-left indicator in stock slot when stock is empty
        if not self.stock_pile.cards:
            stock_rect = self.stock_pile.top_rect().copy(); stock_rect.move_ip(self.scroll_x, self.scroll_y)
            resets_left = "∞" if self.allowed_resets is None else str(max(0, self.allowed_resets - self.resets_used))
            # Override with a clean symbol for unlimited
            resets_left = "∞" if self.allowed_resets is None else resets_left
            font = getattr(C, "FONT", getattr(C, "FONT_TITLE", None))
            if font is None:
                font = pygame.font.SysFont(None, 28)
            surf = font.render(resets_left, True, C.WHITE)
            screen.blit(surf, (stock_rect.centerx - surf.get_width()//2, stock_rect.centery - surf.get_height()//2))

            # If unlimited, redraw with a Unicode-capable font to avoid glyph issues
            if self.allowed_resets is None:
                try:
                    _font_path = os.path.join(os.path.dirname(C.__file__), "assets", "fonts", "DejaVuSans.ttf")
                    _font = pygame.font.Font(_font_path, 28)
                except Exception:
                    _font = pygame.font.SysFont("Segoe UI Symbol", 28) or pygame.font.SysFont(None, 28)
                _surf = _font.render("∞", True, C.WHITE)
                # Clear any previously drawn glyph by overdrawing a small bg patch
                bw, bh = _surf.get_size()
                clear_rect = pygame.Rect(0, 0, bw + 8, bh + 8)
                clear_rect.center = stock_rect.center
                pygame.draw.rect(screen, C.TABLE_BG, clear_rect)
                screen.blit(_surf, (stock_rect.centerx - _surf.get_width()//2, stock_rect.centery - _surf.get_height()//2))

        if self.sel_src == ("w1", 0, 0) and self.waste_left.cards:
            r = self.waste_left.top_rect().copy(); r.move_ip(self.scroll_x, self.scroll_y)
            pygame.draw.rect(screen, C.GOLD, r, 4, border_radius=C.CARD_RADIUS)
        if self.sel_src == ("w2", 0, 0) and self.waste_right.cards:
            r = self.waste_right.top_rect().copy(); r.move_ip(self.scroll_x, self.scroll_y)
            pygame.draw.rect(screen, C.GOLD, r, 4, border_radius=C.CARD_RADIUS)
        # Hint highlight on waste piles
        if self.hint_srcs:
            if ("w1", 0, 0) in self.hint_srcs and self.waste_left.cards:
                r = self.waste_left.top_rect().copy(); r.move_ip(self.scroll_x, self.scroll_y)
                pygame.draw.rect(screen, C.BLUE, r, 6, border_radius=C.CARD_RADIUS)
            if ("w2", 0, 0) in self.hint_srcs and self.waste_right.cards:
                r = self.waste_right.top_rect().copy(); r.move_ip(self.scroll_x, self.scroll_y)
                pygame.draw.rect(screen, C.BLUE, r, 6, border_radius=C.CARD_RADIUS)

        # Draw scrollbars when content extends beyond view
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0
        bottom = self._content_bottom_y()
        if bottom > C.SCREEN_H:
            track_rect, knob_rect, *_ = self._vertical_scrollbar()
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Horizontal scrollbar if content wider than view
        widest_row_w = C.CARD_W * 7 + self.inner_gap_x * 6
        left_x = self.center_x - widest_row_w // 2
        right_x = left_x + widest_row_w
        step_x = C.CARD_W + self.inner_gap_x
        group_w = step_x * 2 + C.CARD_W
        piles_left = self.center_x - group_w // 2
        piles_right = piles_left + group_w
        left = min(left_x, piles_left)
        right = max(right_x, piles_right)
        if right - left > C.SCREEN_W - 40:
            track_rect, knob_rect, *_ = self._horizontal_scrollbar()
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Draw top bar and toolbar last so content scrolls behind
        C.Scene.draw_top_bar(self, screen, "Pyramid", resets_txt)
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

    # ---------- Scrollbar geometry helpers ----------
    def _vertical_scrollbar(self):
        bottom = self._content_bottom_y()
        if bottom <= C.SCREEN_H:
            return None
        track_x = C.SCREEN_W - 12
        track_y = getattr(C, "TOP_BAR_H", 64)
        track_h = C.SCREEN_H - track_y - 10
        track_rect = pygame.Rect(track_x, track_y, 6, track_h)
        view_h = C.SCREEN_H
        content_h = bottom
        knob_h = max(30, int(track_h * (view_h / content_h)))
        max_scroll = 0
        min_scroll = C.SCREEN_H - bottom - 20
        denom = (max_scroll - min_scroll)
        t = (self.scroll_y - min_scroll) / denom if denom != 0 else 1.0
        knob_y = int(track_y + (track_h - knob_h) * (1.0 - t))
        knob_rect = pygame.Rect(track_x, knob_y, 6, knob_h)
        return track_rect, knob_rect, min_scroll, max_scroll, track_y, track_h, knob_h

    def _horizontal_scrollbar(self):
        # Compute content bounds
        widest_row_w = C.CARD_W * 7 + self.inner_gap_x * 6
        left_x = self.center_x - widest_row_w // 2
        right_x = left_x + widest_row_w
        step_x = C.CARD_W + self.inner_gap_x
        group_w = step_x * 2 + C.CARD_W
        piles_left = self.center_x - group_w // 2
        piles_right = piles_left + group_w
        left, right = min(left_x, piles_left), max(right_x, piles_right)
        if right - left <= C.SCREEN_W - 40:
            return None
        track_x = 10
        track_w = C.SCREEN_W - 20
        track_y = C.SCREEN_H - 10
        track_rect = pygame.Rect(track_x, track_y-6, track_w, 6)
        view_w = C.SCREEN_W
        content_w = right - left + 40
        knob_w = max(30, int(track_w * (view_w / max(view_w, content_w))))
        max_scroll_x = 20 - left
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        denom = (max_scroll_x - min_scroll_x)
        t = (self.scroll_x - min_scroll_x) / denom if denom != 0 else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        knob_rect = pygame.Rect(knob_x, track_y-6, knob_w, 6)
        return track_rect, knob_rect, min_scroll_x, max_scroll_x, track_x, track_w, knob_w

    # ---------- Input ----------
    def handle_event(self, e):
        # Help overlay intercept (swallow inputs while open)
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return
        if self.ui_helper.handle_menu_event(e):
            return
        # Toolbar first
        if self.toolbar.handle_event(e):
            return
        if self.ui_helper.handle_shortcuts(e):
            return

        # Mouse wheel -> scroll (vertical + horizontal if available)
        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll()
            return

        # Scrollbar interactions (mouse) — handle before content clicks
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    self._vscroll_drag_dy = e.pos[1] - knob_rect.y
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    return
                elif track_rect.collidepoint(e.pos):
                    y = min(max(e.pos[1] - knob_h//2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    t = 1.0 - t_knob
                    self.scroll_y = min_sy + t * (max_sy - min_sy)
                    self._clamp_scroll()
                    return

            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_hscroll = True
                    self._hscroll_drag_dx = e.pos[0] - knob_rect.x
                    self._hscroll_geom = (min_sx, max_sx, track_x, track_w, knob_w)
                    return
                elif track_rect.collidepoint(e.pos):
                    x = min(max(e.pos[0] - knob_w//2, track_x), track_x + track_w - knob_w)
                    t_knob = (x - track_x) / max(1, (track_w - knob_w))
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll()
                    return

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._drag_vscroll = False
            self._drag_hscroll = False

        if self.drag_pan.handle_event(e, target=self, clamp=self._clamp_scroll):
            return

        if e.type == pygame.MOUSEMOTION:
            if getattr(self, "_drag_vscroll", False):
                min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
                y = min(max(e.pos[1] - self._vscroll_drag_dy, track_y), track_y + track_h - knob_h)
                t_knob = (y - track_y) / max(1, (track_h - knob_h))
                t = 1.0 - t_knob
                self.scroll_y = min_sy + t * (max_sy - min_sy)
                self._clamp_scroll()
                return
            if getattr(self, "_drag_hscroll", False):
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_dx, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll()
                return

        if e.type == pygame.KEYDOWN:
            self.ui_helper.handle_shortcuts(e)

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Prevent interactions under top bar (content is visually behind it)
            if my < getattr(C, "TOP_BAR_H", 64):
                return
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y

            # Toolbar handles its own clicks

            # 1) Stock click (even when empty to attempt reset)
            if self.stock_pile.top_rect().collidepoint((mxw, myw)):
                self.on_stock_click()
                return

            # 2) Waste clicks
            if self.waste_left.top_rect().collidepoint((mxw,myw)) and self.waste_left.cards:
                self.on_source_click(("w1", 0, 0)); return
            if self.waste_right.top_rect().collidepoint((mxw,myw)) and self.waste_right.cards:
                self.on_source_click(("w2", 0, 0)); return

            # 3) Pyramid clicks – iterate from bottom to top so the
            # visually front-most cards receive the click first.
            for r in range(len(self.pyramid) - 1, -1, -1):
                row = self.pyramid[r]
                for i in range(len(row) - 1, -1, -1):
                    card = row[i]
                    if card is None:
                        continue
                    x, y = self.pos_for(r, i)
                    rect = pygame.Rect(x, y, C.CARD_W, C.CARD_H)
                    if rect.collidepoint((mxw, myw)) and self.is_free(r, i):
                        self.on_source_click(("pyr", r, i))
                        return

    # ---------- Mechanics ----------
    def on_stock_click(self):
        # Clear hint on action
        self.hint_srcs = None
        if self.stock_pile.cards:
            self.push_undo()
            c = self.stock_pile.cards.pop()
            c.face_up = True
            if self.waste_left.cards:
                self.waste_right.cards.append(self.waste_left.cards.pop())
            self.waste_left.cards.append(c)
            if self.sel_src and self.sel_src[0] == "stock":
                self.sel_src = None
            return

        # Empty stock => attempt reset
        if (self.allowed_resets is None) or (self.resets_used < self.allowed_resets):
            self.push_undo()
            if self.waste_left.cards:
                self.waste_right.cards.append(self.waste_left.cards.pop())
            if self.waste_right.cards:
                for c in self.waste_right.cards:
                    c.face_up = False
                self.stock_pile.cards = self.waste_right.cards[:]  # maintain order; top remains last
                self.waste_right.cards.clear()
            if self.allowed_resets is not None:
                self.resets_used += 1
        else:
            if not self.any_moves_available():
                self.message = "Game Over"

    def on_source_click(self, src: Tuple[str, int, int]):
        # Clear hint on action
        self.hint_srcs = None
        card = self.card_from_src(src)
        if card is None:
            return

        if is_king(card):
            self.push_undo()
            self.remove_src(src)
            self.sel_src = None
            self.after_move_checks()
            return

        if self.sel_src is None:
            self.sel_src = src
            return

        if self.sel_src == src:
            self.sel_src = None
            return

        other = self.card_from_src(self.sel_src)
        if other and pair_to_13(card, other):
            self.push_undo()
            self.remove_src(src)
            self.remove_src(self.sel_src)
            self.sel_src = None
            self.after_move_checks()
        else:
            self.sel_src = src

    def card_from_src(self, src: Tuple[str, int, int]) -> Optional[C.Card]:
        kind, a, b = src
        if kind == "pyr":
            return self.pyramid[a][b]
        if kind == "w1":
            return self.waste_left.cards[-1] if self.waste_left.cards else None
        if kind == "w2":
            return self.waste_right.cards[-1] if self.waste_right.cards else None
        return None

    def remove_src(self, src: Tuple[str, int, int]):
        kind, a, b = src
        if kind == "pyr":
            self.pyramid[a][b] = None
        elif kind == "w1":
            if self.waste_left.cards:
                self.waste_left.cards.pop()
        elif kind == "w2":
            if self.waste_right.cards:
                self.waste_right.cards.pop()

    def after_move_checks(self):
        if all(card is None for row in self.pyramid for card in row):
            self.message = "🎉 You win!"
            _clear_saved_game()
            return
        if (not self.stock_pile.cards) and (self.allowed_resets is not None and self.resets_used >= self.allowed_resets):
            if not self.any_moves_available():
                self.message = "Game Over"
                _clear_saved_game()

    # ---------- Move search ----------
    def free_pyramid_cards(self) -> List[C.Card]:
        out = []
        for r, row in enumerate(self.pyramid):
            for i, c in enumerate(row):
                if c and self.is_free(r, i):
                    out.append(c)
        return out

    def any_moves_available(self) -> bool:
        tops: List[C.Card] = self.free_pyramid_cards()
        if self.waste_left.cards:
            tops.append(self.waste_left.cards[-1])
        if self.waste_right.cards:
            tops.append(self.waste_right.cards[-1])
        if any(is_king(c) for c in tops):
            return True
        vals = [card_value(c) for c in tops]
        s = set(vals)
        for v in vals:
            if (13 - v) in s:
                return True
        return False

# (win message normalized in after_move_checks)
