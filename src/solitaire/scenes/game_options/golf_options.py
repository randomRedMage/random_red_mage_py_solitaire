import os
import pygame
from solitaire import common as C
from solitaire.modes.golf import (
    GolfGameScene,
    GolfScoresScene,
    _golf_save_path,
    _safe_read_json,
)


class GolfOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.holes_options = [1, 3, 9, 18]
        self.holes_idx = 0
        self.around = True

        cx = C.SCREEN_W // 2 - 220
        y = 220
        self.b_new1 = C.Button("New 1 Hole", cx, y, w=440); y += 56
        self.b_new3 = C.Button("New 3 Holes", cx, y, w=440); y += 56
        self.b_new9 = C.Button("New 9 Holes", cx, y, w=440); y += 56
        self.b_new18 = C.Button("New 18 Holes", cx, y, w=440); y += 56
        y += 8
        self.b_wrap = C.Button(self._wrap_label(), cx, y, w=440); y += 56
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440); y += 56
        self.b_scores = C.Button("View Recent Scores", cx, y, w=440); y += 56
        y += 8
        self.b_back = C.Button("Back", cx, y, w=440)

    def _wrap_label(self):
        return f"Around the Corner: {'On' if self.around else 'Off'}"

    def _start_new(self, holes: int):
        try:
            if os.path.isfile(_golf_save_path()):
                os.remove(_golf_save_path())
        except Exception:
            pass
        self.next_scene = GolfGameScene(self.app, holes_total=holes, around=self.around, load_state=None)

    def _has_save(self) -> bool:
        s = _safe_read_json(_golf_save_path())
        return bool(s) and not s.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_new1.hovered((mx, my)):
                self._start_new(1)
            elif self.b_new3.hovered((mx, my)):
                self._start_new(3)
            elif self.b_new9.hovered((mx, my)):
                self._start_new(9)
            elif self.b_new18.hovered((mx, my)):
                self._start_new(18)
            elif self.b_wrap.hovered((mx, my)):
                self.around = not self.around
                self.b_wrap.text = self._wrap_label()
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                load_state = _safe_read_json(_golf_save_path())
                self.next_scene = GolfGameScene(self.app, holes_total=load_state.get("holes_total", 1), around=bool(load_state.get("around", False)), load_state=load_state)
            elif self.b_scores.hovered((mx, my)):
                self.next_scene = GolfScoresScene(self.app)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Golf - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 120))
        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        if not has_save:
            old = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for b in [self.b_new1, self.b_new3, self.b_new9, self.b_new18, self.b_wrap, self.b_continue, self.b_scores, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))
        if not has_save:
            self.b_continue.text = old

