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
        "options_module": "solitaire.scenes.game_options.klondike_options",
        "options_class": "KlondikeOptionsScene",
        "game_class": "KlondikeGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": False,
        "verify": _verify_klondike,
    },
    {
        "key": "freecell",
        "menu_index": 1,
        "module": "solitaire.modes.freecell",
        "options_module": "solitaire.scenes.game_options.freecell_options",
        "options_class": "FreeCellOptionsScene",
        "game_class": "FreeCellGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": False,
        "verify": _verify_freecell,
    },
    {
        "key": "pyramid",
        "menu_index": 2,
        "module": "solitaire.modes.pyramid",
        "options_module": "solitaire.scenes.game_options.pyramid_options",
        "options_class": "PyramidOptionsScene",
        "game_class": "PyramidGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": False,
        "verify": _verify_pyramid,
    },
    {
        "key": "tripeaks",
        "menu_index": 3,
        "module": "solitaire.modes.tripeaks",
        "options_module": "solitaire.scenes.game_options.tripeaks_options",
        "options_class": "TriPeaksOptionsScene",
        "game_class": "TriPeaksGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": False,
        "verify": _verify_tripeaks,
    },
    {
        "key": "gate",
        "menu_index": 4,
        "module": "solitaire.modes.gate",
        "options_module": "solitaire.scenes.game_options.gate_options",
        "options_class": "GateOptionsScene",
        "game_class": "GateGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": False,
        "verify": _verify_gate,
    },
    {
        "key": "beleaguered_castle",
        "menu_index": 5,
        "module": "solitaire.modes.beleaguered_castle",
        "options_module": "solitaire.scenes.game_options.beleaguered_castle_options",
        "options_class": "BeleagueredCastleOptionsScene",
        "game_class": "BeleagueredCastleGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": True,
        "verify": _verify_beleaguered,
    },
    {
        "key": "big_ben",
        "menu_index": 6,
        "module": "solitaire.modes.big_ben",
        "options_module": "solitaire.scenes.game_options.big_ben_options",
        "options_class": "BigBenOptionsScene",
        "game_class": "BigBenGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": True,
        "verify": _verify_big_ben,
    },
    {
        "key": "golf",
        "menu_index": 7,
        "module": "solitaire.modes.golf",
        "options_module": "solitaire.scenes.game_options.golf_options",
        "options_class": "GolfOptionsScene",
        "game_class": "GolfGameScene",
        "start_attr": "b_new1",
        "back_attr": "b_back",
        "returns_to_options": True,
        "verify": _verify_golf,
    },
    {
        "key": "yukon",
        "menu_index": 8,
        "module": "solitaire.modes.yukon",
        "options_module": "solitaire.scenes.game_options.yukon_options",
        "options_class": "YukonOptionsScene",
        "game_class": "YukonGameScene",
        "start_attr": "b_start",
        "back_attr": "b_back",
        "returns_to_options": True,
        "verify": _verify_yukon,
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

    # Prefer new options module path; fall back to mode module if not yet refactored
    options_module_name = mode.get("options_module", mode["module"])
    try:
        options_module = importlib.import_module(options_module_name)
    except Exception:
        options_module = target_module

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

    monkeypatch.setattr(menu_module, "MainMenuScene", LoggedMainMenu)
    monkeypatch.setattr(entry, "MainMenuScene", LoggedMainMenu)

    orig_options_cls = getattr(options_module, mode["options_class"])

    class LoggedOptionsScene(orig_options_cls):
        def __init__(self, app):
            super().__init__(app)
            transitions.append(mode["options_class"])
            captured["options_scene"] = self

    monkeypatch.setattr(options_module, mode["options_class"], LoggedOptionsScene)

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

    def _click_button(scene_key, attr):
        scene = captured.get(scene_key)
        assert scene is not None, f"{scene_key} should be available for {mode['key']}"
        button = getattr(scene, attr, None)
        assert button is not None, f"{attr} missing on {scene}"
        rect = getattr(button, "rect", None)
        assert rect is not None, f"{attr} missing rect"
        cx, cy = rect.center
        return _click_pos((cx, cy))

    def _click_toolbar_menu():
        scene = captured.get("game_scene")
        assert scene is not None, "Game scene not captured"
        toolbar = getattr(scene, "toolbar", None)
        assert toolbar is not None, "Toolbar missing on game scene"
        for button in getattr(toolbar, "buttons", []):
            if getattr(button, "label", "") == "Menu":
                rect = getattr(button, "rect", None)
                assert rect is not None, "Menu button missing rect"
                events = _click_pos(rect.center)
                getter = getattr(button, "get_menu_item_rect", None)
                if callable(getter):
                    item_rect = getter("Menu")
                    if item_rect is not None:
                        events.extend(_click_pos(item_rect.center))
                return events
        raise AssertionError("Menu button not found on toolbar")

    def _click_menu_entry():
        scene = captured.get("menu_scene")
        assert scene is not None, f"menu_scene should be available for {mode['key']}"
        getter = getattr(scene, "get_entry_rect", None)
        assert callable(getter), "Main menu does not expose get_entry_rect"
        rect = getter(mode["key"])
        assert rect is not None, f"No entry rect for {mode['key']}"
        return _click_pos(rect.center)

    event_steps = [
        lambda: [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})],
        _click_menu_entry,
        lambda: _click_button("options_scene", mode["start_attr"]),
        _click_toolbar_menu,
    ]

    if mode["returns_to_options"]:
        event_steps.append(lambda: _click_button("options_scene", mode["back_attr"]))

    event_steps.extend([
        lambda: [pygame.event.Event(pygame.QUIT, {})],
        lambda: [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN, "mod": 0})],
    ])

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

    expected_prefix = [
        "TitleScene",
        "MainMenuScene",
        mode["options_class"],
        mode["game_class"],
    ]
    assert transitions[: len(expected_prefix)] == expected_prefix

    game_scene = captured.get("game_scene")
    assert game_scene is not None, "Game scene should be captured"
    mode["verify"](game_scene)

