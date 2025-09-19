# freecell.py - FreeCell mode (options + game)
import pygame
from typing import List, Optional, Tuple
from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT, ModalHelp
from solitaire import mechanics as M


def is_red(suit: int) -> bool:
    return suit in (1, 2)


class FreeCellOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 210
        y = 300
        # Use width 420 to center like other option screens
        self.b_start = C.Button("Start FreeCell", cx, y, w=420); y += 70
        self.b_back = C.Button("Back", cx, y, w=420)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self.next_scene = FreeCellGameScene(self.app)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("FreeCell - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))


class FreeCellGameScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)

        # Scrolling (support tall columns and wide layouts)
        self.scroll_x = 0
        self.scroll_y = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._hscroll_drag_dx = 0
        self._hscroll_geom = None

        # Piles
        self.freecells: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        # Dedicated foundation suits left-to-right: [Spades, Hearts, Diamonds, Clubs]
        self.foundation_suits: List[int] = [0, 1, 2, 3]
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=max(24, C.CARD_H // 5)) for _ in range(8)]

        # Drag state: (stack, src_kind, src_index)
        self.drag_stack: Optional[Tuple[List[C.Card], str, int]] = None
        self.drag_offset = (0, 0)
        self.peek = M.PeekController(delay_ms=2000)

        # Undo manager
        self.undo_mgr = C.UndoManager()

        # Toolbar
        def goto_menu():
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

        def can_undo():
            return self.undo_mgr.can_undo()

        actions = {
            "Menu":    {"on_click": goto_menu},
            "New":     {"on_click": self.deal_new},
            "Restart": {"on_click": self.restart, "tooltip": "Restart current deal"},
            "Undo":    {"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            "Auto":    {"on_click": self.auto_to_foundations, "tooltip": "Auto-move available cards to foundations"},
            "Help":    {"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        }
        self.toolbar = make_toolbar(
            actions,
            height=DEFAULT_BUTTON_HEIGHT,
            margin=(10, 8),
            gap=8,
            align="right",
            width_provider=lambda: C.SCREEN_W,
        )

        self.message = ""
        self.compute_layout()
        self.deal_new()
        # Double-click tracking
        self._last_click_time = 0
        self._last_click_pos = (0, 0)

        # Help overlay
        self.help = ModalHelp(
            "FreeCell — How to Play",
            [
                "Goal: Build up four foundations A→K by suit.",
                "Tableau: Build down by rank with alternating colors.",
                "Empty column accepts any card or a valid descending run.",
                "Free cells: Four cells each hold one card to help maneuver.",
                "You can drag runs; movable length depends on empty cells and columns.",
                "Double-click a safe top card to move to a foundation.",
                "Use Auto to move obvious cards to foundations. Undo/Restart available.",
                "Press H to close this help.",
            ],
        )
        # Edge panning while dragging near screen edges
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 60))

    # ----- Layout -----
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        # Leave generous space below the top bar so labels and card tops don't overlap it
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(100, top_bar_h + 40)

        # Extra separation between FreeCells group (left) and Foundations group (right)
        group_gap = max(int(C.CARD_W * 0.8), 60)

        # Top row: 4 free cells (left), 4 foundations (right) with extra group gap
        total_w = 8 * C.CARD_W + 7 * gap_x + group_gap
        left_x = (C.SCREEN_W - total_w) // 2
        # Freecells
        for i in range(4):
            x = left_x + i * (C.CARD_W + gap_x)
            self.freecells[i].x, self.freecells[i].y = x, top_y
        # Foundations
        for i in range(4):
            x = left_x + 4 * (C.CARD_W + gap_x) + group_gap + i * (C.CARD_W + gap_x)
            self.foundations[i].x, self.foundations[i].y = x, top_y

        # Tableau under top row
        base_y = top_y + C.CARD_H + getattr(C, "CARD_GAP_Y", 26)
        for i in range(8):
            x = left_x + i * (C.CARD_W + gap_x)
            self.tableau[i].x, self.tableau[i].y = x, base_y

    # ----- Deal / Restart -----
    def _clear(self):
        for p in self.tableau:
            p.cards.clear()
        for p in self.freecells:
            p.cards.clear()
        for p in self.foundations:
            p.cards.clear()
        self.drag_stack = None
        self.message = ""

    def deal_new(self):
        self._clear()
        deck = C.make_deck(shuffle=True)
        # Remember initial order for restart
        self._initial_order = [(c.suit, c.rank) for c in deck]
        for idx, c in enumerate(deck):
            c.face_up = True
            col = idx % 8
            self.tableau[col].cards.append(c)
        # reset undo
        self.undo_mgr = C.UndoManager()
        self.push_undo()

    def restart(self):
        if getattr(self, "_initial_order", None):
            deck = [C.Card(s, r, True) for (s, r) in self._initial_order]
            self._clear()
            for idx, c in enumerate(deck):
                col = idx % 8
                self.tableau[col].cards.append(c)
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ----- Undo -----
    def record_snapshot(self):
        return {
            "freecells": [[(c.suit, c.rank, c.face_up) for c in p.cards] for p in self.freecells],
            "foundations": [[(c.suit, c.rank, c.face_up) for c in p.cards] for p in self.foundations],
            "tableau": [[(c.suit, c.rank, c.face_up) for c in p.cards] for p in self.tableau],
            "message": self.message,
            "scroll_y": self.scroll_y,
        }

    def restore_snapshot(self, snap):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, p in enumerate(self.freecells):
            p.cards = mk(snap["freecells"][i])
        for i, p in enumerate(self.foundations):
            p.cards = mk(snap["foundations"][i])
        for i, p in enumerate(self.tableau):
            p.cards = mk(snap["tableau"][i])
        self.message = snap.get("message", "")
        self.scroll_y = snap.get("scroll_y", 0)

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ----- Rules -----
    def _can_stack_tableau(self, upper: C.Card, lower: Optional[C.Card]) -> bool:
        if lower is None:
            return True  # empty target column accepts any rank in FreeCell
        # Alternating colors, descending by 1
        return (is_red(upper.suit) != is_red(lower.suit)) and (upper.rank == lower.rank - 1)

    def _can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        # Enforce dedicated suit per foundation index
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        f = self.foundations[fi]
        if not f.cards:
            return card.rank == 1  # Ace of the required suit
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _maybe_handle_double_click(self, e, mx: int, myw: int) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - getattr(self, "_last_click_time", 0) <= 350
            and abs(e.pos[0] - getattr(self, "_last_click_pos", (0, 0))[0]) <= 6
            and abs(e.pos[1] - getattr(self, "_last_click_pos", (0, 0))[1]) <= 6
        )
        handled = False
        if double:
            # Freecell tops
            for ci, cell in enumerate(self.freecells):
                if cell.cards and cell.top_rect().collidepoint((mx, myw)):
                    c = cell.cards[-1]
                    fi = self._foundation_index_for_suit(c.suit)
                    if self._can_move_to_foundation(c, fi):
                        self.push_undo()
                        cell.cards.pop()
                        self.foundations[fi].cards.append(c)
                        handled = True
                        break
            # Tableau tops
            if not handled:
                for ti, t in enumerate(self.tableau):
                    hi = t.hit((mx, myw))
                    if hi is None:
                        continue
                    if hi == -1 and t.cards:
                        hi = len(t.cards) - 1
                    if hi == len(t.cards) - 1 and t.cards[hi].face_up:
                        c = t.cards[-1]
                        fi = self._foundation_index_for_suit(c.suit)
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            t.cards.pop()
                            self.foundations[fi].cards.append(c)
                            handled = True
                            break
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    def _is_valid_sequence(self, seq: List[C.Card]) -> bool:
        # Strictly descending by 1, alternating colors
        for i in range(len(seq) - 1):
            a, b = seq[i], seq[i + 1]
            if not (is_red(a.suit) != is_red(b.suit) and a.rank == b.rank + 1):
                return False
        return True

    def _max_movable(self, target_is_empty: bool) -> int:
        empty_cells = sum(1 for p in self.freecells if not p.cards)
        empty_cols = sum(1 for p in self.tableau if not p.cards)
        if target_is_empty and empty_cols > 0:
            empty_cols -= 1  # destination empty column is not a helper
        # (empty_cells + 1) * 2^(empty_cols)
        cap = (empty_cells + 1)
        # Avoid huge growth; practical boards keep this small
        for _ in range(empty_cols):
            cap *= 2
            if cap > 52:
                return 52
        return max(1, cap)

    # ----- Auto to foundation -----
    def auto_to_foundations(self):
        moved_any = False
        while True:
            moved = False
            # Try freecells first
            for fi in range(4):
                for ci in range(4):
                    if self.freecells[ci].cards:
                        c = self.freecells[ci].cards[-1]
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            self.freecells[ci].cards.pop()
                            self.foundations[fi].cards.append(c)
                            moved = True
                            moved_any = True
                            break
                if moved:
                    break
            if moved:
                continue
            # Try tableau tops
            for fi in range(4):
                for ti in range(8):
                    if self.tableau[ti].cards:
                        c = self.tableau[ti].cards[-1]
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            self.tableau[ti].cards.pop()
                            self.foundations[fi].cards.append(c)
                            moved = True
                            moved_any = True
                            break
                if moved:
                    break
            if not moved:
                break
        if moved_any:
            # Expand any newly uncovered card faces (should already be face up)
            pass

    # ----- Events -----
    def handle_event(self, e):
        # Track mouse for edge panning
        if e.type == pygame.MOUSEMOTION:
            self.edge_pan.on_mouse_pos(e.pos)
        # Help overlay intercept
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return
        # Toggle help via keyboard
        if e.type == pygame.KEYDOWN and e.key == pygame.K_h:
            if getattr(self, "help", None):
                if self.help.visible:
                    self.help.close()
                else:
                    self.help.open()
                return
        if self.toolbar.handle_event(e):
            return

        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll_xy()
            # Scrolling cancels peek
            self.peek.cancel()
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            # Clicking cancels peek
            self.peek.cancel()

            # Double-click to auto-move to foundations from freecell/tableau tops
            if self._maybe_handle_double_click(e, mxw, myw):
                return

            # Start drag from freecell
            for i, p in enumerate(self.freecells):
                if p.top_rect().collidepoint((mxw, myw)) and p.cards:
                    c = p.cards.pop()
                    self.drag_stack = ([c], "free", i)
                    self.drag_offset = (mxw - p.top_rect().x, myw - p.top_rect().y)
                    self.edge_pan.set_active(True)
                    return

            # Start drag from tableau (allow valid sequences)
            for i, p in enumerate(self.tableau):
                if not p.cards:
                    continue
                # Find clicked index (within tableau pile considering fan)
                idx = p.hit((mxw, myw))
                if idx is None:
                    continue
                if idx == -1 and p.cards:
                    idx = len(p.cards) - 1
                seq = p.cards[idx:]
                if self._is_valid_sequence(seq):
                    chosen_idx = idx
                    picked = seq[:]
                else:
                    chosen_idx = len(p.cards) - 1
                    picked = [p.cards[-1]]
                # Remove picked cards from the column immediately (like Klondike)
                p.cards = p.cards[:chosen_idx]
                self.drag_stack = (picked, "tab", i)
                top_r = p.rect_for_index(chosen_idx)
                self.drag_offset = (mxw - top_r.x, myw - top_r.y)
                self.edge_pan.set_active(True)
                return

            # Start drag from foundation? (disallow moving out to keep rules simple)

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack:
                return
            stack, skind, sidx = self.drag_stack
            self.drag_stack = None
            self.edge_pan.set_active(False)

            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y

            # Try drop on foundations (only single card)
            if len(stack) == 1:
                for fi, f in enumerate(self.foundations):
                    if f.top_rect().collidepoint((mxw, myw)) and self._can_move_to_foundation(stack[0], fi):
                        self.push_undo()
                        f.cards.append(stack[0])
                        return

            # Try drop on freecells (only single card)
            if len(stack) == 1:
                for ci, cell in enumerate(self.freecells):
                    if cell.top_rect().collidepoint((mxw, myw)) and not cell.cards:
                        self.push_undo()
                        cell.cards.append(stack[0])
                        return

            # Try drop on tableau
            for ti, t in enumerate(self.tableau):
                if t.top_rect().collidepoint((mxw, myw)):
                    target_top = t.cards[-1] if t.cards else None
                    if self._can_stack_tableau(stack[0], target_top):
                        # Capacity check for sequences
                        cap = self._max_movable(target_is_empty=(len(t.cards) == 0))
                        if len(stack) <= cap:
                            self.push_undo()
                            t.cards.extend(stack)
                            return

            # If we reach here, drop failed: restore to origin
            if skind == "free":
                self.freecells[sidx].cards.extend(stack)
            elif skind == "tab":
                self.tableau[sidx].cards.extend(stack)
            return

        if e.type == pygame.MOUSEMOTION and not self.drag_stack:
            # Compute peek overlay using centralized Klondike-style logic
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            self.peek.on_motion_over_piles(self.tableau, (mxw, myw))

        # Horizontal scrollbar interactions
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_hscroll = True
                    self._hscroll_drag_dx = e.pos[0] - knob_rect.x
                    self._hscroll_geom = (min_sx, max_sx, track_x, track_w, knob_w)
                    return
                elif track_rect.collidepoint(e.pos):
                    x = min(max(e.pos[0] - knob_w // 2, track_x), track_x + track_w - knob_w)
                    t_knob = (x - track_x) / max(1, (track_w - knob_w))
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll_xy()
                    return
        if e.type == pygame.MOUSEMOTION and self._drag_hscroll:
            if self._hscroll_geom is not None:
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_dx, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll_xy()
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_hscroll:
            self._drag_hscroll = False
            self._hscroll_geom = None
            return

        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_r:
                self.restart()
            elif e.key == pygame.K_n:
                self.deal_new()
            elif e.key == pygame.K_u:
                self.undo()
            elif e.key == pygame.K_a:
                self.auto_to_foundations()
            elif e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)

    # ----- Scroll helpers -----
    def _content_bottom_y(self) -> int:
        bottoms = []
        # Consider tallest tableau column
        for p in self.tableau:
            if p.cards:
                r = p.rect_for_index(len(p.cards) - 1)
                bottoms.append(r.bottom)
            else:
                bottoms.append(p.y + C.CARD_H)
        return max(bottoms) if bottoms else C.SCREEN_H

    def _clamp_scroll_xy(self):
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y > 0:
            self.scroll_y = 0
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        # Horizontal bounds
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

    def _content_bounds_x(self):
        lefts = []
        rights = []
        piles = list(self.freecells) + list(self.foundations) + list(self.tableau)
        for p in piles:
            lefts.append(p.x)
            rights.append(p.x + C.CARD_W)
        return (min(lefts) if lefts else 0, max(rights) if rights else C.SCREEN_W)

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

    # ----- Drawing -----
    def draw(self, screen):
        screen.fill(C.TABLE_BG)

        # Edge panning while dragging near edges
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        has_v = self._vertical_scrollbar() is not None
        has_h = self._horizontal_scrollbar() is not None
        dx, dy = self.edge_pan.step(has_h_scroll=has_h, has_v_scroll=has_v)
        if dx or dy:
            self.scroll_x += dx
            self.scroll_y += dy
            self._clamp_scroll_xy()

        # Apply scroll for card content
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        # If a peek is pending and delay elapsed, activate it even without mouse movement
        now = pygame.time.get_ticks()
        self.peek.maybe_activate(now)

        # Draw top placeholders
        font_lbl = C.FONT_SMALL
        for i, p in enumerate(self.freecells):
            p.draw(screen)
            lab = font_lbl.render("Free", True, (245, 245, 245))
            screen.blit(lab, (p.x + (C.CARD_W - lab.get_width()) // 2 + self.scroll_x, p.y - 22 + self.scroll_y))
        for i, p in enumerate(self.foundations):
            p.draw(screen)
            # Draw suit character (plain white) on empty foundation placeholder
            if not p.cards:
                suit_i = self.foundation_suits[i]
                suit_char = C.SUITS[suit_i]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                cx = p.x + C.CARD_W // 2 + self.scroll_x
                cy = p.y + C.CARD_H // 2 + self.scroll_y
                screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        # Draw tableau
        for p in self.tableau:
            p.draw(screen)

        # Draw dragging stack on top
        if self.drag_stack:
            stack, _, _ = self.drag_stack
            mx, my = pygame.mouse.get_pos()
            # Render as a fanned stack following the mouse
            for i, c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W // 2, my - C.CARD_H // 2 + i * max(24, C.CARD_H // 5)))
        elif self.peek.overlay:
            # Show a full preview of the hovered face-up, partially covered card, in-place
            card, rx, ry = self.peek.overlay
            surf = C.get_card_surface(card)
            sx = rx + self.scroll_x
            sy = ry + self.scroll_y
            screen.blit(surf, (sx, sy))

        # Reset offsets for UI drawing
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0

        # Scrollbars
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)

        # Title bar and toolbar
        C.Scene.draw_top_bar(self, screen, "FreeCell")
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
