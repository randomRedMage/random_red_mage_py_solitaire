# klondike.py - Klondike scenes with flip-on-click, auto-finish, and win message
import pygame
from collections import deque
from solitaire import common as C


KLONDIKE_DIFFICULTY_LABELS = [
    "Easy (Unlimited stock cycles)",
    "Medium (2 stock cycles)",
    "Hard (1 stock cycle)",
]

KLONDIKE_STOCK_CYCLE_LIMITS = [None, 2, 1]


def is_red(suit):
    return suit in (1, 2)


class KlondikeGameScene(C.Scene):
    def __init__(self, app, draw_count=3, stock_cycles=None):
        super().__init__(app)
        self.draw_count = draw_count
        self.stock_cycles_allowed = stock_cycles
        self.stock_cycles_used = 0
        self.foundations = [C.Pile(40 + i*(C.CARD_W+20), 90) for i in range(4)]
        self.stock_pile = C.Pile(40, 260)
        self.waste_pile = C.Pile(40 + (C.CARD_W+20), 260)
        self.tableau = [C.Pile(300 + i*(C.CARD_W+C.CARD_GAP_X), 260, fan_y=28) for i in range(7)]
        self.undo_stack = deque(maxlen=200)
        self.message = ""
        self.drag_stack = None

        # Auto-finish UI/logic
        self.b_autofinish = C.Button("Auto Finish", C.SCREEN_W//2 - 85, 46, w=170, h=28)
        self.auto_play_active = False
        self.auto_last_time = 0
        self.auto_interval_ms = 180  # move a card roughly every 0.18s

        self.deal_new()

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

        # Remaining cards go to stock, face down
        self.stock_pile.cards = deck
        for c in self.stock_pile.cards:
            c.face_up = False

        # Reset counters & undo; remember opening state for true restart
        self.stock_cycles_used = 0
        self.undo_stack.clear()
        self.push_undo()
        self._initial_snapshot = self.snapshot()

        # stop any auto-play
        self.auto_play_active = False

    def restart(self):
        if getattr(self, "_initial_snapshot", None):
            self.restore(self._initial_snapshot)
            self.drag_stack = None
            self.message = ""
            self.undo_stack.clear()
            self.push_undo()
            self.auto_play_active = False

    def snapshot(self):
        return {
            "foundations": [[C.Card(c.suit,c.rank,c.face_up) for c in f.cards] for f in self.foundations],
            "stock": [C.Card(c.suit,c.rank,c.face_up) for c in self.stock_pile.cards],
            "waste": [C.Card(c.suit,c.rank,c.face_up) for c in self.waste_pile.cards],
            "tableau": [[C.Card(c.suit,c.rank,c.face_up) for c in p.cards] for p in self.tableau],
            "stock_cycles_used": self.stock_cycles_used
        }

    def restore(self, snap):
        for i,f in enumerate(self.foundations):
            f.cards = [C.Card(c.suit,c.rank,c.face_up) for c in snap["foundations"][i]]
        self.stock_pile.cards = [C.Card(c.suit,c.rank,c.face_up) for c in snap["stock"]]
        self.waste_pile.cards = [C.Card(c.suit,c.rank,c.face_up) for c in snap["waste"]]
        for i,p in enumerate(self.tableau):
            p.cards = [C.Card(c.suit,c.rank,c.face_up) for c in snap["tableau"][i]]
        self.stock_cycles_used = snap["stock_cycles_used"]

    def push_undo(self):
        self.undo_stack.append(self.snapshot())

    def undo(self):
        if len(self.undo_stack) > 1:
            self.undo_stack.pop()
            self.restore(self.undo_stack[-1])
            # Cancel auto-finish if running
            self.auto_play_active = False
            # No automatic flip here; allow click-to-flip on face-down tops

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
        return ((upper.suit in (0,3) and lower.suit in (1,2)) or (upper.suit in (1,2) and lower.suit in (0,3))) and (upper.rank == lower.rank - 1)

    def can_move_to_empty_tableau(self, card: C.Card):
        return card.rank == 13  # King

    def can_move_to_foundation(self, card: C.Card, foundation_index: int):
        f = self.foundations[foundation_index]
        if not f.cards: return card.rank == 1
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

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
        # Flip newly exposed tableau tops
        for p in self.tableau:
            if p.cards and not p.cards[-1].face_up:
                p.cards[-1].face_up = True
        # Check win
        if all(len(f.cards)==13 for f in self.foundations):
            self.message = "🎉 Congratulations! You won! Press N for a new game."

    # ---------- Auto finish helpers ----------
    def can_autofinish(self):
        """Eligible when stock and waste are empty and all tableau cards are face-up."""
        if self.stock_pile.cards or self.waste_pile.cards:
            return False
        for p in self.tableau:
            for c in p.cards:
                if not c.face_up:
                    return False
        return True

    def _find_next_auto_move(self):
        """Find the next tableau->foundation move. Return (ti, fi) or None."""
        # Prefer moving Aces/low ranks first naturally by checking foundations suitability
        for ti, t in enumerate(self.tableau):
            if not t.cards: continue
            c = t.cards[-1]
            # try each foundation; can_move_to_foundation encodes order
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
        """Execute one auto move if possible; stop when done."""
        nxt = self._find_next_auto_move()
        if not nxt:
            # no more moves
            self.auto_play_active = False
            # final win check
            if all(len(f.cards)==13 for f in self.foundations):
                self.message = "🎉 Congratulations! You won! Press N for a new game."
            return
        ti, fi = nxt
        c = self.tableau[ti].cards.pop()
        self.foundations[fi].cards.append(c)
        # don't clutter undo with auto steps; if desired, add push_undo()
        # Flip exposed card if needed after move
        if self.tableau[ti].cards and not self.tableau[ti].cards[-1].face_up:
            self.tableau[ti].cards[-1].face_up = True

    # ---------- Event handling ----------
    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos

            # Auto Finish button
            if self.b_autofinish.hovered((mx,my)) and self.can_autofinish():
                self.start_auto_finish()
                return

            # Stock
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mx,my)):
                self.push_undo(); self.draw_from_stock(); return

            # Waste (only top card draggable)
            wi = self.waste_pile.hit((mx,my))
            if wi is not None and wi == len(self.waste_pile.cards)-1:
                c = self.waste_pile.cards.pop()
                self.drag_stack = ([c], ("waste", None)); return

            # Foundations (top only)
            for fi,f in enumerate(self.foundations):
                hi = f.hit((mx,my))
                if hi is not None and hi == len(f.cards)-1:
                    c = f.cards.pop()
                    self.drag_stack = ([c], ("foundation", fi)); return

            # Tableau
            for ti,t in enumerate(self.tableau):
                hi = t.hit((mx,my))
                if hi is None: 
                    continue
                # If clicking the top card and it's face-down, flip it (click-to-reveal)
                if hi == len(t.cards)-1 and not t.cards[hi].face_up:
                    t.cards[hi].face_up = True
                    self.push_undo()
                    return
                # Otherwise, start a drag if clicked on a face-up card/sequence
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]; t.cards = t.cards[:hi]
                    self.drag_stack = (seq, ("tableau", ti)); return

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack: return
            stack, from_info = self.drag_stack; self.drag_stack = None
            mx, my = e.pos
            # Try foundations (single-card)
            for fi,f in enumerate(self.foundations):
                if f.top_rect().collidepoint((mx,my)) and len(stack)==1:
                    c = stack[0]
                    if self.can_move_to_foundation(c, fi):
                        self.push_undo(); f.cards.append(c); self.post_move_cleanup(); return
            # Try tableau piles
            for ti,t in enumerate(self.tableau):
                if t.top_rect().collidepoint((mx,my)):
                    if self.drop_stack_on_tableau(stack, t):
                        self.push_undo(); self.post_move_cleanup(); return
            # Return to origin
            origin, idx = from_info
            if origin == "waste": self.waste_pile.cards.extend(stack)
            elif origin == "foundation": self.foundations[idx].cards.extend(stack)
            elif origin == "tableau": self.tableau[idx].cards.extend(stack)

        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_r: 
                self.restart()
            elif e.key == pygame.K_n:
                self.deal_new()
            elif e.key == pygame.K_u: 
                self.undo()
            elif e.key == pygame.K_a:
                if self.can_autofinish():
                    self.start_auto_finish()
            elif e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill((2,100,40))

        # Auto-finish animation stepper
        if self.auto_play_active:
            now = pygame.time.get_ticks()
            if now - self.auto_last_time >= self.auto_interval_ms:
                self.step_auto_finish()
                self.auto_last_time = now

        # HUD
        hints = "ESC: Menu  N: New  R: Restart  U: Undo  A: Auto Finish"
        h = C.FONT_UI.render(hints, True, (245,245,245))
        screen.blit(h, (C.SCREEN_W - h.get_width() - 20, 10))
        if self.stock_cycles_allowed is not None:
            left = max(0, self.stock_cycles_allowed - self.stock_cycles_used)
            sc = C.FONT_UI.render(f"Stock cycles left: {left}", True, (245,245,245))
            screen.blit(sc, (C.SCREEN_W//2 - sc.get_width()//2, 10))

        # Auto Finish button (enabled only when eligible)
        mp = pygame.mouse.get_pos()
        self.b_autofinish.draw(screen, hover=self.b_autofinish.hovered(mp) and self.can_autofinish())

        # Foundations
        for i,f in enumerate(self.foundations):
            f.draw(screen)
            label = C.FONT_SMALL.render("Foundation", True, (245,245,245))
            screen.blit(label, (f.x + (C.CARD_W - label.get_width())//2, f.y - 22))

        # Stock/Waste
        self.stock_pile.draw(screen); lab = C.FONT_SMALL.render("Stock", True, (245,245,245))
        screen.blit(lab, (self.stock_pile.x + (C.CARD_W - lab.get_width())//2, self.stock_pile.y - 22))
        self.waste_pile.draw(screen); lab2 = C.FONT_SMALL.render("Waste", True, (245,245,245))
        screen.blit(lab2, (self.waste_pile.x + (C.CARD_W - lab2.get_width())//2, self.waste_pile.y - 22))

        # Tableau
        for t in self.tableau: t.draw(screen)

        # Drag visuals
        if self.drag_stack:
            stack,_ = self.drag_stack; mx,my = pygame.mouse.get_pos()
            from common import get_card_surface
            for i,c in enumerate(stack):
                surf = get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W//2, my - C.CARD_H//2 + i*28))

        # Message
        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W//2 - msg.get_width()//2, C.SCREEN_H - 40))
