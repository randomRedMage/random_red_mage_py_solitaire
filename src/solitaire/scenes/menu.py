# menu.py - Main menu
import os
from math import ceil

import pygame

from solitaire import common as C
from solitaire.modes.base_scene import GAME_REGISTRY, GAME_SECTIONS, GameMetadata
from solitaire.scenes.menu_options import (
    CONTROLLER_REGISTRY,
    ButtonState,
    GameOptionsController,
    OptionState,
)


class _GameEntry:
    __slots__ = (
        "metadata",
        "key",
        "label",
        "icon_filename",
        "module",
        "scene_cls",
        "surface",
        "rect",
        "label_surf",
        "label_rect",
    )

    def __init__(self, metadata: GameMetadata):
        self.metadata = metadata
        self.key = metadata.key
        self.label = metadata.label
        self.icon_filename = metadata.icon_filename
        self.module = metadata.options_module
        self.scene_cls = metadata.options_class
        self.surface: pygame.Surface | None = None
        self.rect = pygame.Rect(0, 0, 128, 128)
        self.label_surf: pygame.Surface | None = None
        self.label_rect = pygame.Rect(0, 0, 0, 0)


class _OptionRowLayout:
    __slots__ = ("key", "label_y", "value_rect", "left_rect", "right_rect")

    def __init__(self, key: str, label_y: int, value_rect, left_rect, right_rect) -> None:
        self.key = key
        self.label_y = label_y
        self.value_rect = value_rect
        self.left_rect = left_rect
        self.right_rect = right_rect


class _ActionLayout:
    __slots__ = ("key", "rect")

    def __init__(self, key: str, rect: pygame.Rect) -> None:
        self.key = key
        self.rect = rect


