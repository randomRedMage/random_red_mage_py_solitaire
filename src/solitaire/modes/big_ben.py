import os
import json
import math
import random
from typing import List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.ui import make_toolbar, DEFAULT_BUTTON_HEIGHT, ModalHelp
from solitaire import mechanics as M


FOUNDATION_CONFIG = [
    {"angle": 180, "suit": 3, "rank": 2, "target": 9},
    {"angle": 150, "suit": 1, "rank": 3, "target": 10},
    {"angle": 120, "suit": 0, "rank": 4, "target": 11},
    {"angle": 90,  "suit": 2, "rank": 5, "target": 12},
    {"angle": 60,  "suit": 3, "rank": 6, "target": 1},
    {"angle": 30,  "suit": 1, "rank": 7, "target": 2},
    {"angle": 0,   "suit": 0, "rank": 8, "target": 3},
    {"angle": -30, "suit": 2, "rank": 9, "target": 4},
    {"angle": -60, "suit": 3, "rank": 10, "target": 5},
    {"angle": -90, "suit": 1, "rank": 11, "target": 6},
    {"angle": -120,"suit": 0, "rank": 12, "target": 7},
    {"angle": -150,"suit": 2, "rank": 13, "target": 8},
]

REFILL_SEQUENCE = list(range(3, 12)) + list(range(0, 3))


def _bb_dir() -> str:
    try:
        return C._settings_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _bb_save_path() -> str:
    return os.path.join(_bb_dir(), "big_ben_save.json")


def _safe_write_json(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clear_saved_game():
    try:
        if os.path.isfile(_bb_save_path()):
            os.remove(_bb_save_path())
    except Exception:
        pass


def _next_rank(rank: int) -> int:
    return 1 if rank == 13 else rank + 1


def _prev_rank(rank: int) -> int:
    return 13 if rank == 1 else rank - 1


class BigBenOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 220
        y = 260
        self.b_start = C.Button("Start Big Ben", cx, y, w=440)
        y += 60
        self.b_resume = C.Button("Continue Saved Game", cx, y, w=440)
        y += 60
        y += 10
        self.b_back = C.Button("Back", cx, y, w=440)

    def _has_save(self) -> bool:
        state = _safe_read_json(_bb_save_path())
        return bool(state) and not state.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                _clear_saved_game()
                self.next_scene = BigBenGameScene(self.app, load_state=None)
            elif self.b_resume.hovered((mx, my)) and self._has_save():
                state = _safe_read_json(_bb_save_path())
                if state:
                    self.next_scene = BigBenGameScene(self.app, load_state=state)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Big Ben - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 130))
        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        resume_label = self.b_resume.text
        if not has_save:
            self.b_resume.text = "Continue Saved Game (None)"
        for btn in (self.b_start, self.b_resume, self.b_back):
            btn.draw(screen, hover=btn.hovered(mp))
        self.b_resume.text = resume_label


