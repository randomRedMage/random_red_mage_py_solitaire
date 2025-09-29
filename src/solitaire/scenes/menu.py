
# menu.py - Main menu
import pygame
from solitaire import common as C
from solitaire.modes.klondike import (
    KLONDIKE_DIFFICULTY_LABELS,
    KLONDIKE_STOCK_CYCLE_LIMITS,
    KlondikeGameScene,
)
from solitaire.scenes.game_options_modal import GameOptionsModal

class MainMenuScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2
        y  = 260
        self.b_klon = C.Button("Play Klondike", cx, y, center=True); y += 60
        self.b_quit = C.Button("Quit", cx, y, center=True)

        # Track any open modal so we can forward events appropriately
        self._active_modal = None
        self._active_modal_start = None

        # Klondike configuration defaults
        self._klondike_diff_index = 0
        self._klondike_draw_mode = 3

        self._klondike_modal = GameOptionsModal(
            "Klondike – Options",
            "Start Klondike",
            [
                (self._klondike_difficulty_label, self._cycle_klondike_difficulty),
                (self._klondike_draw_label, self._toggle_klondike_draw_mode),
            ],
        )


    def handle_event(self, e):
        if self._active_modal is not None:
            result = self._active_modal.handle_event(e)
            if result == "start":
                if self._active_modal_start is not None:
                    self._active_modal_start()
                return
            if result == "close":
                self._close_active_modal()
                return
            if result:
                return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx,my = e.pos
            if self.b_klon.hovered((mx,my)):
                self._open_modal(self._klondike_modal, self._start_klondike_game)
            elif self.b_quit.hovered((mx,my)):
                pygame.quit(); raise SystemExit
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                pygame.quit(); raise SystemExit

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Solitaire Suite", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 120))
        mp = pygame.mouse.get_pos()
        for b in [self.b_klon, self.b_quit]:
            b.draw(screen, hover=b.hovered(mp))
        if self._active_modal is not None:
            self._active_modal.draw(screen)

    # ------------------------------------------------------------------
    # Modal helpers
    def _open_modal(self, modal, start_callback):
        self._active_modal = modal
        self._active_modal_start = start_callback
        modal.open()

    def _close_active_modal(self):
        if self._active_modal is not None:
            self._active_modal.close()
        self._active_modal = None
        self._active_modal_start = None

    # ------------------------------------------------------------------
    # Klondike-specific helpers
    def _klondike_difficulty_label(self):
        return "Difficulty: " + KLONDIKE_DIFFICULTY_LABELS[self._klondike_diff_index]

    def _klondike_draw_label(self):
        return f"Draw: {self._klondike_draw_mode}"

    def _cycle_klondike_difficulty(self):
        self._klondike_diff_index = (self._klondike_diff_index + 1) % len(KLONDIKE_DIFFICULTY_LABELS)
        self._klondike_modal.refresh()

    def _toggle_klondike_draw_mode(self):
        self._klondike_draw_mode = 1 if self._klondike_draw_mode == 3 else 3
        self._klondike_modal.refresh()

    def _start_klondike_game(self):
        stock_cycles = KLONDIKE_STOCK_CYCLE_LIMITS[self._klondike_diff_index]
        self.next_scene = KlondikeGameScene(
            self.app,
            draw_count=self._klondike_draw_mode,
            stock_cycles=stock_cycles,
        )
        self._close_active_modal()
