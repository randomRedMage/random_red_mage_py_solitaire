"""British Square solitaire implementation."""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.ui import Button


_SAVE_FILENAME = "british_square_save.json"


def _bs_dir() -> str:
    return C.project_saves_dir("british_square")


def _bs_save_path() -> str:
    return os.path.join(_bs_dir(), _SAVE_FILENAME)


def _safe_write_json(path: str, data: Any) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _clear_saved_game() -> None:
    try:
        if os.path.isfile(_bs_save_path()):
            os.remove(_bs_save_path())
    except Exception:
        pass


def has_saved_game() -> bool:
    state = _safe_read_json(_bs_save_path())
    if not isinstance(state, dict):
        return False
    if state.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    state = _safe_read_json(_bs_save_path())
    if not isinstance(state, dict):
        return None
    if state.get("completed"):
        return None
    return state


_FOUNDATION_SEQUENCE: Tuple[int, ...] = tuple(list(range(1, 14)) + [13] + list(range(12, 0, -1)))


@dataclass
class _DragState:
    cards: List[C.Card]
    src_kind: str
    src_index: int
    offset: Tuple[int, int]


class BritishSquareGameScene(C.Scene):
    """Game scene for British Square."""

    def __init__(self, app, load_state: Optional[Dict[str, Any]] = None):
        super().__init__(app)

        # Core piles
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
        self.foundation_progress: List[int] = [0, 0, 0, 0]
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=0) for _ in range(16)]
        self.tableau_dirs: List[int] = [0 for _ in range(16)]  # 0 = not set, 1 = building up, -1 = down
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.waste_pile: C.Pile = C.Pile(0, 0)

        # Interaction helpers
        self.undo_mgr = C.UndoManager()
        self.animator = M.CardAnimator()
        self.drag_state: Optional[_DragState] = None
        self.message: str = ""
        self.completed: bool = False
        self._game_over: bool = False

        # Scrolling and peeking
        self.scroll_x = 0
        self.scroll_y = 0
        self.drag_pan = M.DragPanController()
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom: Optional[Tuple[int, int, int, int, int]] = None
        self._hscroll_geom: Optional[Tuple[int, int, int, int, int]] = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self.peek = M.PeekController(delay_ms=1200)
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 60))

        # Hint + Auto-complete state
        self.hint_targets: Optional[List[Tuple[str, int]]] = None
        self.hint_expires_at: int = 0
        self.auto_active = False
        self.auto_last_time = 0
        self.auto_interval_ms = 200
        self._stock_hint_active = False

        # End-of-game modal state
        self._result_modal: Optional[Dict[str, Any]] = None
        self._refill_button: Optional[Button] = None

        # UI helper / toolbar
        self.ui_helper = ModeUIHelper(self, game_id="british_square")

        font_path = os.path.join(
            os.path.dirname(__file__), "..", "assets", "fonts", "DejaVuSans.ttf"
        )
        font_path = os.path.abspath(font_path)
        try:
            self.tableau_info_font = pygame.font.Font(font_path, 22)
        except Exception:
            self.tableau_info_font = pygame.font.SysFont("DejaVu Sans", 22, bold=True)
        self._tableau_arrow_glyphs = {
            1: self.tableau_info_font.render("\u2B06", True, (255, 255, 255)),
            -1: self.tableau_info_font.render("\u2B07", True, (255, 255, 255)),
        }

        def can_undo() -> bool:
            return self.undo_mgr.can_undo()

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            hint_action={"on_click": self.show_hint, "enabled": lambda: not self.auto_active},
            save_action=(
                "Save&Exit",
                {
                    "on_click": lambda: self._save_game(to_menu=True),
                    "tooltip": "Save game and return to menu",
                },
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            extra_actions=[
                (
                    "Refill",
                    {
                        "on_click": self._on_click_refill,
                        "tooltip": "Draw from stock",
                    },
                )
            ],
            toolbar_kwargs={"primary_labels": ("Refill", "Undo", "Hint")},
        )
        self._refill_button = self.toolbar.get_button("Refill")

        # Help modal (raises if entry missing – ensures help text provided)
        self.help = create_modal_help("british_square")

        # Layout / setup
        self.compute_layout()
        if load_state:
            self._load_from_state(load_state)
            self.undo_mgr = C.UndoManager()
            self.push_undo()  # baseline undo for loaded state
        else:
            self.deal_new()

        self._initial_snapshot = self.record_snapshot()
        self._last_click_time = 0
        self._last_click_pos = (0, 0)

    # ------------------------------------------------------------------
    # Layout & scrolling helpers
    # ------------------------------------------------------------------
    def compute_layout(self) -> None:
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))

        top_bar = getattr(C, "TOP_BAR_H", 60)
        top_y = top_bar + C.CARD_H // 2

        cols = 4
        rows = 4
        tableau_width = cols * C.CARD_W + (cols - 1) * gap_x
        left = (C.SCREEN_W - tableau_width) // 2

        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                pile = self.tableau[idx]
                pile.x = left + c * (C.CARD_W + gap_x)
                pile.y = top_y + r * (C.CARD_H + gap_y)
                pile.fan_y = 0

        # Foundations column to the right with full card width gap
        rightmost = left + (cols - 1) * (C.CARD_W + gap_x)
        foundation_gap_x = max(gap_x, C.CARD_W // 2)
        foundation_cols = 2
        foundation_rows = max(1, (len(self.foundations) + foundation_cols - 1) // foundation_cols)
        foundation_start_x = rightmost + C.CARD_W + foundation_gap_x
        for i, pile in enumerate(self.foundations):
            col = i // foundation_rows
            row = i % foundation_rows
            pile.x = foundation_start_x + col * (C.CARD_W + foundation_gap_x)
            pile.y = stock_y + row * (C.CARD_H + gap_y)

        # Stock / waste to the left of tableau for balance
        stock_gap = max(gap_x * 2, int(C.CARD_W * 0.8))
        stock_x = left - stock_gap - C.CARD_W
        stock_y = top_y
        self.stock_pile.x, self.stock_pile.y = stock_x, stock_y
        self.waste_pile.x = stock_x
        self.waste_pile.y = stock_y + C.CARD_H + gap_y

        self._clamp_scroll_xy()

    def _pile_bounds(self, pile: C.Pile, max_len: Optional[int] = None) -> Tuple[int, int, int, int]:
        count = len(pile.cards)
        if max_len is not None:
            count = max(count, max_len)
        if count <= 0:
            count = 1
        xs: List[int] = []
        ys: List[int] = []
        for idx in range(count):
            r = pile.rect_for_index(idx)
            xs.extend([r.x, r.x + C.CARD_W])
            ys.extend([r.y, r.y + C.CARD_H])
        return min(xs), max(xs), min(ys), max(ys)

    def _content_bounds(self) -> Tuple[int, int, int, int]:
        piles = [self.stock_pile, self.waste_pile] + self.tableau
        bounds = [self._pile_bounds(p) for p in piles]
        lefts, rights, tops, bottoms = zip(*bounds)
        pad = 18
        return min(lefts) - pad, max(rights) + pad, min(tops) - pad, max(bottoms) + pad

    def _scroll_limits(self) -> Tuple[int, int, int, int]:
        left, right, top, bottom = self._content_bounds()
        margin = 20
        top_bar = getattr(C, "TOP_BAR_H", 60)
        max_sx = margin - left
        min_sx = min(0, C.SCREEN_W - right - margin)
        max_sy = top_bar + margin - top
        min_sy = min(0, C.SCREEN_H - bottom - margin)
        return min_sx, max_sx, min_sy, max_sy

    def _clamp_scroll_xy(self) -> None:
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sx < min_sx:
            max_sx = min_sx
        if max_sy < min_sy:
            max_sy = min_sy
        self.scroll_x = max(min(self.scroll_x, max_sx), min_sx)
        self.scroll_y = max(min(self.scroll_y, max_sy), min_sy)

    def _scroll_offset_for_kind(self, kind: str) -> Tuple[int, int]:
        if kind in {"stock", "waste", "tableau"}:
            return self.scroll_x, self.scroll_y
        return 0, 0

    def _vertical_scrollbar(self):
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
        thumb_h = max(30, int(view_h * (view_h / content_h)))
        rel = 0 if max_sy == min_sy else (self.scroll_y - min_sy) / float(max_sy - min_sy)
        thumb_y = track_y + int((view_h - thumb_h) * rel)
        return track_x, track_y, track_h, thumb_y, thumb_h

    def _horizontal_scrollbar(self):
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sx <= min_sx:
            return None
        track_y = C.SCREEN_H - 12
        track_x = 10
        track_w = C.SCREEN_W - 20
        if track_w <= 0:
            return None
        view_w = track_w
        content_w = view_w + (max_sx - min_sx)
        thumb_w = max(30, int(view_w * (view_w / content_w)))
        rel = 0 if max_sx == min_sx else (self.scroll_x - min_sx) / float(max_sx - min_sx)
        thumb_x = track_x + int((view_w - thumb_w) * rel)
        return track_x, track_y, track_w, thumb_x, thumb_w

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def record_snapshot(self) -> Dict[str, Any]:
        def cap_pile(p: C.Pile) -> List[Tuple[int, int, bool]]:
            return [(c.suit, c.rank, c.face_up) for c in p.cards]

        return {
            "foundations": [cap_pile(p) for p in self.foundations],
            "progress": list(self.foundation_progress),
            "tableau": [cap_pile(p) for p in self.tableau],
            "dirs": list(self.tableau_dirs),
            "stock": cap_pile(self.stock_pile),
            "waste": cap_pile(self.waste_pile),
            "message": self.message,
            "completed": self.completed,
            "game_over": self._game_over,
            "scroll_x": self.scroll_x,
            "scroll_y": self.scroll_y,
        }

    def restore_snapshot(self, snap: Dict[str, Any]) -> None:
        def mk(seq: Iterable[Sequence[Any]]) -> List[C.Card]:
            result: List[C.Card] = []
            for suit, rank, face_up in seq:
                card = C.Card(suit, rank, face_up)
                result.append(card)
            return result

        for i, pile in enumerate(self.foundations):
            pile.cards = mk(snap.get("foundations", [])[i]) if i < len(snap.get("foundations", [])) else []
        self.foundation_progress = list(snap.get("progress", [0, 0, 0, 0]))[:4]
        if len(self.foundation_progress) < 4:
            self.foundation_progress += [0] * (4 - len(self.foundation_progress))
        for i, pile in enumerate(self.tableau):
            pile.cards = mk(snap.get("tableau", [])[i]) if i < len(snap.get("tableau", [])) else []
        self.tableau_dirs = list(snap.get("dirs", [0] * 16))[:16]
        if len(self.tableau_dirs) < 16:
            self.tableau_dirs += [0] * (16 - len(self.tableau_dirs))
        self.stock_pile.cards = mk(snap.get("stock", []))
        self.waste_pile.cards = mk(snap.get("waste", []))
        self.message = snap.get("message", "")
        self.completed = bool(snap.get("completed", False))
        self._game_over = bool(snap.get("game_over", False))
        self.scroll_x = int(snap.get("scroll_x", 0))
        self.scroll_y = int(snap.get("scroll_y", 0))
        self._clamp_scroll_xy()
        self._result_modal = None

    def push_undo(self) -> None:
        snap = self.record_snapshot()

        def _undo(snapshot=snap):
            self.restore_snapshot(snapshot)

        self.undo_mgr.push(_undo)

    def undo(self) -> None:
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.peek.cancel()
            self._clear_hint_targets()
            self.auto_active = False
            self._game_over = False
            self._result_modal = None

    def restart(self) -> None:
        if hasattr(self, "_initial_snapshot") and self._initial_snapshot:
            self.restore_snapshot(self._initial_snapshot)
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self.completed = False
            self._game_over = False
            self.auto_active = False
            self._result_modal = None
            self._clear_hint_targets()

    def _save_game(self, *, to_menu: bool = False) -> None:
        state = self.record_snapshot()
        state["completed"] = self.completed
        try:
            _safe_write_json(_bs_save_path(), state)
        finally:
            if to_menu:
                self.ui_helper.goto_main_menu()

    def _load_from_state(self, state: Dict[str, Any]) -> None:
        self.restore_snapshot(state)
        self._clear_hint_targets()

    # ------------------------------------------------------------------
    # Dealing & stock logic
    # ------------------------------------------------------------------
    def deal_new(self) -> None:
        self._clear_hint_targets()
        deck: List[C.Card] = []
        for _ in range(2):
            for suit in range(4):
                for rank in range(1, 14):
                    deck.append(C.Card(suit, rank, face_up=False))
        random.shuffle(deck)

        for pile in self.tableau:
            pile.cards.clear()
        for pile in self.foundations:
            pile.cards.clear()
        self.stock_pile.cards.clear()
        self.waste_pile.cards.clear()
        self.foundation_progress = [0, 0, 0, 0]
        self.tableau_dirs = [0] * 16
        self.completed = False
        self._game_over = False
        self.message = ""
        self.auto_active = False
        self._result_modal = None

        cols = 4
        rows = 4
        for r in range(rows):
            for c in range(cols):
                idx = r * cols + c
                card = deck.pop()
                card.face_up = True
                self.tableau[idx].cards.append(card)

        for card in deck:
            card.face_up = False
        self.stock_pile.cards = deck
        self.waste_pile.cards = []

        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()
        _clear_saved_game()

    def _draw_from_stock(self) -> bool:
        if not self.stock_pile.cards:
            return False
        card = self.stock_pile.cards.pop()
        card.face_up = True
        self.waste_pile.cards.append(card)
        return True

    # ------------------------------------------------------------------
    # Game rule helpers
    # ------------------------------------------------------------------
    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _can_place_on_foundation(self, card: C.Card, fi: int) -> bool:
        if card.suit != self.foundation_suits[fi]:
            return False
        progress = self.foundation_progress[fi]
        if progress >= len(_FOUNDATION_SEQUENCE):
            return False
        expected_rank = _FOUNDATION_SEQUENCE[progress]
        return card.rank == expected_rank

    def _advance_foundation(self, card: C.Card, fi: int) -> None:
        self.foundations[fi].cards.append(card)
        self.foundation_progress[fi] += 1
        if self.foundation_progress[fi] >= len(_FOUNDATION_SEQUENCE):
            self.foundation_progress[fi] = len(_FOUNDATION_SEQUENCE)

    def _reset_tableau_dir(self, idx: int) -> None:
        if not self.tableau[idx].cards:
            self.tableau_dirs[idx] = 0

    def _set_tableau_dir(self, idx: int, moving: C.Card, target: C.Card) -> bool:
        direction = 1 if moving.rank == target.rank + 1 else -1 if moving.rank == target.rank - 1 else 0
        if direction == 0:
            return False
        current = self.tableau_dirs[idx]
        if current == 0:
            self.tableau_dirs[idx] = direction
            return True
        return current == direction

    def _can_place_on_tableau(self, card: C.Card, idx: int) -> bool:
        pile = self.tableau[idx]
        if not pile.cards:
            return False
        top = pile.cards[-1]
        if top.suit != card.suit:
            return False
        direction = self.tableau_dirs[idx]
        if direction == 0:
            return abs(card.rank - top.rank) == 1
        if direction > 0:
            return card.rank == top.rank + 1
        return card.rank == top.rank - 1

    def _fill_empty_piles(self) -> None:
        if self.animator.active:
            return
        for idx, pile in enumerate(self.tableau):
            if pile.cards:
                continue
            source_pile: Optional[C.Pile] = None
            if self.waste_pile.cards:
                source_pile = self.waste_pile
            elif self.stock_pile.cards:
                source_pile = self.stock_pile
            if source_pile is None or not source_pile.cards:
                continue

            src_index = len(source_pile.cards) - 1
            if src_index >= 0:
                src_rect = source_pile.rect_for_index(src_index)
            else:
                src_rect = pygame.Rect(source_pile.x, source_pile.y, C.CARD_W, C.CARD_H)
            card = source_pile.cards.pop()
            card.face_up = True

            dest_rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)

            def _on_complete(card_ref: C.Card = card, dest_idx: int = idx) -> None:
                self.tableau[dest_idx].cards.append(card_ref)
                self.tableau_dirs[dest_idx] = 0
                self._fill_empty_piles()

            self.animator.start_move(
                card,
                (src_rect.x, src_rect.y),
                (dest_rect.x, dest_rect.y),
                dur_ms=260,
                on_complete=_on_complete,
            )
            return

    def _try_move_to_foundation(self, src_kind: str, src_index: int) -> bool:
        if self.animator.active:
            return False
        if src_kind == "tableau":
            pile = self.tableau[src_index]
            if not pile.cards:
                return False
            card = pile.cards[-1]
            from_rect = pile.rect_for_index(len(pile.cards) - 1)
        elif src_kind == "waste":
            if not self.waste_pile.cards:
                return False
            card = self.waste_pile.cards[-1]
            from_rect = self.waste_pile.rect_for_index(len(self.waste_pile.cards) - 1)
        else:
            return False
        fi = self._foundation_index_for_suit(card.suit)
        if not self._can_place_on_foundation(card, fi):
            return False

        self.push_undo()
        if src_kind == "tableau":
            pile.cards.pop()
            self._reset_tableau_dir(src_index)
        else:
            self.waste_pile.cards.pop()
        card.face_up = True

        dest_pile = self.foundations[fi]
        dest_rect = dest_pile.rect_for_index(len(dest_pile.cards)) if dest_pile.cards else pygame.Rect(dest_pile.x, dest_pile.y, C.CARD_W, C.CARD_H)

        def _on_complete(card_ref: C.Card = card, foundation_index: int = fi) -> None:
            self._advance_foundation(card_ref, foundation_index)
            self._fill_empty_piles()
            self._check_for_completion()
            self._check_for_loss()

        self.animator.start_move(
            card,
            (from_rect.x, from_rect.y),
            (dest_rect.x, dest_rect.y),
            dur_ms=260,
            on_complete=_on_complete,
            to_use_scroll=False,
        )
        return True

    def _check_for_completion(self) -> None:
        if all(progress == len(_FOUNDATION_SEQUENCE) for progress in self.foundation_progress):
            self.completed = True
            self._game_over = True
            self.message = "You won!"
            self._open_result_modal(win=True)

    def _check_for_loss(self) -> None:
        if self.completed:
            return
        if self.stock_pile.cards or self.waste_pile.cards:
            return
        if any(p.cards for p in self.tableau):
            for idx, pile in enumerate(self.tableau):
                if not pile.cards:
                    continue
                card = pile.cards[-1]
                if self._can_place_on_foundation(card, self._foundation_index_for_suit(card.suit)):
                    return
                for other_idx, other in enumerate(self.tableau):
                    if other_idx == idx or not other.cards:
                        continue
                    top = other.cards[-1]
                    if top.suit != card.suit:
                        continue
                    direction = self.tableau_dirs[other_idx]
                    if direction == 0 and abs(card.rank - top.rank) == 1:
                        return
                    if direction > 0 and card.rank == top.rank + 1:
                        return
                    if direction < 0 and card.rank == top.rank - 1:
                        return
        self._game_over = True
        self.message = "No more moves. You lose."
        self._open_result_modal(win=False)

    def _open_result_modal(self, *, win: bool) -> None:
        if self._result_modal:
            return
        self.auto_active = False
        self._clear_hint_targets()
        self._result_modal = {
            "win": win,
            "message": "You won! Start a new game?" if win else "No more moves. Start a new game?",
            "buttons": [
                {"label": "Yes", "action": "new", "rect": None},
                {"label": "No", "action": "menu", "rect": None},
            ],
        }

    def can_autocomplete(self) -> bool:
        if self.auto_active:
            return True
        if self._result_modal:
            return False
        if self.stock_pile.cards or self.waste_pile.cards:
            return False
        return self._is_auto_win_state()

    def _is_auto_win_state(self) -> bool:
        pending_cards: Dict[int, List[int]] = {suit: [] for suit in range(4)}
        for pile in self.tableau:
            for card in pile.cards:
                pending_cards[card.suit].append(card.rank)
        for suit in range(4):
            pending_cards[suit].sort()

        progress = list(self.foundation_progress)
        remaining_sequences = []
        for suit in range(4):
            seq = list(_FOUNDATION_SEQUENCE[progress[suit]:])
            remaining_sequences.append((suit, seq))

        temp = {s: list(ranks) for s, ranks in pending_cards.items()}
        for suit, seq in remaining_sequences:
            for rank in seq:
                if not temp[suit]:
                    return False
                if rank not in temp[suit]:
                    return False
                temp[suit].remove(rank)
        return True

    def start_autocomplete(self) -> None:
        if self._result_modal or not self.can_autocomplete():
            return
        self.auto_active = True
        self.auto_last_time = 0

    def _auto_play_step(self) -> None:
        if not self.auto_active:
            return
        if self._result_modal:
            self.auto_active = False
            return
        if self.animator.active:
            return
        now = pygame.time.get_ticks()
        if now - self.auto_last_time < self.auto_interval_ms:
            return
        self.auto_last_time = now
        moved = False
        # Try tableau tops first, then waste
        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            card = pile.cards[-1]
            fi = self._foundation_index_for_suit(card.suit)
            if self._can_place_on_foundation(card, fi):
                self.push_undo()
                pile.cards.pop()
                self._reset_tableau_dir(idx)
                self._advance_foundation(card, fi)
                moved = True
                break
        if not moved and self.waste_pile.cards:
            card = self.waste_pile.cards[-1]
            fi = self._foundation_index_for_suit(card.suit)
            if self._can_place_on_foundation(card, fi):
                self.push_undo()
                self.waste_pile.cards.pop()
                self._advance_foundation(card, fi)
                moved = True
        if moved:
            self._fill_empty_piles()
            self._check_for_completion()
            if self.completed:
                self.auto_active = False
        else:
            self.auto_active = False

    # ------------------------------------------------------------------
    # Hint logic
    # ------------------------------------------------------------------
    def show_hint(self) -> None:
        if self.auto_active or self._result_modal:
            return
        self._clear_hint_targets()
        now = pygame.time.get_ticks()

        # Moves to foundation
        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            card = pile.cards[-1]
            fi = self._foundation_index_for_suit(card.suit)
            if self._can_place_on_foundation(card, fi):
                self.hint_targets = [("tableau", idx)]
                self.hint_expires_at = now + 2500
                return
        if self.waste_pile.cards:
            card = self.waste_pile.cards[-1]
            fi = self._foundation_index_for_suit(card.suit)
            if self._can_place_on_foundation(card, fi):
                self.hint_targets = [("waste", 0)]
                self.hint_expires_at = now + 2500
                return

        # Tableau moves
        for src_idx, src in enumerate(self.tableau):
            if not src.cards:
                continue
            card = src.cards[-1]
            for dst_idx, dst in enumerate(self.tableau):
                if src_idx == dst_idx:
                    continue
                if not dst.cards:
                    continue
                if self._can_place_on_tableau(card, dst_idx):
                    self.hint_targets = [("tableau", src_idx), ("tableau", dst_idx)]
                    self.hint_expires_at = now + 2500
                    return
        if self.waste_pile.cards:
            card = self.waste_pile.cards[-1]
            for dst_idx, dst in enumerate(self.tableau):
                if not dst.cards:
                    continue
                if self._can_place_on_tableau(card, dst_idx):
                    self.hint_targets = [("waste", 0), ("tableau", dst_idx)]
                    self.hint_expires_at = now + 2500
                    return

        if self.stock_pile.cards:
            self.hint_targets = [("stock", 0)]
            self._set_stock_hint_active(True)
            self.hint_expires_at = now + 2500
            return

    def _maybe_expire_hint(self) -> None:
        if self.hint_targets and pygame.time.get_ticks() > self.hint_expires_at:
            self._clear_hint_targets()

    def _set_stock_hint_active(self, active: bool) -> None:
        if self._stock_hint_active == active:
            return
        self._stock_hint_active = active
        if self._refill_button:
            self._refill_button.set_highlight(active)

    def _clear_hint_targets(self) -> None:
        self.hint_targets = None
        self._set_stock_hint_active(False)

    def _handle_stock_action(self) -> None:
        self._clear_hint_targets()
        if not self.stock_pile.cards:
            return
        self.push_undo()
        if self._draw_from_stock():
            self.peek.cancel()

    def _on_click_refill(self) -> None:
        if self.animator.active:
            return
        self._handle_stock_action()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        if self._result_modal:
            if self._handle_result_modal_event(event):
                return
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return
        if self.ui_helper.handle_menu_event(event):
            return
        if self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return
        if event.type == pygame.QUIT:
            self.app.running = False
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.ui_helper.toggle_menu_modal()
            return
        if self.drag_pan.handle_event(event, target=self, clamp=self._clamp_scroll_xy):
            self.peek.cancel()
            return
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y += event.y * 60
            self.scroll_x += event.x * 40
            self._clamp_scroll_xy()
            self.peek.cancel()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_mouse_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._on_mouse_up(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            self._on_mouse_motion(event.pos, event.rel)

    def _screen_to_world(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        return pos[0] - self.scroll_x, pos[1] - self.scroll_y

    def _on_mouse_down(self, pos: Tuple[int, int]) -> None:
        if self.animator.active:
            return
        self._clear_hint_targets()
        world = self._screen_to_world(pos)

        # Stock click
        if self.stock_pile.hit(world) is not None:
            self._handle_stock_action()
            return

        # Waste drag
        if self.waste_pile.cards:
            hit = self.waste_pile.hit(world)
            if hit is not None and hit >= len(self.waste_pile.cards) - 1:
                now = pygame.time.get_ticks()
                if now - self._last_click_time < 350 and (abs(world[0] - self._last_click_pos[0]) < 6 and abs(world[1] - self._last_click_pos[1]) < 6):
                    if self._try_move_to_foundation("waste", 0):
                        return
                self.drag_state = _DragState(
                    cards=[self.waste_pile.cards[-1]],
                    src_kind="waste",
                    src_index=0,
                    offset=(world[0] - self.waste_pile.x, world[1] - self.waste_pile.y),
                )
                self.edge_pan.set_active(True)
                self._last_click_time = now
                self._last_click_pos = world
                return

        # Tableau drag
        for idx, pile in enumerate(self.tableau):
            hit = pile.hit(world)
            if hit is None:
                continue
            if hit == -1:
                continue
            if hit != len(pile.cards) - 1:
                continue
            card = pile.cards[-1]
            self.drag_state = _DragState(
                cards=[card],
                src_kind="tableau",
                src_index=idx,
                offset=(world[0] - pile.x, world[1] - pile.y),
            )
            # Double-click detection for quick foundation move
            now = pygame.time.get_ticks()
            if now - self._last_click_time < 350 and (abs(world[0] - self._last_click_pos[0]) < 6 and abs(world[1] - self._last_click_pos[1]) < 6):
                if self._try_move_to_foundation("tableau", idx):
                    self.drag_state = None
                    self.edge_pan.set_active(False)
                    return
            self.edge_pan.set_active(True)
            self._last_click_time = pygame.time.get_ticks()
            self._last_click_pos = world
            return

        # Foundation double-click (no drag)
        for fi, pile in enumerate(self.foundations):
            hit = pile.hit(pos)
            if hit is None:
                continue
            if pile.cards:
                card = pile.cards[-1]
                self.message = f"Foundation: {C.RANK_TO_TEXT[card.rank]}{C.SUITS[card.suit]}"
            return

    def _on_mouse_up(self, pos: Tuple[int, int]) -> None:
        if not self.drag_state:
            return
        world = self._screen_to_world(pos)
        drag = self.drag_state
        self.drag_state = None
        self.edge_pan.set_active(False)

        card = drag.cards[-1]
        if drag.src_kind == "tableau":
            origin = self.tableau[drag.src_index]
        else:
            origin = self.waste_pile

        # Attempt foundation placement first
        for fi, pile in enumerate(self.foundations):
            rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            if rect.collidepoint(pos):
                if self._can_place_on_foundation(card, fi):
                    self.push_undo()
                    origin.cards.pop()
                    if drag.src_kind == "tableau":
                        self._reset_tableau_dir(drag.src_index)
                    self._advance_foundation(card, fi)
                    self._fill_empty_piles()
                    self._check_for_completion()
                    self._check_for_loss()
                    return

        # Tableau drop
        for idx, pile in enumerate(self.tableau):
            rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H + max(0, (len(pile.cards) - 1) * pile.fan_y))
            if rect.collidepoint(world):
                if self._can_place_on_tableau(card, idx) and self._set_tableau_dir(idx, card, pile.cards[-1]):
                    self.push_undo()
                    origin.cards.pop()
                    pile.cards.append(card)
                    if drag.src_kind == "tableau":
                        self._reset_tableau_dir(drag.src_index)
                    self._fill_empty_piles()
                    self._check_for_completion()
                    self._check_for_loss()
                    return

        # No valid move – leave card in its original pile

    def _on_mouse_motion(self, pos: Tuple[int, int], rel: Tuple[int, int]) -> None:
        world = self._screen_to_world(pos)
        self.edge_pan.on_mouse_pos(pos)
        piles_for_peek = [self.waste_pile] + self.tableau
        self.peek.on_motion_over_piles(piles_for_peek, world)

    # ------------------------------------------------------------------
    # Update & draw
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        self._maybe_expire_hint()
        self._auto_play_step()
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        has_h = max_sx > min_sx
        has_v = max_sy > min_sy
        dx, dy = self.edge_pan.step(has_h_scroll=has_h, has_v_scroll=has_v)
        if dx or dy:
            self.scroll_x += dx
            self.scroll_y += dy
            self._clamp_scroll_xy()

    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)

        # Draw piles
        self._draw_pile(screen, self.stock_pile, "stock", 0)
        self._draw_pile(screen, self.waste_pile, "waste", 0)
        for idx, pile in enumerate(self.tableau):
            self._draw_pile(screen, pile, "tableau", idx)
        for fi, pile in enumerate(self.foundations):
            self._draw_pile(screen, pile, "foundation", fi)

        # Draw dragged card on top
        if self.drag_state:
            card = self.drag_state.cards[-1]
            mx, my = pygame.mouse.get_pos()
            world_x = mx - self.scroll_x
            world_y = my - self.scroll_y
            dx, dy = self.drag_state.offset
            surf = C.get_card_surface(card)
            screen.blit(surf, (world_x - dx + self.scroll_x, world_y - dy + self.scroll_y))

        # Draw hint overlay
        if self.hint_targets:
            overlay = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
            pygame.draw.rect(overlay, (255, 255, 0, 80), overlay.get_rect(), border_radius=C.CARD_RADIUS)
            for kind, index in self.hint_targets:
                if kind == "tableau":
                    pile = self.tableau[index]
                elif kind == "waste":
                    pile = self.waste_pile
                elif kind == "stock":
                    pile = self.stock_pile
                else:
                    continue
                ox, oy = self._scroll_offset_for_kind(kind)
                screen.blit(overlay, (pile.x + ox, pile.y + oy))

        # Scrollbars
        vbar = self._vertical_scrollbar()
        if vbar:
            track_x, track_y, track_h, thumb_y, thumb_h = vbar
            pygame.draw.rect(screen, (40, 40, 40), (track_x, track_y, 6, track_h), border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), (track_x, thumb_y, 6, thumb_h), border_radius=3)
        hbar = self._horizontal_scrollbar()
        if hbar:
            track_x, track_y, track_w, thumb_x, thumb_w = hbar
            pygame.draw.rect(screen, (40, 40, 40), (track_x, track_y, track_w, 6), border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), (thumb_x, track_y, thumb_w, 6), border_radius=3)

        # Top bar + message
        title = "British Square"
        extra = self.message
        self.draw_top_bar(screen, title, extra)
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

        # Result modal overlay (drawn after UI)
        if self._result_modal:
            self._draw_result_modal(screen)

        # Animator (on top of everything else)
        if self.animator.active:
            self.animator.draw(screen, self.scroll_x, self.scroll_y)

        # Peek overlay
        if not self._result_modal:
            self.peek.maybe_activate(pygame.time.get_ticks())
            if self.peek.overlay:
                card, px, py = self.peek.overlay
                surf = C.get_card_surface(card)
                screen.blit(surf, (px + self.scroll_x, py + self.scroll_y))

    def _draw_pile(self, screen, pile: C.Pile, kind: str = "", index: int = -1) -> None:
        skip_top = False
        if self.drag_state:
            if (
                kind == "tableau"
                and self.drag_state.src_kind == "tableau"
                and self.drag_state.src_index == index
            ):
                skip_top = True
            elif kind == "waste" and self.drag_state.src_kind == "waste":
                skip_top = True
        visible_count = len(pile.cards) - (1 if skip_top else 0)
        ox, oy = self._scroll_offset_for_kind(kind)
        if visible_count <= 0:
            pygame.draw.rect(
                screen,
                (255, 255, 255, 50),
                (pile.x + ox, pile.y + oy, C.CARD_W, C.CARD_H),
                width=2,
                border_radius=C.CARD_RADIUS,
            )
        else:
            for idx_card, card in enumerate(pile.cards):
                if skip_top and idx_card == len(pile.cards) - 1:
                    continue
                rect = pile.rect_for_index(idx_card)
                surf = C.get_card_surface(card)
                screen.blit(surf, (rect.x + ox, rect.y + oy))
        if kind == "tableau":
            self._draw_tableau_indicators(screen, pile, index, skip_top)

    def _draw_tableau_indicators(
        self, screen, pile: C.Pile, index: int, skip_top: bool
    ) -> None:
        if not hasattr(self, "tableau_info_font"):
            return
        ox, oy = self._scroll_offset_for_kind("tableau")
        base_x = pile.x + ox
        base_y = pile.y + oy
        display_count = max(0, len(pile.cards) - (1 if skip_top else 0))

        count_text = self.tableau_info_font.render(str(display_count), True, (255, 255, 255))
        count_box = pygame.Surface(
            (count_text.get_width() + 8, count_text.get_height() + 4), pygame.SRCALPHA
        )
        pygame.draw.rect(count_box, (0, 0, 0, 170), count_box.get_rect(), border_radius=4)
        count_box.blit(
            count_text,
            (
                (count_box.get_width() - count_text.get_width()) // 2,
                (count_box.get_height() - count_text.get_height()) // 2,
            ),
        )
        screen.blit(
            count_box,
            (
                base_x + C.CARD_W - count_box.get_width() - 4,
                base_y + C.CARD_H - count_box.get_height() - 4,
            ),
        )

        direction = 0
        if 0 <= index < len(self.tableau_dirs):
            direction = self.tableau_dirs[index]
        if direction == 0 or display_count <= 0:
            return
        arrow_surf = self._tableau_arrow_glyphs.get(direction)
        if arrow_surf is None:
            glyph = "\u2B06" if direction > 0 else "\u2B07"
            arrow_surf = self.tableau_info_font.render(glyph, True, (255, 255, 255))
            self._tableau_arrow_glyphs[direction] = arrow_surf
        arrow_box = pygame.Surface(
            (arrow_surf.get_width() + 8, arrow_surf.get_height() + 4), pygame.SRCALPHA
        )
        pygame.draw.rect(arrow_box, (0, 0, 0, 170), arrow_box.get_rect(), border_radius=4)
        arrow_box.blit(
            arrow_surf,
            (
                (arrow_box.get_width() - arrow_surf.get_width()) // 2,
                (arrow_box.get_height() - arrow_surf.get_height()) // 2,
            ),
        )
        screen.blit(
            arrow_box,
            (
                base_x + 4,
                base_y + C.CARD_H - arrow_box.get_height() - 4,
            ),
        )

    def _draw_result_modal(self, screen) -> None:
        modal_rect = pygame.Rect(0, 0, 420, 220)
        modal_rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))
        pygame.draw.rect(screen, (245, 245, 245), modal_rect, border_radius=12)
        pygame.draw.rect(screen, (40, 40, 45), modal_rect, width=2, border_radius=12)
        message = self._result_modal.get("message", "") if self._result_modal else ""
        font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        text_surf = font.render(message, True, (30, 30, 40))
        screen.blit(text_surf, (modal_rect.centerx - text_surf.get_width() // 2, modal_rect.y + 56))

        buttons = self._result_modal.get("buttons", []) if self._result_modal else []
        btn_width = 140
        btn_height = 50
        gap = 24
        total_width = len(buttons) * btn_width + max(0, len(buttons) - 1) * gap
        start_x = modal_rect.centerx - total_width // 2
        btn_y = modal_rect.bottom - btn_height - 36
        font_btn = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 24, bold=True)
        for idx, button in enumerate(buttons):
            rect = pygame.Rect(start_x + idx * (btn_width + gap), btn_y, btn_width, btn_height)
            button["rect"] = rect
            pygame.draw.rect(screen, (230, 230, 235), rect, border_radius=10)
            pygame.draw.rect(screen, (60, 60, 65), rect, width=2, border_radius=10)
            label = button.get("label", "")
            label_surf = font_btn.render(label, True, (20, 20, 30))
            screen.blit(label_surf, (rect.centerx - label_surf.get_width() // 2, rect.centery - label_surf.get_height() // 2))

    def _handle_result_modal_event(self, event) -> bool:
        if event.type == pygame.QUIT:
            self.app.running = False
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            buttons = self._result_modal.get("buttons", []) if self._result_modal else []
            for button in buttons:
                rect = button.get("rect")
                if rect and rect.collidepoint(event.pos):
                    action = button.get("action")
                    if action == "new":
                        self.deal_new()
                    else:
                        self.ui_helper.goto_main_menu()
                    self._result_modal = None
                    return True
            return True
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_y):
                self.deal_new()
                self._result_modal = None
                return True
            if event.key in (pygame.K_ESCAPE, pygame.K_n):
                self.ui_helper.goto_main_menu()
                self._result_modal = None
                return True
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            return True
        return True

