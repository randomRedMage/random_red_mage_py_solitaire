import pygame
from typing import Callable, List, Optional, Tuple

from solitaire import common as C


class CardAnimator:
    """
    Simple single-card animation helper.
    Scenes remove the card from its source pile before starting. On completion,
    the provided callback is invoked (append to destination, chain logic, etc.).
    Supports optional mid-animation flip (draw back then front).
    """

    def __init__(self):
        self.active: bool = False
        self._card: Optional[C.Card] = None
        self._from: Tuple[int, int] = (0, 0)
        self._to: Tuple[int, int] = (0, 0)
        self._start_ms: int = 0
        self._dur_ms: int = 300
        self._on_complete: Optional[Callable[[], None]] = None
        self._flip_mid: bool = False
        self._flipped: bool = False

    def start_move(
        self,
        card: C.Card,
        from_xy: Tuple[int, int],
        to_xy: Tuple[int, int],
        dur_ms: int = 300,
        on_complete: Optional[Callable[[], None]] = None,
        flip_mid: bool = False,
    ):
        self._card = card
        self._from = from_xy
        self._to = to_xy
        self._start_ms = pygame.time.get_ticks()
        self._dur_ms = max(1, int(dur_ms))
        self._on_complete = on_complete
        self._flip_mid = bool(flip_mid)
        self._flipped = False
        self.active = True

    def cancel(self):
        self.active = False
        self._card = None
        self._on_complete = None
        self._flipped = False

    def draw(self, surface: pygame.Surface, scroll_x: int = 0, scroll_y: int = 0):
        if not self.active or self._card is None:
            return
        now = pygame.time.get_ticks()
        t = (now - self._start_ms) / float(self._dur_ms)
        if t >= 1.0:
            # Finish
            if self._flip_mid and not self._flipped:
                self._card.face_up = True
            cb = self._on_complete
            self.cancel()
            if cb:
                try:
                    cb()
                except Exception:
                    pass
            return
        # Interpolate
        sx, sy = self._from
        tx, ty = self._to
        x = int(sx + (tx - sx) * t)
        y = int(sy + (ty - sy) * t)
        if self._flip_mid:
            if t >= 0.5 and not self._flipped:
                self._card.face_up = True
                self._flipped = True
            if t < 0.5:
                back = C.get_back_surface()
                surface.blit(back, (x + scroll_x, y + scroll_y))
            else:
                surf = C.get_card_surface(self._card)
                surface.blit(surf, (x + scroll_x, y + scroll_y))
        else:
            surf = C.get_card_surface(self._card)
            surface.blit(surf, (x + scroll_x, y + scroll_y))


def auto_move_first_ace(
    sources: List[C.Pile],
    foundations: List[C.Pile],
    foundation_suits: List[int],
    animator: CardAnimator,
) -> bool:
    """
    Find the first pile whose top card is an exposed Ace; pop it and animate to its
    suit's foundation. Returns True if a move was started.
    """
    if animator.active:
        return False
    for src in sources:
        if not src.cards:
            continue
        top = src.cards[-1]
        if not top.face_up or top.rank != 1:
            continue
        try:
            fi = foundation_suits.index(top.suit)
        except ValueError:
            fi = 0
        # Pop and animate
        src.cards.pop()
        r = src.rect_for_index(len(src.cards)) if src.cards else pygame.Rect(src.x, src.y, C.CARD_W, C.CARD_H)
        from_xy = (r.x, r.y) if src.cards else (src.x, src.y)
        to_xy = (foundations[fi].x, foundations[fi].y)
        card_ref = top

        def _done():
            foundations[fi].cards.append(card_ref)

        animator.start_move(card_ref, from_xy, to_xy, dur_ms=260, on_complete=_done, flip_mid=False)
        return True
    return False


def build_hover_overlay(pile: C.Pile, hover_index: int):
    """Return (overlay_list, mask_rect) for a hover peek starting at hover_index.
    overlay_list is a list of (card, x, y) tuples for cards hover_index..top.
    mask_rect is the rect to cover area above the hover card in the pile.
    """
    if hover_index < 0 or hover_index >= len(pile.cards):
        return [], None
    overlay = []
    for j in range(hover_index, len(pile.cards)):
        rj = pile.rect_for_index(j)
        overlay.append((pile.cards[j], rj.x, rj.y))
    r = pile.rect_for_index(hover_index)
    mask = (pile.x, pile.y, C.CARD_W, max(0, r.y - pile.y))
    return overlay, mask


def compact_fan(current_len: int, default_fan: int, compact_fan: int, threshold: int = 3) -> int:
    """Return a fan_y value that compacts when stack is tall."""
    return default_fan if current_len <= threshold else compact_fan


class PeekController:
    """
    Klondike-style peek:
    - When hovering over a face-up card that is not the top card of a pile,
      after a short delay show a full overlay of just that card at its pile position.
    Scenes should:
      - call cancel() on scroll/clicks
      - call on_motion_over_piles(piles, world_pos)
      - call maybe_activate(now_ms) before draw
      - draw overlay if present, adding their scroll offsets
    """

    def __init__(self, delay_ms: int = 2000):
        self.delay_ms = delay_ms
        self.overlay: Optional[Tuple[C.Card, int, int]] = None  # (card, world_x, world_y)
        self._candidate: Optional[Tuple[int, int]] = None  # (pile_id, index)
        self._started_at: int = 0
        self._pending: Optional[Tuple[C.Card, int, int]] = None

    def cancel(self):
        self.overlay = None
        self._candidate = None
        self._pending = None
        self._started_at = 0

    def on_motion_over_piles(self, piles: List[C.Pile], world_pos: Tuple[int, int]):
        mxw, myw = world_pos
        candidate = None
        pending = None
        for p in piles:
            hi = p.hit((mxw, myw))
            if hi is None or hi == -1:
                continue
            # Only peek if not the top card and it is face-up
            if hi < len(p.cards) - 1 and p.cards[hi].face_up:
                r = p.rect_for_index(hi)
                candidate = (id(p), hi)
                pending = (p.cards[hi], r.x, r.y)
                break
        now = pygame.time.get_ticks()
        if candidate is None:
            self._candidate = None
            self._pending = None
            self.overlay = None
            return
        if candidate != self._candidate:
            self._candidate = candidate
            self._started_at = now
            self._pending = pending
            self.overlay = None
        else:
            if now - self._started_at >= self.delay_ms and self._pending is not None:
                self.overlay = self._pending

    def maybe_activate(self, now_ms: int):
        if (
            self.overlay is None
            and self._candidate is not None
            and self._pending is not None
            and now_ms - self._started_at >= self.delay_ms
        ):
            self.overlay = self._pending
