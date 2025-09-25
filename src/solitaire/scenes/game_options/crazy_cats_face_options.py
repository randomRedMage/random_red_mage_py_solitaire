import pygame

from solitaire import common as C
from solitaire.modes import crazy_cats_face as crazy_mode


class CrazyCatsFaceOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.message: str = ""

        cx = C.SCREEN_W // 2
        btn_w = 440
        y = 280
        self.b_start = C.Button("Start Crazy Cat's Face", cx - btn_w // 2, y, w=btn_w)
        y += 70
        self.b_back = C.Button("Back", cx - btn_w // 2, y, w=btn_w)

    def _start_new(self):
        self.next_scene = crazy_mode.CrazyCatsFaceScene(self.app)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self._start_new()
            elif event.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.b_start.hovered((mx, my)):
                self._start_new()
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Crazy Cat's Face - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 160))

        mp = pygame.mouse.get_pos()
        for button in [self.b_start, self.b_back]:
            button.draw(screen, hover=button.hovered(mp))

        if self.message:
            msg = C.FONT_UI.render(self.message, True, C.WHITE)
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, self.b_back.rect.bottom + 20))
