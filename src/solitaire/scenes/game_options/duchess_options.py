import pygame

from solitaire import common as C
from solitaire.modes import duchess as duchess_mode


class DuchessOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)

        cx = C.SCREEN_W // 2 - 220
        y = 240
        self.b_start = C.Button("Start Duchess", cx, y, w=440)
        y += 56
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440)
        y += 64
        self.b_back = C.Button("Back", cx, y, w=440)

    def _start_new(self) -> None:
        duchess_mode.clear_saved_state()
        self.next_scene = duchess_mode.DuchessGameScene(self.app, load_state=None)

    def _continue_game(self) -> None:
        state = duchess_mode.load_saved_state()
        if not state or state.get("completed"):
            return
        self.next_scene = duchess_mode.DuchessGameScene(self.app, load_state=state)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.b_start.hovered((mx, my)):
                self._start_new()
            elif self.b_continue.hovered((mx, my)) and duchess_mode.duchess_save_exists():
                self._continue_game()
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene

            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Duchess - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        has_save = duchess_mode.duchess_save_exists()
        if not has_save:
            original = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for button in [self.b_start, self.b_continue, self.b_back]:
            button.draw(screen, hover=button.hovered(mp))
        if not has_save:
            self.b_continue.text = original
