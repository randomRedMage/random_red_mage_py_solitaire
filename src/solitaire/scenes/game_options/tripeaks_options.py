import pygame
from solitaire import common as C
from solitaire.modes import tripeaks as tripeaks_mode


class TriPeaksOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 210
        y = 300
        self.wrap_ak = True
        self.b_start = C.Button("Start TriPeaks", cx, y, w=420); y += 60
        self.b_wrap  = C.Button("Wrap A↔K: On", cx, y, w=420); y += 60
        self.b_back = C.Button("Back", cx, y, w=420)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self.next_scene = tripeaks_mode.TriPeaksGameScene(self.app, wrap_ak=self.wrap_ak)
            elif self.b_wrap.hovered((mx, my)):
                self.wrap_ak = not self.wrap_ak
                self.b_wrap.text = f"Wrap A↔K: {'On' if self.wrap_ak else 'Off'}"
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("TriPeaks - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        for b in [self.b_start, self.b_wrap, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))

