import json
import os
from typing import Any, Dict, List, Optional, Tuple

import pygame

from solitaire import common as C
from solitaire.modes.base_scene import ModeUIHelper
from solitaire.help_data import create_modal_help
from solitaire import mechanics as M


_SAVE_FILENAME = "gate_save.json"


def _gate_dir() -> str:
    return C.project_saves_dir("gate")


def _gate_save_path() -> str:
    return os.path.join(_gate_dir(), _SAVE_FILENAME)


def _safe_write_json(path: str, data: Any) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception:
        pass


def _safe_read_json(path: str) -> Optional[Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _clear_saved_game() -> None:
    try:
        if os.path.isfile(_gate_save_path()):
            os.remove(_gate_save_path())
    except Exception:
        pass


def has_saved_game() -> bool:
    state = _safe_read_json(_gate_save_path())
    if not isinstance(state, dict):
        return False
    if state.get("completed"):
        return False
    return True


def load_saved_game() -> Optional[Dict[str, Any]]:
    state = _safe_read_json(_gate_save_path())
    if not isinstance(state, dict):
        return None
    if state.get("completed"):
        return None
    return state


def is_red(suit: int) -> bool:
    return suit in (1, 2)


 


class GateGameScene(C.Scene):
    """
    Gate mode.
    - 8 center tableau piles (2 rows x 4 columns), build down by 1, alternating colors.
    - 2 reserve piles (left/right of the 8 center piles), start with 5 face-up cards; cannot place onto reserves.
    - 4 foundations with dedicated suits (Spades, Hearts, Diamonds, Clubs) above the top row of 4 center piles.
    - Stock (above) and Waste (below) on the far left; click stock to draw 1 card (no redeal).
    - When a center pile becomes empty, it is immediately filled from Stock, else from Waste. If both are empty, it stays
      empty; the player may manually move a reserve top card into the empty center (optional).
    - Objective: complete all foundations A->K of their suit. Cards cannot be removed from foundations.
    """

    def __init__(self, app, load_state: Optional[Dict[str, Any]] = None):
        super().__init__(app)

        # Piles
        self.foundations: List[C.Pile] = [C.Pile(0, 0) for _ in range(4)]
        self.foundation_suits: List[int] = [0, 1, 2, 3]  # Spades, Hearts, Diamonds, Clubs
        self.stock_pile: C.Pile = C.Pile(0, 0)
        self.waste_pile: C.Pile = C.Pile(0, 0)
        # 8 center tableau (2 x 4). Match Klondike fan height so stacks read the same
        self.center: List[C.Pile] = [C.Pile(0, 0, fan_y=max(18, int(C.CARD_H * 0.28))) for _ in range(8)]
        # Presets for dynamic center stacking (compact when tall)
        self._center_fan_default = max(18, int(C.CARD_H * 0.28))
        # Increase compact overlap to ~20px for better readability
        self._center_fan_compact = 20
        # Left and Right Reserve; ensure each card overlaps no more than half height
        self.reserves: List[C.Pile] = [C.Pile(0, 0, fan_y=max(C.CARD_H // 2, 24)) for _ in range(2)]

        # Drag state: (cards, src_kind, src_index)
        self.drag_stack: Optional[Tuple[List[C.Card], str, int]] = None
        self.message: str = ""
        self.undo_mgr = C.UndoManager()

        self.ui_helper = ModeUIHelper(self, game_id="gate")

        def can_undo():
            return self.undo_mgr.can_undo()

        def save_and_exit() -> None:
            self._save_game(to_menu=True)

        self.toolbar = self.ui_helper.build_toolbar(
            new_action={"on_click": self.deal_new},
            restart_action={"on_click": self.restart, "tooltip": "Restart current deal"},
            undo_action={"on_click": self.undo, "enabled": can_undo, "tooltip": "Undo last move"},
            auto_action={
                "on_click": self.start_auto_complete,
                "enabled": self.can_autocomplete,
                "tooltip": "Auto-finish to foundations",
            },
            save_action=(
                "Save&Exit",
                {
                    "on_click": save_and_exit,
                    "tooltip": "Save game and return to menu",
                },
            ),
            help_action={"on_click": lambda: self.help.open(), "tooltip": "How to play"},
        )

        # Shared animator for single-card moves (needed before loading saved games)
        self.anim: M.CardAnimator = M.CardAnimator()

        self.compute_layout()
        if load_state:
            self._load_from_state(load_state)
        else:
            self.deal_new()
        # Help overlay
        self.help = create_modal_help("gate")

        # Double-click tracking (to foundations)
        self._last_click_time = 0
        self._last_click_pos = (0, 0)
        # Klondike-style peek controller (shows single hovered face-up card under delay)
        self.peek = M.PeekController(delay_ms=2000)
        # Auto-complete state
        self._auto_complete_active = False
        # Vertical scrolling
        self.scroll_y = 0
        self.drag_pan = M.DragPanController()
        self._drag_vscroll = False
        self._vscroll_drag_dy = 0
        self._vscroll_geom: Optional[Tuple[int, int, int, int, int]] = None
        # Edge panning while dragging (vertical only in Gate)
        self.edge_pan = M.EdgePanDuringDrag(edge_margin_px=28, top_inset_px=getattr(C, "TOP_BAR_H", 64))

    # ----- Layout -----
    def compute_layout(self):
        gap_x = getattr(C, "CARD_GAP_X", max(18, C.CARD_W // 6))
        gap_y = getattr(C, "CARD_GAP_Y", max(20, C.CARD_H // 6))

        top_bar_h = getattr(C, "TOP_BAR_H", 60)
        top_y = max(90, top_bar_h + 24)

        # 4 center columns remain centered
        cols = 4
        center_block_w = cols * C.CARD_W + (cols - 1) * gap_x
        center_left = (C.SCREEN_W - center_block_w) // 2

        # Top middle tableaus move up to previous foundation row (top_y)
        row1_y = top_y
        # Bottom middle tableaus at original spacing, lowered ~0.25 card height
        row2_y = row1_y + C.CARD_H + max(gap_y, int(C.CARD_H * 1.25)) + (C.CARD_H // 4)

        # Foundations: single column on the right side, Spades->Clubs top to bottom
        # Make spacing from right reserve to foundations equal to stock-to-left-reserve spacing
        reserve_gap = max(gap_x * 2, int(C.CARD_W * 0.6))
        center_block_w = cols * C.CARD_W + (cols - 1) * gap_x
        center_left = (C.SCREEN_W - center_block_w) // 2
        right_res_x = center_left + center_block_w + reserve_gap
        # We'll compute stock gap next; use a default for now and adjust after stock_x is known
        # Temporarily set foundation_x; will be recomputed after stock_x
        foundation_x = right_res_x + C.CARD_W + max(16, gap_x * 2)
        for i in range(4):
            fy = top_y + i * (C.CARD_H + gap_y)
            self.foundations[i].x, self.foundations[i].y = foundation_x, fy

        # Center piles (2 rows x 4 columns)
        for i in range(4):
            x = center_left + i * (C.CARD_W + gap_x)
            self.center[i].x, self.center[i].y = x, row1_y
            self.center[4 + i].x, self.center[4 + i].y = x, row2_y
            # Match Klondike fan height
            self.center[i].fan_y = max(18, int(C.CARD_H * 0.28))
            self.center[4 + i].fan_y = max(18, int(C.CARD_H * 0.28))

        # Reserves to left and right of the 8 center piles
        # Reserve Y so the center of the middle card (index 2 of 5) sits on the midline
        left_res_x = center_left - reserve_gap - C.CARD_W
        hearts_mid_y = self.foundations[1].y + (C.CARD_H // 2)
        diamonds_mid_y = self.foundations[2].y + (C.CARD_H // 2)
        mid_y = (hearts_mid_y + diamonds_mid_y) // 2
        reserve_middle_index = 2  # for initial 5-card reserve
        reserve_fan_y = max(C.CARD_H // 2, 24)
        res_y = mid_y - (reserve_middle_index * reserve_fan_y + C.CARD_H // 2)
        self.reserves[0].x, self.reserves[0].y = left_res_x, res_y
        self.reserves[1].x, self.reserves[1].y = right_res_x, res_y
        # Reinforce reserve fan so underlying rank/suit remain visible
        self.reserves[0].fan_y = max(C.CARD_H // 2, self.reserves[0].fan_y)
        self.reserves[1].fan_y = max(C.CARD_H // 2, self.reserves[1].fan_y)

        # Stock/Waste on the far left, stock above waste
        stock_gap = max(16, gap_x * 2)
        stock_x = max(10, left_res_x - (C.CARD_W + stock_gap))
        # Align stock with Hearts foundation (index 1), waste with Diamonds (index 2)
        stock_y = self.foundations[1].y
        waste_y = self.foundations[2].y
        self.stock_pile.x, self.stock_pile.y = stock_x, stock_y
        self.waste_pile.x, self.waste_pile.y = stock_x, waste_y

        # Now that stock_x is known, set foundations X so gap to right reserve equals stock gap
        foundation_x = right_res_x + C.CARD_W + stock_gap
        # Keep on screen
        foundation_x = min(foundation_x, C.SCREEN_W - C.CARD_W - 10)
        for i in range(4):
            self.foundations[i].x = foundation_x

    # ----- Deal / Restart -----
    def _clear(self):
        for p in self.center:
            p.cards.clear()
        for p in self.foundations:
            p.cards.clear()
        for p in self.reserves:
            p.cards.clear()
        self.stock_pile.cards.clear()
        self.waste_pile.cards.clear()
        self.drag_stack = None
        self.message = ""

    def deal_new(self):
        _clear_saved_game()
        self._clear()
        deck = C.make_deck(shuffle=True)

        # Reserves: 5 face-up each
        for i in range(5):
            c = deck.pop(); c.face_up = True
            self.reserves[0].cards.append(c)
        for i in range(5):
            c = deck.pop(); c.face_up = True
            self.reserves[1].cards.append(c)

        # Center piles: 1 face-up card each
        for i in range(8):
            c = deck.pop(); c.face_up = True
            self.center[i].cards.append(c)

        # Remaining to stock (face-down)
        for c in deck:
            c.face_up = False
        self.stock_pile.cards = deck

        # Reset undo
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        # Store restart snapshot
        self._initial_snapshot = self.record_snapshot()

    def restart(self):
        if getattr(self, "_initial_snapshot", None):
            self.restore_snapshot(self._initial_snapshot)
            self.drag_stack = None
            self.message = ""
            self.undo_mgr = C.UndoManager()
            self.push_undo()

    def _state_dict(self) -> Dict[str, Any]:
        state = self.record_snapshot()
        state.update(
            {
                "scroll_y": self.scroll_y,
                "initial_snapshot": getattr(self, "_initial_snapshot", None),
                "foundation_suits": list(self.foundation_suits),
                "completed": all(len(f.cards) == 13 for f in self.foundations),
            }
        )
        return state

    def _save_game(self, to_menu: bool = False) -> None:
        state = self._state_dict()
        _safe_write_json(_gate_save_path(), state)
        if to_menu:
            self.ui_helper.goto_main_menu()

    def _load_from_state(self, state: Dict[str, Any]) -> None:
        if not state:
            self.deal_new()
            return
        self.restore_snapshot(state)
        self.scroll_y = state.get("scroll_y", 0)
        suits = state.get("foundation_suits")
        if isinstance(suits, (list, tuple)) and len(suits) >= 4:
            self.foundation_suits = [int(s) for s in suits[:4]]
        init = state.get("initial_snapshot")
        if isinstance(init, dict):
            self._initial_snapshot = init
        else:
            self._initial_snapshot = self.record_snapshot()
        self.undo_mgr = C.UndoManager()
        self.push_undo()
        self.message = state.get("message", self.message)
        self._auto_complete_active = False
        self.anim.cancel()
        self._clamp_scroll()

    # ----- Undo -----
    def record_snapshot(self):
        def cap_pile(p: C.Pile):
            return [(c.suit, c.rank, c.face_up) for c in p.cards]
        return {
            "foundations": [cap_pile(p) for p in self.foundations],
            "stock": cap_pile(self.stock_pile),
            "waste": cap_pile(self.waste_pile),
            "center": [cap_pile(p) for p in self.center],
            "reserves": [cap_pile(p) for p in self.reserves],
            "message": self.message,
        }

    def restore_snapshot(self, snap):
        def mk(seq):
            return [C.Card(s, r, f) for (s, r, f) in seq]
        for i, p in enumerate(self.foundations):
            p.cards = mk(snap["foundations"][i])
        self.stock_pile.cards = mk(snap["stock"]) 
        self.waste_pile.cards = mk(snap["waste"]) 
        for i, p in enumerate(self.center):
            p.cards = mk(snap["center"][i])
        for i, p in enumerate(self.reserves):
            p.cards = mk(snap["reserves"][i])
        self.message = snap.get("message", "")

    def push_undo(self):
        s = self.record_snapshot()
        self.undo_mgr.push(lambda snap=s: self.restore_snapshot(snap))

    def undo(self):
        if self.undo_mgr.can_undo():
            self.undo_mgr.undo()

    # ----- Rules helpers -----
    def _can_stack_center(self, moving: C.Card, target: Optional[C.Card]) -> bool:
        if target is None:
            return False  # Center empties are auto-filled (not via manual placements)
        return (is_red(moving.suit) != is_red(target.suit)) and (moving.rank == target.rank - 1)

    def _can_move_to_foundation(self, card: C.Card, fi: int) -> bool:
        required_suit = self.foundation_suits[fi]
        if card.suit != required_suit:
            return False
        f = self.foundations[fi]
        if not f.cards:
            return card.rank == 1
        top = f.cards[-1]
        return (card.suit == top.suit) and (card.rank == top.rank + 1)

    def _foundation_index_for_suit(self, suit: int) -> int:
        try:
            return self.foundation_suits.index(suit)
        except ValueError:
            return 0

    def _fill_center_vacancies(self):
        """Start an animation to fill the next empty center pile from Stock, else Waste.
        If both are empty, leave as-is. Only one auto-fill animation runs at a time.
        If an Ace is drawn from stock here, animate it to its foundation first."""
        if self.anim.active:
            return
        for ti, p in enumerate(self.center):
            if p.cards:
                continue
            if self.stock_pile.cards:
                card = self.stock_pile.cards.pop()
                # If it's an Ace, route to foundation instead
                if card.rank == 1:
                    fi = self._foundation_index_for_suit(card.suit)
                    card.face_up = True
                    def _done(ci=card, ffi=fi):
                        self.foundations[ffi].cards.append(ci)
                        # Chain next fill and auto-move aces
                        self._fill_center_vacancies()
                        self._maybe_auto_move_revealed_aces()
                    self.anim.start_move(card, (self.stock_pile.x, self.stock_pile.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=320, on_complete=_done)
                else:
                    # Flip mid animation from back to face-up
                    def _done(ci=card, t_index=ti):
                        self.center[t_index].cards.append(ci)
                        self._fill_center_vacancies()
                        self._maybe_auto_move_revealed_aces()
                    self.anim.start_move(card, (self.stock_pile.x, self.stock_pile.y), (p.x, p.y), dur_ms=350, on_complete=_done, flip_mid=True)
                return
            elif self.waste_pile.cards:
                card = self.waste_pile.cards.pop()
                card.face_up = True
                def _done(ci=card, t_index=ti):
                    self.center[t_index].cards.append(ci)
                    self._fill_center_vacancies()
                    self._maybe_auto_move_revealed_aces()
                self.anim.start_move(card, (self.waste_pile.x, self.waste_pile.y), (p.x, p.y), dur_ms=300, on_complete=_done)
                return
            else:
                return

    def _has_legal_moves_when_stock_empty(self) -> bool:
        # Any move from waste to foundation or center?
        if self.waste_pile.cards:
            wc = self.waste_pile.cards[-1]
            # To foundation
            fi = self._foundation_index_for_suit(wc.suit)
            if self._can_move_to_foundation(wc, fi):
                return True
            # To any center top
            for p in self.center:
                top = p.cards[-1] if p.cards else None
                if top and self._can_stack_center(wc, top):
                    return True
        # From reserves to foundation or center
        for ri, r in enumerate(self.reserves):
            if not r.cards:
                continue
            c = r.cards[-1]
            fi = self._foundation_index_for_suit(c.suit)
            if self._can_move_to_foundation(c, fi):
                return True
            for p in self.center:
                top = p.cards[-1] if p.cards else None
                if top and self._can_stack_center(c, top):
                    return True
            # Optional rule: allow placing reserve top to an empty center only when stock and waste are empty
            if not self.waste_pile.cards:
                for p in self.center:
                    if not p.cards:
                        return True
        # From center to foundations or between centers
        for src in self.center:
            if not src.cards:
                continue
            top = src.cards[-1]
            # To foundation
            fi = self._foundation_index_for_suit(top.suit)
            if self._can_move_to_foundation(top, fi):
                return True
            # Between centers
            for dst in self.center:
                if src is dst:
                    continue
                if not dst.cards:
                    continue
                if self._can_stack_center(top, dst.cards[-1]):
                    return True
        return False

    # ----- Stock / Waste -----
    def draw_from_stock(self):
        if not self.stock_pile.cards:
            return  # No redeal in Gate
        c = self.stock_pile.cards.pop()
        c.face_up = True
        self.waste_pile.cards.append(c)
        self.message = ""
        # Auto-move Ace from waste to foundation with animation
        if c.rank == 1 and not self.anim.active:
            # Remove back from waste and animate to foundation
            self.waste_pile.cards.pop()
            fi = self._foundation_index_for_suit(c.suit)
            c.face_up = True
            def _done(ci=c, ffi=fi):
                self.foundations[ffi].cards.append(ci)
                self._fill_center_vacancies()
            self.anim.start_move(c, (self.waste_pile.x, self.waste_pile.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=300, on_complete=_done)

    # ----- Double-click helper -----
    def _maybe_handle_double_click(self, e, mx: int, my: int) -> bool:
        now = pygame.time.get_ticks()
        double = (
            now - getattr(self, "_last_click_time", 0) <= 350
            and abs(e.pos[0] - getattr(self, "_last_click_pos", (0, 0))[0]) <= 6
            and abs(e.pos[1] - getattr(self, "_last_click_pos", (0, 0))[1]) <= 6
        )
        handled = False
        if double:
            # Waste top -> foundation if legal
            if self.waste_pile.cards and self.waste_pile.top_rect().collidepoint((mx, my)):
                c = self.waste_pile.cards[-1]
                fi = self._foundation_index_for_suit(c.suit)
                if self._can_move_to_foundation(c, fi):
                    self.push_undo()
                    self.waste_pile.cards.pop()
                    self.foundations[fi].cards.append(c)
                    self._fill_center_vacancies()
                    handled = True
            # Center tops -> foundation
            if not handled:
                for t in self.center:
                    hi = t.hit((mx, my))
                    if hi is None:
                        continue
                    if hi == -1 and t.cards:
                        hi = len(t.cards) - 1
                    if hi == len(t.cards) - 1 and t.cards[hi].face_up:
                        c = t.cards[-1]
                        fi = self._foundation_index_for_suit(c.suit)
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            t.cards.pop()
                            self.foundations[fi].cards.append(c)
                            self._fill_center_vacancies()
                            handled = True
                            break
            # Reserve tops -> foundation
            if not handled:
                for ri, r in enumerate(self.reserves):
                    if r.cards and r.top_rect().collidepoint((mx, my)):
                        c = r.cards[-1]
                        fi = self._foundation_index_for_suit(c.suit)
                        if self._can_move_to_foundation(c, fi):
                            self.push_undo()
                            r.cards.pop()
                            self.foundations[fi].cards.append(c)
                            self._fill_center_vacancies()
                            handled = True
                            break
        self._last_click_time = now
        self._last_click_pos = e.pos
        return handled

    # ----- Events -----
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

        # Avoid interactions while auto-fill animation is running
        if self.anim.active:
            return

        # Update dynamic fan spacing for center piles
        self._update_center_fans()

        if self.drag_pan.handle_event(e, target=self, clamp=self._clamp_scroll, attr_x=None):
            self.peek.cancel()
            return

        # Mouse wheel vertical scroll
        if e.type == pygame.MOUSEWHEEL:
            self.scroll_y += e.y * 60
            self._clamp_scroll()
            # Cancel any peek while scrolling
            self.peek.cancel()
            return

        # Vertical scrollbar interactions
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
                    y = min(max(e.pos[1] - knob_h//2, track_y), track_y + track_h - knob_h)
                    t_knob = (y - track_y) / max(1, (track_h - knob_h))
                    # Map knob pos to scroll
                    self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                    self._clamp_scroll()
                    return
        elif e.type == pygame.MOUSEMOTION and self._drag_vscroll:
            if self._vscroll_geom is not None:
                min_sy, max_sy, track_y, track_h, knob_h = self._vscroll_geom
                y = min(max(e.pos[1] - self._vscroll_drag_dy, track_y), track_y + track_h - knob_h)
                t_knob = (y - track_y) / max(1, (track_h - knob_h))
                self.scroll_y = min_sy + (1.0 - t_knob) * (max_sy - min_sy)
                self._clamp_scroll()
            return
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self._drag_vscroll:
            self._drag_vscroll = False
            self._vscroll_geom = None
            return

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            # Clear message on click
            self.message = ""
            # Cancel any pending peek on click
            self.peek.cancel()

        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            mx, my = e.pos
            # Convert to world coordinates for pile interactions
            myw = my - self.scroll_y
            mxw = mx
            # Prevent interactions under the top bar
            if my < getattr(C, "TOP_BAR_H", 60):
                return
            if self._maybe_handle_double_click(e, mxw, myw):
                self._post_move_checks()
                return
            # Stock click -> draw 1
            if pygame.Rect(self.stock_pile.x, self.stock_pile.y, C.CARD_W, C.CARD_H).collidepoint((mxw, myw)):
                self.push_undo(); self.draw_from_stock(); return
            # Waste drag (top only)
            wi = self.waste_pile.hit((mxw, myw))
            if wi is not None and wi == len(self.waste_pile.cards) - 1:
                c = self.waste_pile.cards.pop()
                self.drag_stack = ([c], "waste", -1)
                self.edge_pan.set_active(True)
                return
            # Reserve drag (top only)
            for ri, r in enumerate(self.reserves):
                hi = r.hit((mxw, myw))
                if hi is not None and hi == len(r.cards) - 1:
                    c = r.cards.pop()
                    self.drag_stack = ([c], "reserve", ri)
                    return
            # Foundations: cannot remove cards in Gate
            # Center drag: any face-up run starting at clicked index
            for ti, t in enumerate(self.center):
                hi = t.hit((mxw, myw))
                if hi is None:
                    continue
                if hi == len(t.cards) - 1 and not t.cards[hi].face_up:
                    t.cards[hi].face_up = True
                    self.push_undo()
                    return
                if hi != -1 and t.cards[hi].face_up:
                    seq = t.cards[hi:]
                    t.cards = t.cards[:hi]
                    self.drag_stack = (seq, "center", ti)
                    return

        # Hover peek (standard Klondike-style)
        if e.type == pygame.MOUSEMOTION and not self.drag_stack:
            mx, my = e.pos
            myw = my - self.scroll_y
            mxw = mx
            # Build peek state from center piles
            self.peek.on_motion_over_piles(self.center, (mxw, myw))

        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if not self.drag_stack:
                return
            stack, src_kind, src_idx = self.drag_stack
            self.drag_stack = None
            self.edge_pan.set_active(False)
            mx, my = e.pos
            myw = my - self.scroll_y
            mxw = mx

            # Try foundations first (only single card allowed)
            if len(stack) == 1:
                for fi, f in enumerate(self.foundations):
                    if f.top_rect().collidepoint((mxw, myw)):
                        if self._can_move_to_foundation(stack[0], fi):
                            self.push_undo()
                            f.cards.append(stack[0])
                            self._fill_center_vacancies()
                            self._post_move_checks()
                            return

            # Try center piles
            for ti, t in enumerate(self.center):
                r = t.top_rect()
                if r.collidepoint((mxw, myw)):
                    # Empty target: only allow when stock and waste are empty and source is reserve (single card)
                    if not t.cards:
                        if not self.stock_pile.cards and not self.waste_pile.cards and src_kind == "reserve" and len(stack) == 1:
                            self.push_undo()
                            t.cards.extend(stack)
                            self._post_move_checks()
                            return
                        else:
                            # Disallow general placement onto empty center
                            break
                    top = t.cards[-1]
                    if not top.face_up:
                        break
                    if self._can_stack_center(stack[0], top):
                        self.push_undo()
                        t.cards.extend(stack)
                        self._post_move_checks()
                        return

            # If we reach here, drop failed -> return cards to source
            self._return_drag_to_source(stack, src_kind, src_idx)

    def _return_drag_to_source(self, stack: List[C.Card], src_kind: str, src_idx: int):
        if src_kind == "waste":
            self.waste_pile.cards.extend(stack)
        elif src_kind == "reserve":
            self.reserves[src_idx].cards.extend(stack)
        elif src_kind == "center":
            self.center[src_idx].cards.extend(stack)

    def _post_move_checks(self):
        # Auto-fill vacancies and check win/lose
        self._fill_center_vacancies()
        if all(len(f.cards) == 13 for f in self.foundations):
            self.message = "Congratulations! You won!"
            _clear_saved_game()
            return
        if not self.stock_pile.cards:
            if not self._has_legal_moves_when_stock_empty():
                self.message = "No more legal moves. You lose."
                _clear_saved_game()

    # ----- Draw -----
    def draw(self, screen):
        screen.fill(C.TABLE_BG)
        # Keep center stacks compact if they grow tall
        self._update_center_fans()
        # Apply draw offset for piles
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = self.scroll_y
        # Draw piles
        for i, f in enumerate(self.foundations):
            f.draw(screen)
            if not f.cards:
                suit_i = self.foundation_suits[i]
                suit_char = C.SUITS[suit_i]
                txt = C.FONT_CENTER_SUIT.render(suit_char, True, C.WHITE)
                cx = f.x + C.CARD_W // 2
                cy = f.y + C.CARD_H // 2 + self.scroll_y
                screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))

        # Stock/Waste (no labels)
        self.stock_pile.draw(screen)
        self.waste_pile.draw(screen)

        # Reserves (no labels)
        for i, r in enumerate(self.reserves):
            r.draw(screen)

        # Center piles
        for t in self.center:
            t.draw(screen)

        # Edge panning while dragging (use current mouse position)
        self.edge_pan.on_mouse_pos(pygame.mouse.get_pos())
        has_v = self._vertical_scrollbar() is not None
        dx, dy = self.edge_pan.step(has_h_scroll=False, has_v_scroll=has_v)
        if dy:
            self.scroll_y += dy
            self._clamp_scroll()

        # Dragging stack follows mouse
        if self.drag_stack:
            stack, _, _ = self.drag_stack
            mx, my = pygame.mouse.get_pos()
            for i, c in enumerate(stack):
                surf = C.get_card_surface(c)
                screen.blit(surf, (mx - C.CARD_W // 2, my - C.CARD_H // 2 + i * 28))
        elif self.peek.overlay:
            # Draw single-card peek overlay at world position
            card, rx, ry = self.peek.overlay
            surf = C.get_card_surface(card)
            screen.blit(surf, (rx, ry + self.scroll_y))

        # Auto-fill animation overlay
        self.anim.draw(screen, scroll_x=0, scroll_y=self.scroll_y)

        # Message
        if self.message:
            msg = C.FONT_UI.render(self.message, True, (255, 255, 180))
            screen.blit(msg, (C.SCREEN_W // 2 - msg.get_width() // 2, C.SCREEN_H - 40))

        # Reset draw offsets for UI, then Top bar and toolbar
        C.DRAW_OFFSET_X = 0
        C.DRAW_OFFSET_Y = 0
        C.Scene.draw_top_bar(self, screen, "Gate")
        self.toolbar.draw(screen)
        if getattr(self, "help", None) and self.help.visible:
            self.help.draw(screen)
        self.ui_helper.draw_menu_modal(screen)

        # Activate any pending peek by time
        self.peek.maybe_activate(pygame.time.get_ticks())

        # Vertical scrollbar when content extends beyond view
        vsb = self._vertical_scrollbar()
        if vsb is not None:
            track_rect, knob_rect, *_ = vsb
            pygame.draw.rect(screen, (40, 40, 40), track_rect, border_radius=3)
            pygame.draw.rect(screen, (200, 200, 200), knob_rect, border_radius=3)

        # Auto-complete driver: when active and idle, start next move
        if self._auto_complete_active and not self.anim.active:
            if not self._step_auto_complete():
                self._auto_complete_active = False
                if all(len(f.cards) == 13 for f in self.foundations):
                    self.message = "Congratulations! You won!"

    def _update_center_fans(self):
        # Compact stacks with more than threshold cards
        for p in self.center:
            p.fan_y = M.compact_fan(len(p.cards), self._center_fan_default, self._center_fan_compact, threshold=3)

    def _maybe_auto_move_revealed_aces(self):
        # If a reserve top card is an Ace, animate it to its foundation
        if self.anim.active:
            return
        if M.auto_move_first_ace(self.reserves, self.foundations, self.foundation_suits, self.anim):
            return

    # ----- Auto-complete (center -> foundations) -----
    def can_autocomplete(self) -> bool:
        if self.stock_pile.cards or self.waste_pile.cards:
            return False
        # All reserve piles must be empty
        for r in self.reserves:
            if r.cards:
                return False
        return True

    def start_auto_complete(self):
        if not self.can_autocomplete():
            return
        self._auto_complete_active = True

    def _find_next_autocomplete_move(self):
        for ti, t in enumerate(self.center):
            if not t.cards:
                continue
            c = t.cards[-1]
            fi = self._foundation_index_for_suit(c.suit)
            if self._can_move_to_foundation(c, fi):
                return (ti, fi)
        return None

    def _step_auto_complete(self) -> bool:
        """Start animation for the next center->foundation move. Returns True if a move was started."""
        nxt = self._find_next_autocomplete_move()
        if not nxt:
            return False
        ti, fi = nxt
        src = self.center[ti]
        # Capture source card and its on-table rect before popping
        c = src.cards[-1]
        r = src.rect_for_index(len(src.cards) - 1)
        src.cards.pop()
        def _done(ci=c, ffi=fi):
            self.foundations[ffi].cards.append(ci)
        self.anim.start_move(c, (r.x, r.y), (self.foundations[fi].x, self.foundations[fi].y), dur_ms=240, on_complete=_done)
        return True

    # ----- Scrolling helpers -----
    def _content_bottom_y(self) -> int:
        bottoms = []
        # Foundations column
        for f in self.foundations:
            bottoms.append(f.y + C.CARD_H)
        # Stock/Waste
        bottoms.append(self.stock_pile.y + C.CARD_H)
        bottoms.append(self.waste_pile.y + C.CARD_H)
        # Reserves
        for r in self.reserves:
            n = max(1, len(r.cards))
            bottoms.append(r.y + (n - 1) * r.fan_y + C.CARD_H)
        # Center piles
        for t in self.center:
            n = max(1, len(t.cards))
            bottoms.append(t.y + (n - 1) * t.fan_y + C.CARD_H)
        return max(bottoms) if bottoms else C.SCREEN_H

    def _clamp_scroll(self):
        bottom = self._content_bottom_y()
        min_scroll = min(0, C.SCREEN_H - bottom - 20)
        if self.scroll_y < min_scroll:
            self.scroll_y = min_scroll
        if self.scroll_y > 0:
            self.scroll_y = 0

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
