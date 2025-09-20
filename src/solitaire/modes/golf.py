# golf.py - Golf Solitaire mode (options + game with multi-hole scoring and save/continue)
import os
import json
import pygame
from typing import List, Optional, Tuple, Dict, Any

from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.ui import ModalHelp


def _golf_dir() -> str:
    # Reuse the app settings dir for saves/history
    try:
        return C._settings_dir()
    except Exception:
        # Fallback to user home if not available
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _golf_save_path() -> str:
    return os.path.join(_golf_dir(), "golf_save.json")


def _golf_history_path() -> str:
    return os.path.join(_golf_dir(), "golf_history.json")


def _safe_write_json(path: str, data: Any):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _rank_adjacent(a: int, b: int, around: bool) -> bool:
    # ranks 1..13 (A..K); adjacent if +/- 1 or wrap A<->K if around
    if a <= 0 or b <= 0:
        return False
    if abs(a - b) == 1:
        return True
    if around and ((a == 1 and b == 13) or (a == 13 and b == 1)):
        return True
    return False


class GolfOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.holes_options = [1, 3, 9, 18]
        self.holes_idx = 0
        self.around = True

        cx = C.SCREEN_W // 2 - 220
        y = 220
        self.b_new1 = C.Button("New 1 Hole", cx, y, w=440); y += 56
        self.b_new3 = C.Button("New 3 Holes", cx, y, w=440); y += 56
        self.b_new9 = C.Button("New 9 Holes", cx, y, w=440); y += 56
        self.b_new18 = C.Button("New 18 Holes", cx, y, w=440); y += 56
        y += 8
        self.b_wrap = C.Button(self._wrap_label(), cx, y, w=440); y += 56
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440); y += 56
        self.b_scores = C.Button("View Recent Scores", cx, y, w=440); y += 56
        y += 8
        self.b_back = C.Button("Back", cx, y, w=440)

    def _wrap_label(self):
        return f"Around the Corner: {'On' if self.around else 'Off'}"

    def _start_new(self, holes: int):
        # Starting a new game overwrites any pending save
        try:
            if os.path.isfile(_golf_save_path()):
                os.remove(_golf_save_path())
        except Exception:
            pass
        self.next_scene = GolfGameScene(self.app, holes_total=holes, around=self.around, load_state=None)

    def _has_save(self) -> bool:
        s = _safe_read_json(_golf_save_path())
        return bool(s) and not s.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_new1.hovered((mx, my)):
                self._start_new(1)
            elif self.b_new3.hovered((mx, my)):
                self._start_new(3)
            elif self.b_new9.hovered((mx, my)):
                self._start_new(9)
            elif self.b_new18.hovered((mx, my)):
                self._start_new(18)
            elif self.b_wrap.hovered((mx, my)):
                self.around = not self.around
                self.b_wrap.text = self._wrap_label()
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                load_state = _safe_read_json(_golf_save_path())
                self.next_scene = GolfGameScene(self.app, holes_total=load_state.get("holes_total", 1), around=bool(load_state.get("around", False)), load_state=load_state)
            elif self.b_scores.hovered((mx, my)):
                self.next_scene = GolfScoresScene(self.app)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Golf - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 120))
        mp = pygame.mouse.get_pos()
        # Gray out continue when no save
        has_save = self._has_save()
        # Temporarily tweak draw to reflect disabled state by label suffix
        if not has_save:
            old = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for b in [self.b_new1, self.b_new3, self.b_new9, self.b_new18, self.b_wrap, self.b_continue, self.b_scores, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))
        if not has_save:
            self.b_continue.text = old


