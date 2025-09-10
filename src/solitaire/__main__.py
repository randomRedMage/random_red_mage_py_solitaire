
# main.py - entry point
import os
import pygame
from solitaire import common as C
from solitaire.scenes.menu import MainMenuScene

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
    # Start at Title screen
    from solitaire.scenes.title import TitleScene
    scene = TitleScene(app=None)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
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
                scene.handle_event(e)
        if scene.next_scene is not None:
            scene = scene.next_scene
        scene.draw(screen)
        pygame.display.flip()
    pygame.quit()

if __name__ == "__main__":
    main()
