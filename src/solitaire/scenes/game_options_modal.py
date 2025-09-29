"""Reusable modal for configuring game options before starting a module."""

from __future__ import annotations

import pygame

from solitaire import common as C


class _ModalOption:
    """Container for a single configurable option inside the modal."""

    def __init__(self, label_func, on_click, x, y, width):
        self._label_func = label_func
        self._on_click = on_click
        self.button = C.Button("", x, y, w=width, h=48)
        self.refresh()

    def refresh(self):
        self.button.text = self._label_func()

    def click(self):
        self._on_click()
        self.refresh()


class GameOptionsModal:
    """Simple modal overlay used to tweak game settings before starting."""

    PANEL_WIDTH = 560
    PANEL_HEIGHT = 420

    def __init__(self, title, start_label, option_specs):
        """Create a modal.

        Args:
            title: Heading to display at the top of the modal.
            start_label: Text for the primary "start" button.
            option_specs: Iterable of ``(label_func, on_click)`` pairs used to
                create interactive option buttons.
        """

        self.title = title
        self._start_label = start_label
        self._options = []
        self.visible = False

        panel_x = (C.SCREEN_W - self.PANEL_WIDTH) // 2
        panel_y = (C.SCREEN_H - self.PANEL_HEIGHT) // 2
        self.panel_rect = pygame.Rect(panel_x, panel_y, self.PANEL_WIDTH, self.PANEL_HEIGHT)

        content_x = self.panel_rect.left + 40
        y = self.panel_rect.top + 140
        option_width = self.PANEL_WIDTH - 80
        for label_func, on_click in option_specs:
            opt = _ModalOption(label_func, on_click, content_x, y, option_width)
            self._options.append(opt)
            y += 64

        button_y = self.panel_rect.bottom - 92
        self._start_button = C.Button(self._start_label, content_x, button_y, w=220, h=48)
        cancel_x = self.panel_rect.right - 40 - 160
        self._cancel_button = C.Button("Cancel", cancel_x, button_y, w=160, h=48)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def open(self):
        self.visible = True
        self.refresh()

    def close(self):
        self.visible = False

    def refresh(self):
        for opt in self._options:
            opt.refresh()
        self._start_button.text = self._start_label

    # ------------------------------------------------------------------
    def handle_event(self, event):
        """Handle pygame events.

        Returns:
            ``"start"`` when the start button was clicked,
            ``"close"`` when the modal should close,
            ``"consumed"`` if the event was handled otherwise,
            or ``None`` if the modal is not visible.
        """

        if not self.visible:
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse = event.pos
            if self._start_button.hovered(mouse):
                return "start"
            if self._cancel_button.hovered(mouse):
                self.close()
                return "close"
            for opt in self._options:
                if opt.button.hovered(mouse):
                    opt.click()
                    return "consumed"
            if not self.panel_rect.collidepoint(mouse):
                self.close()
                return "close"
            return "consumed"

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return "close"
            return "consumed"

        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
            return "consumed"

        return "consumed"

    def draw(self, screen):
        if not self.visible:
            return

        # Dim background
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        # Panel
        pygame.draw.rect(screen, C.LIGHT, self.panel_rect, border_radius=18)
        pygame.draw.rect(screen, C.BLACK, self.panel_rect, 2, border_radius=18)

        title_text = C.FONT_TITLE.render(self.title, True, C.BLACK)
        title_pos = (
            self.panel_rect.centerx - title_text.get_width() // 2,
            self.panel_rect.top + 50,
        )
        screen.blit(title_text, title_pos)

        subtitle = C.FONT_SMALL.render("Adjust the settings before starting.", True, C.BLACK)
        subtitle_pos = (
            self.panel_rect.centerx - subtitle.get_width() // 2,
            title_pos[1] + title_text.get_height() + 10,
        )
        screen.blit(subtitle, subtitle_pos)

        mouse_pos = pygame.mouse.get_pos()
        for opt in self._options:
            opt.button.draw(screen, hover=opt.button.hovered(mouse_pos))
        self._start_button.draw(screen, hover=self._start_button.hovered(mouse_pos))
        self._cancel_button.draw(screen, hover=self._cancel_button.hovered(mouse_pos))

