"""La Duchesse de Luynes solitaire mode.

Implements the initial deal and core mechanics for the La Duchesse de Luynes
builder-style solitaire variant. Additional reserve interactions and advanced
rules may be added in future sessions; this module focuses on the basic play
loop, stock dealing, foundation building, and win detection as described in the
initial specification.
"""

from __future__ import annotations

import json
import os
import random
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.modes.base_scene import ModeUIHelper


_SAVE_FILENAME = "duchess_de_luynes_save.json"


def _save_dir() -> str:
    return C.project_saves_dir("duchess_de_luynes")


def _save_path() -> str:
    return os.path.join(_save_dir(), _SAVE_FILENAME)


def _safe_write_json(path: str, data: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def has_saved_game() -> bool:
    data = _safe_read_json(_save_path())
    if not data or data.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    data = _safe_read_json(_save_path())
    if not data or data.get("completed"):
        return None
    return data


def delete_saved_game() -> None:
    try:
        path = _save_path()
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def _deck_two_decks() -> List[C.Card]:
    cards: List[C.Card] = [
        C.Card(suit, rank, face_up=False)
        for _ in range(2)
        for suit in range(4)
        for rank in range(1, 14)
    ]
    random.shuffle(cards)
    return cards


def _serialise_cards(cards: Sequence[C.Card]) -> List[Tuple[int, int, bool]]:
    return [(c.suit, c.rank, bool(c.face_up)) for c in cards]


def _deserialise_cards(entries: Iterable[Sequence[int]]) -> List[C.Card]:
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
    origin: Tuple[str, int]  # ("tableau", index)
    offset: Tuple[int, int]
    snapshot: Optional[Dict[str, Any]] = None


class _EndGameModal:
    """Simple modal displayed when the player wins the game."""

    def __init__(self, on_new_game, on_menu):
        self.visible: bool = False
        self._panel = pygame.Rect(0, 0, 0, 0)
        self._new_btn = C.Button("New Game", 0, 0, w=220, h=52, center=False)
        self._menu_btn = C.Button("Main Menu", 0, 0, w=220, h=52, center=False)
        self._on_new_game = on_new_game
        self._on_menu = on_menu

    def open(self) -> None:
        self.visible = True
        self._layout()

    def close(self) -> None:
        self.visible = False

    def _layout(self) -> None:
        width = min(520, max(420, C.SCREEN_W - 200))
        height = 240
        self._panel = pygame.Rect(0, 0, width, height)
        self._panel.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)

        btn_w = 200
        btn_h = 52
        gap = 32
        start_x = self._panel.centerx - (btn_w * 2 + gap) // 2
        y = self._panel.bottom - btn_h - 28
        self._new_btn.rect.size = (btn_w, btn_h)
        self._new_btn.rect.topleft = (start_x, y)
        self._menu_btn.rect.size = (btn_w, btn_h)
        self._menu_btn.rect.topleft = (start_x + btn_w + gap, y)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_y):
                self._on_new_game()
                return True
            if event.key in (pygame.K_ESCAPE, pygame.K_n):
                self._on_menu()
                return True
            return True
        if event.type == pygame.VIDEORESIZE:
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
        pygame.draw.rect(surface, (246, 248, 250), panel, border_radius=18)
        pygame.draw.rect(surface, (70, 70, 80), panel, width=2, border_radius=18)

        title_font = C.FONT_TITLE or pygame.font.SysFont(pygame.font.get_default_font(), 40, bold=True)
        title_surf = title_font.render("You Won!", True, (30, 30, 45))
        surface.blit(title_surf, (panel.centerx - title_surf.get_width() // 2, panel.top + 28))

        msg_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26)
        message = "Congratulations on completing La Duchesse de Luynes!"
        msg_surf = msg_font.render(message, True, (40, 40, 55))
        surface.blit(msg_surf, (panel.centerx - msg_surf.get_width() // 2, panel.top + 28 + title_surf.get_height() + 18))

        mouse_pos = pygame.mouse.get_pos()
        self._new_btn.draw(surface, hover=self._new_btn.hovered(mouse_pos))
        self._menu_btn.draw(surface, hover=self._menu_btn.hovered(mouse_pos))


class LaDuchesseDeLuynesGameScene(C.Scene):
    """Game scene for La Duchesse de Luynes."""

    FOUNDATION_ORDER = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs

    def __init__(self, app, load_state: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(app)
        self.ui_helper = ModeUIHelper(self, game_id="duchess_de_luynes")

        self.stock_pile = C.Pile(0, 0)
        self.reserve_pile = C.Pile(0, 0)
        self.tableau: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.top_foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.bottom_foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        for pile in (*self.tableau, *self.top_foundations, *self.bottom_foundations, self.reserve_pile):
            pile.fan_x = 0
            pile.fan_y = 0

        self.anim = M.CardAnimator()
        self._animation_queue: Deque[
            Tuple[C.Card, Tuple[int, int], Tuple[int, int], Optional[Callable[[], None]], bool, int]
        ] = deque()
        self.undo_mgr = C.UndoManager()
        self._pending_post_deal: bool = False
        self.drag_state: Optional[_DragState] = None
        self._drag_pos: Tuple[int, int] = (0, 0)
        self._last_click_time: int = 0
        self._last_click_pos: Tuple[int, int] = (0, 0)
        self._highlight_targets: List[Tuple[str, int]] = []
        self._highlight_until: int = 0
        self._stock_highlight: bool = False
        self._hint_sources: List[Tuple[str, int]] = []
        self._hint_targets: List[Tuple[str, int]] = []
        self._hint_until: int = 0
        self._hint_stock: bool = False

        self.end_modal = _EndGameModal(self.deal_new_game, self.ui_helper.goto_menu)

        def can_undo() -> bool:
            return self.undo_mgr.can_undo() and not (self.anim.active or self._animation_queue)

        def can_hint() -> bool:
            return self._can_show_hint()

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new_game},
            restart_action={"on_click": self.restart_current_deal},
            undo_action={
                "on_click": self.undo,
                "enabled": can_undo,
                "tooltip": "Undo last move",
            },
            hint_action={
                "on_click": self.show_hint,
                "enabled": can_hint,
                "tooltip": "Highlight a possible move",
            },
            save_action=(
                "Save&Exit",
                {"on_click": lambda: self._save_game(to_menu=True), "tooltip": "Save game and return to menu"},
            ),
            menu_tooltip="Game menu",
        )

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal_new_game()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------
    def compute_layout(self) -> None:
        top_bar = getattr(C, "TOP_BAR_H", 60)
        padding_y = 24
        foundation_gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        row_gap_y = getattr(C, "CARD_GAP_Y", max(28, C.CARD_H // 4))

        total_foundation_width = 4 * C.CARD_W + 3 * foundation_gap_x
        left_x = C.SCREEN_W // 2 - total_foundation_width // 2

        # Top foundations
        top_y = top_bar + padding_y
        for idx, pile in enumerate(self.top_foundations):
            pile.x = left_x + idx * (C.CARD_W + foundation_gap_x)
            pile.y = top_y

        tableau_y = top_y + C.CARD_H + row_gap_y
        for idx, pile in enumerate(self.tableau):
            pile.x = left_x + idx * (C.CARD_W + foundation_gap_x)
            pile.y = tableau_y

        # Stock to the left, reserve to the right of tableau
        stock_gap = max(foundation_gap_x, 24)
        self.stock_pile.x = left_x - stock_gap - C.CARD_W
        self.stock_pile.y = tableau_y

        self.reserve_pile.x = left_x + 4 * (C.CARD_W + foundation_gap_x) + stock_gap
        self.reserve_pile.y = tableau_y

        self._reserve_label_pos = (self.reserve_pile.x + C.CARD_W // 2, self.reserve_pile.y - 28)

        bottom_y = tableau_y + C.CARD_H + row_gap_y
        for idx, pile in enumerate(self.bottom_foundations):
            pile.x = left_x + idx * (C.CARD_W + foundation_gap_x)
            pile.y = bottom_y

        if self.toolbar:
            # The shared toolbar exposes a ``relayout`` helper (matching other
            # modes such as Monte Carlo). The previous call to ``reflow`` was a
            # typo which caused an ``AttributeError`` when the scene initialised
            # via the menu options controller.
            self.toolbar.relayout()

    # ------------------------------------------------------------------
    # Game setup & persistence
    # ------------------------------------------------------------------
    def deal_new_game(self) -> None:
        delete_saved_game()
        self.undo_mgr = C.UndoManager()
        self._clear_hint()
        self._highlight_targets = []
        self._highlight_until = 0
        self._stock_highlight = False
        self._clear_all_piles()
        deck = _deck_two_decks()
        self.stock_pile.cards = deck
        self._deal_initial_layout()

    def restart_current_deal(self) -> None:
        # Restart behaves as a new shuffle for now.
        self.deal_new_game()

    def _deal_initial_layout(self) -> None:
        self._pending_post_deal = False
        dealt_tableau = False
        for pile in self.tableau:
            if not self.stock_pile.cards:
                break
            if self._deal_card_to_tableau(pile):
                dealt_tableau = True
        for _ in range(2):
            stock_entry = self._pop_stock_card()
            if not stock_entry:
                break
            card, _ = stock_entry
            card.face_up = False
            self.reserve_pile.cards.append(card)
        if dealt_tableau:
            self._pending_post_deal = True
        else:
            self._update_move_state()
            self._save_game()

    def _deal_round_from_stock(self) -> bool:
        if self.anim.active or self._animation_queue:
            return False
        self._pending_post_deal = False
        dealt_tableau = False
        dealt_any = False
        undo_pushed = False
        for pile in self.tableau:
            if not self.stock_pile.cards:
                break
            if not undo_pushed:
                self.push_undo()
                self._clear_hint()
                undo_pushed = True
            if self._deal_card_to_tableau(pile):
                dealt_tableau = True
                dealt_any = True
        for _ in range(2):
            if not self.stock_pile.cards:
                break
            if not undo_pushed:
                self.push_undo()
                self._clear_hint()
                undo_pushed = True
            stock_entry = self._pop_stock_card()
            if not stock_entry:
                break
            card, _ = stock_entry
            card.face_up = False
            self.reserve_pile.cards.append(card)
            dealt_any = True
        if dealt_tableau:
            self._pending_post_deal = True
            return True
        if dealt_any:
            self._save_game()
            self._update_move_state()
            return True
        self._update_move_state()
        return False

    def _clear_all_piles(self) -> None:
        for pile in (
            [self.stock_pile, self.reserve_pile]
            + self.tableau
            + self.top_foundations
            + self.bottom_foundations
        ):
            pile.cards = []
        self.anim.cancel()
        self._animation_queue.clear()
        self._pending_post_deal = False
        self.drag_state = None
        self._clear_hint()
        self._highlight_targets = []
        self._highlight_until = 0
        self.end_modal.close()

    def _save_game(self, *, to_menu: bool = False) -> None:
        state = {
            "stock": _serialise_cards(self.stock_pile.cards),
            "reserve": _serialise_cards(self.reserve_pile.cards),
            "tableau": [_serialise_cards(p.cards) for p in self.tableau],
            "foundations_top": [_serialise_cards(p.cards) for p in self.top_foundations],
            "foundations_bottom": [_serialise_cards(p.cards) for p in self.bottom_foundations],
            "completed": self._is_completed(),
        }
        _safe_write_json(_save_path(), state)
        if to_menu:
            self.ui_helper.goto_menu()

    def _load_from_state(self, state: Dict[str, Any]) -> None:
        self._clear_all_piles()
        self.stock_pile.cards = _deserialise_cards(state.get("stock", []))
        self.reserve_pile.cards = _deserialise_cards(state.get("reserve", []))
        tableau_states = state.get("tableau", [])
        for idx, pile in enumerate(self.tableau):
            cards = tableau_states[idx] if idx < len(tableau_states) else []
            pile.cards = _deserialise_cards(cards)
        top_states = state.get("foundations_top", [])
        for idx, pile in enumerate(self.top_foundations):
            cards = top_states[idx] if idx < len(top_states) else []
            pile.cards = _deserialise_cards(cards)
        bottom_states = state.get("foundations_bottom", [])
        for idx, pile in enumerate(self.bottom_foundations):
            cards = bottom_states[idx] if idx < len(bottom_states) else []
            pile.cards = _deserialise_cards(cards)
        if state.get("completed") and self._is_completed():
            self.end_modal.open()
        self._update_move_state()

    # ------------------------------------------------------------------
    # Undo & hint helpers
    # ------------------------------------------------------------------
    def _record_snapshot(self) -> Dict[str, Any]:
        return {
            "stock": _serialise_cards(self.stock_pile.cards),
            "reserve": _serialise_cards(self.reserve_pile.cards),
            "tableau": [_serialise_cards(p.cards) for p in self.tableau],
            "foundations_top": [_serialise_cards(p.cards) for p in self.top_foundations],
            "foundations_bottom": [_serialise_cards(p.cards) for p in self.bottom_foundations],
            "completed": self._is_completed(),
        }

    def _restore_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self.anim.cancel()
        self._animation_queue.clear()
        self.drag_state = None
        self._clear_hint()
        self._highlight_targets = []
        self._highlight_until = 0
        self._pending_post_deal = False

        self.stock_pile.cards = _deserialise_cards(snapshot.get("stock", []))
        self.reserve_pile.cards = _deserialise_cards(snapshot.get("reserve", []))

        tableau_states = snapshot.get("tableau", [])
        for idx, pile in enumerate(self.tableau):
            cards = tableau_states[idx] if idx < len(tableau_states) else []
            pile.cards = _deserialise_cards(cards)

        top_states = snapshot.get("foundations_top", [])
        for idx, pile in enumerate(self.top_foundations):
            cards = top_states[idx] if idx < len(top_states) else []
            pile.cards = _deserialise_cards(cards)

        bottom_states = snapshot.get("foundations_bottom", [])
        for idx, pile in enumerate(self.bottom_foundations):
            cards = bottom_states[idx] if idx < len(bottom_states) else []
            pile.cards = _deserialise_cards(cards)

        self.end_modal.close()
        if snapshot.get("completed") and self._is_completed():
            self.end_modal.open()

        self._update_move_state()
        self._save_game()

    def push_undo(self, snapshot: Optional[Dict[str, Any]] = None) -> None:
        snap = snapshot if snapshot is not None else self._record_snapshot()
        self.undo_mgr.push(lambda snap=snap: self._restore_snapshot(snap))

    def undo(self) -> None:
        if not self.undo_mgr.can_undo() or self.anim.active or self._animation_queue:
            return
        self.anim.cancel()
        self._animation_queue.clear()
        self.drag_state = None
        self._clear_hint()
        self._highlight_targets = []
        self._highlight_until = 0
        self.undo_mgr.undo()

    def _clear_hint(self) -> None:
        self._hint_sources = []
        self._hint_targets = []
        self._hint_until = 0
        self._hint_stock = False

    def _compute_hint(self) -> Optional[Tuple[List[Tuple[str, int]], List[Tuple[str, int]], bool]]:
        if self.anim.active or self._animation_queue:
            return None
        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            card = pile.cards[-1]
            if not card.face_up:
                continue
            eligible = self._eligible_foundations(card)
            if eligible:
                return ([("tableau", idx)], eligible, False)
        if self.stock_pile.cards:
            return ([], [], True)
        return None

    def _can_show_hint(self) -> bool:
        return self._compute_hint() is not None

    def show_hint(self) -> None:
        hint = self._compute_hint()
        self._clear_hint()
        if not hint:
            return
        sources, targets, stock_flag = hint
        now = pygame.time.get_ticks()
        if stock_flag and self.stock_pile.cards:
            self._hint_stock = True
            self._hint_until = now + 2200
            return
        if not targets:
            return
        self._hint_sources = sources
        self._hint_targets = targets
        self._hint_until = now + 2200


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _enqueue_animation(
        self,
        card: C.Card,
        from_xy: Tuple[int, int],
        to_xy: Tuple[int, int],
        on_complete: Optional[Callable[[], None]] = None,
        *,
        flip_mid: bool = False,
        duration: int = 260,
    ) -> None:
        self._animation_queue.append((card, from_xy, to_xy, on_complete, flip_mid, duration))
        if not self.anim.active:
            self._start_next_animation()

    def _start_next_animation(self) -> None:
        if self.anim.active:
            return
        if not self._animation_queue:
            self._on_animation_queue_empty()
            return
        card, from_xy, to_xy, callback, flip_mid, duration = self._animation_queue.popleft()

        def _finish(cb: Optional[Callable[[], None]] = callback) -> None:
            if cb:
                try:
                    cb()
                except Exception:
                    pass
            self._start_next_animation()

        self.anim.start_move(
            card,
            from_xy,
            to_xy,
            dur_ms=duration,
            on_complete=_finish,
            flip_mid=flip_mid,
        )

    def _on_animation_queue_empty(self) -> None:
        if self._pending_post_deal:
            self._handle_post_deal_actions()

    def _handle_post_deal_actions(self) -> None:
        self._pending_post_deal = False
        if self._queue_auto_foundation_moves():
            self._pending_post_deal = True
            return
        self._update_move_state()
        self._save_game()

    def _queue_auto_foundation_moves(self) -> bool:
        moves: List[Tuple[C.Pile, C.Pile]] = []
        moved_top_suits: Set[int] = set()
        moved_bottom_suits: Set[int] = set()
        for pile in self.tableau:
            if not pile.cards:
                continue
            card = pile.cards[-1]
            if card.rank == 13:
                dest = self.top_foundations[card.suit]
                if not dest.cards and card.suit not in moved_top_suits:
                    moves.append((pile, dest))
                    moved_top_suits.add(card.suit)
            elif card.rank == 1:
                dest = self.bottom_foundations[card.suit]
                if not dest.cards and card.suit not in moved_bottom_suits:
                    moves.append((pile, dest))
                    moved_bottom_suits.add(card.suit)
        if moves:
            self.push_undo()
            self._clear_hint()
        for source, dest in moves:
            if not source.cards:
                continue
            top_index = len(source.cards) - 1
            rect = source.rect_for_index(top_index)
            card = source.cards.pop()

            def _complete(card_ref: C.Card = card, dest_pile: C.Pile = dest) -> None:
                dest_pile.cards.append(card_ref)

            self._enqueue_animation(card, (rect.x, rect.y), (dest.x, dest.y), _complete)
        return bool(moves)

    def _pop_stock_card(self) -> Optional[Tuple[C.Card, Tuple[int, int]]]:
        if not self.stock_pile.cards:
            return None
        index = len(self.stock_pile.cards) - 1
        rect = self.stock_pile.rect_for_index(index)
        card = self.stock_pile.cards.pop()
        return card, (rect.x, rect.y)

    def _deal_card_to_tableau(self, pile: C.Pile) -> bool:
        stock_entry = self._pop_stock_card()
        if not stock_entry:
            return False
        card, from_xy = stock_entry
        card.face_up = True

        def _complete(card_ref: C.Card = card, dest_pile: C.Pile = pile) -> None:
            dest_pile.cards.append(card_ref)

        self._enqueue_animation(card, from_xy, (pile.x, pile.y), _complete)
        return True

    def _eligible_foundations(self, card: C.Card) -> List[Tuple[str, int]]:
        results: List[Tuple[str, int]] = []
        idx = card.suit
        top_pile = self.top_foundations[idx]
        if not top_pile.cards:
            if card.rank == 13:
                results.append(("top", idx))
        else:
            top_rank = top_pile.cards[-1].rank
            if top_rank - 1 == card.rank:
                results.append(("top", idx))
        bottom_pile = self.bottom_foundations[idx]
        if not bottom_pile.cards:
            if card.rank == 1:
                results.append(("bottom", idx))
        else:
            bottom_rank = bottom_pile.cards[-1].rank
            if bottom_rank + 1 == card.rank:
                results.append(("bottom", idx))
        return results

    def _is_completed(self) -> bool:
        return all(len(p.cards) == 13 for p in self.top_foundations + self.bottom_foundations)

    def _update_move_state(self) -> None:
        moves_available = False
        for pile in self.tableau:
            if not pile.cards:
                continue
            card = pile.cards[-1]
            if not card.face_up:
                continue
            if self._eligible_foundations(card):
                moves_available = True
                break
        self._stock_highlight = not moves_available and bool(self.stock_pile.cards)
        if not self._stock_highlight and not self.stock_pile.cards:
            self._stock_highlight = False
        if self._is_completed():
            self._on_game_won()

    def _on_game_won(self) -> None:
        self.end_modal.open()
        state = {
            "stock": _serialise_cards(self.stock_pile.cards),
            "reserve": _serialise_cards(self.reserve_pile.cards),
            "tableau": [_serialise_cards(p.cards) for p in self.tableau],
            "foundations_top": [_serialise_cards(p.cards) for p in self.top_foundations],
            "foundations_bottom": [_serialise_cards(p.cards) for p in self.bottom_foundations],
            "completed": True,
        }
        _safe_write_json(_save_path(), state)

    def _card_from_tableau_at_pos(self, pos: Tuple[int, int]) -> Optional[Tuple[int, C.Card]]:
        mx, my = pos
        for idx, pile in enumerate(self.tableau):
            hit = pile.hit((mx, my))
            if hit is None or hit == -1:
                continue
            if hit == len(pile.cards) - 1:
                card = pile.cards[-1]
                if card.face_up:
                    return idx, card
        return None

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.end_modal.visible:
            if self.end_modal.handle_event(event):
                return

        if self.ui_helper.handle_menu_event(event):
            return
        if self.toolbar and self.toolbar.handle_event(event):
            return

        if event.type == pygame.VIDEORESIZE:
            self.compute_layout()
            self.ui_helper.relayout_menu_modal()
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._maybe_handle_double_click(event):
                return
            self._last_click_time = pygame.time.get_ticks()
            self._last_click_pos = event.pos
            if self._handle_stock_click(event.pos):
                return
            if self._start_drag(event.pos):
                return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.drag_state:
                self._finish_drag(event.pos)

        if event.type == pygame.MOUSEMOTION and self.drag_state:
            self._drag_pos = event.pos

    def _maybe_handle_double_click(self, event: pygame.event.Event) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - self._last_click_time <= 350
            and abs(event.pos[0] - self._last_click_pos[0]) <= 6
            and abs(event.pos[1] - self._last_click_pos[1]) <= 6
        )
        if not double:
            return False
        self._last_click_time = now
        self._last_click_pos = event.pos
        if self.anim.active:
            return True
        card_info = self._card_from_tableau_at_pos(event.pos)
        if not card_info:
            return False
        tableau_index, card = card_info
        eligible = self._eligible_foundations(card)
        if not eligible:
            return True
        if len(eligible) > 1:
            self._highlight_targets = eligible
            self._highlight_until = now + 2000
            return True

        dest_type, dest_index = eligible[0]
        pile = self.tableau[tableau_index]
        if not pile.cards:
            return True
        source_rect = pile.rect_for_index(len(pile.cards) - 1)
        self.push_undo()
        self._clear_hint()
        card_to_move = pile.cards.pop()

        dest_pile = self.top_foundations[dest_index] if dest_type == "top" else self.bottom_foundations[dest_index]

        def _on_complete(ci=card_to_move, dp=dest_pile):
            dp.cards.append(ci)
            self._update_move_state()
            self._save_game()

        self.anim.start_move(
            card_to_move,
            (source_rect.x, source_rect.y),
            (dest_pile.x, dest_pile.y),
            dur_ms=260,
            on_complete=_on_complete,
            flip_mid=False,
        )
        return True

    def _handle_stock_click(self, pos: Tuple[int, int]) -> bool:
        rect = pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H)
        if rect.collidepoint(pos):
            if self.stock_pile.cards:
                dealt = self._deal_round_from_stock()
            else:
                dealt = False
            if dealt or not self.stock_pile.cards:
                self._stock_highlight = False
            return True
        return False

    def _start_drag(self, pos: Tuple[int, int]) -> bool:
        if self.anim.active:
            return False
        mx, my = pos
        for idx, pile in enumerate(self.tableau):
            hit = pile.hit((mx, my))
            if hit is None or hit == -1:
                continue
            if hit != len(pile.cards) - 1:
                continue
            snapshot = self._record_snapshot()
            card = pile.cards.pop()
            if not card.face_up:
                pile.cards.append(card)
                continue
            rect = pile.rect_for_index(len(pile.cards)) if pile.cards else pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            offset = (mx - rect.x, my - rect.y)
            self.drag_state = _DragState(card=card, origin=("tableau", idx), offset=offset, snapshot=snapshot)
            self._drag_pos = pos
            return True
        return False

    def _finish_drag(self, pos: Tuple[int, int]) -> None:
        drag = self.drag_state
        self.drag_state = None
        if not drag:
            return
        card = drag.card
        eligible = self._eligible_foundations(card)
        destination = None
        drop_rect = pygame.Rect(pos[0] - drag.offset[0], pos[1] - drag.offset[1], C.CARD_W, C.CARD_H)
        for dest_type, dest_index in eligible:
            pile = self.top_foundations[dest_index] if dest_type == "top" else self.bottom_foundations[dest_index]
            area = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            if area.colliderect(drop_rect):
                destination = (dest_type, dest_index)
                break
        origin_type, origin_index = drag.origin
        if destination is None:
            self._return_to_origin(card, origin_type, origin_index)
            return
        dest_type, dest_index = destination
        dest_pile = self.top_foundations[dest_index] if dest_type == "top" else self.bottom_foundations[dest_index]
        self.push_undo(drag.snapshot)
        self._clear_hint()
        dest_pile.cards.append(card)
        self._update_move_state()
        self._save_game()

    def _return_to_origin(self, card: C.Card, origin_type: str, origin_index: int) -> None:
        if origin_type == "tableau":
            self.tableau[origin_index].cards.append(card)

    # ------------------------------------------------------------------
    # Update & draw
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        now = pygame.time.get_ticks()
        if self._highlight_targets and now >= self._highlight_until:
            self._highlight_targets = []
            self._highlight_until = 0
        if self._hint_until and now >= self._hint_until:
            self._clear_hint()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(C.TABLE_BG)

        for pile in self.top_foundations + self.bottom_foundations + self.tableau + [self.stock_pile, self.reserve_pile]:
            pile.draw(surface)

        self._draw_foundation_placeholders(surface)

        self._draw_labels(surface)
        self._draw_highlights(surface)

        if self.drag_state:
            card = self.drag_state.card
            surf = C.get_card_surface(card)
            draw_pos = (self._drag_pos[0] - self.drag_state.offset[0], self._drag_pos[1] - self.drag_state.offset[1])
            surface.blit(surf, draw_pos)

        self.anim.draw(surface)

        C.Scene.draw_top_bar(self, surface, "La Duchesse de Luynes")
        if self.toolbar:
            self.toolbar.draw(surface)

        self.ui_helper.draw_menu_modal(surface)

        self.end_modal.draw(surface)

    def _draw_foundation_placeholders(self, surface: pygame.Surface) -> None:
        corner_font = C.FONT_CORNER_RANK or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        suit_font = C.FONT_CENTER_SUIT or pygame.font.SysFont(pygame.font.get_default_font(), 64)
        color = (245, 245, 250)
        pad_x = max(6, C.CARD_W // 12)
        pad_y = max(6, C.CARD_H // 12)

        def draw_corner_markers(pile: C.Pile, text: str) -> None:
            if pile.cards:
                return
            marker = corner_font.render(text, True, color)
            surface.blit(marker, (pile.x + pad_x, pile.y + pad_y))
            surface.blit(
                marker,
                (
                    pile.x + C.CARD_W - marker.get_width() - pad_x,
                    pile.y + C.CARD_H - marker.get_height() - pad_y,
                ),
            )

        def draw_suit_symbol(pile: C.Pile, suit_index: int) -> None:
            if pile.cards:
                return
            suit_char = C.SUITS[suit_index]
            suit_surface = suit_font.render(suit_char, True, color)
            surface.blit(
                suit_surface,
                (
                    pile.x + C.CARD_W // 2 - suit_surface.get_width() // 2,
                    pile.y + C.CARD_H // 2 - suit_surface.get_height() // 2,
                ),
            )

        for idx, pile in enumerate(self.top_foundations):
            draw_suit_symbol(pile, self.FOUNDATION_ORDER[idx])
            draw_corner_markers(pile, "K")
        for idx, pile in enumerate(self.bottom_foundations):
            draw_suit_symbol(pile, self.FOUNDATION_ORDER[idx])
            draw_corner_markers(pile, "A")

    def _draw_labels(self, surface: pygame.Surface) -> None:
        label_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        reserve_surf = label_font.render("Reserve", True, C.WHITE)
        surface.blit(reserve_surf, (self._reserve_label_pos[0] - reserve_surf.get_width() // 2, self._reserve_label_pos[1]))

    def _draw_highlights(self, surface: pygame.Surface) -> None:
        if self._stock_highlight and self.stock_pile.cards:
            rect = pygame.Rect(self.stock_pile.x - 4, self.stock_pile.y - 4, C.CARD_W + 8, C.CARD_H + 8)
            pygame.draw.rect(surface, (255, 215, 0), rect, width=4, border_radius=C.CARD_RADIUS)

        if self._hint_stock and self.stock_pile.cards and self._hint_until and pygame.time.get_ticks() <= self._hint_until:
            rect = pygame.Rect(self.stock_pile.x - 4, self.stock_pile.y - 4, C.CARD_W + 8, C.CARD_H + 8)
            pygame.draw.rect(surface, (120, 200, 255), rect, width=4, border_radius=C.CARD_RADIUS)

        if self._highlight_targets and pygame.time.get_ticks() <= self._highlight_until:
            color = (255, 230, 90)
            for dest_type, dest_index in self._highlight_targets:
                pile = self.top_foundations[dest_index] if dest_type == "top" else self.bottom_foundations[dest_index]
                rect = pygame.Rect(pile.x - 4, pile.y - 4, C.CARD_W + 8, C.CARD_H + 8)
                pygame.draw.rect(surface, color, rect, width=4, border_radius=C.CARD_RADIUS)

        if self._hint_targets and self._hint_until and pygame.time.get_ticks() <= self._hint_until:
            hint_color = (120, 200, 255)
            for dest_type, dest_index in self._hint_targets:
                pile = self.top_foundations[dest_index] if dest_type == "top" else self.bottom_foundations[dest_index]
                rect = pygame.Rect(pile.x - 4, pile.y - 4, C.CARD_W + 8, C.CARD_H + 8)
                pygame.draw.rect(surface, hint_color, rect, width=4, border_radius=C.CARD_RADIUS)

        if self._hint_sources and self._hint_until and pygame.time.get_ticks() <= self._hint_until:
            hint_color = (120, 200, 255)
            for origin_type, origin_index in self._hint_sources:
                rect: Optional[pygame.Rect] = None
                if origin_type == "tableau":
                    pile = self.tableau[origin_index]
                    if pile.cards:
                        rect = pile.rect_for_index(len(pile.cards) - 1)
                elif origin_type == "reserve":
                    rect = pygame.Rect(self.reserve_pile.x, self.reserve_pile.y, C.CARD_W, C.CARD_H)
                if rect is None:
                    continue
                inflated = pygame.Rect(rect.x - 4, rect.y - 4, rect.width + 8, rect.height + 8)
                pygame.draw.rect(surface, hint_color, inflated, width=4, border_radius=C.CARD_RADIUS)

