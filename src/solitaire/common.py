
# common.py - shared utilities for Solitaire Suite
import os
import json
import pygame
from collections import deque
from typing import Callable, List, Optional

# --- Settings / Image card settings ---
USE_IMAGE_CARDS = True

# Defaults (may be overridden by persisted settings)
_DEFAULT_SETTINGS = {
    "card_size": "Medium",   # Small | Medium | Large
    "back_color": "Blue",    # Blue | Grey | Red
    "back_variant": 1,        # 1 | 2
}

_CURRENT_SETTINGS = dict(_DEFAULT_SETTINGS)

def _settings_dir() -> str:
    # Prefer %APPDATA% on Windows, else ~/.random_red_mage_solitaire
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "RandomRedMageSolitaire")
    return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")

def _settings_path() -> str:
    return os.path.join(_settings_dir(), "settings.json")


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def project_saves_dir(subdir: Optional[str] = None) -> str:
    base = os.path.join(_project_root(), "saves")
    if subdir:
        base = os.path.join(base, subdir)
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return base

def get_current_settings():
    return dict(_CURRENT_SETTINGS)

def load_settings():
    global _CURRENT_SETTINGS
    try:
        with open(_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _CURRENT_SETTINGS.update({
                    "card_size": data.get("card_size", _CURRENT_SETTINGS["card_size"]),
                    "back_color": data.get("back_color", _CURRENT_SETTINGS["back_color"]),
                    "back_variant": int(data.get("back_variant", _CURRENT_SETTINGS["back_variant"]))
                })
    except Exception:
        pass

def save_settings(new_values: dict):
    # Merge and write to disk
    global _CURRENT_SETTINGS
    _CURRENT_SETTINGS.update({
        k: new_values[k] for k in ("card_size", "back_color", "back_variant") if k in new_values
    })
    try:
        os.makedirs(_settings_dir(), exist_ok=True)
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(_CURRENT_SETTINGS, f, indent=2)
    except Exception:
        pass

def _size_to_dims(size_name: str):
    size_name = (size_name or "Medium").capitalize()
    if size_name == "Small":
        return 75, 105
    if size_name == "Large":
        return 150, 210
    return 100, 140

def _size_to_dir(size_name: str):
    size_name = (size_name or "Medium").capitalize()
    return {"Small": "Small", "Medium": "Medium", "Large": "Large"}.get(size_name, "Medium")

def invalidate_card_caches():
    global _img_face_cache, _img_back_cache, _card_face_cache, _card_back_cache
    _img_face_cache = {}
    _img_back_cache = None
    _card_face_cache = {}
    _card_back_cache = None

def apply_card_settings(size_name: str = None, back_color: str = None, back_variant: int = None):
    # Update globals for gameplay rendering
    global IMAGE_CARDS_DIR, BACK_COLOR, BACK_VARIANT, CARD_W, CARD_H
    if size_name is not None:
        CARD_W, CARD_H = _size_to_dims(size_name)
        IMAGE_CARDS_DIR = os.path.join(os.path.dirname(__file__), "assets", "cards", "PNG", _size_to_dir(size_name))
    if back_color is not None:
        BACK_COLOR = back_color
    if back_variant is not None:
        BACK_VARIANT = int(back_variant)
    invalidate_card_caches()

# Load any persisted settings and apply now
load_settings()
IMAGE_CARDS_DIR = os.path.join(os.path.dirname(__file__), "assets", "cards", "PNG", _size_to_dir(_CURRENT_SETTINGS["card_size"]))
BACK_COLOR = _CURRENT_SETTINGS["back_color"]
BACK_VARIANT = int(_CURRENT_SETTINGS["back_variant"])


# ---------- Configuration ----------
SCREEN_W, SCREEN_H = 1280, 800
GREEN_TABLE = (2, 100, 40)
TABLE_BG = GREEN_TABLE

CARD_W, CARD_H = _size_to_dims(_CURRENT_SETTINGS.get("card_size", "Medium"))
CARD_RADIUS = 10
CARD_GAP_X = 18
CARD_GAP_Y = 26

# Fonts are initialized via setup_fonts() AFTER pygame.init() in main.py
FONT_NAME = None
FONT_RANK = None
FONT_SMALL = None
FONT_UI = None
FONT_TITLE = None
FONT_CORNER_RANK = None
FONT_CORNER_SUIT = None
FONT_CENTER_SUIT = None

def setup_fonts():
    global FONT_NAME, FONT_RANK, FONT_SMALL, FONT_UI, FONT_TITLE, FONT_CORNER_RANK, FONT_CORNER_SUIT, FONT_CENTER_SUIT
    FONT_NAME = pygame.font.get_default_font()
    # Core UI/number fonts (system default is fine)
    FONT_RANK = pygame.font.SysFont(FONT_NAME, 24, bold=True)
    FONT_SMALL = pygame.font.SysFont(FONT_NAME, 20, bold=True)
    FONT_UI = pygame.font.SysFont(FONT_NAME, 26, bold=True)
    FONT_TITLE = pygame.font.SysFont(FONT_NAME, 44, bold=True)
    FONT_CORNER_RANK = pygame.font.SysFont(FONT_NAME, 28, bold=True)

    # Suit glyphs require a Unicode-capable font. Prefer bundled DejaVuSans.
    suit_font_small = None
    suit_font_large = None
    try:
        _font_path = os.path.join(os.path.dirname(__file__), "assets", "fonts", "DejaVuSans.ttf")
        if os.path.isfile(_font_path):
            suit_font_small = pygame.font.Font(_font_path, 26)
            suit_font_large = pygame.font.Font(_font_path, 56)
    except Exception:
        suit_font_small = None
        suit_font_large = None
    # Fallbacks for environments without the bundled font
    if suit_font_small is None:
        try:
            suit_font_small = pygame.font.SysFont("Segoe UI Symbol", 26, bold=True)
        except Exception:
            suit_font_small = pygame.font.SysFont(FONT_NAME, 26, bold=True)
    if suit_font_large is None:
        try:
            suit_font_large = pygame.font.SysFont("Segoe UI Symbol", 56, bold=True)
        except Exception:
            suit_font_large = pygame.font.SysFont(FONT_NAME, 56, bold=True)

    FONT_CORNER_SUIT = suit_font_small
    FONT_CENTER_SUIT = suit_font_large

# UI bar heights
TOP_BAR_H = 60

# Colors
BLACK = (20, 20, 20)
WHITE = (245, 245, 245)
RED = (200, 20, 20)
BLUE = (34, 96, 200)
GOLD = (230, 190, 80)
LIGHT = (220, 220, 220)

SUITS = ["♠", "♥", "♦", "♣"]  # 0..3
RANK_TO_TEXT = {1:"A", 11:"J", 12:"Q", 13:"K"}
for _r in range(2,11):
    RANK_TO_TEXT[_r] = str(_r)

def is_red(suit):
    return suit in (1,2)  # hearts, diamonds

# ---------- Cards & Piles ----------
class Card:
    __slots__ = ("suit", "rank", "face_up")
    def __init__(self, suit, rank, face_up=False):
        self.suit = suit   # 0..3
        self.rank = rank   # 1..13
        self.face_up = face_up
    def color(self):
        return "red" if is_red(self.suit) else "black"
    def __repr__(self):
        return f"{RANK_TO_TEXT[self.rank]}{SUITS[self.suit]}{'↑' if self.face_up else '↓'}"

def make_deck(shuffle=True):
    import random
    d = [Card(suit, rank, False) for suit in range(4) for rank in range(1,14)]
    if shuffle:
        random.shuffle(d)
    return d

_card_face_cache = {}
_card_back_cache = None

# Global draw offsets for scrolling game areas (set by scenes during draw)
DRAW_OFFSET_X = 0
DRAW_OFFSET_Y = 0

def draw_suit_shape(surface, center, suit_index, color, size=42):
    x, y = center
    if suit_index == 2:  # ♦ diamond
        half = size//2
        points = [(x, y - half), (x + half, y), (x, y + half), (x - half, y)]
        pygame.draw.polygon(surface, color, points)
    elif suit_index == 1:  # ♥ heart
        r = size//3
        pygame.draw.circle(surface, color, (x - r, y - r), r)
        pygame.draw.circle(surface, color, (x + r, y - r), r)
        tri = [(x - 2*r, y - r), (x + 2*r, y - r), (x, y + 2*r)]
        pygame.draw.polygon(surface, color, tri)
    elif suit_index == 0:  # ♠ spade
        r = size//3
        pygame.draw.circle(surface, color, (x - r, y), r)
        pygame.draw.circle(surface, color, (x + r, y), r)
        tri = [(x - 2*r, y), (x + 2*r, y), (x, y - 2*r)]
        pygame.draw.polygon(surface, color, tri)
        stem_w = max(6, size//6)
        pygame.draw.rect(surface, color, (x - stem_w//2, y + r, stem_w, size//2))
    else:  # ♣ club
        r = size//3
        pygame.draw.circle(surface, color, (x, y - r), r)
        pygame.draw.circle(surface, color, (x - r, y + r//3), r)
        pygame.draw.circle(surface, color, (x + r, y + r//3), r)
        stem_w = max(6, size//6)
        pygame.draw.rect(surface, color, (x - stem_w//2, y + r, stem_w, size//2))

# Cache
_img_face_cache = {}   # (suit, rank) -> Surface
_img_back_cache = None

# Suit index -> name(s) used in filenames; try both to be safe
_SUITS_PRIMARY  = {0: "Spades",   1: "Hearts",   2: "Diamonds", 3: "Clubs"}
_SUITS_ALT      = {0: "Spade",    1: "Heart",    2: "Diamond",  3: "Club"}  # just in case

def _face_filename_stems(suit_index, rank):
    """Yield plausible filename stems (without extension) for a card face."""
    yield f"{_SUITS_PRIMARY[suit_index]} {rank}"
    yield f"{_SUITS_ALT[suit_index]} {rank}"

def _back_filename_stems():
    """Yield plausible filename stems (without extension) for backs in a sensible order."""
    # Start with the user's preferred choice
    yield f"Back {BACK_COLOR} {BACK_VARIANT}"
    # Then try other variants/colors
    for color in ("Blue", "Grey", "Red"):
        for n in (1, 2):
            if color == BACK_COLOR and n == BACK_VARIANT:
                continue
            yield f"Back {color} {n}"

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

def _find_file_for_stem(stem):
    for ext in _IMAGE_EXTS:
        p = os.path.join(IMAGE_CARDS_DIR, stem + ext)
        if os.path.isfile(p):
            return p
    return None

def _load_scaled(path, size):
    try:
        surf = pygame.image.load(path)
        # convert after display is set (we're called during gameplay)
        surf = surf.convert_alpha() if surf.get_alpha() is not None else surf.convert()
        if surf.get_size() != size:
            surf = pygame.transform.smoothscale(surf, size)
        return surf
    except Exception:
        return None

def _get_image_face_surface(card, size):
    key = (card.suit, card.rank)
    if key in _img_face_cache:
        return _img_face_cache[key]
    for stem in _face_filename_stems(card.suit, card.rank):
        path = _find_file_for_stem(stem)
        if path:
            s = _load_scaled(path, size)
            if s:
                _img_face_cache[key] = s
                return s
    return None

def _get_image_back_surface(size):
    global _img_back_cache
    if _img_back_cache is not None:
        return _img_back_cache
    for stem in _back_filename_stems():
        path = _find_file_for_stem(stem)
        if path:
            s = _load_scaled(path, size)
            if s:
                _img_back_cache = s
                return s
    return None



def get_card_surface(card):
        # NEW: image-based rendering first
    if USE_IMAGE_CARDS:
        if not card.face_up:
            return get_back_surface()
        s = _get_image_face_surface(card, (CARD_W, CARD_H))
        if s is not None:
            return s
    # EXISTING fallback drawing continues below...

    if not card.face_up:
        return get_back_surface()
    key = (card.suit, card.rank)
    if key in _card_face_cache:
        return _card_face_cache[key]
    surf = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
    pygame.draw.rect(surf, WHITE, (0,0,CARD_W,CARD_H), border_radius=CARD_RADIUS)
    pygame.draw.rect(surf, BLACK, (0,0,CARD_W,CARD_H), width=3, border_radius=CARD_RADIUS)
    color = RED if is_red(card.suit) else BLACK
    margin = 10
    rtxt = FONT_CORNER_RANK.render(RANK_TO_TEXT[card.rank], True, color)
    stxt = FONT_CORNER_SUIT.render(SUITS[card.suit], True, color)
    surf.blit(rtxt, (margin, margin))
    surf.blit(stxt, (margin, margin + rtxt.get_height() - 2))
    r180 = pygame.transform.rotate(rtxt, 180)
    s180 = pygame.transform.rotate(stxt, 180)
    surf.blit(r180, (CARD_W - margin - r180.get_width(), CARD_H - margin - r180.get_height() - s180.get_height() + 2))
    surf.blit(s180, (CARD_W - margin - s180.get_width(), CARD_H - margin - s180.get_height()))
    draw_suit_shape(surf, (CARD_W//2, CARD_H//2), card.suit, color, size=56)
    _card_face_cache[key] = surf
    return surf

def get_back_surface():

    global _card_back_cache
    # NEW: image-based back first
    if USE_IMAGE_CARDS:
        s = _get_image_back_surface((CARD_W, CARD_H))
        if s is not None:
            return s
    # EXISTING fallback drawing continues below...

    global _card_back_cache
    if _card_back_cache is not None:
        return _card_back_cache
    surf = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
    pygame.draw.rect(surf, WHITE, (0,0,CARD_W,CARD_H), border_radius=CARD_RADIUS)
    pygame.draw.rect(surf, BLACK, (0,0,CARD_W,CARD_H), width=3, border_radius=CARD_RADIUS)
    inset = 8
    inner_rect = pygame.Rect(inset, inset, CARD_W-2*inset, CARD_H-2*inset)
    pygame.draw.rect(surf, (34,96,200), inner_rect, border_radius=8)
    for i in range(-CARD_H, CARD_W, 12):
        pygame.draw.line(surf, LIGHT, (i, 8), (i+CARD_H, CARD_H-8), 1)
        pygame.draw.line(surf, LIGHT, (i+6, 8), (i+CARD_H+6, CARD_H-8), 1)
    _card_back_cache = surf
    return surf

class Draggable:
    def __init__(self):
        self.dragging = False
        self.drag_offset = (0,0)
        self.drag_cards = []

class Pile(Draggable):
    def __init__(self, x, y, fan_y=0, fan_x=0):
        super().__init__()
        self.x, self.y = x, y
        self.cards = []
        self.fan_y = fan_y
        self.fan_x = fan_x
    def rect_for_index(self, idx):
        rx = self.x + idx * self.fan_x
        ry = self.y + idx * self.fan_y
        return pygame.Rect(rx, ry, CARD_W, CARD_H)
    def top_rect(self):
        if not self.cards:
            return pygame.Rect(self.x, self.y, CARD_W, CARD_H)
        return self.rect_for_index(len(self.cards)-1)
    def draw(self, screen):
        if not self.cards:
            pygame.draw.rect(
                screen,
                (255, 255, 255, 40),
                (self.x + DRAW_OFFSET_X, self.y + DRAW_OFFSET_Y, CARD_W, CARD_H),
                border_radius=CARD_RADIUS,
                width=2,
            )
        for i, c in enumerate(self.cards):
            r = self.rect_for_index(i)
            surf = get_card_surface(c)
            screen.blit(surf, (r.left + DRAW_OFFSET_X, r.top + DRAW_OFFSET_Y))
    def hit(self, pos):
        if not self.cards:
            r = pygame.Rect(self.x, self.y, CARD_W, CARD_H)
            if r.collidepoint(pos):
                return -1
            return None
        for i in reversed(range(len(self.cards))):
            r = self.rect_for_index(i)
            if r.collidepoint(pos):
                return i
        return None

# ---------- UI ----------
class Button:
    def __init__(self, text, x, y, w=280, h=48, center=False):
        self.text = text
        self.rect = pygame.Rect(0, 0, w, h)
        if center:
            self.rect.center = (x, y)
        else:
            self.rect.topleft = (x, y)

    def draw(self, screen, hover=False):
        col = GOLD if hover else (200, 200, 200)
        pygame.draw.rect(screen, col, self.rect, border_radius=12)
        pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=12)
        t = FONT_UI.render(self.text, True, BLACK)
        screen.blit(t, (self.rect.centerx - t.get_width() // 2,
                        self.rect.centery - t.get_height() // 2))

    def hovered(self, mouse_pos):
        return self.rect.collidepoint(mouse_pos)

# ---------- Base Scene ----------
class Scene:
    def __init__(self, app):
        self.app = app
        self.next_scene = None
    def handle_event(self, e): pass
    def update(self, dt): pass
    def draw(self, screen): pass
    def draw_top_bar(self, screen, title, extra=""):
        pygame.draw.rect(screen, (0,0,0,70), (0,0,SCREEN_W,60))
        t = FONT_TITLE.render(title, True, WHITE)
        screen.blit(t, (20, 10))
        if extra:
            s = FONT_UI.render(extra, True, WHITE)
            screen.blit(s, (20, 60 - s.get_height() - 6))

class UndoManager:
    """
    Store undo lambdas. After each successful move, push a function
    that will restore the prior state.
    """
    def __init__(self):
        self._stack: List[Callable[[], None]] = []

    def push(self, undo_fn: Callable[[], None]):
        self._stack.append(undo_fn)

    def can_undo(self) -> bool:
        return len(self._stack) > 0

    def undo(self):
        if self._stack:
            fn = self._stack.pop()
            fn()

"""
Note: SUITS and Card.__repr__ are defined once above.
Avoid redefining these at the bottom to prevent confusion.
"""