class BigBenGameScene(C.Scene):
    MAX_FAN_CARDS = 3

    def __init__(self, app, load_state: Optional[dict] = None):
        super().__init__(app)
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in FOUNDATION_CONFIG]
        self.tableau: List[C.Pile] = [C.Pile(0, 0) for _ in FOUNDATION_CONFIG]
        self.stock: C.Pile = C.Pile(0, 0)
        self.waste: C.Pile = C.Pile(0, 0)

        self.foundation_suits = [cfg["suit"] for cfg in FOUNDATION_CONFIG]
        self.foundation_targets = [cfg["target"] for cfg in FOUNDATION_CONFIG]

        self.undo_mgr = C.UndoManager()
        self.message = ""
        self.completed = False
        self._game_over = False

        self.drag_card: Optional[C.Card] = None
        self.drag_from: Optional[Tuple[str, int]] = None
        self.drag_offset: Tuple[int, int] = (0, 0)
        self.drag_pos: Tuple[int, int] = (0, 0)
        self._drag_snapshot = None

        self._initial_snapshot = None
        self._center = (0, 0)
        self.scroll_x = 0
        self.scroll_y = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._card_diag = int(math.ceil(math.hypot(C.CARD_W, C.CARD_H)))

        def goto_menu():
            from solitaire.modes.big_ben import BigBenOptionsScene
            self.next_scene = BigBenOptionsScene(self.app)

        def do_new():
            self.deal_new()

        def do_restart():
            self.restart()

        def do_undo():
            self.undo()

        def can_undo():
            return self.undo_mgr.can_undo()

        actions = {
            "Menu": {"on_click": goto_menu, "tooltip": "Return to Big Ben menu"},
            "New": {"on_click": do_new},
            "Restart": {"on_click": do_restart, "tooltip": "Restart current deal"},
            "Undo": {"on_click": do_undo, "enabled": can_undo, "tooltip": "Undo last move"},
            "Help": {"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            "Save&Exit": {"on_click": lambda: self._save_game(to_main=True), "tooltip": "Save game and return to main menu"},
        }
        self.toolbar = make_toolbar(
            actions,
            height=DEFAULT_BUTTON_HEIGHT,
            margin=(10, 8),
            gap=8,
            align="right",
            width_provider=lambda: C.SCREEN_W,
        )

        self.help = ModalHelp(
            "Big Ben - How to Play",
            [
                "Goal: Build each foundation to its clock value using cards of the same suit.",
                "Setup: One copy of the highlighted cards forms the twelve foundations arranged like a clock (starting at the 9 o'clock position).",
                "Tableau: Each foundation has an outward fan of up to three face-up cards. The outermost card of a fan is the only card that may move.",
                "Tableau moves: Move a fan's top card onto another fan when it is exactly one rank lower (wrapping K->A) and the same suit.",
                "Foundations: Build upward by suit from the starting card, wrapping K->A, until the foundation's clock rank is on top. Waste cards may also be played here.",
                "Stock: Click the stock to refill every fan with fewer than three cards (starting at 12 o'clock clockwise). If no fan needs cards, the click moves the top stock card to the waste face-up.",
                "Waste: Its top card can only be played to foundations. It never refills tableau fans.",
                "End: Win when all foundations reach their clock rank. Lose when the stock is empty and there are no legal moves left.",
                "Toolbar: Menu (return to Big Ben menu), New deal, Restart, Undo, Help, Save&Exit.",
            ],
            max_width=880,
        )
        self.peek = M.PeekController(delay_ms=500)

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
            self.undo_mgr = C.UndoManager()
            self._initial_snapshot = self.record_snapshot()
        else:
            self.deal_new()


    def _pile_bounds(self, pile: C.Pile, max_len: int) -> Tuple[float, float, float, float]:
            diag = self._card_diag
            half = diag / 2.0
            count = max(len(pile.cards), max_len)
            if count <= 0:
                count = 1
            xs: List[float] = []
            ys: List[float] = []
            for idx in range(count):
                r = pile.rect_for_index(idx)
                cx = r.x + C.CARD_W / 2
                cy = r.y + C.CARD_H / 2
                xs.extend([cx - half, cx + half])
                ys.extend([cy - half, cy + half])
            return min(xs), max(xs), min(ys), max(ys)

    def _content_bounds(self) -> Tuple[float, float, float, float]:
        entries: List[Tuple[float, float, float, float]] = []
        for pile in self.foundations:
            entries.append(self._pile_bounds(pile, 1))
        for pile in self.tableau:
            entries.append(self._pile_bounds(pile, self.MAX_FAN_CARDS))
        for pile in (self.stock, self.waste):
            entries.append(self._pile_bounds(pile, 1))
        if not entries:
            top_bar = getattr(C, "TOP_BAR_H", 60)
            return 0, C.SCREEN_W, top_bar, C.SCREEN_H
        lefts, rights, tops, bottoms = zip(*entries)
        pad = 18
        return min(lefts) - pad, max(rights) + pad, min(tops) - pad, max(bottoms) + pad

    def _scroll_limits(self):
        left, right, top, bottom = self._content_bounds()
        margin = 20
        top_bar = getattr(C, "TOP_BAR_H", 60)
        max_sx = margin - left
        min_sx = min(0, C.SCREEN_W - right - margin)
        max_sy = top_bar + margin - top
        min_sy = min(0, C.SCREEN_H - bottom - margin)
        return min_sx, max_sx, min_sy, max_sy

    def _clamp_scroll_xy(self):
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sx < min_sx:
            max_sx = min_sx
        if max_sy < min_sy:
            max_sy = min_sy
        self.scroll_x = max(min(self.scroll_x, max_sx), min_sx)
        self.scroll_y = max(min(self.scroll_y, max_sy), min_sy)

    def _vertical_scrollbar(self):
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sy <= min_sy:
            return None
        track_x = C.SCREEN_W - 12
        track_y = getattr(C, "TOP_BAR_H", 60)
        track_h = C.SCREEN_H - track_y - 10
        if track_h <= 0:
            return None
        view_h = track_h
        content_h = view_h + (max_sy - min_sy)
        knob_h = max(30, int(track_h * (view_h / max(1, content_h))))
        denom = max_sy - min_sy
        t = (self.scroll_y - min_sy) / denom if denom else 1.0
        knob_y = int(track_y + (track_h - knob_h) * (1.0 - t))
        knob_rect = pygame.Rect(track_x, knob_y, 6, knob_h)
        track_rect = pygame.Rect(track_x, track_y, 6, track_h)
        return track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h

    def _horizontal_scrollbar(self):
        min_sx, max_sx, min_sy, max_sy = self._scroll_limits()
        if max_sx <= min_sx:
            return None
        track_x = 10
        track_w = C.SCREEN_W - 20
        track_y = C.SCREEN_H - 12
        if track_w <= 0:
            return None
        view_w = track_w
        content_w = view_w + (max_sx - min_sx)
        knob_w = max(30, int(track_w * (view_w / max(1, content_w))))
        denom = max_sx - min_sx
        t = (self.scroll_x - min_sx) / denom if denom else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        knob_rect = pygame.Rect(knob_x, track_y, knob_w, 6)
        track_rect = pygame.Rect(track_x, track_y, track_w, 6)
        return track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w


    def compute_layout(self):
        top_bar = getattr(C, "TOP_BAR_H", 60)
        available_h = max(200, C.SCREEN_H - top_bar - 40)
        center_x = C.SCREEN_W // 2
        center_y = top_bar + available_h // 2
        self._center = (center_x, center_y)
        self._card_diag = int(math.ceil(math.hypot(C.CARD_W, C.CARD_H)))

        screen_margin = max(120, int(max(C.CARD_W, C.CARD_H) * 0.8))
        max_radius = min(center_x - screen_margin, available_h // 2 - screen_margin)
        if max_radius <= 0:
            max_radius = min(center_x, available_h // 2) - max(20, screen_margin // 2)
        max_radius = max(max_radius, int(C.CARD_H * 2.6))

        angle_step = math.radians(30)
        #[debug] (C.CARD_W + 18) to (C.CARD_W + 25)
        min_spacing_radius = (C.CARD_W + 25) / (2.0 * math.sin(angle_step / 2.0))
        stock_gap = max(24, int(C.CARD_W * 0.25))
        min_stock_radius = C.CARD_W + stock_gap + 32
        base_min_radius = max(int(math.ceil(min_spacing_radius)), int(min_stock_radius), int(C.CARD_H * 1.4))

        fan_step = max(10, int(C.CARD_H * 0.2))
        #[debug] max(28, int(C.CARD_H * 0.2)) to max(20, int(C.CARD_H * 0.2))
        radial_pad = self._card_diag + max(28, int(C.CARD_H * 0.2))

        outer_buffer = radial_pad + (self.MAX_FAN_CARDS - 1) * fan_step + C.CARD_H // 2
        foundation_radius = max(base_min_radius, max_radius - outer_buffer)
        if foundation_radius < base_min_radius and self.MAX_FAN_CARDS > 1:
            deficit = base_min_radius - foundation_radius
            reduce = min(fan_step - 8, int(math.ceil(deficit / max(1, self.MAX_FAN_CARDS - 1))))
            if reduce > 0:
                fan_step -= reduce
            foundation_radius = base_min_radius
        fan_inner_radius = foundation_radius + radial_pad
        outer_radius = fan_inner_radius + (self.MAX_FAN_CARDS - 1) * fan_step + C.CARD_H // 2
        if outer_radius > max_radius and self.MAX_FAN_CARDS > 1:
            overflow = outer_radius - max_radius
            reduce = min(fan_step - 40, int(math.ceil(overflow / max(1, self.MAX_FAN_CARDS - 1))))
            if reduce > 0:
                fan_step -= reduce                
                fan_inner_radius = foundation_radius + radial_pad
                outer_radius = fan_inner_radius + (self.MAX_FAN_CARDS - 1) * fan_step + C.CARD_H // 2
        if outer_radius > max_radius:
            foundation_radius = max(
                base_min_radius,
                max_radius - ((self.MAX_FAN_CARDS - 1) * fan_step + C.CARD_H // 2 + radial_pad),
            )
            fan_inner_radius = foundation_radius + radial_pad

        for idx, cfg in enumerate(FOUNDATION_CONFIG):
            rad = math.radians(cfg["angle"])
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            fx = center_x + int(round(cos_a * foundation_radius)) - C.CARD_W // 2
            fy = center_y - int(round(sin_a * foundation_radius)) - C.CARD_H // 2
            self.foundations[idx].x = fx
            self.foundations[idx].y = fy

            base_x = center_x + int(round(cos_a * fan_inner_radius)) - C.CARD_W // 2
            base_y = center_y - int(round(sin_a * fan_inner_radius)) - C.CARD_H // 2
            self.tableau[idx].x = base_x
            self.tableau[idx].y = base_y
            self.tableau[idx].fan_x = int(round(cos_a * fan_step))
            self.tableau[idx].fan_y = -int(round(sin_a * fan_step))

        self.stock.x = center_x - C.CARD_W - stock_gap // 2
        self.stock.y = center_y - C.CARD_H // 2
        self.waste.x = center_x + stock_gap // 2
        self.waste.y = center_y - C.CARD_H // 2

        self._clamp_scroll_xy()
        self._vscroll_geom = None
        self._hscroll_geom = None
        self.peek.cancel()


    def _clear(self):
        for pile in self.foundations + self.tableau:
            pile.cards.clear()
        self.stock.cards.clear()
        self.waste.cards.clear()
        self.message = ""
        self.completed = False
        self._game_over = False
        self.drag_card = None
        self.drag_from = None
        self._drag_snapshot = None
        self.scroll_x = 0
        self.scroll_y = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._clamp_scroll_xy()
        self.peek.cancel()

    def deal_new(self):
        self._clear()
        deck: List[C.Card] = C.make_deck(shuffle=False) + C.make_deck(shuffle=False)

        for idx, cfg in enumerate(FOUNDATION_CONFIG):
            suit = cfg["suit"]
            rank = cfg["rank"]
            card_index = next((i for i, c in enumerate(deck) if c.suit == suit and c.rank == rank), None)
            if card_index is None:
                continue
            card = deck.pop(card_index)
            card.face_up = True
            self.foundations[idx].cards = [card]

        random.shuffle(deck)

        for _ in range(self.MAX_FAN_CARDS):
            for pile in self.tableau:
                if deck:
                    card = deck.pop()
                    card.face_up = True
                    pile.cards.append(card)

        self.stock.cards = deck
        self.waste.cards.clear()
        self.undo_mgr = C.UndoManager()
        self._initial_snapshot = self.record_snapshot()
        self.push_undo(self._initial_snapshot)
        self.message = ""
        self.completed = False
        self._game_over = False
        self._clamp_scroll_xy()
        self.peek.cancel()
        _clear_saved_game()

    def restart(self):
        if self._initial_snapshot:
            self.restore_snapshot(self._initial_snapshot)
            self.undo_mgr = C.UndoManager()
            self.message = ""
            self.completed = False
            self._game_over = False
            self.scroll_x = 0
            self.scroll_y = 0
            self._clamp_scroll_xy()
            self.peek.cancel()

    def record_snapshot(self):
        def capture(pile: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in pile.cards]

        return {
            "foundations": [capture(p) for p in self.foundations],
            "tableau": [capture(p) for p in self.tableau],
            "stock": capture(self.stock),
            "waste": capture(self.waste),
            "message": self.message,
            "completed": self.completed,
            "game_over": self._game_over,
        }

    def restore_snapshot(self, snap):
        def rebuild(seq):
            return [C.Card(int(s), int(r), bool(f)) for (s, r, f) in seq]

        for idx, pile in enumerate(self.foundations):
            data = snap.get("foundations", [])
            pile.cards = rebuild(data[idx]) if idx < len(data) else []
        for idx, pile in enumerate(self.tableau):
            data = snap.get("tableau", [])
            pile.cards = rebuild(data[idx]) if idx < len(data) else []
        self.stock.cards = rebuild(snap.get("stock", []))
        self.waste.cards = rebuild(snap.get("waste", []))
        self.message = snap.get("message", "")
        self.completed = bool(snap.get("completed", False))
        self._game_over = bool(snap.get("game_over", False))
        self.drag_card = None
        self.drag_from = None
        self._drag_snapshot = None
        self.scroll_x = 0
        self.scroll_y = 0
        self._clamp_scroll_xy()
        self.peek.cancel()

    def push_undo(self, snapshot=None):
        snap = snapshot if snapshot is not None else self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.drag_card = None
            self.drag_from = None
            self._drag_snapshot = None
            self._clamp_scroll_xy()
            self.peek.cancel()

    def _state_dict(self):
        state = self.record_snapshot()
        state.update({"targets": self.foundation_targets})
        return state

    def _save_game(self, to_main: bool = False):
        state = self._state_dict()
        _safe_write_json(_bb_save_path(), state)
        if to_main:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def _load_from_state(self, state: dict):
        self.restore_snapshot(state)
        self._clamp_scroll_xy()
        self.peek.cancel()

    def _foundation_complete(self, idx: int) -> bool:
        pile = self.foundations[idx]
        if not pile.cards:
            return False
        return pile.cards[-1].rank == self.foundation_targets[idx]

    def _can_place_on_foundation(self, card: C.Card, idx: int) -> bool:
        if self._foundation_complete(idx):
            return False
        if card.suit != self.foundation_suits[idx]:
            return False
        pile = self.foundations[idx]
        top = pile.cards[-1] if pile.cards else None
        if top is None:
            return False
        expected = _next_rank(top.rank)
        return card.rank == expected

    def _can_place_on_fan(self, card: C.Card, idx: int, from_source: str) -> bool:
        if from_source == "waste":
            return False
        pile = self.tableau[idx]
        if not pile.cards:
            return True
        top = pile.cards[-1]
        expected = _prev_rank(top.rank)
        return card.suit == top.suit and card.rank == expected

    def _has_any_moves(self) -> bool:
        if self.completed:
            return False
        if self.stock.cards:
            return True
        for ti, pile in enumerate(self.tableau):
            if not pile.cards:
                if any(p.cards for j, p in enumerate(self.tableau) if j != ti):
                    return True
                continue
            card = pile.cards[-1]
            for dj, other in enumerate(self.tableau):
                if dj == ti or not other.cards:
                    continue
                top = other.cards[-1]
                if card.suit == top.suit and card.rank == _prev_rank(top.rank):
                    return True
            for fi in range(len(self.foundations)):
                if self._can_place_on_foundation(card, fi):
                    return True
        if self.waste.cards:
            card = self.waste.cards[-1]
            for fi in range(len(self.foundations)):
                if self._can_place_on_foundation(card, fi):
                    return True
        return False

    def _check_completion(self):
        if all(self._foundation_complete(i) for i in range(len(self.foundations))):
            self.completed = True
            self._game_over = True
            self.message = "Big Ben complete!"
            _clear_saved_game()
            return
        self.completed = False
        if not self.stock.cards and not self._has_any_moves():
            self._game_over = True
            self.message = "No moves left."
        else:
            self._game_over = False
            self.message = ""

    def _finish_drag(self, valid_drop: bool):
        if not valid_drop and self._drag_snapshot is not None:
            self.restore_snapshot(self._drag_snapshot)
        elif valid_drop and self._drag_snapshot is not None:
            self.push_undo(self._drag_snapshot)
            self._check_completion()
        self.drag_card = None
        self.drag_from = None
        self._drag_snapshot = None
        self._clamp_scroll_xy()
        self.peek.cancel()

    def _refill_from_stock(self):
        changed = False
        if not self.stock.cards:
            return False
        for idx in REFILL_SEQUENCE:
            pile = self.tableau[idx]
            while len(pile.cards) < self.MAX_FAN_CARDS and self.stock.cards:
                card = self.stock.cards.pop()
                card.face_up = True
                pile.cards.append(card)
                changed = True
        return changed

    def _move_stock_to_waste(self):
        if not self.stock.cards:
            return False
        card = self.stock.cards.pop()
        card.face_up = True
        self.waste.cards.append(card)
        return True

    def _angle_to_center(self, cx: int, cy: int) -> float:
        dx = self._center[0] - cx
        dy = self._center[1] - cy
        return math.degrees(math.atan2(-dy, dx))

    def _rotation_angle(self, cx: int, cy: int) -> float:
        return self._angle_to_center(cx, cy) - 90.0

    def _blit_card_rotated(self, screen: pygame.Surface, card: C.Card, center: Tuple[int, int]):
        angle = self._rotation_angle(*center)
        surf = C.get_card_surface(card)
        rotated = pygame.transform.rotate(surf, angle)
        screen_center = (int(round(center[0] + self.scroll_x)), int(round(center[1] + self.scroll_y)))
        rect = rotated.get_rect(center=screen_center)
        screen.blit(rotated, rect)

    def _draw_empty_slot(self, screen: pygame.Surface, pile: C.Pile):
        rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
        cx, cy = rect.center
        placeholder = pygame.Surface((C.CARD_W, C.CARD_H), pygame.SRCALPHA)
        pygame.draw.rect(placeholder, (255, 255, 255, 40), placeholder.get_rect(), border_radius=C.CARD_RADIUS)
        pygame.draw.rect(placeholder, (180, 180, 190, 200), placeholder.get_rect(), width=2, border_radius=C.CARD_RADIUS)
        angle = self._rotation_angle(cx, cy)
        rotated = pygame.transform.rotate(placeholder, angle)
        screen_center = (int(round(cx + self.scroll_x)), int(round(cy + self.scroll_y)))
        screen.blit(rotated, rotated.get_rect(center=screen_center))

    def _draw_rotated_pile(self, screen: pygame.Surface, pile: C.Pile):
        if not pile.cards:
            self._draw_empty_slot(screen, pile)
            return
        for idx, card in enumerate(pile.cards):
            rect = pile.rect_for_index(idx)
            cx = rect.x + C.CARD_W // 2
            cy = rect.y + C.CARD_H // 2
            self._blit_card_rotated(screen, card, (cx, cy))

    def handle_event(self, e):
        if self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN):
                return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.peek.cancel()
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    self._vscroll_drag_offset = e.pos[1] - knob_rect.y
                    return
                if track_rect.collidepoint(e.pos):
                    y = min(max(e.pos[1] - knob_h // 2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                    self._clamp_scroll_xy()
                    return
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_hscroll = True
                    self._hscroll_geom = (min_sx, max_sx, track_x, track_w, knob_w)
                    self._hscroll_drag_offset = e.pos[0] - knob_rect.x
                    return
                if track_rect.collidepoint(e.pos):
                    x = min(max(e.pos[0] - knob_w // 2, track_x), track_x + track_w - knob_w)
                    t_knob = (x - track_x) / max(1, (track_w - knob_w))
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll_xy()
                    return

        if e.type == pygame.MOUSEMOTION and self._drag_vscroll:
            if self._vscroll_geom is not None:
                min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
                y = min(max(e.pos[1] - self._vscroll_drag_offset, track_y), track_y + track_h - knob_h)
                t_knob = (y - track_y) / max(1, (track_h - knob_h))
                self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                self._clamp_scroll_xy()
            self.peek.cancel()
            return
        if e.type == pygame.MOUSEMOTION and self._drag_hscroll:
            if self._hscroll_geom is not None:
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_offset, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll_xy()
            self.peek.cancel()
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_vscroll:
            self._drag_vscroll = False
            self._vscroll_geom = None
            self.peek.cancel()
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_hscroll:
            self._drag_hscroll = False
            self._hscroll_geom = None
            self.peek.cancel()
            return

        if self.toolbar.handle_event(e):
            self.peek.cancel()
            return

        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll_xy()
            self.peek.cancel()
            return

        if e.type == pygame.KEYDOWN:
            self.peek.cancel()
            if e.key == pygame.K_ESCAPE:
                from solitaire.modes.big_ben import BigBenOptionsScene
                self.next_scene = BigBenOptionsScene(self.app)
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            self.peek.cancel()
            self._on_left_down(e.pos)
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._on_left_up(e.pos)
        elif e.type == pygame.MOUSEMOTION and self.drag_card is not None:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            self.drag_pos = (mxw - self.drag_offset[0], myw - self.drag_offset[1])
            self.peek.cancel()
        elif e.type == pygame.MOUSEMOTION:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            self.peek.on_motion_over_piles(self.tableau, (mxw, myw))

    def _on_left_down(self, pos):
        if self._game_over and not self.undo_mgr.can_undo():
            return
        self.peek.cancel()
        mx, my = pos
        mxw = mx - self.scroll_x
        myw = my - self.scroll_y
        stock_rect = pygame.Rect(self.stock.x, self.stock.y, C.CARD_W, C.CARD_H)
        if stock_rect.collidepoint((mxw, myw)):
            if self._game_over and not self.stock.cards:
                return
            snapshot = self.record_snapshot()
            changed = False
            if any(len(p.cards) < self.MAX_FAN_CARDS for p in self.tableau):
                changed = self._refill_from_stock()
            else:
                changed = self._move_stock_to_waste()
            if changed:
                self.push_undo(snapshot)
                self._check_completion()
            return
        if self.drag_card is not None:
            return
        for idx, pile in enumerate(self.tableau):
            if not pile.cards:
                continue
            rect = pile.rect_for_index(len(pile.cards) - 1)
            if rect.collidepoint((mxw, myw)):
                self._drag_snapshot = self.record_snapshot()
                self.drag_card = pile.cards.pop()
                self.drag_from = ("tableau", idx)
                self.drag_offset = (mxw - rect.x, myw - rect.y)
                self.drag_pos = (rect.x, rect.y)
                return
        if self.waste.cards:
            rect = pygame.Rect(self.waste.x, self.waste.y, C.CARD_W, C.CARD_H)
            if rect.collidepoint((mxw, myw)):
                self._drag_snapshot = self.record_snapshot()
                self.drag_card = self.waste.cards.pop()
                self.drag_from = ("waste", 0)
                self.drag_offset = (mxw - rect.x, myw - rect.y)
                self.drag_pos = (rect.x, rect.y)

    def _on_left_up(self, pos):
        if self.drag_card is None:
            return
        self.peek.cancel()
        mx, my = pos
        mxw = mx - self.scroll_x
        myw = my - self.scroll_y
        card = self.drag_card
        placed = False
        for idx, pile in enumerate(self.foundations):
            rect = pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
            if rect.collidepoint((mxw, myw)) and self._can_place_on_foundation(card, idx):
                pile.cards.append(card)
                placed = True
                break
        if not placed:
            source_kind = self.drag_from[0] if self.drag_from else ""
            for idx, pile in enumerate(self.tableau):
                rect = pile.rect_for_index(len(pile.cards) - 1) if pile.cards else pygame.Rect(pile.x, pile.y, C.CARD_W, C.CARD_H)
                if rect.collidepoint((mxw, myw)) and self._can_place_on_fan(card, idx, source_kind):
                    pile.cards.append(card)
                    placed = True
                    break
        if not placed and self.drag_from:
            kind, idx = self.drag_from
            if kind == "tableau":
                self.tableau[idx].cards.append(card)
            elif kind == "waste":
                self.waste.cards.append(card)
        self._finish_drag(placed)

    def update(self, dt):
        pass

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
               
        center_screen = (int(round(self._center[0] + self.scroll_x)), int(round(self._center[1] + self.scroll_y)))
        pygame.draw.circle(screen, (10, 80, 36), center_screen, 6)

        for pile in self.tableau:
            self._draw_rotated_pile(screen, pile)
        for pile in self.foundations:
            self._draw_rotated_pile(screen, pile)

        prev_dx, prev_dy = C.DRAW_OFFSET_X, C.DRAW_OFFSET_Y
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y
        self.stock.draw(screen)
        self.waste.draw(screen)
        C.DRAW_OFFSET_X = prev_dx
        C.DRAW_OFFSET_Y = prev_dy

        self.peek.maybe_activate(pygame.time.get_ticks())
        if self.peek.overlay and self.drag_card is None:
            card, ox, oy = self.peek.overlay
            center = (ox + C.CARD_W // 2, oy + C.CARD_H // 2)
            self._blit_card_rotated(screen, card, center)

        if self.drag_card is not None:
            card = self.drag_card
            if self.drag_from and self.drag_from[0] == "tableau":
                world_center = (self.drag_pos[0] + C.CARD_W // 2, self.drag_pos[1] + C.CARD_H // 2)
                self._blit_card_rotated(screen, card, world_center)
            else:
                screen.blit(
                    C.get_card_surface(card),
                    (int(round(self.drag_pos[0] + self.scroll_x)), int(round(self.drag_pos[1] + self.scroll_y))),
                )

        if self.message:
            font = C.FONT_UI if C.FONT_UI is not None else pygame.font.SysFont(pygame.font.get_default_font(), 26, bold=True)
            text_surf = font.render(self.message, True, C.WHITE)
            screen.blit(text_surf, (C.SCREEN_W // 2 - text_surf.get_width() // 2, getattr(C, "TOP_BAR_H", 60) + 16))

        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (60, 60, 70), track_rect, border_radius=3)
            pygame.draw.rect(screen, (220, 220, 230), knob_rect, border_radius=3)

        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (60, 60, 70), track_rect, border_radius=3)
            pygame.draw.rect(screen, (220, 220, 230), knob_rect, border_radius=3)

         # Draw top bar and toolbar last so content scrolls behind
        C.Scene.draw_top_bar(self, screen, "Big Ben")
        self.toolbar.draw(screen)
        # Help overlay on top
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
        
    def debug_state(self):
        return {
            "foundations": len(self.foundations),
            "tableau": len(self.tableau),
            "stock_count": len(self.stock.cards),
            "waste_count": len(self.waste.cards),
            "completed": self.completed,
        }