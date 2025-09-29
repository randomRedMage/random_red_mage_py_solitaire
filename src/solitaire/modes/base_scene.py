"""Shared helpers for solitaire modes.

This module centralises metadata about the available solitaire games and
provides a small helper that standardises toolbar creation and keyboard
shortcuts for in-game scenes.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire import mechanics as M
from solitaire.ui import DEFAULT_BUTTON_HEIGHT, GameMenuModal, make_toolbar


@dataclass(frozen=True)
class GameMetadata:
    """Description and options-scene metadata for a solitaire mode."""

    key: str
    label: str
    icon_filename: str
    options_module: str
    options_class: str
    section: str
    return_to_options: bool = True


_GAME_METADATA: Tuple[GameMetadata, ...] = (
    GameMetadata(
        key="accordion",
        label="Accordion",
        icon_filename="icon_accordion.png",
        options_module="solitaire.scenes.game_options.accordion_options",
        options_class="AccordionOptionsScene",
        section="Other",
        return_to_options=True,
    ),
    GameMetadata(
        key="klondike",
        label="Klondike",
        icon_filename="icon_klondike.png",
        options_module="solitaire.scenes.game_options.klondike_options",
        options_class="KlondikeOptionsScene",
        section="Packers",
        return_to_options=True,
    ),
    GameMetadata(
        key="freecell",
        label="FreeCell",
        icon_filename="icon_freecell.png",
        options_module="solitaire.scenes.game_options.freecell_options",
        options_class="FreeCellOptionsScene",
        section="Packers",
        return_to_options=True,
    ),
    GameMetadata(
        key="gate",
        label="Gate",
        icon_filename="icon_gate.png",
        options_module="solitaire.scenes.game_options.gate_options",
        options_class="GateOptionsScene",
        section="Packers",
        return_to_options=True,
    ),
    GameMetadata(
        key="demon",
        label="Demon\n(Canfield)",
        icon_filename="icon_demon.png",
        options_module="solitaire.scenes.game_options.demon_options",
        options_class="DemonOptionsScene",
        section="Packers",
    ),
    GameMetadata(
        key="duchess",
        label="Duchess",
        icon_filename="icon_duchess.png",
        options_module="solitaire.scenes.game_options.duchess_options",
        options_class="DuchessOptionsScene",
        section="Packers",
    ),
    GameMetadata(
        key="chameleon",
        label="Chameleon",
        icon_filename="icon_chameleon.png",
        options_module="solitaire.scenes.game_options.chameleon_options",
        options_class="ChameleonOptionsScene",
        section="Packers",
    ),
    GameMetadata(
        key="beleaguered_castle",
        label="Beleaguered\nCastle",
        icon_filename="icon_beleagured_castle.png",
        options_module="solitaire.scenes.game_options.beleaguered_castle_options",
        options_class="BeleagueredCastleOptionsScene",
        section="Packers",
    ),
    GameMetadata(
        key="yukon",
        label="Yukon",
        icon_filename="icon_yukon.png",
        options_module="solitaire.scenes.game_options.yukon_options",
        options_class="YukonOptionsScene",
        section="Packers",
    ),
    GameMetadata(
        key="big_ben",
        label="Big Ben",
        icon_filename="icon_big_ben.png",
        options_module="solitaire.scenes.game_options.big_ben_options",
        options_class="BigBenOptionsScene",
        section="Builders",
    ),
    GameMetadata(
        key="golf",
        label="Golf",
        icon_filename="icon_golf.png",
        options_module="solitaire.scenes.game_options.golf_options",
        options_class="GolfOptionsScene",
        section="Builders",
    ),
    GameMetadata(
        key="pyramid",
        label="Pyramid",
        icon_filename="icon_pyramid.png",
        options_module="solitaire.scenes.game_options.pyramid_options",
        options_class="PyramidOptionsScene",
        section="Builders",
        return_to_options=True,
    ),
    GameMetadata(
        key="tripeaks",
        label="TriPeaks",
        icon_filename="icon_tripeaks.png",
        options_module="solitaire.scenes.game_options.tripeaks_options",
        options_class="TriPeaksOptionsScene",
        section="Builders",
        return_to_options=True,
    ),
    GameMetadata(
        key="bowling_solitaire",
        label="Bowling\nSolitaire",
        icon_filename="icon_bowling_solitaire.png",
        options_module="solitaire.scenes.game_options.bowling_solitaire_options",
        options_class="BowlingSolitaireOptionsScene",
        section="Other",
        return_to_options=True,
    ),
)


GAME_REGISTRY: Dict[str, GameMetadata] = {meta.key: meta for meta in _GAME_METADATA}


# Section definitions preserve the ordering from the original main menu.
GAME_SECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("Packers", ("klondike", "freecell", "gate", "demon", "duchess", "chameleon", "beleaguered_castle", "yukon")),
    ("Builders", ("big_ben", "golf", "pyramid", "tripeaks")),
    ("Other", ("accordion", "bowling_solitaire")),
)


ActionSpec = Optional[Mapping[str, Any] | Callable[[], None] | Tuple[str, Mapping[str, Any] | Callable[[], None]]]


class ModeUIHelper:
    """Utility class that wires shared toolbar buttons and shortcuts."""

    def __init__(
        self,
        scene,
        *,
        game_id: Optional[str] = None,
        options_scene: Optional[str | type] = None,
        return_to_options: Optional[bool] = None,
    ) -> None:
        self.scene = scene
        self._options_module: Optional[str] = None
        self._options_class_name: Optional[str] = None
        self._options_cls: Optional[type] = None
        self._return_to_options: bool = True
        self._game_id: Optional[str] = None
        if game_id is not None:
            meta = GAME_REGISTRY.get(game_id)
            if meta is None:
                raise KeyError(f"Unknown solitaire game id: {game_id}")
            self._options_module = meta.options_module
            self._options_class_name = meta.options_class
            self._return_to_options = meta.return_to_options
            self._game_id = meta.key
        elif options_scene is not None:
            if isinstance(options_scene, str):
                module_name, class_name = self._split_import_path(options_scene)
                self._options_module = module_name
                self._options_class_name = class_name
            else:
                self._options_cls = options_scene
                self._options_module = options_scene.__module__
                self._options_class_name = options_scene.__name__
            if return_to_options is not None:
                self._return_to_options = bool(return_to_options)
        else:
            raise ValueError("ModeUIHelper requires either a game_id or an options_scene")
        if return_to_options is not None and game_id is not None:
            self._return_to_options = bool(return_to_options)
        self._shortcut_actions: Dict[int, Mapping[str, Any]] = {}
        self.menu_modal: GameMenuModal | None = None
        self._modal_support: Optional[bool] = None

    @staticmethod
    def _split_import_path(path: str) -> Tuple[str, str]:
        if ":" in path:
            module_name, class_name = path.split(":", 1)
        else:
            module_name, class_name = path.rsplit(".", 1)
        return module_name, class_name

    def _load_options_scene(self):
        if self._options_cls is None:
            if not self._options_module or not self._options_class_name:
                raise RuntimeError("Options scene information is missing")
            module = importlib.import_module(self._options_module)
            self._options_cls = getattr(module, self._options_class_name)
        return self._options_cls

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
        register("Hint", hint_action, shortcut=pygame.K_h, store_key="hint")
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
            hint_action=stored.get("hint"),
        )

        return make_toolbar(actions, **kwargs)

    def toggle_menu_modal(self) -> None:
        if self.menu_modal is None:
            return
        self.menu_modal.toggle()

    def close_menu_modal(self) -> None:
        if self.menu_modal and self.menu_modal.visible:
            self.menu_modal.close()

    def handle_menu_event(self, event) -> bool:
        if self.menu_modal and self.menu_modal.visible:
            return self.menu_modal.handle_event(event)
        return False

    def draw_menu_modal(self, surface) -> None:
        if self.menu_modal and self.menu_modal.visible:
            self.menu_modal.draw(surface)

    def relayout_menu_modal(self) -> None:
        if self.menu_modal:
            self.menu_modal.relayout()

    def can_open_options(self) -> bool:
        if self._supports_game_modal():
            return True
        try:
            self._load_options_scene()
        except Exception:
            return False
        return True

    def open_options(self) -> None:
        if self._supports_game_modal():
            from solitaire.scenes.menu import MainMenuScene

            menu_scene = MainMenuScene(self.scene.app)
            game_key = self._game_id
            if game_key and menu_scene._open_game_modal(game_key):
                self.scene.next_scene = menu_scene
                return
        try:
            scene_cls = self._load_options_scene()
        except Exception:
            return
        self.scene.next_scene = scene_cls(self.scene.app)

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
        if self._return_to_options and self._game_id:
            from solitaire.scenes.menu import MainMenuScene

            proxy = None
            meta = GAME_REGISTRY.get(self._game_id)
            if meta is not None:
                try:
                    module = __import__(meta.options_module, fromlist=[meta.options_class])
                    scene_cls = getattr(module, meta.options_class)
                    proxy = scene_cls(self.scene.app)
                except Exception:
                    proxy = None
            menu_scene = MainMenuScene(self.scene.app)
            menu_scene._open_game_modal(self._game_id, proxy=proxy)
            self.scene.next_scene = menu_scene
            return
        if self._return_to_options:
            scene_cls = self._load_options_scene()
            self.scene.next_scene = scene_cls(self.scene.app)
        else:
            from solitaire.scenes.menu import MainMenuScene

            self.scene.next_scene = MainMenuScene(self.scene.app)

    def handle_shortcuts(self, event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if self.menu_modal and self.menu_modal.visible:
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

