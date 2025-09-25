import pygame

from solitaire import common as C
from solitaire.modes import chameleon as chameleon_mode


class ChameleonOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cfg = chameleon_mode.load_chameleon_config()
        self.stock_cycles = cfg.get("stock_cycles")

        cx = C.SCREEN_W // 2 - 220
        y = 240
        self.b_start = C.Button("Start Chameleon", cx, y, w=440)
        y += 56
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440)
        y += 64
        self.b_difficulty = C.Button(self._difficulty_label(), cx, y, w=440)
        y += 64
        self.b_back = C.Button("Back", cx, y, w=440)

    def _difficulty_label(self) -> str:
        if self.stock_cycles is None:
            return "Difficulty: Easy (Unlimited redeals)"
        if self.stock_cycles <= 0:
            return "Difficulty: Hard (No redeal)"
        if self.stock_cycles == 1:
            return "Difficulty: Normal (1 redeal)"
        return f"Difficulty: Custom ({self.stock_cycles} redeals)"

    def _cycle_difficulty(self) -> None:
        if self.stock_cycles is None:
            self.stock_cycles = 0
        elif self.stock_cycles <= 0:
            self.stock_cycles = 1
        else:
            self.stock_cycles = None
        chameleon_mode.save_chameleon_config(self.stock_cycles)
        chameleon_mode.update_saved_stock_cycles(self.stock_cycles)
        self.b_difficulty.text = self._difficulty_label()

    def _start_new(self) -> None:
        chameleon_mode.clear_saved_state()
        self.next_scene = chameleon_mode.ChameleonGameScene(
            self.app, load_state=None, stock_cycles=self.stock_cycles
        )

    def _continue_game(self) -> None:
        state = chameleon_mode.load_saved_state()
        if not state or state.get("completed"):
            return
        state["stock_cycles_allowed"] = self.stock_cycles
        if self.stock_cycles is not None and state.get("stock_cycles_used", 0) > self.stock_cycles:
            state["stock_cycles_used"] = self.stock_cycles
        self.next_scene = chameleon_mode.ChameleonGameScene(
            self.app, load_state=state, stock_cycles=self.stock_cycles
        )

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self.b_start.hovered((mx, my)):
                self._start_new()
            elif self.b_continue.hovered((mx, my)) and chameleon_mode.chameleon_save_exists():
                self._continue_game()
            elif self.b_difficulty.hovered((mx, my)):
                self._cycle_difficulty()
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene

            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Chameleon - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 140))
        mp = pygame.mouse.get_pos()
        has_save = chameleon_mode.chameleon_save_exists()
        if not has_save:
            original = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for button in [self.b_start, self.b_continue, self.b_difficulty, self.b_back]:
            button.draw(screen, hover=button.hovered(mp))
        if not has_save:
            self.b_continue.text = original
