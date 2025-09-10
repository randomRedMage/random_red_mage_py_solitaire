import os
import math
import pygame
from solitaire import common as C


class TitleScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        self._img_path = os.path.join(os.path.dirname(C.__file__), "assets", "images", "title.png")
        self._raw_image = None  # original loaded surface
        self._image = None      # scaled surface to current window
        self._image_rect = pygame.Rect(0, 0, 0, 0)
        self._prompt_text = "Click or press Enter/Space to play — Esc returns"
        self._pulse_period_ms = 1600  # slow flash
        self._load_image()
        self.compute_layout()

    def _load_image(self):
        try:
            if os.path.isfile(self._img_path):
                s = pygame.image.load(self._img_path)
                self._raw_image = s.convert_alpha() if s.get_alpha() else s.convert()
            else:
                self._raw_image = None
        except Exception:
            self._raw_image = None

    def compute_layout(self):
        # Scale the title image to fit comfortably within the window
        max_w = int(C.SCREEN_W * 0.8)
        max_h = int(C.SCREEN_H * 0.6)
        if self._raw_image is not None:
            iw, ih = self._raw_image.get_size()
            scale = min(max_w / iw, max_h / ih, 1.0)
            tw, th = int(iw * scale), int(ih * scale)
            if (tw, th) != (iw, ih):
                self._image = pygame.transform.smoothscale(self._raw_image, (tw, th))
            else:
                self._image = self._raw_image
            self._image_rect = self._image.get_rect()
            self._image_rect.centerx = C.SCREEN_W // 2
            self._image_rect.centery = C.SCREEN_H // 2 - 30
        else:
            self._image = None
            self._image_rect = pygame.Rect(0, 0, 0, 0)

    def _goto_menu(self):
        from solitaire.scenes.menu import MainMenuScene
        self.next_scene = MainMenuScene(self.app)

    def handle_event(self, e):
        # Enter/Space: go to menu; Esc or Q: confirm quit
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self._goto_menu(); return
            elif e.key in (pygame.K_ESCAPE, pygame.K_q):
                try:
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                except Exception:
                    pygame.quit(); raise SystemExit
        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button in (1, 2, 3):
                self._goto_menu(); return

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Draw title image or fallback text
        if self._image is not None:
            screen.blit(self._image, (self._image_rect.x, self._image_rect.y))
        else:
            title = C.FONT_TITLE.render("Random Red Solitaire", True, C.WHITE)
            screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, C.SCREEN_H//2 - title.get_height() - 20))

        # Prompt text
        prompt = C.FONT_UI.render(self._prompt_text, True, C.WHITE)
        # Pulse alpha between ~110 and 255
        t = pygame.time.get_ticks() % self._pulse_period_ms
        phase = (t / self._pulse_period_ms) * 2 * math.pi
        alpha = int(110 + 145 * (0.5 + 0.5 * math.sin(phase)))  # [110..255]
        prompt.set_alpha(alpha)
        py = max(self._image_rect.bottom, C.SCREEN_H//2) + 24
        rect = prompt.get_rect()
        rect.centerx = C.SCREEN_W // 2
        rect.top = py
        screen.blit(prompt, rect)