class GolfGameScene(C.Scene):
    def __init__(self, app, holes_total: int = 1, around: bool = False, load_state: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.holes_total = holes_total
        self.around = around
        self.current_hole = 1
        self.scores: List[int] = []  # per-hole completed scores
        self.message = ""
        # Scrolling (vertical + horizontal)
        self.scroll_y: int = 0
        self.scroll_x: int = 0
        self._drag_vscroll: bool = False
        self._drag_hscroll: bool = False
        # Last drawn geometry for scrollbar calculations
        self._last_tableau_rect: Optional[pygame.Rect] = None
        self._last_bottom_rect: Optional[pygame.Rect] = None
        self._last_score_rect: Optional[pygame.Rect] = None
        # Piles
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=0) for _ in range(7)]
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.foundation: C.Pile = C.Pile(0, 0)
        # Undo
        self.undo_mgr = C.UndoManager()
        # Restart snapshot for the current hole
        self._initial_snapshot = None

        self.ui_helper = ModeUIHelper(self, game_id="golf")

        def can_undo():
            return self.undo_mgr.can_undo()

        def save_and_exit():
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self._new_game_reset},
            restart_action={"on_click": self.restart_hole, "tooltip": "Restart current hole"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            save_action=("Save&Exit", {"on_click": save_and_exit, "tooltip": "Save game and exit to menu"}),
        )

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal_new_hole()

        # Help overlay
        self.help = ModalHelp(
            "Golf — How to Play",
            [
                "Goal: Clear tableau piles across 1/3/9/18 holes for a low total score.",
                "Play: Move the top card of any tableau pile to the foundation",
                "if it is one rank higher or lower than the foundation top (suit doesn't matter).",
                "Wrap A↔K is controlled by the Around-the-Corner option on the options screen.",
                "Stock: Flip one to the foundation to start, and when stuck. No redeals.",
                "Scoring: If tableau is cleared, score = -remaining stock; else = remaining tableau count.",
                "Save&Exit lets you continue later; recent totals shown in Scores.",
                "Undo/Restart available from the toolbar. Press Esc/Close to dismiss help.",
            ],
        )

        # Lazy-load golf placeholder image
        self._golf_img_raw: Optional[pygame.Surface] = None
        self._golf_img_scaled: Optional[pygame.Surface] = None
        self._golf_img_size: Tuple[int, int] = (0, 0)
        # Fix panel height: Golf tableau starts with 5 rows; keep layout stable per hole
        self._tableau_rows_nominal: int = 5

    def _ensure_golf_image(self, size: Tuple[int, int]):
        """Load and scale the optional golf image if available.
        Looks for assets/images/golf.png relative to the package directory.
        """
        try:
            # Reload scale if size changed
            if self._golf_img_scaled is not None and self._golf_img_size == size:
                return
            # Load raw if needed
            if self._golf_img_raw is None:
                base = os.path.dirname(C.__file__)
                path = os.path.join(base, "assets", "images", "golf.png")
                if os.path.isfile(path):
                    s = pygame.image.load(path)
                    self._golf_img_raw = s.convert_alpha() if s.get_alpha() else s.convert()
                else:
                    self._golf_img_raw = None
            # Produce scaled variant
            if self._golf_img_raw is not None:
                if self._golf_img_raw.get_size() != size:
                    self._golf_img_scaled = pygame.transform.smoothscale(self._golf_img_raw, size)
                else:
                    self._golf_img_scaled = self._golf_img_raw
                self._golf_img_size = size
            else:
                self._golf_img_scaled = None
                self._golf_img_size = (0, 0)
        except Exception:
            self._golf_img_raw = None
            self._golf_img_scaled = None
            self._golf_img_size = (0, 0)

    # ----- Scroll helpers -----
    def _content_bottom_y(self) -> int:
        if isinstance(self._last_bottom_rect, pygame.Rect):
            return self._last_bottom_rect.bottom
        # Fallback: use screen height
        return C.SCREEN_H

    def _clamp_scroll(self):
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        if self.scroll_y > 0:
            self.scroll_y = 0
        # Horizontal clamp based on content bounds
        left, right = self._content_bounds_x()
        max_scroll_x = 20 - left
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        if self.scroll_x > max_scroll_x:
            self.scroll_x = max_scroll_x
        if self.scroll_x < min_scroll_x:
            self.scroll_x = min_scroll_x

    def _vertical_scrollbar(self):
        bottom = self._content_bottom_y()
        if bottom <= C.SCREEN_H:
            return None
        track_x = C.SCREEN_W - 12
        track_y = getattr(C, "TOP_BAR_H", 60)
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

    def _content_bounds_x(self) -> Tuple[int, int]:
        # Use last layout of tableau panel
        if isinstance(self._last_tableau_rect, pygame.Rect):
            return self._last_tableau_rect.left, self._last_tableau_rect.right
        # Fallback: treat current designed geometry
        return 0, C.SCREEN_W

    def _horizontal_scrollbar(self):
        left, right = self._content_bounds_x()
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

    # ----- Layout -----
    def compute_layout(self):
        # Layout is finalized during draw to reflect dynamic tableau height.
        # Provide a sensible initial placement and set fan to 50% overlap.
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar_h + 22)

        score_w = max(240, int(C.CARD_W * 2))
        left_margin = 16
        tab_left = left_margin + score_w + 16
        for i, t in enumerate(self.tableau):
            t.x = tab_left + i * (C.CARD_W + gap_x)
            t.y = top_y
            t.fan_y = max(12, int(C.CARD_H * 0.5))
        # Put stock/foundation below; switch positions horizontally (stock left, foundation right)
        self.stock_pile.x, self.stock_pile.y = tab_left, top_y + C.CARD_H * 3
        self.foundation.x, self.foundation.y = tab_left + 6 * (C.CARD_W + gap_x), self.stock_pile.y

    # ----- Persistence -----
    def _game_state(self) -> Dict[str, Any]:
        def dump_pile(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "version": 1,
            "around": self.around,
            "holes_total": self.holes_total,
            "current_hole": self.current_hole,
            "scores": list(self.scores),
            "tableau": [dump_pile(p) for p in self.tableau],
            "stock": dump_pile(self.stock_pile),
            "foundation": dump_pile(self.foundation),
            "message": self.message,
            "completed": False,
        }

    def _save_game(self, to_menu: bool = False):
        state = self._game_state()
        _safe_write_json(_golf_save_path(), state)
        if to_menu:
            from solitaire.scenes.game_options.golf_options import GolfOptionsScene
            self.next_scene = GolfOptionsScene(self.app)

    def _load_from_state(self, state: Dict[str, Any]):
        self.around = bool(state.get("around", False))
        self.holes_total = int(state.get("holes_total", 1))
        self.current_hole = int(state.get("current_hole", 1))
        self.scores = [int(x) for x in state.get("scores", [])]
        # Keep panels from shrinking on load; Golf deals 5 tableau rows
        self._tableau_rows_nominal = 5

        def mk(seq):
            return [C.Card(int(s), int(r), bool(f)) for (s, r, f) in seq]
        for i, t in enumerate(self.tableau):
            t.cards = mk(state.get("tableau", [[]]*7)[i])
        self.stock_pile.cards = mk(state.get("stock", []))
        self.foundation.cards = mk(state.get("foundation", []))
        self.message = state.get("message", "")
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        # Restart snapshot of loaded state
        self._initial_snapshot = self.record_snapshot()

    # ----- Deal / Restart -----
    def _clear(self):
        for p in self.tableau:
            p.cards.clear()
        self.stock_pile.cards.clear()
        self.foundation.cards.clear()
        self.message = ""

    def deal_new_hole(self):
        self._clear()
        deck = C.make_deck(shuffle=True)
        # Tableau: 7 columns, 5 face-up each
        for col in range(7):
            for r in range(5):
                c = deck.pop()
                c.face_up = True
                self.tableau[col].cards.append(c)
        # Freeze tableau panel height for this hole (prevents shrink as cards are removed)
        self._tableau_rows_nominal = 5
        # Stock: remaining deck, face-down
        for c in deck:
            c.face_up = False
        self.stock_pile.cards = deck
        # Foundation starts empty; first click on stock flips to foundation
        self.foundation.cards = []

        # Reset undo; capture restart snapshot
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()

    def restart_hole(self):
        if self._initial_snapshot is not None:
            self.restore_snapshot(self._initial_snapshot)
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self.message = ""

    def _new_game_reset(self):
        # Resets entire multi-hole game using current around+holes settings
        self.current_hole = 1
        self.scores = []
        # Remove any in-progress save and history unaffected
        try:
            if os.path.isfile(_golf_save_path()):
                os.remove(_golf_save_path())
        except Exception:
            pass
        self.deal_new_hole()

    # ----- Undo -----
    def record_snapshot(self) -> Dict[str, Any]:
        def dump(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "tab": [dump(t) for t in self.tableau],
            "stock": dump(self.stock_pile),
            "found": dump(self.foundation),
            "msg": self.message,
            "hole": self.current_hole,
            "scores": list(self.scores),
        }

    def restore_snapshot(self, snap: Dict[str, Any]):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, t in enumerate(self.tableau):
            t.cards = mk(snap["tab"][i])
        self.stock_pile.cards = mk(snap["stock"]) if snap.get("stock") is not None else []
        self.foundation.cards = mk(snap["found"]) if snap.get("found") is not None else []
        self.message = snap.get("msg", "")
        self.current_hole = int(snap.get("hole", self.current_hole))
        self.scores = [int(x) for x in snap.get("scores", self.scores)]

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ----- Rules / Moves -----
    def _foundation_rank(self) -> int:
        if not self.foundation.cards:
            return 0
        return self.foundation.cards[-1].rank

    def _is_playable(self, c: C.Card) -> bool:
        if not c.face_up:
            return False
        # Only top card of each tableau pile is playable
        for t in self.tableau:
            if t.cards and t.cards[-1] is c:
                break
        else:
            return False
        top = self._foundation_rank()
        if top == 0:
            return False  # need to flip stock first
        return _rank_adjacent(c.rank, top, self.around)

    def _any_moves_available(self) -> bool:
        if self._foundation_rank() == 0:
            return True if self.stock_pile.cards else False
        for t in self.tableau:
            if t.cards and self._is_playable(t.cards[-1]):
                return True
        return False

    def _score_for_current_hole(self) -> int:
        # If tableau cleared, score = -remaining stock count; else = remaining tableau count
        remaining_tab = sum(len(t.cards) for t in self.tableau)
        if remaining_tab == 0:
            return -len(self.stock_pile.cards)
        return remaining_tab

    def _complete_hole(self):
        sc = self._score_for_current_hole()
        self.scores.append(int(sc))
        total = sum(self.scores)
        self.message = f"Hole {self.current_hole} complete. Score {sc} (Total {total})."
        # Save progress (so user can continue the next hole later)
        st = self._game_state()
        _safe_write_json(_golf_save_path(), st)
        # If last hole, finalize game and archive score history
        if self.current_hole >= self.holes_total:
            self._finalize_game_history(total)
            # Clear save since game completed
            try:
                if os.path.isfile(_golf_save_path()):
                    os.remove(_golf_save_path())
            except Exception:
                pass

    def _finalize_game_history(self, total_score: int):
        rec = {
            "holes": self.holes_total,
            "around": self.around,
            "total": total_score,
        }
        hist = _safe_read_json(_golf_history_path())
        if not isinstance(hist, list):
            hist = []
        hist.append(rec)
        # Keep only last 10
        hist = hist[-10:]
        _safe_write_json(_golf_history_path(), hist)

    def _check_end_conditions(self):
        if sum(len(t.cards) for t in self.tableau) == 0:
            self._complete_hole()
            return
        # If stock empty and no moves available -> hole complete
        if not self.stock_pile.cards and not self._any_moves_available():
            self._complete_hole()

    # ----- Events -----
    def handle_event(self, e):
        # Help overlay intercepts input
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return
        if self.toolbar.handle_event(e):
            return
        if self.ui_helper.handle_shortcuts(e):
            return
        # Scroll wheel for content
        if e.type == pygame.MOUSEWHEEL:
            # Keep vertical: up => content down (positive scroll_y)
            self.scroll_y += e.y * 60
            # Invert horizontal: left => content moves right
            try:
                self.scroll_x -= e.x * 60
            except Exception:
                pass
            self._clamp_scroll()
            return
        # Scrollbar drag
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, *_ = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    return
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, *_ = hsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_hscroll = True
                    return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._drag_vscroll = False
            self._drag_hscroll = False
        if e.type == pygame.MOUSEMOTION and self._drag_vscroll:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                t = (e.pos[1] - track_y - knob_h / 2) / max(1, (track_h - knob_h))
                t = max(0.0, min(1.0, t))
                self.scroll_y = min_sy + t * (max_sy - min_sy)
                self._clamp_scroll()
        if e.type == pygame.MOUSEMOTION and self._drag_hscroll:
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                t = (e.pos[0] - track_x - knob_w / 2) / max(1, (track_w - knob_w))
                t = max(0.0, min(1.0, t))
                self.scroll_x = min_sx + t * (max_sx - min_sx)
                self._clamp_scroll()
        if e.type == pygame.KEYDOWN:
            self.ui_helper.handle_shortcuts(e)

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y  # convert to world coords for hit-tests
            # Click stock to flip to foundation
            if self.stock_pile.top_rect().collidepoint((mxw, myw)):
                if self.stock_pile.cards:
                    self.push_undo()
                    c = self.stock_pile.cards.pop()
                    c.face_up = True
                    self.foundation.cards.append(c)
                    self._check_end_conditions()
                return
            # Click tableau playable card to move to foundation
            for t in self.tableau:
                if not t.cards:
                    continue
                top_i = len(t.cards) - 1
                r = t.rect_for_index(top_i)
                if r.collidepoint((mxw, myw)) and self._is_playable(t.cards[-1]):
                    self.push_undo()
                    c = t.cards.pop()
                    # already face_up
                    self.foundation.cards.append(c)
                    self._check_end_conditions()
                    return
            # If hole completed and not final, clicking message area can advance
            if self._can_advance_hole() and self._next_button_rect().collidepoint((mx, my)):
                self._advance_to_next_hole()
                return
            if self._is_game_complete() and self._finish_button_rect().collidepoint((mx, my)):
                from solitaire.scenes.game_options.golf_options import GolfOptionsScene
                self.next_scene = GolfOptionsScene(self.app)
                return

    # ----- Hole advancement -----
    def _can_advance_hole(self) -> bool:
        return (len(self.scores) >= self.current_hole) and (self.current_hole < self.holes_total)

    def _is_game_complete(self) -> bool:
        return (len(self.scores) >= self.holes_total)

    def _advance_to_next_hole(self):
        if not self._can_advance_hole():
            return
        self.current_hole += 1
        self.deal_new_hole()

    # ----- Drawing helpers -----
    def _draw_score_grid(self, screen: pygame.Surface, panel_rect: pygame.Rect):
        """Draw score grid with no outer border lines, thicker internals, centered text."""
        # Inset grid so we don't overlap the rounded panel border
        inset = 6
        inner = pygame.Rect(panel_rect.x + inset, panel_rect.y + inset,
                            panel_rect.w - 2 * inset, panel_rect.h - 2 * inset)
        rows = 1 + 19
        row_h = max(22, int(inner.h / rows))

        # Two columns; first is 'Hole', second 'Score'
        col1_w = max(90, int(inner.w * 0.5))
        col2_w = inner.w - col1_w

        grid_col = (225, 225, 232)  # slightly brighter for thicker lines
        h_thick = 4  # horizontal separators
        v_thick = 4  # vertical divider

        # Horizontal lines (skip top and bottom to avoid table border)
        for r in range(1, rows):
            y = inner.y + r * row_h
            pygame.draw.line(screen, grid_col, (inner.x, y), (inner.right, y), width=h_thick)

        # Vertical divider only (no left/right table borders)
        divider_x = inner.x + col1_w
        pygame.draw.line(screen, grid_col, (divider_x, inner.y), (divider_x, inner.bottom), v_thick)

        # Header labels centered (white for contrast)
        hdr_hole = C.FONT_SMALL.render("Hole", True, C.WHITE)
        hdr_score = C.FONT_SMALL.render("Score", True, C.WHITE)
        hdr_y = inner.y + (row_h - hdr_hole.get_height()) // 2
        hole_cx = inner.x + col1_w // 2
        score_cx = inner.x + col1_w + col2_w // 2
        screen.blit(hdr_hole, (hole_cx - hdr_hole.get_width() // 2, hdr_y))
        screen.blit(hdr_score, (score_cx - hdr_score.get_width() // 2, hdr_y))

        # Body rows
        total_so_far = sum(self.scores)
        for i in range(19):
            ry = inner.y + row_h * (i + 1)
            if i < 18:
                hole_num = i + 1
                hole_label = str(hole_num) if hole_num <= self.holes_total else ""
                hole_score = ""
                if hole_num <= self.holes_total and hole_num <= len(self.scores):
                    hole_score = str(self.scores[hole_num - 1])
                t1 = C.FONT_SMALL.render(hole_label, True, C.WHITE)
                t2 = C.FONT_SMALL.render(hole_score, True, C.WHITE)
            else:
                t1 = C.FONT_SMALL.render("Total", True, C.WHITE)
                t2 = C.FONT_SMALL.render(str(total_so_far), True, C.WHITE)

            c1_y = ry + (row_h - t1.get_height()) // 2
            c2_y = ry + (row_h - t2.get_height()) // 2
            screen.blit(t1, (hole_cx - t1.get_width() // 2, c1_y))
            screen.blit(t2, (score_cx - t2.get_width() // 2, c2_y))

    def _next_button_rect(self) -> pygame.Rect:
        w, h = 160, 36
        rect = pygame.Rect(0, 0, w, h)
        rect.centerx = C.SCREEN_W // 2
        rect.y = C.SCREEN_H - h - 14
        return rect

    def _finish_button_rect(self) -> pygame.Rect:
        w, h = 220, 36
        rect = pygame.Rect(0, 0, w, h)
        rect.centerx = C.SCREEN_W // 2
        rect.y = C.SCREEN_H - h - 14
        return rect

    # ----- Draw -----
    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Title and info
        extra = f"Holes: {self.holes_total} — Hole {self.current_hole}/{self.holes_total}  |  Around: {'On' if self.around else 'Off'}"

        # Dynamic layout calculations for panels (world coordinates)
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar_h + 22)
        left_margin = 16
        pad_score = 12
        pad_tab = 18   # extra space inside tableau border
        pad_bottom = 8
        border_w = 4   # thicker borders
        score_w = max(240, int(C.CARD_W * 2))
        # Tableau geometry
        tab_sep = 24   # more space between score and tableau
        tab_left = left_margin + score_w + tab_sep   # border left of tableau panel
        tab_width = 7 * C.CARD_W + 6 * gap_x         # content width of 7 columns
        # Update tableau pile positions and overlap (50%), add inner padding from border
        for i, t in enumerate(self.tableau):
            t.x = tab_left + pad_tab + i * (C.CARD_W + gap_x)
            t.y = top_y + pad_tab
            t.fan_y = max(12, int(C.CARD_H * 0.5))
        # Compute tableau panel height from nominal rows, not current cards
        rows_nominal = max(1, getattr(self, "_tableau_rows_nominal", 5))
        tab_height = (pad_tab * 2) + C.CARD_H + max(0, rows_nominal - 1) * self.tableau[0].fan_y

        # Panel rects (ensure equal padding on all sides of tableau content)
        tableau_rect = pygame.Rect(tab_left, top_y, tab_width + 2 * pad_tab, tab_height)
        score_rect = pygame.Rect(left_margin, tableau_rect.y, score_w, tableau_rect.h)

        # Stock/Foundation panel centered horizontally under tableau
        bottom_gap = 22
        bottom_h = C.CARD_H + 2 * pad_bottom
        small_gap = max(12, int(gap_x * 0.9))
        # Compute total width needed to include stock, gap, foundation and padding
        bottom_w = 2 * C.CARD_W + small_gap + 2 * pad_bottom
        bottom_left = tableau_rect.centerx - bottom_w // 2
        bottom_top = tableau_rect.bottom + bottom_gap
        bottom_rect = pygame.Rect(bottom_left, bottom_top, bottom_w, bottom_h)
        # Position piles inside the bottom panel (stock left, foundation right)
        stock_x = bottom_left + pad_bottom
        foundation_x = bottom_left + bottom_w - pad_bottom - C.CARD_W

        # Store last geometry for scroll metrics
        self._last_tableau_rect = tableau_rect.copy()
        self._last_score_rect = score_rect.copy()
        self._last_bottom_rect = bottom_rect.copy()

        # Apply vertical scroll offset for drawing
        sy = int(self.scroll_y)
        sx = int(self.scroll_x)
        tableau_rect_draw = tableau_rect.move(sx, sy)
        score_rect_draw = score_rect.move(0, sy)
        bottom_rect_draw = bottom_rect.move(sx, sy)

        # Place stock (left) and foundation (right) inside bottom panel; switched positions horizontally
        self.stock_pile.x = stock_x
        self.stock_pile.y = bottom_rect.y + pad_bottom
        self.foundation.x = foundation_x
        self.foundation.y = bottom_rect.y + pad_bottom

        # Draw panel outlines
        for r in (score_rect_draw, tableau_rect_draw, bottom_rect_draw):
            pygame.draw.rect(screen, C.WHITE, r, width=border_w, border_radius=14)

        # Draw tableau piles within tableau panel
        C.DRAW_OFFSET_X = sx
        C.DRAW_OFFSET_Y = sy
        for t in self.tableau:
            t.draw(screen)

        # Draw stock and foundation in bottom panel (no labels)
        self.stock_pile.draw(screen)
        self.foundation.draw(screen)
        C.DRAW_OFFSET_Y = 0

        # Draw score grid in left panel
        self._draw_score_grid(screen, score_rect_draw)

        # Golf image: fixed 256x256 square centered at the intersection of
        #   - vertical center line of the score panel, and
        #   - horizontal center line of the stock pile.
        side = 200
        center_x = score_rect_draw.centerx
        center_y = self.stock_pile.y + C.CARD_H // 2 + sy
        ph_rect = pygame.Rect(0, 0, side, side)
        ph_rect.center = (int(center_x), int(center_y))

        # Try to draw the provided image at assets/images/golf.png (transparent PNG; no border/background)
        self._ensure_golf_image((side, side))
        if self._golf_img_scaled is not None:
            screen.blit(self._golf_img_scaled, ph_rect)
        else:
            # Fallback placeholder
            pygame.draw.rect(screen, (245,245,245), ph_rect, border_radius=10)
            pygame.draw.rect(screen, (180,180,190), ph_rect, width=1, border_radius=10)
            txt = C.FONT_SMALL.render("Golf img", True, (40,40,50))
            screen.blit(txt, (ph_rect.centerx - txt.get_width()//2, ph_rect.centery - txt.get_height()//2))

        # Completion buttons
        if self._can_advance_hole():
            r = self._next_button_rect()
            pygame.draw.rect(screen, (230,230,235), r, border_radius=8)
            pygame.draw.rect(screen, (160,160,170), r, 1, border_radius=8)
            txt = C.FONT_UI.render("Next Hole", True, (30,30,35))
            screen.blit(txt, (r.centerx - txt.get_width()//2, r.centery - txt.get_height()//2))
        elif self._is_game_complete():
            r = self._finish_button_rect()
            pygame.draw.rect(screen, (230,230,235), r, border_radius=8)
            pygame.draw.rect(screen, (160,160,170), r, 1, border_radius=8)
            txt = C.FONT_UI.render("Back to Golf Menu", True, (30,30,35))
            screen.blit(txt, (r.centerx - txt.get_width()//2, r.centery - txt.get_height()//2))

        # Win/target thresholds messaging when game complete
        if self._is_game_complete():
            total = sum(self.scores)
            target = {18: 72, 9: 32, 3: 18, 1: 0}.get(self.holes_total, 0)
            win = total < target
            msg = f"Game complete. Total {total}. Target < {target}. {'You win!' if win else 'Try again!'}"
            msg_s = C.FONT_UI.render(msg, True, (255,255,180))
            screen.blit(msg_s, (C.SCREEN_W//2 - msg_s.get_width()//2, C.SCREEN_H - 60))
        elif self.message:
            msg_s = C.FONT_UI.render(self.message, True, (255,255,180))
            screen.blit(msg_s, (C.SCREEN_W//2 - msg_s.get_width()//2, C.SCREEN_H - 60))

        # Reset offsets for UI
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0

        # Vertical scrollbar (if content extends beyond view)
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)
        # Horizontal scrollbar (if content wider than view)
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Top bar and toolbar
        C.Scene.draw_top_bar(self, screen, "Golf", extra)
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)


class GolfScoresScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.b_back = C.Button("Back", C.SCREEN_W//2 - 160, C.SCREEN_H - 80, w=320, h=48)
        self._hist = _safe_read_json(_golf_history_path())
        if not isinstance(self._hist, list):
            self._hist = []

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_back.hovered((mx, my)):
                from solitaire.scenes.game_options.golf_options import GolfOptionsScene
                self.next_scene = GolfOptionsScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.game_options.golf_options import GolfOptionsScene
            self.next_scene = GolfOptionsScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Golf - Recent Scores", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 100))

        y = 170
        if not self._hist:
            t = C.FONT_UI.render("No completed games yet.", True, C.WHITE)
            screen.blit(t, (C.SCREEN_W//2 - t.get_width()//2, y))
        else:
            # Show last up to 10
            start_x = C.SCREEN_W//2 - 280
            header = C.FONT_UI.render("Holes    Around    Total", True, C.WHITE)
            screen.blit(header, (start_x, y)); y += header.get_height() + 6
            for rec in self._hist[-10:]:
                holes = int(rec.get("holes", 0))
                around = "On" if rec.get("around", False) else "Off"
                total = int(rec.get("total", 0))
                line = C.FONT_SMALL.render(f"{holes:<8} {around:<9} {total:>5}", True, C.WHITE)
                screen.blit(line, (start_x, y)); y += line.get_height() + 4

        mp = pygame.mouse.get_pos()
        self.b_back.draw(screen, hover=self.b_back.hovered(mp))
