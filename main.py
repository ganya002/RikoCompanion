import pygame
import sys
import json
import os

pygame.init()

WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Riko Companion")

from sprites import RikoSprite
from riko_brain import RikoBrain

DARK_BG = (15, 15, 22)
TEXT_COLOR = (220, 220, 230)
ACCENT = (255, 180, 200)
INPUT_BG = (30, 30, 42)
BORDER = (50, 50, 70)

clock = pygame.time.Clock()
font = pygame.font.SysFont("Menlo", 18)
font_small = pygame.font.SysFont("Menlo", 14)

riko_sprite = RikoSprite("riko.png")
riko_brain = RikoBrain()
history = riko_brain.get_history()

input_box = pygame.Rect(60, 530, 600, 44)
input_text = ""
input_active = False

current_response = "Hey... you finally opened me~"
waiting_for_response = False

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.MOUSEBUTTONDOWN:
            if input_box.collidepoint(event.pos):
                input_active = True
            else:
                input_active = False

        if event.type == pygame.KEYDOWN:
            if input_active:
                if (
                    event.key == pygame.K_RETURN
                    and input_text.strip()
                    and not waiting_for_response
                ):
                    waiting_for_response = True
                    riko_brain.respond(input_text)
                    current_response = "Thinking..."
                    input_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                elif event.unicode and len(input_text) < 200:
                    input_text += event.unicode

    screen.fill(DARK_BG)

    sprite_surf = riko_sprite.get_surface()
    sw, sh = sprite_surf.get_size()
    screen.blit(sprite_surf, ((WIDTH - sw) // 2, 50))

    title = font.render("Riko", True, ACCENT)
    screen.blit(title, ((WIDTH - title.get_width()) // 2, 15))

    y = 300
    for entry in history[-10:]:
        color = ACCENT if entry["from"] == "riko" else TEXT_COLOR
        text = entry["text"][:60] + ("..." if len(entry["text"]) > 60 else "")
        msg = font_small.render(text, True, color)
        screen.blit(msg, (50, y))
        y += 22

    pygame.draw.rect(screen, INPUT_BG, input_box, border_radius=8)
    if input_active:
        pygame.draw.rect(screen, ACCENT, input_box, 2, border_radius=8)
    else:
        pygame.draw.rect(screen, BORDER, input_box, 1, border_radius=8)

    if input_text:
        msg = font.render(input_text, True, TEXT_COLOR)
        screen.blit(msg, (input_box.x + 12, input_box.y + 10))
    else:
        placeholder = font.render("Say something...", True, (100, 100, 120))
        screen.blit(placeholder, (input_box.x + 12, input_box.y + 10))

    resp_msg = font_small.render(
        current_response[:70] + ("..." if len(current_response) > 70 else ""),
        True,
        ACCENT,
    )
    screen.blit(resp_msg, (50, 495))

    riko_sprite.update()

    if waiting_for_response:
        resp = riko_brain.check_response()
        if resp:
            current_response = resp
            history = riko_brain.get_history()
            waiting_for_response = False

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()
