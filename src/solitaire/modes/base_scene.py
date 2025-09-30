"""Shared helpers for solitaire modes.

This module centralises metadata about the available solitaire games and
provides a small helper that standardises toolbar creation and keyboard
shortcuts for in-game scenes.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.ui import DEFAULT_BUTTON_HEIGHT, GameMenuModal, make_toolbar


class _InGameMenuProxy:
    """Lightweight stand-in for main menu when opening game options in-scene."""

    __slots__ = ("app", "next_scene")

    def __init__(self, helper: "ModeUIHelper") -> None:
        self.app = helper.scene.app
        self.next_scene = None


@dataclass(frozen=True)
class GameMetadata:
    """Description metadata for a solitaire mode."""

    key: str
    label: str
    icon_filename: str
    section: str


_GAME_METADATA: Tuple[GameMetadata, ...] = (
    GameMetadata(
        key="accordion",
        label="Accordion",
        icon_filename="icon_accordion.png",
        section="Other",
    ),
    GameMetadata(
        key="klondike",
        label="Klondike",
        icon_filename="icon_klondike.png",
        section="Packers",
    ),
    GameMetadata(
        key="freecell",
        label="FreeCell",
        icon_filename="icon_freecell.png",
        section="Packers",
    ),
    GameMetadata(
        key="gate",
        label="Gate",
        icon_filename="icon_gate.png",
        section="Packers",
    ),
    GameMetadata(
        key="demon",
        label="Demon\n(Canfield)",
        icon_filename="icon_demon.png",
        section="Packers",
    ),
    GameMetadata(
        key="duchess",
        label="Duchess",
        icon_filename="icon_duchess.png",
        section="Packers",
    ),
    GameMetadata(
        key="chameleon",
        label="Chameleon",
        icon_filename="icon_chameleon.png",
        section="Packers",
    ),
    GameMetadata(
        key="beleaguered_castle",
        label="Beleaguered\nCastle",
        icon_filename="icon_beleagured_castle.png",
        section="Packers",
    ),
    GameMetadata(
        key="yukon",
        label="Yukon",
        icon_filename="icon_yukon.png",
        section="Packers",
    ),
    GameMetadata(
        key="big_ben",
        label="Big Ben",
        icon_filename="icon_big_ben.png",
        section="Builders",
    ),
    GameMetadata(
        key="golf",
        label="Golf",
        icon_filename="icon_golf.png",
        section="Builders",
    ),
    GameMetadata(
        key="monte_carlo",
        label="Monte Carlo",
        icon_filename="icon_monte_carlo.png",
        section="Builders",
    ),
    GameMetadata(
        key="pyramid",
        label="Pyramid",
        icon_filename="icon_pyramid.png",
        section="Builders",
    ),
    GameMetadata(
        key="tripeaks",
        label="TriPeaks",
        icon_filename="icon_tripeaks.png",
        section="Builders",
    ),
    GameMetadata(
        key="bowling_solitaire",
        label="Bowling\nSolitaire",
        icon_filename="icon_bowling_solitaire.png",
        section="Other",
    ),
)


GAME_REGISTRY: Dict[str, GameMetadata] = {meta.key: meta for meta in _GAME_METADATA}


# Section definitions preserve the ordering from the original main menu.
GAME_SECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Packers", ("klondike", "freecell", "gate", "demon", "duchess", "chameleon", "beleaguered_castle", "yukon")),
    ("Builders", ("big_ben", "golf", "monte_carlo", "pyramid", "tripeaks")),
    ("Other", ("accordion", "bowling_solitaire")),
)


ActionSpec = Optional[Mapping[str, Any] | Callable[[], None] | Tuple[str, Mapping[str, Any] | Callable[[], None]]]


class ModeUIHelper:
    """Utility class that wires shared toolbar buttons and shortcuts."""

    def __init__(
        self,
        scene,
        *,
        game_id: str,
    ) -> None:
        self.scene = scene
        self._game_id: Optional[str] = None
        meta = GAME_REGISTRY.get(game_id)
        if meta is None:
            raise KeyError(f"Unknown solitaire game id: {game_id}")
        self._game_id = meta.key
        self._shortcut_actions: Dict[int, Mapping[str, Any]] = {}
        self.menu_modal: GameMenuModal | None = None
        self._modal_support: Optional[bool] = None
        self._options_modal = None
        self._options_proxy: _InGameMenuProxy | None = None

    def _supports_game_modal(self) -> bool:
        if not self._game_id:
            return False
        if self._modal_support is not None:
            return self._modal_support
        try:
            from solitaire.scenes import menu_options  # type: ignore
        except Exception:
            self._modal_support = False
            return False
        registry = getattr(menu_options, "CONTROLLER_REGISTRY", {})
        self._modal_support = self._game_id in registry
        return self._modal_support

    def _invoke_action(self, action: Mapping[str, Any]) -> bool:
        enabled = action.get("enabled", True)
        if callable(enabled):
            try:
                if not enabled():
                    return False
            except Exception:
                return False
        elif not enabled:
            return False
        callback = action.get("on_click")
        if not callable(callback):
            return False
        callback()
        return True

    def _normalise_action(
        self,
        default_label: str,
        spec: ActionSpec,
        *,
        default_shortcut: Optional[int] = None,
    ) -> Optional[Tuple[str, Mapping[str, Any], Optional[int]]]:
        if spec is None:
            return None
        label = default_label
        cfg: Mapping[str, Any] | Callable[[], None]
        if isinstance(spec, tuple):
            label, cfg = spec
        else:
            cfg = spec
        if callable(cfg):
            action_dict: MutableMapping[str, Any] = {"on_click": cfg}
        else:
            action_dict = dict(cfg)
        shortcut = action_dict.pop("shortcut", default_shortcut)
        return label, action_dict, shortcut


    def build_toolbar(
        self,
        *,
        new_action: ActionSpec = None,
        restart_action: ActionSpec = None,
        undo_action: ActionSpec = None,
        auto_action: ActionSpec = None,
        hint_action: ActionSpec = None,
        save_action: ActionSpec = None,
        help_action: ActionSpec = None,
        extra_actions: Optional[Iterable[Tuple[str, ActionSpec]]] = None,
        menu_tooltip: Optional[str] = None,
        toolbar_kwargs: Optional[Mapping[str, Any]] = None,
    ):
        """Construct a toolbar with shared buttons, shortcuts, and modal menu."""

        self._shortcut_actions = {}

        actions: Dict[str, Mapping[str, Any]] = {}
        stored: Dict[str, Tuple[str, Mapping[str, Any]]] = {}

        def register(
            default_label: str,
            spec: ActionSpec | Mapping[str, Any] | None,
            *,
            shortcut: Optional[int] = None,
            store_key: Optional[str] = None,
        ) -> Optional[Tuple[str, Mapping[str, Any]]]:
            normalised = self._normalise_action(default_label, spec, default_shortcut=shortcut)
            if normalised is None:
                return None
            label, action_dict, resolved_shortcut = normalised
            actions[label] = action_dict
            if resolved_shortcut is not None:
                self._shortcut_actions[resolved_shortcut] = action_dict
            if store_key:
                stored[store_key] = (label, action_dict)
            return label, action_dict

        menu_spec: Dict[str, Any] = {"on_click": self.toggle_menu_modal}
        if menu_tooltip:
            menu_spec["tooltip"] = menu_tooltip
        register("Menu", menu_spec, shortcut=pygame.K_ESCAPE)

        register("New", new_action, shortcut=pygame.K_n, store_key="new")
        register("Restart", restart_action, shortcut=pygame.K_r, store_key="restart")
        register("Undo", undo_action, shortcut=pygame.K_u)
        register("Auto", auto_action, shortcut=pygame.K_a)
        register("Hint", hint_action, shortcut=pygame.K_h)
        register("Save", save_action, shortcut=pygame.K_s, store_key="save")
        register("Help", help_action, store_key="help")

        if extra_actions:
            for label, spec in extra_actions:
                register(label, spec)

        kwargs = {
            "height": DEFAULT_BUTTON_HEIGHT,
            "margin": (10, 8),
            "gap": 8,
            "align": "right",
            "width_provider": lambda: C.SCREEN_W,
        }
        if toolbar_kwargs:
            kwargs.update(toolbar_kwargs)

        self.menu_modal = GameMenuModal(
            self,
            new_action=stored.get("new"),
            restart_action=stored.get("restart"),
            help_action=stored.get("help"),
            save_action=stored.get("save"),
        )

        return make_toolbar(actions, **kwargs)

    def toggle_menu_modal(self) -> None:
        if self._options_modal is not None:
            self._close_options_modal()
            return
        if self.menu_modal is None:
            return
        self.menu_modal.toggle()

    def close_menu_modal(self) -> None:
        if self.menu_modal and self.menu_modal.visible:
            self.menu_modal.close()
        if self._options_modal is not None:
            self._close_options_modal()

    def handle_menu_event(self, event) -> bool:
        if self._options_modal is not None:
            should_close = self._options_modal.handle_event(event)
            if should_close:
                self._close_options_modal()
            return True
        if self.menu_modal and self.menu_modal.visible:
            return self.menu_modal.handle_event(event)
        return False

    def draw_menu_modal(self, surface) -> None:
        if self._options_modal is not None:
            self._options_modal.draw(surface)
        elif self.menu_modal and self.menu_modal.visible:
            self.menu_modal.draw(surface)

    def relayout_menu_modal(self) -> None:
        if self.menu_modal:
            self.menu_modal.relayout()

    def _build_in_game_options_modal(self):
        if not self._game_id:
            return None
        try:
            from solitaire.scenes import menu_options  # type: ignore
            from solitaire.scenes.menu import GameOptionsModal  # type: ignore
        except Exception:
            return None
        registry = getattr(menu_options, "CONTROLLER_REGISTRY", {})
        controller_cls = registry.get(self._game_id)
        if controller_cls is None:
            return None
        metadata = GAME_REGISTRY.get(self._game_id)
        if metadata is None:
            return None
        try:
            proxy = _InGameMenuProxy(self)
            controller = controller_cls(proxy, metadata=metadata)
            modal = GameOptionsModal(self.scene, controller)
        except Exception:
            return None
        return proxy, modal

    def _close_options_modal(self) -> None:
        proxy = self._options_proxy
        self._options_modal = None
        self._options_proxy = None
        if proxy and proxy.next_scene is not None:
            self.scene.next_scene = proxy.next_scene

    def can_open_options(self) -> bool:
        if self._supports_game_modal():
            return True
        return False

    def open_options(self) -> None:
        if self._supports_game_modal():
            if self._options_modal is not None:
                return
            modal_info = self._build_in_game_options_modal()
            if modal_info is not None:
                self.close_menu_modal()
                proxy, modal = modal_info
                self._options_proxy = proxy
                self._options_modal = modal
                return
        self.goto_main_menu()

    def goto_main_menu(self) -> None:
        from solitaire.scenes.menu import MainMenuScene

        self.scene.next_scene = MainMenuScene(self.scene.app)

    def quit_to_desktop(self) -> None:
        pygame.quit()
        sys.exit(0)

    def is_game_completed(self) -> bool:
        scene = self.scene
        if hasattr(scene, "is_game_complete"):
            try:
                if scene.is_game_complete():
                    return True
            except Exception:
                pass
        for attr in ("game_over", "_game_over", "completed"):
            value = getattr(scene, attr, None)
            if isinstance(value, bool) and value:
                return True
        message = getattr(scene, "message", "")
        if isinstance(message, str):
            lower = message.lower()
            if "congratulations" in lower or "you won" in lower:
                return True
        return False

    def should_confirm_reset(self) -> bool:
        return not self.is_game_completed()


    def goto_menu(self) -> None:
        self.close_menu_modal()
        from solitaire.scenes.menu import MainMenuScene

        menu_scene = MainMenuScene(self.scene.app)
        if self._game_id:
            try:
                menu_scene._open_game_modal(self._game_id)
            except Exception:
                pass
        self.scene.next_scene = menu_scene

    def handle_shortcuts(self, event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if self.menu_modal and self.menu_modal.visible:
            return True
        if self._options_modal is not None:
            return True
        action = self._shortcut_actions.get(event.key)
        if action is None:
            return False
        return self._invoke_action(action)


class ScrollableSceneMixin:
    """Reusable helpers for solitaire scenes that support scrolling."""

    scroll_step: int = 60

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[override]
        super().__init__(*args, **kwargs)
        self.scroll_x: int = 0
        self.scroll_y: int = 0
        self._panning: bool = False
        self._pan_anchor: Optional[Tuple[int, int]] = None
        self._scroll_anchor: Optional[Tuple[int, int]] = None
        self.edge_pan = M.EdgePanDuringDrag(
            edge_margin_px=28,
            top_inset_px=getattr(C, "TOP_BAR_H", 60),
        )

    # ----- Abstract helpers -----
    def iter_scroll_piles(self) -> Iterable["C.Pile"]:
        """Return the piles that should be considered when clamping scroll."""

        raise NotImplementedError

    # ----- Coordinate transforms -----
    def _screen_to_world(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        sx, sy = pos
        return (sx - self.scroll_x, sy - self.scroll_y)

    def _world_to_screen(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        wx, wy = pos
        return (wx + self.scroll_x, wy + self.scroll_y)

    # ----- Scroll bounds -----
    def _scroll_content_bounds(self) -> Tuple[int, int, int, int]:
        piles = tuple(self.iter_scroll_piles())
        if not piles:
            top_margin = getattr(C, "TOP_BAR_H", 60)
            return (0, top_margin, C.SCREEN_W, top_margin + C.CARD_H)

        left = min(p.x for p in piles)
        top = min(p.y for p in piles)
        right = left
        bottom = top
        for pile in piles:
            if pile.cards:
                last_rect = pile.rect_for_index(len(pile.cards) - 1)
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
                rect.union_ip(last_rect)
            else:
                rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            left = min(left, rect.left)
            top = min(top, rect.top)
            right = max(right, rect.right)
            bottom = max(bottom, rect.bottom)
        return left, top, right, bottom

    def _clamp_scroll(self) -> None:
        left, _top, right, bottom = self._scroll_content_bounds()
        margin = 20
        max_scroll_x = margin - left
        min_scroll_x = min(0, C.SCREEN_W - right - margin)
        if self.scroll_x > max_scroll_x:
            self.scroll_x = max_scroll_x
        if self.scroll_x < min_scroll_x:
            self.scroll_x = min_scroll_x

        max_scroll_y = 0
        min_scroll_y = min(0, C.SCREEN_H - bottom - margin)
        if self.scroll_y > max_scroll_y:
            self.scroll_y = max_scroll_y
        if self.scroll_y < min_scroll_y:
            self.scroll_y = min_scroll_y

    def _scroll_ranges(self) -> Tuple[int, int, int, int]:
        left, _top, right, bottom = self._scroll_content_bounds()
        margin = 20
        min_scroll_x = min(0, C.SCREEN_W - right - margin)
        max_scroll_x = margin - left
        min_scroll_y = min(0, C.SCREEN_H - bottom - margin)
        max_scroll_y = 0
        return min_scroll_x, max_scroll_x, min_scroll_y, max_scroll_y

    def _step_edge_pan(self) -> None:
        # Called during drawing to gently scroll when dragging near edges.
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        min_sx, max_sx, min_sy, max_sy = self._scroll_ranges()
        has_h = max_sx > min_sx
        has_v = max_sy > min_sy
        dx, dy = self.edge_pan.step(has_h_scroll=has_h, has_v_scroll=has_v)
        if dx or dy:
            self.scroll_x += dx
            self.scroll_y += dy
            self._clamp_scroll()

    # ----- Scroll interaction -----
    def handle_scroll_event(self, event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            self.scroll_y += event.y * self.scroll_step
            self.scroll_x += getattr(event, "x", 0) * self.scroll_step
            self._clamp_scroll()
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            self._panning = True
            self._pan_anchor = event.pos
            self._scroll_anchor = (self.scroll_x, self.scroll_y)
            return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self._panning = False
            self._pan_anchor = None
            self._scroll_anchor = None
            return True

        if event.type == pygame.MOUSEMOTION and self._panning and self._pan_anchor and self._scroll_anchor:
            mx, my = event.pos
            ax, ay = self._pan_anchor
            dx = mx - ax
            dy = my - ay
            self.scroll_x = self._scroll_anchor[0] + dx
            self.scroll_y = self._scroll_anchor[1] + dy
            self._clamp_scroll()
            return True

        return False

    # ----- Drawing helpers -----
    @contextmanager
    def scrolling_draw_offset(self):
        self._step_edge_pan()
        self._clamp_scroll()
        prev_dx, prev_dy = C.DRAW_OFFSET_X, C.DRAW_OFFSET_Y
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y
        try:
            yield
        finally:
            C.DRAW_OFFSET_X = prev_dx
            C.DRAW_OFFSET_Y = prev_dy

    def reset_scroll(self) -> None:
        self.scroll_x = 0
        self.scroll_y = 0
        self._clamp_scroll()
        self.edge_pan.set_active(False)


__all__ = [
    "GAME_REGISTRY",
    "GAME_SECTIONS",
    "GameMetadata",
    "ModeUIHelper",
    "ScrollableSceneMixin",
]

