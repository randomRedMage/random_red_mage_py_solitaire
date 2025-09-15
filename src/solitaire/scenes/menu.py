
# menu.py - Main menu
import pygame
from solitaire import common as C

class MainMenuScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2
        y  = 260
        self.b_klon = C.Button("Play Klondike", cx, y, center=True); y += 60
        self.b_free = C.Button("Play FreeCell", cx, y, center=True); y += 60
        self.b_pyr  = C.Button("Play Pyramid",  cx, y, center=True); y += 60
        self.b_tri  = C.Button("Play TriPeaks", cx, y, center=True); y += 60
        self.b_gate = C.Button("Play Gate", cx, y, center=True); y += 60
        self.b_golf = C.Button("Play Golf", cx, y, center=True); y += 60
        self.b_yukon = C.Button("Play Yukon", cx, y, center=True); y += 60
        self.b_settings = C.Button("Settings", cx, y, center=True); y += 60
        self.b_quit = C.Button("Quit", cx, y, center=True)


    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx,my = e.pos
            if self.b_klon.hovered((mx,my)):
                from solitaire.modes.klondike import KlondikeOptionsScene
                self.next_scene = KlondikeOptionsScene(self.app)
            elif self.b_free.hovered((mx,my)):
                from solitaire.modes.freecell import FreeCellOptionsScene
                self.next_scene = FreeCellOptionsScene(self.app)
            elif self.b_pyr.hovered((mx,my)):
                from solitaire.modes.pyramid import PyramidOptionsScene
                self.next_scene = PyramidOptionsScene(self.app)
            elif self.b_tri.hovered((mx,my)):
                from solitaire.modes.tripeaks import TriPeaksOptionsScene
                self.next_scene = TriPeaksOptionsScene(self.app)
            elif self.b_gate.hovered((mx,my)):
                from solitaire.modes.gate import GateOptionsScene
                self.next_scene = GateOptionsScene(self.app)
            elif self.b_golf.hovered((mx,my)):
                from solitaire.modes.golf import GolfOptionsScene
                self.next_scene = GolfOptionsScene(self.app)
            elif self.b_yukon.hovered((mx,my)):
                from solitaire.modes.yukon import YukonOptionsScene
                self.next_scene = YukonOptionsScene(self.app)
            elif self.b_settings.hovered((mx,my)):
                from solitaire.scenes.settings import SettingsScene
                self.next_scene = SettingsScene(self.app)
            elif self.b_quit.hovered((mx,my)):
                pygame.quit(); raise SystemExit
        elif e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                from solitaire.scenes.title import TitleScene
                self.next_scene = TitleScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Solitaire Suite", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 120))
        mp = pygame.mouse.get_pos()
        for b in [self.b_klon, self.b_free, self.b_pyr, self.b_tri, self.b_gate, self.b_golf, self.b_yukon, self.b_settings, self.b_quit]:
            b.draw(screen, hover=b.hovered(mp))
