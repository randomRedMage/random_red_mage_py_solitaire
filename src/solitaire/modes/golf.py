# golf.py - Golf Solitaire mode (options + game with multi-hole scoring and save/continue)
import os
import json
import pygame
from typing import List, Optional, Tuple, Dict, Any

from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT


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
        self.around = False

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
        # Piles
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=0) for _ in range(7)]
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.foundation: C.Pile = C.Pile(0, 0)
        # Undo
        self.undo_mgr = C.UndoManager()
        # Restart snapshot for the current hole
        self._initial_snapshot = None

        # Toolbar
        def goto_menu():
            # Return without saving (discard progress)
            from solitaire.modes.golf import GolfOptionsScene
            self.next_scene = GolfOptionsScene(self.app)

        def can_undo():
            return self.undo_mgr.can_undo()

        def save_and_exit():
            self._save_game(to_menu=True)

        actions = {
            "Menu":    {"on_click": goto_menu},
            "New":     {"on_click": self._new_game_reset},
            "Restart": {"on_click": self.restart_hole, "tooltip": "Restart current hole"},
            "Undo":    {"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            "Save&Exit": {"on_click": save_and_exit, "tooltip": "Save game and exit to menu"},
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

        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal_new_hole()

    # ----- Layout -----
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar_h + 22)

        # Row 1: foundation (left), stock (right of foundation)
        self.foundation.x, self.foundation.y = 20, top_y
        self.stock_pile.x, self.stock_pile.y = self.foundation.x + (C.CARD_W + gap_x), top_y

        # Row 2: tableau columns start to the right, 7 columns
        tab_left = self.stock_pile.x + (C.CARD_W + gap_x) + max(30, gap_x)
        for i, t in enumerate(self.tableau):
            t.x = tab_left + i * (C.CARD_W + gap_x)
            t.y = top_y
            t.fan_y = max(12, int(C.CARD_H * 0.06))

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
            from solitaire.modes.golf import GolfOptionsScene
            self.next_scene = GolfOptionsScene(self.app)

    def _load_from_state(self, state: Dict[str, Any]):
        self.around = bool(state.get("around", False))
        self.holes_total = int(state.get("holes_total", 1))
        self.current_hole = int(state.get("current_hole", 1))
        self.scores = [int(x) for x in state.get("scores", [])]

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
        if self.toolbar.handle_event(e):
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            # ESC = back to options (no save)
            from solitaire.modes.golf import GolfOptionsScene
            self.next_scene = GolfOptionsScene(self.app)
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Click stock to flip to foundation
            if self.stock_pile.top_rect().collidepoint((mx, my)):
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
                if r.collidepoint((mx, my)) and self._is_playable(t.cards[-1]):
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
                from solitaire.modes.golf import GolfOptionsScene
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
    def _draw_scores_table(self, screen):
        # Draw a small table with hole scores and running total
        x = 20
        y = self.foundation.y + C.CARD_H + 14
        header = C.FONT_UI.render("Scores (Hole / Total)", True, C.WHITE)
        screen.blit(header, (x, y)); y += header.get_height() + 6
        running = 0
        for i in range(self.holes_total):
            label = f"{i+1:>2}:"
            if i < len(self.scores):
                running += self.scores[i]
                val = f"{self.scores[i]:>4} / {running:>4}"
            else:
                val = "--   / --"
            t1 = C.FONT_SMALL.render(label, True, C.WHITE)
            t2 = C.FONT_SMALL.render(val, True, C.WHITE)
            screen.blit(t1, (x, y))
            screen.blit(t2, (x + 40, y))
            y += t1.get_height() + 2

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

        # Draw piles
        self.foundation.draw(screen)
        labf = C.FONT_SMALL.render("Foundation", True, (245,245,245))
        screen.blit(labf, (self.foundation.x + (C.CARD_W - labf.get_width())//2, self.foundation.y - 22))
        self.stock_pile.draw(screen)
        labs = C.FONT_SMALL.render("Stock", True, (245,245,245))
        screen.blit(labs, (self.stock_pile.x + (C.CARD_W - labs.get_width())//2, self.stock_pile.y - 22))
        for t in self.tableau:
            t.draw(screen)

        # Scores panel
        self._draw_scores_table(screen)

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

        # Top bar and toolbar
        C.Scene.draw_top_bar(self, screen, "Golf", extra)
        self.toolbar.draw(screen)


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
                from solitaire.modes.golf import GolfOptionsScene
                self.next_scene = GolfOptionsScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.modes.golf import GolfOptionsScene
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

