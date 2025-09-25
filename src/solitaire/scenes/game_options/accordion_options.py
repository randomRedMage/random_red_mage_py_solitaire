import pygame

from solitaire import common as C
from solitaire.modes import accordion as accordion_mode


class AccordionOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self._difficulties = [
            ("easy", "Easy — win with 7 piles or fewer"),
            ("normal", "Normal — win with 4 piles or fewer"),
            ("hard", "Hard — win with 1 pile"),
        ]
        self._difficulty_index = 1  # default to Normal

        cx = C.SCREEN_W // 2 - 220
        y = 260
        self.b_difficulty = C.Button(self._difficulty_label(), cx, y, w=440)
        y += 60
        self.b_new = C.Button("Start New Game", cx, y, w=440)
        y += 60
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440)
        y += 80
        self.b_back = C.Button("Back", cx, y, w=440)

    def _difficulty_label(self) -> str:
        key, description = self._difficulties[self._difficulty_index]
        label = accordion_mode.get_difficulty_label(key)
        return f"Difficulty: {label} ({description.split('—')[-1].strip()})"

    def _cycle_difficulty(self):
        self._difficulty_index = (self._difficulty_index + 1) % len(self._difficulties)
        self.b_difficulty.text = self._difficulty_label()

    def _current_difficulty(self) -> str:
        return self._difficulties[self._difficulty_index][0]

    def _has_save(self) -> bool:
        return accordion_mode.has_saved_game()

    def _saved_game_label(self) -> str:
        if not self._has_save():
            return "Continue Saved Game (None)"
        summary = accordion_mode.peek_saved_game_summary()
        if summary:
            return f"Continue Saved Game ({summary})"
        return "Continue Saved Game"

    def _start_new_game(self):
        accordion_mode.delete_saved_game()
        difficulty = self._current_difficulty()
        self.next_scene = accordion_mode.AccordionGameScene(self.app, difficulty=difficulty)

    def _continue_game(self):
        state = accordion_mode.load_saved_game()
        if not state:
            return
        self.next_scene = accordion_mode.AccordionGameScene(self.app, load_state=state)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_difficulty.hovered((mx, my)):
                self._cycle_difficulty()
            elif self.b_new.hovered((mx, my)):
                self._start_new_game()
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                self._continue_game()
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene

            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Accordion - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 160))

        self.b_continue.text = self._saved_game_label()
        mp = pygame.mouse.get_pos()
        for button in [self.b_difficulty, self.b_new, self.b_continue, self.b_back]:
            button.draw(screen, hover=button.hovered(mp))
