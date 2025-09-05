import os
import pygame
from solitaire import common as C


SIZES = ["Small", "Medium", "Large"]
BACKS = [("Blue", 1), ("Blue", 2), ("Grey", 1), ("Grey", 2), ("Red", 1), ("Red", 2)]


class SizeButton:
    def __init__(self, label: str, w: int = 120, h: int = 42, selected: bool = False):
        self.label = label
        self.rect = pygame.Rect(0, 0, w, h)
        self.selected = selected

    def set_center(self, x: int, y: int):
        self.rect.center = (x, y)

    def hovered(self, pos) -> bool:
        return self.rect.collidepoint(pos)

    def draw(self, screen):
        bg_sel = (190, 190, 205)  # darker when selected
        bg = (230, 230, 235)
        border = (160, 160, 170)
        fill = bg_sel if self.selected else bg
        pygame.draw.rect(screen, fill, self.rect, border_radius=10)
        pygame.draw.rect(screen, border, self.rect, width=1, border_radius=10)
        t = C.FONT_UI.render(self.label, True, (30, 30, 35))
        screen.blit(t, (self.rect.centerx - t.get_width() // 2, self.rect.centery - t.get_height() // 2))


class SettingsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)

        # Load current settings
        settings = C.get_current_settings()
        size_name = settings.get("card_size", "Medium")
        if size_name not in SIZES:
            size_name = "Medium"

        color = settings.get("back_color", "Blue")
        variant = int(settings.get("back_variant", 1))
        try:
            back_idx = BACKS.index((color, variant))
        except ValueError:
            back_idx = 0

        cx = C.SCREEN_W // 2
        y = 160

        self.title_text = "Settings"

        # Size buttons (row above the preview). Medium button centered with the card.
        self.size_selected = size_name
        self.btn_small = SizeButton("Small", selected=(self.size_selected == "Small"))
        self.btn_medium = SizeButton("Medium", selected=(self.size_selected == "Medium"))
        self.btn_large = SizeButton("Large", selected=(self.size_selected == "Large"))

        y += 140
        self.preview_center = (cx, y)
        # Static Y for size buttons computed to allow largest preview without overlap
        max_h = self._size_to_wh("Large")[1]
        btn_h = self.btn_medium.rect.height
        top_margin = 16  # spacing between buttons and largest card top
        self.buttons_row_y = self.preview_center[1] - (max_h // 2 + top_margin + btn_h // 2)
        self.back_index = back_idx

        # Arrows (positions updated each draw to align with card middle)
        self.arrow_left = pygame.Rect(0, 0, 40, 40)
        self.arrow_right = pygame.Rect(0, 0, 40, 40)

        # Buttons (center group horizontally)
        by = y + 170
        bw = 200
        gap = 16
        total = bw * 2 + gap
        left_x = cx - total // 2
        self.b_save = C.Button("Save", left_x, by, w=bw, h=48, center=False)
        self.b_back = C.Button("Back", left_x + bw + gap, by, w=bw, h=48, center=False)

        # no flash message; we return to menu on Save

    # Helpers
    def _selected_size(self):
        return self.size_selected

    def _selected_back(self):
        return BACKS[self.back_index]

    def _change_back(self, delta):
        self.back_index = (self.back_index + delta) % len(BACKS)

    def _apply_and_save(self):
        size_name = self._selected_size()
        color, variant = self._selected_back()
        C.save_settings({
            "card_size": size_name,
            "back_color": color,
            "back_variant": int(variant),
        })
        # Apply runtime
        C.apply_card_settings(size_name=size_name, back_color=color, back_variant=int(variant))
        # After saving, return to main menu
        from solitaire.scenes.menu import MainMenuScene
        self.next_scene = MainMenuScene(self.app)

    def handle_event(self, e):
        # Update button and arrow layout before processing the click
        self._update_layout_positions(self._selected_size())
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Size buttons (exclusive selection)
            if self.btn_small.hovered((mx, my)):
                self._set_size("Small"); return
            if self.btn_medium.hovered((mx, my)):
                self._set_size("Medium"); return
            if self.btn_large.hovered((mx, my)):
                self._set_size("Large"); return
            if self.arrow_left.collidepoint((mx, my)):
                self._change_back(-1)
                return
            if self.arrow_right.collidepoint((mx, my)):
                self._change_back(1)
                return
            if self.b_save.hovered((mx, my)):
                self._apply_and_save()
                return
            if self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
                return
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def update(self, dt):
        pass

    def _size_to_wh(self, size_name):
        # Keep aspect ~5:7 like the gameplay
        if size_name == "Small":
            return 75, 105
        if size_name == "Large":
            return 150, 210
        return 100, 140  # Medium default

    def _set_size(self, size_name: str):
        self.size_selected = size_name
        self.btn_small.selected = (size_name == "Small")
        self.btn_medium.selected = (size_name == "Medium")
        self.btn_large.selected = (size_name == "Large")

    def _preview_surface(self, size_name):
        # Temporarily resolve path for preview without mutating global state
        # Preview uses image assets if available; falls back to current back surface
        w, h = self._size_to_wh(size_name)
        color, variant = self._selected_back()
        # Build path to the back image in the selected size
        size_dir = {"Small": "Small", "Medium": "Medium", "Large": "Large"}[size_name]
        base_dir = os.path.join(os.path.dirname(C.__file__), "assets", "cards", "PNG", size_dir)
        fname = f"Back {color} {variant}.png"
        path = os.path.join(base_dir, fname)
        try:
            if os.path.isfile(path):
                s = pygame.image.load(path)
                s = s.convert_alpha() if s.get_alpha() is not None else s.convert()
                if s.get_size() != (w, h):
                    s = pygame.transform.smoothscale(s, (w, h))
                return s
        except Exception:
            pass
        # Fallback: use current back renderer, scaled to requested size
        s = C.get_back_surface()
        if s.get_size() != (w, h):
            s = pygame.transform.smoothscale(s, (w, h))
        return s

    def draw(self, screen):
        screen.fill(C.TABLE_BG)

        # Update dynamic layout positions for current size
        self._update_layout_positions(self._selected_size())

        # Title
        title = C.FONT_TITLE.render(self.title_text, True, C.WHITE)
        screen.blit(title, (C.SCREEN_W//2 - title.get_width()//2, 80))

        # Size buttons row above preview; Medium centered with card
        self.btn_small.draw(screen)
        self.btn_medium.draw(screen)
        self.btn_large.draw(screen)

        # Preview
        size_name = self._selected_size()
        surf = self._preview_surface(size_name)
        card_x = self.preview_center[0] - surf.get_width() // 2
        card_y = self.preview_center[1] - surf.get_height() // 2
        screen.blit(surf, (card_x, card_y))

        # Arrow centers are set by _update_layout_positions; just use mid_y for drawing
        mid_y = self.preview_center[1]
        # Flip arrows to point away from the card (direction of navigation)
        pygame.draw.polygon(screen, C.WHITE, [
            (self.arrow_left.left, mid_y),
            (self.arrow_left.left + 16, mid_y - 12),
            (self.arrow_left.left + 16, mid_y + 12),
        ])
        pygame.draw.polygon(screen, C.WHITE, [
            (self.arrow_right.right, mid_y),
            (self.arrow_right.right - 16, mid_y - 12),
            (self.arrow_right.right - 16, mid_y + 12),
        ])

        # Back caption
        color, variant = self._selected_back()
        cap = C.FONT_UI.render(f"Back: {color} {variant}", True, C.WHITE)
        screen.blit(cap, (self.preview_center[0] - cap.get_width() // 2, card_y + surf.get_height() + 12))

        # Buttons
        mp = pygame.mouse.get_pos()
        self.b_save.draw(screen, hover=self.b_save.hovered(mp))
        self.b_back.draw(screen, hover=self.b_back.hovered(mp))

        # no flash now; we immediately leave on Save

    def _update_layout_positions(self, size_name: str):
        # Compute positions for size buttons and arrows based on current preview size
        w, h = self._size_to_wh(size_name)
        card_x = self.preview_center[0] - w // 2
        card_y = self.preview_center[1] - h // 2

        # Size buttons use a static Y position; Medium centered with the card horizontally
        row_y = self.buttons_row_y
        btn_w = self.btn_medium.rect.width
        spacing = 12
        # Medium
        self.btn_medium.set_center(self.preview_center[0], row_y)
        # Small to the left; Large to the right with small space
        self.btn_small.set_center(self.preview_center[0] - (btn_w + spacing), row_y)
        self.btn_large.set_center(self.preview_center[0] + (btn_w + spacing), row_y)

        # Arrows centered vertically to card
        mid_y = self.preview_center[1]
        gap = 18
        self.arrow_left.center = (card_x - gap - self.arrow_left.width // 2, mid_y)
        self.arrow_right.center = (card_x + w + gap + self.arrow_right.width // 2, mid_y)
