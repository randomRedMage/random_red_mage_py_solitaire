# menu.py - Main menu
import os
import pygame
from math import ceil
from solitaire import common as C


class _GameEntry:
    __slots__ = ("name", "icon_filename", "module", "scene_cls", "surface", "rect", "label_surf", "label_rect")

    def __init__(self, name: str, icon_filename: str, module: str, scene_cls: str):
        self.name = name
        self.icon_filename = icon_filename
        self.module = module
        self.scene_cls = scene_cls
        self.surface: pygame.Surface | None = None
        self.rect = pygame.Rect(0, 0, 128, 128)
        self.label_surf: pygame.Surface | None = None
        self.label_rect = pygame.Rect(0, 0, 0, 0)


class MainMenuScene(C.Scene):
    ICON_SIZE = 128
    ICON_GAP = 24
    ICON_BORDER_RADIUS = 18
    ICON_BORDER = (60, 60, 70)
    ICON_BORDER_HOVER = (255, 215, 80)
    LABEL_MARGIN = 10

    SECTION_PADDING = 28
    SECTION_TITLE_GAP = 18
    SECTION_VERTICAL_GAP = 48
    SECTION_OUTER_MARGIN_X = 80
    SECTION_BG = (248, 248, 248)
    SECTION_BORDER = (0, 0, 0)
    SECTION_BORDER_RADIUS = 26

    def __init__(self, app):
        super().__init__(app)
        self._menu_button_rect = pygame.Rect(0, 0, 56, 40)
        self._menu_margin = (28, 24)
        self._menu_hover = False
        self._modal_open = False
        self._hover_entry: _GameEntry | None = None

        icon_dir = os.path.join(os.path.dirname(C.__file__), "assets", "images", "game_icons")
        self._icon_dir = icon_dir

        self._sections = [
            {
                "title": "Packers",
                "entries": [
                    _GameEntry("Klondike", "icon_klondike.png", "solitaire.modes.klondike", "KlondikeOptionsScene"),
                    _GameEntry("FreeCell", "icon_freecell.png", "solitaire.modes.freecell", "FreeCellOptionsScene"),
                    _GameEntry("Gate", "icon_gate.png", "solitaire.modes.gate", "GateOptionsScene"),
                    _GameEntry("Beleaguered Castle", "icon_bleagured_castle.png", "solitaire.modes.beleaguered_castle", "BeleagueredCastleOptionsScene"),
                    _GameEntry("Yukon", "icon_yukon.png", "solitaire.modes.yukon", "YukonOptionsScene"),
                ],
                "rect": pygame.Rect(0, 0, 0, 0),
                "title_surf": None,
            },
            {
                "title": "Builders",
                "entries": [
                    _GameEntry("Golf", "icon_golf.png", "solitaire.modes.golf", "GolfOptionsScene"),
                    _GameEntry("Pyramid", "icon_pyramid.png", "solitaire.modes.pyramid", "PyramidOptionsScene"),
                    _GameEntry("TriPeaks", "icon_tripeaks.png", "solitaire.modes.tripeaks", "TriPeaksOptionsScene"),
                ],
                "rect": pygame.Rect(0, 0, 0, 0),
                "title_surf": None,
            },
        ]

        self._modal_rect = pygame.Rect(0, 0, 520, 360)
        self._modal_padding_top = 130
        self._modal_padding_bottom = 70
        self._modal_gap = 26
        self._modal_settings = C.Button("Settings", 0, 0, center=True)
        self._modal_back = C.Button("Back to Menu", 0, 0, center=True)
        self._modal_quit = C.Button("Quit Game", 0, 0, center=True)
        self._modal_buttons = [self._modal_settings, self._modal_back, self._modal_quit]

        self._prepare_assets()
        self.compute_layout()

    # --- asset helpers -------------------------------------------------
    def _prepare_assets(self):
        font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 28, bold=True)
        section_font = C.FONT_TITLE if C.FONT_TITLE is not None else pygame.font.SysFont(pygame.font.get_default_font(), 38, bold=True)
        for section in self._sections:
            section["title_surf"] = section_font.render(section["title"], True, (40, 40, 40))
            for entry in section["entries"]:
                entry.surface = self._load_icon(entry.icon_filename)
                entry.label_surf = font.render(entry.name, True, (35, 35, 40))
                entry.label_rect = entry.label_surf.get_rect()

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
            # Placeholder surface if icon missing
            surf = pygame.Surface((self.ICON_SIZE, self.ICON_SIZE), pygame.SRCALPHA)
            surf.fill((120, 120, 130))
            pygame.draw.line(surf, (200, 200, 210), (0, 0), (self.ICON_SIZE, self.ICON_SIZE), 4)
            pygame.draw.line(surf, (200, 200, 210), (0, self.ICON_SIZE), (self.ICON_SIZE, 0), 4)
        else:
            if surf.get_size() != (self.ICON_SIZE, self.ICON_SIZE):
                surf = pygame.transform.smoothscale(surf, (self.ICON_SIZE, self.ICON_SIZE))
        return surf

    # --- layout --------------------------------------------------------
    def compute_layout(self):
        margin_x = min(self.SECTION_OUTER_MARGIN_X, max(20, (C.SCREEN_W - 640) // 4))
        available_width = max(self.ICON_SIZE, C.SCREEN_W - margin_x * 2)
        top = 210
        label_height = (C.FONT_UI.get_height() if C.FONT_UI else 26)
        row_height = self.ICON_SIZE + self.LABEL_MARGIN + label_height

        for section in self._sections:
            entries = section["entries"]
            columns = max(1, min(len(entries), (available_width + self.ICON_GAP) // (self.ICON_SIZE + self.ICON_GAP)))
            rows = ceil(len(entries) / columns)
            content_width = columns * self.ICON_SIZE + (columns - 1) * self.ICON_GAP
            content_height = rows * row_height + (rows - 1) * self.ICON_GAP
            title_surf: pygame.Surface = section["title_surf"]
            title_height = title_surf.get_height()
            section_width = content_width + self.SECTION_PADDING * 2
            section_height = content_height + self.SECTION_PADDING * 2 + title_height + self.SECTION_TITLE_GAP

            rect = section["rect"]
            rect.size = (section_width, section_height)
            rect.centerx = C.SCREEN_W // 2
            rect.top = top

            # Layout title inside section
            title_rect = title_surf.get_rect()
            title_rect.centerx = rect.centerx
            title_rect.top = rect.top + self.SECTION_PADDING
            section["title_rect"] = title_rect

            grid_left = rect.left + self.SECTION_PADDING + (content_width - (columns * self.ICON_SIZE + (columns - 1) * self.ICON_GAP)) // 2
            grid_top = title_rect.bottom + self.SECTION_TITLE_GAP

            for index, entry in enumerate(entries):
                col = index % columns
                row = index // columns
                x = grid_left + col * (self.ICON_SIZE + self.ICON_GAP)
                y = grid_top + row * (row_height + self.ICON_GAP)
                entry.rect.topleft = (x, y)
                entry.label_rect.centerx = entry.rect.centerx
                entry.label_rect.top = entry.rect.bottom + self.LABEL_MARGIN

            top = rect.bottom + self.SECTION_VERTICAL_GAP

        # Position modal and hamburger after sections computed
        margin_x, margin_y = self._menu_margin
        self._menu_button_rect.topright = (C.SCREEN_W - margin_x, margin_y)
        self._modal_rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._position_modal_buttons()

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

    # --- interaction ---------------------------------------------------
    def _activate_entry(self, entry: _GameEntry):
        try:
            module = __import__(entry.module, fromlist=[entry.scene_cls])
            scene_cls = getattr(module, entry.scene_cls)
            self.next_scene = scene_cls(self.app)
        except Exception:
            # Fallback: ignore failure gracefully
            pass

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
        if e.type == pygame.MOUSEMOTION:
            self._menu_hover = self._menu_button_rect.collidepoint(e.pos)
            if not self._modal_open:
                self._hover_entry = None
                for section in self._sections:
                    for entry in section["entries"]:
                        if entry.rect.collidepoint(e.pos):
                            self._hover_entry = entry
                            break
                    if self._hover_entry is not None:
                        break

        if self._modal_open:
            self._handle_modal_event(e)
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self._menu_button_rect.collidepoint((mx, my)):
                self._modal_open = True
                return
            for section in self._sections:
                for entry in section["entries"]:
                    if entry.rect.collidepoint((mx, my)):
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
            rect = section["rect"]
            pygame.draw.rect(screen, self.SECTION_BG, rect, border_radius=self.SECTION_BORDER_RADIUS)
            pygame.draw.rect(screen, self.SECTION_BORDER, rect, width=2, border_radius=self.SECTION_BORDER_RADIUS)
            title_surf: pygame.Surface = section["title_surf"]
            title_rect = section["title_rect"]
            screen.blit(title_surf, (title_rect.x, title_rect.y))
            for entry in section["entries"]:
                screen.blit(entry.surface, entry.rect.topleft)
                border_color = self.ICON_BORDER_HOVER if (not self._modal_open and entry is self._hover_entry) else self.ICON_BORDER
                pygame.draw.rect(screen, border_color, entry.rect, width=3, border_radius=self.ICON_BORDER_RADIUS)
                if entry.label_surf is not None:
                    screen.blit(entry.label_surf, entry.label_rect.topleft)

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
        self._draw_menu_button(screen)
        if self._modal_open:
            self._draw_modal(screen)
