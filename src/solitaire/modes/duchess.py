"""Implementation of the Duchess (Canfield) solitaire variant."""

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper


def _duchess_dir() -> str:
    """Return the directory used to persist Duchess save data."""

    try:
        return C._settings_dir()  # type: ignore[attr-defined]
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _duchess_save_path() -> str:
    return os.path.join(_duchess_dir(), "duchess_save.json")


def _safe_write_json(path: str, data: Dict) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def duchess_save_exists() -> bool:
    state = _safe_read_json(_duchess_save_path())
    return bool(state) and not state.get("completed", False)


def load_saved_state() -> Optional[Dict]:
    return _safe_read_json(_duchess_save_path())


def clear_saved_state() -> None:
    try:
        os.remove(_duchess_save_path())
    except Exception:
        pass


@dataclass
class _DragState:
    cards: List[C.Card]
    origin: Tuple[str, Optional[int]]
    offset: Tuple[int, int]
    position: Tuple[int, int]


class DuchessGameScene(C.Scene):
    """Game scene implementing the Duchess variant."""

    draw_count: int = 1

    def __init__(self, app, *, load_state: Optional[Dict] = None):
        super().__init__(app)

        reserve_fan = max(20, C.CARD_W // 4)
        self.reserves: List[C.Pile] = [C.Pile(0, 0, fan_x=reserve_fan) for _ in range(4)]
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=max(24, int(C.CARD_H * 0.3))) for _ in range(4)]
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.waste_pile: C.Pile = C.Pile(0, 0)

        self.base_rank: Optional[int] = None
        self.waiting_for_base: bool = True
        self.stock_cycles_allowed: int = 1
        self.stock_cycles_used: int = 0

        self.undo_mgr = C.UndoManager()
        self.message = ""

        self.drag: Optional[_DragState] = None
        self._last_click_time = 0
        self._last_click_pos: Tuple[int, int] = (0, 0)

        self.ui_helper = ModeUIHelper(self, game_id="duchess")

        def can_undo() -> bool:
            return self.undo_mgr.can_undo()

        def save_and_exit() -> None:
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            save_action=("Save&Exit", {"on_click": save_and_exit, "tooltip": "Save game and exit to menu"}),
        )

        self.help = create_modal_help("duchess")

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self._initial_snapshot = self.record_snapshot()
        else:
            self.deal_new()

    # ----- Layout -----
    def compute_layout(self) -> None:
        top_bar = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar + 28)
        foundation_gap = max(32, C.CARD_W // 3)
        row_gap = max(36, C.CARD_H // 4)
        reserve_gap_y = max(26, C.CARD_H // 5)
        column_gap = C.CARD_W // 2

        foundation_span = len(self.foundations) * C.CARD_W + (len(self.foundations) - 1) * foundation_gap
        total_width = C.CARD_W + column_gap + foundation_span
        left_edge = max((C.SCREEN_W - total_width) // 2, 24)

        column_x = left_edge
        foundation_start_x = column_x + C.CARD_W + column_gap

        reserve_y = top_y
        for idx, pile in enumerate(self.reserves):
            pile.x = foundation_start_x + idx * (C.CARD_W + foundation_gap)
            pile.y = reserve_y

        foundation_y = reserve_y + C.CARD_H + reserve_gap_y
        for idx, pile in enumerate(self.foundations):
            pile.x = foundation_start_x + idx * (C.CARD_W + foundation_gap)
            pile.y = foundation_y

        row2_y = foundation_y + C.CARD_H + row_gap
        self.stock_pile.x = column_x
        self.stock_pile.y = foundation_y

        self.waste_pile.x = column_x
        self.waste_pile.y = row2_y

        tableau_start_x = foundation_start_x
        for idx, pile in enumerate(self.tableau):
            pile.x = tableau_start_x + idx * (C.CARD_W + foundation_gap)
            pile.y = row2_y

    # ----- Deal / Restart -----
    def _clear(self) -> None:
        for pile in self.reserves:
            pile.cards.clear()
        for pile in self.foundations:
            pile.cards.clear()
        for pile in self.tableau:
            pile.cards.clear()
        self.stock_pile.cards.clear()
        self.waste_pile.cards.clear()
        self.drag = None
        self.message = ""

    def deal_new(self) -> None:
        self._clear()
        deck = C.make_deck(shuffle=True)

        reserve_counts = [4, 3, 3, 3]
        for idx, pile in enumerate(self.reserves):
            count = reserve_counts[idx]
            for _ in range(count):
                card = deck.pop()
                card.face_up = True
                pile.cards.append(card)

        self.base_rank = None
        self.waiting_for_base = True
        self.foundation_suits = [0, 1, 2, 3]
        for pile in self.foundations:
            pile.cards.clear()

        for pile in self.tableau:
            card = deck.pop()
            card.face_up = True
            pile.cards.append(card)

        for card in deck:
            card.face_up = False
        self.stock_pile.cards = deck
        self.waste_pile.cards.clear()

        self.stock_cycles_used = 0
        self.message = "Select a reserve card to start the foundations"

        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()

    def restart(self) -> None:
        if hasattr(self, "_initial_snapshot"):
            self.restore_snapshot(self._initial_snapshot)
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ----- Snapshot / Undo -----
    def record_snapshot(self) -> Dict:
        def cap_pile(pile: C.Pile):
            return [(card.suit, card.rank, card.face_up) for card in pile.cards]

        return {
            "reserves": [cap_pile(p) for p in self.reserves],
            "foundations": [cap_pile(p) for p in self.foundations],
            "foundation_suits": list(self.foundation_suits),
            "tableau": [cap_pile(p) for p in self.tableau],
            "stock": cap_pile(self.stock_pile),
            "waste": cap_pile(self.waste_pile),
            "base_rank": self.base_rank,
            "waiting_for_base": self.waiting_for_base,
            "stock_cycles_allowed": self.stock_cycles_allowed,
            "stock_cycles_used": self.stock_cycles_used,
            "message": self.message,
        }

    def restore_snapshot(self, snap: Dict) -> None:
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]

        reserves = snap.get("reserves", [])
        for idx, pile in enumerate(self.reserves):
            pile.cards = mk(reserves[idx] if idx < len(reserves) else [])
        for idx, pile in enumerate(self.foundations):
            data = snap.get("foundations", [])
            pile.cards = mk(data[idx] if idx < len(data) else [])
        self.foundation_suits = list(snap.get("foundation_suits", [0, 1, 2, 3]))
        for idx, pile in enumerate(self.tableau):
            data = snap.get("tableau", [])
            pile.cards = mk(data[idx] if idx < len(data) else [])
        self.stock_pile.cards = mk(snap.get("stock", []))
        self.waste_pile.cards = mk(snap.get("waste", []))
        base_rank = snap.get("base_rank")
        self.base_rank = int(base_rank) if base_rank is not None else None
        self.waiting_for_base = bool(snap.get("waiting_for_base", False))
        self.stock_cycles_allowed = int(snap.get("stock_cycles_allowed", 1))
        self.stock_cycles_used = int(snap.get("stock_cycles_used", 0))
        self.message = snap.get("message", "")
        self.drag = None

    def push_undo(self) -> None:
        snap = self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self) -> None:
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.message = ""
            self.drag = None

    # ----- Save / Load helpers -----
    def _state_dict(self) -> Dict:
        state = self.record_snapshot()
        state["completed"] = self.is_completed()
        return state

    def _save_game(self, to_menu: bool = False) -> None:
        _safe_write_json(_duchess_save_path(), self._state_dict())
        if to_menu:
            from solitaire.scenes.game_options.duchess_options import DuchessOptionsScene

            self.next_scene = DuchessOptionsScene(self.app)

    def _load_from_state(self, state: Dict) -> None:
        self.restore_snapshot(state)
        self.drag = None

    # ----- Gameplay helpers -----
    def is_completed(self) -> bool:
        if self.waiting_for_base:
            return False
        return all(len(pile.cards) == 13 for pile in self.foundations)

    def draw_from_stock(self) -> None:
        if not self.stock_pile.cards:
            if not self.waste_pile.cards:
                return
            if self.stock_cycles_used >= self.stock_cycles_allowed:
                self.message = "No more stock replays"
                return
            self.stock_pile.cards = [C.Card(c.suit, c.rank, False) for c in reversed(self.waste_pile.cards)]
            for card in self.stock_pile.cards:
                card.face_up = False
            self.waste_pile.cards.clear()
            self.stock_cycles_used += 1
            return

        card = self.stock_pile.cards.pop()
        card.face_up = True
        self.waste_pile.cards.append(card)
        self.message = ""

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        if self.waiting_for_base:
            return False
        if fi < 0 or fi >= len(self.foundations):
            return False
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        pile = self.foundations[fi]
        if not pile.cards:
            return card.rank == self.base_rank
        top = pile.cards[-1]
        next_rank = top.rank + 1
        if next_rank > 13:
            next_rank = 1
        return card.rank == next_rank

    def _tableau_allows(self, moving: C.Card, target: Optional[C.Card]) -> bool:
        if target is None:
            return True
        if (moving.suit in (1, 2)) == (target.suit in (1, 2)):
            return False
        expected = target.rank - 1
        if expected == 0:
            expected = 13
        return moving.rank == expected

    def _sequence_is_valid(self, cards: List[C.Card]) -> bool:
        if not cards:
            return False
        for idx in range(len(cards) - 1):
            upper = cards[idx]
            lower = cards[idx + 1]
            if (upper.suit in (1, 2)) == (lower.suit in (1, 2)):
                return False
            expected = lower.rank + 1
            if expected > 13:
                expected = 1
            if upper.rank != expected:
                return False
        return True

    def _pop_reserve_card(self) -> Optional[Tuple[C.Card, int]]:
        for idx, pile in enumerate(self.reserves):
            if pile.cards:
                return pile.cards.pop(), idx
        return None

    def _auto_fill_empty_columns(self) -> None:
        changed = True
        while changed:
            changed = False
            for pile in self.tableau:
                if pile.cards:
                    continue
                card_info = self._pop_reserve_card()
                card: Optional[C.Card] = None
                if card_info is not None:
                    card, _ = card_info
                elif self.waste_pile.cards:
                    card = self.waste_pile.cards.pop()
                elif self.stock_pile.cards:
                    card = self.stock_pile.cards.pop()
                if card is not None:
                    card.face_up = True
                    pile.cards.append(card)
                    changed = True

    def post_move_cleanup(self) -> None:
        self._auto_fill_empty_columns()
        if self.is_completed():
            self.message = "You win!"

    def _maybe_auto_to_foundation(self, mx: int, my: int) -> bool:
        if self.waiting_for_base:
            return False

        now = pygame.time.get_ticks()
        if now - self._last_click_time > 400:
            self._last_click_time = now
            self._last_click_pos = (mx, my)
            return False
        lx, ly = self._last_click_pos
        if abs(mx - lx) > 6 or abs(my - ly) > 6:
            self._last_click_time = now
            self._last_click_pos = (mx, my)
            return False

        if self.waste_pile.cards:
            rect = self.waste_pile.top_rect()
            if rect.collidepoint((mx, my)):
                card = self.waste_pile.cards[-1]
                if self._try_move_card_to_foundation(card, ("waste", None)):
                    return True

        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            rect = pile.top_rect()
            if rect.collidepoint((mx, my)):
                card = pile.cards[-1]
                if self._try_move_card_to_foundation(card, ("tableau", idx)):
                    return True

        for idx, pile in enumerate(self.reserves):
            if not pile.cards:
                continue
            rect = pile.top_rect()
            if rect.collidepoint((mx, my)):
                card = pile.cards[-1]
                if self._try_move_card_to_foundation(card, ("reserve", idx)):
                    return True

        self._last_click_time = now
        self._last_click_pos = (mx, my)
        return False

    def _try_move_card_to_foundation(self, card: C.Card, origin: Tuple[str, Optional[int]]) -> bool:
        fi = self._foundation_index_for_suit(card.suit)
        if self.can_move_to_foundation(card, fi):
            self.push_undo()
            if origin[0] == "waste":
                self.waste_pile.cards.pop()
            elif origin[0] == "reserve" and origin[1] is not None:
                self.reserves[origin[1]].cards.pop()
            elif origin[0] == "tableau" and origin[1] is not None:
                self.tableau[origin[1]].cards.pop()
            self.foundations[fi].cards.append(card)
            self.post_move_cleanup()
            return True
        return False

    def _start_foundations_from_reserve(self, reserve_index: int) -> None:
        pile = self.reserves[reserve_index]
        if not pile.cards:
            return

        card = pile.cards.pop()
        card.face_up = True
        self.base_rank = card.rank
        suits = [card.suit] + [s for s in range(4) if s != card.suit]
        self.foundation_suits = suits
        self.foundations[0].cards.append(card)
        self.waiting_for_base = False
        self.message = ""
        self.post_move_cleanup()

    def handle_event(self, event) -> None:
        if self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return

        if self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if my < getattr(C, "TOP_BAR_H", 60):
                self._last_click_time = pygame.time.get_ticks()
                self._last_click_pos = (mx, my)
                return

            if not self.waiting_for_base and self._maybe_auto_to_foundation(mx, my):
                return

            stock_rect = pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H)
            if stock_rect.collidepoint((mx, my)):
                self.push_undo()
                self.draw_from_stock()
                self.post_move_cleanup()
                return

            waste_idx = self.waste_pile.hit((mx, my))
            if waste_idx is not None and waste_idx == len(self.waste_pile.cards) - 1:
                rect = self.waste_pile.rect_for_index(waste_idx)
                card = self.waste_pile.cards.pop()
                self.drag = _DragState([card], ("waste", None), (mx - rect.x, my - rect.y), (mx, my))
                return

            for ri, pile in enumerate(self.reserves):
                hit = pile.hit((mx, my))
                if hit is None or hit != len(pile.cards) - 1:
                    continue
                if self.waiting_for_base:
                    self.push_undo()
                    self._start_foundations_from_reserve(ri)
                    return
                rect = pile.rect_for_index(hit)
                card = pile.cards.pop()
                self.drag = _DragState([card], ("reserve", ri), (mx - rect.x, my - rect.y), (mx, my))
                return

            for ti, pile in enumerate(self.tableau):
                hit = pile.hit((mx, my))
                if hit is None or hit == -1:
                    continue
                if not pile.cards[hit].face_up:
                    continue
                seq = pile.cards[hit:]
                if not self._sequence_is_valid(seq):
                    continue
                rect = pile.rect_for_index(hit)
                pile.cards = pile.cards[:hit]
                self.drag = _DragState(seq, ("tableau", ti), (mx - rect.x, my - rect.y), (mx, my))
                return

        elif event.type == pygame.MOUSEMOTION:
            if self.drag:
                self.drag.position = event.pos

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.drag:
                return
            drag = self.drag
            self.drag = None
            stack = drag.cards
            origin, idx = drag.origin
            mx, my = event.pos

            if len(stack) == 1 and not self.waiting_for_base:
                card = stack[0]
                for fi, pile in enumerate(self.foundations):
                    if pile.top_rect().collidepoint((mx, my)) and self.can_move_to_foundation(card, fi):
                        self.push_undo()
                        pile.cards.append(card)
                        self.post_move_cleanup()
                        return

            for ti, pile in enumerate(self.tableau):
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, max(C.CARD_H, len(pile.cards) * pile.fan_y + C.CARD_H))
                if rect.collidepoint((mx, my)):
                    target = pile.cards[-1] if pile.cards else None
                    if self._tableau_allows(stack[0], target):
                        self.push_undo()
                        pile.cards.extend(stack)
                        self.post_move_cleanup()
                        return

            if origin == "waste":
                self.waste_pile.cards.extend(stack)
            elif origin == "reserve" and idx is not None:
                self.reserves[idx].cards.extend(stack)
            elif origin == "tableau" and idx is not None:
                self.tableau[idx].cards.extend(stack)

    def _draw_reserves(self, screen: pygame.Surface) -> None:
        for idx, pile in enumerate(self.reserves):
            pile.draw(screen)
            if self.waiting_for_base and pile.cards:
                rect = pile.top_rect()
                highlight = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
                highlight.fill((255, 220, 120, 60))
                screen.blit(highlight, (rect.x + C.DRAW_OFFSET_X, rect.y + C.DRAW_OFFSET_Y))

    # ----- Draw -----
    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)

        extra = f"Stock replays used: {self.stock_cycles_used}/{self.stock_cycles_allowed}"

        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0

        self._draw_reserves(screen)

        for fi, pile in enumerate(self.foundations):
            pile.draw(screen)
            if not pile.cards:
                if self.waiting_for_base:
                    if fi == 0:
                        txt = C.FONT_SMALL.render("Select base", True, (245, 245, 245))
                        cx = pile.x + C.CARD_W // 2
                        cy = pile.y + C.CARD_H // 2
                        screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
                else:
                    suit = self.foundation_suits[fi]
                    txt = C.FONT_CENTER_SUIT.render(C.SUITS[suit], True, (245, 245, 245))
                    cx = pile.x + C.CARD_W // 2
                    cy = pile.y + C.CARD_H // 2
                    screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        self.stock_pile.draw(screen)
        self.waste_pile.draw(screen)
        for pile in self.tableau:
            pile.draw(screen)

        if self.drag:
            cards = self.drag.cards
            mx, my = self.drag.position
            ox, oy = self.drag.offset
            fan = self.tableau[0].fan_y if self.tableau else 0
            for idx, card in enumerate(cards):
                surf = C.get_card_surface(card)
                screen.blit(surf, (mx - ox, my - oy + idx * fan))

        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 210))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 48))

        C.Scene.draw_top_bar(self, screen, "Duchess (Canfield)", extra)
        self.toolbar.draw(screen)
        if self.help.visible:
            self.help.draw(screen)

    def update(self, dt):
        pass


__all__ = [
    "DuchessGameScene",
    "duchess_save_exists",
    "load_saved_state",
    "clear_saved_state",
]
