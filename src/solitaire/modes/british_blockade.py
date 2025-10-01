"""British Blockade solitaire mode."""

from __future__ import annotations

import json
import os
import random
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.modes.base_scene import ModeUIHelper, ScrollableSceneMixin


_SAVE_FILENAME = "british_blockade_save.json"


def _bb_dir() -> str:
    return C.project_saves_dir("british_blockade")


def _bb_save_path() -> str:
    return os.path.join(_bb_dir(), _SAVE_FILENAME)


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
            return json.load(fh)
    except Exception:
        return None


def has_saved_game() -> bool:
    data = _safe_read_json(_bb_save_path())
    if not isinstance(data, dict):
        return False
    if data.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict]:
    data = _safe_read_json(_bb_save_path())
    if not isinstance(data, dict):
        return None
    return data


def delete_saved_game() -> None:
    try:
        path = _bb_save_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def _deck_two_decks(shuffle: bool = True) -> List[C.Card]:
    cards: List[C.Card] = [
        C.Card(suit, rank, False)
        for suit in range(4)
        for rank in range(1, 14)
        for _ in range(2)
    ]
    if shuffle:
        random.shuffle(cards)
    return cards


def _serialize_pile_cards(cards: Sequence[C.Card]) -> List[Tuple[int, int, bool]]:
    return [(c.suit, c.rank, bool(c.face_up)) for c in cards]


def _deserialize_cards(entries: Iterable[Sequence[int]]) -> List[C.Card]:
    result: List[C.Card] = []
    for entry in entries:
        try:
            suit, rank, face_up = entry
        except ValueError:
            continue
        result.append(C.Card(int(suit), int(rank), bool(face_up)))
    return result


@dataclass
class _DragState:
    card: C.Card
    src_kind: str  # "tableau" | "foundation_up" | "foundation_down"
    row: int
    col: int
    offset: Tuple[int, int]


