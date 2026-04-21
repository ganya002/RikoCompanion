import base64
import json
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import requests

try:
    from kokoro_onnx import Kokoro
    import soundfile as sf

    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    Kokoro = None
    sf = None


KOKORO_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.int8.onnx"
)
KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/voices-v1.0.bin"
)
DEFAULT_VOICE = "af_heart"
PREFERRED_VOICES = [
    "af_heart",
    "af_bella",
    "af_nova",
    "af_sarah",
    "af_jessica",
    "bf_emma",
]
BLOCKED_SHELL_PATTERNS = [
    r"rm\s+-rf\s+/$",
    r"rm\s+-rf\s+--no-preserve-root\s+/$",
    r"mkfs",
    r"diskutil\s+erase",
    r":\(\)\s*\{\s*:\|:\&\s*\};:",
    r"\bshutdown\b",
    r"\breboot\b",
]


@dataclass
class RikoSettings:
    tts_enabled: bool = True
    screen_access_enabled: bool = True
    command_access_enabled: bool = True
    voice: str = DEFAULT_VOICE
    tts_speed: float = 1.0

    @classmethod
    def load(cls, path: str = "riko_config.json"):
        settings_path = Path(path)
        if not settings_path.exists():
            return cls()
        try:
            with settings_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(**{**asdict(cls()), **payload})

    def save(self, path: str = "riko_config.json"):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(asdict(self), handle, indent=2)


class OllamaVisionClient:
    def __init__(self, base_url: str, model_name: str | None):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    @property
    def enabled(self) -> bool:
        return bool(self.model_name)

    def describe_image(
        self,
        image_path: str,
        prompt: str,
        extra_context: str = "",
        timeout: int = 60,
    ) -> str | None:
        if not self.model_name or not os.path.exists(image_path):
            return None

        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("utf-8")

        composed_prompt = prompt
        if extra_context:
            composed_prompt = f"{prompt}\n\nLocal metadata:\n{extra_context}"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model_name,
                    "prompt": composed_prompt,
                    "images": [encoded],
                    "stream": False,
                    "options": {"temperature": 0.35, "top_p": 0.9},
                },
                timeout=timeout,
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip() or None
        except requests.RequestException:
            return None
        return None


class TTSManager:
    def __init__(
        self,
        settings: RikoSettings,
        model_dir: str = "models/tts",
        tmp_dir: str = "tmp",
    ):
        self.settings = settings
        self.model_dir = Path(model_dir)
        self.tmp_dir = Path(tmp_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "kokoro-v1.0.int8.onnx"
        self.voices_path = self.model_dir / "voices-v1.0.bin"
        self.status = "Voice offline"
        self.last_error = ""
        self._engine = None
        self._engine_lock = threading.Lock()
        self._speak_lock = threading.Lock()
        self._download_lock = threading.Lock()

    def is_ready(self) -> bool:
        return KOKORO_AVAILABLE and self.model_path.exists() and self.voices_path.exists()

    def available_voices(self) -> list[str]:
        return PREFERRED_VOICES

    def cycle_voice(self) -> str:
        voices = self.available_voices()
        if self.settings.voice not in voices:
            self.settings.voice = voices[0]
        else:
            index = (voices.index(self.settings.voice) + 1) % len(voices)
            self.settings.voice = voices[index]
        self.status = f"Voice set to {self.settings.voice}"
        return self.settings.voice

    def ensure_ready(self) -> tuple[bool, str]:
        if not KOKORO_AVAILABLE:
            self.status = "Install kokoro-onnx and soundfile to enable voice"
            return False, self.status

        if not self.model_path.exists() or not self.voices_path.exists():
            downloaded, message = self._download_models()
            if not downloaded:
                self.status = message
                return False, message

        try:
            self._load_engine()
        except Exception as exc:  # pragma: no cover - hardware/runtime dependent
            self.last_error = str(exc)
            self.status = f"TTS unavailable: {exc}"
            return False, self.status

        self.status = f"Kokoro ready ({self.settings.voice})"
        return True, self.status

    def _download_models(self) -> tuple[bool, str]:
        with self._download_lock:
            if self.model_path.exists() and self.voices_path.exists():
                return True, "Models ready"
            try:
                self._download_file(KOKORO_MODEL_URL, self.model_path)
                self._download_file(KOKORO_VOICES_URL, self.voices_path)
            except requests.RequestException as exc:
                return False, f"Couldn't download Kokoro models: {exc}"
        return True, "Downloaded Kokoro voice files"

    @staticmethod
    def _download_file(url: str, destination: Path):
        response = requests.get(url, stream=True, timeout=90)
        response.raise_for_status()
        tmp_path = destination.with_suffix(destination.suffix + ".part")
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    handle.write(chunk)
        tmp_path.replace(destination)

    def _load_engine(self):
        with self._engine_lock:
            if self._engine is None:
                self._engine = Kokoro(
                    str(self.model_path),
                    str(self.voices_path),
                )
        return self._engine

    def speak_async(self, text: str):
        if not self.settings.tts_enabled or not text.strip():
            return
        worker = threading.Thread(target=self._speak, args=(text,), daemon=True)
        worker.start()

    def _speak(self, text: str):  # pragma: no cover - hardware/audio dependent
        with self._speak_lock:
            ready, message = self.ensure_ready()
            if not ready:
                self.last_error = message
                return
            try:
                import pygame

                engine = self._load_engine()
                audio, sample_rate = engine.create(
                    text=text[:500],
                    voice=self.settings.voice,
                    speed=self.settings.tts_speed,
                    lang="en-us",
                )
                audio_path = self.tmp_dir / "riko_tts.wav"
                sf.write(audio_path, audio, sample_rate)
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=sample_rate)
                pygame.mixer.music.stop()
                pygame.mixer.music.load(str(audio_path))
                pygame.mixer.music.play()
                self.status = f"Speaking with {self.settings.voice}"
            except Exception as exc:
                self.last_error = str(exc)
                self.status = f"Voice error: {exc}"


