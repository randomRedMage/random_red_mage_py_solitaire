"""Controllers for game option modals on the main menu."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Sequence

from solitaire import common as C


@dataclass
class OptionState:
    """Represents a selectable option row in the game modal."""

    key: str
    label: str
    values: Sequence[Any]
    index: int = 0
    formatter: Callable[[Any], str] = str

    def current_value(self) -> Any:
        if not self.values:
            return None
        return self.values[self.index % len(self.values)]

    def current_text(self) -> str:
        value = self.current_value()
        return self.formatter(value)

    def step(self, delta: int) -> None:
        if not self.values:
            return
        self.index = (self.index + delta) % len(self.values)


@dataclass
class ButtonState:
    """Metadata for an action button in the game modal."""

    key: str
    label: str
    enabled: bool = True
    variant: str = "default"  # "default", "cancel", "primary"


@dataclass
class ActionResult:
    """Return value from controller button handlers."""

    close_modal: bool = False


class GameOptionsController:
    """Base controller that describes actions and options for a game."""

    def __init__(self, menu_scene, *, metadata) -> None:
        self.menu_scene = menu_scene
        self.app = menu_scene.app
        self.metadata = metadata
        self._options: List[OptionState] = []
        self._message: str = ""

    # ----- lifecycle -------------------------------------------------
    def refresh(self) -> None:
        """Update any dynamic state prior to drawing."""

    # ----- helpers ---------------------------------------------------
    @property
    def message(self) -> str:
        return self._message

    def set_message(self, text: str = "") -> None:
        self._message = text

    def title(self) -> str:
        label = self.metadata.label.replace("\n", " ") if self.metadata else "Game"
        return f"{label} Options"

    # ----- options ---------------------------------------------------
    def options(self) -> Iterable[OptionState]:
        return self._options

    def change_option(self, key: str, delta: int) -> None:
        lookup: Dict[str, OptionState] = {opt.key: opt for opt in self._options}
        option = lookup.get(key)
        if option is None:
            return
        option.step(delta)
        self.on_option_changed(option)

    def on_option_changed(self, option: OptionState) -> None:
        """Hook invoked whenever an option value changes."""

    # ----- buttons ---------------------------------------------------
    def buttons(self) -> Sequence[ButtonState]:
        return []

    def handle_button(self, key: str) -> ActionResult:
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        """Mapping of legacy button attribute names to action keys."""

        return {}


# --- Accordion -------------------------------------------------------

from solitaire.modes import accordion as accordion_mode


class AccordionController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        difficulties = [
            ("easy", "Easy — win with 7 piles or fewer"),
            ("normal", "Normal — win with 4 piles or fewer"),
            ("hard", "Hard — win with 1 pile"),
        ]
        self._options = [
            OptionState(
                key="difficulty",
                label="Difficulty",
                values=difficulties,
                index=1,
                formatter=lambda item: f"{accordion_mode.get_difficulty_label(item[0])}",
            )
        ]

    def _has_save(self) -> bool:
        return accordion_mode.has_saved_game()

    def _resume_label(self) -> str:
        if not self._has_save():
            return "Resume"
        summary = accordion_mode.peek_saved_game_summary()
        if summary:
            return f"Resume ({summary})"
        return "Resume"

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", self._resume_label(), enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            accordion_mode.delete_saved_game()
            difficulty_key, _ = self._options[0].current_value()
            self.menu_scene.next_scene = accordion_mode.AccordionGameScene(
                self.app, difficulty=difficulty_key
            )
            return ActionResult(close_modal=True)
        if key == "resume":
            if not self._has_save():
                return ActionResult(close_modal=False)
            state = accordion_mode.load_saved_game()
            if not state:
                return ActionResult(close_modal=False)
            self.menu_scene.next_scene = accordion_mode.AccordionGameScene(
                self.app, load_state=state
            )
            return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_new": "start", "b_continue": "resume", "b_back": "cancel"}


# --- Beleaguered Castle ----------------------------------------------

from solitaire.modes import beleaguered_castle as beleaguered_castle_mode


class BeleagueredCastleController(GameOptionsController):
    def _has_save(self) -> bool:
        state = beleaguered_castle_mode._safe_read_json(
            beleaguered_castle_mode._bc_save_path()
        )
        return bool(state) and not state.get("completed", False)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            beleaguered_castle_mode._clear_saved_game()
            self.menu_scene.next_scene = (
                beleaguered_castle_mode.BeleagueredCastleGameScene(
                    self.app, load_state=None
                )
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = beleaguered_castle_mode._safe_read_json(
                beleaguered_castle_mode._bc_save_path()
            )
            if state:
                self.menu_scene.next_scene = (
                    beleaguered_castle_mode.BeleagueredCastleGameScene(
                        self.app, load_state=state
                    )
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_resume": "resume", "b_back": "cancel"}


# --- Big Ben ---------------------------------------------------------

from solitaire.modes import big_ben as big_ben_mode
from solitaire.modes import british_blockade as british_blockade_mode


class BigBenController(GameOptionsController):
    def _has_save(self) -> bool:
        state = big_ben_mode._safe_read_json(big_ben_mode._bb_save_path())
        return bool(state) and not state.get("completed", False)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            big_ben_mode._clear_saved_game()
            self.menu_scene.next_scene = big_ben_mode.BigBenGameScene(
                self.app, load_state=None
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = big_ben_mode._safe_read_json(big_ben_mode._bb_save_path())
            if state:
                self.menu_scene.next_scene = big_ben_mode.BigBenGameScene(
                    self.app, load_state=state
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_resume": "resume", "b_back": "cancel"}


class BritishBlockadeController(GameOptionsController):
    def _has_save(self) -> bool:
        return british_blockade_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            british_blockade_mode.delete_saved_game()
            self.menu_scene.next_scene = british_blockade_mode.BritishBlockadeGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume":
            if not self._has_save():
                return ActionResult(close_modal=False)
            state = british_blockade_mode.load_saved_game()
            if not state:
                return ActionResult(close_modal=False)
            self.menu_scene.next_scene = british_blockade_mode.BritishBlockadeGameScene(
                self.app, load_state=state
            )
            return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)


# --- Bowling Solitaire -----------------------------------------------

from solitaire.modes import bowling_solitaire as bowling_mode


class BowlingSolitaireController(GameOptionsController):
    def buttons(self) -> Sequence[ButtonState]:
        has_save = bowling_mode.has_saved_game()
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=has_save),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            self.set_message("")
            return ActionResult(close_modal=True)
        if key == "start":
            self.set_message("")
            self.menu_scene.next_scene = bowling_mode.BowlingSolitaireGameScene(
                self.app
            )
            return ActionResult(close_modal=True)
        if key == "resume":
            load_state = bowling_mode.load_saved_game()
            if not load_state:
                self.set_message("No saved game found.")
                return ActionResult(close_modal=False)
            self.set_message("")
            self.menu_scene.next_scene = bowling_mode.BowlingSolitaireGameScene(
                self.app, load_state=load_state
            )
            return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


# --- Chameleon -------------------------------------------------------

from solitaire.modes import chameleon as chameleon_mode


class ChameleonController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        cfg = chameleon_mode.load_chameleon_config()
        self.stock_cycles = cfg.get("stock_cycles")
        values: List[Any] = [None, 0, 1]
        if self.stock_cycles not in values and self.stock_cycles is not None:
            values.append(self.stock_cycles)
        index = values.index(self.stock_cycles) if self.stock_cycles in values else 0
        self._options = [
            OptionState(
                key="redeals",
                label="Redeals",
                values=values,
                index=index,
                formatter=self._format_value,
            )
        ]

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "Unlimited"
        if value <= 0:
            return "None"
        if value == 1:
            return "1 Redeal"
        return f"{value} Redeals"

    def on_option_changed(self, option: OptionState) -> None:
        self.stock_cycles = option.current_value()
        chameleon_mode.save_chameleon_config(self.stock_cycles)
        chameleon_mode.update_saved_stock_cycles(self.stock_cycles)

    def _has_save(self) -> bool:
        return chameleon_mode.chameleon_save_exists()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            chameleon_mode.clear_saved_state()
            self.menu_scene.next_scene = chameleon_mode.ChameleonGameScene(
                self.app, load_state=None, stock_cycles=self.stock_cycles
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = chameleon_mode.load_saved_state()
            if state and not state.get("completed"):
                state["stock_cycles_allowed"] = self.stock_cycles
                if (
                    self.stock_cycles is not None
                    and state.get("stock_cycles_used", 0) > self.stock_cycles
                ):
                    state["stock_cycles_used"] = self.stock_cycles
                self.menu_scene.next_scene = chameleon_mode.ChameleonGameScene(
                    self.app, load_state=state, stock_cycles=self.stock_cycles
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


# --- Demon -----------------------------------------------------------

from solitaire.modes import demon as demon_mode


class DemonController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        cfg = demon_mode.load_demon_config()
        self.stock_cycles = cfg.get("stock_cycles")
        values: List[Any] = [None, 3, 1]
        if self.stock_cycles not in values:
            values.append(self.stock_cycles)
        index = values.index(self.stock_cycles) if self.stock_cycles in values else 0
        self._options = [
            OptionState(
                key="stock",
                label="Stock Replays",
                values=values,
                index=index,
                formatter=self._format_value,
            )
        ]

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "Unlimited"
        return "1 Replay" if value == 1 else f"{value} Replays"

    def on_option_changed(self, option: OptionState) -> None:
        self.stock_cycles = option.current_value()
        demon_mode.save_demon_config(self.stock_cycles)
        demon_mode.update_saved_stock_cycles(self.stock_cycles)

    def _has_save(self) -> bool:
        return demon_mode.demon_save_exists()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            demon_mode.clear_saved_state()
            self.menu_scene.next_scene = demon_mode.DemonGameScene(
                self.app, load_state=None, stock_cycles=self.stock_cycles
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = demon_mode.load_saved_state()
            if state and not state.get("completed"):
                state["stock_cycles_allowed"] = self.stock_cycles
                if (
                    self.stock_cycles is not None
                    and state.get("stock_cycles_used", 0) > self.stock_cycles
                ):
                    state["stock_cycles_used"] = self.stock_cycles
                self.menu_scene.next_scene = demon_mode.DemonGameScene(
                    self.app, load_state=state, stock_cycles=self.stock_cycles
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


# --- Duchess ---------------------------------------------------------

from solitaire.modes import duchess as duchess_mode


class DuchessController(GameOptionsController):
    def _has_save(self) -> bool:
        return duchess_mode.duchess_save_exists()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            duchess_mode.clear_saved_state()
            self.menu_scene.next_scene = duchess_mode.DuchessGameScene(
                self.app, load_state=None
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = duchess_mode.load_saved_state()
            if state and not state.get("completed"):
                self.menu_scene.next_scene = duchess_mode.DuchessGameScene(
                    self.app, load_state=state
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


# --- FreeCell --------------------------------------------------------

from solitaire.modes import freecell as freecell_mode


class FreeCellController(GameOptionsController):
    def _has_save(self) -> bool:
        return freecell_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                freecell_mode._clear_saved_game()
            except Exception:
                pass
            self.menu_scene.next_scene = freecell_mode.FreeCellGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            load_state = freecell_mode.load_saved_game()
            if load_state:
                self.menu_scene.next_scene = freecell_mode.FreeCellGameScene(
                    self.app, load_state=load_state
                )
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- Gate ------------------------------------------------------------

from solitaire.modes import gate as gate_mode


class GateController(GameOptionsController):
    def _has_save(self) -> bool:
        return gate_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                gate_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = gate_mode.GateGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = gate_mode.load_saved_game()
            if state:
                self.menu_scene.next_scene = gate_mode.GateGameScene(self.app, load_state=state)
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- Golf ------------------------------------------------------------

from solitaire.modes import golf as golf_mode


class GolfController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        self._holes_values = [1, 3, 9, 18]
        self._options = [
            OptionState(
                key="holes",
                label="Course Length",
                values=self._holes_values,
                index=0,
                formatter=lambda v: f"{v} Hole{'s' if v != 1 else ''}",
            ),
            OptionState(
                key="around",
                label="Around the Corner",
                values=[True, False],
                index=0,
                formatter=lambda v: "On" if v else "Off",
            ),
        ]

    def on_option_changed(self, option: OptionState) -> None:
        if option.key == "holes":
            return

    def _holes(self) -> int:
        return int(self._options[0].current_value())

    def _around_flag(self) -> bool:
        return bool(self._options[1].current_value())

    def _has_save(self) -> bool:
        state = golf_mode._safe_read_json(golf_mode._golf_save_path())
        return bool(state) and not state.get("completed", False)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("scores", "Scores"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "scores":
            self.menu_scene.next_scene = golf_mode.GolfScoresScene(self.app)
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                save_path = golf_mode._golf_save_path()
                import os

                if os.path.isfile(save_path):
                    os.remove(save_path)
            except Exception:
                pass
            self.menu_scene.next_scene = golf_mode.GolfGameScene(
                self.app,
                holes_total=self._holes(),
                around=self._around_flag(),
                load_state=None,
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            load_state = golf_mode._safe_read_json(golf_mode._golf_save_path())
            if load_state:
                self.menu_scene.next_scene = golf_mode.GolfGameScene(
                    self.app,
                    holes_total=load_state.get("holes_total", 1),
                    around=bool(load_state.get("around", False)),
                    load_state=load_state,
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {
            "b_new1": "start",
            "b_continue": "resume",
            "b_scores": "scores",
            "b_back": "cancel",
        }


# --- Klondike --------------------------------------------------------

from solitaire.modes import klondike as klondike_mode


class KlondikeController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        difficulty_values = [None, 2, 1]
        self._options = [
            OptionState(
                key="difficulty",
                label="Stock Cycles",
                values=difficulty_values,
                index=0,
                formatter=self._format_difficulty,
            ),
            OptionState(
                key="draw",
                label="Draw Mode",
                values=[3, 1],
                index=0,
                formatter=lambda v: f"Draw {v}",
            ),
        ]

    def _has_save(self) -> bool:
        return klondike_mode.has_saved_game()

    def _format_difficulty(self, value: Any) -> str:
        if value is None:
            return "Unlimited"
        if value == 2:
            return "2 Cycles"
        if value == 1:
            return "1 Cycle"
        return str(value)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            draw_count = int(self._options[1].current_value())
            stock_cycles = self._options[0].current_value()
            try:
                klondike_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = klondike_mode.KlondikeGameScene(
                self.app,
                draw_count=draw_count,
                stock_cycles=stock_cycles,
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = klondike_mode.load_saved_game()
            if state:
                draw_count = int(state.get("draw_count", 3))
                stock_cycles = state.get("stock_cycles_allowed")
                self.menu_scene.next_scene = klondike_mode.KlondikeGameScene(
                    self.app,
                    draw_count=draw_count,
                    stock_cycles=stock_cycles,
                    load_state=state,
                )
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- British Square ---------------------------------------------------

from solitaire.modes import british_square as british_square_mode


class BritishSquareController(GameOptionsController):
    def _has_save(self) -> bool:
        return british_square_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                british_square_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = british_square_mode.BritishSquareGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = british_square_mode.load_saved_game()
            if state:
                self.menu_scene.next_scene = british_square_mode.BritishSquareGameScene(
                    self.app,
                    load_state=state,
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- Pyramid ---------------------------------------------------------

from solitaire.modes import pyramid as pyramid_mode


class PyramidController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        self._options = [
            OptionState(
                key="difficulty",
                label="Resets",
                values=[None, 2, 1],
                index=0,
                formatter=self._format_value,
            )
        ]

    def _has_save(self) -> bool:
        return pyramid_mode.has_saved_game()

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "Unlimited"
        if value == 2:
            return "2 Resets"
        if value == 1:
            return "1 Reset"
        return str(value)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            allowed = self._options[0].current_value()
            try:
                pyramid_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = pyramid_mode.PyramidGameScene(
                self.app, allowed_resets=allowed
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = pyramid_mode.load_saved_game()
            if state:
                allowed = state.get("allowed_resets")
                self.menu_scene.next_scene = pyramid_mode.PyramidGameScene(
                    self.app,
                    allowed_resets=allowed,
                    load_state=state,
                )
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- TriPeaks --------------------------------------------------------

from solitaire.modes import tripeaks as tripeaks_mode
from solitaire.modes import monte_carlo as monte_carlo_mode
from solitaire.modes import duchess_de_luynes as duchess_de_luynes_mode


class TriPeaksController(GameOptionsController):
    def __init__(self, menu_scene, *, metadata) -> None:
        super().__init__(menu_scene, metadata=metadata)
        self._options = [
            OptionState(
                key="wrap",
                label="Wrap A↔K",
                values=[True, False],
                index=0,
                formatter=lambda v: "On" if v else "Off",
            )
        ]

    def _has_save(self) -> bool:
        return tripeaks_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            wrap = bool(self._options[0].current_value())
            try:
                tripeaks_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = tripeaks_mode.TriPeaksGameScene(
                self.app, wrap_ak=wrap
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = tripeaks_mode.load_saved_game()
            if state:
                wrap = bool(state.get("wrap_ak", True))
                self.menu_scene.next_scene = tripeaks_mode.TriPeaksGameScene(
                    self.app,
                    wrap_ak=wrap,
                    load_state=state,
                )
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


# --- Monte Carlo -----------------------------------------------------


class MonteCarloController(GameOptionsController):
    def _has_save(self) -> bool:
        return monte_carlo_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                monte_carlo_mode._clear_saved_game()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.menu_scene.next_scene = monte_carlo_mode.MonteCarloGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = monte_carlo_mode.load_saved_game()
            if state:
                self.menu_scene.next_scene = monte_carlo_mode.MonteCarloGameScene(
                    self.app, load_state=state
                )
                return ActionResult(close_modal=True)
            self.set_message("No saved game found.")
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_back": "cancel", "b_continue": "resume"}


class DuchessDeLuynesController(GameOptionsController):
    def _has_save(self) -> bool:
        return duchess_de_luynes_mode.has_saved_game()

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            duchess_de_luynes_mode.delete_saved_game()
            self.menu_scene.next_scene = duchess_de_luynes_mode.LaDuchesseDeLuynesGameScene(self.app)
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = duchess_de_luynes_mode.load_saved_game()
            if state:
                self.menu_scene.next_scene = duchess_de_luynes_mode.LaDuchesseDeLuynesGameScene(
                    self.app, load_state=state
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


# --- Yukon -----------------------------------------------------------

from solitaire.modes import yukon as yukon_mode


class YukonController(GameOptionsController):
    def _has_save(self) -> bool:
        state = yukon_mode._safe_read_json(yukon_mode._yukon_save_path())
        return bool(state) and not state.get("completed", False)

    def buttons(self) -> Sequence[ButtonState]:
        return [
            ButtonState("cancel", "Cancel", variant="cancel"),
            ButtonState("resume", "Resume", enabled=self._has_save()),
            ButtonState("start", "Start", variant="primary"),
        ]

    def handle_button(self, key: str) -> ActionResult:
        if key == "cancel":
            return ActionResult(close_modal=True)
        if key == "start":
            try:
                import os

                save_path = yukon_mode._yukon_save_path()
                if os.path.isfile(save_path):
                    os.remove(save_path)
            except Exception:
                pass
            self.menu_scene.next_scene = yukon_mode.YukonGameScene(
                self.app, load_state=None
            )
            return ActionResult(close_modal=True)
        if key == "resume" and self._has_save():
            state = yukon_mode._safe_read_json(yukon_mode._yukon_save_path())
            if state:
                self.menu_scene.next_scene = yukon_mode.YukonGameScene(
                    self.app, load_state=state
                )
                return ActionResult(close_modal=True)
        return ActionResult(close_modal=False)

    def compatibility_actions(self) -> Dict[str, str]:
        return {"b_start": "start", "b_continue": "resume", "b_back": "cancel"}


CONTROLLER_REGISTRY = {
    "accordion": AccordionController,
    "beleaguered_castle": BeleagueredCastleController,
    "big_ben": BigBenController,
    "british_blockade": BritishBlockadeController,
    "british_square": BritishSquareController,
    "bowling_solitaire": BowlingSolitaireController,
    "chameleon": ChameleonController,
    "demon": DemonController,
    "duchess": DuchessController,
    "duchess_de_luynes": DuchessDeLuynesController,
    "freecell": FreeCellController,
    "gate": GateController,
    "golf": GolfController,
    "monte_carlo": MonteCarloController,
    "klondike": KlondikeController,
    "pyramid": PyramidController,
    "tripeaks": TriPeaksController,
    "yukon": YukonController,
}

