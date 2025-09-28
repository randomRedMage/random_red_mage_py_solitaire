import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper, ScrollableSceneMixin


def _chameleon_dir() -> str:
    """Return the directory used to persist Chameleon save data."""

    try:
        return C._settings_dir()  # type: ignore[attr-defined]
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _chameleon_save_path() -> str:
    return os.path.join(_chameleon_dir(), "chameleon_save.json")


def _chameleon_config_path() -> str:
    return os.path.join(_chameleon_dir(), "chameleon_config.json")


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


DEFAULT_CONFIG: Dict[str, Optional[int]] = {"stock_cycles": 1}


def load_chameleon_config() -> Dict[str, Optional[int]]:
    data = _safe_read_json(_chameleon_config_path())
    config = dict(DEFAULT_CONFIG)
    if not data:
        return config
    value = data.get("stock_cycles")
    if value in (None, 0, 1, 3):
        config["stock_cycles"] = value
    elif isinstance(value, int) and value >= 0:
        config["stock_cycles"] = value
    return config


def save_chameleon_config(stock_cycles: Optional[int]) -> None:
    _safe_write_json(_chameleon_config_path(), {"stock_cycles": stock_cycles})


def chameleon_save_exists() -> bool:
    state = _safe_read_json(_chameleon_save_path())
    return bool(state) and not state.get("completed", False)


def update_saved_stock_cycles(stock_cycles: Optional[int]) -> None:
    state = _safe_read_json(_chameleon_save_path())
    if not state:
        return
    state["stock_cycles_allowed"] = stock_cycles
    if stock_cycles is not None:
        used = int(state.get("stock_cycles_used", 0))
        if used > stock_cycles:
            state["stock_cycles_used"] = stock_cycles
    _safe_write_json(_chameleon_save_path(), state)


def load_saved_state() -> Optional[Dict]:
    return _safe_read_json(_chameleon_save_path())


def clear_saved_state() -> None:
    try:
        os.remove(_chameleon_save_path())
    except Exception:
        pass


@dataclass
class _DragState:
    cards: List[C.Card]
    origin: Tuple[str, Optional[int]]
    offset: Tuple[int, int]
    position: Tuple[int, int]


