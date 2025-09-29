
# main.py - entry point
import os
import pygame
from solitaire import common as C
from solitaire.scenes.menu import MainMenuScene
from solitaire import mechanics as M

def _initial_window_size():
    info = pygame.display.Info()
    # Keep a safety margin so the window never hides under taskbar
    margin_w, margin_h = 120, 140
    w = min(C.SCREEN_W, max(640, info.current_w - margin_w))
    h = min(C.SCREEN_H, max(480, info.current_h - margin_h))
    return w, h

def main():
    # Center window and init
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()

    # Pick a safe default size for this desktop
    w, h = _initial_window_size()
    C.SCREEN_W, C.SCREEN_H = w, h
    screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
    pygame.display.set_caption("Solitaire Suite")
    C.setup_fonts()
    clock = pygame.time.Clock()
    # Developer debug: launch a specific scene via environment
    debug_scene = os.environ.get("SOLI_DEBUG_SCENE", "").strip().lower()
    debug_tall = os.environ.get("SOLI_DEBUG_TALL", "").strip() in ("1", "true", "yes")
    debug_card_size = os.environ.get("SOLI_CARD_SIZE", "").strip().capitalize()

    if debug_card_size in ("Small", "Medium", "Large"):
        try:
            C.apply_card_settings(size_name=debug_card_size)
        except Exception:
            pass

    scene = None
    if debug_scene:
        try:
            if debug_scene in ("klondike", "k"):
                from solitaire.modes.klondike import KlondikeGameScene
                scene = KlondikeGameScene(app=None)
            elif debug_scene in ("freecell", "fc"):
                from solitaire.modes.freecell import FreeCellGameScene
                scene = FreeCellGameScene(app=None)
            elif debug_scene in ("yukon", "y"):
                from solitaire.modes.yukon import YukonGameScene
                scene = YukonGameScene(app=None)
            elif debug_scene in ("gate", "g"):
                from solitaire.modes.gate import GateGameScene, GateOptionsScene
                try:
                    scene = GateGameScene(app=None)
                except Exception:
                    # Fallback to options for easier debugging if game scene fails
                    scene = GateOptionsScene(app=None)
            elif debug_scene in ("bigben", "big_ben", "bb"):
                from solitaire.modes.big_ben import BigBenGameScene
                scene = BigBenGameScene(app=None)
            elif debug_scene in ("beleaguered", "beleaguered_castle", "bc"):
                from solitaire.modes.beleaguered_castle import BeleagueredCastleGameScene
                scene = BeleagueredCastleGameScene(app=None)
        except Exception:
            scene = None
    if scene is None:
        # Start at Title screen
        from solitaire.scenes.title import TitleScene
        scene = TitleScene(app=None)

    # Optionally reshape piles for edge-pan testing
    if debug_tall:
        try:
            M.debug_prepare_edge_pan_test(scene)
        except Exception:
            pass

    # Build a filter set of system/media keys to ignore
    def _system_keys_set():
        names = [
            # Brightness / keyboard illumination
            "K_BRIGHTNESSUP", "K_BRIGHTNESSDOWN", "K_KBDILLUMUP", "K_KBDILLUMDOWN", "K_KBDILLUMTOGGLE",
            # Volume / media
            "K_VOLUMEUP", "K_VOLUMEDOWN", "K_MUTE", "K_AUDIOMUTE",
            "K_AUDIOPLAY", "K_AUDIOSTOP", "K_AUDIONEXT", "K_AUDIOPREV",
            "K_MEDIASELECT",
        ]
        out = set()
        for n in names:
            v = getattr(pygame, n, None)
            if isinstance(v, int):
                out.add(v)
        # Add F1..F12 to ignore set (apps rarely bind these by default)
        for i in range(1, 13):
            keyname = f"K_F{i}"
            v = getattr(pygame, keyname, None)
            if isinstance(v, int):
                out.add(v)
        return out

    _SYSTEM_KEYS = _system_keys_set()
    # Allowlist of keys scenes are allowed to receive (everything else is ignored)
    def _allowed_keys_set():
        keys = [
            "K_ESCAPE", "K_RETURN", "K_KP_ENTER", "K_SPACE",
            "K_n", "K_r", "K_u", "K_h", "K_a", "K_q",
        ]
        out = set()
        for n in keys:
            v = getattr(pygame, n, None)
            if isinstance(v, int):
                out.add(v)
        return out

    _ALLOWED_KEYS = _allowed_keys_set()

    running = True
    confirm_quit = False

    def _confirm_modal_rects():
        mw, mh = 460, 180
        modal = pygame.Rect(0, 0, mw, mh)
        modal.center = (C.SCREEN_W // 2, C.SCREEN_H // 2)
        # Buttons
        bw, bh = 120, 44
        gap = 30
        yes = pygame.Rect(0, 0, bw, bh)
        no  = pygame.Rect(0, 0, bw, bh)
        yes.centerx = modal.centerx - (bw // 2 + gap)
        no.centerx  = modal.centerx + (bw // 2 + gap)
        yes.bottom = modal.bottom - 20
        no.bottom  = modal.bottom - 20
        return modal, yes, no
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                helper = getattr(scene, "ui_helper", None)
                modal = getattr(helper, "menu_modal", None)
                if modal and hasattr(modal, "has_pending_confirm"):
                    try:
                        if modal.has_pending_confirm():
                            modal.accept_default_confirm()
                    except Exception:
                        pass
                confirm_quit = True
                continue
            elif e.type == pygame.VIDEORESIZE:
                # Apply new size and relayout UI
                C.SCREEN_W, C.SCREEN_H = e.size
                screen = pygame.display.set_mode((C.SCREEN_W, C.SCREEN_H), pygame.RESIZABLE)
                # Relayout any scene that supports it
                if hasattr(scene, "compute_layout"):
                    try:
                        scene.compute_layout()
                    except Exception:
                        pass
                if hasattr(scene, "toolbar") and hasattr(scene.toolbar, "relayout"):
                    try:
                        scene.toolbar.relayout()
                    except Exception:
                        pass
            else:
                # Filter out system/media keys to avoid accidental actions
                if confirm_quit:
                    # Handle confirm dialog input only
                    if e.type == pygame.KEYDOWN:
                        if e.key in (pygame.K_ESCAPE, pygame.K_n):
                            confirm_quit = False
                            continue
                        if e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y):
                            running = False
                            continue
                        # Swallow all other keys while modal is active
                        continue
                    if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                        modal, yes_r, no_r = _confirm_modal_rects()
                        if yes_r.collidepoint(e.pos):
                            running = False
                            continue
                        if no_r.collidepoint(e.pos):
                            confirm_quit = False
                            continue
                        # Clicks outside modal are ignored
                        continue
                    # Ignore other events during confirm
                    continue
                # Normal input path
                if e.type == pygame.KEYDOWN and getattr(e, "key", None) in _SYSTEM_KEYS:
                    # Allow Alt+F4 to still be caught via QUIT; otherwise ignore F-keys
                    continue
                # Detect Alt+F4 explicitly to trigger confirm
                if e.type == pygame.KEYDOWN and getattr(e, "key", None) == getattr(pygame, "K_F4", -1):
                    if getattr(e, "mod", 0) & pygame.KMOD_ALT:
                        confirm_quit = True
                        continue
                # Enforce key allowlist (except Alt+F4 path handled above)
                if e.type == pygame.KEYDOWN and getattr(e, "key", None) not in _ALLOWED_KEYS:
                    continue
                scene.handle_event(e)
        if scene.next_scene is not None:
            scene = scene.next_scene
        scene.draw(screen)
        # Overlay quit confirmation if active
        if confirm_quit:
            # Dim background
            overlay = pygame.Surface((C.SCREEN_W, C.SCREEN_H), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 160))
            screen.blit(overlay, (0, 0))
            # Modal
            modal, yes_r, no_r = _confirm_modal_rects()
            pygame.draw.rect(screen, (240, 240, 240), modal, border_radius=16)
            pygame.draw.rect(screen, (80, 80, 80), modal, width=2, border_radius=16)
            title = C.FONT_TITLE.render("Quit Game?", True, (20, 20, 20))
            screen.blit(title, (modal.centerx - title.get_width() // 2, modal.y + 20))
            msg = C.FONT_UI.render("Unsaved progress may be lost.", True, (30, 30, 30))
            screen.blit(msg, (modal.centerx - msg.get_width() // 2, modal.y + 20 + title.get_height() + 8))
            # Buttons
            def draw_btn(rect, label):
                pygame.draw.rect(screen, (230, 230, 235), rect, border_radius=10)
                pygame.draw.rect(screen, (100, 100, 110), rect, 1, border_radius=10)
                t = C.FONT_UI.render(label, True, (20, 20, 25))
                screen.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
            draw_btn(yes_r, "Yes")
            draw_btn(no_r, "No")
        pygame.display.flip()
    pygame.quit()

if __name__ == "__main__":
    main()
