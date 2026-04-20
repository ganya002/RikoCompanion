import pygame
import os


class RikoSprite:
    def __init__(self, image_path="riko.png", gif_path="animation.gif"):
        self.png_scale = 3
        self.bounce_offset = 0
        self.heart_eyes = False
        self.heart_eyes_timer = 0
        self.frames = []
        self.frame_index = 0
        self.frame_speed = 6
        self.frame_timer = 0
        self.base_image = None
        self.gif_loaded = False

        if os.path.exists(gif_path):
            try:
                from PIL import Image

                gif = Image.open(gif_path)
                count = 0
                while True:
                    try:
                        frame = gif.copy().convert("RGBA")
                        pygame_image = pygame.image.fromstring(
                            frame.tobytes(), frame.size, frame.mode
                        )
                        self.frames.append(pygame_image)
                        count += 1
                        gif.seek(gif.tell() + 1)
                    except EOFError:
                        break
                if self.frames:
                    self.gif_loaded = True
                    print(f"Loaded GIF: {len(self.frames)} frames")
            except Exception as e:
                print(f"GIF error: {e}")

        if not self.gif_loaded and os.path.exists(image_path):
            self.base_image = pygame.image.load(image_path).convert_alpha()

    def set_mood(self, mood):
        pass

    def trigger_heart_eyes(self):
        self.heart_eyes = True
        self.heart_eyes_timer = 120

    def update(self):
        self.frame_timer += 1
        if self.gif_loaded and self.frame_timer >= self.frame_speed:
            self.frame_timer = 0
            self.frame_index = (self.frame_index + 1) % len(self.frames)

        if self.heart_eyes:
            self.heart_eyes_timer -= 1
            if self.heart_eyes_timer <= 0:
                self.heart_eyes = False

    def get_surface(self):
        if self.gif_loaded and self.frames:
            frame = self.frames[self.frame_index]
            w = frame.get_width()
            h = frame.get_height()
            return frame
        elif self.base_image:
            w = self.base_image.get_width() * self.png_scale
            h = self.base_image.get_height() * self.png_scale
            return pygame.transform.scale(self.base_image, (w, h))
        else:
            return pygame.Surface((256, 384), pygame.SRCALPHA)

    def _create_heart(self, scale):
        s = pygame.Surface((20 * scale, 20 * scale), pygame.SRCALPHA)
        c = (255, 100, 150)
        for x in range(20):
            for y in range(20):
                dx, dy = x - 10, y - 10
                if ((dx + dy) ** 2 + (dx - dy) ** 2) ** 0.5 < 9:
                    s.set_at((x, y), c)
        return s
