import os
import pygame
from solitaire import common as C
from solitaire.modes import yukon as yukon_mode


class YukonOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 220
        y = 260
        self.b_start = C.Button("Start Yukon", cx, y, w=440); y += 60
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440); y += 60
        y += 10
        self.b_back = C.Button("Back", cx, y, w=440)

    def _has_save(self) -> bool:
        s = yukon_mode._safe_read_json(yukon_mode._yukon_save_path())
        return bool(s) and not s.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                try:
                    save_path = yukon_mode._yukon_save_path()
                    if os.path.isfile(save_path):
                        os.remove(save_path)
                except Exception:
                    pass
                self.next_scene = yukon_mode.YukonGameScene(self.app, load_state=None)
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                state = yukon_mode._safe_read_json(yukon_mode._yukon_save_path())
                self.next_scene = yukon_mode.YukonGameScene(self.app, load_state=state)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Yukon - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 130))
        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        if not has_save:
            old = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for b in [self.b_start, self.b_continue, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))
        if not has_save:
            self.b_continue.text = old

