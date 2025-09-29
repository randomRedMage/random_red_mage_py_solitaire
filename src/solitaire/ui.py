# ui.py
import pygame
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
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
    """Toolbar button that opens an in-game modal menu."""

    def __init__(
        self,
        on_click: Callable[[], None],
        *,
        height: int = DEFAULT_BUTTON_HEIGHT,
        tooltip: Optional[str] = None,
    ) -> None:
        super().__init__(
            label="Menu",
            on_click=on_click,
            height=height,
            min_width=max(height, 32),
            tooltip=tooltip,
        )
        compact_w = max(height, 32)
        self.rect.size = (compact_w, self.rect.height)

    def draw(self, surface: pygame.Surface):
        original_label = self.label
        self.label = ""
        super().draw(surface)
        self.label = original_label

        icon_color = BTN_TEXT if self.is_enabled() else BTN_TEXT_DISABLED
        self._draw_icon(surface, icon_color)

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
    """Create a toolbar that shows primary actions and a modal menu button."""

    direct_buttons: List[Button] = []
    menu_button_tooltip: Optional[str] = None
    menu_callback: Optional[Callable[[], None]] = None
    visible_labels = set(primary_labels or ())

    for label, cfg in actions.items():
        on_click = cfg.get("on_click")
        if not callable(on_click):
            continue
        enabled = cfg.get("enabled")
        tooltip = cfg.get("tooltip")
        if label.lower() == "menu":
            menu_callback = on_click
            if tooltip:
                menu_button_tooltip = tooltip
            continue
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

    buttons: List[Button] = []
    if menu_callback:
        buttons.append(
            HamburgerMenuButton(
                menu_callback,
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


class GameMenuModal:
    """Modal overlay that exposes in-game actions and quit options."""

    PANEL_WIDTH = 480
    PANEL_MIN_WIDTH = 340
    PANEL_PADDING_X = 48
    PADDING_TOP = 96
    BUTTON_HEIGHT = 52
    BUTTON_GAP = 16
    BOTTOM_PADDING = 48

    def __init__(
        self,
        helper,
        *,
        new_action: Optional[Tuple[str, Mapping[str, Any]]] = None,
        restart_action: Optional[Tuple[str, Mapping[str, Any]]] = None,
        help_action: Optional[Tuple[str, Mapping[str, Any]]] = None,
        save_action: Optional[Tuple[str, Mapping[str, Any]]] = None,
        hint_action: Optional[Tuple[str, Mapping[str, Any]]] = None,
    ) -> None:
        self.helper = helper
        self.visible = False
        self._panel_rect = pygame.Rect(0, 0, 0, 0)
        self._title_pos: Tuple[int, int] = (0, 0)
        self._buttons: List[Button] = []
        self._button_keys: List[str] = []
        self._actions: Dict[str, Optional[Tuple[str, Mapping[str, Any]]]] = {
            "new": new_action,
            "restart": restart_action,
            "help": help_action,
            "save": save_action,
            "hint": hint_action,
        }
        self._layout_dirty = True
        self._confirm_state: Optional[Dict[str, Any]] = None
        self._build_buttons()

    def _build_buttons(self) -> None:
        self._buttons = []
        self._button_keys = []
        specs: List[Tuple[str, str]] = []
        if self._actions.get("new"):
            specs.append(("new", "New Game"))
        if self._actions.get("restart"):
            specs.append(("restart", "Restart Game"))
        if self._actions.get("hint"):
            specs.append(("hint", "Hint"))
        specs.append(("options", "Game Options"))
        if self._actions.get("help"):
            specs.append(("help", "Help"))
        if self._actions.get("save"):
            specs.append(("save", "Save and Exit"))
        specs.append(("quit_menu", "Quit to Menu"))
        specs.append(("quit_desktop", "Quit to Desktop"))
        specs.append(("cancel", "Cancel"))

        for key, label in specs:
            enabled_fn: Optional[Callable[[], bool]] = None
            if key in ("new", "restart", "hint", "help", "save"):
                entry = self._actions.get(key)
                if entry is None:
                    continue
                enabled_fn = (lambda e=entry: self._is_entry_enabled(e))
            elif key == "options":
                enabled_fn = self.helper.can_open_options
            button = Button(
                label=label,
                on_click=lambda k=key: self._handle_button(k),
                enabled_fn=enabled_fn,
                height=self.BUTTON_HEIGHT,
                min_width=260,
            )
            self._buttons.append(button)
            self._button_keys.append(key)
        self._layout_dirty = True

    def relayout(self) -> None:
        self._layout_dirty = True

    def open(self) -> None:
        self.visible = True
        self._confirm_state = None
        self._layout_dirty = True

    def close(self) -> None:
        self.visible = False
        self._confirm_state = None

    def toggle(self) -> None:
        if self.visible:
            self.close()
        else:
            self.open()

    def has_pending_confirm(self) -> bool:
        return bool(self._confirm_state)

    def has_pending_quit_confirm(self) -> bool:
        state = self._confirm_state or {}
        return state.get("kind") == "quit"

    def _execute_confirm_option(self, index: int) -> bool:
        if not self._confirm_state:
            return False
        options: Sequence[Dict[str, Any]] = self._confirm_state.get("options", [])  # type: ignore[index]
        if not (0 <= index < len(options)):
            return False
        action = options[index].get("action")
        self._confirm_state = None
        if callable(action):
            action()
            return True
        return False

    def accept_default_confirm(self) -> bool:
        return self._execute_confirm_option(0)

    def _is_entry_enabled(self, entry: Tuple[str, Mapping[str, Any]]) -> bool:
        enabled = entry[1].get("enabled", True)
        if callable(enabled):
            try:
                return bool(enabled())
            except Exception:
                return False
        return bool(enabled)

    def _execute_entry(self, entry: Optional[Tuple[str, Mapping[str, Any]]]) -> None:
        if entry is None:
            return
        if not self._is_entry_enabled(entry):
            return
        callback = entry[1].get("on_click")
        if not callable(callback):
            return
        self.close()
        callback()

    def _request_confirm(
        self,
        message: str,
        *,
        options: Sequence[Tuple[str, Callable[[], None]]],
        cancel_label: str = "Cancel",
        kind: Optional[str] = None,
    ) -> None:
        entries: List[Dict[str, Any]] = []
        for label, action in options:
            if not callable(action):
                continue
            entries.append({"label": label, "action": action})
        if not entries:
            return
        self._confirm_state = {
            "message": message,
            "options": entries,
            "cancel_label": cancel_label,
        }
        if kind:
            self._confirm_state["kind"] = kind

    def _handle_button(self, key: str) -> None:
        if key == "new":
            entry = self._actions.get("new")
            if entry is None:
                return
            if self.helper.should_confirm_reset():
                self._request_confirm(
                    "Start a new game?\nUnsaved progress will be lost.",
                    options=[("OK", lambda e=entry: self._execute_entry(e))],
                )
            else:
                self._execute_entry(entry)
        elif key == "restart":
            entry = self._actions.get("restart")
            if entry is None:
                return
            if self.helper.should_confirm_reset():
                self._request_confirm(
                    "Restart the current game?\nUnsaved progress will be lost.",
                    options=[("OK", lambda e=entry: self._execute_entry(e))],
                )
            else:
                self._execute_entry(entry)
        elif key == "hint":
            self._execute_entry(self._actions.get("hint"))
        elif key == "help":
            self._execute_entry(self._actions.get("help"))
        elif key == "save":
            self._execute_entry(self._actions.get("save"))
        elif key == "options":
            if self.helper.can_open_options():
                self.close()
                self.helper.open_options()
        elif key == "quit_menu":
            self._confirm_quit(target="menu")
        elif key == "quit_desktop":
            self._confirm_quit(target="desktop")
        elif key == "cancel":
            self.close()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False
        if self._confirm_state:
            return self._handle_confirm_event(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self._panel_rect.collidepoint(event.pos):
                self.close()
                return True
        if event.type == pygame.MOUSEMOTION:
            for btn in self._buttons:
                btn.handle_event(event)
            return True
        for btn in self._buttons:
            if btn.handle_event(event):
                return True
        return True

    def _handle_confirm_event(self, event: pygame.event.Event) -> bool:
        state = self._confirm_state or {}
        options: Sequence[Dict[str, Any]] = state.get("options", [])
        cancel_label = state.get("cancel_label")
        modal_rect, option_rects, cancel_rect = self._confirm_geometry(
            len(options), bool(cancel_label)
        )
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_n):
                self._confirm_state = None
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y):
                if options:
                    self._execute_confirm_option(0)
                return True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for idx, rect in enumerate(option_rects):
                if rect.collidepoint(event.pos):
                    self._execute_confirm_option(idx)
                    return True
            if cancel_rect and cancel_rect.collidepoint(event.pos):
                self._confirm_state = None
                return True
            if not modal_rect.collidepoint(event.pos):
                return True
        return True

    def _confirm_geometry(
        self, option_count: int, include_cancel: bool
    ) -> Tuple[pygame.Rect, List[pygame.Rect], Optional[pygame.Rect]]:
        width, height = 460, 220
        total_buttons = max(1, option_count + (1 if include_cancel else 0))
        btn_w, btn_h = 150, 46
        gap = 28
        total_width = total_buttons * btn_w + max(0, total_buttons - 1) * gap
        modal_width = max(width, total_width + 80)
        modal = pygame.Rect(0, 0, modal_width, height)
        modal.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        start_x = modal.centerx - total_width // 2
        option_rects: List[pygame.Rect] = []
        for i in range(option_count):
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.x = start_x + i * (btn_w + gap)
            rect.bottom = modal.bottom - 28
            option_rects.append(rect)
        cancel_rect: Optional[pygame.Rect] = None
        if include_cancel:
            rect = pygame.Rect(0, 0, btn_w, btn_h)
            rect.x = start_x + option_count * (btn_w + gap)
            rect.bottom = modal.bottom - 28
            cancel_rect = rect
        return modal, option_rects, cancel_rect

    def _reflow(self) -> None:
        width = min(self.PANEL_WIDTH, max(self.PANEL_MIN_WIDTH, C.SCREEN_W - 120))
        button_width = max(220, width - 2 * self.PANEL_PADDING_X)
        count = len(self._buttons)
        total_height = count * self.BUTTON_HEIGHT + max(0, count - 1) * self.BUTTON_GAP
        height = self.PADDING_TOP + total_height + self.BOTTOM_PADDING
        panel = pygame.Rect(0, 0, width, height)
        panel.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        self._panel_rect = panel
        self._title_pos = (panel.centerx, panel.y + 36)
        y = panel.y + self.PADDING_TOP
        for btn in self._buttons:
            btn.rect.size = (button_width, self.BUTTON_HEIGHT)
            btn.set_position(panel.centerx - button_width // 2, y)
            y += self.BUTTON_HEIGHT + self.BUTTON_GAP
        self._layout_dirty = False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.visible:
            return
        if self._layout_dirty:
            self._reflow()
        overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))
        pygame.draw.rect(surface, (250, 250, 250), self._panel_rect, border_radius=24)
        pygame.draw.rect(surface, (80, 80, 90), self._panel_rect, width=2, border_radius=24)
        title_font = C.FONT_TITLE or pygame.font.SysFont(pygame.font.get_default_font(), 40, bold=True)
        title_surf = title_font.render("Game Menu", True, (40, 40, 45))
        surface.blit(title_surf, (self._title_pos[0] - title_surf.get_width() // 2, self._title_pos[1]))
        for btn in self._buttons:
            btn.draw(surface)
        if self._confirm_state:
            self._draw_confirm(surface)

    def _draw_confirm(self, surface: pygame.Surface) -> None:
        state = self._confirm_state or {}
        options: Sequence[Dict[str, Any]] = state.get("options", [])
        cancel_label = state.get("cancel_label")
        modal_rect, option_rects, cancel_rect = self._confirm_geometry(
            len(options), bool(cancel_label)
        )
        pygame.draw.rect(surface, (245, 245, 245), modal_rect, border_radius=16)
        pygame.draw.rect(surface, (90, 90, 95), modal_rect, width=2, border_radius=16)
        title_font = C.FONT_TITLE or pygame.font.SysFont(pygame.font.get_default_font(), 34, bold=True)
        title = title_font.render("Warning", True, (40, 40, 45))
        surface.blit(title, (modal_rect.centerx - title.get_width() // 2, modal_rect.y + 18))
        msg_font = C.FONT_UI or pygame.font.SysFont(pygame.font.get_default_font(), 24)
        message = self._confirm_state.get("message", "")
        lines = [line.strip() for line in message.splitlines() if line.strip()] or [message]
        y = modal_rect.y + 18 + title.get_height() + 12
        for line in lines:
            surf = msg_font.render(line, True, (40, 40, 45))
            surface.blit(surf, (modal_rect.centerx - surf.get_width() // 2, y))
            y += surf.get_height() + 4
        def draw_btn(rect: pygame.Rect, label: str) -> None:
            pygame.draw.rect(surface, (230, 230, 235), rect, border_radius=10)
            pygame.draw.rect(surface, (90, 90, 95), rect, width=1, border_radius=10)

            def wrap_text(text: str, max_width: int) -> List[str]:
                words = text.split()
                if not words:
                    return [""]
                lines: List[str] = []
                current = words[0]
                for word in words[1:]:
                    candidate = f"{current} {word}".strip()
                    if msg_font.size(candidate)[0] <= max_width:
                        current = candidate
                    else:
                        lines.append(current)
                        current = word
                if current:
                    lines.append(current)
                return lines or [""]

            text_lines = wrap_text(label, rect.width - 16)
            rendered = [msg_font.render(line, True, (30, 30, 35)) for line in text_lines]
            if rendered:
                line_gap = 4
                total_height = sum(s.get_height() for s in rendered) + line_gap * (len(rendered) - 1)
                y = rect.centery - total_height // 2
                for surf in rendered:
                    surface.blit(surf, (rect.centerx - surf.get_width() // 2, y))
                    y += surf.get_height() + line_gap

        for rect, option in zip(option_rects, options):
            draw_btn(rect, str(option.get("label", "OK")))
        if cancel_rect and cancel_label:
            draw_btn(cancel_rect, str(cancel_label))

    def _confirm_quit(self, *, target: str) -> None:
        def quit_without_save() -> None:
            self.close()
            if target == "menu":
                self.helper.goto_main_menu()
            else:
                self.helper.quit_to_desktop()

        message = (
            "Quit to main menu?\nUnsaved progress will be lost."
            if target == "menu"
            else "Quit to desktop?\nUnsaved progress will be lost."
        )

        options: List[Tuple[str, Callable[[], None]]] = [
            ("Quit Without Saving", quit_without_save)
        ]

        save_entry = self._actions.get("save")
        if save_entry and self._is_entry_enabled(save_entry):
            def save_and_quit(entry=save_entry) -> None:
                self._execute_entry(entry)
                if target == "desktop":
                    self.helper.quit_to_desktop()
                else:
                    self.helper.goto_main_menu()

            options.append(("Save And Quit", save_and_quit))


        self._request_confirm(message, options=options, kind="quit")
