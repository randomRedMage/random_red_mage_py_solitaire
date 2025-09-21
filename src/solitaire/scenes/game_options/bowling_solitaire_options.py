import pygame

from solitaire import common as C
from solitaire.modes import bowling_solitaire as bowling_mode


class BowlingSolitaireOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.message: str = ""

        cx = C.SCREEN_W // 2
        btn_w = 420
        y = 260
        self.b_start = C.Button("Start Bowling Solitaire", cx - btn_w // 2, y, w=btn_w); y += 70
        self.b_continue = C.Button("Continue Saved Game", cx - btn_w // 2, y, w=btn_w); y += 70
        y += 10
        self.b_back = C.Button("Back", cx - btn_w // 2, y, w=btn_w)

    def _has_save(self) -> bool:
        return bowling_mode.has_saved_game()

    def _start_new(self):
        self.message = ""
        self.next_scene = bowling_mode.BowlingSolitaireGameScene(self.app, player_initials="")

    def _continue_saved(self):
        load_state = bowling_mode.load_saved_game()
        if not load_state:
            self.message = "No saved game found."
            return
        self.message = ""
        initials = load_state.get("player_initials", "PLY") or "PLY"
        self.next_scene = bowling_mode.BowlingSolitaireGameScene(
            self.app,
            player_initials=initials,
            load_state=load_state,
        )

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_RETURN:
                self._start_new()
            elif e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                self._start_new()
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                self._continue_saved()
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Bowling Solitaire - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 130))

        subtitle = C.FONT_UI.render("Player initials will be requested when the game begins.", True, C.WHITE)
        screen.blit(subtitle, (C.SCREEN_W // 2 - subtitle.get_width() // 2, 190))

        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        if not has_save:
            old = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for btn in [self.b_start, self.b_continue, self.b_back]:
            btn.draw(screen, hover=btn.hovered(mp))
        if not has_save:
            self.b_continue.text = old

        if self.message:
            msg = C.FONT_UI.render(self.message, True, C.WHITE)
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, self.b_back.rect.bottom + 20))
