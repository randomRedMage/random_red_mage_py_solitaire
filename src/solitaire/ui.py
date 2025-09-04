# ui.py
import pygame
from typing import Callable, Dict, Optional, List, Tuple

pygame.font.init()

# --- Centralized style (match Pyramid’s button height) ---
DEFAULT_BUTTON_HEIGHT = 36
DEFAULT_BUTTON_PADDING_X = 12
DEFAULT_BUTTON_GAP = 8
DEFAULT_TOOLBAR_MARGIN = (12, 12)  # (x, y) from the chosen edge

# Colors
BTN_BG = (230, 230, 235)
BTN_BG_HOVER = (215, 215, 225)
BTN_BG_DISABLED = (200, 200, 205)
BTN_BORDER = (160, 160, 170)
BTN_TEXT = (30, 30, 35)
BTN_TEXT_DISABLED = (120, 120, 130)

FONT = pygame.font.SysFont("Segoe UI", 18)

class Button:
    def __init__(
        self,
        label: str,
        on_click: Callable[[], None],
        enabled_fn: Optional[Callable[[], bool]] = None,
        tooltip: Optional[str] = None,
        height: int = DEFAULT_BUTTON_HEIGHT,
        min_width: int = 0,
    ):
        self.label = label
        self.on_click = on_click
        self.enabled_fn = enabled_fn
        self.tooltip = tooltip
        self.height = height
        self.min_width = min_width
        self.rect = pygame.Rect(0, 0, 0, 0)
        self._hover = False

        text_w = FONT.render(self.label, True, BTN_TEXT).get_width()
        w = max(self.min_width, text_w + DEFAULT_BUTTON_PADDING_X * 2)
        self.rect.size = (w, self.height)

    def is_enabled(self) -> bool:
        return True if self.enabled_fn is None else bool(self.enabled_fn())

    def set_position(self, x: int, y: int):
        self.rect.topleft = (x, y)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._hover and self.is_enabled():
                self.on_click()
                return True
        return False

    def draw(self, surface: pygame.Surface):
        enabled = self.is_enabled()
        bg = BTN_BG_DISABLED if not enabled else (BTN_BG_HOVER if self._hover else BTN_BG)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, BTN_BORDER, self.rect, width=1, border_radius=8)
        color = BTN_TEXT if enabled else BTN_TEXT_DISABLED
        label_surf = FONT.render(self.label, True, color)
        surface.blit(
            label_surf,
            (self.rect.centerx - label_surf.get_width() // 2,
             self.rect.centery - label_surf.get_height() // 2),
        )

class Toolbar:
    """Upper toolbar; supports left or right alignment."""
    def __init__(
        self,
        buttons: List[Button],
        margin: Tuple[int, int] = DEFAULT_TOOLBAR_MARGIN,
        gap: int = DEFAULT_BUTTON_GAP,
        align: str = "left",                 # 'left' or 'right'
        width_provider: Optional[Callable[[], int]] = None,
    ):
        self.buttons = buttons
        self.margin = margin
        self.gap = gap
        self.align = align
        self.width_provider = width_provider
        self._layout()

    def _total_width(self) -> int:
        if not self.buttons:
            return 0
        return sum(b.rect.width for b in self.buttons) + self.gap * (len(self.buttons) - 1)

    def _layout(self):
        mx, my = self.margin
        if self.align == "right" and callable(self.width_provider):
            x = self.width_provider() - mx - self._total_width()
        else:
            x = mx
        y = my
        for b in self.buttons:
            b.set_position(x, y)
            x += b.rect.width + self.gap

    def relayout(self):
        self._layout()

    def handle_event(self, event: pygame.event.Event) -> bool:
        for b in self.buttons:
            if b.handle_event(event):
                return True
        return False

    def draw(self, surface: pygame.Surface):
        for b in self.buttons:
            b.draw(surface)

def make_toolbar(
    actions: Dict[str, Dict],
    height: int = DEFAULT_BUTTON_HEIGHT,
    margin: Tuple[int, int] = DEFAULT_TOOLBAR_MARGIN,
    gap: int = DEFAULT_BUTTON_GAP,
    align: str = "left",
    width_provider: Optional[Callable[[], int]] = None,
) -> Toolbar:
    """
    actions = {
      "New": {"on_click": fn, "enabled": fn_opt, "tooltip": str_opt},
      ...
    }
    """
    btns: List[Button] = []
    for label, cfg in actions.items():
        btns.append(
            Button(
                label=label,
                on_click=cfg["on_click"],
                enabled_fn=cfg.get("enabled"),
                tooltip=cfg.get("tooltip"),
                height=height,
            )
        )
    return Toolbar(btns, margin=margin, gap=gap, align=align, width_provider=width_provider)
