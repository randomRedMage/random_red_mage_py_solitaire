import os
import json
from typing import List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help
from solitaire import mechanics as M


def is_red(suit: int) -> bool:
    return suit in (1, 2)


def _yukon_dir() -> str:
    try:
        return C._settings_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".random_red_mage_solitaire")


def _yukon_save_path() -> str:
    return os.path.join(_yukon_dir(), "yukon_save.json")


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


class YukonOptionsScene(C.Scene):
    def __init__(self, app):
        super().__init__(app)
        cx = C.SCREEN_W // 2 - 220
        y = 260
        self.b_start = C.Button("Start Yukon", cx, y, w=440); y += 60
        self.b_continue = C.Button("Continue Saved Game", cx, y, w=440); y += 60
        y += 10
        self.b_back = C.Button("Back", cx, y, w=440)

    def _has_save(self) -> bool:
        s = _safe_read_json(_yukon_save_path())
        return bool(s) and not s.get("completed", False)

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if self.b_start.hovered((mx, my)):
                # Starting a new game clears any previous save
                try:
                    if os.path.isfile(_yukon_save_path()):
                        os.remove(_yukon_save_path())
                except Exception:
                    pass
                self.next_scene = YukonGameScene(self.app, load_state=None)
            elif self.b_continue.hovered((mx, my)) and self._has_save():
                state = _safe_read_json(_yukon_save_path())
                self.next_scene = YukonGameScene(self.app, load_state=state)
            elif self.b_back.hovered((mx, my)):
                from solitaire.scenes.menu import MainMenuScene
                self.next_scene = MainMenuScene(self.app)
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            from solitaire.scenes.menu import MainMenuScene
            self.next_scene = MainMenuScene(self.app)

    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        title = C.FONT_TITLE.render("Yukon - Options", True, C.WHITE)
        screen.blit(title, (C.SCREEN_W // 2 - title.get_width() // 2, 130))
        mp = pygame.mouse.get_pos()
        has_save = self._has_save()
        # Show disabled hint in label if no save present
        if not has_save:
            old = self.b_continue.text
            self.b_continue.text = "Continue Saved Game (None)"
        for b in [self.b_start, self.b_continue, self.b_back]:
            b.draw(screen, hover=b.hovered(mp))
        if not has_save:
            self.b_continue.text = old


class YukonGameScene(C.Scene):
    """
    Yukon Solitaire
    - 4 foundations (single column on the right), build up A->K by suit.
    - 7 tableau piles to the left with counts: 1, 6, 7, 8, 9, 10, 11. In each, the top 5 are face-up (or the only card).
    - No stock/waste. Move any face-up substack to another tableau if the bottom card is rank-1 and opposite color of target.
      Only Kings may be placed in empty tableaus.
    - Auto-move exposed Aces to foundations. Double-click top card to move to foundation if legal.
    - Auto-complete available once all tableau cards are face-up.
    """

    def __init__(self, app, load_state: Optional[dict] = None):
        super().__init__(app)
        # Piles
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
        self.tableau: List[C.Pile] = [C.Pile(0, 0, fan_y=max(18, int(C.CARD_H * 0.28))) for _ in range(7)]

        # Drag state: (cards, src_index)
        self.drag_stack: Optional[Tuple[List[C.Card], int]] = None
        self.undo_mgr = C.UndoManager()
        self.message = ""

        # Shared animator for card moves
        self.anim: M.CardAnimator = M.CardAnimator()

        # Scrolling (both axes)
        self.scroll_x = 0
        self.scroll_y = 0
        self.drag_pan = M.DragPanController()
        self._drag_vscroll = False
        self._drag_hscroll = False
        self._vscroll_geom = None
        self._hscroll_geom = None

        # Toolbar
        self.ui_helper = ModeUIHelper(self, game_id="yukon")

        def can_undo():
            return self.undo_mgr.can_undo()

        def save_and_exit():
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            auto_action={
                "on_click": self.start_autocomplete,
                "enabled": self.can_autocomplete,
                "tooltip": "Auto-finish to foundations",
            },
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
            save_action=("Save&Exit", {"on_click": save_and_exit, "tooltip": "Save game and exit to menu"}),
        )

        self.compute_layout()

        if load_state:
            self._load_from_state(load_state)
            # New undo baseline
            self.undo_mgr = C.UndoManager()
            self.push_undo()
            self._initial_snapshot = self.record_snapshot()
        else:
            self.deal_new()

        # Help overlay
        self.help = create_modal_help("yukon")

        # Double-click tracking
        self._last_click_time = 0
        self._last_click_pos = (0, 0)
        # Auto-complete flag
        self._auto_active = False
        # Klondike-style peek
        self.peek = M.PeekController(delay_ms=2000)
        # Edge panning during drags (both axes)
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 64))

    # ----- Layout -----
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))
        top_bar_h = getattr(C, "TOP_BAR_H", 64)
        top_y = max(80, top_bar_h + 26)

        # Compute a centered layout block consisting of 7 tableau columns,
        # a comfortable gap, and the single foundations column on the right.
        tableau_cols = 7
        tableau_block_w = tableau_cols * C.CARD_W + (tableau_cols - 1) * gap_x
        gap_tf = max(gap_x * 2, int(C.CARD_W * 0.6))
        total_block_w = tableau_block_w + gap_tf + C.CARD_W
        left_edge = max(10, (C.SCREEN_W - total_block_w) // 2)

        # Foundations: single column on the right side of the centered block
        foundation_x = left_edge + tableau_block_w + gap_tf
        for i, f in enumerate(self.foundations):
            f.x = foundation_x
            f.y = top_y + i * (C.CARD_H + gap_y)

        # Tableau: centered block to the left of foundations
        tab_left = left_edge
        fan_y = max(18, int(C.CARD_H * 0.28))
        row_y = top_y
        for i, t in enumerate(self.tableau):
            t.x = tab_left + i * (C.CARD_W + gap_x)
            t.y = row_y
            t.fan_y = fan_y

    # ----- Deal / Restart -----
    def _clear(self):
        for p in self.tableau:
            p.cards.clear()
        for p in self.foundations:
            p.cards.clear()
        self.drag_stack = None
        self.anim.cancel()
        self.message = ""

    def deal_new(self):
        self._clear()
        deck = C.make_deck(shuffle=True)
        # Layout counts per column: 1, 6, 7, 8, 9, 10, 11 (total 52)
        counts = [1, 6, 7, 8, 9, 10, 11]
        for col, count in enumerate(counts):
            pile = []
            for i in range(count):
                c = deck.pop()
                pile.append(c)
            # Top 5 face up (or the only card in first column)
            face_up_n = 5 if count > 1 else 1
            face_up_n = min(face_up_n, count)
            for i, c in enumerate(pile):
                # Bottom of pile is index 0; top is last
                c.face_up = (i >= count - face_up_n)
            self.tableau[col].cards = pile

        # Reset undo and baseline snapshot
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self._initial_snapshot = self.record_snapshot()
        self._auto_active = False

    def restart(self):
        if getattr(self, "_initial_snapshot", None):
            self.restore_snapshot(self._initial_snapshot)
            self.drag_stack = None
            self.anim.cancel()
            self.message = ""
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    # ----- Saving -----
    def _save_game(self, to_menu: bool = False):
        state = self._state_dict()
        _safe_write_json(_yukon_save_path(), state)
        if to_menu:
            from solitaire.scenes.game_options.yukon_options import YukonOptionsScene
            self.next_scene = YukonOptionsScene(self.app)

    def _state_dict(self):
        def cap_pile(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [cap_pile(f) for f in self.foundations],
            "tableau": [cap_pile(t) for t in self.tableau],
            "completed": all(len(f.cards) == 13 for f in self.foundations),
        }

    def _load_from_state(self, state: dict):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, f in enumerate(self.foundations):
            f.cards = mk(state.get("foundations", [[]])[i] if i < len(state.get("foundations", [])) else [])
        for i, t in enumerate(self.tableau):
            t.cards = mk(state.get("tableau", [[]])[i] if i < len(state.get("tableau", [])) else [])
        self._auto_active = False

    # ----- Undo -----
    def record_snapshot(self):
        def cap_pile(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [cap_pile(p) for p in self.foundations],
            "tableau": [cap_pile(p) for p in self.tableau],
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, p in enumerate(self.foundations):
            p.cards = mk(snap["foundations"][i])
        for i, p in enumerate(self.tableau):
            p.cards = mk(snap["tableau"][i])
        self.message = snap.get("message", "")

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()
            self.anim.cancel()
            self._auto_active = False

    # ----- Rules helpers -----
    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        f = self.foundations[fi]
        if not f.cards:
            return card.rank == 1
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

    def _can_stack_tableau(self, moving_bottom: C.Card, target_top: Optional[C.Card]) -> bool:
        if target_top is None:
            return moving_bottom.rank == 13  # King to empty
        return (is_red(moving_bottom.suit) != is_red(target_top.suit)) and (moving_bottom.rank == target_top.rank - 1)

    # ----- Animation helpers -----
    # (centralized in mechanics via CardAnimator)

    # ----- Auto helpers -----
    def can_autocomplete(self) -> bool:
        # All tableau cards must be face-up
        for t in self.tableau:
            for c in t.cards:
                if not c.face_up:
                    return False
        return True

    def start_autocomplete(self):
        if not self.can_autocomplete():
            return
        self._auto_active = True

    def _find_next_auto_move(self):
        for ti, t in enumerate(self.tableau):
            if not t.cards:
                continue
            c = t.cards[-1]
            fi = self._foundation_index_for_suit(c.suit)
            if self._can_move_to_foundation(c, fi):
                return (ti, fi)
        return None

    # ----- Events -----
    def _maybe_handle_double_click(self, e, mxw: int, myw: int) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - getattr(self, "_last_click_time", 0) <= 350
            and abs(e.pos[0] - getattr(self, "_last_click_pos", (0, 0))[0]) <= 6
            and abs(e.pos[1] - getattr(self, "_last_click_pos", (0, 0))[1]) <= 6
        )
        handled = False
        if double:
            # Tableau top cards -> foundation
            for ti, t in enumerate(self.tableau):
                hi = t.hit((mxw, myw))
                if hi is None:
                    continue
                if hi == -1 and t.cards:
                    hi = len(t.cards) - 1
                if hi == len(t.cards) - 1 and t.cards[hi].face_up:
                    c = t.cards[-1]
                    fi = self._foundation_index_for_suit(c.suit)
                    if self._can_move_to_foundation(c, fi):
                        # Animate from card rect to foundation
                        r = t.rect_for_index(len(t.cards) - 1)
                        self.push_undo()
                        t.cards.pop()
                        def _done(ci=c, ffi=fi):
                            self.foundations[ffi].cards.append(ci)
                            self._post_move_cleanup()
                        self.anim.start_move(c, (r.x, r.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=260, on_complete=_done)
                        handled = True
                        break
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    def handle_event(self, e):
        # Help overlay intercept
        if getattr(self, "help", None) and self.help.visible:
            if self.help.handle_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.KEYDOWN, pygame.MOUSEWHEEL):
                return
        if self.ui_helper.handle_menu_event(e):
            return

        if self.toolbar.handle_event(e):
            return
        if self.ui_helper.handle_shortcuts(e):
            return

        if self.drag_pan.handle_event(e, target=self, clamp=self._clamp_scroll_xy):
            self.peek.cancel()
            return

        # Do not interact while animation is running
        if self.anim.active:
            return

        if e.type == pygame.KEYDOWN:
            self.ui_helper.handle_shortcuts(e)
            return

        # Mouse wheel scroll
        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            try:
                self.scroll_x += e.x * 60
            except Exception:
                pass
            self._clamp_scroll_xy()
            self.peek.cancel()
            return

        # Scrollbar interactions (vertical)
        # Track mouse for edge panning and handle clicks
        if e.type == pygame.MOUSEMOTION:
            self.edge_pan.on_mouse_pos(e.pos)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            vsb = self._vertical_scrollbar()
            if vsb is not None:
                track_rect, knob_rect, min_sy, max_sy, track_y, track_h, knob_h = vsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_vscroll = True
                    self._vscroll_drag_dy = e.pos[1] - knob_rect.y
                    self._vscroll_geom = (min_sy, max_sy, track_y, track_h, knob_h)
                    return
                elif track_rect.collidepoint(e.pos):
                    y = min(max(e.pos[1] - knob_h // 2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                    self._clamp_scroll_xy()
                    return
        elif e.type == pygame.MOUSEMOTION and self._drag_vscroll:
            if self._vscroll_geom is not None:
                min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
                y = min(max(e.pos[1] - self._vscroll_drag_dy, track_y), track_y + track_h - knob_h)
                t_knob = (y - track_y) / max(1, (track_h - knob_h))
                self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                self._clamp_scroll_xy()
            return
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_vscroll:
            self._drag_vscroll = False
            self._vscroll_geom = None
            return

        # Scrollbar interactions (horizontal)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            hsb = self._horizontal_scrollbar()
            if hsb is not None:
                track_rect, knob_rect, min_sx, max_sx, track_x, track_w, knob_w = hsb
                if knob_rect.collidepoint(e.pos):
                    self._drag_hscroll = True
                    self._hscroll_drag_dx = e.pos[0] - knob_rect.x
                    self._hscroll_geom = (min_sx, max_sx, track_x, track_w, knob_w)
                    return
                elif track_rect.collidepoint(e.pos):
                    x = min(max(e.pos[0] - knob_w // 2, track_x), track_x + track_w - knob_w)
                    t_knob = (x - track_x) / max(1, (track_w - knob_w))
                    self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                    self._clamp_scroll_xy()
                    return
        elif e.type == pygame.MOUSEMOTION and self._drag_hscroll:
            if self._hscroll_geom is not None:
                min_sx, max_sx, track_x, track_w, knob_w = self._hscroll_geom
                x = min(max(e.pos[0] - self._hscroll_drag_dx, track_x), track_x + track_w - knob_w)
                t_knob = (x - track_x) / max(1, (track_w - knob_w))
                self.scroll_x = min_sx + t_knob * (max_sx - min_sx)
                self._clamp_scroll_xy()
            return
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_hscroll:
            self._drag_hscroll = False
            self._hscroll_geom = None
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            if my < getattr(C, "TOP_BAR_H", 60):
                return
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y

            # Double-click -> foundation
            if self._maybe_handle_double_click(e, mxw, myw):
                self._post_move_cleanup()
                return

            # Cancel peek on click
            self.peek.cancel()

            # Tableau drag: any face-up substack starting at clicked index
            for ti, t in enumerate(self.tableau):
                hi = t.hit((mxw, myw))
                if hi is None:
                    continue
                if hi == len(t.cards) - 1 and not t.cards[hi].face_up:
                    # Flip a face-down top card when clicked
                    t.cards[hi].face_up = True
                    self.push_undo()
                    return
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]
                    t.cards = t.cards[:hi]
                    self.drag_stack = (seq, ti)
                    self.edge_pan.set_active(True)
                    return

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag_stack:
            stack, src_i = self.drag_stack
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            dropped = False
            for ti, t in enumerate(self.tableau):
                r = pygame.Rect(t.x, t.y, C.CARD_W, max(C.CARD_H, len(t.cards) * t.fan_y + C.CARD_H))
                if r.collidepoint((mxw, myw)):
                    # Determine target top card
                    top = t.cards[-1] if t.cards else None
                    if self._can_stack_tableau(stack[0], top):
                        self.push_undo()
                        t.cards.extend(stack)
                        dropped = True
                    break
            if not dropped:
                # Return to source
                self.tableau[src_i].cards.extend(stack)
            self.drag_stack = None
            self.edge_pan.set_active(False)
            self._post_move_cleanup()

        # Hover peek (Klondike-style)
        if e.type == pygame.MOUSEMOTION and not self.drag_stack and not self._drag_vscroll and not self._drag_hscroll:
            mx, my = e.pos
            mxw = mx - self.scroll_x
            myw = my - self.scroll_y
            self.peek.on_motion_over_piles(self.tableau, (mxw, myw))

    def _post_move_cleanup(self):
        # Flip newly exposed cards
        for p in self.tableau:
            if p.cards and not p.cards[-1].face_up:
                p.cards[-1].face_up = True
        # Auto-move exposed aces using shared helper
        if not self.anim.active:
            M.auto_move_first_ace(self.tableau, self.foundations, self.foundation_suits, self.anim)
        # Check win
        if all(len(f.cards) == 13 for f in self.foundations):
            self.message = "Congratulations! You won!"

    # ----- Scrolling helpers -----
    def _content_bounds_x(self):
        lefts = []
        rights = []
        piles = self.foundations + self.tableau
        for p in piles:
            lefts.append(p.x)
            rights.append(p.x + C.CARD_W)
        return (min(lefts) if lefts else 0, max(rights) if rights else C.SCREEN_W)

    def _content_bottom_y(self) -> int:
        bottoms = []
        for f in self.foundations:
            bottoms.append(f.y + C.CARD_H)
        for t in self.tableau:
            n = max(1, len(t.cards))
            bottoms.append(t.y + (n - 1) * t.fan_y + C.CARD_H)
        return max(bottoms) if bottoms else C.SCREEN_H

    def _clamp_scroll_xy(self):
        bottom = self._content_bottom_y()
        min_sy = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y < min_sy:
            self.scroll_y = min_sy
        if self.scroll_y > 0:
            self.scroll_y = 0
        left, right = self._content_bounds_x()
        max_sx = 20 - left
        min_sx = min(0, C.SCREEN_W - right - 20)
        if self.scroll_x > max_sx:
            self.scroll_x = max_sx
        if self.scroll_x < min_sx:
            self.scroll_x = min_sx

    def _vertical_scrollbar(self):
        bottom = self._content_bottom_y()
        if bottom <= C.SCREEN_H:
            return None
        track_x = C.SCREEN_W - 12
        track_y = getattr(C, "TOP_BAR_H", 64)
        track_h = C.SCREEN_H - track_y - 10
        track_rect = pygame.Rect(track_x, track_y, 6, track_h)
        view_h = C.SCREEN_H
        content_h = bottom
        knob_h = max(30, int(track_h * (view_h / content_h)))
        max_scroll = 0
        min_scroll = C.SCREEN_H - bottom - 20
        denom = (max_scroll - min_scroll)
        t = (self.scroll_y - min_scroll) / denom if denom != 0 else 1.0
        knob_y = int(track_y + (track_h - knob_h) * (1.0 - t))
        knob_rect = pygame.Rect(track_x, knob_y, 6, knob_h)
        return track_rect, knob_rect, min_scroll, max_scroll, track_y, track_h, knob_h

    def _horizontal_scrollbar(self):
        left, right = self._content_bounds_x()
        if right - left <= C.SCREEN_W - 40:
            return None
        track_x = 10
        track_w = C.SCREEN_W - 20
        track_y = C.SCREEN_H - 10
        track_rect = pygame.Rect(track_x, track_y - 6, track_w, 6)
        view_w = C.SCREEN_W
        content_w = right - left + 40
        knob_w = max(30, int(track_w * (view_w / max(view_w, content_w))))
        max_scroll_x = 20 - left
        min_scroll_x = min(0, C.SCREEN_W - right - 20)
        denom = (max_scroll_x - min_scroll_x)
        t = (self.scroll_x - min_scroll_x) / denom if denom != 0 else 1.0
        knob_x = int(track_x + (track_w - knob_w) * t)
        knob_rect = pygame.Rect(knob_x, track_y - 6, knob_w, 6)
        return track_rect, knob_rect, min_scroll_x, max_scroll_x, track_x, track_w, knob_w

    # ----- Update/Draw -----
    def update(self, dt):
        # Drive auto-complete with animation steps
        if self._auto_active and not self.anim.active:
            nxt = self._find_next_auto_move()
            if not nxt:
                self._auto_active = False
                if all(len(f.cards) == 13 for f in self.foundations):
                    self.message = "Congratulations! You won!"
            else:
                ti, fi = nxt
                src = self.tableau[ti]
                c = src.cards[-1]
                r = src.rect_for_index(len(src.cards) - 1)
                src.cards.pop()
                def _done(ci=c, ffi=fi):
                    self.foundations[ffi].cards.append(ci)
                self.anim.start_move(c, (r.x, r.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=240, on_complete=_done)

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

        # Apply scroll offsets for pile drawing
        C.DRAW_OFFSET_X = self.scroll_x
        C.DRAW_OFFSET_Y = self.scroll_y

        # Draw foundations (with suit markers on empty)
        for i, f in enumerate(self.foundations):
            f.draw(screen)
            if not f.cards:
                suit_i = self.foundation_suits[i]
                suit_char = C.SUITS[suit_i]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                cx = f.x + C.CARD_W // 2 + self.scroll_x
                cy = f.y + C.CARD_H // 2 + self.scroll_y
                screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        # Draw tableau
        for t in self.tableau:
            t.draw(screen)

        # Dragging stack follows mouse
        if self.drag_stack:
            stack, _ = self.drag_stack
            mx, my = pygame.mouse.get_pos()
            for i, c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W // 2, my - C.CARD_H // 2 + i * 28))
        elif self.peek.overlay:
            # Draw peek overlay before animation/UI
            card, rx, ry = self.peek.overlay
            surf = C.get_card_surface(card)
            screen.blit(surf, (rx + self.scroll_x, ry + self.scroll_y))

        # Animation overlay
        self.anim.draw(screen, scroll_x=self.scroll_x, scroll_y=self.scroll_y)

        # Message
        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 40))

        # UI reset
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0
        C.Scene.draw_top_bar(self, screen, "Yukon")
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

        # Scrollbars
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

        # Auto-complete driver
        if self._auto_active and not self.anim.active:
            nxt = self._find_next_auto_move()
            if not nxt:
                self._auto_active = False
                if all(len(f.cards) == 13 for f in self.foundations):
                    self.message = "Congratulations! You won!"
            else:
                ti, fi = nxt
                src = self.tableau[ti]
                c = src.cards[-1]
                r = src.rect_for_index(len(src.cards) - 1)
                src.cards.pop()
                def _done(ci=c, ffi=fi):
                    self.foundations[ffi].cards.append(ci)
                self.anim.start_move(c, (r.x, r.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=240, on_complete=_done)

        # Activate pending peek by time
        self.peek.maybe_activate(pygame.time.get_ticks())
