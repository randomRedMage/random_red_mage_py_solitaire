import os
import json
from typing import List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help
from solitaire import mechanics as M


def _bc_dir() -> str:
    try:
        return C._settings_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _bc_save_path() -> str:
    return os.path.join(_bc_dir(), "beleaguered_castle_save.json")


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
        if os.path.isfile(_bc_save_path()):
            os.remove(_bc_save_path())
    except Exception:
        pass


class BeleagueredCastleGameScene(C.Scene):
    """Beleaguered Castle solitaire implementation."""

    def __init__(self, app, load_state: Optional[dict] = None):
        super().__init__(app)
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=max(16, int(C.CARD_H * 0.22))) for _ in range(8)]
        self.undo_mgr = C.UndoManager()
        self.anim = M.CardAnimator()
        self.drag_card: Optional[Tuple[C.Card, int]] = None
        self._drag_offset = (0, 0)
        self.message = ""
        self._auto_active = False
        self.scroll_x = 0
        self.scroll_y = 0
        self.drag_pan = M.DragPanController()
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._clamp_scroll_xy()
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._initial_snapshot = None
        self._last_click_time = 0
        self._last_click_pos = (0, 0)
        # Help modal
        self.help = create_modal_help("beleaguered_castle")
        # Edge panning while dragging (both axes)
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 60))

        self.ui_helper = ModeUIHelper(self, game_id="beleaguered_castle")

        def can_undo():
            return self.undo_mgr.can_undo()

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            auto_action={
                "on_click": self.start_autocomplete,
                "enabled": self.can_autocomplete,
                "tooltip": "Auto-finish foundations",
            },
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play", "shortcut": pygame.K_h},
            save_action=(
                "Save&Exit",
                {"on_click": lambda: self._save_game(to_menu=True), "tooltip": "Save game and return to menu"},
            ),
        )

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self._initial_snapshot = self.record_snapshot()
        else:
            self.deal_new()

    # ----- Layout -----
    def compute_layout(self):
        top_bar = getattr(C, "TOP_BAR_H", 60)
        vertical_gap = max(24, int(C.CARD_H * 0.25))
        start_y = top_bar + 80
        foundation_x = C.SCREEN_W // 2 - C.CARD_W // 2
        inner_gap = max(16, int(C.CARD_W * 0.25))
        fan = max(28, int(C.CARD_W * 0.4))
        for idx in range(4):
            y = start_y + idx * (C.CARD_H + vertical_gap)
            foundation = self.foundations[idx]
            foundation.x = foundation_x
            foundation.y = y

            left = self.tableau[idx * 2]
            right = self.tableau[idx * 2 + 1]

            left.x = foundation_x - inner_gap - C.CARD_W
            left.y = y
            left.fan_y = 0
            left.fan_x = -fan

            right.x = foundation_x + C.CARD_W + inner_gap
            right.y = y
            right.fan_y = 0
            right.fan_x = fan

        self._clamp_scroll_xy()

    def _pile_bounds(self, pile: C.Pile):
        span = max(0, len(pile.cards) - 1)
        if pile.fan_x < 0:
            left = pile.x + pile.fan_x * span
            right = pile.x + C.CARD_W
        elif pile.fan_x > 0:
            left = pile.x
            right = pile.x + C.CARD_W + pile.fan_x * span
        else:
            left = pile.x
            right = pile.x + C.CARD_W
        if pile.fan_y > 0:
            top = pile.y
            bottom = pile.y + C.CARD_H + pile.fan_y * span
        else:
            top = pile.y
            bottom = pile.y + C.CARD_H
        return left, right, top, bottom

    def _content_bounds(self):
        piles = list(self.foundations) + list(self.tableau)
        if not piles:
            return 0, C.SCREEN_W, getattr(C, "TOP_BAR_H", 60), C.SCREEN_H
        bounds = [self._pile_bounds(p) for p in piles]
        lefts, rights, tops, bottoms = zip(*bounds)
        return min(lefts), max(rights), min(tops), max(bottoms)

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
        t = (self.scroll_y - min_sy) / denom if denom != 0 else 1.0
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
        t = (self.scroll_x - min_sx) / denom if denom != 0 else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        knob_rect = pygame.Rect(knob_x, track_y, knob_w, 6)
        track_rect = pygame.Rect(track_x, track_y, track_w, 6)
        return track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w

    def _row_hit_rect(self, pile: C.Pile) -> pygame.Rect:
        span = max(0, len(pile.cards) - 1)
        if pile.fan_x < 0:
            left = pile.x + pile.fan_x * span
            right = pile.x + C.CARD_W
        elif pile.fan_x > 0:
            left = pile.x
            right = pile.x + C.CARD_W + pile.fan_x * span
        else:
            left = pile.x
            right = pile.x + C.CARD_W
        width = max(C.CARD_W, right - left)
        return pygame.Rect(int(left), int(pile.y), int(width), int(C.CARD_H))

    # ----- Deal / Restart -----
    def _clear(self):
        for f in self.foundations:
            f.cards.clear()
        for t in self.tableau:
            t.cards.clear()
        self.message = ""
        self.drag_card = None
        self.anim.cancel()
        self._auto_active = False
        self.scroll_x = 0
        self.scroll_y = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._clamp_scroll_xy()

    def deal_new(self):
        self._clear()
        deck = C.make_deck(shuffle=True)
        # Move aces to foundations by suit order
        for suit in self.foundation_suits:
            ace_idx = next((i for i, card in enumerate(deck) if card.suit == suit and card.rank == 1), None)
            if ace_idx is None:
                continue
            ace = deck.pop(ace_idx)
            ace.face_up = True
            self.foundations[self._foundation_index_for_suit(suit)].cards = [ace]
        # Deal remaining cards into eight rows of six (all face up)
        for pile in self.tableau:
            pile.cards.clear()
        for _ in range(6):
            for pile in self.tableau:
                if deck:
                    c = deck.pop()
                    c.face_up = True
                    pile.cards.append(c)
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()
        self._auto_active = False
        self.message = ""
        self._clamp_scroll_xy()
        _clear_saved_game()

    def restart(self):
        if self._initial_snapshot:
            self.restore_snapshot(self._initial_snapshot)
            self.drag_card = None
            self.anim.cancel()
            self._auto_active = False
            self.scroll_x = 0
            self.scroll_y = 0
            self._drag_vscroll = False
            self._drag_hscroll = False
            self._vscroll_geom = None
            self._hscroll_geom = None
            self._vscroll_drag_offset = 0
            self._hscroll_drag_offset = 0
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self._clamp_scroll_xy()
            self.message = ""
        self._clamp_scroll_xy()

    def _state_dict(self):
        def dump(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [dump(f) for f in self.foundations],
            "tableau": [dump(t) for t in self.tableau],
            "message": self.message,
            "completed": all(len(f.cards) == 13 for f in self.foundations),
        }

    def _save_game(self, to_menu: bool = False):
        state = self._state_dict()
        _safe_write_json(_bc_save_path(), state)
        if to_menu:
            self.ui_helper.goto_main_menu()

    def _load_from_state(self, state: dict):
        def mk(seq):
            return [C.Card(int(s), int(r), bool(f)) for (s, r, f) in seq]
        for i, f in enumerate(self.foundations):
            data = state.get("foundations", [])
            if i < len(data):
                f.cards = mk(data[i])
            else:
                f.cards = []
        for i, t in enumerate(self.tableau):
            data = state.get("tableau", [])
            if i < len(data):
                t.cards = mk(data[i])
            else:
                t.cards = []
        self.message = state.get("message", "")
        self.drag_card = None
        self.anim.cancel()
        self._auto_active = False
        self.scroll_x = 0
        self.scroll_y = 0
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None
        self._vscroll_drag_offset = 0
        self._hscroll_drag_offset = 0
        self._clamp_scroll_xy()

    def record_snapshot(self):
        def cap(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [cap(f) for f in self.foundations],
            "tableau": [cap(t) for t in self.tableau],
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, f in enumerate(self.foundations):
            f.cards = mk(snap["foundations"][i])
        for i, t in enumerate(self.tableau):
            t.cards = mk(snap["tableau"][i])
        self.message = snap.get("message", "")
        self.drag_card = None
        self.anim.cancel()

    def push_undo(self):
        snap = self.record_snapshot()
        self.undo_mgr.push(lambda s=snap: self.restore_snapshot(s))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.anim.cancel()
            self.drag_card = None
            self._auto_active = False

    # ----- Rules helpers -----
    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        target = self.foundations[fi]
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        if not target.cards:
            return card.rank == 1
        top = target.cards[-1]
        return top.suit == card.suit and card.rank == top.rank + 1

    def _can_stack_tableau(self, moving: C.Card, target_top: Optional[C.Card]) -> bool:
        if target_top is None:
            return True
        return moving.rank == target_top.rank - 1

    # ----- Auto-complete -----
    def can_autocomplete(self) -> bool:
        for t in self.tableau:
            if not t.cards:
                continue
            for i in range(len(t.cards) - 1):
                lower = t.cards[i]
                above = t.cards[i + 1]
                if above.rank != lower.rank - 1:
                    return False
        return True

    def start_autocomplete(self):
        if not self.can_autocomplete():
            return
        self._auto_active = True

    def _find_next_auto_move(self):
        top_cards = []
        for ti, t in enumerate(self.tableau):
            if t.cards:
                top_cards.append((ti, t.cards[-1]))
        for fi, suit in enumerate(self.foundation_suits):
            needed = len(self.foundations[fi].cards) + 1
            if needed > 13:
                continue
            for ti, card in top_cards:
                if card.suit == suit and card.rank == needed:
                    return ti, fi
        return None

    def _step_auto_move(self) -> bool:
        nxt = self._find_next_auto_move()
        if not nxt:
            return False
        ti, fi = nxt
        src = self.tableau[ti]
        if not src.cards:
            return False
        idx = len(src.cards) - 1
        r = src.rect_for_index(idx)
        card = src.cards.pop()
        from_xy = (r.x, r.y)
        to_xy = (self.foundations[fi].x, self.foundations[fi].y)

        def _done(ci=card, idx=fi):
            self.foundations[idx].cards.append(ci)
            self._post_move_cleanup(auto=True)

        self.anim.start_move(card, from_xy, to_xy, dur_ms=220, on_complete=_done)
        return True

    # ----- Event helpers -----
    def _maybe_handle_double_click(self, e) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - self._last_click_time <= 350
            and abs(e.pos[0] - self._last_click_pos[0]) <= 6
            and abs(e.pos[1] - self._last_click_pos[1]) <= 6
        )
        handled = False
        if double:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            for ti, t in enumerate(self.tableau):
                hi = t.hit((mxw, myw))
                if hi is None or hi == -1:
                    continue
                if hi == len(t.cards) - 1:
                    card = t.cards[-1]
                    fi = self._foundation_index_for_suit(card.suit)
                    if self._can_move_to_foundation(card, fi):
                        r = t.rect_for_index(len(t.cards) - 1)
                        self.push_undo()
                        t.cards.pop()
                        def _done(ci=card, idx=fi):
                            self.foundations[idx].cards.append(ci)
                            self._post_move_cleanup()
                        self.anim.start_move(
                            card,
                            (r.x, r.y),
                            (self.foundations[fi].x, self.foundations[fi].y),
                            dur_ms=220,
                            on_complete=_done,
                        )
                        handled = True
                        break
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    def _post_move_cleanup(self, auto: bool = False):
        if not auto:
            self._auto_active = False
        if all(len(f.cards) == 13 for f in self.foundations):
            self.message = "Congratulations! You won!"
            _clear_saved_game()
        else:
            self.message = ""

    # ----- Event handling -----
    def handle_event(self, e):
        if self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN):
                return

        if self.ui_helper.handle_menu_event(e):
            return
        if self.toolbar.handle_event(e):
            return
        if self.ui_helper.handle_shortcuts(e):
            return

        if self.anim.active:
            return

        if self.drag_pan.handle_event(e, target=self, clamp=self._clamp_scroll_xy):
            return

        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll_xy()
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    self._vscroll_drag_offset = e.pos[1] - knob_rect.y
                    return
                elif track_rect.collidepoint(e.pos):
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
                elif track_rect.collidepoint(e.pos):
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
            return
        if e.type == pygame.MOUSEMOTION and self._drag_hscroll:
            if self._hscroll_geom is not None:
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_offset, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll_xy()
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_vscroll:
            self._drag_vscroll = False
            self._vscroll_geom = None
            return
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_hscroll:
            self._drag_hscroll = False
            self._hscroll_geom = None
            return

        if e.type == pygame.KEYDOWN:
            self.ui_helper.handle_shortcuts(e)

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._maybe_handle_double_click(e):
                return
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            for ti, t in enumerate(self.tableau):
                hi = t.hit((mxw, myw))
                if hi is None:
                    continue
                if hi == len(t.cards) - 1 and t.cards:
                    r = t.rect_for_index(len(t.cards) - 1)
                    card = t.cards.pop()
                    self.drag_card = (card, ti)
                    self._drag_offset = (mx - (r.x + self.scroll_x), my - (r.y + self.scroll_y))
                    self.edge_pan.set_active(True)
                    return
            return

        if e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag_card:
            card, src_i = self.drag_card
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            placed = False
            for fi, f in enumerate(self.foundations):
                rect = pygame.Rect(f.x, f.y, C.CARD_W, C.CARD_H)
                if rect.collidepoint((mxw, myw)) and self._can_move_to_foundation(card, fi):
                    self.push_undo()
                    self.foundations[fi].cards.append(card)
                    placed = True
                    break
            if not placed:
                for ti, t in enumerate(self.tableau):
                    rect = self._row_hit_rect(t)
                    if rect.collidepoint((mxw, myw)):
                        top = t.cards[-1] if t.cards else None
                        if self._can_stack_tableau(card, top):
                            self.push_undo()
                            t.cards.append(card)
                            placed = True
                        break
            if not placed:
                self.tableau[src_i].cards.append(card)
            else:
                self._post_move_cleanup()
            self.drag_card = None
            self.edge_pan.set_active(False)
            return

        if e.type == pygame.MOUSEMOTION and self.drag_card:
            return
    def update(self, dt):
        if self._auto_active and not self.anim.active:
            if not self._step_auto_move():
                self._auto_active = False
                if all(len(f.cards) == 13 for f in self.foundations):
                    self.message = "Congratulations! You won!"
                    _clear_saved_game()

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Edge panning while dragging near edges
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        has_v = self._vertical_scrollbar() is not None
        has_h = self._horizontal_scrollbar() is not None
        dx, dy = self.edge_pan.step(has_h_scroll=has_h, has_v_scroll=has_v)
        if dx or dy:
            self.scroll_x += dx
            self.scroll_y += dy
            self._clamp_scroll_xy()

        # Apply scroll offsets for piles
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        for i, f in enumerate(self.foundations):
            f.draw(screen)
            if not f.cards:
                suit_char = C.SUITS[self.foundation_suits[i]]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                fx = f.x + self.scroll_x
                fy = f.y + self.scroll_y
                screen.blit(txt, (fx + (C.CARD_W - txt.get_width()) // 2, fy + (C.CARD_H - txt.get_height()) // 2))
        for t in self.tableau:
            t.draw(screen)

        if self.drag_card:
            card, _ = self.drag_card
            mx, my = pygame.mouse.get_pos()
            surf = C.get_card_surface(card)
            screen.blit(surf, (mx - self._drag_offset[0], my - self._drag_offset[1]))

        self.anim.draw(screen, scroll_x=self.scroll_x, scroll_y=self.scroll_y)

        # Reset offsets for UI
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0

        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 40))

        C.Scene.draw_top_bar(self, screen, "Beleaguered Castle")
        self.toolbar.draw(screen)
        if self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

        # Draw scrollbars last
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)
        hsb = self._horizontal_scrollbar()
        if hsb is not None:
            track_rect, knob_rect, *_ = hsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)
