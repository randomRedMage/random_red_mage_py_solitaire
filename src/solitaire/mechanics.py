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
        self._from_use_scroll: bool = True
        self._to_use_scroll: bool = True

    def start_move(
        self,
        card: C.Card,
        from_xy: Tuple[int, int],
        to_xy: Tuple[int, int],
        dur_ms: int = 300,
        on_complete: Optional[Callable[[], None]] = None,
        flip_mid: bool = False,
        *,
        from_use_scroll: bool = True,
        to_use_scroll: bool = True,
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
        self._from_use_scroll = from_use_scroll
        self._to_use_scroll = to_use_scroll

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
        from_sx = sx + (scroll_x if self._from_use_scroll else 0)
        from_sy = sy + (scroll_y if self._from_use_scroll else 0)
        to_sx = tx + (scroll_x if self._to_use_scroll else 0)
        to_sy = ty + (scroll_y if self._to_use_scroll else 0)
        x = int(from_sx + (to_sx - from_sx) * t)
        y = int(from_sy + (to_sy - from_sy) * t)
        if self._flip_mid:
            if t >= 0.5 and not self._flipped:
                self._card.face_up = True
                self._flipped = True
            if t < 0.5:
                back = C.get_back_surface()
                surface.blit(back, (x, y))
            else:
                surf = C.get_card_surface(self._card)
                surface.blit(surf, (x, y))
        else:
            surf = C.get_card_surface(self._card)
            surface.blit(surf, (x, y))


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


class EdgePanDuringDrag:
    """
    Edge panning while dragging cards.

    Scenes create one instance and wire it as follows:
      - call on_mouse_pos((mx, my)) on every MOUSEMOTION
      - call set_active(True) when a card/stack drag starts; set_active(False) when it ends
      - call step(has_h_scroll, has_v_scroll) once per frame (e.g., in draw)
        and apply returned (dx, dy) to scroll_x/scroll_y, then clamp

    Behavior:
      - When the cursor is within `edge_margin_px` of a screen edge, produce a
        scroll delta in that direction. Speed scales with proximity to the edge
        between min_speed and max_speed (pixels/second).
      - Top edge respects a configurable `top_inset_px` so UI toolbars don't
        accidentally trigger vertical panning.
    """

    def __init__(
        self,
        edge_margin_px: int = 28,
        min_speed_pps: int = 220,
        max_speed_pps: int = 900,
        top_inset_px: int = 0,
    ):
        self.edge = int(edge_margin_px)
        self.vmin = float(max(0, min_speed_pps))
        self.vmax = float(max(min_speed_pps, max_speed_pps))
        self.top_inset = int(max(0, top_inset_px))
        self._active = False
        self._mx = 0
        self._my = 0
        self._last_ms: Optional[int] = None

    def set_active(self, active: bool):
        self._active = bool(active)
        # Reset timing on activation to avoid a large first dt
        self._last_ms = pygame.time.get_ticks() if self._active else None

    def on_mouse_pos(self, pos: Tuple[int, int]):
        self._mx, self._my = int(pos[0]), int(pos[1])

    def _axis_speed(self, t: float) -> float:
        # t in [0,1]; ease with a quadratic curve for smoother start
        if t <= 0.0:
            return 0.0
        t = min(1.0, t)
        eased = t * t  # ease-in
        return self.vmin + (self.vmax - self.vmin) * eased

    def step(self, has_h_scroll: bool, has_v_scroll: bool) -> Tuple[int, int]:
        if not self._active:
            self._last_ms = pygame.time.get_ticks()
            return (0, 0)
        now = pygame.time.get_ticks()
        if self._last_ms is None:
            self._last_ms = now
            return (0, 0)
        dt_ms = max(0, now - self._last_ms)
        self._last_ms = now
        if dt_ms == 0:
            return (0, 0)

        mx, my = self._mx, self._my
        W, H = C.SCREEN_W, C.SCREEN_H
        dx = 0.0
        dy = 0.0

        # Horizontal near-edges (compute even if has_h_scroll is False; scene clamping will prevent movement)
        if self.edge > 0:
            if mx <= self.edge:
                t = (self.edge - mx) / float(self.edge)
                dx = +self._axis_speed(t)
            elif mx >= W - self.edge:
                t = (mx - (W - self.edge)) / float(self.edge)
                dx = -self._axis_speed(t)

        # Vertical near-edges (respect top inset to avoid toolbars; compute regardless of has_v_scroll)
        if self.edge > 0:
            top_edge = self.top_inset + self.edge
            if my <= top_edge:
                t = (top_edge - my) / float(self.edge)
                dy = +self._axis_speed(t)  # top edge pans upward (toward top content)
            elif my >= H - self.edge:
                t = (my - (H - self.edge)) / float(self.edge)
                dy = -self._axis_speed(t)

        # Convert to per-frame pixel deltas
        dt = dt_ms / 1000.0
        return (int(dx * dt), int(dy * dt))


class DragPanController:
    """Handle middle-mouse drag panning for scrollable scenes."""

    def __init__(self, *, button: int = 2) -> None:
        self.button = int(button)
        self._active: bool = False
        self._anchor: Optional[Tuple[int, int]] = None
        self._scroll_anchor: Optional[Tuple[int, int]] = None

    def handle_event(
        self,
        event,
        *,
        target,
        clamp: Callable[[], None],
        attr_x: Optional[str] = "scroll_x",
        attr_y: Optional[str] = "scroll_y",
    ) -> bool:
        """Process a pygame event and update the target scroll offsets.

        Returns True when the event was consumed by drag panning.
        """

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == self.button:
            self._active = True
            self._anchor = event.pos
            sx = getattr(target, attr_x, 0) if attr_x else 0
            sy = getattr(target, attr_y, 0) if attr_y else 0
            self._scroll_anchor = (int(sx), int(sy))
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == self.button:
            if self._active:
                self._active = False
                self._anchor = None
                self._scroll_anchor = None
                return True
            return False

        if (
            event.type == pygame.MOUSEMOTION
            and self._active
            and self._anchor is not None
            and self._scroll_anchor is not None
        ):
            mx, my = event.pos
            ax, ay = self._anchor
            sx, sy = self._scroll_anchor
            if attr_x:
                setattr(target, attr_x, sx + (mx - ax))
            if attr_y:
                setattr(target, attr_y, sy + (my - ay))
            clamp()
            return True

        return False


def debug_prepare_edge_pan_test(scene):
    """
    Developer-only helper. If a scene has common pile attributes, rearrange
    cards to create an intentionally large stack or row to force scrollbars so
    edge panning can be verified quickly. Does nothing if attributes unknown.

    Safe to call after a scene has been constructed and dealt.
    """
    try:
        # Prefer tableau-style merging into first pile
        if hasattr(scene, "tableau") and isinstance(scene.tableau, list) and scene.tableau:
            all_cards = []
            for p in scene.tableau:
                all_cards.extend(p.cards)
                p.cards = []
            for c in all_cards:
                c.face_up = True
            scene.tableau[0].cards = all_cards
        # Gate uses 'center' and 'reserves'
        elif hasattr(scene, "center") and isinstance(scene.center, list) and scene.center:
            all_cards = []
            for p in scene.center:
                all_cards.extend(p.cards)
                p.cards = []
            # include reserves if present
            if hasattr(scene, "reserves") and isinstance(scene.reserves, list):
                for r in scene.reserves:
                    all_cards.extend(r.cards)
                    r.cards = []
            for c in all_cards:
                c.face_up = True
            scene.center[0].cards = all_cards
        # Nothing to do for radial modes like Big Ben
        # Clamp scroll if supported
        if hasattr(scene, "_clamp_scroll_xy") and callable(scene._clamp_scroll_xy):
            scene._clamp_scroll_xy()
        elif hasattr(scene, "_clamp_scroll") and callable(scene._clamp_scroll):
            scene._clamp_scroll()
    except Exception:
        # Best-effort only; never crash in debug helper
        pass
