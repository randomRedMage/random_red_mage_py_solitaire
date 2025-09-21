# klondike.py - Klondike scenes with flip-on-click, auto-finish, and win message
import pygame
from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help
from solitaire import mechanics as M

def is_red(suit): return suit in (1,2)

# -----------------------------
# Game Scene
# -----------------------------
class KlondikeGameScene(C.Scene):
    def __init__(self, app, draw_count=3, stock_cycles=None):
        super().__init__(app)
        # 2D scroll for large cards
        self.scroll_x = 0
        self.scroll_y = 0
        self._panning = False
        self._pan_anchor = (0, 0)
        self._scroll_anchor = (0, 0)
        self._drag_vscroll = False
        self._drag_hscroll = False
        self.draw_count = draw_count
        self.stock_cycles_allowed = stock_cycles
        self.stock_cycles_used = 0
        # Piles (positions/fan set in compute_layout)
        self.foundations = [C.Pile(0, 0) for _ in range(4)]
        # Dedicated foundation suits left-to-right: [Spades, Hearts, Diamonds, Clubs]
        self.foundation_suits = [0, 1, 2, 3]
        self.stock_pile = C.Pile(0, 0)
        self.waste_pile = C.Pile(0, 0)
        self.tableau = [C.Pile(0, 0, fan_y=0) for _ in range(7)]
        self.undo_mgr = C.UndoManager()
        self.message = ""
        self.drag_stack = None

        self.ui_helper = ModeUIHelper(self, game_id="klondike", return_to_options=False)

        def can_undo():
            return self.undo_mgr.can_undo()

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            auto_action={
                "on_click": self.start_auto_finish,
                "enabled": self.can_autofinish,
                "tooltip": "Auto-finish to foundations",
            },
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        )

        # Auto-finish timing state
        self.auto_play_active = False
        self.auto_last_time = 0
        self.auto_interval_ms = 180

        # Layout depends on current card size and screen size
        self.compute_layout()
        self.deal_new()
        # Hover peek for face-up cards within a pile

        # Help overlay
        self.help = create_modal_help("klondike")
        # Klondike-style delayed single-card peek (shared across modes)
        self.peek = M.PeekController(delay_ms=2000)
        # Central edge-panning controller for drag-to-edge auto-scroll
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 64))
        # Double-click tracking
        self._last_click_time = 0
        self._last_click_pos = (0, 0)

    # ---------- Layout ----------
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))
        left_margin = 20
        top_bar_h = getattr(C, "TOP_BAR_H", 64)
        top_y = max(80, top_bar_h + 26)

        # Row 1: Foundations across the top
        for i, f in enumerate(self.foundations):
            f.x = left_margin + i * (C.CARD_W + gap_x)
            f.y = top_y

        # Row 2: Stock + Waste directly below foundations
        row2_y = top_y + C.CARD_H + gap_y
        self.stock_pile.x, self.stock_pile.y = left_margin, row2_y
        self.waste_pile.x, self.waste_pile.y = left_margin + (C.CARD_W + gap_x), row2_y

        # Tableau starts to the right, 7 columns
        tab_left = left_margin + 2 * (C.CARD_W + gap_x) + max(40, 2 * gap_x)
        fan_y = max(18, int(C.CARD_H * 0.28))
        for i, t in enumerate(self.tableau):
            t.x = tab_left + i * (C.CARD_W + gap_x)
            t.y = row2_y
            t.fan_y = fan_y

    # ---------- Scrolling helpers ----------
    def _content_bottom_y(self) -> int:
        # Estimate the maximum Y occupied by content (foundations/tableau)
        bottoms = []
        bottoms.append(self.stock_pile.y + C.CARD_H)
        bottoms.append(self.waste_pile.y + C.CARD_H)
        for f in self.foundations:
            bottoms.append(f.y + C.CARD_H)
        for t in self.tableau:
            n = max(1, len(t.cards))
            bottoms.append(t.y + (n-1)*t.fan_y + C.CARD_H)
        return max(bottoms) if bottoms else C.SCREEN_H

    def _clamp_scroll(self):
        # Allow scrolling upward to reveal content bottom, but not past the top
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)  # bottom margin
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        if self.scroll_y > 0:
            self.scroll_y = 0

    def _content_bounds_x(self):
        # Compute min left and max right of content (foundations, stock/waste, tableau)
        lefts = []
        rights = []
        piles = self.foundations + [self.stock_pile, self.waste_pile] + self.tableau
        for p in piles:
            lefts.append(p.x)
            rights.append(p.x + C.CARD_W)
        return (min(lefts) if lefts else 0, max(rights) if rights else C.SCREEN_W)

    def _clamp_scroll_xy(self):
        # Clamp Y using existing helper
        self._clamp_scroll()
        # Clamp X using computed bounds: keep some 20px margin both sides
        left, right = self._content_bounds_x()
        # how far can we scroll rightwards (positive scroll_x) so left edge doesn't pass 20px
        max_scroll_x = 20 - left
        # how far can we scroll leftwards (negative scroll_x) so right edge stays within screen - 20
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        if self.scroll_x > max_scroll_x:
            self.scroll_x = max_scroll_x
        if self.scroll_x < min_scroll_x:
            self.scroll_x = min_scroll_x

    # ---------- Lifecycle ----------
    def _clear_all_piles(self):
        for p in self.tableau: p.cards = []
        for f in self.foundations: f.cards = []
        self.waste_pile.cards = []
        self.stock_pile.cards = []
        self.drag_stack = None
        self.message = ""

    def deal_new(self):
        # Reset & redeal
        self._clear_all_piles()
        deck = C.make_deck(shuffle=True)

        for col in range(7):
            for r in range(col+1):
                c = deck.pop()
                c.face_up = (r == col)
                self.tableau[col].cards.append(c)

        self.stock_pile.cards = deck
        for c in self.stock_pile.cards:
            c.face_up = False

        self.stock_cycles_used = 0

        # Reset undo
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()

        self.auto_play_active = False

    def restart(self):
        if getattr(self, "_initial_snapshot", None):
            self.restore_snapshot(self._initial_snapshot)
            self.drag_stack = None
            self.message = ""
            self.auto_play_active = False
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ---------- Undo helpers ----------
    def record_snapshot(self):
        return {
            "foundations": [[C.Card(c.suit, c.rank, c.face_up) for c in f.cards] for f in self.foundations],
            "stock": [C.Card(c.suit, c.rank, c.face_up) for c in self.stock_pile.cards],
            "waste": [C.Card(c.suit, c.rank, c.face_up) for c in self.waste_pile.cards],
            "tableau": [[C.Card(c.suit, c.rank, c.face_up) for c in p.cards] for p in self.tableau],
            "stock_cycles_used": self.stock_cycles_used
        }

    def restore_snapshot(self, snap):
        for i,f in enumerate(self.foundations):
            f.cards = [C.Card(c.suit, c.rank, c.face_up) for c in snap["foundations"][i]]
        self.stock_pile.cards = [C.Card(c.suit, c.rank, c.face_up) for c in snap["stock"]]
        self.waste_pile.cards = [C.Card(c.suit, c.rank, c.face_up) for c in snap["waste"]]
        for i,p in enumerate(self.tableau):
            p.cards = [C.Card(c.suit, c.rank, c.face_up) for c in snap["tableau"][i]]
        self.stock_cycles_used = snap["stock_cycles_used"]

    def push_undo(self):
        snap = self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.auto_play_active = False

    # ---------- Gameplay helpers ----------
    def draw_from_stock(self):
        if not self.stock_pile.cards:
            if not self.waste_pile.cards:
                return
            if self.stock_cycles_allowed is not None:
                if self.stock_cycles_used >= self.stock_cycles_allowed:
                    self.message = "No more stock cycles!"
                    return
            self.stock_pile.cards = [C.Card(c.suit,c.rank,False) for c in reversed(self.waste_pile.cards)]
            for c in self.stock_pile.cards: c.face_up = False
            self.waste_pile.cards.clear()
            self.stock_cycles_used += 1
            return
        n = min(self.draw_count, len(self.stock_pile.cards))
        moved = []
        for _ in range(n):
            c = self.stock_pile.cards.pop()
            c.face_up = True
            moved.append(c)
        self.waste_pile.cards.extend(moved)
        self.message = ""

    def can_stack_tableau(self, upper: C.Card, lower: C.Card):
        if not lower or not upper: return False
        return ((upper.suit in (0,3) and lower.suit in (1,2)) or
                (upper.suit in (1,2) and lower.suit in (0,3))) and (upper.rank == lower.rank - 1)

    def can_move_to_empty_tableau(self, card: C.Card):
        return card.rank == 13  # King

    def can_move_to_foundation(self, card: C.Card, foundation_index: int):
        # Enforce dedicated suit per foundation index
        required_suit = self.foundation_suits[foundation_index]
        if card.suit != required_suit:
            return False
        f = self.foundations[foundation_index]
        if not f.cards:
            return card.rank == 1  # Ace of the required suit
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _maybe_handle_double_click(self, e, mxw: int, myw: int) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - getattr(self, "_last_click_time", 0) <= 350
            and abs(e.pos[0] - getattr(self, "_last_click_pos", (0, 0))[0]) <= 6
            and abs(e.pos[1] - getattr(self, "_last_click_pos", (0, 0))[1]) <= 6
        )
        handled = False
        if double:
            # Waste top card
            if self.waste_pile.cards and self.waste_pile.top_rect().collidepoint((mxw, myw)):
                c = self.waste_pile.cards[-1]
                fi = self._foundation_index_for_suit(c.suit)
                if self.can_move_to_foundation(c, fi):
                    self.push_undo()
                    self.waste_pile.cards.pop()
                    self.foundations[fi].cards.append(c)
                    self.post_move_cleanup()
                    handled = True
            # Tableau top cards
            if not handled:
                for ti, t in enumerate(self.tableau):
                    hi = t.hit((mxw, myw))
                    if hi is None:
                        continue
                    if hi == -1 and t.cards:
                        hi = len(t.cards) - 1
                    if hi == len(t.cards) - 1 and t.cards[hi].face_up:
                        c = t.cards[-1]
                        fi = self._foundation_index_for_suit(c.suit)
                        if self.can_move_to_foundation(c, fi):
                            self.push_undo()
                            t.cards.pop()
                            self.foundations[fi].cards.append(c)
                            self.post_move_cleanup()
                            handled = True
                            break
        # Update click tracking (always)
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    def drop_stack_on_tableau(self, stack, target_pile):
        if not stack: return False
        if not target_pile.cards:
            if self.can_move_to_empty_tableau(stack[0]):
                target_pile.cards.extend(stack); return True
            return False
        top = target_pile.cards[-1]
        if not top.face_up: return False
        if self.can_stack_tableau(stack[0], top):
            target_pile.cards.extend(stack); return True
        return False

    def post_move_cleanup(self):
        for p in self.tableau:
            if p.cards and not p.cards[-1].face_up:
                p.cards[-1].face_up = True
        if all(len(f.cards)==13 for f in self.foundations):
            self.message = "🎉 Congratulations! You won! Press N for a new game."

    # ---------- Auto finish ----------
    def can_autofinish(self):
        if self.stock_pile.cards or self.waste_pile.cards:
            return False
        for p in self.tableau:
            for c in p.cards:
                if not c.face_up:
                    return False
        return True

    def _find_next_auto_move(self):
        for ti, t in enumerate(self.tableau):
            if not t.cards: continue
            c = t.cards[-1]
            for fi in range(4):
                if self.can_move_to_foundation(c, fi):
                    return (ti, fi)
        return None

    def start_auto_finish(self):
        if not self.can_autofinish():
            return
        self.auto_play_active = True
        self.auto_last_time = pygame.time.get_ticks()

    def step_auto_finish(self):
        nxt = self._find_next_auto_move()
        if not nxt:
            self.auto_play_active = False
            if all(len(f.cards)==13 for f in self.foundations):
                self.message = "🎉 Congratulations! You won! Press N for a new game."
            return
        ti, fi = nxt
        c = self.tableau[ti].cards.pop()
        self.foundations[fi].cards.append(c)
        if self.tableau[ti].cards and not self.tableau[ti].cards[-1].face_up:
            self.tableau[ti].cards[-1].face_up = True

    # ---------- Events ----------
    def handle_event(self, e):
        # Always track mouse position for edge panning
        if e.type == pygame.MOUSEMOTION:
            self.edge_pan.on_mouse_pos(e.pos)
        # Help overlay intercepts input when visible
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(e):
                return
            # Swallow other input while help is open
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
        if self.ui_helper.handle_shortcuts(e):
            return

        # Mouse wheel scrolling (supports trackpads: e.x horizontal, e.y vertical)
        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60  # up is positive
            # Horizontal wheel (shift+wheel or trackpad)
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll_xy()
            # Scrolling cancels peek state
            self.peek.cancel()
            return

        # Scrollbar interactions (mouse)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            # Vertical scrollbar knob
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    self._vscroll_drag_dy = e.pos[1] - knob_rect.y
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    return
                elif track_rect.collidepoint(e.pos):
                    # Jump to position
                    y = min(max(e.pos[1] - knob_h//2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    t = 1.0 - t_knob
                    self.scroll_y = min_sy + t * (max_sy - min_sy)
                    self._clamp_scroll_xy()
                    return

            # Horizontal scrollbar knob
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
                    # Map knob position to scroll_x
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll_xy()
                    return

        # Hover peek when not dragging scrollbars or stacks
        if e.type == pygame.MOUSEMOTION and not getattr(self, "_drag_vscroll", False) and not getattr(self, "_drag_hscroll", False) and not self.drag_stack:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            self.peek.on_motion_over_piles(self.tableau, (mxw, myw))

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._drag_vscroll = False
            self._drag_hscroll = False

        if e.type == pygame.MOUSEMOTION:
            if getattr(self, "_drag_vscroll", False):
                min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
                y = min(max(e.pos[1] - self._vscroll_drag_dy, track_y), track_y + track_h - knob_h)
                t_knob = (y - track_y) / max(1, (track_h - knob_h))
                t = 1.0 - t_knob
                self.scroll_y = min_sy + t * (max_sy - min_sy)
                self._clamp_scroll_xy()
                return
            if getattr(self, "_drag_hscroll", False):
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_dx, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll_xy()
                return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            # Any click clears peek state
            self.peek.cancel()
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y  # convert to world coords for hit-tests
            # Prevent interactions under top bar (content is visually behind it)
            if my < getattr(C, "TOP_BAR_H", 64):
                return
            # Double-click to auto-move to foundation (waste or tableau tops)
            if self._maybe_handle_double_click(e, mxw, myw):
                return
            # Stock
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mxw,myw)):
                self.push_undo(); self.draw_from_stock(); return
            # Waste
            wi = self.waste_pile.hit((mxw,myw))
            if wi is not None and wi == len(self.waste_pile.cards)-1:
                c = self.waste_pile.cards.pop()
                self.drag_stack = ([c], ("waste", None)); self.edge_pan.set_active(True); return
            # Foundations
            for fi,f in enumerate(self.foundations):
                hi = f.hit((mxw,myw))
                if hi is not None and hi == len(f.cards)-1 and f.cards:
                    c = f.cards.pop()
                    self.drag_stack = ([c], ("foundation", fi)); self.edge_pan.set_active(True); return
            # Tableau
            for ti,t in enumerate(self.tableau):
                hi = t.hit((mxw,myw))
                if hi is None: continue
                if hi == len(t.cards)-1 and not t.cards[hi].face_up:
                    t.cards[hi].face_up = True
                    self.push_undo(); return
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]; t.cards = t.cards[:hi]
                    self.drag_stack = (seq, ("tableau", ti)); self.edge_pan.set_active(True); return

        # Middle-button drag panning
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 2:
            self._panning = True
            self._pan_anchor = e.pos
            self._scroll_anchor = (self.scroll_x, self.scroll_y)
            return
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 2:
            self._panning = False
            return
        elif e.type == pygame.MOUSEMOTION and self._panning:
            mx, my = e.pos
            ax, ay = self._pan_anchor
            dx = mx - ax
            dy = my - ay
            self.scroll_x = self._scroll_anchor[0] + dx
            self.scroll_y = self._scroll_anchor[1] + dy
            self._clamp_scroll_xy()
            return

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack: return
            stack, from_info = self.drag_stack; self.drag_stack = None; self.edge_pan.set_active(False)
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            # Foundations
            for fi,f in enumerate(self.foundations):
                if f.top_rect().collidepoint((mxw,myw)) and len(stack)==1:
                    c = stack[0]
                    if self.can_move_to_foundation(c, fi):
                        self.push_undo(); f.cards.append(c); self.post_move_cleanup(); return
            # Tableau
            for ti,t in enumerate(self.tableau):
                if t.top_rect().collidepoint((mxw,myw)):
                    if self.drop_stack_on_tableau(stack, t):
                        self.push_undo(); self.post_move_cleanup(); return
            # Return to origin
            origin, idx = from_info
            if origin == "waste": self.waste_pile.cards.extend(stack)
            elif origin == "foundation": self.foundations[idx].cards.extend(stack)
            elif origin == "tableau": self.tableau[idx].cards.extend(stack)

    # ---------- Drawing ----------
    def draw(self, screen):
        screen.fill(C.TABLE_BG)

        if self.auto_play_active:
            now = pygame.time.get_ticks()
            if now - self.auto_last_time >= self.auto_interval_ms:
                self.step_auto_finish()
                self.auto_last_time = now

        # Edge panning while dragging near the screen edges
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        has_v = self._vertical_scrollbar() is not None
        has_h = self._horizontal_scrollbar() is not None
        dx, dy = self.edge_pan.step(has_h_scroll=has_h, has_v_scroll=has_v)
        if dx or dy:
            self.scroll_x += dx
            self.scroll_y += dy
            self._clamp_scroll_xy()

        extra = ("Stock cycles: unlimited" if self.stock_cycles_allowed is None
                 else f"Stock cycles used: {self.stock_cycles_used}/{self.stock_cycles_allowed}")

        # Apply draw offset for piles and other content
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        # If a peek is pending and delay elapsed, activate it even without mouse movement
        self.peek.maybe_activate(pygame.time.get_ticks())

        for i,f in enumerate(self.foundations):
            f.draw(screen)
            # Draw suit character (plain white) on empty foundation placeholder
            if not f.cards:
                suit_i = self.foundation_suits[i]
                suit_char = C.SUITS[suit_i]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                cx = f.x + C.CARD_W // 2 + self.scroll_x
                cy = f.y + C.CARD_H // 2 + self.scroll_y
                screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        self.stock_pile.draw(screen)
        lab = C.FONT_SMALL.render("Stock", True, (245,245,245))
        screen.blit(lab, (self.stock_pile.x + (C.CARD_W - lab.get_width())//2 + self.scroll_x, self.stock_pile.y - 22 + self.scroll_y))
        self.waste_pile.draw(screen)
        lab2 = C.FONT_SMALL.render("Waste", True, (245,245,245))
        screen.blit(lab2, (self.waste_pile.x + (C.CARD_W - lab2.get_width())//2 + self.scroll_x, self.waste_pile.y - 22 + self.scroll_y))

        for t in self.tableau:
            t.draw(screen)

        if self.drag_stack:
            stack,_ = self.drag_stack; mx,my = pygame.mouse.get_pos()
            for i,c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W//2, my - C.CARD_H//2 + i*28))
        elif getattr(self, 'peek', None) and self.peek.overlay:
            c, rx, ry = self.peek.overlay
            surf = C.get_card_surface(c)
            sx = rx + self.scroll_x
            sy = ry + self.scroll_y
            screen.blit(surf, (sx, sy))

        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W//2 - msg.get_width()//2, C.SCREEN_H - 40))

        # Draw a simple vertical scrollbar when content extends beyond view
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0  # reset for UI
        bottom = self._content_bottom_y()
        if bottom > C.SCREEN_H:
            track_rect, knob_rect, *_ = self._vertical_scrollbar()
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Horizontal scrollbar when content wider than view
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (40,40,40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200,200,200), knob_rect, border_radius=3)

        # Draw top bar and toolbar last so content scrolls behind
        C.Scene.draw_top_bar(self, screen, "Klondike", extra)
        self.toolbar.draw(screen)
        # Help overlay on top
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)

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
