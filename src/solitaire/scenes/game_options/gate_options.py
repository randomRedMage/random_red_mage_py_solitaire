import pygame
from solitaire import common as C
from solitaire.modes import gate as gate_mode


class GateOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 210
        y = 300
        self.b_start = C.Button("Start Gate", cx, y, w=420); y += 70
        self.b_back = C.Button("Back", cx, y, w=420)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self.next_scene = gate_mode.GateGameScene(self.app)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Gate - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))

