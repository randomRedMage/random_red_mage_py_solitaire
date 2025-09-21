import pygame
from solitaire import common as C
from solitaire.modes import pyramid as pyramid_mode


class PyramidOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.diff_index = 0  # 0: Easy(∞), 1: Normal(2), 2: Hard(1)
        cx = C.SCREEN_W//2 - 210
        y  = 260
        self.b_start = C.Button("Start Pyramid", cx, y); y += 60
        self.b_diff  = C.Button("Difficulty: Easy (Unlimited resets)", cx, y, w=420); y += 70
        self.b_back  = C.Button("Back", cx, y)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                allowed = [None, 2, 1][self.diff_index]
                self.next_scene = pyramid_mode.PyramidGameScene(self.app, allowed_resets=allowed)
            elif self.b_diff.hovered((mx, my)):
                self.diff_index = (self.diff_index + 1) % 3
                text = ["Easy (Unlimited resets)", "Normal (2 resets)", "Hard (1 reset)"][self.diff_index]
                self.b_diff.text = "Difficulty: " + text
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Pyramid - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 120))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_diff, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))

