# menu.py - Main menu
import pygame
from solitaire import common as C


class MainMenuScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self._main_button_start_y = 260
        self._main_button_gap = 60
        y = self._main_button_start_y
        self.b_klon = C.Button("Play Klondike", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_free = C.Button("Play FreeCell", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_pyr = C.Button("Play Pyramid", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_tri = C.Button("Play TriPeaks", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_gate = C.Button("Play Gate", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_castle = C.Button("Play Beleaguered Castle", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_golf = C.Button("Play Golf", C.SCREEN_W // 2, y, center=True); y += self._main_button_gap
        self.b_yukon = C.Button("Play Yukon", C.SCREEN_W // 2, y, center=True)
        self._main_buttons = [
            self.b_klon,
            self.b_free,
            self.b_pyr,
            self.b_tri,
            self.b_gate,
            self.b_castle,
            self.b_golf,
            self.b_yukon,
        ]

        # Hamburger menu button in the top-right corner
        self._menu_button_rect = pygame.Rect(0, 0, 56, 40)
        self._menu_margin = (28, 24)
        self._menu_hover = False
        self._modal_open = False

        # Modal layout for settings / quit
        modal_w, modal_h = 520, 360
        self._modal_rect = pygame.Rect(0, 0, modal_w, modal_h)
        self._modal_padding_top = 130
        self._modal_padding_bottom = 70
        self._modal_gap = 26
        self._modal_settings = C.Button("Settings", 0, 0, center=True)
        self._modal_back = C.Button("Back to Menu", 0, 0, center=True)
        self._modal_quit = C.Button("Quit Game", 0, 0, center=True)
        self._modal_buttons = [self._modal_settings, self._modal_back, self._modal_quit]

        self.compute_layout()

    def compute_layout(self):
        # Center the main menu buttons horizontally
        cx = C.SCREEN_W // 2
        y = self._main_button_start_y
        for btn in self._main_buttons:
            btn.rect.center = (cx, y)
            y += self._main_button_gap

        # Pin the hamburger button to the top-right corner with a consistent margin
        margin_x, margin_y = self._menu_margin
        self._menu_button_rect.topright = (C.SCREEN_W - margin_x, margin_y)

        # Center the modal in the window and relayout its buttons
        self._modal_rect.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._position_modal_buttons()

    def _position_modal_buttons(self):
        gap = self._modal_gap
        cx = self._modal_rect.centerx
        total_height = sum(btn.rect.height for btn in self._modal_buttons)
        total_gap = gap * (len(self._modal_buttons) - 1)
        available_height = self._modal_rect.height - self._modal_padding_top - self._modal_padding_bottom
        if total_height + total_gap > available_height:
            # Reduce spacing to keep all buttons visible while maintaining equal gaps
            gap = max(8, gap - ((total_height + total_gap) - available_height) // max(1, len(self._modal_buttons) - 1))
            total_gap = gap * (len(self._modal_buttons) - 1)
        start_top = self._modal_rect.y + self._modal_padding_top
        current_y = start_top
        for btn in self._modal_buttons:
            btn.rect.center = (cx, current_y + btn.rect.height // 2)
            current_y += btn.rect.height + gap

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

        if self._modal_open:
            self._handle_modal_event(e)
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self._menu_button_rect.collidepoint((mx, my)):
                self._modal_open = True
                return
            if self.b_klon.hovered((mx, my)):
                from solitaire.modes.klondike import KlondikeOptionsScene
                self.next_scene = KlondikeOptionsScene(self.app)
            elif self.b_free.hovered((mx, my)):
                from solitaire.modes.freecell import FreeCellOptionsScene
                self.next_scene = FreeCellOptionsScene(self.app)
            elif self.b_pyr.hovered((mx, my)):
                from solitaire.modes.pyramid import PyramidOptionsScene
                self.next_scene = PyramidOptionsScene(self.app)
            elif self.b_tri.hovered((mx, my)):
                from solitaire.modes.tripeaks import TriPeaksOptionsScene
                self.next_scene = TriPeaksOptionsScene(self.app)
            elif self.b_gate.hovered((mx, my)):
                from solitaire.modes.gate import GateOptionsScene
                self.next_scene = GateOptionsScene(self.app)
            elif self.b_castle.hovered((mx, my)):
                from solitaire.modes.beleaguered_castle import BeleagueredCastleOptionsScene
                self.next_scene = BeleagueredCastleOptionsScene(self.app)
            elif self.b_golf.hovered((mx, my)):
                from solitaire.modes.golf import GolfOptionsScene
                self.next_scene = GolfOptionsScene(self.app)
            elif self.b_yukon.hovered((mx, my)):
                from solitaire.modes.yukon import YukonOptionsScene
                self.next_scene = YukonOptionsScene(self.app)
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.title import TitleScene
                self.next_scene = TitleScene(self.app)

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

    def _draw_modal(self, screen):
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))
        pygame.draw.rect(screen, (245, 245, 245), self._modal_rect, border_radius=16)
        pygame.draw.rect(screen, (70, 70, 70), self._modal_rect, width=2, border_radius=16)

        title = C.FONT_TITLE.render("Menu", True, (40, 40, 40))
        screen.blit(title, (self._modal_rect.centerx - title.get_width() // 2, self._modal_rect.y + 48))

        mp = pygame.mouse.get_pos()
        for btn in self._modal_buttons:
            btn.draw(screen, hover=btn.hovered(mp))

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Solitaire Suite", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 120))
        mp = pygame.mouse.get_pos()
        for b in self._main_buttons:
            hover = (not self._modal_open) and b.hovered(mp)
            b.draw(screen, hover=hover)
        self._draw_menu_button(screen)
        if self._modal_open:
            self._draw_modal(screen)
