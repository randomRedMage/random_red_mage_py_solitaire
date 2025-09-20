import pygame
from solitaire import common as C
from solitaire.modes import big_ben as big_ben_mode


class BigBenOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 220
        y = 260
        self.b_start = C.Button("Start Big Ben", cx, y, w=440); y += 60
        self.b_resume = C.Button("Continue Saved Game", cx, y, w=440); y += 60
        y += 10
        self.b_back = C.Button("Back", cx, y, w=440)

    def _has_save(self) -> bool:
        state = big_ben_mode._safe_read_json(big_ben_mode._bb_save_path())
        return bool(state) and not state.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                big_ben_mode._clear_saved_game()
                self.next_scene = big_ben_mode.BigBenGameScene(self.app, load_state=None)
            elif self.b_resume.hovered((mx, my)) and self._has_save():
                state = big_ben_mode._safe_read_json(big_ben_mode._bb_save_path())
                if state:
                    self.next_scene = big_ben_mode.BigBenGameScene(self.app, load_state=state)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Big Ben - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 130))
        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        resume_label = self.b_resume.text
        if not has_save:
            self.b_resume.text = "Continue Saved Game (None)"
        for btn in (self.b_start, self.b_resume, self.b_back):
            btn.draw(screen, hover=btn.hovered(mp))
        self.b_resume.text = resume_label

