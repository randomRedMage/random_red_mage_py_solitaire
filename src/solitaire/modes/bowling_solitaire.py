"""Bowling Solitaire mode implementation."""

from __future__ import annotations

import json
import os
import random
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

import pygame

from solitaire import common as C
from solitaire import ui as UI
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper


# --- Save helpers -----------------------------------------------------------


def _data_dir() -> str:
    try:
        return C._settings_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _save_path() -> str:
    return os.path.join(_data_dir(), "bowling_solitaire_save.json")


def _safe_write(path: str, payload: Dict[str, Any]) -> None:
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
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def has_saved_game() -> bool:
    state = _safe_read(_save_path())
    return bool(state) and not state.get("completed", False)


def load_saved_game() -> Optional[Dict[str, Any]]:
    return _safe_read(_save_path())


# --- Core data structures ---------------------------------------------------


PIN_ROW_COUNTS: Tuple[int, ...] = (4, 3, 2, 1)


PIN_ADJACENCY: Dict[int, Set[int]] = {
    0: {1, 4},
    1: {0, 2, 4, 5},
    2: {1, 3, 5, 6},
    3: {2, 6},
    4: {0, 1, 5, 7},
    5: {1, 2, 4, 6, 7, 8},
    6: {2, 3, 5, 8},
    7: {4, 5, 8, 9},
    8: {5, 6, 7, 9},
    9: {7, 8},
}


BACK_ROW_INDICES: Set[int] = {0, 1, 2, 3}
CENTER_PIN_INDEX = 5


def _create_deck(shuffle: bool = True) -> List[C.Card]:
    cards = [C.Card(0, rank, True) for rank in range(1, 11)]
    cards.extend(C.Card(1, rank, True) for rank in range(1, 11))
    if shuffle:
        random.shuffle(cards)
    return cards


def _card_to_dict(card: C.Card) -> Dict[str, Any]:
    return {"suit": int(card.suit), "rank": int(card.rank), "face_up": bool(card.face_up)}


def _card_from_dict(data: Mapping[str, Any]) -> C.Card:
    suit = int(data.get("suit", 0))
    rank = int(data.get("rank", 1))
    card = C.Card(suit, rank, bool(data.get("face_up", True)))
    return card


@dataclass
class Pin:
    index: int
    card: C.Card
    row: int
    col: int
    rect: pygame.Rect
    removed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "card": _card_to_dict(self.card),
            "row": self.row,
            "col": self.col,
            "removed": self.removed,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any], rect: pygame.Rect) -> "Pin":
        idx = int(data.get("index", 0))
        row = int(data.get("row", 0))
        col = int(data.get("col", 0))
        removed = bool(data.get("removed", False))
        card_data = data.get("card", {})
        card = _card_from_dict(card_data if isinstance(card_data, Mapping) else {})
        return Pin(index=idx, card=card, row=row, col=col, rect=rect.copy(), removed=removed)


@dataclass
class FrameScore:
    symbols: List[str]
    total: Optional[int] = None

    def reset(self) -> None:
        for i in range(len(self.symbols)):
            self.symbols[i] = ""
        self.total = None

    def to_dict(self) -> Dict[str, Any]:
        return {"symbols": list(self.symbols), "total": self.total}

    @staticmethod
    def from_dict(data: Mapping[str, Any], expected_len: int) -> "FrameScore":
        symbols = list(data.get("symbols", [""] * expected_len))
        if len(symbols) < expected_len:
            symbols.extend([""] * (expected_len - len(symbols)))
        elif len(symbols) > expected_len:
            symbols = symbols[:expected_len]
        total = data.get("total")
        if isinstance(total, int):
            return FrameScore(symbols=symbols, total=total)
        return FrameScore(symbols=symbols, total=None)


class BallPile:
    def __init__(self, cards: Iterable[C.Card]):
        stack = list(cards)
        self._stack: List[C.Card] = stack[:-1]
        self.face_up: Optional[C.Card] = stack[-1] if stack else None
        if self.face_up is not None:
            self.face_up.face_up = True
        for c in self._stack:
            c.face_up = False

    def remaining_hidden(self) -> int:
        return len(self._stack)

    def flip_next(self) -> None:
        if self._stack:
            self.face_up = self._stack.pop()
            self.face_up.face_up = True
        else:
            self.face_up = None

    def use_face_up(self) -> Optional[C.Card]:
        card = self.face_up
        if card is not None:
            card.face_up = True
        self.face_up = None
        self.flip_next()
        return card

    def discard_face_up(self) -> Optional[C.Card]:
        card = self.face_up
        if card is not None:
            card.face_up = True
        self.face_up = None
        self.flip_next()
        return card

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_up": _card_to_dict(self.face_up) if self.face_up else None,
            "stack": [_card_to_dict(c) for c in self._stack],
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> "BallPile":
        stack_data = data.get("stack", [])
        cards = [_card_from_dict(entry) for entry in stack_data if isinstance(entry, Mapping)]
        face_up_data = data.get("face_up")
        if isinstance(face_up_data, Mapping):
            face = _card_from_dict(face_up_data)
            cards.append(face)
        return BallPile(cards)


# --- Bowling Solitaire game scene ------------------------------------------


