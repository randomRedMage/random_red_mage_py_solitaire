"""
tripeaks.py - TriPeaks (Tri-Towers) solitaire

Rules (implemented):
- Tableau has 4 rows sized [3, 6, 9, 10] forming three peaks above a base.
- Bottom row starts face-up; upper rows start face-down and flip when uncovered.
- One stock pile and one waste pile. Deal the first stock card to waste at start.
- You may move any free, face-up tableau card whose rank is adjacent (±1 with wrap A↔K)
  to the waste top; moved cards become the new waste top.
- Click stock to deal next card to waste when stuck. No redeals when stock is empty.
- Win by clearing all tableau cards.
"""

from typing import List, Optional, Tuple
import pygame
from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT


def rank_adjacent(a: int, b: int) -> bool:
    if a == b:
        return False
    # adjacency with wrap A(1) <-> K(13)
    return abs(a - b) == 1 or (a == 1 and b == 13) or (a == 13 and b == 1)


# -----------------------------
# Options Scene
# -----------------------------
class TriPeaksOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 210
        y = 300
        # Option: allow A↔K wrap (play a King on an Ace)
        self.wrap_ak = True
        self.b_start = C.Button("Start TriPeaks", cx, y, w=420); y += 60
        self.b_wrap  = C.Button("Wrap A↔K: On", cx, y, w=420); y += 60
        self.b_back = C.Button("Back", cx, y, w=420)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self.next_scene = TriPeaksGameScene(self.app, wrap_ak=self.wrap_ak)
            elif self.b_wrap.hovered((mx, my)):
                self.wrap_ak = not self.wrap_ak
                self.b_wrap.text = f"Wrap A↔K: {'On' if self.wrap_ak else 'Off'}"
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("TriPeaks - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_wrap, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))


# -----------------------------
# Game Scene
# -----------------------------
class TriPeaksGameScene(C.Scene):
    def __init__(self, app, wrap_ak: bool = True):
        super().__init__(app)
        self.wrap_ak = wrap_ak

        # Scroll (vertical + slight horizontal, similar to Pyramid)
        self.scroll_x: int = 0
        self.scroll_y: int = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._panning = False
        self._pan_anchor = (0, 0)
        self._scroll_anchor = (0, 0)

        # Tableau rows: sizes [3, 6, 9, 10]
        self.rows: List[List[Optional[C.Card]]] = []

        # Layout params
        self.top_y: int = 110
        self.overlap_y: int = int(C.CARD_H * 0.48)
        self.inner_gap_x: int = getattr(C, "CARD_GAP_X", max(10, C.CARD_W // 8))
        self.center_x: int = C.SCREEN_W // 2

        # Piles
        self.stock_pile = C.Pile(0, 0)
        self.waste_pile = C.Pile(0, 0)

        # Undo and UI
        self.undo_mgr = C.UndoManager()
        self.message: str = ""

        def goto_menu():
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

        def can_undo():
            return self.undo_mgr.can_undo()

        def can_hint():
            return self.any_moves_available()

        actions = {
            "Menu":    {"on_click": goto_menu},
            "New":     {"on_click": self.new_game},
            "Restart": {"on_click": self.restart_deal, "tooltip": "Restart current deal"},
            "Undo":    {"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            "Hint":    {"on_click": self.show_hint, "enabled": can_hint, "tooltip": "Show a playable card"},
        }
        self.toolbar = make_toolbar(
            actions,
            height=DEFAULT_BUTTON_HEIGHT,
            margin=(10, 8),
            gap=8,
            align="right",
            width_provider=lambda: C.SCREEN_W,
        )

        # Hint selection: store (row_index, idx) pairs
        self.hint_cells: Optional[List[Tuple[int, int]]] = None
        self.hint_expires_at: int = 0

        # Deal
        self.compute_layout()
        self.deal()
        self._initial_order: List[Tuple[int, int]] = self._deck_order_snapshot[:]
        self.undo_mgr = C.UndoManager()
        self.push_undo()

    # ---------- Layout ----------
    def compute_layout(self):
        self.center_x = C.SCREEN_W // 2
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        self.top_y = max(90, top_bar_h + 20)
        self.overlap_y = int(C.CARD_H * 0.48)
        self.inner_gap_x = getattr(C, "CARD_GAP_X", max(10, C.CARD_W // 8))

        # Position stock/waste centered below the tableau
        base_y = self.top_y + 3 * self.overlap_y + C.CARD_H + getattr(C, "CARD_GAP_Y", 26)
        group_w = 2 * C.CARD_W + self.inner_gap_x
        left_x = self.center_x - group_w // 2
        self.stock_pile.x, self.stock_pile.y = left_x, base_y
        self.waste_pile.x, self.waste_pile.y = left_x + C.CARD_W + self.inner_gap_x, base_y

    def _content_bounds_x(self) -> Tuple[int, int]:
        # Compute bounds from actual positioned cards to account for extra gaps
        left = 10**9
        right = -10**9
        for r, row in enumerate(self.rows if self.rows else [[], [], [], [None]*10]):
            n = len(row) if row else [3, 6, 9, 10][r]
            for i in range(n):
                x, _ = self.pos_for(r, i)
                left = min(left, x)
                right = max(right, x + C.CARD_W)
        # include piles
        left = min(left, self.stock_pile.x)
        right = max(right, self.waste_pile.x + C.CARD_W)
        return left, right

    def _content_bottom_y(self) -> int:
        bottom_tableau = self.top_y + 3 * self.overlap_y + C.CARD_H
        piles_bottom = self.stock_pile.y + C.CARD_H
        return max(bottom_tableau, piles_bottom)

    def _clamp_scroll(self):
        # Clamp Y
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        if self.scroll_y > 0:
            self.scroll_y = 0
        # Clamp X
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

    def _horizontal_scrollbar(self):
        left, right = self._content_bounds_x()
        if right - left <= C.SCREEN_W - 40:
            return None
        track_x = 10
        track_w = C.SCREEN_W - 20
        track_y = C.SCREEN_H - 10
        track_rect = pygame.Rect(track_x, track_y - 6, track_w, 6)
        view_w = C.SCREEN_W
        content_w = right - left + 40
        knob_w = max(30, int(track_w * (view_w / max(view_w, content_w))))
        max_scroll_x = 20 - left
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        denom = (max_scroll_x - min_scroll_x)
        t = (self.scroll_x - min_scroll_x) / denom if denom != 0 else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        knob_rect = pygame.Rect(knob_x, track_y - 6, knob_w, 6)
        return track_rect, knob_rect, min_scroll_x, max_scroll_x, track_x, track_w, knob_w

    # ---------- Deal / Restart ----------
    def _clear(self):
        self.rows = []
        self.stock_pile.cards = []
        self.waste_pile.cards = []
        self.message = ""
        self.hint_cells = None

    def deal(self, preset_order: Optional[List[Tuple[int, int]]] = None):
        self._clear()
        if preset_order is None:
            deck = C.make_deck(shuffle=True)
            self._deck_order_snapshot = [(c.suit, c.rank) for c in deck]
        else:
            deck = [C.Card(s, r, False) for (s, r) in preset_order]
            self._deck_order_snapshot = preset_order[:]

        # Build rows sizes [3, 6, 9, 10]
        sizes = [3, 6, 9, 10]
        k = 0
        self.rows = []
        for ri, n in enumerate(sizes):
            row: List[Optional[C.Card]] = []
            for _ in range(n):
                c = deck[k]; k += 1
                # bottom row face-up; others start face-down
                c.face_up = (ri == 3)
                row.append(c)
            self.rows.append(row)

        # Remaining cards become stock (face-down)
        self.stock_pile.cards = deck[k:]
        for c in self.stock_pile.cards:
            c.face_up = False

        # Deal first waste card
        if self.stock_pile.cards:
            c0 = self.stock_pile.cards.pop()
            c0.face_up = True
            self.waste_pile.cards.append(c0)

    def new_game(self):
        self.deal()
        self.undo_mgr = C.UndoManager()
        self.push_undo()

    def restart_deal(self):
        if getattr(self, "_deck_order_snapshot", None):
            self.deal(self._deck_order_snapshot[:])
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ---------- Undo ----------
    def record_snapshot(self):
        return {
            "rows": [[(c.suit, c.rank, c.face_up) if c is not None else None for c in row] for row in self.rows],
            "stock": [(c.suit, c.rank, c.face_up) for c in self.stock_pile.cards],
            "waste": [(c.suit, c.rank, c.face_up) for c in self.waste_pile.cards],
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        rows: List[List[Optional[C.Card]]] = []
        for row in snap["rows"]:
            rr: List[Optional[C.Card]] = []
            for t in row:
                if t is None:
                    rr.append(None)
                else:
                    s, r, f = t
                    rr.append(C.Card(s, r, f))
            rows.append(rr)
        self.rows = rows

        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        self.stock_pile.cards = mk(snap["stock"])  # face_down by stored flags
        self.waste_pile.cards = mk(snap["waste"])  # top is last
        self.scroll_x = snap.get("scroll_x", 0)
        self.scroll_y = snap.get("scroll_y", 0)
        self.message = snap.get("message", "")
        self.hint_cells = None

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ---------- Helpers ----------
    def pos_for(self, r: int, i: int) -> Tuple[int, int]:
        """Position cards using a group-based TriPeaks layout:
        - Row 3 (bottom): 10 cards at slots 0..9
        - Row 2: 9 cards at half-slots 0.5..8.5 (3,3,3 groups)
        - Row 1: 6 cards grouped as (2,2,2) at slots [1,2], [4,5], [7,8]
        - Row 0 (top): 3 cards at slots 1.5, 4.5, 7.5
        A "slot" is measured in multiples of (card_width + inner_gap_x) from the left edge
        of the bottom row.
        """
        step_x = C.CARD_W + self.inner_gap_x
        bottom_w = 10 * C.CARD_W + 9 * self.inner_gap_x
        left_base = self.center_x - bottom_w // 2

        # Determine fractional slot index s for (r, i)
        if r == 3:
            s = float(i)
        elif r == 2:
            s = i + 0.5
        elif r == 1:
            g = i // 2  # group 0..2
            k = i % 2   # position within group
            s = 1.0 + 3.0 * g + k
        elif r == 0:
            s = 1.5 + 3.0 * i
        else:
            s = float(i)

        x = int(left_base + s * step_x)
        y = self.top_y + r * self.overlap_y
        return x, y

    def children_indices(self, r: int, i: int) -> List[Tuple[int, int]]:
        # Respect the grouped geometry so flipping works with the visual layout
        if r == 0:
            # top -> row1 pairs within each peak
            return [(1, 2 * i), (1, 2 * i + 1)]
        if r == 1:
            # row1 -> row2 (3 per group). Map pair index to two beneath within same group
            g = i // 2
            k = i % 2
            return [(2, 3 * g + k), (2, 3 * g + k + 1)]
        if r == 2:
            # row2 -> bottom: standard adjacent mapping
            return [(3, i), (3, i + 1)]
        return []

    def is_free(self, r: int, i: int) -> bool:
        card = self.rows[r][i]
        if card is None:
            return False
        for (cr, ci) in self.children_indices(r, i):
            child = self.rows[cr][ci]
            if child is not None:
                return False
        return True

    def waste_top(self) -> Optional[C.Card]:
        return self.waste_pile.cards[-1] if self.waste_pile.cards else None

    def _adjacent(self, a: int, b: int) -> bool:
        if a == b:
            return False
        if abs(a - b) == 1:
            return True
        if self.wrap_ak and ((a == 1 and b == 13) or (a == 13 and b == 1)):
            return True
        return False

    def can_play(self, card: C.Card) -> bool:
        top = self.waste_top()
        if top is None:
            return True  # shouldn't happen; we always have a waste top after deal
        return self._adjacent(card.rank, top.rank)

    def any_moves_available(self) -> bool:
        top = self.waste_top()
        if top is None:
            return True
        for r, row in enumerate(self.rows):
            for i, c in enumerate(row):
                if c and c.face_up and self.is_free(r, i) and self._adjacent(c.rank, top.rank):
                    return True
        return False

    def _flip_newly_uncovered(self):
        # Any card whose children are all None becomes face_up
        for r in range(2, -1, -1):  # check upper rows
            for i, c in enumerate(self.rows[r]):
                if c and not c.face_up:
                    ch = self.children_indices(r, i)
                    if all(self.rows[cr][ci] is None for (cr, ci) in ch):
                        c.face_up = True

    def _after_move_checks(self):
        # Win when all rows are cleared
        if all(c is None for row in self.rows for c in row):
            self.message = "🎉 You win!"
            return
        # If no stock and no moves, game over
        if not self.stock_pile.cards and not self.any_moves_available():
            self.message = "Game Over"

    # ---------- Hint ----------
    def show_hint(self):
        top = self.waste_top()
        self.hint_cells = None
        if not top:
            return
        for r, row in enumerate(self.rows):
            for i, c in enumerate(row):
                if c and c.face_up and self.is_free(r, i) and self._adjacent(c.rank, top.rank):
                    self.hint_cells = [(r, i)]
                    self.hint_expires_at = pygame.time.get_ticks() + 2000
                    return

    # ---------- Drawing ----------
    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Expire hint
        if self.hint_cells and pygame.time.get_ticks() > self.hint_expires_at:
            self.hint_cells = None

        # Apply draw offset for piles & tableau
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        # Draw tableau
        for r, row in enumerate(self.rows):
            for i, c in enumerate(row):
                if c is None:
                    continue
                x, y = self.pos_for(r, i)
                surf = C.get_card_surface(c) if c.face_up else C.get_back_surface()
                screen.blit(surf, (x + self.scroll_x, y + self.scroll_y))
                # Hint highlight
                if self.hint_cells and (r, i) in self.hint_cells:
                    rect = pygame.Rect(x + self.scroll_x, y + self.scroll_y, C.CARD_W, C.CARD_H)
                    pygame.draw.rect(screen, C.GOLD, rect, width=4, border_radius=C.CARD_RADIUS)

        # Draw piles
        self.stock_pile.draw(screen)
        self.waste_pile.draw(screen)

        # Reset offsets for UI
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0

        # Labels
        lab = C.FONT_SMALL.render("Stock", True, C.WHITE)
        screen.blit(lab, (self.stock_pile.x + (C.CARD_W - lab.get_width()) // 2 + self.scroll_x,
                          self.stock_pile.y - 22 + self.scroll_y))
        lab2 = C.FONT_SMALL.render("Waste", True, C.WHITE)
        screen.blit(lab2, (self.waste_pile.x + (C.CARD_W - lab2.get_width()) // 2 + self.scroll_x,
                           self.waste_pile.y - 22 + self.scroll_y))

        # Message
        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 40))

        # Vertical scrollbar
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)
        # Horizontal scrollbar
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Tooling: top bar + toolbar (draw last)
        C.Scene.draw_top_bar(self, screen, "TriPeaks")
        self.toolbar.draw(screen)

    # ---------- Events ----------
    def handle_event(self, e):
        # Toolbar first
        if hasattr(self, "toolbar") and self.toolbar.handle_event(e):
            return

        # Mouse wheel scrolling
        if e.type == pygame.MOUSEWHEEL:
            # Keep vertical: up => content down
            self.scroll_y += e.y * 60
            # Invert horizontal: left => content moves right
            try:
                self.scroll_x -= e.x * 60
            except Exception:
                pass
            self._clamp_scroll()
            return

        # Scrollbar interactions
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
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
            elif e.key == pygame.K_n:
                self.new_game()
            elif e.key == pygame.K_r:
                self.restart_deal()
            elif e.key == pygame.K_u:
                self.undo()

        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y

            # Stock click -> deal next
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mxw, myw)):
                if self.stock_pile.cards:
                    self.push_undo()
                    c = self.stock_pile.cards.pop()
                    c.face_up = True
                    self.waste_pile.cards.append(c)
                    self.message = ""
                else:
                    # no redeal; maybe game over check
                    if not self.any_moves_available():
                        self.message = "Game Over"
                return

            # Tableau click: prefer top-most visible cards (bottom row drawn last)
            for r in range(len(self.rows) - 1, -1, -1):
                row = self.rows[r]
                for i in range(len(row) - 1, -1, -1):
                    c = row[i]
                    if c is None:
                        continue
                    x, y = self.pos_for(r, i)
                    if pygame.Rect(x, y, C.CARD_W, C.CARD_H).collidepoint((mxw, myw)):
                        if c.face_up and self.is_free(r, i) and self.can_play(c):
                            self.push_undo()
                            # move to waste
                            self.rows[r][i] = None
                            self.waste_pile.cards.append(C.Card(c.suit, c.rank, True))
                            self._flip_newly_uncovered()
                            self.message = ""
                            self._after_move_checks()
                        return