class ChameleonGameScene(ScrollableSceneMixin, C.Scene):
    draw_count: int = 1

    def __init__(self, app, *, load_state: Optional[Dict] = None, stock_cycles: Optional[int] = None):
        super().__init__(app)

        cfg = load_chameleon_config()
        if stock_cycles is None:
            stock_cycles = cfg.get("stock_cycles")

        self.reserve: C.Pile = C.Pile(0, 0, fan_y=0)
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=max(28, int(C.CARD_H * 0.35))) for _ in range(3)]
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.waste_pile: C.Pile = C.Pile(0, 0)

        self.base_rank: int = 1
        self.stock_cycles_allowed: Optional[int] = stock_cycles
        self.stock_cycles_used: int = 0

        self.undo_mgr = C.UndoManager()
        self.message = ""

        self.drag: Optional[_DragState] = None
        self._last_click_time = 0
        self._last_click_pos: Tuple[int, int] = (0, 0)

        self.ui_helper = ModeUIHelper(self, game_id="chameleon")

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

        self.help = create_modal_help("chameleon")

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
        column_gap = C.CARD_W // 2

        foundation_span = len(self.foundations) * C.CARD_W + (len(self.foundations) - 1) * foundation_gap
        total_width = C.CARD_W + column_gap + foundation_span
        left_edge = max((C.SCREEN_W - total_width) // 2, 24)

        column_x = left_edge
        self.reserve.x = column_x
        self.reserve.y = top_y

        foundation_start_x = column_x + C.CARD_W + column_gap
        for idx, pile in enumerate(self.foundations):
            pile.x = foundation_start_x + idx * (C.CARD_W + foundation_gap)
            pile.y = top_y

        row2_y = top_y + C.CARD_H + row_gap
        self.stock_pile.x = column_x
        self.stock_pile.y = row2_y

        self.waste_pile.x = column_x
        self.waste_pile.y = row2_y + C.CARD_H + row_gap

        tableau_start_x = foundation_start_x
        for idx, pile in enumerate(self.tableau):
            pile.x = tableau_start_x + idx * (C.CARD_W + foundation_gap)
            pile.y = row2_y

    def iter_scroll_piles(self):  # type: ignore[override]
        yield self.reserve
        yield from self.foundations
        yield from self.tableau
        yield self.stock_pile
        yield self.waste_pile

    # ----- Deal / Restart -----
    def _clear(self) -> None:
        self.reserve.cards.clear()
        for pile in self.foundations:
            pile.cards.clear()
        for pile in self.tableau:
            pile.cards.clear()
        self.stock_pile.cards.clear()
        self.waste_pile.cards.clear()
        self.drag = None
        self.message = ""
        self.edge_pan.set_active(False)

    def deal_new(self) -> None:
        cfg = load_chameleon_config()
        self.stock_cycles_allowed = cfg.get("stock_cycles")
        self._clear()
        deck = C.make_deck(shuffle=True)

        for _ in range(12):
            card = deck.pop()
            card.face_up = True
            self.reserve.cards.append(card)

        starter = deck.pop()
        starter.face_up = True
        self.base_rank = starter.rank
        suits = [starter.suit] + [s for s in range(4) if s != starter.suit]
        self.foundation_suits = suits
        self.foundations[0].cards.append(starter)

        for idx in range(1, 4):
            self.foundations[idx].cards.clear()

        for pile in self.tableau:
            card = deck.pop()
            card.face_up = True
            pile.cards.append(card)

        for card in deck:
            card.face_up = False
        self.stock_pile.cards = deck
        self.waste_pile.cards.clear()

        self.stock_cycles_used = 0
        self.reset_scroll()
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
            "reserve": cap_pile(self.reserve),
            "foundations": [cap_pile(p) for p in self.foundations],
            "foundation_suits": list(self.foundation_suits),
            "tableau": [cap_pile(p) for p in self.tableau],
            "stock": cap_pile(self.stock_pile),
            "waste": cap_pile(self.waste_pile),
            "base_rank": self.base_rank,
            "stock_cycles_allowed": self.stock_cycles_allowed,
            "stock_cycles_used": self.stock_cycles_used,
            "message": self.message,
        }

    def restore_snapshot(self, snap: Dict) -> None:
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]

        self.reserve.cards = mk(snap.get("reserve", []))
        for idx, pile in enumerate(self.foundations):
            data = snap.get("foundations", [])
            pile.cards = mk(data[idx] if idx < len(data) else [])
        self.foundation_suits = list(snap.get("foundation_suits", [0, 1, 2, 3]))
        for idx, pile in enumerate(self.tableau):
            data = snap.get("tableau", [])
            pile.cards = mk(data[idx] if idx < len(data) else [])
        self.stock_pile.cards = mk(snap.get("stock", []))
        self.waste_pile.cards = mk(snap.get("waste", []))
        self.base_rank = int(snap.get("base_rank", 1))
        self.stock_cycles_allowed = snap.get("stock_cycles_allowed")
        self.stock_cycles_used = int(snap.get("stock_cycles_used", 0))
        self.message = snap.get("message", "")
        self.drag = None
        self.reset_scroll()
        self.edge_pan.set_active(False)

    def push_undo(self) -> None:
        snap = self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self) -> None:
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.message = ""
            self.drag = None
            self.edge_pan.set_active(False)

    # ----- Save / Load helpers -----
    def _state_dict(self) -> Dict:
        state = self.record_snapshot()
        state["completed"] = self.is_completed()
        return state

    def _save_game(self, to_menu: bool = False) -> None:
        _safe_write_json(_chameleon_save_path(), self._state_dict())
        if to_menu:
            from solitaire.scenes.game_options.chameleon_options import ChameleonOptionsScene

            self.next_scene = ChameleonOptionsScene(self.app)

    def _load_from_state(self, state: Dict) -> None:
        self.restore_snapshot(state)
        self.drag = None
        self.edge_pan.set_active(False)

    # ----- Gameplay helpers -----
    def is_completed(self) -> bool:
        return all(len(pile.cards) == 13 for pile in self.foundations)

    def draw_from_stock(self) -> None:
        if not self.stock_pile.cards:
            if not self.waste_pile.cards:
                return
            if self.stock_cycles_allowed is not None and self.stock_cycles_used >= self.stock_cycles_allowed:
                self.message = "No more stock replays"
                return
            self.stock_pile.cards = [C.Card(c.suit, c.rank, False) for c in reversed(self.waste_pile.cards)]
            for card in self.stock_pile.cards:
                card.face_up = False
            self.waste_pile.cards.clear()
            self.stock_cycles_used += 1
            return

        count = min(self.draw_count, len(self.stock_pile.cards))
        moved: List[C.Card] = []
        for _ in range(count):
            card = self.stock_pile.cards.pop()
            card.face_up = True
            moved.append(card)
        self.waste_pile.cards.extend(moved)
        self.message = ""

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
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
            expected = lower.rank + 1
            if expected > 13:
                expected = 1
            if upper.rank != expected:
                return False
        return True

    def _auto_fill_empty_columns(self) -> None:
        changed = True
        while changed:
            changed = False
            for pile in self.tableau:
                if pile.cards:
                    continue
                card: Optional[C.Card] = None
                if self.reserve.cards:
                    card = self.reserve.cards.pop()
                elif self.waste_pile.cards:
                    card = self.waste_pile.cards.pop()
                if card is not None:
                    card.face_up = True
                    pile.cards.append(card)
                    changed = True

    def post_move_cleanup(self) -> None:
        self._auto_fill_empty_columns()
        if self.is_completed():
            self.message = "You win!"
        self._clamp_scroll()

    # ----- Event handling -----
    def _maybe_auto_to_foundation(self, mx: int, my: int) -> bool:
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

        # Check waste top first
        if self.waste_pile.cards:
            rect = self.waste_pile.top_rect()
            if rect.collidepoint((mx, my)):
                card = self.waste_pile.cards[-1]
                if self._try_move_card_to_foundation(card, ("waste", None)):
                    return True

        # Tableau tops
        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            rect = pile.top_rect()
            if rect.collidepoint((mx, my)):
                card = pile.cards[-1]
                if self._try_move_card_to_foundation(card, ("tableau", idx)):
                    return True

        # Reserve top
        if self.reserve.cards and self.reserve.top_rect().collidepoint((mx, my)):
            card = self.reserve.cards[-1]
            if self._try_move_card_to_foundation(card, ("reserve", None)):
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
            elif origin[0] == "reserve":
                self.reserve.cards.pop()
            elif origin[0] == "tableau" and origin[1] is not None:
                self.tableau[origin[1]].cards.pop()
            self.foundations[fi].cards.append(card)
            self.post_move_cleanup()
            return True
        return False

    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.edge_pan.on_mouse_pos(event.pos)

        if self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return

        if self.ui_helper.handle_menu_event(event):
            return
        if self.handle_scroll_event(event):
            return

        if self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            mxw, myw = self._screen_to_world((mx, my))
            if my < getattr(C, "TOP_BAR_H", 60):
                self._last_click_time = pygame.time.get_ticks()
                self._last_click_pos = (mxw, myw)
                return

            if self._maybe_auto_to_foundation(mxw, myw):
                return

            stock_rect = pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H)
            if stock_rect.collidepoint((mxw, myw)):
                self.push_undo()
                self.draw_from_stock()
                self.post_move_cleanup()
                return

            waste_idx = self.waste_pile.hit((mxw, myw))
            if waste_idx is not None and waste_idx == len(self.waste_pile.cards) - 1:
                rect = self.waste_pile.rect_for_index(waste_idx)
                card = self.waste_pile.cards.pop()
                self.drag = _DragState([card], ("waste", None), (mxw - rect.x, myw - rect.y), event.pos)
                self.edge_pan.set_active(True)
                return

            reserve_idx = self.reserve.hit((mxw, myw))
            if reserve_idx is not None and reserve_idx == len(self.reserve.cards) - 1:
                rect = self.reserve.rect_for_index(reserve_idx)
                card = self.reserve.cards.pop()
                self.drag = _DragState([card], ("reserve", None), (mxw - rect.x, myw - rect.y), event.pos)
                self.edge_pan.set_active(True)
                return

            for ti, pile in enumerate(self.tableau):
                hit = pile.hit((mxw, myw))
                if hit is None or hit == -1:
                    continue
                if not pile.cards[hit].face_up:
                    continue
                seq = pile.cards[hit:]
                if not self._sequence_is_valid(seq):
                    continue
                rect = pile.rect_for_index(hit)
                pile.cards = pile.cards[:hit]
                self.drag = _DragState(seq, ("tableau", ti), (mxw - rect.x, myw - rect.y), event.pos)
                self.edge_pan.set_active(True)
                return

        elif event.type == pygame.MOUSEMOTION:
            if self.drag:
                self.drag.position = event.pos

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.drag:
                return
            drag = self.drag
            self.drag = None
            self.edge_pan.set_active(False)
            stack = drag.cards
            origin, idx = drag.origin
            mxw, myw = self._screen_to_world(event.pos)

            # Foundations (single card only)
            if len(stack) == 1:
                card = stack[0]
                for fi, pile in enumerate(self.foundations):
                    if pile.top_rect().collidepoint((mxw, myw)) and self.can_move_to_foundation(card, fi):
                        self.push_undo()
                        pile.cards.append(card)
                        self.post_move_cleanup()
                        return

            # Tableau drops
            for ti, pile in enumerate(self.tableau):
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, max(C.CARD_H, len(pile.cards) * pile.fan_y + C.CARD_H))
                if rect.collidepoint((mxw, myw)):
                    target = pile.cards[-1] if pile.cards else None
                    if self._tableau_allows(stack[0], target):
                        self.push_undo()
                        pile.cards.extend(stack)
                        self.post_move_cleanup()
                        return

            # Return to origin if move invalid
            if origin == "waste":
                self.waste_pile.cards.extend(stack)
            elif origin == "reserve":
                self.reserve.cards.extend(stack)
            elif origin == "tableau" and idx is not None:
                self.tableau[idx].cards.extend(stack)

    def _draw_reserve_with_count(self, screen: pygame.Surface) -> None:
        self.reserve.draw(screen)
        total_cards = len(self.reserve.cards)
        if total_cards <= 0:
            return
        rect = pygame.Rect(
            self.reserve.x + C.DRAW_OFFSET_X,
            self.reserve.y + C.DRAW_OFFSET_Y,
            C.CARD_W,
            C.CARD_H,
        )
        badge_rect = pygame.Rect(rect.right - 34, rect.bottom - 28, 28, 22)
        pygame.draw.rect(screen, (35, 35, 50), badge_rect, border_radius=8)
        pygame.draw.rect(screen, (210, 210, 220), badge_rect, width=1, border_radius=8)
        badge_text = C.FONT_SMALL.render(str(total_cards), True, (235, 235, 245))
        screen.blit(
            badge_text,
            (
                badge_rect.centerx - badge_text.get_width() // 2,
                badge_rect.centery - badge_text.get_height() // 2,
            ),
        )

    # ----- Draw -----
    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)

        extra = (
            "Stock replays: unlimited"
            if self.stock_cycles_allowed is None
            else f"Stock replays used: {self.stock_cycles_used}/{self.stock_cycles_allowed}"
        )

        with self.scrolling_draw_offset():
            for fi, pile in enumerate(self.foundations):
                pile.draw(screen)
                if not pile.cards:
                    suit = self.foundation_suits[fi]
                    txt = C.FONT_CENTER_SUIT.render(C.SUITS[suit], True, (245, 245, 245))
                    cx, cy = self._world_to_screen((pile.x + C.CARD_W // 2, pile.y + C.CARD_H // 2))
                    screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

            self._draw_reserve_with_count(screen)
            self.stock_pile.draw(screen)
            self.waste_pile.draw(screen)
            for pile in self.tableau:
                pile.draw(screen)

        if self.drag:
            cards = self.drag.cards
            mx, my = self.drag.position
            ox, oy = self.drag.offset
            for idx, card in enumerate(cards):
                surf = C.get_card_surface(card)
                screen.blit(surf, (mx - ox, my - oy + idx * self.tableau[0].fan_y))

        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 210))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 48))

        C.Scene.draw_top_bar(self, screen, "Chameleon", extra)
        self.toolbar.draw(screen)
        if self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

    def update(self, dt):
        pass


__all__ = [
    "ChameleonGameScene",
    "chameleon_save_exists",
    "load_saved_state",
    "load_chameleon_config",
    "clear_saved_state",
    "save_chameleon_config",
    "update_saved_stock_cycles",
]