class _EndGamePrompt:
    """Simple modal offering a new game or returning to the menu."""

    def __init__(self, on_new_game, on_menu):
        self.visible: bool = False
        self.title: str = ""
        self.message: str = ""
        self._panel = pygame.Rect(0, 0, 0, 0)
        self._new_btn = C.Button("New Game", 0, 0, w=220, h=52, center=False)
        self._menu_btn = C.Button("Main Menu", 0, 0, w=220, h=52, center=False)
        self._on_new_game = on_new_game
        self._on_menu = on_menu

    def open(self, title: str, message: str) -> None:
        self.title = title
        self.message = message
        self.visible = True
        self._layout()

    def close(self) -> None:
        self.visible = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_y, pygame.K_SPACE):
                self._on_new_game()
                return True
            if event.key in (pygame.K_ESCAPE, pygame.K_n):
                self._on_menu()
                return True
            return True
        if event.type == pygame.MOUSEMOTION:
            self._layout()
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._new_btn.hovered(event.pos):
                self._on_new_game()
                return True
            if self._menu_btn.hovered(event.pos):
                self._on_menu()
                return True
            if not self._panel.collidepoint(event.pos):
                self.close()
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        surface.blit(overlay, (0, 0))
        self._layout()
        panel = self._panel
        pygame.draw.rect(surface, (245, 245, 250), panel, border_radius=18)
        pygame.draw.rect(surface, (90, 90, 100), panel, width=2, border_radius=18)

        title_font = C.FONT_TITLE or pygame.font.SysFont(pygame.font.get_default_font(), 38, bold=True)
        title_surf = title_font.render(self.title, True, (40, 40, 55))
        surface.blit(title_surf, (panel.centerx - title_surf.get_width() // 2, panel.top + 24))

        msg_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 24)
        lines = [line.strip() for line in self.message.splitlines() if line.strip()]
        y = panel.top + 24 + title_surf.get_height() + 16
        for line in lines:
            surf = msg_font.render(line, True, (40, 40, 45))
            surface.blit(surf, (panel.centerx - surf.get_width() // 2, y))
            y += surf.get_height() + 6

        mouse_pos = pygame.mouse.get_pos()
        self._new_btn.draw(surface, hover=self._new_btn.hovered(mouse_pos))
        self._menu_btn.draw(surface, hover=self._menu_btn.hovered(mouse_pos))

    def _layout(self) -> None:
        width = min(520, max(420, C.SCREEN_W - 200))
        height = 260
        panel = pygame.Rect(0, 0, width, height)
        panel.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._panel = panel

        btn_w = 200
        btn_h = 52
        gap = 32
        total = btn_w * 2 + gap
        start_x = panel.centerx - total // 2
        y = panel.bottom - btn_h - 28

        self._new_btn.rect.size = (btn_w, btn_h)
        self._new_btn.rect.topleft = (start_x, y)

        self._menu_btn.rect.size = (btn_w, btn_h)
        self._menu_btn.rect.topleft = (start_x + btn_w + gap, y)


class BritishBlockadeGameScene(ScrollableSceneMixin, C.Scene):
    columns: int = 10

    def __init__(self, app, load_state: Optional[Dict] = None):
        super().__init__(app)

        self.stock_pile = C.Pile(0, 0)
        self.foundation_up: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_down: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.tableau_rows: List[List[C.Pile]] = []

        self.anim: M.CardAnimator = M.CardAnimator()
        self.deal_queue: Deque[Tuple[C.Card, C.Pile, Tuple[int, int]]] = deque()

        self.undo_mgr = C.UndoManager()
        self.message: str = ""
        self.phase_two: bool = False
        self.drag_state: Optional[_DragState] = None
        self.hint_cells: Optional[List[Tuple[int, int]]] = None
        self.hint_expires_at: int = 0
        self.hint_stock: bool = False
        self.hint_stock_expires_at: int = 0
        self._last_click_time: int = 0
        self._last_click_pos: Tuple[int, int] = (0, 0)
        self._pending_auto_fill: bool = False
        self._initial_state: Optional[Dict] = None
        self._initialising: bool = False

        self.ui_helper = ModeUIHelper(self, game_id="british_blockade")

        def can_undo() -> bool:
            return self.undo_mgr.can_undo() and not self.anim.active

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart},
            undo_action={"on_click": self.undo, "enabled": can_undo},
            hint_action={"on_click": self.show_hint},
            save_action=(
                "Save&Exit",
                {"on_click": lambda: self._save_game(to_menu=True), "tooltip": "Save game and return to menu"},
            ),
            menu_tooltip="Return to menu",
        )

        self.end_prompt = _EndGamePrompt(self.deal_new, self.ui_helper.goto_menu)

        self.tableau_gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        self.tableau_gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))
        self.tableau_left = 0
        self.tableau_top = 0

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal_new()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def compute_layout(self) -> None:
        top_bar = getattr(C, "TOP_BAR_H", 60)
        self.stock_pile.x = C.SCREEN_W // 2 - C.CARD_W // 2
        self.stock_pile.y = top_bar + int(C.CARD_H * 0.5)

        self.tableau_top = self.stock_pile.y + C.CARD_H + int(C.CARD_H * 0.25)
        total_width = self.columns * C.CARD_W + (self.columns - 1) * self.tableau_gap_x
        self.tableau_left = self.stock_pile.x + C.CARD_W // 2 - total_width // 2

        self._ensure_rows(len(self.tableau_rows) or 1)

        foundation_pad = max(self.tableau_gap_x, 24)
        foundation_y = self.tableau_top + C.CARD_H // 2
        for idx, pile in enumerate(self.foundation_up):
            pile.x = self.tableau_left - foundation_pad - C.CARD_W
            pile.y = foundation_y + idx * (C.CARD_H + self.tableau_gap_y)
        for idx, pile in enumerate(self.foundation_down):
            pile.x = self.tableau_left + total_width + foundation_pad
            pile.y = foundation_y + idx * (C.CARD_H + self.tableau_gap_y)

    def _ensure_rows(self, count: int) -> None:
        while len(self.tableau_rows) < count:
            self.tableau_rows.append([C.Pile(0, 0) for _ in range(self.columns)])
        self._update_tableau_layout()

    def _update_tableau_layout(self) -> None:
        for row_index, row in enumerate(self.tableau_rows):
            y = self.tableau_top + row_index * (C.CARD_H + self.tableau_gap_y)
            for col_index, pile in enumerate(row):
                pile.fan_y = 0
                pile.fan_x = 0
                pile.x = self.tableau_left + col_index * (C.CARD_W + self.tableau_gap_x)
                pile.y = y

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _capture_state(self) -> Dict:
        tableau_data: List[List[List[Tuple[int, int, bool]]]] = []
        for row in self.tableau_rows:
            tableau_data.append([_serialize_pile_cards(pile.cards) for pile in row])
        return {
            "version": 1,
            "phase_two": self.phase_two,
            "stock": _serialize_pile_cards(self.stock_pile.cards),
            "tableau": tableau_data,
            "foundation_up": [_serialize_pile_cards(p.cards) for p in self.foundation_up],
            "foundation_down": [_serialize_pile_cards(p.cards) for p in self.foundation_down],
        }

    def _restore_state(self, state: Dict, *, reset_undo: bool = False) -> None:
        self.phase_two = bool(state.get("phase_two", False))

        self.stock_pile.cards = _deserialize_cards(state.get("stock", []))

        tableau = state.get("tableau", [])
        self.tableau_rows = []
        for row_entries in tableau:
            row: List[C.Pile] = [C.Pile(0, 0) for _ in range(self.columns)]
            for idx, entry in enumerate(row_entries[: self.columns]):
                row[idx].cards = _deserialize_cards(entry)
            self.tableau_rows.append(row)
        if not self.tableau_rows:
            self.tableau_rows = [[C.Pile(0, 0) for _ in range(self.columns)]]

        for idx, pile in enumerate(self.foundation_up):
            data = state.get("foundation_up", [])
            if idx < len(data):
                pile.cards = _deserialize_cards(data[idx])
            else:
                pile.cards = []
        for idx, pile in enumerate(self.foundation_down):
            data = state.get("foundation_down", [])
            if idx < len(data):
                pile.cards = _deserialize_cards(data[idx])
            else:
                pile.cards = []

        self._ensure_rows(len(self.tableau_rows))
        self._update_tableau_layout()
        self._pending_auto_fill = False
        self.drag_state = None
        self.deal_queue.clear()
        self.anim.cancel()
        if reset_undo:
            self.undo_mgr = C.UndoManager()

    def _save_game(self, *, to_menu: bool = False) -> None:
        data = self._capture_state()
        data["completed"] = False
        _safe_write_json(_bb_save_path(), data)
        if to_menu:
            self.ui_helper.goto_menu()

    def _load_from_state(self, state: Dict) -> None:
        cleaned = dict(state)
        cleaned.pop("completed", None)
        self._restore_state(cleaned, reset_undo=True)
        self._initial_state = self._capture_state()
        self._initialising = False

    # ------------------------------------------------------------------
    # Undo helpers
    # ------------------------------------------------------------------
    def push_undo(self) -> None:
        snapshot = self._capture_state()

        def _restore(snapshot=snapshot):
            self._restore_state(snapshot, reset_undo=False)

        self.undo_mgr.push(_restore)

    def undo(self) -> None:
        if self.anim.active:
            return
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.hint_cells = None
            self.hint_expires_at = 0
            self.end_prompt.close()

    # ------------------------------------------------------------------
    # Game setup
    # ------------------------------------------------------------------
    def deal_new(self) -> None:
        self.end_prompt.close()
        delete_saved_game()
        deck = _deck_two_decks(shuffle=True)
        self.phase_two = False
        self.drag_state = None
        self.hint_cells = None
        self.hint_expires_at = 0
        self.deal_queue.clear()
        self.anim.cancel()
        self.undo_mgr = C.UndoManager()
        self._initial_state = None
        self._initialising = True

        self.stock_pile.cards = []
        self.tableau_rows = []
        self._ensure_rows(1)
        self._pending_auto_fill = False

        # Prepare foundations
        suit_order = [0, 1, 2, 3]
        for idx, suit in enumerate(suit_order):
            ace = next((card for card in deck if card.suit == suit and card.rank == 1), None)
            king = next((card for card in deck if card.suit == suit and card.rank == 13), None)
            if ace:
                deck.remove(ace)
                ace.face_up = True
                self.foundation_up[idx].cards = [ace]
            else:
                self.foundation_up[idx].cards = []
            if king:
                deck.remove(king)
                king.face_up = True
                self.foundation_down[idx].cards = [king]
            else:
                self.foundation_down[idx].cards = []

        self.stock_pile.cards = deck
        for card in self.stock_pile.cards:
            card.face_up = False

        self._update_tableau_layout()
        self._deal_initial_row()

    def restart(self) -> None:
        if self.anim.active:
            return
        if self._initial_state:
            self._restore_state(self._initial_state, reset_undo=True)
        else:
            self.deal_new()

    def _deal_initial_row(self) -> None:
        if not self.tableau_rows:
            self._ensure_rows(1)
        first_row = self.tableau_rows[0]
        for pile in first_row:
            self._enqueue_deal(pile)
        if not self.deal_queue:
            # No cards to animate (stock empty) – capture immediate state
            self._initial_state = self._capture_state()
            self._initialising = False

    # ------------------------------------------------------------------
    # Tableau / foundation helpers
    # ------------------------------------------------------------------
    def _iter_tableau(self) -> Iterable[Tuple[int, int, C.Pile]]:
        for row_idx, row in enumerate(self.tableau_rows):
            for col_idx, pile in enumerate(row):
                yield row_idx, col_idx, pile

    def iter_scroll_piles(self) -> Iterable[C.Pile]:  # type: ignore[override]
        for _row, _col, pile in self._iter_tableau():
            yield pile
        for pile in self.foundation_up:
            yield pile
        for pile in self.foundation_down:
            yield pile
        yield self.stock_pile

    def _enqueue_deal(self, target: C.Pile) -> bool:
        if not self.stock_pile.cards:
            return False
        index = len(self.stock_pile.cards) - 1
        if index >= 0:
            src_rect = self.stock_pile.rect_for_index(index)
        else:
            src_rect = pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H)
        card = self.stock_pile.cards.pop()
        card.face_up = True
        self.deal_queue.append((card, target, (src_rect.x, src_rect.y)))
        if not self.anim.active:
            self._start_next_animation()
        return True

    def _start_next_animation(self) -> None:
        if self.anim.active:
            return
        if not self.deal_queue:
            self._after_deal_queue_empty()
            return
        card, target, from_xy = self.deal_queue.popleft()
        self.anim.start_move(
            card,
            from_xy,
            (target.x, target.y),
            dur_ms=260,
            on_complete=lambda c=card, p=target: self._on_deal_complete(c, p),
        )

    def _on_deal_complete(self, card: C.Card, pile: C.Pile) -> None:
        pile.cards.append(card)
        if self.deal_queue:
            self.anim.cancel()
            self._start_next_animation()
        else:
            self.anim.cancel()
            self._after_deal_queue_empty()

    def _after_deal_queue_empty(self) -> None:
        if self._initialising and not self.deal_queue:
            self._initialising = False
            self._initial_state = self._capture_state()
        if self._pending_auto_fill:
            self._pending_auto_fill = False
            self._fill_gaps_if_needed()
        self._check_phase_progress()

    def _fill_gaps_if_needed(self) -> None:
        if self.phase_two:
            return
        if self.anim.active:
            return
        filled = False
        for row_idx, row in enumerate(self.tableau_rows):
            for pile in row:
                if pile.cards:
                    continue
                if self._enqueue_deal(pile):
                    filled = True
                    break
            if filled:
                break
        if not filled:
            self._check_phase_progress()

    def _check_phase_progress(self) -> None:
        if self.phase_two:
            self._check_for_completion()
            return
        rows_filled = all(all(bool(pile.cards) for pile in row) for row in self.tableau_rows)
        if len(self.tableau_rows) == 1 and rows_filled and not self._has_tableau_moves():
            self._add_row_with_deal()
            return
        if len(self.tableau_rows) == 2 and rows_filled and not self._has_tableau_moves():
            self._add_row_with_deal()
            self.phase_two = True
            return
        self._check_for_completion()

    def _add_row_with_deal(self) -> None:
        self._ensure_rows(len(self.tableau_rows) + 1)
        new_row = self.tableau_rows[-1]
        for pile in new_row:
            self._enqueue_deal(pile)

    def _has_tableau_moves(self) -> bool:
        for row_idx, col_idx, pile in self._iter_tableau():
            if not pile.cards:
                continue
            if not self._card_accessible(row_idx, col_idx):
                continue
            card = pile.cards[-1]
            up_idx = self._foundation_index(card.suit)
            if self._can_place_on_up(card, up_idx):
                return True
            if self._can_place_on_down(card, up_idx):
                return True
        return False

    def _foundation_index(self, suit: int) -> int:
        return max(0, min(3, suit))

    def _can_place_on_up(self, card: C.Card, index: int) -> bool:
        pile = self.foundation_up[index]
        if not pile.cards:
            return card.rank == 1
        top = pile.cards[-1]
        return card.rank == top.rank + 1 and card.suit == top.suit and top.rank < 13

    def _can_place_on_down(self, card: C.Card, index: int) -> bool:
        pile = self.foundation_down[index]
        if not pile.cards:
            return card.rank == 13
        top = pile.cards[-1]
        return card.rank == top.rank - 1 and card.suit == top.suit and top.rank > 1

    def _card_accessible(self, row: int, col: int) -> bool:
        if row < 0 or col < 0:
            return False
        if row >= len(self.tableau_rows):
            return False
        pile = self.tableau_rows[row][col]
        if not pile.cards:
            return False
        if not self.phase_two:
            return True
        # Phase two – a card can be played only if it has at least one open vertical edge
        has_above = row > 0 and bool(self.tableau_rows[row - 1][col].cards)
        has_below = row + 1 < len(self.tableau_rows) and bool(self.tableau_rows[row + 1][col].cards)
        return not (has_above and has_below)

    def _move_card_to_foundation(self, row: int, col: int, target_kind: str, *, animate: bool = True) -> bool:
        if self.anim.active:
            return False
        if row >= len(self.tableau_rows):
            return False
        pile = self.tableau_rows[row][col]
        if not pile.cards:
            return False
        card = pile.cards[-1]
        f_index = self._foundation_index(card.suit)
        dest_pile = self.foundation_up[f_index] if target_kind == "up" else self.foundation_down[f_index]
        can_place = (
            self._can_place_on_up(card, f_index)
            if target_kind == "up"
            else self._can_place_on_down(card, f_index)
        )
        if not can_place:
            return False
        self.push_undo()
        pile.cards.pop()
        start = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)

        def _finish(card_ref: C.Card = card, dest=dest_pile):
            dest.cards.append(card_ref)
            self._pending_auto_fill = True
            self._fill_gaps_if_needed()
            self._check_for_completion()

        if animate:
            self.anim.start_move(card, (start.x, start.y), (dest_pile.x, dest_pile.y), dur_ms=260, on_complete=_finish)
        else:
            _finish()
        return True

    def _double_click_move(self, row: int, col: int) -> bool:
        if not self._card_accessible(row, col):
            return False
        pile = self.tableau_rows[row][col]
        if not pile.cards:
            return False
        card = pile.cards[-1]
        idx = self._foundation_index(card.suit)
        can_up = self._can_place_on_up(card, idx)
        can_down = self._can_place_on_down(card, idx)
        if can_up and not can_down:
            return self._move_card_to_foundation(row, col, "up")
        if can_down and not can_up:
            return self._move_card_to_foundation(row, col, "down")
        return False

    def _check_for_completion(self) -> None:
        if all(len(pile.cards) >= 13 for pile in self.foundation_up) and all(len(pile.cards) >= 13 for pile in self.foundation_down):
            self.end_prompt.open("You Win", "All foundations complete!")
            return
        if not self.stock_pile.cards:
            if not self._has_any_moves():
                self.end_prompt.open("Game Over", "No more moves are available.")

    def _has_any_moves(self) -> bool:
        if self._has_tableau_moves():
            return True
        if self.phase_two:
            # Check foundation transfers
            for idx in range(4):
                up = self.foundation_up[idx]
                down = self.foundation_down[idx]
                if up.cards and self._can_place_on_down(up.cards[-1], idx):
                    return True
                if down.cards and self._can_place_on_up(down.cards[-1], idx):
                    return True
        return False

    # ------------------------------------------------------------------
    # Hinting
    # ------------------------------------------------------------------
    def show_hint(self) -> None:
        self.hint_cells = None
        self.hint_expires_at = 0
        self.hint_stock = False
        self.hint_stock_expires_at = 0
        if self.anim.active:
            return
        suggestions: List[Tuple[int, int]] = []
        for row_idx, col_idx, pile in self._iter_tableau():
            if not pile.cards:
                continue
            if not self._card_accessible(row_idx, col_idx):
                continue
            card = pile.cards[-1]
            idx = self._foundation_index(card.suit)
            can_up = self._can_place_on_up(card, idx)
            can_down = self._can_place_on_down(card, idx)
            if can_up or can_down:
                suggestions.append((row_idx, col_idx))
                break
        if suggestions:
            self.hint_cells = suggestions
            self.hint_expires_at = pygame.time.get_ticks() + 3500
            return
        if not self._has_any_moves() and self.stock_pile.cards:
            self.hint_stock = True
            self.hint_stock_expires_at = pygame.time.get_ticks() + 3500

    def _update_hint(self) -> None:
        if self.hint_cells and pygame.time.get_ticks() > self.hint_expires_at:
            self.hint_cells = None
        if self.hint_stock and pygame.time.get_ticks() > self.hint_stock_expires_at:
            self.hint_stock = False

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        if self.end_prompt.visible and self.end_prompt.handle_event(event):
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
        if ScrollableSceneMixin.handle_scroll_event(self, event):
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.ui_helper.toggle_menu_modal()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_mouse_down(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._on_mouse_up(event.pos)
        elif event.type == pygame.MOUSEMOTION:
            if self.drag_state:
                self.edge_pan.on_mouse_pos(event.pos)

    def _on_mouse_down(self, pos: Tuple[int, int]) -> None:
        if self.anim.active:
            return
        self.hint_cells = None
        world = self._screen_to_world(pos)

        if not self.phase_two and self.stock_pile.hit(world) is not None:
            return

        if self.phase_two and self.stock_pile.hit(world) is not None:
            if self.stock_pile.cards:
                self.push_undo()
                self._deal_from_stock_phase_two()
            return

        # Tableau selection
        for row_idx, col_idx, pile in self._iter_tableau():
            rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            if not rect.collidepoint(world):
                continue
            if not pile.cards:
                continue
            if not self._card_accessible(row_idx, col_idx):
                continue
            now = pygame.time.get_ticks()
            if (
                now - self._last_click_time < 350
                and abs(world[0] - self._last_click_pos[0]) < 6
                and abs(world[1] - self._last_click_pos[1]) < 6
            ):
                if self._double_click_move(row_idx, col_idx):
                    self._last_click_time = now
                    self._last_click_pos = world
                    return
            self.drag_state = _DragState(
                card=pile.cards[-1],
                src_kind="tableau",
                row=row_idx,
                col=col_idx,
                offset=(world[0] - pile.x, world[1] - pile.y),
            )
            self.edge_pan.set_active(True)
            self._last_click_time = now
            self._last_click_pos = world
            return

        # Foundation drag (phase two)
        if self.phase_two:
            for idx, pile in enumerate(self.foundation_up):
                if not pile.cards:
                    continue
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
                if rect.collidepoint(world):
                    card = pile.cards[-1]
                    if self._can_place_on_down(card, idx):
                        self.drag_state = _DragState(
                            card=card,
                            src_kind="foundation_up",
                            row=idx,
                            col=0,
                            offset=(world[0] - pile.x, world[1] - pile.y),
                        )
                        self.edge_pan.set_active(True)
                        self._last_click_time = pygame.time.get_ticks()
                        self._last_click_pos = world
                        return
            for idx, pile in enumerate(self.foundation_down):
                if not pile.cards:
                    continue
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
                if rect.collidepoint(world):
                    card = pile.cards[-1]
                    if self._can_place_on_up(card, idx):
                        self.drag_state = _DragState(
                            card=card,
                            src_kind="foundation_down",
                            row=idx,
                            col=0,
                            offset=(world[0] - pile.x, world[1] - pile.y),
                        )
                        self.edge_pan.set_active(True)
                        self._last_click_time = pygame.time.get_ticks()
                        self._last_click_pos = world
                        return

    def _on_mouse_up(self, pos: Tuple[int, int]) -> None:
        if not self.drag_state:
            return
        drag = self.drag_state
        self.drag_state = None
        self.edge_pan.set_active(False)
        world = self._screen_to_world(pos)

        if drag.src_kind == "tableau":
            origin = self.tableau_rows[drag.row][drag.col]
            card = origin.cards[-1] if origin.cards else None
            if not card:
                return
            idx = self._foundation_index(card.suit)
            for target_kind, pile in (("up", self.foundation_up[idx]), ("down", self.foundation_down[idx])):
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
                if rect.collidepoint(world):
                    if (target_kind == "up" and self._can_place_on_up(card, idx)) or (
                        target_kind == "down" and self._can_place_on_down(card, idx)
                    ):
                        self._move_card_to_foundation(drag.row, drag.col, target_kind)
                        return
            return

        if drag.src_kind in {"foundation_up", "foundation_down"} and self.phase_two:
            source_list = self.foundation_up if drag.src_kind == "foundation_up" else self.foundation_down
            source_pile = source_list[drag.row]
            if not source_pile.cards:
                return
            card = source_pile.cards[-1]
            idx = drag.row
            dest_pile = self.foundation_down[idx] if drag.src_kind == "foundation_up" else self.foundation_up[idx]
            dest_kind = "down" if drag.src_kind == "foundation_up" else "up"
            rect = pygame.Rect(dest_pile.x, dest_pile.y, C.CARD_W, C.CARD_H)
            if rect.collidepoint(world):
                can = self._can_place_on_down(card, idx) if dest_kind == "down" else self._can_place_on_up(card, idx)
                if can:
                    self.push_undo()
                    source_pile.cards.pop()

                    def _finish(card_ref: C.Card = card, pile_ref: C.Pile = dest_pile):
                        pile_ref.cards.append(card_ref)
                        self._check_for_completion()

                    self.anim.start_move(card, (source_pile.x, source_pile.y), (dest_pile.x, dest_pile.y), dur_ms=260, on_complete=_finish)
                    return

    def _deal_from_stock_phase_two(self) -> None:
        targets: List[C.Pile] = []
        for _row_idx, _col_idx, pile in self._iter_tableau():
            if not pile.cards:
                targets.append(pile)
        # Always add a new row
        self._ensure_rows(len(self.tableau_rows) + 1)
        for pile in self.tableau_rows[-1]:
            targets.append(pile)
        for pile in targets:
            if not self.stock_pile.cards:
                break
            self._enqueue_deal(pile)

    # ------------------------------------------------------------------
    # Update & draw
    # ------------------------------------------------------------------
    def _draw_pile_with_drag(
        self,
        screen: pygame.Surface,
        pile: C.Pile,
        *,
        row: Optional[int] = None,
        col: Optional[int] = None,
        foundation_kind: Optional[str] = None,
        foundation_index: Optional[int] = None,
    ) -> None:
        drag = self.drag_state
        skip_top = False
        if drag and pile.cards:
            if drag.src_kind == "tableau" and row is not None and col is not None:
                if drag.row == row and drag.col == col and pile.cards[-1] is drag.card:
                    skip_top = True
            elif (
                foundation_kind
                and foundation_index is not None
                and drag.src_kind == foundation_kind
                and drag.row == foundation_index
                and pile.cards[-1] is drag.card
            ):
                skip_top = True
        if skip_top:
            card = pile.cards.pop()
            try:
                pile.draw(screen)
            finally:
                pile.cards.append(card)
        else:
            pile.draw(screen)

    def update(self, dt: float) -> None:
        self._update_hint()
        if not self.anim.active and self.deal_queue:
            self._start_next_animation()

    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)
        with self.scrolling_draw_offset():
            # Draw stock
            self.stock_pile.draw(screen)
            if self.hint_stock:
                overlay = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
                pygame.draw.rect(overlay, (255, 255, 0, 90), overlay.get_rect(), border_radius=C.CARD_RADIUS)
                screen.blit(overlay, (self.stock_pile.x + self.scroll_x, self.stock_pile.y + self.scroll_y))
            for idx, pile in enumerate(self.foundation_up):
                self._draw_pile_with_drag(
                    screen,
                    pile,
                    foundation_kind="foundation_up",
                    foundation_index=idx,
                )
            for idx, pile in enumerate(self.foundation_down):
                self._draw_pile_with_drag(
                    screen,
                    pile,
                    foundation_kind="foundation_down",
                    foundation_index=idx,
                )
            for row_idx, col_idx, pile in self._iter_tableau():
                self._draw_pile_with_drag(screen, pile, row=row_idx, col=col_idx)

            if self.hint_cells:
                overlay = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
                pygame.draw.rect(overlay, (255, 255, 0, 90), overlay.get_rect(), border_radius=C.CARD_RADIUS)
                for row_idx, col_idx in self.hint_cells:
                    if row_idx < len(self.tableau_rows) and col_idx < len(self.tableau_rows[row_idx]):
                        pile = self.tableau_rows[row_idx][col_idx]
                        screen.blit(overlay, (pile.x + self.scroll_x, pile.y + self.scroll_y))

            if self.anim.active:
                self.anim.draw(screen, self.scroll_x, self.scroll_y)

        if self.drag_state:
            card = self.drag_state.card
            mx, my = pygame.mouse.get_pos()
            dx, dy = self.drag_state.offset
            surf = C.get_card_surface(card)
            screen.blit(surf, (mx - dx, my - dy))

        self.toolbar.draw(screen)
        self.ui_helper.draw_menu_modal(screen)
        if self.end_prompt.visible:
            self.end_prompt.draw(screen)

    def is_game_complete(self) -> bool:
        return all(len(pile.cards) >= 13 for pile in self.foundation_up) and all(len(pile.cards) >= 13 for pile in self.foundation_down)


__all__ = [
    "BritishBlockadeGameScene",
    "delete_saved_game",
    "has_saved_game",
    "load_saved_game",
]

