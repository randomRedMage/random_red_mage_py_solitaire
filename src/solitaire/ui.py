# ui.py
import pygame
from dataclasses import dataclass
from typing import Callable, Dict, Optional, List, Tuple
from solitaire import common as C

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
MENU_PANEL_BG = (245, 245, 250)

FONT = pygame.font.SysFont("Segoe UI", 18)


@dataclass
class MenuItem:
    label: str
    on_click: Callable[[], None]
    enabled: Optional[Callable[[], bool] | bool] = None
    tooltip: Optional[str] = None


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

class HamburgerMenuButton(Button):
    """Toolbar button that expands into a drop-down menu of actions."""

    def __init__(
        self,
        items: List[MenuItem],
        *,
        height: int = DEFAULT_BUTTON_HEIGHT,
        tooltip: Optional[str] = None,
    ) -> None:
        super().__init__(
            label="Menu",
            on_click=self._toggle_menu,
            height=height,
            min_width=max(height, 32),
            tooltip=tooltip,
        )
        # Compact width for icon presentation
        compact_w = max(height, 32)
        self.rect.size = (compact_w, self.rect.height)
        self.items: List[MenuItem] = items
        self._open: bool = False
        self._panel_padding: int = 6
        self._item_rects: List[pygame.Rect] = []
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._menu_hover_index: int = -1
        self._item_height: int = height
        self._menu_width: int = self.rect.width
        self._update_menu_geometry()

    def _toggle_menu(self) -> None:
        if not self.items:
            return
        if not self._open:
            self._update_menu_geometry()
        self._open = not self._open
        if not self._open:
            self._menu_hover_index = -1

    def set_position(self, x: int, y: int):
        super().set_position(x, y)
        self._item_height = self.rect.height
        if self._open:
            self._open = False
            self._menu_hover_index = -1
        self._update_menu_geometry()

    def _update_menu_geometry(self) -> None:
        if not self.items:
            self._panel_rect.size = (0, 0)
            self._item_rects = []
            return

        text_widths = [FONT.render(item.label, True, BTN_TEXT).get_width() for item in self.items]
        content_width = max([self.rect.width] + [w + DEFAULT_BUTTON_PADDING_X * 2 for w in text_widths])
        padding = self._panel_padding
        panel_width = content_width + padding * 2
        panel_height = self._item_height * len(self.items) + padding * 2

        left = self.rect.right - panel_width
        left = max(0, min(left, C.SCREEN_W - panel_width))
        top_below = self.rect.bottom + 4
        top_above = self.rect.top - 4 - panel_height
        if top_below + panel_height <= C.SCREEN_H:
            top = max(0, top_below)
        elif top_above >= 0:
            top = top_above
        else:
            top = max(0, min(top_below, C.SCREEN_H - panel_height))

        self._panel_rect = pygame.Rect(left, top, panel_width, panel_height)
        item_left = left + padding
        item_top = top + padding
        self._menu_width = content_width
        self._item_rects = []
        for index in range(len(self.items)):
            rect = pygame.Rect(item_left, item_top + index * self._item_height, content_width, self._item_height)
            self._item_rects.append(rect)

    @staticmethod
    def _item_enabled(item: MenuItem) -> bool:
        if item.enabled is None:
            return True
        if callable(item.enabled):
            try:
                return bool(item.enabled())
            except Exception:
                return False
        return bool(item.enabled)

    def _hit_test(self, pos: Tuple[int, int]) -> Optional[int]:
        for idx, rect in enumerate(self._item_rects):
            if rect.collidepoint(pos):
                return idx
        return None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            super().handle_event(event)
            if self._open:
                hovered = self._hit_test(event.pos)
                self._menu_hover_index = hovered if hovered is not None else -1
            else:
                self._menu_hover_index = -1
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._open:
                if self._panel_rect.collidepoint(event.pos):
                    idx = self._hit_test(event.pos)
                    if idx is not None:
                        item = self.items[idx]
                        if self._item_enabled(item) and callable(item.on_click):
                            item.on_click()
                        self._open = False
                        self._menu_hover_index = -1
                    else:
                        self._open = False
                        self._menu_hover_index = -1
                    return True
                elif not self.rect.collidepoint(event.pos):
                    self._open = False
                    self._menu_hover_index = -1
                    return False
            handled = super().handle_event(event)
            return handled

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and self._open:
            self._open = False
            self._menu_hover_index = -1
            return True

        return super().handle_event(event)

    def draw(self, surface: pygame.Surface):
        original_label = self.label
        self.label = ""
        super().draw(surface)
        self.label = original_label

        icon_color = BTN_TEXT if self.is_enabled() else BTN_TEXT_DISABLED
        self._draw_icon(surface, icon_color)
        if not (self._open and self.items and self._panel_rect.width > 0):
            return

        pygame.draw.rect(surface, MENU_PANEL_BG, self._panel_rect, border_radius=8)
        pygame.draw.rect(surface, BTN_BORDER, self._panel_rect, width=1, border_radius=8)

        for idx, rect in enumerate(self._item_rects):
            item = self.items[idx]
            inner = rect.inflate(-2, -2)
            enabled = self._item_enabled(item)
            if not enabled:
                bg = BTN_BG_DISABLED
            elif idx == self._menu_hover_index:
                bg = BTN_BG_HOVER
            else:
                bg = BTN_BG
            pygame.draw.rect(surface, bg, inner, border_radius=6)

            text_color = BTN_TEXT if enabled else BTN_TEXT_DISABLED
            label_surf = FONT.render(item.label, True, text_color)
            surface.blit(
                label_surf,
                (inner.left + DEFAULT_BUTTON_PADDING_X,
                 inner.centery - label_surf.get_height() // 2),
            )

    def get_menu_item_rect(self, label: str) -> Optional[pygame.Rect]:
        """Return the rect of a drop-down entry matching *label* (if available)."""

        if not self.items:
            return None
        self._update_menu_geometry()
        for idx, item in enumerate(self.items):
            if item.label == label and idx < len(self._item_rects):
                return self._item_rects[idx].copy()
        return None

    def _draw_icon(self, surface: pygame.Surface, color: Tuple[int, int, int]) -> None:
        """Draw a hamburger icon using geometry instead of relying on font glyphs."""

        rect = self.rect
        icon_width = max(4, min(rect.width - 4, int(rect.width * 0.6)))
        start_x = rect.centerx - icon_width // 2

        line_thickness = max(2, rect.height // 12)
        gap = max(2, rect.height // 10)
        total_height = line_thickness * 3 + gap * 2
        max_height = max(4, rect.height - 8)
        if total_height > max_height:
            scale = max_height / total_height
            line_thickness = max(1, int(line_thickness * scale))
            gap = max(1, int(gap * scale))
            total_height = line_thickness * 3 + gap * 2

        start_y = rect.centery - total_height // 2
        for index in range(3):
            top = start_y + index * (line_thickness + gap)
            line_rect = pygame.Rect(start_x, top, icon_width, line_thickness)
            pygame.draw.rect(surface, color, line_rect, border_radius=line_thickness // 2)


def make_toolbar(
    actions: Dict[str, Dict],
    *,
    height: int = DEFAULT_BUTTON_HEIGHT,
    margin: Tuple[int, int] = DEFAULT_TOOLBAR_MARGIN,
    gap: int = DEFAULT_BUTTON_GAP,
    align: str = "left",
    width_provider: Optional[Callable[[], int]] = None,
    primary_labels: Optional[Tuple[str, ...]] = ("Undo", "Auto"),
) -> Toolbar:
    """Create a toolbar that collapses secondary actions into a menu."""

    menu_items: List[MenuItem] = []
    direct_buttons: List[Button] = []
    menu_button_tooltip: Optional[str] = None
    visible_labels = set(primary_labels or ())

    for label, cfg in actions.items():
        on_click = cfg.get("on_click")
        if not callable(on_click):
            continue
        enabled = cfg.get("enabled")
        tooltip = cfg.get("tooltip")
        if label in visible_labels:
            direct_buttons.append(
                Button(
                    label=label,
                    on_click=on_click,
                    enabled_fn=enabled,
                    tooltip=tooltip,
                    height=height,
                )
            )
        else:
            if label.lower() == "menu" and tooltip:
                menu_button_tooltip = tooltip
            menu_items.append(MenuItem(label=label, on_click=on_click, enabled=enabled, tooltip=tooltip))

    buttons: List[Button] = []
    if menu_items:
        buttons.append(
            HamburgerMenuButton(
                menu_items,
                height=height,
                tooltip=menu_button_tooltip,
            )
        )
    buttons.extend(direct_buttons)

    return Toolbar(buttons, margin=margin, gap=gap, align=align, width_provider=width_provider)


class ModalHelp:
    """
    Simple modal help overlay: dims background, shows a centered panel with
    title, wrapped text, and a Close button. Consume ESC/Enter/H and clicks
    on Close to dismiss.
    """
    def __init__(self, title: str, lines: List[str], max_width: int = 900):
        self.title = title
        self.lines = lines[:] if lines else []
        self.visible = False
        self.max_width = max_width
        # Close button; position is computed per-draw based on panel rect
        self._close_btn = C.Button("Close", 0, 0, w=180, h=44, center=False)

    def open(self):
        self.visible = True

    def close(self):
        self.visible = False

    def _wrap_lines(self, text_lines: List[str], max_w: int) -> List[pygame.Surface]:
        """Wrap provided lines to fit max_w using C.FONT_UI, return rendered surfaces."""
        out: List[pygame.Surface] = []
        font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 24, bold=True)
        for raw in (text_lines or []):
            if not raw:
                # Blank line spacer
                out.append(font.render(" ", True, (30, 30, 35)))
                continue
            words = raw.split(" ")
            cur = ""
            for w in words:
                trial = w if not cur else (cur + " " + w)
                surf = font.render(trial, True, (30, 30, 35))
                if surf.get_width() <= max_w:
                    cur = trial
                else:
                    # flush current line
                    if cur:
                        out.append(font.render(cur, True, (30, 30, 35)))
                    # very long single word fallback
                    lw = font.render(w, True, (30, 30, 35))
                    if lw.get_width() > max_w:
                        out.append(lw)
                        cur = ""
                    else:
                        cur = w
            if cur:
                out.append(font.render(cur, True, (30, 30, 35)))
        return out

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if the event was handled/consumed."""
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_h):
                self.close()
                return True
            return True  # swallow other keys while visible
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            if self._close_btn.hovered((mx, my)):
                self.close()
                return True
            return True  # swallow other clicks while visible
        if event.type in (pygame.MOUSEMOTION, ):  # allow hover state for button
            # Recompute layout to keep hover detection accurate across resizes
            self._layout()
        return False

    def _layout(self) -> Tuple[pygame.Rect, List[pygame.Surface]]:
        # Panel width: clamp to screen and max_width
        pad = 20
        panel_w = min(self.max_width, max(400, C.SCREEN_W - 2 * 40))
        # Leave space for title + text + button
        wrapped = self._wrap_lines(self.lines, max_w=panel_w - 2 * pad)
        title_font = C.FONT_TITLE if C.FONT_TITLE is not None else pygame.font.SysFont(pygame.font.get_default_font(), 40, bold=True)
        title_surf = title_font.render(self.title, True, (20, 20, 25))
        # Estimate heights
        text_h = sum(s.get_height() for s in wrapped)
        btn_h = self._close_btn.rect.height
        title_gap = 10
        content_gap = 12
        panel_h = min(C.SCREEN_H - 120, 40 + title_surf.get_height() + title_gap + text_h + content_gap + btn_h + 24)
        # Center the panel
        panel = pygame.Rect(0, 0, panel_w, panel_h)
        panel.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        # Position button centered at bottom with small margin
        bx = panel.centerx - self._close_btn.rect.width // 2
        by = panel.bottom - self._close_btn.rect.height - 14
        self._close_btn.rect.topleft = (bx, by)
        return panel, [title_surf] + wrapped

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return
        # Dim background
        dim = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 160))
        surface.blit(dim, (0, 0))

        panel, items = self._layout()
        # Panel background
        pygame.draw.rect(surface, (240, 240, 245), panel, border_radius=12)
        pygame.draw.rect(surface, (120, 120, 130), panel, width=1, border_radius=12)

        # Title and content
        y = panel.top + 16
        # Title
        title_surf = items[0]
        surface.blit(title_surf, (panel.centerx - title_surf.get_width() // 2, y))
        y += title_surf.get_height() + 10
        # Text
        for s in items[1:]:
            surface.blit(s, (panel.left + 20, y))
            y += s.get_height()

        # Close button
        mp = pygame.mouse.get_pos()
        self._close_btn.draw(surface, hover=self._close_btn.hovered(mp))