class GameOptionsModal:
    WIDTH = 680
    PADDING_X = 48
    PADDING_TOP = 96
    OPTION_GAP = 32
    OPTION_HEIGHT = 56
    OPTION_ARROW = 48
    OPTION_ARROW_GAP = 16
    MESSAGE_HEIGHT = 32
    BUTTON_HEIGHT = 56
    BUTTON_GAP = 20
    BOTTOM_PADDING = 70

    def __init__(self, scene: "MainMenuScene", controller: GameOptionsController) -> None:
        self.scene = scene
        self.controller = controller
        self.rect = pygame.Rect(0, 0, self.WIDTH, 400)
        self.rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._options_layout: list[_OptionRowLayout] = []
        self._actions_layout: list[_ActionLayout] = []
        self._option_signature: tuple[str, ...] = ()
        self._button_signature: tuple[str, ...] = ()
        self._message_rect = pygame.Rect(0, 0, 0, 0)
        self._title_pos = (0, 0)
        self._reflow()

    # ----- layout ----------------------------------------------------
    def _option_rows(self) -> list[OptionState]:
        return list(self.controller.options())

    def _button_rows(self) -> list[ButtonState]:
        return list(self.controller.buttons())

    def _reflow(self) -> None:
        options = self._option_rows()
        buttons = self._button_rows()
        option_keys = tuple(opt.key for opt in options)
        button_keys = tuple(btn.key for btn in buttons)
        if option_keys == self._option_signature and button_keys == self._button_signature:
            return
        self._option_signature = option_keys
        self._button_signature = button_keys

        label_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        label_height = label_font.get_height()

        current_y = self.PADDING_TOP
        relative_rows = []
        for opt in options:
            label_y = current_y
            current_y += label_height + 10
            value_y = current_y
            current_y += self.OPTION_HEIGHT + self.OPTION_GAP
            relative_rows.append((opt.key, label_y, value_y))

        message_top = current_y
        action_top = message_top + self.MESSAGE_HEIGHT + 10
        total_height = action_top + self.BUTTON_HEIGHT + self.BOTTOM_PADDING
        self.rect = pygame.Rect(0, 0, self.WIDTH, total_height)
        self.rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._title_pos = (self.rect.centerx, self.rect.y + 46)

        self._options_layout = []
        value_width = self.rect.width - 2 * self.PADDING_X - 2 * (self.OPTION_ARROW + self.OPTION_ARROW_GAP)
        for key, label_y, value_y in relative_rows:
            label_y_abs = self.rect.y + label_y
            value_rect = pygame.Rect(
                self.rect.x + self.PADDING_X + self.OPTION_ARROW + self.OPTION_ARROW_GAP,
                self.rect.y + value_y,
                value_width,
                self.OPTION_HEIGHT,
            )
            left_rect = pygame.Rect(
                value_rect.left - self.OPTION_ARROW - self.OPTION_ARROW_GAP,
                value_rect.y,
                self.OPTION_ARROW,
                self.OPTION_HEIGHT,
            )
            right_rect = pygame.Rect(
                value_rect.right + self.OPTION_ARROW_GAP,
                value_rect.y,
                self.OPTION_ARROW,
                self.OPTION_HEIGHT,
            )
            self._options_layout.append(_OptionRowLayout(key, label_y_abs, value_rect, left_rect, right_rect))

        self._message_rect = pygame.Rect(
            self.rect.x + self.PADDING_X,
            self.rect.y + message_top,
            self.rect.width - 2 * self.PADDING_X,
            self.MESSAGE_HEIGHT,
        )

        actions = []
        if buttons:
            available_width = self.rect.width - 2 * self.PADDING_X
            btn_count = len(buttons)
            button_width = min(200, max(120, (available_width - self.BUTTON_GAP * (btn_count - 1)) // btn_count))
            total_width = button_width * btn_count + self.BUTTON_GAP * (btn_count - 1)
            start_x = self.rect.x + self.PADDING_X + (available_width - total_width) // 2
            button_y = self.rect.y + action_top
            for index, btn in enumerate(buttons):
                rect = pygame.Rect(start_x + index * (button_width + self.BUTTON_GAP), button_y, button_width, self.BUTTON_HEIGHT)
                actions.append(_ActionLayout(btn.key, rect))
        self._actions_layout = actions

    # ----- event handling -------------------------------------------
    def handle_event(self, event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                return True
            option_map = {opt.key: opt for opt in self._option_rows()}
            for layout in self._options_layout:
                opt = option_map.get(layout.key)
                if opt is None or len(opt.values) <= 1:
                    continue
                if layout.left_rect.collidepoint(event.pos):
                    self.controller.change_option(layout.key, -1)
                    self._reflow()
                    return False
                if layout.right_rect.collidepoint(event.pos):
                    self.controller.change_option(layout.key, 1)
                    self._reflow()
                    return False
            button_states = {btn.key: btn for btn in self._button_rows()}
            for layout in self._actions_layout:
                state = button_states.get(layout.key)
                if state is None:
                    continue
                if not state.enabled:
                    continue
                if layout.rect.collidepoint(event.pos):
                    result = self.controller.handle_button(layout.key)
                    self._reflow()
                    return result.close_modal
        return False

    def get_action_rect(self, key: str) -> pygame.Rect | None:
        for layout in self._actions_layout:
            if layout.key == key:
                return layout.rect.copy()
        return None

    # ----- drawing --------------------------------------------------
    def _draw_arrow_button(self, screen, rect: pygame.Rect, direction: str, enabled: bool, hover: bool) -> None:
        base = (200, 200, 205)
        hover_col = (230, 210, 120)
        disabled = (160, 160, 160)
        color = disabled if not enabled else (hover_col if hover else base)
        pygame.draw.rect(screen, color, rect, border_radius=rect.height // 2)
        border_col = (80, 80, 85)
        pygame.draw.rect(screen, border_col, rect, width=2, border_radius=rect.height // 2)
        cx = rect.centerx
        cy = rect.centery
        size = rect.height // 3
        if direction == "left":
            points = [(cx + size // 2, cy - size), (cx - size, cy), (cx + size // 2, cy + size)]
        else:
            points = [(cx - size // 2, cy - size), (cx + size, cy), (cx - size // 2, cy + size)]
        pygame.draw.polygon(screen, border_col if enabled else (110, 110, 110), points)

    def _draw_value_box(self, screen, rect: pygame.Rect, text: str) -> None:
        pygame.draw.rect(screen, (245, 245, 245), rect, border_radius=rect.height // 2)
        pygame.draw.rect(screen, (90, 90, 90), rect, width=2, border_radius=rect.height // 2)
        font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        surf = font.render(text, True, (40, 40, 45))
        screen.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))

    def _draw_action_button(self, screen, rect: pygame.Rect, state: ButtonState, hover: bool) -> None:
        if state.variant == "primary":
            base = (230, 200, 90)
            hover_col = (240, 210, 110)
        elif state.variant == "cancel":
            base = (210, 210, 210)
            hover_col = (230, 230, 230)
        else:
            base = (210, 210, 210)
            hover_col = (225, 225, 225)
        disabled = (170, 170, 170)
        color = disabled if not state.enabled else (hover_col if hover else base)
        pygame.draw.rect(screen, color, rect, border_radius=18)
        pygame.draw.rect(screen, (60, 60, 65), rect, width=2, border_radius=18)
        font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 24, bold=True)
        text_color = (40, 40, 40)
        surf = font.render(state.label, True, text_color)
        screen.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))

    def draw(self, screen) -> None:
        self.controller.refresh()
        self._reflow()

        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        screen.blit(overlay, (0, 0))

        pygame.draw.rect(screen, (250, 250, 250), self.rect, border_radius=28)
        pygame.draw.rect(screen, (70, 70, 70), self.rect, width=2, border_radius=28)

        title_font = C.FONT_TITLE or pygame.font.SysFont(pygame.font.get_default_font(), 42, bold=True)
        title_text = self.controller.title()
        title_surf = title_font.render(title_text, True, (40, 40, 45))
        screen.blit(title_surf, (self._title_pos[0] - title_surf.get_width() // 2, self._title_pos[1]))

        label_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
        options_map = {opt.key: opt for opt in self._option_rows()}
        mp = pygame.mouse.get_pos()
        for layout in self._options_layout:
            opt = options_map.get(layout.key)
            if opt is None:
                continue
            label_surf = label_font.render(opt.label, True, (60, 60, 65))
            screen.blit(label_surf, (self.rect.centerx - label_surf.get_width() // 2, layout.label_y))
            value_text = opt.current_text()
            self._draw_value_box(screen, layout.value_rect, value_text)
            arrows_enabled = len(opt.values) > 1
            self._draw_arrow_button(
                screen,
                layout.left_rect,
                "left",
                arrows_enabled,
                arrows_enabled and layout.left_rect.collidepoint(mp),
            )
            self._draw_arrow_button(
                screen,
                layout.right_rect,
                "right",
                arrows_enabled,
                arrows_enabled and layout.right_rect.collidepoint(mp),
            )

        message = self.controller.message
        if message:
            msg_font = C.FONT_SMALL or pygame.font.SysFont(pygame.font.get_default_font(), 20)
            msg_surf = msg_font.render(message, True, (160, 30, 30))
            screen.blit(
                msg_surf,
                (
                    self._message_rect.centerx - msg_surf.get_width() // 2,
                    self._message_rect.centery - msg_surf.get_height() // 2,
                ),
            )

        button_states = {btn.key: btn for btn in self._button_rows()}
        for layout in self._actions_layout:
            state = button_states.get(layout.key)
            if state is None:
                continue
            hover = state.enabled and layout.rect.collidepoint(mp)
            self._draw_action_button(screen, layout.rect, state, hover)


class MainMenuScene(C.Scene):
    ICON_SIZE = 128
    ICON_GAP = 24
    LABEL_MARGIN = 10

    SECTION_PADDING = 28
    SECTION_TITLE_GAP = 18
    SECTION_VERTICAL_GAP = 48
    SECTION_OUTER_MARGIN_X = 80
    SECTION_BG = (248, 248, 248)
    SECTION_BORDER = (0, 0, 0)
    SECTION_BORDER_RADIUS = 26

    SCROLL_MIN_TOP = 140
    SCROLL_BOTTOM_MARGIN = 80
    SCROLLBAR_WIDTH = 14
    SCROLL_STEP = 48

    def __init__(self, app, *, open_game_key: str | None = None):
        super().__init__(app)
        self._menu_button_rect = pygame.Rect(0, 0, 56, 40)
        self._menu_margin = (28, 24)
        self._menu_hover = False
        self._modal_open = False
        self._options_modal: GameOptionsModal | None = None
        self._options_proxy = None
        self._pending_open_key = open_game_key
        self._hover_entry: _GameEntry | None = None

        icon_dir = os.path.join(os.path.dirname(C.__file__), "assets", "images", "game_icons")
        self._icon_dir = icon_dir

        self._sections = []
        for title, game_keys in GAME_SECTIONS:
            entries: list[_GameEntry] = []
            for key in game_keys:
                meta = GAME_REGISTRY.get(key)
                if meta is None:
                    continue
                entries.append(_GameEntry(meta))
            if not entries:
                continue
            self._sections.append(
                {
                    "title": title,
                    "entries": entries,
                    "rect": pygame.Rect(0, 0, 0, 0),
                    "title_surf": None,
                    "title_rect": pygame.Rect(0, 0, 0, 0),
                }
            )

        self._entry_lookup = {}
        for section in self._sections:
            for entry in section["entries"]:
                self._entry_lookup[entry.key] = entry

        self._modal_rect = pygame.Rect(0, 0, 520, 360)
        self._modal_padding_top = 130
        self._modal_padding_bottom = 70
        self._modal_gap = 26
        self._modal_settings = C.Button("Settings", 0, 0, center=True)
        self._modal_back = C.Button("Back to Menu", 0, 0, center=True)
        self._modal_quit = C.Button("Quit Game", 0, 0, center=True)
        self._modal_buttons = [self._modal_settings, self._modal_back, self._modal_quit]

        # Scroll state
        self._scroll_offset = 0
        self._max_scroll = 0
        self._viewport_height = 0
        self._content_start = self.SCROLL_MIN_TOP
        self._content_total_height = 0
        self._scroll_track_rect = pygame.Rect(0, 0, 0, 0)
        self._scroll_thumb_rect = pygame.Rect(0, 0, 0, 0)
        self._scroll_dragging = False
        self._scroll_drag_anchor = 0
        self._scroll_drag_start_offset = 0

        self._prepare_assets()
        self.compute_layout()
        if self._pending_open_key:
            self._open_game_modal(self._pending_open_key)
            self._pending_open_key = None

    # --- asset helpers -------------------------------------------------
    def _prepare_assets(self):
        font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 28, bold=True)
        section_font = C.FONT_TITLE if C.FONT_TITLE is not None else pygame.font.SysFont(pygame.font.get_default_font(), 38, bold=True)
        for section in self._sections:
            section["title_surf"] = section_font.render(section["title"], True, (40, 40, 40))
            for entry in section["entries"]:
                entry.surface = self._load_icon(entry.icon_filename)
                entry.label_surf = self._render_label(font, entry.label)
                entry.label_rect = entry.label_surf.get_rect()

    def _render_label(self, font: pygame.font.Font, text: str) -> pygame.Surface:
        lines = text.split("\n")
        surfaces = [font.render(line, True, (35, 35, 40)) for line in lines]
        max_w = max((surf.get_width() for surf in surfaces), default=0)
        total_h = sum(surf.get_height() for surf in surfaces) + max(0, len(surfaces) - 1) * 4
        label = pygame.Surface((max_w, total_h), pygame.SRCALPHA)
        y = 0
        for surf in surfaces:
            label.blit(surf, ((max_w - surf.get_width()) // 2, y))
            y += surf.get_height() + 4
        return label

    def _load_icon(self, filename: str) -> pygame.Surface:
        icon_path = os.path.join(self._icon_dir, filename)
        surf = None
        try:
            if os.path.isfile(icon_path):
                loaded = pygame.image.load(icon_path)
                surf = loaded.convert_alpha() if loaded.get_alpha() else loaded.convert()
        except Exception:
            surf = None
        if surf is None:
            surf = pygame.Surface((self.ICON_SIZE, self.ICON_SIZE), pygame.SRCALPHA)
            surf.fill((120, 120, 130))
            pygame.draw.line(surf, (200, 200, 210), (0, 0), (self.ICON_SIZE, self.ICON_SIZE), 4)
            pygame.draw.line(surf, (200, 200, 210), (0, self.ICON_SIZE), (self.ICON_SIZE, 0), 4)
        elif surf.get_size() != (self.ICON_SIZE, self.ICON_SIZE):
            surf = pygame.transform.smoothscale(surf, (self.ICON_SIZE, self.ICON_SIZE))
        return surf

    # --- layout --------------------------------------------------------
    def compute_layout(self):
        sections_info = []
        margin_x = min(self.SECTION_OUTER_MARGIN_X, max(20, (C.SCREEN_W - 640) // 4))
        available_width = max(self.ICON_SIZE, C.SCREEN_W - margin_x * 2)

        for section in self._sections:
            entries = section["entries"]
            columns = max(1, min(len(entries), (available_width + self.ICON_GAP) // (self.ICON_SIZE + self.ICON_GAP)))
            rows = ceil(len(entries) / columns)
            content_width = columns * self.ICON_SIZE + (columns - 1) * self.ICON_GAP
            max_label_height = max((entry.label_surf.get_height() if entry.label_surf else 0) for entry in entries)
            row_height = self.ICON_SIZE + self.LABEL_MARGIN + max_label_height
            content_height = rows * row_height + (rows - 1) * self.ICON_GAP
            title_surf: pygame.Surface = section["title_surf"]
            title_height = title_surf.get_height()
            section_width = content_width + self.SECTION_PADDING * 2
            section_height = content_height + self.SECTION_PADDING * 2 + title_height + self.SECTION_TITLE_GAP
            sections_info.append({
                "section": section,
                "columns": columns,
                "rows": rows,
                "content_width": content_width,
                "row_height": row_height,
                "section_width": section_width,
                "section_height": section_height,
                "title_height": title_height,
            })

        total_height = sum(info["section_height"] for info in sections_info)
        if sections_info:
            total_height += self.SECTION_VERTICAL_GAP * (len(sections_info) - 1)

        available_height = max(120, C.SCREEN_H - (self.SCROLL_MIN_TOP + self.SCROLL_BOTTOM_MARGIN))
        if total_height <= available_height:
            start_top = self.SCROLL_MIN_TOP + (available_height - total_height) // 2
            self._max_scroll = 0
            self._scroll_offset = 0
        else:
            start_top = self.SCROLL_MIN_TOP
            self._max_scroll = total_height - available_height
            self._scroll_offset = max(0, min(self._scroll_offset, self._max_scroll))
        self._viewport_height = available_height
        self._content_start = start_top
        self._content_total_height = total_height

        top = start_top
        for info in sections_info:
            section = info["section"]
            rect = section["rect"]
            rect.size = (info["section_width"], info["section_height"])
            rect.centerx = C.SCREEN_W // 2
            rect.top = top

            title_rect = section["title_surf"].get_rect()
            title_rect.centerx = rect.centerx
            title_rect.top = rect.top + self.SECTION_PADDING
            section["title_rect"] = title_rect

            grid_left = rect.left + self.SECTION_PADDING
            grid_top = title_rect.bottom + self.SECTION_TITLE_GAP

            columns = info["columns"]
            row_height = info["row_height"]
            for index, entry in enumerate(section["entries"]):
                col = index % columns
                row = index // columns
                x = grid_left + col * (self.ICON_SIZE + self.ICON_GAP)
                y = grid_top + row * (row_height + self.ICON_GAP)
                entry.rect.topleft = (x, y)
                entry.label_rect.centerx = entry.rect.centerx
                entry.label_rect.top = entry.rect.bottom + self.LABEL_MARGIN

            top = rect.bottom + self.SECTION_VERTICAL_GAP

        margin_x, margin_y = self._menu_margin
        self._menu_button_rect.topright = (C.SCREEN_W - margin_x, margin_y)
        self._modal_rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._position_modal_buttons()
        self._update_scrollbar_rects()
        if not self._max_scroll:
            self._scroll_dragging = False

    def _position_modal_buttons(self):
        gap = self._modal_gap
        cx = self._modal_rect.centerx
        total_height = sum(btn.rect.height for btn in self._modal_buttons)
        total_gap = gap * (len(self._modal_buttons) - 1)
        available_height = self._modal_rect.height - self._modal_padding_top - self._modal_padding_bottom
        if total_height + total_gap > available_height:
            gap = max(8, gap - ((total_height + total_gap) - available_height) // max(1, len(self._modal_buttons) - 1))
            total_gap = gap * (len(self._modal_buttons) - 1)
        start_top = self._modal_rect.y + self._modal_padding_top
        current_y = start_top
        for btn in self._modal_buttons:
            btn.rect.center = (cx, current_y + btn.rect.height // 2)
            current_y += btn.rect.height + gap

    def _update_scrollbar_rects(self):
        if self._viewport_height <= 0:
            self._scroll_track_rect = pygame.Rect(0, 0, 0, 0)
            self._scroll_thumb_rect = pygame.Rect(0, 0, 0, 0)
            return
        track_x = C.SCREEN_W - self.SCROLLBAR_WIDTH - 32
        self._scroll_track_rect = pygame.Rect(track_x, self._content_start, self.SCROLLBAR_WIDTH, self._viewport_height)
        if self._max_scroll <= 0:
            self._scroll_thumb_rect = pygame.Rect(track_x, self._content_start, self.SCROLLBAR_WIDTH, self._viewport_height)
            return
        ratio = min(1.0, self._viewport_height / float(self._content_total_height)) if self._content_total_height else 0
        thumb_h = max(40, int(self._viewport_height * ratio))
        thumb_h = min(self._viewport_height, thumb_h)
        travel = max(1, self._viewport_height - thumb_h)
        thumb_y = self._content_start + int((self._scroll_offset / self._max_scroll) * travel)
        self._scroll_thumb_rect = pygame.Rect(track_x, thumb_y, self.SCROLLBAR_WIDTH, thumb_h)

    def _scroll_by(self, delta: int):
        if self._max_scroll <= 0:
            self._scroll_offset = 0
            return
        self._scroll_offset = max(0, min(self._max_scroll, self._scroll_offset + delta))
        self._update_scrollbar_rects()

    def _to_content_pos(self, pos):
        return pos[0], pos[1] + self._scroll_offset

    def get_entry_rect(self, key: str):
        entry = self._entry_lookup.get(key)
        if entry is None:
            return None
        rect = entry.rect.copy()
        rect.y -= self._scroll_offset
        return rect

    # --- interaction ---------------------------------------------------
    def _open_game_modal(self, game_key: str, *, proxy=None) -> None:
        entry = self._entry_lookup.get(game_key)
        if entry is None:
            return
        self._open_game_modal_for_entry(entry, proxy=proxy)

    def _open_game_modal_for_entry(self, entry: _GameEntry, *, proxy=None) -> bool:
        controller_cls = CONTROLLER_REGISTRY.get(entry.key)
        if controller_cls is None:
            return False
        controller = controller_cls(self, metadata=entry.metadata)
        self._options_modal = GameOptionsModal(self, controller)
        self._prepare_options_proxy(entry, controller, proxy=proxy)
        return True

    def _prepare_options_proxy(self, entry: _GameEntry, controller: GameOptionsController, *, proxy=None) -> None:
        self._options_proxy = None
        if self._options_modal is None:
            return
        if proxy is None:
            if not entry.scene_cls or not entry.module:
                return
            try:
                module = __import__(entry.module, fromlist=[entry.scene_cls])
                scene_cls = getattr(module, entry.scene_cls)
                proxy = scene_cls(self.app)
            except Exception:
                return
        mapping = controller.compatibility_actions()
        for attr, action_key in mapping.items():
            btn = getattr(proxy, attr, None)
            if btn is None:
                continue
            rect = self._options_modal.get_action_rect(action_key)
            if rect is None:
                continue
            btn.rect.size = rect.size
            btn.rect.center = rect.center
        self._options_proxy = proxy

    def _activate_entry(self, entry: _GameEntry):
        if self._modal_open:
            return
        if not self._open_game_modal_for_entry(entry):
            try:
                module = __import__(entry.module, fromlist=[entry.scene_cls])
                scene_cls = getattr(module, entry.scene_cls)
                self.next_scene = scene_cls(self.app)
            except Exception:
                pass
            return

    def _handle_modal_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._modal_open = False
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._modal_settings.hovered((mx, my)):
                from solitaire.scenes.settings import SettingsScene
                self._modal_open = False
                self.next_scene = SettingsScene(self.app)
            elif self._modal_back.hovered((mx, my)):
                self._modal_open = False
            elif self._modal_quit.hovered((mx, my)):
                pygame.quit()
                raise SystemExit
            elif not self._modal_rect.collidepoint((mx, my)):
                self._modal_open = False
            return

    def handle_event(self, e):
        if e.type == pygame.MOUSEWHEEL and not self._modal_open:
            if self._max_scroll > 0:
                self._scroll_by(-e.y * self.SCROLL_STEP)
            return

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._scroll_dragging = False

        if self._options_modal is not None:
            should_close = False
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.KEYDOWN):
                should_close = self._options_modal.handle_event(e)
            if should_close:
                self._options_modal = None
                self._options_proxy = None
            return

        if self._modal_open:
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.KEYDOWN):
                self._handle_modal_event(e)
            return

        if e.type == pygame.MOUSEMOTION:
            if self._scroll_dragging and self._max_scroll > 0:
                dy = e.pos[1] - self._scroll_drag_anchor
                travel = max(1, self._viewport_height - self._scroll_thumb_rect.height)
                ratio = dy / float(travel)
                self._scroll_offset = max(0, min(self._max_scroll, self._scroll_drag_start_offset + ratio * self._max_scroll))
                self._update_scrollbar_rects()
                return
            self._menu_hover = self._menu_button_rect.collidepoint(e.pos)
            self._hover_entry = None
            content_pos = self._to_content_pos(e.pos)
            for section in self._sections:
                for entry in section["entries"]:
                    if entry.rect.collidepoint(content_pos):
                        self._hover_entry = entry
                        break
                if self._hover_entry is not None:
                    break
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._max_scroll > 0 and self._scroll_thumb_rect.collidepoint(e.pos):
                self._scroll_dragging = True
                self._scroll_drag_anchor = e.pos[1]
                self._scroll_drag_start_offset = self._scroll_offset
                return
            if self._max_scroll > 0 and self._scroll_track_rect.collidepoint(e.pos):
                if e.pos[1] < self._scroll_thumb_rect.top:
                    self._scroll_by(-self._viewport_height)
                else:
                    self._scroll_by(self._viewport_height)
                return
            if self._menu_button_rect.collidepoint(e.pos):
                self._modal_open = True
                return
            content_pos = self._to_content_pos(e.pos)
            for section in self._sections:
                for entry in section["entries"]:
                    if entry.rect.collidepoint(content_pos):
                        self._activate_entry(entry)
                        return
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.title import TitleScene
                self.next_scene = TitleScene(self.app)

    # --- drawing -------------------------------------------------------
    def _draw_menu_button(self, screen):
        rect = self._menu_button_rect
        is_active = self._modal_open or self._menu_hover
        bg = (60, 60, 65) if is_active else (35, 35, 40)
        pygame.draw.rect(screen, bg, rect, border_radius=10)
        pygame.draw.rect(screen, C.WHITE, rect, width=2, border_radius=10)
        line_color = C.WHITE
        line_padding_x = 12
        line_width = rect.width - line_padding_x * 2
        start_x = rect.x + line_padding_x
        spacing = 8
        first_y = rect.y + 10
        for i in range(3):
            y = first_y + i * spacing
            pygame.draw.line(screen, line_color, (start_x, y), (start_x + line_width, y), 3)

    def _draw_sections(self, screen):
        for section in self._sections:
            rect = section["rect"].move(0, -self._scroll_offset)
            if rect.bottom < 0 or rect.top > C.SCREEN_H:
                continue
            pygame.draw.rect(screen, self.SECTION_BG, rect, border_radius=self.SECTION_BORDER_RADIUS)
            pygame.draw.rect(screen, self.SECTION_BORDER, rect, width=2, border_radius=self.SECTION_BORDER_RADIUS)
            title_rect = section["title_rect"].move(0, -self._scroll_offset)
            screen.blit(section["title_surf"], title_rect.topleft)
            for entry in section["entries"]:
                icon_rect = entry.rect.move(0, -self._scroll_offset)
                label_rect = entry.label_rect.move(0, -self._scroll_offset)
                screen.blit(entry.surface, icon_rect.topleft)
                if entry.label_surf is not None:
                    screen.blit(entry.label_surf, label_rect.topleft)

    def _draw_scrollbar(self, screen):
        if self._max_scroll <= 0:
            return
        track = self._scroll_track_rect
        thumb = self._scroll_thumb_rect
        pygame.draw.rect(screen, (40, 40, 45), track, border_radius=6)
        pygame.draw.rect(screen, (180, 180, 190), thumb, border_radius=6)

    def _draw_modal(self, screen):
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))
        pygame.draw.rect(screen, (245, 245, 245), self._modal_rect, border_radius=16)
        pygame.draw.rect(screen, (70, 70, 70), self._modal_rect, width=2, border_radius=16)

        title = C.FONT_TITLE.render("Menu", True, (40, 40, 40)) if C.FONT_TITLE else pygame.font.SysFont(pygame.font.get_default_font(), 44, bold=True).render("Menu", True, (40, 40, 40))
        screen.blit(title, (self._modal_rect.centerx - title.get_width() // 2, self._modal_rect.y + 48))

        mp = pygame.mouse.get_pos()
        for btn in self._modal_buttons:
            btn.draw(screen, hover=btn.hovered(mp))

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Solitaire Suite", True, C.WHITE) if C.FONT_TITLE else pygame.font.SysFont(pygame.font.get_default_font(), 44, bold=True).render("Solitaire Suite", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 110))
        self._draw_sections(screen)
        self._draw_scrollbar(screen)
        self._draw_menu_button(screen)
        if self._modal_open:
            self._draw_modal(screen)
        if self._options_modal is not None:
            self._options_modal.draw(screen)







