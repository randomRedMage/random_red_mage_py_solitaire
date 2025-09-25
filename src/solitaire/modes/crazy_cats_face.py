"""Crazy Cat's Face mode implementation."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple, Union

import pygame

from solitaire import common as C
from solitaire.help_data import create_modal_help
from solitaire.modes.base_scene import ModeUIHelper

CardLike = Union[C.Card, "JokerCard"]


class JokerCard:
    """Simple representation for joker cards used in the tableau."""

    __slots__ = ("color", "face_up")

    def __init__(self, color: str) -> None:
        self.color = color.lower()
        self.face_up: bool = False

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Joker({self.color}){'↑' if self.face_up else '↓'}"


@dataclass
class FaceCardSlot:
    card: CardLike
    center: Tuple[int, int]
    angle: int = 0
    face_up: bool = False

    def __post_init__(self) -> None:
        self.update_rect()

    def update_rect(self) -> None:
        width, height = C.CARD_W, C.CARD_H
        if self.angle % 180 != 0:
            width, height = height, width
        rect = pygame.Rect(0, 0, width, height)
        rect.center = self.center
        self.rect = rect


_STOCK_SPECS: Tuple[Tuple[int, int], ...] = (
    (0, 1),
    (1, 1),
    (0, 2),
    (1, 2),
    (0, 3),
    (1, 3),
    (0, 4),
    (1, 4),
)

_FACE_SPECS: Tuple[CardLike, ...] = (
    C.Card(2, 13, False),
    C.Card(3, 13, False),
    C.Card(2, 12, False),
    C.Card(3, 12, False),
    C.Card(2, 10, False),
    C.Card(3, 10, False),
    JokerCard("red"),
    JokerCard("black"),
)

_JOKER_CACHE: dict[Tuple[str, Tuple[int, int]], pygame.Surface] = {}


def _load_joker_surface(color: str) -> pygame.Surface:
    """Return a cached surface for the requested joker colour."""

    size = (C.CARD_W, C.CARD_H)
    key = (color, size)
    cached = _JOKER_CACHE.get(key)
    if cached is not None:
        return cached

    filename = f"Joker {'Red' if color == 'red' else 'Black'}.png"
    path = os.path.join(C.IMAGE_CARDS_DIR, filename)
    surface: pygame.Surface | None = None
    try:
        if os.path.isfile(path):
            loaded = pygame.image.load(path)
            surface = loaded.convert_alpha() if loaded.get_alpha() else loaded.convert()
            if surface.get_size() != size:
                surface = pygame.transform.smoothscale(surface, size)
    except Exception:
        surface = None

    if surface is None:
        surface = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.rect(surface, C.WHITE, (0, 0, *size), border_radius=C.CARD_RADIUS)
        pygame.draw.rect(surface, C.BLACK, (0, 0, *size), width=2, border_radius=C.CARD_RADIUS)
        label = C.FONT_UI.render("Joker", True, C.BLACK) if C.FONT_UI else None
        if label is not None:
            surface.blit(label, (size[0] // 2 - label.get_width() // 2, size[1] // 2 - label.get_height() // 2))

    _JOKER_CACHE[key] = surface
    return surface


def _build_stock(shuffle: bool = True) -> List[C.Card]:
    cards = [C.Card(suit, rank, False) for suit, rank in _STOCK_SPECS]
    if shuffle:
        random.shuffle(cards)
    return cards


def _build_face_cards(shuffle: bool = True) -> List[CardLike]:
    cards = [
        C.Card(card.suit, card.rank, False) if isinstance(card, C.Card) else JokerCard(card.color)
        for card in _FACE_SPECS
    ]
    if shuffle:
        random.shuffle(cards)
    return cards


class CrazyCatsFaceScene(C.Scene):
    """Game scene for Crazy Cat's Face."""

    def __init__(self, app):
        super().__init__(app)
        self.ui_helper = ModeUIHelper(self, game_id="crazy_cats_face")
        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.start_new_game, "tooltip": "Shuffle and redeal Crazy Cat's Face"},
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        )
        self.help = create_modal_help("crazy_cats_face")

        stock_x = 120
        stock_y = C.TOP_BAR_H + 120
        self.stock_pile = C.Pile(stock_x, stock_y)
        self.waste_pile = C.Pile(stock_x, stock_y + C.CARD_H + 24)

        self.face_slots: List[FaceCardSlot] = []
        self.pending_flips: int = 0
        self.pending_note: str = ""
        self.waste_total: int = 0
        self.jokers_flipped: int = 0
        self.game_over: bool = False
        self.message: str = ""

        self.start_new_game()

    # ------------------------------------------------------------------
    def start_new_game(self) -> None:
        self.stock_pile.cards = _build_stock(shuffle=True)
        for card in self.stock_pile.cards:
            card.face_up = False
        self.waste_pile.cards = []

        face_cards = _build_face_cards(shuffle=True)
        self.face_slots = self._deal_face_cards(face_cards)
        self.pending_flips = 0
        self.pending_note = "Click the stock to draw a card."
        self.waste_total = 0
        self.jokers_flipped = 0
        self.game_over = False
        self.message = ""

    def _deal_face_cards(self, cards: Sequence[CardLike]) -> List[FaceCardSlot]:
        layout = self._tableau_layout()
        slots: List[FaceCardSlot] = []
        for idx, ((cx, cy), angle) in enumerate(layout):
            card = cards[idx]
            if isinstance(card, C.Card):
                card.face_up = False
            else:
                card.face_up = False
            slot = FaceCardSlot(card=card, center=(int(cx), int(cy)), angle=angle, face_up=False)
            slots.append(slot)
        return slots

    def _tableau_layout(self) -> List[Tuple[Tuple[float, float], int]]:
        center_x = C.SCREEN_W // 2
        column_gap = C.CARD_W + max(40, C.CARD_W // 2)
        inner_gap = column_gap / 2
        vertical_gap = max(32, C.CARD_H // 5)
        top_y = C.TOP_BAR_H + 160

        left_x = center_x - column_gap
        mid_x = center_x
        right_x = center_x + column_gap
        inner_left_x = center_x - inner_gap
        inner_right_x = center_x + inner_gap

        rows: List[Tuple[Tuple[float, float], int]] = []

        top_center_y = top_y + C.CARD_H / 2
        rows.append(((left_x, top_center_y), 0))
        rows.append(((mid_x, top_center_y), 0))
        rows.append(((right_x, top_center_y), 0))

        second_row_y = top_center_y + C.CARD_H + vertical_gap
        rows.append(((inner_left_x, second_row_y), 0))
        rows.append(((inner_right_x, second_row_y), 0))

        third_row_y = second_row_y + C.CARD_H + vertical_gap
        rows.append(((left_x, third_row_y), 0))
        rows.append(((right_x, third_row_y), 0))

        chin_y = third_row_y + C.CARD_H + vertical_gap
        rows.append(((mid_x, chin_y), 0))

        return rows

    # ------------------------------------------------------------------
    def _remaining_face_down(self) -> int:
        return sum(1 for slot in self.face_slots if not slot.face_up)

    def _current_score(self) -> int:
        return self.waste_total - self.jokers_flipped * 2

    def _draw_stock_card(self) -> None:
        if self.game_over:
            return
        if self.pending_flips > 0:
            self.message = "Flip the required cards before drawing again."
            return
        if not self.stock_pile.cards:
            self.message = "The stock is empty."
            return

        card = self.stock_pile.cards.pop()
        card.face_up = True
        self.waste_pile.cards.append(card)
        self.waste_total += card.rank

        self.pending_flips = 0
        suit = card.suit
        rank = card.rank
        if suit == 0:  # Spades
            needed = rank % 2
            if needed <= 0:
                self.pending_note = f"Spade {C.RANK_TO_TEXT[rank]}: no flips required."
            else:
                available = self._remaining_face_down()
                flips = min(needed, available)
                if flips <= 0:
                    self.pending_note = "No tableau cards remain to flip."
                else:
                    self.pending_flips = flips
                    if flips < needed:
                        self.pending_note = (
                            f"Spade {C.RANK_TO_TEXT[rank]}: flip {flips} card"
                            f"{'s' if flips != 1 else ''} (only {available} hidden)."
                        )
                    else:
                        self.pending_note = f"Spade {C.RANK_TO_TEXT[rank]}: flip {flips} card{'s' if flips != 1 else ''}."
        elif suit == 1:  # Hearts
            needed = rank
            available = self._remaining_face_down()
            flips = min(needed, available)
            if flips <= 0:
                self.pending_note = "No tableau cards remain to flip."
            else:
                self.pending_flips = flips
                if flips < needed:
                    self.pending_note = (
                        f"Heart {C.RANK_TO_TEXT[rank]}: flip {flips} card"
                        f"{'s' if flips != 1 else ''} (only {available} hidden)."
                    )
                else:
                    self.pending_note = f"Heart {C.RANK_TO_TEXT[rank]}: flip {flips} card{'s' if flips != 1 else ''}."
        else:
            self.pending_note = "Drawn card has no effect."

        self.message = ""
        if self.pending_flips == 0 and self._remaining_face_down() == 0:
            self._finish_game()

    def _flip_slot(self, slot: FaceCardSlot) -> None:
        if self.game_over:
            return
        if slot.face_up:
            return
        if self.pending_flips <= 0:
            self.message = "Draw a card to reveal more of the face."
            return

        slot.face_up = True
        if isinstance(slot.card, C.Card):
            slot.card.face_up = True
        else:
            slot.card.face_up = True
            self.jokers_flipped += 1
        self.pending_flips = max(0, self.pending_flips - 1)

        if self._remaining_face_down() == 0:
            self.pending_flips = 0
            self._finish_game()
            return

        if self.pending_flips == 0:
            self.pending_note = "All required cards flipped."
            self.message = "All required cards flipped. Draw again!"

    def _finish_game(self) -> None:
        self.game_over = True
        score = self._current_score()
        self.message = f"All cards revealed! Final score: {score}."
        self.pending_note = f"Final score: {score}"

    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(event):
                return
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return

        if self.toolbar.handle_event(event):
            return
        if self.ui_helper.handle_shortcuts(event):
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            stock_rect = self.stock_pile.top_rect()
            if stock_rect.collidepoint(pos):
                self._draw_stock_card()
                return
            for slot in self.face_slots:
                if slot.rect.collidepoint(pos):
                    self._flip_slot(slot)
                    return

    def update(self, dt) -> None:
        pass

    # ------------------------------------------------------------------
    def _draw_pile(self, screen: pygame.Surface, pile: C.Pile, label: str) -> None:
        pile.draw(screen)
        text = C.FONT_UI.render(label, True, C.WHITE) if C.FONT_UI else None
        if text is not None:
            rect = pile.top_rect()
            screen.blit(text, (rect.centerx - text.get_width() // 2, rect.top - text.get_height() - 8))

    def _draw_face_slots(self, screen: pygame.Surface) -> None:
        back = C.get_back_surface()
        for slot in self.face_slots:
            if slot.face_up:
                if isinstance(slot.card, C.Card):
                    surface = C.get_card_surface(slot.card)
                else:
                    surface = _load_joker_surface(slot.card.color)
            else:
                surface = back
            if slot.angle % 360 != 0:
                surface = pygame.transform.rotate(surface, slot.angle)
                rect = surface.get_rect(center=slot.rect.center)
            else:
                rect = slot.rect
            screen.blit(surface, rect.topleft)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(C.TABLE_BG)
        extra = f"Score: {self._current_score()}"
        if self.pending_flips > 0:
            extra += f"  |  Flips remaining: {self.pending_flips}"
        elif self.pending_note:
            extra += f"  |  {self.pending_note}"
        C.Scene.draw_top_bar(self, screen, "Crazy Cat's Face", extra)

        self.toolbar.draw(screen)

        self._draw_pile(screen, self.stock_pile, "Stock")
        self._draw_pile(screen, self.waste_pile, "Waste")
        self._draw_face_slots(screen)

        if self.message:
            msg = C.FONT_UI.render(self.message, True, C.WHITE) if C.FONT_UI else None
            if msg is not None:
                screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - msg.get_height() - 40))

        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