class SystemTools:
    def __init__(self, settings: RikoSettings):
        self.settings = settings

    def clipboard_text(self) -> str:
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            return result.stdout.strip() or "Clipboard is empty."
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return "Couldn't read the clipboard."

    def open_target(self, target: str) -> str:
        if not self.settings.command_access_enabled:
            return "Computer control is disabled."

        cleaned = target.strip()
        if not cleaned:
            return "Tell me what to open."

        try:
            if re.match(r"^https?://", cleaned):
                subprocess.run(["open", cleaned], check=True, timeout=5)
                return f"Opened {cleaned}"

            path = Path(cleaned).expanduser()
            if path.exists():
                subprocess.run(["open", str(path)], check=True, timeout=5)
                return f"Opened {path}"

            subprocess.run(["open", "-a", cleaned], check=True, timeout=5)
            return f"Opened app {cleaned}"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return f"Couldn't open {cleaned}"

    def run_shell(self, command: str) -> str:
        if not self.settings.command_access_enabled:
            return "Computer control is disabled."
        stripped = command.strip()
        if not stripped:
            return "Give me a shell command after /shell."
        if self._is_blocked_command(stripped):
            return "I'm not running that command."

        try:
            result = subprocess.run(
                stripped,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except subprocess.TimeoutExpired:
            return "Command timed out after 20s."

        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        output = output[:1200]
        if result.returncode == 0:
            return f"Exit 0\n{output}"
        return f"Exit {result.returncode}\n{output}"

    @staticmethod
    def _is_blocked_command(command: str) -> bool:
        lowered = command.strip().lower()
        return any(re.search(pattern, lowered) for pattern in BLOCKED_SHELL_PATTERNS)

    def get_frontmost_context(self) -> str:
        script = """
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            try
                set windowName to name of front window of frontApp
            on error
                set windowName to ""
            end try
        end tell
        return appName & "||" & windowName
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=4,
                check=True,
            )
            app_name, _, window_name = result.stdout.strip().partition("||")
            if window_name:
                return f"{app_name} - {window_name}"
            return app_name or "Unknown app"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return "Screen context unavailable"

    def battery_status(self) -> str:
        try:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                timeout=4,
                check=True,
            )
            match = re.search(r"(\d+%);", result.stdout)
            source = "charging" if "AC Power" in result.stdout else "battery"
            if match:
                return f"{match.group(1)} on {source}"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        return "Battery status unavailable"

    def quick_status(self) -> str:
        return (
            f"Battery: {self.battery_status()}\n"
            f"Frontmost: {self.get_frontmost_context()}"
        )


class ScreenObserver:
    def __init__(
        self,
        settings: RikoSettings,
        system_tools: SystemTools,
        vision_client: OllamaVisionClient | None = None,
        cache_dir: str = "tmp",
    ):
        self.settings = settings
        self.system_tools = system_tools
        self.vision_client = vision_client
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def capture_screen(self) -> str:
        image_path = self.cache_dir / "latest_screen.png"
        try:
            subprocess.run(
                ["screencapture", "-x", str(image_path)],
                check=True,
                timeout=8,
                capture_output=True,
                text=True,
            )
            return str(image_path)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            try:
                from PIL import ImageGrab

                grabbed = ImageGrab.grab()
                grabbed.save(image_path)
                return str(image_path)
            except Exception as exc:
                raise RuntimeError(f"screen capture failed: {exc}") from exc

    def describe_screen(self) -> str:
        if not self.settings.screen_access_enabled:
            return "Screen access is disabled."

        try:
            image_path = self.capture_screen()
        except Exception as exc:
            return f"I couldn't capture the screen. {exc}"

        metadata = self.system_tools.get_frontmost_context()
        if self.vision_client and self.vision_client.enabled:
            prompt = (
                "Describe what is visible on screen in a few sentences. "
                "Focus on the active app, the layout, and anything that stands out."
            )
            described = self.vision_client.describe_image(
                image_path=image_path,
                prompt=prompt,
                extra_context=f"Frontmost window: {metadata}",
            )
            if described:
                return described

        return (
            "I grabbed the screen, but there's no local vision model ready. "
            f"Frontmost window: {metadata}"
        )


def wrap_text(
    text: str,
    font_measure: Callable[[str], tuple[int, int]],
    max_width: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font_measure(candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
