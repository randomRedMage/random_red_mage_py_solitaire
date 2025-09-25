"""Shared helpers for solitaire modes.

This module centralises metadata about the available solitaire games and
provides a small helper that standardises toolbar creation and keyboard
shortcuts for in-game scenes.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.ui import DEFAULT_BUTTON_HEIGHT, make_toolbar


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
    ("Packers", ("klondike", "freecell", "gate", "demon", "beleaguered_castle", "yukon")),
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
        if game_id is not None:
            meta = GAME_REGISTRY.get(game_id)
            if meta is None:
                raise KeyError(f"Unknown solitaire game id: {game_id}")
            self._options_module = meta.options_module
            self._options_class_name = meta.options_class
            self._return_to_options = meta.return_to_options
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

    def _add_action(
        self,
        actions: MutableMapping[str, Mapping[str, Any]],
        default_label: str,
        spec: ActionSpec,
        *,
        default_shortcut: Optional[int] = None,
    ) -> None:
        normalised = self._normalise_action(default_label, spec, default_shortcut=default_shortcut)
        if normalised is None:
            return
        label, action_dict, shortcut = normalised
        actions[label] = action_dict
        if shortcut is not None:
            self._shortcut_actions[shortcut] = action_dict

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
        """Construct a toolbar with shared buttons and shortcuts."""

        self._shortcut_actions = {}

        actions: Dict[str, Mapping[str, Any]] = {}
        menu_action: Dict[str, Any] = {"on_click": self.goto_menu}
        if menu_tooltip:
            menu_action["tooltip"] = menu_tooltip
        actions["Menu"] = menu_action
        self._shortcut_actions[pygame.K_ESCAPE] = menu_action

        self._add_action(actions, "New", new_action, default_shortcut=pygame.K_n)
        self._add_action(actions, "Restart", restart_action, default_shortcut=pygame.K_r)
        self._add_action(actions, "Undo", undo_action, default_shortcut=pygame.K_u)
        self._add_action(actions, "Auto", auto_action, default_shortcut=pygame.K_a)
        self._add_action(actions, "Hint", hint_action, default_shortcut=pygame.K_h)
        self._add_action(actions, "Save", save_action, default_shortcut=pygame.K_s)
        self._add_action(actions, "Help", help_action)

        if extra_actions:
            for label, spec in extra_actions:
                self._add_action(actions, label, spec)

        kwargs = {
            "height": DEFAULT_BUTTON_HEIGHT,
            "margin": (10, 8),
            "gap": 8,
            "align": "right",
            "width_provider": lambda: C.SCREEN_W,
        }
        if toolbar_kwargs:
            kwargs.update(toolbar_kwargs)
        return make_toolbar(actions, **kwargs)

    def goto_menu(self) -> None:
        if self._return_to_options:
            scene_cls = self._load_options_scene()
            self.scene.next_scene = scene_cls(self.scene.app)
        else:
            from solitaire.scenes.menu import MainMenuScene

            self.scene.next_scene = MainMenuScene(self.scene.app)

    def handle_shortcuts(self, event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        action = self._shortcut_actions.get(event.key)
        if action is None:
            return False
        return self._invoke_action(action)


__all__ = ["GAME_REGISTRY", "GAME_SECTIONS", "GameMetadata", "ModeUIHelper"]

