import pygame
from solitaire import common as C
from solitaire.modes.klondike import KlondikeGameScene


class KlondikeOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.diff_index = 0  # 0: Easy(∞), 1: Medium(2), 2: Hard(1)
        self.draw_mode = 3   # 1 or 3
        cx = C.SCREEN_W//2 - 210
        y = 260
        self.b_start = C.Button("Start Klondike", cx, y); y+=60
        self.b_diff  = C.Button("Difficulty: Easy (Unlimited stock cycles)", cx, y, w=420); y+=60
        self.b_draw  = C.Button("Draw: 3", cx, y, w=420); y+=60
        y+=10
        self.b_back  = C.Button("Back", cx, y)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx,my = e.pos
            if self.b_start.hovered((mx,my)):
                self.next_scene = KlondikeGameScene(
                    self.app,
                    draw_count=self.draw_mode,
                    stock_cycles=[None,2,1][self.diff_index]
                )
            elif self.b_diff.hovered((mx,my)):
                self.diff_index = (self.diff_index + 1) % 3
                txt = ["Easy (Unlimited stock cycles)",
                       "Medium (2 stock cycles)",
                       "Hard (1 stock cycle)"][self.diff_index]
                self.b_diff.text = "Difficulty: " + txt
            elif self.b_draw.hovered((mx,my)):
                self.draw_mode = 1 if self.draw_mode == 3 else 3
                self.b_draw.text = f"Draw: {self.draw_mode}"
            elif self.b_back.hovered((mx,my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Klondike – Options", True, C.WHITE)
        # Override garbled title with a clean one
        title = C.FONT_TITLE.render("Klondike - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 120))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_diff, self.b_draw, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))

