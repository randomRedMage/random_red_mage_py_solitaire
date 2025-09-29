"""Monte Carlo solitaire mode."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pygame

from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help


_SAVE_FILENAME = "monte_carlo_save.json"
_ROWS = 5
_COLS = 5


def _data_dir() -> str:
    return C.project_saves_dir("monte_carlo")


def _save_path() -> str:
    return os.path.join(_data_dir(), _SAVE_FILENAME)


def _safe_write_json(path: str, payload: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def _clear_saved_game() -> None:
    try:
        if os.path.isfile(_save_path()):
            os.remove(_save_path())
    except Exception:
        pass


def has_saved_game() -> bool:
    state = _safe_read_json(_save_path())
    if not isinstance(state, dict):
        return False
    if state.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    state = _safe_read_json(_save_path())
    if not isinstance(state, dict):
        return None
    if state.get("completed"):
        return None
    return state


def _card_to_dict(card: C.Card) -> Dict[str, Any]:
    return {"suit": int(card.suit), "rank": int(card.rank), "face_up": bool(card.face_up)}


def _card_from_dict(data: Dict[str, Any]) -> C.Card:
    suit = int(data.get("suit", 0))
    rank = int(data.get("rank", 1))
    face_up = bool(data.get("face_up", False))
    return C.Card(suit, rank, face_up)


class MonteCarloGameScene(C.Scene):
    rows: int = _ROWS
    cols: int = _COLS

    def __init__(self, app, load_state: Optional[Dict[str, Any]] = None):
        super().__init__(app)
        self.tableau: List[List[Optional[C.Card]]] = [[None for _ in range(self.cols)] for _ in range(self.rows)]
        self.stock_pile = C.Pile(0, 0)
        # Show a shallow upward fan so removed pairs form a neat stack.
        self.matched_pile = C.Pile(0, 0, fan_y=-max(4, C.CARD_H // 10))
        self.selection: Optional[Tuple[int, int]] = None
        self.message: str = ""
        self.game_over: bool = False
        self.did_win: bool = False
        self._initial_order: List[Tuple[int, int]] = []
        self._grid_left: int = 0
        self._grid_top: int = 0
        self._gap_x: int = getattr(C, "CARD_GAP_X", max(16, C.CARD_W // 6))
        self._gap_y: int = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))

        self.ui_helper = ModeUIHelper(self, game_id="monte_carlo")
        self.help = create_modal_help("monte_carlo")

        def can_compact() -> bool:
            return self.can_compact()

        def save_and_exit() -> None:
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.new_game},
            restart_action={"on_click": self.restart_current_deal, "tooltip": "Redeal the current layout"},
            save_action=(
                "Save&Exit",
                {"on_click": save_and_exit, "tooltip": "Save progress and return to the main menu"},
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            extra_actions=[
                (
                    "Compact",
                    {
                        "on_click": self.compact_and_fill,
                        "enabled": can_compact,
                        "tooltip": "Compact gaps and refill from the stock",
                        "shortcut": pygame.K_c,
                    },
                )
            ],
            toolbar_kwargs={"primary_labels": ("Compact",)},
        )

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
        else:
            self.new_game(clear_save=True)

    # ----- Game setup -----
    def compute_layout(self) -> None:
        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        self._gap_x = getattr(C, "CARD_GAP_X", max(16, C.CARD_W // 6))
        self._gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))
        top_y = max(80, top_bar_h + 24)

        left_column_width = C.CARD_W + self._gap_x
        tableau_width = self.cols * C.CARD_W + (self.cols - 1) * self._gap_x
        total_width = left_column_width + tableau_width
        left_edge = max(16, (C.SCREEN_W - total_width) // 2)

        stock_x = left_edge
        self.stock_pile.x = stock_x
        self.stock_pile.y = top_y

        self.matched_pile.x = stock_x
        self.matched_pile.y = top_y + C.CARD_H + self._gap_y

        self._grid_left = stock_x + C.CARD_W + self._gap_x
        self._grid_top = top_y

        if hasattr(self, "toolbar") and self.toolbar:
            self.toolbar.relayout()
        self.ui_helper.relayout_menu_modal()

    def new_game(self, *, clear_save: bool = True) -> None:
        deck = C.make_deck(shuffle=True)
        self._initial_order = [(card.suit, card.rank) for card in deck]
        self._deal_from_deck(deck)
        if clear_save:
            _clear_saved_game()

    def restart_current_deal(self) -> None:
        if not self._initial_order:
            self.new_game()
            return
        deck = [C.Card(s, r, False) for (s, r) in self._initial_order]
        self._deal_from_deck(deck)
        _clear_saved_game()

    def _deal_from_deck(self, deck_cards: Sequence[C.Card]) -> None:
        deck: List[C.Card] = [C.Card(card.suit, card.rank, False) for card in deck_cards]
        self.tableau = [[None for _ in range(self.cols)] for _ in range(self.rows)]
        for row in range(self.rows):
            for col in range(self.cols):
                if not deck:
                    self.tableau[row][col] = None
                    continue
                card = deck.pop()
                card.face_up = True
                self.tableau[row][col] = card
        self.stock_pile.cards = deck
        self.matched_pile.cards = []
        self.selection = None
        self.message = ""
        self.game_over = False
        self.did_win = False

    # ----- Persistence -----
    def _serialise_state(self, *, completed: Optional[bool] = None) -> Dict[str, Any]:
        tableau_data: List[List[Optional[Dict[str, Any]]]] = []
        for row in self.tableau:
            tableau_row: List[Optional[Dict[str, Any]]] = []
            for card in row:
                tableau_row.append(_card_to_dict(card) if card is not None else None)
            tableau_data.append(tableau_row)
        state = {
            "tableau": tableau_data,
            "stock": [_card_to_dict(card) for card in self.stock_pile.cards],
            "matched": [_card_to_dict(card) for card in self.matched_pile.cards],
            "selection": list(self.selection) if self.selection else None,
            "message": self.message,
            "game_over": self.game_over,
            "did_win": self.did_win,
            "initial_order": [(int(s), int(r)) for (s, r) in self._initial_order],
            "completed": bool(completed) if completed is not None else bool(self.game_over),
        }
        return state

    def _save_game(self, *, to_menu: bool = False) -> None:
        state = self._serialise_state()
        _safe_write_json(_save_path(), state)
        if to_menu:
            self.ui_helper.goto_main_menu()

    def _load_from_state(self, state: Dict[str, Any]) -> None:
        tableau_data = state.get("tableau", [])
        rows: List[List[Optional[C.Card]]] = []
        for row in tableau_data:
            new_row: List[Optional[C.Card]] = []
            if isinstance(row, list):
                for entry in row:
                    if entry is None:
                        new_row.append(None)
                    elif isinstance(entry, dict):
                        card = _card_from_dict(entry)
                        card.face_up = True
                        new_row.append(card)
            rows.append(new_row)
        while len(rows) < self.rows:
            rows.append([None for _ in range(self.cols)])
        for idx, row in enumerate(rows):
            if len(row) < self.cols:
                row.extend([None] * (self.cols - len(row)))
            rows[idx] = row[: self.cols]
        self.tableau = rows[: self.rows]

        stock_data = state.get("stock", [])
        self.stock_pile.cards = []
        if isinstance(stock_data, list):
            for entry in stock_data:
                if isinstance(entry, dict):
                    card = _card_from_dict(entry)
                    card.face_up = False
                    self.stock_pile.cards.append(card)

        matched_data = state.get("matched", [])
        self.matched_pile.cards = []
        if isinstance(matched_data, list):
            for entry in matched_data:
                if isinstance(entry, dict):
                    card = _card_from_dict(entry)
                    card.face_up = True
                    self.matched_pile.cards.append(card)

        sel = state.get("selection")
        if isinstance(sel, (list, tuple)) and len(sel) == 2:
            try:
                r = int(sel[0])
                c = int(sel[1])
                if 0 <= r < self.rows and 0 <= c < self.cols and self.tableau[r][c] is not None:
                    self.selection = (r, c)
                else:
                    self.selection = None
            except Exception:
                self.selection = None
        else:
            self.selection = None

        self.message = str(state.get("message", "")) if isinstance(state.get("message"), str) else ""
        self.game_over = bool(state.get("game_over", False))
        self.did_win = bool(state.get("did_win", False))

        init = state.get("initial_order")
        if isinstance(init, list):
            order: List[Tuple[int, int]] = []
            for item in init:
                try:
                    s, r = item
                    order.append((int(s), int(r)))
                except Exception:
                    continue
            self._initial_order = order
        else:
            self._initial_order = []

    # ----- Helpers -----
    def can_compact(self) -> bool:
        if self.game_over:
            return False
        return self._has_gaps()

    def _has_gaps(self) -> bool:
        for row in self.tableau:
            for card in row:
                if card is None:
                    return True
        return False

    def _is_full(self) -> bool:
        return not self._has_gaps()

    def _cell_rect(self, row: int, col: int) -> pygame.Rect:
        x = self._grid_left + col * (C.CARD_W + self._gap_x)
        y = self._grid_top + row * (C.CARD_H + self._gap_y)
        return pygame.Rect(x, y, C.CARD_W, C.CARD_H)

    def _cell_at_point(self, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        px, py = pos
        for row in range(self.rows):
            for col in range(self.cols):
                rect = self._cell_rect(row, col)
                if rect.collidepoint(px, py):
                    return row, col
        return None

    def _cells_adjacent(self, a: Tuple[int, int], b: Tuple[int, int]) -> bool:
        ra, ca = a
        rb, cb = b
        if ra == rb and ca == cb:
            return False
        return max(abs(ra - rb), abs(ca - cb)) == 1

    def _remove_pair(self, first: Tuple[int, int], second: Tuple[int, int]) -> None:
        r1, c1 = first
        r2, c2 = second
        card1 = self.tableau[r1][c1]
        card2 = self.tableau[r2][c2]
        if card1 is None or card2 is None:
            return
        self.tableau[r1][c1] = None
        self.tableau[r2][c2] = None
        card1.face_up = True
        card2.face_up = True
        self.matched_pile.cards.append(card1)
        self.matched_pile.cards.append(card2)
        self.selection = None
        self.message = "Pair removed."
        self._check_game_end()

    def _compact_rows(self) -> bool:
        changed = False
        for idx, row in enumerate(self.tableau):
            filtered = [card for card in row if card is not None]
            if len(filtered) != len(row):
                filtered.extend([None] * (len(row) - len(filtered)))
                if filtered != row:
                    self.tableau[idx] = filtered
                    changed = True
        return changed

    def _compact_columns(self) -> bool:
        changed = False
        for col in range(self.cols):
            column_cards: List[C.Card] = []
            for row in range(self.rows):
                card = self.tableau[row][col]
                if card is not None:
                    column_cards.append(card)
            for row in range(self.rows):
                new_card = column_cards[row] if row < len(column_cards) else None
                if self.tableau[row][col] is not new_card:
                    self.tableau[row][col] = new_card
                    changed = True
        return changed

    def compact_and_fill(self) -> None:
        if not self.can_compact():
            if not self.game_over:
                self.message = "No gaps to compact."
            return
        changed = True
        while changed:
            changed = False
            if self._compact_rows():
                changed = True
            if self._compact_columns():
                changed = True
        self._fill_from_stock()
        if not self.game_over:
            self.message = "Tableau compacted."
        self._check_game_end()

    def _fill_from_stock(self) -> None:
        for row in range(self.rows):
            for col in range(self.cols):
                if self.tableau[row][col] is None and self.stock_pile.cards:
                    card = self.stock_pile.cards.pop()
                    card.face_up = True
                    self.tableau[row][col] = card

    def _has_matching_pairs(self) -> bool:
        for row in range(self.rows):
            for col in range(self.cols):
                card = self.tableau[row][col]
                if card is None:
                    continue
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr = row + dr
                        nc = col + dc
                        if 0 <= nr < self.rows and 0 <= nc < self.cols:
                            other = self.tableau[nr][nc]
                            if other is not None and other.rank == card.rank:
                                return True
        return False

    def _check_game_end(self) -> None:
        if all(card is None for row in self.tableau for card in row) and not self.stock_pile.cards:
            self.game_over = True
            self.did_win = True
            self.message = "You win!"
            _clear_saved_game()
            return
        if self._is_full() and not self.stock_pile.cards and not self._has_matching_pairs():
            self.game_over = True
            self.did_win = False
            self.message = "No more moves."
            _clear_saved_game()

    # ----- Drawing -----
    def draw(self, screen) -> None:
        screen.fill(C.TABLE_BG)

        # Draw tableau grid
        for row in range(self.rows):
            for col in range(self.cols):
                rect = self._cell_rect(row, col)
                card = self.tableau[row][col]
                if card is None:
                    pygame.draw.rect(screen, (255, 255, 255, 60), rect, border_radius=C.CARD_RADIUS, width=2)
                else:
                    surf = C.get_card_surface(card)
                    screen.blit(surf, rect.topleft)
        if self.selection is not None:
            sr, sc = self.selection
            rect = self._cell_rect(sr, sc)
            pygame.draw.rect(screen, C.GOLD, rect, width=4, border_radius=C.CARD_RADIUS)

        # Draw piles
        self.stock_pile.draw(screen)
        self.matched_pile.draw(screen)

        # Labels
        font = C.FONT_SMALL if C.FONT_SMALL is not None else pygame.font.SysFont(pygame.font.get_default_font(), 20, bold=True)
        stock_label = font.render("Stock", True, C.WHITE)
        screen.blit(stock_label, (self.stock_pile.x + (C.CARD_W - stock_label.get_width()) // 2, self.stock_pile.y - 24))
        pairs_label = font.render("Pairs", True, C.WHITE)
        screen.blit(pairs_label, (self.matched_pile.x + (C.CARD_W - pairs_label.get_width()) // 2, self.matched_pile.y - 24))

        if self.message:
            msg_font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 24, bold=True)
            msg_surf = msg_font.render(self.message, True, (255, 255, 200))
            screen.blit(msg_surf, (C.SCREEN_W // 2 - msg_surf.get_width() // 2, C.SCREEN_H - 48))

        C.Scene.draw_top_bar(self, screen, "Monte Carlo")
        if self.toolbar:
            self.toolbar.draw(screen)
        if self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

    # ----- Event handling -----
    def handle_event(self, event) -> None:
        if self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN):
                return
        if self.ui_helper.handle_menu_event(event):
            return
        if self.toolbar and self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return

        if event.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", pygame.NOEVENT)):
            self.compute_layout()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.selection = None
            self.message = ""
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.help.visible:
                return
            if self.stock_pile.top_rect().collidepoint(event.pos):
                if self.can_compact():
                    self.compact_and_fill()
                return
            if self.game_over:
                return
            cell = self._cell_at_point(event.pos)
            if cell is None:
                self.selection = None
                return
            row, col = cell
            card = self.tableau[row][col]
            if card is None:
                self.selection = None
                return
            if self.selection is None:
                self.selection = (row, col)
                self.message = "Select a matching neighbor."
                return
            if self.selection == (row, col):
                self.selection = None
                self.message = ""
                return
            current = self.selection
            first_card = self.tableau[current[0]][current[1]]
            if first_card is None:
                self.selection = (row, col)
                return
            if not self._cells_adjacent(current, (row, col)):
                self.selection = (row, col)
                self.message = "Cards must touch to pair."
                return
            if first_card.rank != card.rank:
                self.selection = (row, col)
                self.message = "Ranks must match."
                return
            self._remove_pair(current, (row, col))
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.ui_helper.toggle_menu_modal()

    # ----- Status helpers -----
    def any_pairs_available(self) -> bool:
        return self._has_matching_pairs()

    def is_game_complete(self) -> bool:
        return self.game_over and self.did_win
