import importlib
import types

import pytest


def _verify_klondike(scene):
    assert scene.draw_count == 3
    assert scene.stock_cycles_allowed is None


def _verify_freecell(scene):
    assert len(scene.freecells) == 4
    assert len(scene.tableau) == 8


def _verify_pyramid(scene):
    assert scene.allowed_resets is None


def _verify_tripeaks(scene):
    assert scene.wrap_ak is True


def _verify_monte_carlo(scene):
    assert len(scene.tableau) == 5
    assert all(len(row) == 5 for row in scene.tableau)
    assert len(scene.stock_pile.cards) == 27
    assert not scene.can_compact()
    assert len(scene.matched_pile.cards) == 0


def _verify_gate(scene):
    assert len(scene.center) == 8
    assert len(scene.reserves) == 2


def _verify_beleaguered(scene):
    assert len(scene.foundations) == 4
    assert all(f.cards and f.cards[0].rank == 1 for f in scene.foundations)
    assert len(scene.tableau) == 8
    assert all(len(t.cards) == 6 for t in scene.tableau)


def _verify_big_ben(scene):
    assert len(scene.foundations) == 12
    assert [f.cards[-1].rank for f in scene.foundations] == [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    assert len(scene.tableau) == 12
    assert all(len(t.cards) == 3 for t in scene.tableau)
    assert len(scene.stock.cards) == 56
    assert len(scene.waste.cards) == 0


def _verify_golf(scene):
    assert scene.holes_total == 1
    assert scene.around is True


def _verify_yukon(scene):
    assert len(scene.tableau) == 7
    assert scene.scroll_x == 0
    assert scene.scroll_y == 0


MODES = [
    {
        "key": "klondike",
        "menu_index": 0,
        "module": "solitaire.modes.klondike",
        "game_class": "KlondikeGameScene",
        "verify": _verify_klondike,
        "has_save": False,
    },
    {
        "key": "freecell",
        "menu_index": 1,
        "module": "solitaire.modes.freecell",
        "game_class": "FreeCellGameScene",
        "verify": _verify_freecell,
        "has_save": False,
    },
    {
        "key": "pyramid",
        "menu_index": 2,
        "module": "solitaire.modes.pyramid",
        "game_class": "PyramidGameScene",
        "verify": _verify_pyramid,
        "has_save": False,
    },
    {
        "key": "tripeaks",
        "menu_index": 3,
        "module": "solitaire.modes.tripeaks",
        "game_class": "TriPeaksGameScene",
        "verify": _verify_tripeaks,
        "has_save": False,
    },
    {
        "key": "gate",
        "menu_index": 4,
        "module": "solitaire.modes.gate",
        "game_class": "GateGameScene",
        "verify": _verify_gate,
        "has_save": False,
    },
    {
        "key": "beleaguered_castle",
        "menu_index": 5,
        "module": "solitaire.modes.beleaguered_castle",
        "game_class": "BeleagueredCastleGameScene",
        "verify": _verify_beleaguered,
        "has_save": True,
    },
    {
        "key": "big_ben",
        "menu_index": 6,
        "module": "solitaire.modes.big_ben",
        "game_class": "BigBenGameScene",
        "verify": _verify_big_ben,
        "has_save": True,
    },
    {
        "key": "golf",
        "menu_index": 7,
        "module": "solitaire.modes.golf",
        "game_class": "GolfGameScene",
        "verify": _verify_golf,
        "has_save": True,
    },
    {
        "key": "monte_carlo",
        "menu_index": 9,
        "module": "solitaire.modes.monte_carlo",
        "game_class": "MonteCarloGameScene",
        "verify": _verify_monte_carlo,
        "has_save": True,
    },
    {
        "key": "yukon",
        "menu_index": 8,
        "module": "solitaire.modes.yukon",
        "game_class": "YukonGameScene",
        "verify": _verify_yukon,
        "has_save": True,
    },
]


@pytest.mark.parametrize("mode", MODES, ids=[m["key"] for m in MODES])
def test_application_flow(monkeypatch, mode):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")

    pygame = importlib.import_module("pygame")

    class DummyFont:
        def __init__(self, size):
            self._size = max(1, int(size) if size else 1)

        def render(self, text, *_, **__):
            width = max(1, len(str(text)) * max(self._size // 2, 1))
            height = max(1, self._size)
            return pygame.Surface((width, height), pygame.SRCALPHA)

        def size(self, text):
            width = max(1, len(str(text)) * max(self._size // 2, 1))
            return width, max(1, self._size)

        def get_height(self):
            return max(1, self._size)

    def _make_font(size):
        return DummyFont(size or 24)

    monkeypatch.setattr(
        pygame.font,
        "SysFont",
        lambda *args, size=None, **kwargs: _make_font(size if size is not None else (args[1] if len(args) > 1 else None)),
        raising=False,
    )
    monkeypatch.setattr(
        pygame.font,
        "Font",
        lambda *args, size=None, **kwargs: _make_font(size if size is not None else (args[1] if len(args) > 1 else None)),
        raising=False,
    )
    monkeypatch.setattr(pygame.font, "get_default_font", lambda: "dummy", raising=False)

    entry = importlib.import_module("solitaire.__main__")
    title_module = importlib.import_module("solitaire.scenes.title")
    menu_module = importlib.import_module("solitaire.scenes.menu")
    target_module = importlib.import_module(mode["module"])

    transitions = []
    captured = {}

    class DummyClock:
        def tick(self, _fps):
            return 16

    monkeypatch.setattr(pygame.time, "Clock", lambda: DummyClock())
    monkeypatch.setattr(pygame.display, "Info", lambda: types.SimpleNamespace(current_w=1600, current_h=900))
    monkeypatch.setattr(pygame.display, "set_mode", lambda size, flags=0: pygame.Surface(size))
    monkeypatch.setattr(pygame.display, "flip", lambda: None)
    monkeypatch.setattr(pygame.display, "set_caption", lambda _title: None)

    target_size = (1024, 768)
    monkeypatch.setattr(entry, "_initial_window_size", lambda: target_size)

    orig_title_cls = title_module.TitleScene

    class LoggedTitleScene(orig_title_cls):
        def __init__(self, app):
            super().__init__(app)
            transitions.append("TitleScene")

    monkeypatch.setattr(title_module, "TitleScene", LoggedTitleScene)

    orig_menu_cls = menu_module.MainMenuScene

    class LoggedMainMenu(orig_menu_cls):
        def __init__(self, app):
            super().__init__(app)
            transitions.append("MainMenuScene")
            captured["menu_scene"] = self

        def _open_game_modal(self, game_key: str, *, proxy=None):  # type: ignore[override]
            opened = super()._open_game_modal(game_key, proxy=proxy)
            if opened:
                transitions.append(f"Modal:{game_key}")
            return opened

    monkeypatch.setattr(menu_module, "MainMenuScene", LoggedMainMenu)
    monkeypatch.setattr(entry, "MainMenuScene", LoggedMainMenu)

    orig_game_cls = getattr(target_module, mode["game_class"])

    class LoggedGameScene(orig_game_cls):
        def __init__(self, app, *args, **kwargs):
            super().__init__(app, *args, **kwargs)
            transitions.append(mode["game_class"])
            captured["game_scene"] = self

    monkeypatch.setattr(target_module, mode["game_class"], LoggedGameScene)

    last_mouse = [0, 0]
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: (last_mouse[0], last_mouse[1]))

    def _click_pos(pos):
        mx, my = pos
        move = pygame.event.Event(pygame.MOUSEMOTION, {"pos": (mx, my), "rel": (0, 0), "buttons": (0, 0, 0)})
        down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (mx, my), "button": 1})
        return [move, down]

    def _click_toolbar_menu():
        scene = captured.get("game_scene")
        assert scene is not None, "Game scene not captured"
        toolbar = getattr(scene, "toolbar", None)
        assert toolbar is not None, "Toolbar missing on game scene"
        for button in getattr(toolbar, "buttons", []):
            if getattr(button, "label", "") == "Menu":
                rect = getattr(button, "rect", None)
                assert rect is not None, "Menu button missing rect"
                return _click_pos(rect.center)
        raise AssertionError("Menu button not found on toolbar")

    def _click_menu_entry():
        scene = captured.get("menu_scene")
        assert scene is not None, f"menu_scene should be available for {mode['key']}"
        getter = getattr(scene, "get_entry_rect", None)
        assert callable(getter), "Main menu does not expose get_entry_rect"
        rect = getter(mode["key"])
        assert rect is not None, f"No entry rect for {mode['key']}"
        return _click_pos(rect.center)

    def _click_modal_button(action_key: str):
        scene = captured.get("menu_scene")
        assert scene is not None, "Main menu not captured"
        modal = getattr(scene, "_options_modal", None)
        assert modal is not None, "Options modal not available"
        rect = modal.get_action_rect(action_key)
        assert rect is not None, f"Modal action {action_key} not found"
        return _click_pos(rect.center)

    def _click_game_menu_button(action_key: str):
        scene = captured.get("game_scene")
        assert scene is not None, "Game scene not captured"
        helper = getattr(scene, "ui_helper", None)
        assert helper is not None, "ui_helper missing"
        modal = getattr(helper, "menu_modal", None)
        assert modal is not None, "Game menu modal missing"
        buttons = getattr(modal, "_buttons", [])
        keys = getattr(modal, "_button_keys", [])
        for key, button in zip(keys, buttons):
            if key == action_key:
                rect = getattr(button, "rect", None)
                assert rect is not None, f"Button rect missing for {action_key}"
                return _click_pos(rect.center)
        raise AssertionError(f"Action {action_key} not found in game menu")

    def _menu_exit_action():
        scene = captured.get("game_scene")
        assert scene is not None, "Game scene not captured"
        helper = getattr(scene, "ui_helper", None)
        assert helper is not None, "ui_helper missing"
        modal = helper.menu_modal
        assert modal is not None, "menu_modal missing"
        action = "save" if mode["has_save"] and modal._actions.get("save") else "quit_menu"  # type: ignore[attr-defined]
        return action

    event_steps = [
        lambda: [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})],
        _click_menu_entry,
        lambda: _click_modal_button("start"),
        _click_toolbar_menu,
        lambda: _click_game_menu_button(_menu_exit_action()),
        lambda: [pygame.event.Event(pygame.QUIT, {})],
        lambda: [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})],
    ]

    index = {"value": 0}

    def scripted_events():
        step = index["value"]
        if step >= len(event_steps):
            return []
        events = event_steps[step]()
        assert events, f"No events returned for step {step} ({mode['key']})"
        for ev in events:
            if hasattr(ev, "pos"):
                last_mouse[0], last_mouse[1] = ev.pos
        index["value"] += 1
        return events

    monkeypatch.setattr(pygame.event, "get", scripted_events)

    quit_calls = []
    real_quit = pygame.quit

    def tracked_quit():
        quit_calls.append(True)
        real_quit()

    monkeypatch.setattr(pygame, "quit", tracked_quit)

    entry.main()

    assert quit_calls, "pygame.quit() should be called"

    assert transitions[0:2] == ["TitleScene", "MainMenuScene"]
    assert mode["game_class"] in transitions, f"{mode['game_class']} did not start"
    assert transitions.count("MainMenuScene") >= 2, "Should return to main menu after exiting the game"

    game_scene = captured.get("game_scene")
    assert game_scene is not None, "Game scene should be captured"
    mode["verify"](game_scene)

