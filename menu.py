
# menu.py - Main menu
import pygame
import common as C

class MainMenuScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W//2 - 180
        y = 260
        self.b_klon = C.Button("Play Klondike", cx, y); y+=60
        self.b_quit = C.Button("Quit", cx, y)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx,my = e.pos
            if self.b_klon.hovered((mx,my)):
                from klondike import KlondikeOptionsScene
                self.next_scene = KlondikeOptionsScene(self.app)
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
