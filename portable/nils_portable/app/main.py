import sys

import pygame

from riko_brain import NilsBrain
from riko_services import (
    OllamaVisionClient,
    NilsSettings,
    ScreenObserver,
    SystemTools,
    TTSManager,
    wrap_text,
)
from sprites import NilsSprite


pygame.init()

WIDTH, HEIGHT = 1220, 780
WINDOW_MARGIN = 20
PANEL_GAP = 20
SIDEBAR_WIDTH = 390
INSPECTOR_WIDTH = 220
INPUT_HEIGHT = 64
CARD_RADIUS = 0
CHAT_BOTTOM_GAP = 18

BG = (18, 18, 24)
SURFACE = (28, 28, 38)
SURFACE_ALT = (38, 40, 52)
TEXT = (235, 235, 245)
MUTED = (130, 135, 155)
ACCENT = (220, 60, 60)
ACCENT_SOFT = (180, 80, 100)
BORDER = (70, 70, 90)
USER_BUBBLE = (50, 80, 140)
NILS_BUBBLE = (180, 60, 60)
SUCCESS = (80, 180, 120)
WARNING = (220, 160, 60)


class ToggleButton:
    def __init__(self, rect, label):
        self.rect = pygame.Rect(rect)
        self.label = label

    def draw(self, surface, font, active=True):
        fill = SURFACE_ALT if active else (33, 33, 43)
        border = ACCENT if active else BORDER
        text_color = TEXT if active else MUTED
        pygame.draw.rect(surface, fill, self.rect)
        pygame.draw.rect(surface, border, self.rect, 2)
        label = font.render(self.label, True, text_color)
        surface.blit(
            label,
            (
                self.rect.centerx - label.get_width() // 2,
                self.rect.centery - label.get_height() // 2,
            ),
        )

    def hit(self, position):
        return self.rect.collidepoint(position)


def draw_card(surface, rect, fill=SURFACE, border=BORDER):
    pygame.draw.rect(surface, fill, rect, border_radius=CARD_RADIUS)
    pygame.draw.rect(surface, border, rect, 2, border_radius=CARD_RADIUS)


def draw_text_lines(surface, font, color, lines, start_x, start_y, line_gap=6):
    y = start_y
    for line in lines:
        rendered = font.render(line, True, color)
        surface.blit(rendered, (start_x, y))
        y += rendered.get_height() + line_gap
    return y


def draw_wrapped_block(
    surface,
    font,
    lines,
    start_x,
    start_y,
    max_width,
    default_color=TEXT,
    line_gap=6,
    paragraph_gap=10,
    color_map=None,
):
    y = start_y
    for line in lines:
        if not line:
            y += paragraph_gap
            continue
        color = default_color
        if color_map:
            for prefix, mapped in color_map.items():
                if line.startswith(prefix):
                    color = mapped
                    break
        wrapped_lines = wrap_text(line, font.size, max_width)
        for wrapped_line in wrapped_lines:
            rendered = font.render(wrapped_line, True, color)
            surface.blit(rendered, (start_x, y))
            y += rendered.get_height() + line_gap
    return y


def draw_chat_bubble(surface, font, small_font, entry, x, y, width):
    is_nils = entry.get("from") == "nils"
    bubble_color = NILS_BUBBLE if is_nils else USER_BUBBLE
    border_color = ACCENT if is_nils else (111, 150, 255)
    speaker = "Nils" if is_nils else "You"
    timestamp = entry.get("timestamp", "")[11:16] if entry.get("timestamp") else ""

    lines = wrap_text(entry.get("text", ""), font.size, width - 28)
    bubble_height = 22 + len(lines) * 28 + 16
    rect = pygame.Rect(x, y, width, bubble_height)
    pygame.draw.rect(surface, bubble_color, rect)
    pygame.draw.rect(surface, border_color, rect, 2)

    header = small_font.render(
        f"{speaker} {timestamp}".strip(),
        True,
        ACCENT_SOFT if is_nils else (191, 213, 255),
    )
    surface.blit(header, (x + 14, y + 10))
    draw_text_lines(surface, font, TEXT, lines, x + 14, y + 34, line_gap=4)
    return y + bubble_height + 14


def measure_chat_bubble(font, entry, width):
    lines = wrap_text(entry.get("text", ""), font.size, width - 28)
    bubble_height = 22 + len(lines) * 28 + 16
    return bubble_height + 14


