# klondike.py - Klondike scenes with flip-on-click, auto-finish, and win message
import pygame
from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT

def is_red(suit): return suit in (1,2)

# -----------------------------
# Options Scene
# -----------------------------
class KlondikeOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.diff_index = 0  # 0: Easy(∞), 1: Medium(2), 2: Hard(1)
        self.draw_mode = 3   # 1 or 3
        cx = C.SCREEN_W//2 - 210
        y = 260
        self.b_start = C.Button("Start Klondike", cx, y); y+=60
        self.b_diff  = C.Button("Difficulty: Easy (Unlimited stock cycles)", cx, y, w=420); y+=60
        self.b_draw  = C.Button("Draw: 3", cx, y, w=420); y+=60
        y+=10
        self.b_back  = C.Button("Back", cx, y)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx,my = e.pos
            if self.b_start.hovered((mx,my)):
                self.next_scene = KlondikeGameScene(
                    self.app,
                    draw_count=self.draw_mode,
                    stock_cycles=[None,2,1][self.diff_index]
                )
            elif self.b_diff.hovered((mx,my)):
                self.diff_index = (self.diff_index + 1) % 3
                txt = ["Easy (Unlimited stock cycles)",
                       "Medium (2 stock cycles)",
                       "Hard (1 stock cycle)"][self.diff_index]
                self.b_diff.text = "Difficulty: " + txt
            elif self.b_draw.hovered((mx,my)):
                self.draw_mode = 1 if self.draw_mode == 3 else 3
                self.b_draw.text = f"Draw: {self.draw_mode}"
            elif self.b_back.hovered((mx,my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Klondike – Options", True, C.WHITE)
        # Override garbled title with a clean one
        title = C.FONT_TITLE.render("Klondike - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 120))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_diff, self.b_draw, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))

# -----------------------------
# Game Scene
# -----------------------------
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
        self.undo_mgr = C.UndoManager()
        self.message = ""
        self.drag_stack = None

        # Toolbar actions
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
                "Auto":    {"on_click": self.start_auto_finish,
                "enabled": self.can_autofinish,
                "tooltip": "Auto-finish to foundations"},
        }

# NEW: align='right', tell toolbar how wide the screen is, and set top-bar margins
        self.toolbar = make_toolbar(
            actions,
            height=DEFAULT_BUTTON_HEIGHT,
            margin=(10, 8),                # (right/left pad when right-aligned, top pad)
            gap=8,
            align="right",                 # <-- key bit
            width_provider=lambda: C.SCREEN_W
        )

        # Auto-finish timing state
        self.auto_play_active = False
        self.auto_last_time = 0
        self.auto_interval_ms = 180

        self.deal_new()

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
        if self.toolbar.handle_event(e):
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Stock
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mx,my)):
                self.push_undo(); self.draw_from_stock(); return
            # Waste
            wi = self.waste_pile.hit((mx,my))
            if wi is not None and wi == len(self.waste_pile.cards)-1:
                c = self.waste_pile.cards.pop()
                self.drag_stack = ([c], ("waste", None)); return
            # Foundations
            for fi,f in enumerate(self.foundations):
                hi = f.hit((mx,my))
                if hi is not None and hi == len(f.cards)-1 and f.cards:
                    c = f.cards.pop()
                    self.drag_stack = ([c], ("foundation", fi)); return
            # Tableau
            for ti,t in enumerate(self.tableau):
                hi = t.hit((mx,my))
                if hi is None: continue
                if hi == len(t.cards)-1 and not t.cards[hi].face_up:
                    t.cards[hi].face_up = True
                    self.push_undo(); return
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]; t.cards = t.cards[:hi]
                    self.drag_stack = (seq, ("tableau", ti)); return

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack: return
            stack, from_info = self.drag_stack; self.drag_stack = None
            mx, my = e.pos
            # Foundations
            for fi,f in enumerate(self.foundations):
                if f.top_rect().collidepoint((mx,my)) and len(stack)==1:
                    c = stack[0]
                    if self.can_move_to_foundation(c, fi):
                        self.push_undo(); f.cards.append(c); self.post_move_cleanup(); return
            # Tableau
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
            if e.key == pygame.K_r: self.restart()
            elif e.key == pygame.K_n: self.deal_new()
            elif e.key == pygame.K_u: self.undo()
            elif e.key == pygame.K_a:
                if self.can_autofinish():
                    self.start_auto_finish()
            elif e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)

    # ---------- Drawing ----------
    def draw(self, screen):
        screen.fill(C.TABLE_BG)

        if self.auto_play_active:
            now = pygame.time.get_ticks()
            if now - self.auto_last_time >= self.auto_interval_ms:
                self.step_auto_finish()
                self.auto_last_time = now

        extra = ("Stock cycles: unlimited" if self.stock_cycles_allowed is None
                 else f"Stock cycles used: {self.stock_cycles_used}/{self.stock_cycles_allowed}")
        C.Scene.draw_top_bar(self, screen, "Klondike", extra)

        self.toolbar.draw(screen)

        for i,f in enumerate(self.foundations):
            f.draw(screen)
            label = C.FONT_SMALL.render("Foundation", True, (245,245,245))
            screen.blit(label, (f.x + (C.CARD_W - label.get_width())//2, f.y - 22))

        self.stock_pile.draw(screen)
        lab = C.FONT_SMALL.render("Stock", True, (245,245,245))
        screen.blit(lab, (self.stock_pile.x + (C.CARD_W - lab.get_width())//2, self.stock_pile.y - 22))
        self.waste_pile.draw(screen)
        lab2 = C.FONT_SMALL.render("Waste", True, (245,245,245))
        screen.blit(lab2, (self.waste_pile.x + (C.CARD_W - lab2.get_width())//2, self.waste_pile.y - 22))

        for t in self.tableau:
            t.draw(screen)

        if self.drag_stack:
            stack,_ = self.drag_stack; mx,my = pygame.mouse.get_pos()
            for i,c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W//2, my - C.CARD_H//2 + i*28))

        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W//2 - msg.get_width()//2, C.SCREEN_H - 40))
