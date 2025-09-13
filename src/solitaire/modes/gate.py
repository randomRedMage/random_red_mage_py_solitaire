import pygame
from typing import List, Optional, Tuple

from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT


def is_red(suit: int) -> bool:
    return suit in (1, 2)


class GateOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 210
        y = 300
        self.b_start = C.Button("Start Gate", cx, y, w=420); y += 70
        self.b_back = C.Button("Back", cx, y, w=420)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self.next_scene = GateGameScene(self.app)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Gate - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))


class GateGameScene(C.Scene):
    """
    Gate mode.
    - 8 center tableau piles (2 rows x 4 columns), build down by 1, alternating colors.
    - 2 reserve piles (left/right of the 8 center piles), start with 5 face-up cards; cannot place onto reserves.
    - 4 foundations with dedicated suits (Spades, Hearts, Diamonds, Clubs) above the top row of 4 center piles.
    - Stock (above) and Waste (below) on the far left; click stock to draw 1 card (no redeal).
    - When a center pile becomes empty, it is immediately filled from Stock, else from Waste. If both are empty, it stays
      empty; the player may manually move a reserve top card into the empty center (optional).
    - Objective: complete all foundations A->K of their suit. Cards cannot be removed from foundations.
    """

    def __init__(self, app):
        super().__init__(app)

        # Piles
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.waste_pile: C.Pile = C.Pile(0, 0)
        # 8 center tableau (2 x 4). Match Klondike fan height so stacks read the same
        self.center: List[C.Pile] = [C.Pile(0, 0, fan_y=max(18, int(C.CARD_H * 0.28))) for _ in range(8)]
        # Presets for dynamic center stacking (compact when tall)
        self._center_fan_default = max(18, int(C.CARD_H * 0.28))
        # Increase compact overlap to ~20px for better readability
        self._center_fan_compact = 20
        # Left and Right Reserve; ensure each card overlaps no more than half height
        self.reserves: List[C.Pile] = [C.Pile(0, 0, fan_y=max(C.CARD_H // 2, 24)) for _ in range(2)]

        # Drag state: (cards, src_kind, src_index)
        self.drag_stack: Optional[Tuple[List[C.Card], str, int]] = None
        self.message: str = ""
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
        }
        self.toolbar = make_toolbar(
            actions,
            height=DEFAULT_BUTTON_HEIGHT,
            margin=(10, 8),
            gap=8,
            align="right",
            width_provider=lambda: C.SCREEN_W,
        )

        self.compute_layout()
        self.deal_new()

        # Double-click tracking (to foundations)
        self._last_click_time = 0
        self._last_click_pos = (0, 0)
        # Hover peek (like Klondike) — but show substack from hover card down
        # Stores list of (card, x, y) to draw, and an optional mask rect to hide cards above
        self.peek_overlay: Optional[List[Tuple[C.Card, int, int]]] = None
        self.peek_mask_rect: Optional[Tuple[int, int, int, int]] = None
        self._peek_candidate: Optional[Tuple[int, int]] = None
        self._peek_started_at: int = 0
        self._peek_pending: Optional[List[Tuple[C.Card, int, int]]] = None
        # Auto-fill animation state
        self._anim: Optional[dict] = None

    # ----- Layout -----
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))

        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar_h + 24)

        # 4 foundations centered over the 4 top center piles
        cols = 4
        center_block_w = cols * C.CARD_W + (cols - 1) * gap_x
        center_left = (C.SCREEN_W - center_block_w) // 2

        # Rows for center piles
        row1_y = top_y + C.CARD_H + gap_y  # under foundations
        # Increase vertical separation to accommodate stacked cards on the top row
        row2_y = row1_y + C.CARD_H + max(gap_y, int(C.CARD_H * 1.25))

        # Position foundations over row1
        for i in range(4):
            x = center_left + i * (C.CARD_W + gap_x)
            self.foundations[i].x, self.foundations[i].y = x, top_y

        # Center piles (2 rows x 4 columns)
        for i in range(4):
            x = center_left + i * (C.CARD_W + gap_x)
            self.center[i].x, self.center[i].y = x, row1_y
            self.center[4 + i].x, self.center[4 + i].y = x, row2_y
            # Match Klondike fan height
            self.center[i].fan_y = max(18, int(C.CARD_H * 0.28))
            self.center[4 + i].fan_y = max(18, int(C.CARD_H * 0.28))

        # Reserves to left and right of the 8 center piles, vertically centered between the two rows
        reserve_gap = max(gap_x * 2, int(C.CARD_W * 0.6))
        # Place reserves near top row and nudge them down a bit for spacing
        res_y = row1_y + 20
        left_res_x = center_left - reserve_gap - C.CARD_W
        right_res_x = center_left + center_block_w + reserve_gap
        self.reserves[0].x, self.reserves[0].y = left_res_x, res_y
        self.reserves[1].x, self.reserves[1].y = right_res_x, res_y
        # Reinforce reserve fan so underlying rank/suit remain visible
        self.reserves[0].fan_y = max(C.CARD_H // 2, self.reserves[0].fan_y)
        self.reserves[1].fan_y = max(C.CARD_H // 2, self.reserves[1].fan_y)

        # Stock/Waste on the far left, stock above waste
        # Bring stock/waste closer to the left reserve and center vertically (extra space ~2x)
        stock_gap = max(16, gap_x * 2)
        stock_x = max(10, left_res_x - (C.CARD_W + stock_gap))
        # Center between stock and waste around the middle of the space between the two center rows
        space_center_y = (row1_y + C.CARD_H + row2_y) / 2.0
        stock_y = int(space_center_y - C.CARD_H - (gap_y / 2))
        self.stock_pile.x, self.stock_pile.y = stock_x, stock_y
        self.waste_pile.x, self.waste_pile.y = stock_x, stock_y + C.CARD_H + gap_y

    # ----- Deal / Restart -----
    def _clear(self):
        for p in self.center:
            p.cards.clear()
        for p in self.foundations:
            p.cards.clear()
        for p in self.reserves:
            p.cards.clear()
        self.stock_pile.cards.clear()
        self.waste_pile.cards.clear()
        self.drag_stack = None
        self.message = ""

    def deal_new(self):
        self._clear()
        deck = C.make_deck(shuffle=True)

        # Reserves: 5 face-up each
        for i in range(5):
            c = deck.pop(); c.face_up = True
            self.reserves[0].cards.append(c)
        for i in range(5):
            c = deck.pop(); c.face_up = True
            self.reserves[1].cards.append(c)

        # Center piles: 1 face-up card each
        for i in range(8):
            c = deck.pop(); c.face_up = True
            self.center[i].cards.append(c)

        # Remaining to stock (face-down)
        for c in deck:
            c.face_up = False
        self.stock_pile.cards = deck

        # Reset undo
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        # Store restart snapshot
        self._initial_snapshot = self.record_snapshot()

    def restart(self):
        if getattr(self, "_initial_snapshot", None):
            self.restore_snapshot(self._initial_snapshot)
            self.drag_stack = None
            self.message = ""
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ----- Undo -----
    def record_snapshot(self):
        def cap_pile(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [cap_pile(p) for p in self.foundations],
            "stock": cap_pile(self.stock_pile),
            "waste": cap_pile(self.waste_pile),
            "center": [cap_pile(p) for p in self.center],
            "reserves": [cap_pile(p) for p in self.reserves],
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, p in enumerate(self.foundations):
            p.cards = mk(snap["foundations"][i])
        self.stock_pile.cards = mk(snap["stock"]) 
        self.waste_pile.cards = mk(snap["waste"]) 
        for i, p in enumerate(self.center):
            p.cards = mk(snap["center"][i])
        for i, p in enumerate(self.reserves):
            p.cards = mk(snap["reserves"][i])
        self.message = snap.get("message", "")

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ----- Rules helpers -----
    def _can_stack_center(self, moving: C.Card, target: Optional[C.Card]) -> bool:
        if target is None:
            return False  # Center empties are auto-filled (not via manual placements)
        return (is_red(moving.suit) != is_red(target.suit)) and (moving.rank == target.rank - 1)

    def _can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        f = self.foundations[fi]
        if not f.cards:
            return card.rank == 1
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _fill_center_vacancies(self):
        """Start an animation to fill the next empty center pile from Stock, else Waste.
        If both are empty, leave as-is. Only one auto-fill animation runs at a time.
        If an Ace is drawn from stock here, animate it to its foundation first."""
        if self._anim is not None:
            return
        for ti, p in enumerate(self.center):
            if p.cards:
                continue
            if self.stock_pile.cards:
                card = self.stock_pile.cards.pop()
                # If it's an Ace, route to foundation instead
                if card.rank == 1:
                    fi = self._foundation_index_for_suit(card.suit)
                    self._anim = {
                        'card': card,
                        'from': (self.stock_pile.x, self.stock_pile.y),
                        'to': (self.foundations[fi].x, self.foundations[fi].y),
                        'start': pygame.time.get_ticks(),
                        'dur': 320,
                        'source': 'stock',
                        'flipped': False,
                        'dest': 'foundation',
                        'foundation_index': fi,
                    }
                else:
                    # Flip mid animation; starts face down
                    self._anim = {
                        'card': card,
                        'from': (self.stock_pile.x, self.stock_pile.y),
                        'to': (p.x, p.y),
                        'start': pygame.time.get_ticks(),
                        'dur': 350,
                        'source': 'stock',
                        'flipped': False,
                        'dest': 'center',
                        'target_index': ti,
                    }
                return
            elif self.waste_pile.cards:
                card = self.waste_pile.cards.pop()
                card.face_up = True
                self._anim = {
                    'card': card,
                    'from': (self.waste_pile.x, self.waste_pile.y),
                    'to': (p.x, p.y),
                    'start': pygame.time.get_ticks(),
                    'dur': 300,
                    'source': 'waste',
                    'flipped': True,
                    'dest': 'center',
                    'target_index': ti,
                }
                return
            else:
                return

    def _has_legal_moves_when_stock_empty(self) -> bool:
        # Any move from waste to foundation or center?
        if self.waste_pile.cards:
            wc = self.waste_pile.cards[-1]
            # To foundation
            fi = self._foundation_index_for_suit(wc.suit)
            if self._can_move_to_foundation(wc, fi):
                return True
            # To any center top
            for p in self.center:
                top = p.cards[-1] if p.cards else None
                if top and self._can_stack_center(wc, top):
                    return True
        # From reserves to foundation or center
        for ri, r in enumerate(self.reserves):
            if not r.cards:
                continue
            c = r.cards[-1]
            fi = self._foundation_index_for_suit(c.suit)
            if self._can_move_to_foundation(c, fi):
                return True
            for p in self.center:
                top = p.cards[-1] if p.cards else None
                if top and self._can_stack_center(c, top):
                    return True
            # Optional rule: allow placing reserve top to an empty center only when stock and waste are empty
            if not self.waste_pile.cards:
                for p in self.center:
                    if not p.cards:
                        return True
        # From center to foundations or between centers
        for src in self.center:
            if not src.cards:
                continue
            top = src.cards[-1]
            # To foundation
            fi = self._foundation_index_for_suit(top.suit)
            if self._can_move_to_foundation(top, fi):
                return True
            # Between centers
            for dst in self.center:
                if src is dst:
                    continue
                if not dst.cards:
                    continue
                if self._can_stack_center(top, dst.cards[-1]):
                    return True
        return False

    # ----- Stock / Waste -----
    def draw_from_stock(self):
        if not self.stock_pile.cards:
            return  # No redeal in Gate
        c = self.stock_pile.cards.pop()
        c.face_up = True
        self.waste_pile.cards.append(c)
        self.message = ""
        # Auto-move Ace from waste to foundation with animation
        if c.rank == 1 and self._anim is None:
            # Remove back from waste and animate to foundation
            self.waste_pile.cards.pop()
            fi = self._foundation_index_for_suit(c.suit)
            self._anim = {
                'card': c,
                'from': (self.waste_pile.x, self.waste_pile.y),
                'to': (self.foundations[fi].x, self.foundations[fi].y),
                'start': pygame.time.get_ticks(),
                'dur': 300,
                'source': 'waste',
                'flipped': True,
                'dest': 'foundation',
                'foundation_index': fi,
            }

    # ----- Double-click helper -----
    def _maybe_handle_double_click(self, e, mx: int, my: int) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - getattr(self, "_last_click_time", 0) <= 350
            and abs(e.pos[0] - getattr(self, "_last_click_pos", (0, 0))[0]) <= 6
            and abs(e.pos[1] - getattr(self, "_last_click_pos", (0, 0))[1]) <= 6
        )
        handled = False
        if double:
            # Waste top -> foundation if legal
            if self.waste_pile.cards and self.waste_pile.top_rect().collidepoint((mx, my)):
                c = self.waste_pile.cards[-1]
                fi = self._foundation_index_for_suit(c.suit)
                if self._can_move_to_foundation(c, fi):
                    self.push_undo()
                    self.waste_pile.cards.pop()
                    self.foundations[fi].cards.append(c)
                    self._fill_center_vacancies()
                    handled = True
            # Center tops -> foundation
            if not handled:
                for t in self.center:
                    hi = t.hit((mx, my))
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
                            self._fill_center_vacancies()
                            handled = True
                            break
            # Reserve tops -> foundation
            if not handled:
                for ri, r in enumerate(self.reserves):
                    if r.cards and r.top_rect().collidepoint((mx, my)):
                        c = r.cards[-1]
                        fi = self._foundation_index_for_suit(c.suit)
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            r.cards.pop()
                            self.foundations[fi].cards.append(c)
                            self._fill_center_vacancies()
                            handled = True
                            break
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    # ----- Events -----
    def handle_event(self, e):
        if self.toolbar.handle_event(e):
            return

        # Avoid interactions while auto-fill animation is running
        if self._anim is not None:
            return

        # Update dynamic fan spacing for center piles
        self._update_center_fans()

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            # Clear message on click
            self.message = ""

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Prevent interactions under the top bar
            if my < getattr(C, "TOP_BAR_H", 60):
                return
            if self._maybe_handle_double_click(e, mx, my):
                self._post_move_checks()
                return
            # Stock click -> draw 1
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mx, my)):
                self.push_undo(); self.draw_from_stock(); return
            # Waste drag (top only)
            wi = self.waste_pile.hit((mx, my))
            if wi is not None and wi == len(self.waste_pile.cards) - 1:
                c = self.waste_pile.cards.pop()
                self.drag_stack = ([c], "waste", -1)
                return
            # Reserve drag (top only)
            for ri, r in enumerate(self.reserves):
                hi = r.hit((mx, my))
                if hi is not None and hi == len(r.cards) - 1:
                    c = r.cards.pop()
                    self.drag_stack = ([c], "reserve", ri)
                    return
            # Foundations: cannot remove cards in Gate
            # Center drag: any face-up run starting at clicked index
            for ti, t in enumerate(self.center):
                hi = t.hit((mx, my))
                if hi is None:
                    continue
                if hi == len(t.cards) - 1 and not t.cards[hi].face_up:
                    t.cards[hi].face_up = True
                    self.push_undo()
                    return
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]
                    t.cards = t.cards[:hi]
                    self.drag_stack = (seq, "center", ti)
                    return

        # Hover peek (like Klondike)
        if e.type == pygame.MOUSEMOTION and not self.drag_stack:
            mx, my = e.pos
            self.peek_overlay = None
            self.peek_mask_rect = None
            candidate = None
            pending = None
            for t in self.center:
                hi = t.hit((mx, my))
                if hi is None or hi == -1:
                    continue
                if hi < len(t.cards) - 1 and t.cards[hi].face_up:
                    r = t.rect_for_index(hi)
                    candidate = (id(t), hi)
                    # Build substack from hover index down
                    sub = []
                    for j in range(hi, len(t.cards)):
                        rj = t.rect_for_index(j)
                        sub.append((t.cards[j], rj.x, rj.y))
                    pending = sub
                    # Mask region above the hover card to hide cards above
                    self.peek_mask_rect = (t.x, t.y, C.CARD_W, max(0, r.y - t.y))
                    break
            now = pygame.time.get_ticks()
            if candidate is None:
                self._peek_candidate = None
                self._peek_pending = None
                self.peek_mask_rect = None
            else:
                if candidate != self._peek_candidate:
                    self._peek_candidate = candidate
                    self._peek_started_at = now
                    self._peek_pending = pending
                elif now - self._peek_started_at >= 2000 and self._peek_pending is not None:
                    self.peek_overlay = self._peek_pending

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack:
                return
            stack, src_kind, src_idx = self.drag_stack
            self.drag_stack = None
            mx, my = e.pos

            # Try foundations first (only single card allowed)
            if len(stack) == 1:
                for fi, f in enumerate(self.foundations):
                    if f.top_rect().collidepoint((mx, my)):
                        if self._can_move_to_foundation(stack[0], fi):
                            self.push_undo()
                            f.cards.append(stack[0])
                            self._fill_center_vacancies()
                            self._post_move_checks()
                            return

            # Try center piles
            for ti, t in enumerate(self.center):
                r = t.top_rect()
                if r.collidepoint((mx, my)):
                    # Empty target: only allow when stock and waste are empty and source is reserve (single card)
                    if not t.cards:
                        if not self.stock_pile.cards and not self.waste_pile.cards and src_kind == "reserve" and len(stack) == 1:
                            self.push_undo()
                            t.cards.extend(stack)
                            self._post_move_checks()
                            return
                        else:
                            # Disallow general placement onto empty center
                            break
                    top = t.cards[-1]
                    if not top.face_up:
                        break
                    if self._can_stack_center(stack[0], top):
                        self.push_undo()
                        t.cards.extend(stack)
                        self._post_move_checks()
                        return

            # If we reach here, drop failed -> return cards to source
            self._return_drag_to_source(stack, src_kind, src_idx)

    def _return_drag_to_source(self, stack: List[C.Card], src_kind: str, src_idx: int):
        if src_kind == "waste":
            self.waste_pile.cards.extend(stack)
        elif src_kind == "reserve":
            self.reserves[src_idx].cards.extend(stack)
        elif src_kind == "center":
            self.center[src_idx].cards.extend(stack)

    def _post_move_checks(self):
        # Auto-fill vacancies and check win/lose
        self._fill_center_vacancies()
        if all(len(f.cards) == 13 for f in self.foundations):
            self.message = "Congratulations! You won!"
            return
        if not self.stock_pile.cards:
            if not self._has_legal_moves_when_stock_empty():
                self.message = "No more legal moves. You lose."

    # ----- Draw -----
    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Keep center stacks compact if they grow tall
        self._update_center_fans()
        # Draw piles
        for i, f in enumerate(self.foundations):
            f.draw(screen)
            if not f.cards:
                suit_i = self.foundation_suits[i]
                suit_char = C.SUITS[suit_i]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                cx = f.x + C.CARD_W // 2
                cy = f.y + C.CARD_H // 2
                screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        # Stock/Waste (no labels)
        self.stock_pile.draw(screen)
        self.waste_pile.draw(screen)

        # Reserves (no labels)
        for i, r in enumerate(self.reserves):
            r.draw(screen)

        # Center piles
        for t in self.center:
            t.draw(screen)

        # Dragging stack follows mouse
        if self.drag_stack:
            stack, _, _ = self.drag_stack
            mx, my = pygame.mouse.get_pos()
            for i, c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W // 2, my - C.CARD_H // 2 + i * 28))
        elif self.peek_overlay:
            # Hide cards above the hover point by repainting table background over that strip
            if self.peek_mask_rect is not None:
                x, y, w, h = self.peek_mask_rect
                pygame.draw.rect(screen, C.TABLE_BG, (x, y, w, h))
            # Draw the substack from hover point down on top
            for c, rx, ry in self.peek_overlay:
                surf = C.get_card_surface(c)
                screen.blit(surf, (rx, ry))

        # Auto-fill animation overlay
        if self._anim is not None:
            now = pygame.time.get_ticks()
            t = (now - self._anim['start']) / max(1, self._anim['dur'])
            if t >= 1.0:
                card = self._anim['card']
                if self._anim['source'] == 'stock' and not self._anim.get('flipped', False):
                    card.face_up = True
                if self._anim.get('dest') == 'center':
                    ti = self._anim['target_index']
                    self.center[ti].cards.append(card)
                else:
                    fi = self._anim.get('foundation_index', 0)
                    self.foundations[fi].cards.append(card)
                self._anim = None
                # Start next fill if other empties or auto ace moves exist
                self._fill_center_vacancies()
                self._maybe_auto_move_revealed_aces()
            else:
                sx, sy = self._anim['from']
                tx, ty = self._anim['to']
                x = int(sx + (tx - sx) * t)
                y = int(sy + (ty - sy) * t)
                card = self._anim['card']
                if self._anim['source'] == 'stock':
                    if t >= 0.5 and not self._anim['flipped']:
                        card.face_up = True
                        self._anim['flipped'] = True
                    if t < 0.5:
                        bs = C.get_back_surface()
                        screen.blit(bs, (x, y))
                    else:
                        surf = C.get_card_surface(card)
                        screen.blit(surf, (x, y))
                else:
                    surf = C.get_card_surface(card)
                    screen.blit(surf, (x, y))

        # Message
        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 40))

        # Top bar and toolbar
        C.Scene.draw_top_bar(self, screen, "Gate")
        self.toolbar.draw(screen)

    def _update_center_fans(self):
        # Compact stacks with more than 3 cards so only 5-10px of each underneath shows
        for p in self.center:
            p.fan_y = self._center_fan_default if len(p.cards) <= 3 else self._center_fan_compact

    def _maybe_auto_move_revealed_aces(self):
        # If a reserve top card is an Ace, animate it to its foundation
        if self._anim is not None:
            return
        for r in self.reserves:
            if not r.cards:
                continue
            top = r.cards[-1]
            if top.rank == 1:
                r.cards.pop()
                fi = self._foundation_index_for_suit(top.suit)
                self._anim = {
                    'card': top,
                    'from': (r.x, r.y),
                    'to': (self.foundations[fi].x, self.foundations[fi].y),
                    'start': pygame.time.get_ticks(),
                    'dur': 280,
                    'source': 'reserve',
                    'flipped': True,
                    'dest': 'foundation',
                    'foundation_index': fi,
                }
                return
