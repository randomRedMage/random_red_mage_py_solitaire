import json
import os
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper


_SAVE_FILENAME = "accordion_save.json"
_DEFAULT_DIFFICULTY = "normal"
_DIFFICULTY_INFO: Dict[str, Dict[str, Any]] = {
    "easy": {"label": "Easy", "target": 7},
    "normal": {"label": "Normal", "target": 4},
    "hard": {"label": "Hard", "target": 1},
}


def get_difficulty_label(key: str) -> str:
    info = _DIFFICULTY_INFO.get(key)
    if info:
        return info.get("label", key.title())
    return _DIFFICULTY_INFO[_DEFAULT_DIFFICULTY]["label"]


def _data_dir() -> str:
    try:
        return C._settings_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _save_path() -> str:
    return os.path.join(_data_dir(), _SAVE_FILENAME)


def _safe_write(path: str, payload: Mapping[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        pass


def _safe_read(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    if isinstance(data, Mapping):
        return dict(data)
    return None


def delete_saved_game() -> None:
    try:
        os.remove(_save_path())
    except FileNotFoundError:
        pass
    except Exception:
        pass


def has_saved_game() -> bool:
    data = _safe_read(_save_path())
    if not data or data.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    data = _safe_read(_save_path())
    if not data or data.get("completed"):
        return None
    return data


def peek_saved_game_summary() -> Optional[str]:
    data = load_saved_game()
    if not data:
        return None
    diff = data.get("difficulty", _DEFAULT_DIFFICULTY)
    return get_difficulty_label(diff)


def _card_to_dict(card: C.Card) -> Dict[str, Any]:
    return {"suit": int(card.suit), "rank": int(card.rank), "face_up": bool(card.face_up)}


def _card_from_dict(data: Mapping[str, Any]) -> C.Card:
    suit = int(data.get("suit", 0))
    rank = int(data.get("rank", 1))
    face_up = bool(data.get("face_up", True))
    return C.Card(suit, rank, face_up)


def _serialise_cards(cards: Iterable[C.Card]) -> List[Dict[str, Any]]:
    return [_card_to_dict(card) for card in cards]


def _deserialise_cards(values: Iterable[Mapping[str, Any]]) -> List[C.Card]:
    return [_card_from_dict(item) for item in values]


def _target_for_difficulty(key: str) -> int:
    info = _DIFFICULTY_INFO.get(key)
    if info:
        return int(info.get("target", 0))
    return int(_DIFFICULTY_INFO[_DEFAULT_DIFFICULTY]["target"])


class AccordionGameScene(C.Scene):
    MAX_COLUMNS = 7

    def __init__(self, app, *, difficulty: str = _DEFAULT_DIFFICULTY, load_state: Optional[Mapping[str, Any]] = None):
        super().__init__(app)
        self.difficulty = difficulty if difficulty in _DIFFICULTY_INFO else _DEFAULT_DIFFICULTY
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.piles: List[C.Pile] = []
        self.scroll_y: int = 0
        self._min_scroll_y: int = 0
        self.drag_pan = M.DragPanController()
        self.edge_pan = M.EdgePanDuringDrag(
            edge_margin_px=28,
            top_inset_px=getattr(C, "TOP_BAR_H", 60),
        )
        self.undo_mgr = C.UndoManager()
        self.undo_after_deal_allowed: bool = self.difficulty == "easy"
        self.drag_info: Optional[Dict[str, Any]] = None
        self.message: str = ""
        self.game_over: bool = False
        self.did_win: bool = False

        self.ui_helper = ModeUIHelper(self, game_id="accordion")

        def can_undo() -> bool:
            if not self.undo_mgr.can_undo():
                return False
            if self.difficulty == "easy":
                return True
            return self.undo_after_deal_allowed

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.start_new_game, "tooltip": "Shuffle a new deck"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last pile move"},
            save_action=(
                "Save&Exit",
                {"on_click": self._save_and_exit, "tooltip": "Save progress and return to menu"},
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        )

        self.help = create_modal_help("accordion")

        if load_state:
            self._load_from_serialised(load_state)
        else:
            self._prepare_new_deck(clear_save=True)

    # ----- Persistence helpers -------------------------------------------------
    def _serialise_state(self, *, completed: Optional[bool] = None) -> Dict[str, Any]:
        return {
            "difficulty": self.difficulty,
            "stock": _serialise_cards(self.stock_pile.cards),
            "piles": [_serialise_cards(p.cards) for p in self.piles],
            "scroll_y": self.scroll_y,
            "message": self.message,
            "game_over": self.game_over,
            "did_win": self.did_win,
            "undo_after_deal": self.undo_after_deal_allowed,
            "completed": bool(completed) if completed is not None else self.game_over,
        }

    def _load_from_serialised(self, data: Mapping[str, Any]) -> None:
        difficulty = str(data.get("difficulty", self.difficulty))
        self.difficulty = difficulty if difficulty in _DIFFICULTY_INFO else _DEFAULT_DIFFICULTY
        self.stock_pile.cards = _deserialise_cards(data.get("stock", []))
        piles_data = data.get("piles", [])
        self.piles = []
        for entry in piles_data:
            pile = C.Pile(0, 0)
            pile.cards = _deserialise_cards(entry)
            self.piles.append(pile)
        self.scroll_y = int(data.get("scroll_y", 0))
        self.message = str(data.get("message", "")) if isinstance(data.get("message", ""), str) else ""
        self.game_over = bool(data.get("game_over", False))
        self.did_win = bool(data.get("did_win", False))
        undo_flag = data.get("undo_after_deal")
        if self.difficulty == "easy":
            self.undo_after_deal_allowed = True
        else:
            self.undo_after_deal_allowed = bool(undo_flag)
        self.undo_mgr = C.UndoManager()
        self.drag_info = None
        self._update_layout()
        self.edge_pan.set_active(False)
        delete_saved_game()

    def _save_and_exit(self) -> None:
        payload = self._serialise_state()
        _safe_write(_save_path(), payload)
        self.ui_helper.goto_menu()

    # ----- Setup / reset -------------------------------------------------------
    def start_new_game(self) -> None:
        self._prepare_new_deck(clear_save=True)

    def _prepare_new_deck(self, *, clear_save: bool = False) -> None:
        deck = C.make_deck(shuffle=True)
        for card in deck:
            card.face_up = False
        self.stock_pile.cards = deck
        self.piles = []
        self.scroll_y = 0
        self._min_scroll_y = 0
        self.undo_mgr = C.UndoManager()
        self.undo_after_deal_allowed = self.difficulty == "easy"
        self.drag_info = None
        self.edge_pan.set_active(False)
        self.message = ""
        self.game_over = False
        self.did_win = False
        self._update_layout()
        if clear_save:
            delete_saved_game()

    # ----- Internal helpers ----------------------------------------------------
    def _update_layout(self) -> None:
        margin_left = 70
        top_y = max(110, getattr(C, "TOP_BAR_H", 60) + 40)
        gap_x = max(16, getattr(C, "CARD_GAP_X", 18))
        gap_y = max(24, getattr(C, "CARD_GAP_Y", 26))
        column_gap = gap_x
        first_col_x = margin_left + C.CARD_W + gap_x * 2

        self.stock_pile.x = margin_left
        self.stock_pile.y = top_y

        for index, pile in enumerate(self.piles):
            col = index % self.MAX_COLUMNS
            row = index // self.MAX_COLUMNS
            pile.x = first_col_x + col * (C.CARD_W + column_gap)
            pile.y = top_y + row * (C.CARD_H + gap_y)
            pile.fan_x = 0
            pile.fan_y = 0

        if self.piles:
            last = self.piles[-1]
            content_bottom = last.y + C.CARD_H
        else:
            content_bottom = top_y + C.CARD_H

        available_height = max(200, C.SCREEN_H - top_y - 120)
        total_height = content_bottom - top_y
        if total_height <= available_height:
            self._min_scroll_y = 0
        else:
            self._min_scroll_y = min(0, available_height - total_height)
        self._clamp_scroll()

    def _clamp_scroll(self) -> None:
        if self.scroll_y > 0:
            self.scroll_y = 0
        if self.scroll_y < self._min_scroll_y:
            self.scroll_y = self._min_scroll_y

    def _world_pos(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        x, y = pos
        return x, y - self.scroll_y

    def _push_undo_snapshot(self) -> None:
        snapshot = {
            "stock": list(self.stock_pile.cards),
            "piles": [list(p.cards) for p in self.piles],
            "scroll_y": self.scroll_y,
            "message": self.message,
            "game_over": self.game_over,
            "did_win": self.did_win,
            "undo_after_deal": self.undo_after_deal_allowed,
        }

        def undo_snapshot() -> None:
            self.stock_pile.cards = list(snapshot["stock"])
            self.piles = []
            for cards in snapshot["piles"]:
                pile = C.Pile(0, 0)
                pile.cards = list(cards)
                self.piles.append(pile)
            self.scroll_y = int(snapshot.get("scroll_y", 0))
            self.message = snapshot.get("message", "")
            self.game_over = bool(snapshot.get("game_over", False))
            self.did_win = bool(snapshot.get("did_win", False))
            if self.difficulty == "easy":
                self.undo_after_deal_allowed = True
            else:
                self.undo_after_deal_allowed = bool(snapshot.get("undo_after_deal", False))
            self.drag_info = None
            self.edge_pan.set_active(False)
            self._update_layout()

        self.undo_mgr.push(undo_snapshot)

    def _after_successful_move(self) -> None:
        if self.difficulty != "easy":
            self.undo_after_deal_allowed = True
        self.message = ""
        self.game_over = False
        self.did_win = False
        self._update_layout()
        self._check_for_end()

    def _check_for_end(self) -> None:
        if self.game_over:
            return
        if self.stock_pile.cards:
            return
        if self._available_moves():
            return
        remaining = len(self.piles)
        target = _target_for_difficulty(self.difficulty)
        self.did_win = remaining <= target
        if self.did_win:
            self.message = "Congratulations! You won the round."
        else:
            self.message = "No more moves — game lost."
        self.game_over = True
        delete_saved_game()

    def _available_moves(self) -> bool:
        if len(self.piles) < 2:
            return False
        for index in range(1, len(self.piles)):
            right_cards = self.piles[index].cards
            if not right_cards:
                continue
            right = right_cards[-1]
            for delta in (1, 3):
                left_index = index - delta
                if left_index < 0:
                    continue
                left_cards = self.piles[left_index].cards
                if not left_cards:
                    continue
                left = left_cards[-1]
                if right.rank == left.rank or right.suit == left.suit:
                    return True
        return False

    def _deal_from_stock(self) -> None:
        if not self.stock_pile.cards or self.game_over:
            return
        card = self.stock_pile.cards.pop()
        card.face_up = True
        pile = C.Pile(0, 0)
        pile.cards = [card]
        self.piles.append(pile)
        if self.difficulty != "easy":
            self.undo_after_deal_allowed = False
        self._update_layout()
        self._check_for_end()

    def _start_drag(self, index: int, mouse_pos: Tuple[int, int]) -> None:
        if index < 0 or index >= len(self.piles):
            return
        pile = self.piles[index]
        if not pile.cards or self.game_over:
            return
        rect = pile.top_rect()
        world_mouse = self._world_pos(mouse_pos)
        if not rect.collidepoint(world_mouse):
            return
        dx = rect.x - world_mouse[0]
        dy = rect.y - world_mouse[1]
        self.drag_info = {
            "index": index,
            "offset": (dx, dy),
            "pos": (rect.x, rect.y),
            "cards": list(pile.cards),
        }
        self.edge_pan.set_active(True)

    def _update_drag(self, mouse_pos: Tuple[int, int]) -> None:
        if not self.drag_info:
            return
        dx, dy = self.drag_info["offset"]
        world_mouse = self._world_pos(mouse_pos)
        new_pos = (world_mouse[0] + dx, world_mouse[1] + dy)
        self.drag_info["pos"] = new_pos

    def _finish_drag(self, mouse_pos: Tuple[int, int]) -> None:
        if not self.drag_info:
            return
        src_index = self.drag_info.get("index")
        self.drag_info = None
        self.edge_pan.set_active(False)
        if src_index is None or src_index < 0 or src_index >= len(self.piles):
            return
        world_pos = self._world_pos(mouse_pos)
        target_index = self._drop_target_index(world_pos, exclude=src_index)
        if target_index is None:
            return
        distance = src_index - target_index
        if distance not in (1, 3):
            return
        src_cards = self.piles[src_index].cards
        dst_cards = self.piles[target_index].cards
        if not src_cards or not dst_cards:
            return
        src_top = src_cards[-1]
        dst_top = dst_cards[-1]
        if src_top.rank != dst_top.rank and src_top.suit != dst_top.suit:
            return
        self._push_undo_snapshot()
        dst_cards.extend(src_cards)
        del self.piles[src_index]
        self._after_successful_move()

    def _drop_target_index(self, pos: Tuple[int, int], *, exclude: Optional[int] = None) -> Optional[int]:
        for idx, pile in enumerate(self.piles):
            if idx == exclude:
                continue
            rect = pile.top_rect()
            if rect.collidepoint(pos):
                return idx
        return None

    # ----- Undo ----------------------------------------------------------------
    def undo(self) -> None:
        if not self.undo_mgr.can_undo():
            return
        self.undo_mgr.undo()

    # ----- Event handling ------------------------------------------------------
    def handle_event(self, event) -> None:
        if event.type == pygame.MOUSEMOTION:
            self.edge_pan.on_mouse_pos(event.pos)

        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.KEYDOWN,
                pygame.MOUSEWHEEL,
            ):
                return

        if self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return

        if self.drag_pan.handle_event(event, target=self, clamp=self._clamp_scroll, attr_x=None):
            return

        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y += event.y * 60
            self._clamp_scroll()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            world_pos = self._world_pos(event.pos)
            stock_rect = pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H)
            if stock_rect.collidepoint(world_pos):
                self._deal_from_stock()
                return
            for idx, pile in enumerate(self.piles):
                rect = pile.top_rect()
                if rect.collidepoint(world_pos):
                    self._start_drag(idx, event.pos)
                    return

        if event.type == pygame.MOUSEMOTION:
            self._update_drag(event.pos)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._finish_drag(event.pos)
            return

    # ----- Draw ----------------------------------------------------------------
    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)

        # Edge panning while dragging near screen edges
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        has_v_scroll = self._min_scroll_y < 0
        _, dy = self.edge_pan.step(has_h_scroll=False, has_v_scroll=has_v_scroll)
        if dy:
            self.scroll_y += dy
            self._clamp_scroll()

        prev_offset_y = C.DRAW_OFFSET_Y
        C.DRAW_OFFSET_Y = self.scroll_y

        self.stock_pile.draw(screen)
        for idx, pile in enumerate(self.piles):
            if self.drag_info and idx == self.drag_info.get("index"):
                continue
            pile.draw(screen)

        C.DRAW_OFFSET_Y = prev_offset_y

        if self.drag_info:
            self._draw_dragged_stack(screen)

        self.toolbar.draw(screen)
        self._draw_status(screen)

        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)

    def _draw_dragged_stack(self, screen) -> None:
        info = self.drag_info
        if not info:
            return
        x, y = info.get("pos", (0, 0))
        cards = info.get("cards", [])
        screen_y = y + self.scroll_y
        for offset, card in enumerate(cards):
            surf = C.get_card_surface(card)
            screen.blit(surf, (x, screen_y + offset * 4))

    def _draw_status(self, screen) -> None:
        label = get_difficulty_label(self.difficulty)
        stock_count = len(self.stock_pile.cards)
        piles_count = len(self.piles)
        font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        status = f"Difficulty: {label}    Stock: {stock_count}    Piles: {piles_count}"
        surf = font.render(status, True, C.WHITE)
        screen.blit(surf, (20, 70))
        if self.message:
            msg_font = C.FONT_TITLE if C.FONT_TITLE is not None else font
            msg_surf = msg_font.render(self.message, True, C.GOLD if self.did_win else C.WHITE)
            screen.blit(msg_surf, (C.SCREEN_W // 2 - msg_surf.get_width() // 2, 110))
