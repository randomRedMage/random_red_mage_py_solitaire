
# main.py - entry point
import pygame
from solitaire.common import (SCREEN_W, SCREEN_H, setup_fonts, TABLE_BG)
from solitaire.scenes.menu import MainMenuScene

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Solitaire Suite")
    setup_fonts()
    clock = pygame.time.Clock()
    scene = MainMenuScene(app=None)
    # Give scene a reference to an app container if needed; here we pass None
    # but scenes don't currently use it beyond storage.
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            else:
                scene.handle_event(e)
        if scene.next_scene is not None:
            scene = scene.next_scene
        scene.draw(screen)
        pygame.display.flip()
    pygame.quit()

if __name__ == "__main__":
    main()