def make_buttons(right_panel):
    button_x = right_panel.x + 16
    button_width = right_panel.width - 32
    return {
        "tts": ToggleButton((button_x, 112, button_width, 44), "Voice"),
        "screen": ToggleButton((button_x, 168, button_width, 44), "Screen"),
        "actions": ToggleButton((button_x, 224, button_width, 44), "Actions"),
        "voice_cycle": ToggleButton((button_x, 280, button_width, 44), "Change Voice"),
        "scan": ToggleButton((button_x, 336, button_width, 44), "Scan Screen"),
        "clear": ToggleButton((button_x, 392, button_width, 44), "Clear Chat"),
    }


def main():
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Nils Companion")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Menlo", 20)
    small_font = pygame.font.SysFont("Menlo", 14)
    title_font = pygame.font.SysFont("Menlo", 28, bold=True)
    big_font = pygame.font.SysFont("Menlo", 42, bold=True)

    settings = NilsSettings.load()
    system_tools = SystemTools(settings)
    tts_manager = TTSManager(settings)
    vision_client = OllamaVisionClient("http://localhost:11434", None)
    screen_observer = ScreenObserver(
        settings, system_tools, vision_client=vision_client
    )
    nils_brain = NilsBrain(
        settings=settings,
        system_tools=system_tools,
        screen_observer=screen_observer,
        tts_manager=tts_manager,
    )
    vision_client.model_name = nils_brain.vision_model
    screen_observer.vision_client = vision_client

    nils_sprite = NilsSprite("riko.png")
    history = nils_brain.get_history()
    left_panel = pygame.Rect(
        WINDOW_MARGIN, WINDOW_MARGIN, SIDEBAR_WIDTH, HEIGHT - (WINDOW_MARGIN * 2)
    )
    center_panel = pygame.Rect(
        left_panel.right + PANEL_GAP,
        WINDOW_MARGIN,
        WIDTH - (WINDOW_MARGIN * 2) - (PANEL_GAP * 2) - SIDEBAR_WIDTH - INSPECTOR_WIDTH,
        HEIGHT - (WINDOW_MARGIN * 2),
    )
    right_panel = pygame.Rect(
        center_panel.right + PANEL_GAP,
        WINDOW_MARGIN,
        INSPECTOR_WIDTH,
        HEIGHT - (WINDOW_MARGIN * 2),
    )
    buttons = make_buttons(right_panel)
    input_box = pygame.Rect(
        left_panel.x + 16,
        left_panel.bottom - INPUT_HEIGHT - 18,
        left_panel.width - 32,
        INPUT_HEIGHT,
    )
    chat_viewport = pygame.Rect(
        left_panel.x + 12,
        136,
        left_panel.width - 24,
        input_box.y - 136 - CHAT_BOTTOM_GAP,
    )
    input_text = ""
    input_active = True
    waiting_for_response = False
    status_text = "Nils is online."
    chat_scroll = 0

    def visible_history():
        pending_entries = list(history)
        if waiting_for_response:
            pending_entries.append(
                {"from": "nils", "text": "Nils is thinking...", "timestamp": ""}
            )
        return pending_entries

    def clamp_chat_scroll():
        nonlocal chat_scroll
        bubble_width = chat_viewport.width - 16
        total_height = 0
        for entry in visible_history():
            total_height += measure_chat_bubble(font, entry, bubble_width)
        max_scroll = max(0, total_height - chat_viewport.height + 8)
        chat_scroll = max(0, min(chat_scroll, max_scroll))

    def scroll_to_bottom():
        nonlocal chat_scroll
        bubble_width = chat_viewport.width - 16
        total_height = 0
        for entry in visible_history():
            total_height += measure_chat_bubble(font, entry, bubble_width)
        chat_scroll = max(0, total_height - chat_viewport.height + 8)

    scroll_to_bottom()

    def save_settings():
        settings.save()

    def queue_message(text):
        nonlocal input_text, waiting_for_response, status_text
        if not text.strip() or waiting_for_response:
            return
        waiting_for_response = True
        status_text = "Nils is thinking..."
        nils_brain.respond(text)
        input_text = ""
        scroll_to_bottom()

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.MOUSEBUTTONDOWN:
                input_active = input_box.collidepoint(event.pos)
                if chat_viewport.collidepoint(event.pos):
                    if event.button == 4:
                        chat_scroll = max(0, chat_scroll - 36)
                    elif event.button == 5:
                        chat_scroll += 36
                    clamp_chat_scroll()
                if buttons["tts"].hit(event.pos):
                    settings.tts_enabled = not settings.tts_enabled
                    status_text = (
                        "Voice enabled." if settings.tts_enabled else "Voice muted."
                    )
                    save_settings()
                elif buttons["screen"].hit(event.pos):
                    settings.screen_access_enabled = not settings.screen_access_enabled
                    status_text = (
                        "Screen access enabled."
                        if settings.screen_access_enabled
                        else "Screen access disabled."
                    )
                    save_settings()
                elif buttons["actions"].hit(event.pos):
                    settings.command_access_enabled = (
                        not settings.command_access_enabled
                    )
                    status_text = (
                        "Computer control enabled."
                        if settings.command_access_enabled
                        else "Computer control disabled."
                    )
                    save_settings()
                elif buttons["voice_cycle"].hit(event.pos):
                    new_voice = tts_manager.cycle_voice()
                    status_text = f"Voice switched to {new_voice}."
                    save_settings()
                elif buttons["scan"].hit(event.pos):
                    queue_message("/screen")
                elif buttons["clear"].hit(event.pos):
                    queue_message("/clear")

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F1:
                    queue_message("/screen")
                elif event.key == pygame.K_F2:
                    settings.tts_enabled = not settings.tts_enabled
                    status_text = (
                        "Voice enabled." if settings.tts_enabled else "Voice muted."
                    )
                    save_settings()
                elif event.key == pygame.K_F3:
                    settings.screen_access_enabled = not settings.screen_access_enabled
                    status_text = (
                        "Screen access enabled."
                        if settings.screen_access_enabled
                        else "Screen access disabled."
                    )
                    save_settings()
                elif event.key == pygame.K_F4:
                    settings.command_access_enabled = (
                        not settings.command_access_enabled
                    )
                    status_text = (
                        "Computer control enabled."
                        if settings.command_access_enabled
                        else "Computer control disabled."
                    )
                    save_settings()
                elif event.key == pygame.K_l and (
                    event.mod & pygame.KMOD_META or event.mod & pygame.KMOD_CTRL
                ):
                    queue_message("/clear")
                elif input_active:
                    if event.key == pygame.K_RETURN:
                        queue_message(input_text)
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    elif event.unicode and len(input_text) < 240:
                        input_text += event.unicode

        response = nils_brain.check_response()
        if response:
            history = nils_brain.get_history()
            waiting_for_response = False
            status_text = response
            scroll_to_bottom()
            if settings.tts_enabled:
                tts_manager.speak_async(response)

        nils_sprite.update()

        screen.fill(BG)

        draw_card(screen, left_panel)
        draw_card(screen, center_panel, fill=(18, 20, 30))
        draw_card(screen, right_panel)

        title = title_font.render("Nils Companion", True, TEXT)
        subtitle = small_font.render(
            "desktop companion / local voice / screen-aware", True, MUTED
        )
        screen.blit(title, (42, 34))
        screen.blit(subtitle, (42, 68))

        chat_header = small_font.render("Conversation", True, ACCENT)
        screen.blit(chat_header, (42, 110))

        draw_card(screen, chat_viewport, fill=(18, 19, 30), border=(32, 37, 58))
        bubble_width = chat_viewport.width - 16
        entries = visible_history()
        total_height = 0
        for entry in entries:
            total_height += measure_chat_bubble(font, entry, bubble_width)
        clamp_chat_scroll()
        chat_y = chat_viewport.y + 8 - chat_scroll
        clip_before = screen.get_clip()
        screen.set_clip(chat_viewport)
        for entry in entries:
            next_y = draw_chat_bubble(
                screen,
                font,
                small_font,
                entry,
                chat_viewport.x + 8,
                chat_y,
                bubble_width,
            )
            chat_y = next_y
        screen.set_clip(clip_before)

        if total_height > chat_viewport.height:
            track = pygame.Rect(
                chat_viewport.right - 8,
                chat_viewport.y + 12,
                4,
                chat_viewport.height - 24,
            )
            pygame.draw.rect(screen, (44, 48, 66), track)
            thumb_height = max(
                36, int(track.height * (chat_viewport.height / total_height))
            )
            travel = max(1, track.height - thumb_height)
            thumb_y = track.y + int(
                travel * (chat_scroll / max(1, total_height - chat_viewport.height))
            )
            thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_height)
            pygame.draw.rect(screen, ACCENT, thumb)

        draw_card(screen, input_box, fill=(26, 29, 43))
        input_border = ACCENT if input_active else BORDER
        pygame.draw.rect(screen, input_border, input_box, 2)
        if input_text:
            input_lines = wrap_text(input_text, font.size, input_box.width - 26)
            current_line = input_lines[-1]
            rendered = font.render(current_line, True, TEXT)
            screen.blit(rendered, (input_box.x + 14, input_box.y + 18))
        else:
            placeholder = font.render(
                "Say something or try /screen, /status, /open Safari, /shell pwd",
                True,
                MUTED,
            )
            screen.blit(placeholder, (input_box.x + 14, input_box.y + 18))

        name = big_font.render("Nils", True, ACCENT)
        screen.blit(name, (center_panel.centerx - name.get_width() // 2, 42))

        status_lines = wrap_text(status_text, small_font.size, center_panel.width - 52)
        draw_text_lines(
            screen, small_font, MUTED, status_lines, center_panel.x + 24, 92
        )

        sprite_surface = nils_sprite.get_surface()
        sprite_scale = min(1.15, 420 / max(sprite_surface.get_width(), 1))
        if sprite_scale != 1:
            sprite_surface = pygame.transform.smoothscale(
                sprite_surface,
                (
                    int(sprite_surface.get_width() * sprite_scale),
                    int(sprite_surface.get_height() * sprite_scale),
                ),
            )
        sprite_x = center_panel.centerx - sprite_surface.get_width() // 2
        sprite_y = 140
        screen.blit(sprite_surface, (sprite_x, sprite_y))

        tip_card = pygame.Rect(
            center_panel.x + 26, HEIGHT - 200, center_panel.width - 52, 124
        )
        draw_card(screen, tip_card, fill=SURFACE_ALT)
        tip_title = small_font.render("Quick shortcuts", True, ACCENT)
        screen.blit(tip_title, (tip_card.x + 16, tip_card.y + 14))
        shortcuts = [
            "Enter send, F1 screen scan, F2 voice toggle",
            "F3 screen access, F4 computer control",
            "Cmd/Ctrl+L clear chat",
        ]
        draw_text_lines(
            screen, small_font, TEXT, shortcuts, tip_card.x + 16, tip_card.y + 40
        )

        inspector_title_x = right_panel.x + 18
        inspector_title = title_font.render("Systems", True, TEXT)
        screen.blit(inspector_title, (inspector_title_x, right_panel.y + 14))
        inspector_subtitle_lines = wrap_text(
            "real controls, not fake demo fluff",
            small_font.size,
            right_panel.width - 36,
        )
        draw_text_lines(
            screen,
            small_font,
            MUTED,
            inspector_subtitle_lines,
            inspector_title_x,
            right_panel.y + 48,
            line_gap=2,
        )

        buttons["tts"].draw(screen, small_font, settings.tts_enabled)
        buttons["screen"].draw(screen, small_font, settings.screen_access_enabled)
        buttons["actions"].draw(screen, small_font, settings.command_access_enabled)
        buttons["voice_cycle"].draw(screen, small_font, True)
        buttons["scan"].draw(screen, small_font, True)
        buttons["clear"].draw(screen, small_font, True)

        voice_clone_status = (
            "clone ready" if tts_manager.has_voice_clone() else "default voice"
        )
        brain_status = nils_brain.last_status
        if nils_brain.last_ollama_error:
            brain_status = f"{brain_status}: {nils_brain.last_ollama_error[:48]}"
        voice_status = [
            f"Voice engine: {tts_manager.status}",
            f"Voice mode: {voice_clone_status}",
            f"Brain mode: {brain_status}",
            f"Vision model: {nils_brain.vision_model or 'not found'}",
            "",
            "Voice clone commands:",
            "/clone voice.wav",
            "(set voice from audio)",
            "",
            "Slash commands:",
            "/screen",
            "/status",
            "/clipboard",
            "/open Safari",
            "/shell pwd",
        ]
        color_map = {
            "Voice engine:": SUCCESS
            if "ready" in tts_manager.status.lower()
            else WARNING,
            "Voice mode:": SUCCESS
            if "clone" in tts_manager.status.lower()
            else WARNING,
            "Brain mode": SUCCESS
            if "ollama live" in nils_brain.last_status.lower()
            else WARNING,
        }

        inspector_content = pygame.Rect(
            right_panel.x + 18,
            buttons["clear"].rect.bottom + 28,
            right_panel.width - 36,
            right_panel.bottom - buttons["clear"].rect.bottom - 44,
        )
        clip_before = screen.get_clip()
        screen.set_clip(inspector_content)
        draw_wrapped_block(
            screen,
            small_font,
            voice_status,
            inspector_content.x,
            inspector_content.y,
            inspector_content.width,
            color_map=color_map,
        )
        screen.set_clip(clip_before)

        pygame.display.flip()
        clock.tick(60)

    settings.save()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
