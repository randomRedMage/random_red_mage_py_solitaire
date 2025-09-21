import pygame

from solitaire import common as C
from solitaire.modes import bowling_solitaire as bowling_mode


class BowlingSolitaireOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self.initials: str = ""
        self.input_active: bool = False
        self.message: str = ""

        cx = C.SCREEN_W // 2
        self.input_rect = pygame.Rect(0, 0, 280, 60)
        self.input_rect.center = (cx, 260)

        btn_w = 420
        y = 360
        self.b_start = C.Button("Start Bowling Solitaire", cx - btn_w // 2, y, w=btn_w); y += 70
        self.b_continue = C.Button("Continue Saved Game", cx - btn_w // 2, y, w=btn_w); y += 70
        y += 10
        self.b_back = C.Button("Back", cx - btn_w // 2, y, w=btn_w)

    def _normalised_initials(self) -> str:
        return self.initials.strip().upper()

    def _has_valid_initials(self) -> bool:
        initials = self._normalised_initials()
        return 1 <= len(initials) <= 3

    def _has_save(self) -> bool:
        return bowling_mode.has_saved_game()

    def _start_new(self):
        if not self._has_valid_initials():
            self.message = "Enter 1-3 letters or numbers."
            return
        initials = self._normalised_initials()
        self.message = ""
        self.next_scene = bowling_mode.BowlingSolitaireGameScene(self.app, player_initials=initials)

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
            if self.input_active:
                if e.key == pygame.K_BACKSPACE:
                    self.initials = self.initials[:-1]
                elif e.key == pygame.K_RETURN:
                    self._start_new()
                else:
                    char = e.unicode.upper()
                    if char.isalnum() and len(self.initials) < 3:
                        self.initials += char
            elif e.key == pygame.K_RETURN:
                self._start_new()
            elif e.key == pygame.K_ESCAPE:
                from solitaire.scenes.menu import MainMenuScene

                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.input_rect.collidepoint((mx, my)):
                self.input_active = True
            else:
                self.input_active = False
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

        prompt = C.FONT_UI.render("Player Initials (1-3 letters/numbers)", True, C.WHITE)
        screen.blit(prompt, (self.input_rect.centerx - prompt.get_width() // 2, self.input_rect.top - 40))

        pygame.draw.rect(screen, (245, 245, 245), self.input_rect, border_radius=10)
        border_col = (255, 220, 120) if self.input_active else (200, 200, 210)
        pygame.draw.rect(screen, border_col, self.input_rect, width=3, border_radius=10)

        initials = self._normalised_initials()
        txt = C.FONT_TITLE.render(initials or "_", True, (30, 30, 35))
        screen.blit(txt, (self.input_rect.centerx - txt.get_width() // 2, self.input_rect.centery - txt.get_height() // 2))

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