class BowlingSolitaireGameScene(C.Scene):
    """Implements Bowling Solitaire gameplay with scoring."""

    def __init__(
        self,
        app,
        *,
        player_initials: str,
        load_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(app)

        provided_initials = (player_initials or "").strip().upper()[:3]
        self.player_initials: str = ""
        self._pending_initials: str = provided_initials
        self._initials_prompt_visible: bool = load_state is None
        self._initials_input_active: bool = self._initials_prompt_visible
        self._initials_panel_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self._initials_input_rect: pygame.Rect = pygame.Rect(0, 0, 280, 60)
        self._initials_accept_button = UI.Button(
            "Confirm Initials",
            self._commit_initials,
            enabled_fn=lambda: bool(self._pending_initials),
            min_width=200,
        )

        self.scroll_x: int = 0
        self.scroll_y: int = 0
        self._drag_vscroll: bool = False
        self._drag_hscroll: bool = False
        self._vscroll_drag_offset: int = 0
        self._hscroll_drag_offset: int = 0
        self._vscroll_geom: Optional[Tuple[int, int, int, int, int]] = None
        self._hscroll_geom: Optional[Tuple[int, int, int, int, int]] = None

        self.ui_helper = ModeUIHelper(self, game_id="bowling_solitaire")

        self.help = create_modal_help("bowling_solitaire")

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.new_game, "tooltip": "Start a new 10-frame game"},
            save_action=(
                "Save&Exit",
                {
                    "on_click": self.save_and_exit,
                    "tooltip": "Save current progress and exit to menu",
                },
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            toolbar_kwargs={"align": "left"},
        )

        self.ball_action_buttons: List[UI.Button] = []
        self._action_button_size: int = 110

        self.score_frames: List[FrameScore] = [FrameScore(["", ""]) for _ in range(9)]
        self.score_frames.append(FrameScore(["", "", ""]))

        self.frame_rolls: List[List[int]] = [[] for _ in range(10)]
        self.roll_history: List[int] = []

        self.current_frame: int = 0
        self.current_ball: int = 0
        self.ball_actions: int = 0
        self.frame_completed: bool = False
        self.game_completed: bool = False

        self.pins: List[Pin] = []
        self.ball_piles: List[BallPile] = []
        self.ball_waste: List[C.Card] = []
        self.pins_removed_this_ball: Set[int] = set()
        self.pins_removed_prev_ball: Set[int] = set()
        self.selected_ball_index: Optional[int] = None
        self.selected_pins: List[int] = []
        self.status_message: str = "Select a ball card to begin."

        self.pin_slots: List[pygame.Rect] = []
        self.ball_face_rects: List[pygame.Rect] = []
        self.ball_stack_rects: List[pygame.Rect] = []
        self.waste_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)

        self.scoreboard_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.player_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.player_header_rect: pygame.Rect = pygame.Rect(0, 0, 0, 0)
        self.score_cells: List[Dict[str, Any]] = []

        self._create_action_buttons()
        self.compute_layout()

        if load_state:
            if not self._load_from_state(load_state):
                self.new_game()
        else:
            self.new_game()

    # ------------------------------------------------------------------ setup

    def compute_layout(self) -> None:
        top_margin = getattr(C, "TOP_BAR_H", 60) + 20
        left_margin = 40
        right_margin = 40
        self.scoreboard_rect = pygame.Rect(
            left_margin,
            top_margin,
            C.SCREEN_W - left_margin - right_margin,
            170,
        )
        self._layout_scoreboard()

        pin_top = self.scoreboard_rect.bottom + 30
        gap_y = 6
        gap_x = 18
        pin_slots: List[pygame.Rect] = []
        cx = C.SCREEN_W // 2
        for row_index, count in enumerate(PIN_ROW_COUNTS):
            row_width = count * C.CARD_W + (count - 1) * gap_x
            left = cx - row_width // 2
            y = pin_top + row_index * (C.CARD_H + gap_y)
            for col in range(count):
                rect = pygame.Rect(left + col * (C.CARD_W + gap_x), y, C.CARD_W, C.CARD_H)
                pin_slots.append(rect)
        self.pin_slots = pin_slots

        lane_bottom = pin_slots[-1].bottom if pin_slots else pin_top
        piles_top = lane_bottom + 40
        pile_gap = 60
        pile_width = C.CARD_W
        total_width = pile_width * 3 + pile_gap * 2
        start_x = cx - total_width // 2
        self.ball_face_rects = []
        self.ball_stack_rects = []
        for i in range(3):
            x = start_x + i * (pile_width + pile_gap)
            face_rect = pygame.Rect(x, piles_top, pile_width, C.CARD_H)
            stack_rect = pygame.Rect(x - 16, piles_top, pile_width // 2, C.CARD_H)
            self.ball_face_rects.append(face_rect)
            self.ball_stack_rects.append(stack_rect)

        waste_rect = pygame.Rect(start_x + 3 * (pile_width + pile_gap), piles_top, pile_width, C.CARD_H)
        self.waste_rect = waste_rect

        button_size = self._action_button_size
        btn_gap = 18
        btn_x = start_x - button_size - 30
        btn_y = piles_top
        for idx, btn in enumerate(self.ball_action_buttons):
            btn.rect.size = (button_size, button_size)
            btn.set_position(btn_x, btn_y + idx * (button_size + btn_gap))

        self._layout_initials_prompt()
        self._clamp_scroll()

    def _layout_scoreboard(self) -> None:
        rect = self.scoreboard_rect
        header_h = 46
        row_h = rect.height - header_h - 16
        player_col_w = 140
        frame_col_w = (rect.width - player_col_w) // 11
        tenth_col_w = frame_col_w * 2
        frame_col_w = (rect.width - player_col_w - tenth_col_w) // 9

        self.player_header_rect = pygame.Rect(rect.left, rect.top, player_col_w, header_h)
        self.player_rect = pygame.Rect(rect.left + 6, rect.top + header_h, player_col_w - 12, row_h)
        self.score_cells = []
        x = rect.left + player_col_w
        header_top = rect.top
        for frame_index in range(10):
            width = tenth_col_w if frame_index == 9 else frame_col_w
            cell_rect = pygame.Rect(x, header_top + header_h, width, row_h)
            box_height = 28
            box_width = max(20, min(38, width // (3 if frame_index == 9 else 2)))
            box_spacing = 4
            ball_boxes: List[pygame.Rect] = []
            boxes = 3 if frame_index == 9 else 2
            right = cell_rect.right - 6
            for _ in range(boxes):
                box = pygame.Rect(right - box_width, cell_rect.top + 6, box_width, box_height)
                ball_boxes.insert(0, box)
                right -= box_width + box_spacing
            score_rect = pygame.Rect(cell_rect.left + 6, cell_rect.bottom - 34, width - 12, 28)
            header_rect = pygame.Rect(cell_rect.left, header_top, width, header_h)
            self.score_cells.append(
                {
                    "frame_rect": cell_rect,
                    "header_rect": header_rect,
                    "ball_boxes": ball_boxes,
                    "score_rect": score_rect,
                }
            )
            x += width

    def _layout_initials_prompt(self) -> None:
        panel_w = 480
        panel_h = 240
        top_bar = getattr(C, "TOP_BAR_H", 60)
        center_y = top_bar + panel_h // 2 + 60
        self._initials_panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        self._initials_panel_rect.center = (C.SCREEN_W // 2, center_y)

        self._initials_input_rect = pygame.Rect(0, 0, 280, 60)
        self._initials_input_rect.center = (
            self._initials_panel_rect.centerx,
            self._initials_panel_rect.top + 120,
        )
        btn_y = self._initials_input_rect.bottom + 30
        self._initials_accept_button.set_position(
            self._initials_panel_rect.centerx - self._initials_accept_button.rect.width // 2,
            btn_y,
        )

    def _content_bounds(self) -> Tuple[int, int, int, int]:
        rects: List[pygame.Rect] = []
        if self.scoreboard_rect.width and self.scoreboard_rect.height:
            rects.append(self.scoreboard_rect)
        rects.extend(pin.rect for pin in self.pins)
        rects.extend(self.ball_face_rects)
        rects.extend(self.ball_stack_rects)
        rects.extend(btn.rect for btn in self.ball_action_buttons)
        if self.waste_rect.width and self.waste_rect.height:
            rects.append(self.waste_rect)
        if not rects:
            top_bar = getattr(C, "TOP_BAR_H", 60)
            return 0, C.SCREEN_W, top_bar, C.SCREEN_H
        left = min(rect.left for rect in rects)
        right = max(rect.right for rect in rects)
        top = min(rect.top for rect in rects)
        bottom = max(rect.bottom for rect in rects)
        return left, right, top, bottom

    def _scroll_limits(self) -> Tuple[int, int, int, int]:
        left, right, top, bottom = self._content_bounds()
        margin_x = 40
        margin_y = 20
        top_bar = getattr(C, "TOP_BAR_H", 60)
        max_sx = margin_x - left
        min_sx = min(0, C.SCREEN_W - right - margin_x)
        max_sy = top_bar + margin_y - top
        min_sy = min(0, C.SCREEN_H - bottom - margin_y)
        if max_sx < min_sx:
            max_sx = min_sx
        if max_sy < min_sy:
            max_sy = min_sy
        return min_sx, max_sx, min_sy, max_sy

    def _clamp_scroll(self) -> None:
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if self.scroll_x < min_sx:
            self.scroll_x = min_sx
        elif self.scroll_x > max_sx:
            self.scroll_x = max_sx
        if self.scroll_y < min_sy:
            self.scroll_y = min_sy
        elif self.scroll_y > max_sy:
            self.scroll_y = max_sy

    def _vertical_scrollbar(self) -> Optional[Tuple[pygame.Rect, pygame.Rect, int, int, int, int, int]]:
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sy <= min_sy:
            return None
        track_x = C.SCREEN_W - 12
        track_y = getattr(C, "TOP_BAR_H", 60)
        track_h = C.SCREEN_H - track_y - 10
        if track_h <= 0:
            return None
        view_h = track_h
        content_h = view_h + (max_sy - min_sy)
        knob_h = max(30, int(track_h * (view_h / max(1, content_h))))
        denom = max_sy - min_sy
        t = (self.scroll_y - min_sy) / denom if denom else 1.0
        knob_y = int(track_y + (track_h - knob_h) * (1.0 - t))
        knob_rect = pygame.Rect(track_x, knob_y, 6, knob_h)
        track_rect = pygame.Rect(track_x, track_y, 6, track_h)
        return track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h

    def _horizontal_scrollbar(self) -> Optional[Tuple[pygame.Rect, pygame.Rect, int, int, int, int, int]]:
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sx <= min_sx:
            return None
        track_x = 10
        track_w = C.SCREEN_W - 20
        track_y = C.SCREEN_H - 12
        if track_w <= 0:
            return None
        view_w = track_w
        content_w = view_w + (max_sx - min_sx)
        knob_w = max(30, int(track_w * (view_w / max(1, content_w))))
        denom = max_sx - min_sx
        t = (self.scroll_x - min_sx) / denom if denom else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        track_rect = pygame.Rect(track_x, track_y, track_w, 6)
        knob_rect = pygame.Rect(knob_x, track_y, knob_w, 6)
        return track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w

    def _create_action_buttons(self) -> None:
        size = self._action_button_size
        self.ball_action_buttons = [
            UI.Button(
                "Bowl",
                self.apply_selection,
                enabled_fn=self.can_apply_selection,
                height=size,
                min_width=size,
            ),
            UI.Button(
                "Next Ball",
                self.advance_to_next_ball,
                enabled_fn=self.can_force_next_ball,
                height=size,
                min_width=size,
            ),
            UI.Button(
                "Discard Ball",
                self.discard_selected_ball,
                enabled_fn=self.can_discard_ball,
                height=size,
                min_width=size,
            ),
            UI.Button(
                "Clear Selection",
                self.clear_selection,
                enabled_fn=lambda: bool(self.selected_pins),
                height=size,
                min_width=size,
            ),
        ]
        for btn in self.ball_action_buttons:
            btn.rect.size = (size, size)

    # ------------------------------------------------------------------ state

    def new_game(self) -> None:
        self.current_frame = 0
        self.current_ball = 0
        self.ball_actions = 0
        self.frame_completed = False
        self.game_completed = False
        self.roll_history = []
        self.frame_rolls = [[] for _ in range(10)]
        for frame in self.score_frames:
            frame.reset()
        self.ball_waste = []
        self.status_message = "Frame 1 – select a ball card to start."
        self.scroll_x = 0
        self.scroll_y = 0
        self._deal_new_frame()
        self._clamp_scroll()
        try:
            if os.path.isfile(_save_path()):
                os.remove(_save_path())
        except Exception:
            pass

    def _deal_new_frame(self) -> None:
        deck = _create_deck(shuffle=True)
        pin_cards = deck[:10]
        ball_cards = deck[10:]
        pins: List[Pin] = []
        for idx, slot in enumerate(self.pin_slots):
            card = pin_cards[idx]
            card.face_up = True
            # Determine row/col
            row = 0
            remaining = idx
            for r_count in PIN_ROW_COUNTS:
                if remaining < r_count:
                    break
                remaining -= r_count
                row += 1
            col = remaining
            pins.append(Pin(index=idx, card=card, row=row, col=col, rect=slot.copy(), removed=False))
        self.pins = pins

        pile_sizes = (5, 3, 2)
        piles: List[BallPile] = []
        offset = 0
        for size in pile_sizes:
            pile_cards = ball_cards[offset : offset + size]
            piles.append(BallPile(pile_cards))
            offset += size
        self.ball_piles = piles
        self.ball_waste = []
        self.selected_ball_index = None
        self.selected_pins = []
        self.pins_removed_this_ball = set()
        self.pins_removed_prev_ball = set()
        self.ball_actions = 0
        self.current_ball = 0

    # ----------------------------------------------------------------- helpers

    def pins_remaining(self) -> int:
        return sum(1 for pin in self.pins if not pin.removed)

    def can_apply_selection(self) -> bool:
        valid, _ = self._validate_current_selection()
        return valid

    def can_discard_ball(self) -> bool:
        if self.game_completed:
            return False
        if self.selected_ball_index is None:
            return False
        pile = self.ball_piles[self.selected_ball_index]
        return pile.face_up is not None

    def can_force_next_ball(self) -> bool:
        if self.game_completed:
            return False
        if self.current_frame >= 10:
            return False
        return True

    # ---------------------------------------------------------------- controls

    def clear_selection(self) -> None:
        self.selected_pins.clear()
        self.status_message = "Selection cleared."

    def apply_selection(self) -> None:
        valid, message = self._validate_current_selection()
        if not valid:
            if message:
                self.status_message = message
            return
        if self.selected_ball_index is None:
            self.status_message = "Select a ball card first."
            return
        pile = self.ball_piles[self.selected_ball_index]
        card = pile.face_up
        if card is None:
            self.status_message = "No card available in that pile."
            return
        pins_to_remove = list(self.selected_pins)
        pins_to_remove.sort()
        for idx in pins_to_remove:
            self.pins[idx].removed = True
        used_card = pile.use_face_up()
        if used_card is not None:
            self.ball_waste.append(used_card)
        self.pins_removed_this_ball.update(pins_to_remove)
        self.selected_pins.clear()
        self.ball_actions += 1
        self.status_message = "Pins knocked down."
        if self.pins_remaining() == 0:
            self._end_ball(after_strike=True)
            return
        if not self._has_available_move():
            self._end_ball(no_moves=True)
            return

    def discard_selected_ball(self) -> None:
        if not self.can_discard_ball():
            return
        self._end_ball(discarded=True)

    def advance_to_next_ball(self) -> None:
        if not self.can_force_next_ball():
            return
        self.selected_ball_index = None
        self.selected_pins.clear()
        self._end_ball(manual=True)

    # --------------------------------------------------------------- validation

    def _validate_current_selection(self) -> Tuple[bool, Optional[str]]:
        if self.game_completed:
            return False, "Game complete."
        if self.selected_ball_index is None:
            return False, None
        pile = self.ball_piles[self.selected_ball_index]
        card = pile.face_up
        if card is None:
            return False, "That pile has no remaining cards."
        if not self.selected_pins:
            return False, "Select one or more pins."
        return self._validate_selection_for_card(self.selected_ball_index, card, self.selected_pins)

    def _validate_selection_for_card(
        self,
        ball_index: int,
        card: C.Card,
        pin_indices: Sequence[int],
    ) -> Tuple[bool, Optional[str]]:
        if not pin_indices:
            return False, "No pins selected."
        if len(pin_indices) > 3:
            return False, "You may remove at most three pins per card."
        pins = [self.pins[idx] for idx in pin_indices]
        if any(pin.removed for pin in pins):
            return False, "One of the selected pins is already removed."

        if self.current_ball == 0 and self.ball_actions == 0:
            for pin in pins:
                if pin.index in BACK_ROW_INDICES:
                    return False, "Back-row pins can't be taken first."
            if len(pins) == 1 and pins[0].index == CENTER_PIN_INDEX:
                return False, "The middle pin must be part of a combo."

        include_back_row = any(pin.index in BACK_ROW_INDICES for pin in pins)

        if (
            self.current_ball == 1
            and self.ball_actions == 0
            and include_back_row
            and not self.pins_removed_prev_ball
            and len(pins) == 1
        ):
            return False, "Back-row pins can't be taken first."

        if self.current_ball > 0 and self.pins_removed_prev_ball:
            if self.current_ball == 1 and self.ball_actions == 0 and include_back_row:
                if not self._selection_connected_to_previous(pin_indices):
                    return False, "Pins must touch pins from the previous ball."
            else:
                for pin in pins:
                    if not (PIN_ADJACENCY.get(pin.index, set()) & self.pins_removed_prev_ball):
                        return False, "Pins must touch pins from the previous ball."

        if len(pins) >= 2:
            if not self._pins_form_connected_group(pin_indices):
                return False, "Pins must be adjacent."

        ball_value = card.rank % 10
        if len(pins) == 1:
            if card.rank != pins[0].card.rank:
                return False, "Single pin must match the card rank."
        else:
            total = sum(pin.card.rank for pin in pins)
            if total % 10 != ball_value:
                return False, "Combo total must share the card's ones digit."
        return True, None

    def _pins_form_connected_group(self, indices: Sequence[int]) -> bool:
        if not indices:
            return False
        visited = set()
        to_visit = [indices[0]]
        target = set(indices)
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in PIN_ADJACENCY.get(current, set()):
                if neighbor in target and neighbor not in visited:
                    to_visit.append(neighbor)
        return visited == target

    def _selection_connected_to_previous(self, indices: Sequence[int]) -> bool:
        if not indices or not self.pins_removed_prev_ball:
            return False
        selection = set(indices)
        previous = set(self.pins_removed_prev_ball)
        seeds = [idx for idx in selection if PIN_ADJACENCY.get(idx, set()) & previous]
        if not seeds:
            return False
        visited: Set[int] = set()
        stack = list(seeds)
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            for neighbor in PIN_ADJACENCY.get(current, set()):
                if neighbor in selection and neighbor not in visited:
                    stack.append(neighbor)
        return visited == selection

    def _has_available_move(self) -> bool:
        if self.game_completed:
            return False
        available_pins = [pin.index for pin in self.pins if not pin.removed]
        if not available_pins:
            return False
        for ball_index, pile in enumerate(self.ball_piles):
            card = pile.face_up
            if card is None:
                continue
            for size in (1, 2, 3):
                for combo in combinations(available_pins, size):
                    valid, _ = self._validate_selection_for_card(ball_index, card, combo)
                    if valid:
                        return True
        return False

    # -------------------------------------------------------------- ball logic

    def _end_ball(
        self,
        *,
        after_strike: bool = False,
        discarded: bool = False,
        no_moves: bool = False,
        manual: bool = False,
    ) -> None:
        if self.game_completed:
            return
        pins_removed = set(self.pins_removed_this_ball)
        knocked = len(pins_removed)
        self.pins_removed_this_ball.clear()

        self.frame_rolls[self.current_frame].append(knocked)
        self.roll_history.append(knocked)
        self._update_score_symbols(self.current_frame, self.current_ball, knocked)
        self._recompute_totals()

        if manual:
            if knocked == 0:
                self.status_message = "Ball advanced – no pins knocked down."
            else:
                self.status_message = (
                    "Ball complete – 1 pin knocked down."
                    if knocked == 1
                    else f"Ball complete – {knocked} pins knocked down."
                )
        elif after_strike and self.current_frame < 9 and self.current_ball == 0:
            self.status_message = "Strike!"
        elif after_strike and self.current_frame == 9:
            self.status_message = "Strike!"
        elif discarded:
            self.status_message = "Ball ended by discard."
        elif no_moves:
            self.status_message = "No moves available – ball over."
        elif knocked == 0:
            self.status_message = "No pins knocked down."

        self._advance_ball_cards()

        frame_done = False
        next_ball = self.current_ball + 1
        if self.current_frame < 9:
            if self.current_ball == 0 and knocked == 10:
                frame_done = True
            elif self.current_ball >= 1:
                frame_done = True
        else:
            rolls = self.frame_rolls[self.current_frame]
            if self.current_ball == 0:
                frame_done = False
                next_ball = 1
                if knocked == 10:
                    self._reset_pins_for_bonus()
                    pins_removed = set()
            elif self.current_ball == 1:
                first = rolls[0]
                if first == 10:
                    next_ball = 2
                    if knocked == 10:
                        self._reset_pins_for_bonus()
                        pins_removed = set()
                elif first + rolls[1] == 10:
                    next_ball = 2
                    self._reset_pins_for_bonus()
                    pins_removed = set()
                else:
                    frame_done = True
            else:
                frame_done = True

        if frame_done:
            self.current_frame += 1
            if self.current_frame >= 10:
                self.game_completed = True
                self.status_message = "Game complete!"
                self.selected_ball_index = None
                self.selected_pins.clear()
                self.pins_removed_prev_ball = set()
                return
            self.current_ball = 0
            self.ball_actions = 0
            self.pins_removed_prev_ball = set()
            self._deal_new_frame()
            self.status_message = f"Frame {self.current_frame + 1} – select a ball card."
            return

        self.current_ball = next_ball
        self.ball_actions = 0
        if self.current_frame < 9:
            if self.pins_remaining() > 0:
                self.pins_removed_prev_ball = pins_removed
            else:
                self.pins_removed_prev_ball = set()
        else:
            if self.pins_remaining() > 0:
                self.pins_removed_prev_ball = pins_removed
            else:
                self.pins_removed_prev_ball = set()
        self.selected_ball_index = None
        self.selected_pins.clear()

    def _advance_ball_cards(self) -> None:
        for pile in self.ball_piles:
            card = pile.discard_face_up()
            if card is not None:
                self.ball_waste.append(card)

    def _reset_pins_for_bonus(self) -> None:
        for pin in self.pins:
            pin.removed = False
        self.selected_pins.clear()
        self.pins_removed_prev_ball = set()

    # --------------------------------------------------------------- scoring UI

    def _update_score_symbols(self, frame_index: int, ball_index: int, knocked: int) -> None:
        frame = self.score_frames[frame_index]
        if frame_index < 9:
            if ball_index == 0:
                frame.symbols[0] = "X" if knocked == 10 else (str(knocked) if knocked > 0 else "-")
                if knocked == 10:
                    frame.symbols[1] = ""
            else:
                first = self.frame_rolls[frame_index][0]
                if first + knocked == 10:
                    frame.symbols[1] = "/"
                else:
                    frame.symbols[1] = str(knocked) if knocked > 0 else "-"
        else:
            rolls = self.frame_rolls[frame_index]
            if ball_index == 0:
                frame.symbols[0] = "X" if knocked == 10 else (str(knocked) if knocked > 0 else "-")
            elif ball_index == 1:
                first = rolls[0]
                if first == 10:
                    frame.symbols[1] = "X" if knocked == 10 else (str(knocked) if knocked > 0 else "-")
                else:
                    frame.symbols[1] = "/" if first + knocked == 10 else (str(knocked) if knocked > 0 else "-")
            else:
                second = rolls[1] if len(rolls) > 1 else 0
                first = rolls[0]
                if second == 10:
                    frame.symbols[2] = "X" if knocked == 10 else (str(knocked) if knocked > 0 else "-")
                elif first == 10 and second + knocked == 10:
                    frame.symbols[2] = "/"
                else:
                    frame.symbols[2] = "X" if knocked == 10 else (str(knocked) if knocked > 0 else "-")

    def _recompute_totals(self) -> None:
        cumulative = 0
        rolls = self.roll_history
        idx = 0
        for frame_index in range(10):
            frame = self.score_frames[frame_index]
            frame.total = None
            if frame_index < 9:
                if idx >= len(rolls):
                    break
                first = rolls[idx]
                if first == 10:
                    if idx + 2 < len(rolls):
                        cumulative += 10 + rolls[idx + 1] + rolls[idx + 2]
                        frame.total = cumulative
                    idx += 1
                else:
                    if idx + 1 >= len(rolls):
                        break
                    second = rolls[idx + 1]
                    if first + second == 10:
                        if idx + 2 < len(rolls):
                            cumulative += 10 + rolls[idx + 2]
                            frame.total = cumulative
                    else:
                        cumulative += first + second
                        frame.total = cumulative
                    idx += 2
            else:
                if idx >= len(rolls):
                    break
                first = rolls[idx]
                if idx + 1 >= len(rolls):
                    break
                second = rolls[idx + 1]
                if first == 10:
                    if idx + 2 >= len(rolls):
                        break
                    third = rolls[idx + 2]
                    cumulative += 10 + second + third
                    frame.total = cumulative
                    idx += 3
                elif first + second == 10:
                    if idx + 2 >= len(rolls):
                        break
                    third = rolls[idx + 2]
                    cumulative += 10 + third
                    frame.total = cumulative
                    idx += 3
                else:
                    cumulative += first + second
                    frame.total = cumulative
                    idx += 2

    # ------------------------------------------------------------------- saving

    def save_state(self) -> Dict[str, Any]:
        return {
            "player_initials": self.player_initials,
            "current_frame": self.current_frame,
            "current_ball": self.current_ball,
            "ball_actions": self.ball_actions,
            "game_completed": self.game_completed,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
            "pins": [pin.to_dict() for pin in self.pins],
            "ball_piles": [pile.to_dict() for pile in self.ball_piles],
            "ball_waste": [_card_to_dict(card) for card in self.ball_waste],
            "frame_rolls": [list(rolls) for rolls in self.frame_rolls],
            "score_frames": [frame.to_dict() for frame in self.score_frames],
            "roll_history": list(self.roll_history),
            "pins_removed_prev_ball": list(self.pins_removed_prev_ball),
            "selected_ball": self.selected_ball_index,
            "selected_pins": list(self.selected_pins),
            "status_message": self.status_message,
        }

    def save_and_exit(self) -> None:
        payload = self.save_state()
        payload["completed"] = self.game_completed
        _safe_write(_save_path(), payload)
        self.ui_helper.goto_menu()

    def _load_from_state(self, state: Mapping[str, Any]) -> bool:
        try:
            initials_val = state.get("player_initials", "")
            if isinstance(initials_val, str):
                initials = initials_val.strip().upper()[:3]
            else:
                initials = ""
            self.player_initials = initials or "PLY"
            self._pending_initials = self.player_initials
            self._initials_prompt_visible = False
            self._initials_input_active = False
            self.current_frame = int(state.get("current_frame", 0))
            self.current_ball = int(state.get("current_ball", 0))
            self.ball_actions = int(state.get("ball_actions", 0))
            self.game_completed = bool(state.get("game_completed", False))
            self.roll_history = [int(x) for x in state.get("roll_history", [])]
            frame_rolls = state.get("frame_rolls", [])
            self.frame_rolls = [
                [int(val) for val in rolls] if isinstance(rolls, Iterable) else []
                for rolls in frame_rolls
            ]
            while len(self.frame_rolls) < 10:
                self.frame_rolls.append([])
            score_frames = state.get("score_frames", [])
            self.score_frames = []
            for i in range(9):
                entry = score_frames[i] if i < len(score_frames) else {}
                self.score_frames.append(FrameScore.from_dict(entry, 2))
            entry = score_frames[9] if len(score_frames) > 9 else {}
            self.score_frames.append(FrameScore.from_dict(entry, 3))
            pin_entries = state.get("pins", [])
            pins: List[Pin] = []
            for idx, entry in enumerate(pin_entries):
                rect = self.pin_slots[idx] if idx < len(self.pin_slots) else pygame.Rect(0, 0, C.CARD_W, C.CARD_H)
                if isinstance(entry, Mapping):
                    pins.append(Pin.from_dict(entry, rect))
            while len(pins) < len(self.pin_slots):
                slot = self.pin_slots[len(pins)]
                pins.append(Pin(len(pins), C.Card(0, 1, True), 0, 0, slot.copy(), removed=True))
            self.pins = pins
            pile_entries = state.get("ball_piles", [])
            piles = []
            for entry in pile_entries:
                if isinstance(entry, Mapping):
                    piles.append(BallPile.from_dict(entry))
            while len(piles) < 3:
                piles.append(BallPile([]))
            self.ball_piles = piles
            waste_entries = state.get("ball_waste", [])
            self.ball_waste = [_card_from_dict(entry) for entry in waste_entries if isinstance(entry, Mapping)]
            self.pins_removed_prev_ball = set(int(x) for x in state.get("pins_removed_prev_ball", []))
            self.selected_ball_index = state.get("selected_ball")
            if self.selected_ball_index is not None:
                self.selected_ball_index = int(self.selected_ball_index)
            self.selected_pins = [int(x) for x in state.get("selected_pins", [])]
            self.status_message = str(state.get("status_message", ""))
            sx = state.get("scroll_x", 0)
            sy = state.get("scroll_y", 0)
            try:
                self.scroll_x = int(sx)
            except Exception:
                self.scroll_x = 0
            try:
                self.scroll_y = int(sy)
            except Exception:
                self.scroll_y = 0
            self._clamp_scroll()
            self._recompute_totals()
            return True
        except Exception:
            return False

    # ----------------------------------------------------------------- drawing

    @contextmanager
    def _ball_action_button_offset(self) -> Iterator[None]:
        sx = self.scroll_x
        sy = self.scroll_y
        originals: List[Tuple[int, int]] = []
        for btn in self.ball_action_buttons:
            originals.append(btn.rect.topleft)
            btn.rect.move_ip(sx, sy)
        try:
            yield
        finally:
            for btn, pos in zip(self.ball_action_buttons, originals):
                btn.rect.topleft = pos

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(C.TABLE_BG)
        if self.toolbar:
            self.toolbar.draw(screen)
        with self._ball_action_button_offset():
            for btn in self.ball_action_buttons:
                btn.draw(screen)
        if self.help.visible:
            self.help.draw(screen)
            return
        self._draw_scoreboard(screen)
        self._draw_pins(screen)
        self._draw_ball_piles(screen)
        self._draw_scrollbars(screen)
        self._draw_status(screen)
        if self._initials_prompt_visible:
            self._draw_initials_prompt(screen)

    def _draw_scoreboard(self, screen: pygame.Surface) -> None:
        sx = self.scroll_x
        sy = self.scroll_y
        scoreboard_rect = self.scoreboard_rect.move(sx, sy)
        pygame.draw.rect(screen, (248, 248, 248), scoreboard_rect, border_radius=18)
        pygame.draw.rect(screen, (0, 0, 0), scoreboard_rect, width=2, border_radius=18)
        header_font = C.FONT_UI
        row_font = C.FONT_RANK
        player_header_rect = self.player_header_rect.move(sx, sy)
        pygame.draw.rect(screen, (245, 245, 245), player_header_rect)
        pygame.draw.rect(screen, (150, 150, 155), player_header_rect, width=1)
        player_title = header_font.render("Player", True, (30, 30, 40))
        screen.blit(
            player_title,
            (
                player_header_rect.centerx - player_title.get_width() // 2,
                player_header_rect.centery - player_title.get_height() // 2,
            ),
        )
        for idx, cell in enumerate(self.score_cells):
            header_rect = cell["header_rect"].move(sx, sy)
            title = header_font.render(str(idx + 1), True, (30, 30, 40))
            screen.blit(
                title,
                (header_rect.centerx - title.get_width() // 2, header_rect.centery - title.get_height() // 2),
            )
            frame_rect = cell["frame_rect"].move(sx, sy)
            pygame.draw.rect(screen, (210, 210, 215), frame_rect, width=1)
            for i, box in enumerate(cell["ball_boxes"]):
                adj_box = box.move(sx, sy)
                pygame.draw.rect(screen, (245, 245, 245), adj_box)
                pygame.draw.rect(screen, (150, 150, 155), adj_box, width=1)
                sym = self.score_frames[idx].symbols[i] if i < len(self.score_frames[idx].symbols) else ""
                if sym:
                    text = row_font.render(sym, True, (30, 30, 35))
                    screen.blit(
                        text,
                        (
                            adj_box.centerx - text.get_width() // 2,
                            adj_box.centery - text.get_height() // 2,
                        ),
                    )
            score_rect = cell["score_rect"].move(sx, sy)
            total = self.score_frames[idx].total
            if total is not None:
                score_text = header_font.render(str(total), True, (10, 70, 10))
                screen.blit(
                    score_text,
                    (
                        score_rect.centerx - score_text.get_width() // 2,
                        score_rect.centery - score_text.get_height() // 2,
                    ),
                )
        player_rect = self.player_rect.move(sx, sy)
        pygame.draw.rect(screen, (255, 255, 255), player_rect)
        pygame.draw.rect(screen, (150, 150, 155), player_rect, width=1)
        initials = self.player_initials or ""
        initials_text = header_font.render(initials, True, (30, 30, 35))
        screen.blit(
            initials_text,
            (
                player_rect.centerx - initials_text.get_width() // 2,
                player_rect.centery - initials_text.get_height() // 2,
            ),
        )

    def _draw_pins(self, screen: pygame.Surface) -> None:
        sx = self.scroll_x
        sy = self.scroll_y
        for pin in self.pins:
            rect = pin.rect.move(sx, sy)
            if pin.removed:
                pygame.draw.rect(screen, (70, 70, 70), rect, width=1, border_radius=8)
                continue
            surf = C.get_card_surface(pin.card)
            screen.blit(surf, (rect.left, rect.top))
            if pin.index in self.selected_pins:
                pygame.draw.rect(screen, (255, 200, 60), rect, width=4, border_radius=10)

    def _draw_ball_piles(self, screen: pygame.Surface) -> None:
        sx = self.scroll_x
        sy = self.scroll_y
        for idx, pile in enumerate(self.ball_piles):
            face_rect = self.ball_face_rects[idx].move(sx, sy)
            stack_rect = self.ball_stack_rects[idx].move(sx, sy)
            if pile.remaining_hidden() > 0:
                pygame.draw.rect(screen, (80, 80, 90), stack_rect)
                count_text = C.FONT_SMALL.render(str(pile.remaining_hidden()), True, (230, 230, 235))
                screen.blit(
                    count_text,
                    (stack_rect.centerx - count_text.get_width() // 2, stack_rect.centery - count_text.get_height() // 2),
                )
            card = pile.face_up
            if card is not None:
                surf = C.get_card_surface(card)
                screen.blit(surf, (face_rect.left, face_rect.top))
            else:
                pygame.draw.rect(screen, (100, 100, 110), face_rect, width=2, border_radius=10)
            if self.selected_ball_index == idx:
                pygame.draw.rect(screen, (255, 220, 90), face_rect, width=4, border_radius=12)

        if self.ball_waste:
            waste_card = self.ball_waste[-1]
            surf = C.get_card_surface(waste_card)
            waste_rect = self.waste_rect.move(sx, sy)
            screen.blit(surf, (waste_rect.left, waste_rect.top))
        else:
            waste_rect = self.waste_rect.move(sx, sy)
            pygame.draw.rect(screen, (160, 160, 165), waste_rect, width=2, border_radius=10)

    def _draw_scrollbars(self, screen: pygame.Surface) -> None:
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (45, 45, 50), track_rect, border_radius=3)
            pygame.draw.rect(screen, (205, 205, 215), knob_rect, border_radius=3)
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (45, 45, 50), track_rect, border_radius=3)
            pygame.draw.rect(screen, (205, 205, 215), knob_rect, border_radius=3)

    def _draw_status(self, screen: pygame.Surface) -> None:
        text = C.FONT_UI.render(self.status_message, True, C.WHITE)
        screen.blit(text, (40, C.SCREEN_H - 60))

    def _draw_initials_prompt(self, screen: pygame.Surface) -> None:
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))

        panel_rect = self._initials_panel_rect
        pygame.draw.rect(screen, (245, 245, 250), panel_rect, border_radius=16)
        pygame.draw.rect(screen, (110, 110, 125), panel_rect, width=2, border_radius=16)

        title = C.FONT_TITLE.render("Enter Player Initials", True, (30, 30, 40))
        screen.blit(
            title,
            (panel_rect.centerx - title.get_width() // 2, panel_rect.top + 28),
        )
        subtitle = C.FONT_UI.render("Use 1-3 letters or numbers.", True, (60, 60, 70))
        screen.blit(
            subtitle,
            (panel_rect.centerx - subtitle.get_width() // 2, panel_rect.top + 74),
        )

        input_rect = self._initials_input_rect
        pygame.draw.rect(screen, (255, 255, 255), input_rect, border_radius=12)
        border_color = (255, 220, 120) if self._initials_input_active else (175, 175, 185)
        pygame.draw.rect(screen, border_color, input_rect, width=3, border_radius=12)

        display = self._pending_initials or "_"
        text = C.FONT_TITLE.render(display, True, (30, 30, 35))
        screen.blit(
            text,
            (input_rect.centerx - text.get_width() // 2, input_rect.centery - text.get_height() // 2),
        )

        hint = C.FONT_SMALL.render("Press Enter or click Confirm when ready.", True, (90, 90, 100))
        screen.blit(
            hint,
            (panel_rect.centerx - hint.get_width() // 2, input_rect.bottom + 8),
        )

        self._initials_accept_button.draw(screen)

    def _handle_initials_event(self, event: pygame.event.Event) -> None:
        self._initials_accept_button.handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._initials_input_rect.collidepoint(event.pos):
                self._initials_input_active = True
            else:
                self._initials_input_active = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self._pending_initials = self._pending_initials[:-1]
            elif event.key == pygame.K_RETURN:
                if self._pending_initials:
                    self._commit_initials()
            else:
                char = event.unicode.upper()
                if char.isalnum() and len(self._pending_initials) < 3:
                    self._pending_initials += char

    def _commit_initials(self) -> None:
        initials = (self._pending_initials or "").strip().upper()
        if not initials:
            return
        self.player_initials = initials[:3]
        self._pending_initials = self.player_initials
        self._initials_prompt_visible = False
        self._initials_input_active = False

    # ---------------------------------------------------------------- events

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._initials_prompt_visible:
            self._handle_initials_event(event)
            return
        if self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
                return
        if self.toolbar and self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return
        if self._handle_scroll_event(event):
            return
        with self._ball_action_button_offset():
            for btn in self.ball_action_buttons:
                if btn.handle_event(event):
                    return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            offset_x = self.scroll_x
            offset_y = self.scroll_y
            for idx, rect in enumerate(self.ball_face_rects):
                if rect.move(offset_x, offset_y).collidepoint(pos):
                    self._handle_ball_click(idx)
                    return
            for pin in self.pins:
                if not pin.removed and pin.rect.move(offset_x, offset_y).collidepoint(pos):
                    self._handle_pin_click(pin.index)
                    return
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.apply_selection()
            elif event.key == pygame.K_BACKSPACE:
                self.clear_selection()
            elif event.key == pygame.K_n:
                self.advance_to_next_ball()

    def _handle_scroll_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y += event.y * 60
            try:
                self.scroll_x += event.x * 60
            except Exception:
                pass
            self._clamp_scroll()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(event.pos):
                    self._drag_vscroll = True
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    self._vscroll_drag_offset = event.pos[1] - knob_rect.y
                    return True
                if track_rect.collidepoint(event.pos):
                    y = min(max(event.pos[1] - knob_h // 2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                    self._clamp_scroll()
                    return True
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                if knob_rect.collidepoint(event.pos):
                    self._drag_hscroll = True
                    self._hscroll_geom = (min_sx, max_sx, track_x, track_w, knob_w)
                    self._hscroll_drag_offset = event.pos[0] - knob_rect.x
                    return True
                if track_rect.collidepoint(event.pos):
                    x = min(max(event.pos[0] - knob_w // 2, track_x), track_x + track_w - knob_w)
                    t_knob = (x - track_x) / max(1, (track_w - knob_w))
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll()
                    return True
        if event.type == pygame.MOUSEMOTION and self._drag_vscroll and self._vscroll_geom is not None:
            min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
            y = min(max(event.pos[1] - self._vscroll_drag_offset, track_y), track_y + track_h - knob_h)
            t_knob = (y - track_y) / max(1, (track_h - knob_h))
            self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
            self._clamp_scroll()
            return True
        if event.type == pygame.MOUSEMOTION and self._drag_hscroll and self._hscroll_geom is not None:
            min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
            x = min(max(event.pos[0] - self._hscroll_drag_offset, track_x), track_x + track_w - knob_w)
            t_knob = (x - track_x) / max(1, (track_w - knob_w))
            self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
            self._clamp_scroll()
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._drag_vscroll or self._drag_hscroll:
                self._drag_vscroll = False
                self._drag_hscroll = False
                self._vscroll_geom = None
                self._hscroll_geom = None
                return True
        return False

    def _handle_ball_click(self, index: int) -> None:
        if self.game_completed:
            return
        pile = self.ball_piles[index]
        if pile.face_up is None:
            self.status_message = "That ball has no remaining cards."
            return
        if self.selected_ball_index == index and self.selected_pins:
            self.apply_selection()
            return
        if self.selected_ball_index == index:
            self.selected_ball_index = None
            self.status_message = "Ball deselected."
            return
        self.selected_ball_index = index
        self.selected_pins.clear()
        self.status_message = "Ball selected – choose pins, then press Bowl."

    def _handle_pin_click(self, index: int) -> None:
        if self.selected_ball_index is None:
            self.status_message = "Select a ball card first."
            return
        if index in self.selected_pins:
            self.selected_pins.remove(index)
            self.status_message = "Pin deselected."
        else:
            if len(self.selected_pins) >= 3:
                self.status_message = "Maximum of three pins per ball."
                return
            self.selected_pins.append(index)
            self.status_message = "Pin selected – press Bowl to knock it down."

