import base64
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import requests

try:
    from qwen_tts import Qwen3TTSModel
    import soundfile as sf

    QWEN_AVAILABLE = True
except ImportError:
    QWEN_AVAILABLE = False
    Qwen3TTSModel = None
    sf = None


DEFAULT_VOICE = "default"
VOICE_CLONE_FILE = "voice_clone.wav"
VOICE_CLONE_TEXT_FILE = "voice_clone.txt"
DEFAULT_VOICE_REF_FILE = "nils-ref.wav"
DEFAULT_VOICE_REF_TEXT_FILE = "nils-ref.txt"
DEFAULT_MLX_STT_MODEL = "mlx-community/whisper-tiny"
DEFAULT_FASTER_WHISPER_MODEL = "tiny.en"
STT_TIMEOUT_SECONDS = 180
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
class NilsSettings:
    tts_enabled: bool = True
    screen_access_enabled: bool = True
    command_access_enabled: bool = True
    voice: str = DEFAULT_VOICE
    tts_speed: float = 1.0

    @classmethod
    def load(cls, path: str = "nils_config.json"):
        settings_path = Path(path)
        if not settings_path.exists():
            return cls()
        try:
            with settings_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(**{**asdict(cls()), **payload})

    def save(self, path: str = "nils_config.json"):
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
        settings: NilsSettings,
        model_dir: str = "models/tts",
        tmp_dir: str = "tmp",
        default_ref_audio: str = DEFAULT_VOICE_REF_FILE,
        default_ref_text: str = DEFAULT_VOICE_REF_TEXT_FILE,
    ):
        self.settings = settings
        self.model_dir = Path(model_dir)
        self.tmp_dir = Path(tmp_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.voice_clone_path = self.model_dir / "voice_clone.wav"
        self.voice_clone_text_path = self.model_dir / VOICE_CLONE_TEXT_FILE
        self.default_ref_audio_path = Path(default_ref_audio)
        self.default_ref_text_path = Path(default_ref_text)
        self.status = "Voice offline"
        self.last_error = ""
        self._engine = None
        self._engine_lock = threading.Lock()
        self._speak_lock = threading.Lock()
        self._playback_channel = None
        self._prime_default_clone()

    def is_ready(self) -> bool:
        return QWEN_AVAILABLE

    def has_voice_clone(self) -> bool:
        return self.voice_clone_path.exists()

    def available_voices(self) -> list[str]:
        return [DEFAULT_VOICE, "clone"]

    def cycle_voice(self) -> str:
        voices = self.available_voices()
        if self.settings.voice not in voices:
            self.settings.voice = voices[0]
        else:
            index = (voices.index(self.settings.voice) + 1) % len(voices)
            self.settings.voice = voices[index]
        self.status = f"Voice set to {self.settings.voice}"
        return self.settings.voice

    def set_voice_clone(self, audio_path: str) -> str:
        src = Path(audio_path)
        if not src.exists():
            return f"Audio file not found: {audio_path}"
        try:
            shutil.copy(src, self.voice_clone_path)
            transcript = self._read_transcript_file(src.with_suffix(".txt"))
            transcript_source = "sidecar"
            if not transcript:
                transcript = self._auto_transcribe_reference(src)
                transcript_source = "auto"
            if transcript:
                self.voice_clone_text_path.write_text(transcript, encoding="utf-8")
                mode = "ICL"
                if transcript_source == "auto":
                    self.status = (
                        "Voice cloned from audio file (ICL mode, auto-transcribed)"
                    )
                    return self.status
            else:
                if self.voice_clone_text_path.exists():
                    self.voice_clone_text_path.unlink()
                mode = "x-vector"
            self.status = f"Voice cloned from audio file ({mode} mode)"
            return self.status
        except Exception as exc:
            return f"Failed to set voice clone: {exc}"

    def ensure_ready(self) -> tuple[bool, str]:
        if not QWEN_AVAILABLE:
            self.status = "Install qwen-tts to enable voice"
            return False, self.status

        try:
            self._load_engine()
        except Exception as exc:
            self.last_error = str(exc)
            self.status = f"TTS unavailable: {exc}"
            return False, self.status

        self.status = f"Qwen TTS ready ({self._status_voice_label()})"
        return True, self.status

    def _load_engine(self):
        with self._engine_lock:
            if self._engine is None:
                try:
                    import torch

                    self._engine = Qwen3TTSModel.from_pretrained(
                        "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
                        device_map="auto",
                    )
                except Exception as exc:
                    self.last_error = str(exc)
                    raise
        return self._engine

    def _prime_default_clone(self):
        if self.voice_clone_path.exists() or not self.default_ref_audio_path.exists():
            return
        try:
            shutil.copy(self.default_ref_audio_path, self.voice_clone_path)
            default_transcript = self._read_transcript_file(self.default_ref_text_path)
            if default_transcript:
                self.voice_clone_text_path.write_text(
                    default_transcript,
                    encoding="utf-8",
                )
        except OSError:
            pass

    def _read_transcript_file(self, path: Path) -> str | None:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return text or None

    def _auto_transcribe_reference(self, audio_path: Path) -> str | None:
        wav_path = self._prepare_transcription_audio(audio_path)
        for transcriber in (
            self._transcribe_with_faster_whisper,
            self._transcribe_with_mlx_whisper,
            self._transcribe_with_openai_whisper,
        ):
            transcript = transcriber(wav_path)
            if transcript:
                return transcript
        return None

    def _find_ffmpeg_executable(self) -> str | None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return None

    def _prepare_transcription_audio(self, audio_path: Path) -> Path:
        ffmpeg = self._find_ffmpeg_executable()
        if not ffmpeg:
            return audio_path

        prepared_path = self.tmp_dir / "voice_clone_input_16k.wav"
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(audio_path),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    str(prepared_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            return prepared_path
        except (OSError, subprocess.SubprocessError):
            return audio_path

    def _transcribe_with_faster_whisper(self, audio_path: Path) -> str | None:
        python_executable = sys.executable
        if not python_executable:
            return None
        command = [
            python_executable,
            "-c",
            (
                "import json, sys\n"
                "try:\n"
                "    from faster_whisper import WhisperModel\n"
                "except Exception:\n"
                "    raise SystemExit(2)\n"
                "device = 'cuda' if sys.platform.startswith('win') else 'auto'\n"
                "model = WhisperModel(sys.argv[2], device=device, compute_type='float16' if device == 'cuda' else 'int8')\n"
                "segments, _ = model.transcribe(sys.argv[1], language='en')\n"
                "text = ' '.join(segment.text.strip() for segment in segments).strip()\n"
                "print(json.dumps({'text': text}))\n"
            ),
            str(audio_path),
            DEFAULT_FASTER_WHISPER_MODEL,
        ]
        return self._run_transcriber_command(command)

    def _transcribe_with_mlx_whisper(self, audio_path: Path) -> str | None:
        python_executable = sys.executable
        if not python_executable:
            return None
        command = [
            python_executable,
            "-c",
            (
                "import json, sys\n"
                "try:\n"
                "    import mlx_whisper\n"
                "except Exception:\n"
                "    raise SystemExit(2)\n"
                "result = mlx_whisper.transcribe(\n"
                "    sys.argv[1],\n"
                "    path_or_hf_repo=sys.argv[2],\n"
                "    language='en',\n"
                ")\n"
                "text = (result or {}).get('text', '').strip()\n"
                "print(json.dumps({'text': text}))\n"
            ),
            str(audio_path),
            DEFAULT_MLX_STT_MODEL,
        ]
        return self._run_transcriber_command(command)

    def _transcribe_with_openai_whisper(self, audio_path: Path) -> str | None:
        python_executable = sys.executable
        if not python_executable:
            return None
        env = os.environ.copy()
        ffmpeg = self._find_ffmpeg_executable()
        if ffmpeg:
            env["PATH"] = f"{Path(ffmpeg).parent}{os.pathsep}{env.get('PATH', '')}"
        command = [
            python_executable,
            "-m",
            "whisper",
            str(audio_path),
            "--model",
            "tiny.en",
            "--language",
            "en",
            "--task",
            "transcribe",
            "--output_format",
            "txt",
            "--output_dir",
            str(self.tmp_dir),
        ]
        transcript = self._run_transcriber_command(
            command,
            parse_json=False,
            env=env,
        )
        if transcript:
            return transcript
        generated = self.tmp_dir / f"{audio_path.stem}.txt"
        return self._read_transcript_file(generated)

    def _run_transcriber_command(
        self,
        command: list[str],
        parse_json: bool = True,
        env: dict[str, str] | None = None,
    ) -> str | None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                env=env,
                text=True,
                timeout=STT_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if result.returncode not in (0,):
            return None

        output = (result.stdout or "").strip()
        if not output:
            return None
        if not parse_json:
            return output
        try:
            payload = json.loads(output.splitlines()[-1])
        except json.JSONDecodeError:
            return None
        text = str(payload.get("text", "")).strip()
        return text or None

    def _normalize_generated_audio(self, wavs):
        audio = wavs
        if hasattr(audio, "tolist"):
            audio = audio.tolist()

        if not isinstance(audio, (list, tuple)):
            raise ValueError(
                f"Unexpected audio payload type from TTS: {type(audio).__name__}"
            )
        if not audio:
            raise ValueError("TTS returned no audio samples.")

        first = audio[0]
        if hasattr(first, "tolist"):
            first = first.tolist()

        # Qwen returns a batch of generated waveforms. Use the first sample.
        if isinstance(first, (list, tuple)):
            audio = first
            if not audio:
                raise ValueError("TTS returned no audio samples.")
            first = audio[0]
            if hasattr(first, "tolist"):
                first = first.tolist()

        if isinstance(first, (list, tuple)):
            if not first:
                raise ValueError("TTS returned an empty audio buffer.")
            # soundfile expects frames x channels; transpose channels-first data.
            if len(audio) <= 8 and len(audio) < len(first):
                return [list(frame) for frame in zip(*audio)]
            return [list(frame) for frame in audio]

        return list(audio)

    def _resolve_voice_reference(self) -> tuple[str | None, str | None]:
        if self.settings.voice == "clone" and self.voice_clone_path.exists():
            return str(self.voice_clone_path), self._read_transcript_file(
                self.voice_clone_text_path
            )
        if self.default_ref_audio_path.exists():
            return str(self.default_ref_audio_path), self._read_transcript_file(
                self.default_ref_text_path
            )
        if self.voice_clone_path.exists():
            return str(self.voice_clone_path), self._read_transcript_file(
                self.voice_clone_text_path
            )
        return None, None

    def _status_voice_label(self) -> str:
        if self.settings.voice == "clone" and self.voice_clone_path.exists():
            transcript = self._read_transcript_file(self.voice_clone_text_path)
            return "clone selected (ICL)" if transcript else "clone selected (x-vector)"
        if self.default_ref_audio_path.exists():
            transcript = self._read_transcript_file(self.default_ref_text_path)
            return (
                "default selected (ICL)"
                if transcript
                else "default selected (x-vector)"
            )
        if self.voice_clone_path.exists():
            transcript = self._read_transcript_file(self.voice_clone_text_path)
            return "clone fallback (ICL)" if transcript else "clone fallback (x-vector)"
        return "no reference"

    def speak_async(self, text: str):
        if not self.settings.tts_enabled or not text.strip():
            return
        worker = threading.Thread(target=self._speak, args=(text,), daemon=True)
        worker.start()

    def _split_text_into_chunks(
        self,
        text: str,
        target_len: int = 140,
        max_len: int = 200,
    ) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []

        parts = re.findall(r"[^,.;!?]+(?:[,.;!?]+|$)", normalized)
        chunks: list[str] = []
        current = ""

        for part in parts:
            segment = " ".join(part.split()).strip()
            if not segment:
                continue

            candidate = f"{current} {segment}".strip() if current else segment
            if current and len(candidate) > max_len:
                chunks.append(current.strip())
                current = ""
                candidate = segment

            if len(candidate) > max_len:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._split_long_segment(segment, max_len))
                continue

            current = candidate
            if len(current) >= target_len and re.search(r"[,.!?]\s*$", current):
                chunks.append(current.strip())
                current = ""

        if current:
            chunks.append(current.strip())

        return chunks or [normalized[:max_len]]

    def _split_long_segment(self, segment: str, max_len: int) -> list[str]:
        words = segment.split()
        if not words:
            return []

        pieces: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if current and len(candidate) > max_len:
                pieces.append(current.strip())
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current.strip())
        return pieces

    def _generate_chunk_audio(self, chunk_text: str, engine, ref_audio: str, ref_text: str | None):
        wavs, sr = engine.generate_voice_clone(
            chunk_text,
            ref_audio=ref_audio,
            ref_text=ref_text,
            x_vector_only_mode=not bool(ref_text),
            non_streaming_mode=True,
        )
        audio = self._normalize_generated_audio(wavs)
        return audio, sr

    def _chunk_path(self, index: int) -> Path:
        token = uuid.uuid4().hex[:8]
        return self.tmp_dir / f"nils_tts_chunk_{index}_{token}.wav"

    def _write_chunk_file(self, audio, sr: int, index: int) -> Path:
        audio_path = self._chunk_path(index)
        sf.write(audio_path, audio, sr)
        return audio_path

    def _load_sound(self, pygame, path: Path):
        sound = pygame.mixer.Sound(str(path))
        try:
            path.unlink()
        except OSError:
            pass
        return sound

    def _stop_current_playback(self, pygame):
        if self._playback_channel and self._playback_channel.get_busy():
            self._playback_channel.stop()
        elif pygame.mixer.get_init():
            pygame.mixer.stop()

    def _ensure_playback_channel(self, pygame):
        if self._playback_channel is None:
            self._playback_channel = pygame.mixer.find_channel(True)
        return self._playback_channel

    def _speak_streaming(self, text: str):
        try:
            import pygame
        except ImportError:
            self._speak(text)
            return

        ready, message = self.ensure_ready()
        if not ready:
            self.last_error = message
            return

        engine = self._load_engine()
        ref_audio, ref_text = self._resolve_voice_reference()
        if not ref_audio:
            self.last_error = "No voice reference audio is configured."
            return

        chunks = self._split_text_into_chunks(text)
        if not chunks:
            return

        with self._speak_lock:
            try:
                first_audio, sr = self._generate_chunk_audio(
                    chunks[0], engine, ref_audio, ref_text
                )
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=sr)
                self._stop_current_playback(pygame)
                channel = self._ensure_playback_channel(pygame)

                ready_chunks: dict[int, object] = {}
                chunk_queue: queue.Queue = queue.Queue()
                producer_error: list[Exception] = []
                producer_done = threading.Event()

                first_path = self._write_chunk_file(first_audio, sr, 0)
                ready_chunks[0] = self._load_sound(pygame, first_path)

                def producer():
                    try:
                        for index, chunk_text in enumerate(chunks[1:], start=1):
                            audio, chunk_sr = self._generate_chunk_audio(
                                chunk_text,
                                engine,
                                ref_audio,
                                ref_text,
                            )
                            chunk_path = self._write_chunk_file(audio, chunk_sr, index)
                            chunk_queue.put((index, chunk_path, chunk_sr))
                    except Exception as exc:
                        producer_error.append(exc)
                    finally:
                        producer_done.set()

                threading.Thread(target=producer, daemon=True).start()

                current_index = 0
                next_index = 1
                current_sound = ready_chunks.pop(0)
                queued_index = None
                queued_sound = None
                channel.play(current_sound)

                while True:
                    while True:
                        try:
                            index, chunk_path, chunk_sr = chunk_queue.get_nowait()
                        except queue.Empty:
                            break
                        if chunk_sr != sr:
                            raise ValueError(
                                f"Inconsistent TTS sample rate: expected {sr}, got {chunk_sr}"
                            )
                        ready_chunks[index] = self._load_sound(pygame, chunk_path)

                    if producer_error:
                        raise producer_error[0]

                    if queued_sound is None and next_index in ready_chunks:
                        queued_sound = ready_chunks.pop(next_index)
                        channel.queue(queued_sound)
                        queued_index = next_index
                        next_index += 1

                    if queued_sound is not None and channel.get_queue() is None:
                        current_index = queued_index
                        current_sound = queued_sound
                        queued_sound = None
                        queued_index = None

                    if not channel.get_busy():
                        if queued_sound is None and next_index in ready_chunks:
                            current_sound = ready_chunks.pop(next_index)
                            current_index = next_index
                            next_index += 1
                            channel.play(current_sound)
                            continue
                        if producer_done.is_set() and next_index >= len(chunks) and not ready_chunks:
                            break

                    time.sleep(0.02)

                self.status = f"Speaking ({self._status_voice_label()})"
            except Exception as exc:
                self.last_error = str(exc)
                self.status = f"Voice error: {exc}"

    def _speak(self, text: str):
        try:
            import pygame
        except ImportError:
            self._speak_legacy(text)
            return

        try:
            self._speak_streaming(text)
        except Exception as exc:
            self.last_error = str(exc)
            try:
                self._speak_legacy(text)
            except Exception as exc2:
                self.last_error = str(exc2)
                self.status = f"Voice error: {exc2}"

    def _speak_legacy(self, text: str):
        ready, message = self.ensure_ready()
        if not ready:
            self.last_error = message
            return
        try:
            import pygame

            engine = self._load_engine()
            ref_audio, ref_text = self._resolve_voice_reference()
            if not ref_audio:
                raise ValueError("No voice reference audio is configured.")
            wavs, sr = engine.generate_voice_clone(
                text[:500],
                ref_audio=ref_audio,
                ref_text=ref_text,
                x_vector_only_mode=not bool(ref_text),
                non_streaming_mode=True,
            )
            audio = self._normalize_generated_audio(wavs)
            audio_path = self.tmp_dir / "nils_tts.wav"
            sf.write(audio_path, audio, sr)
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=sr)
            pygame.mixer.music.stop()
            pygame.mixer.music.load(str(audio_path))
            pygame.mixer.music.play()
            self.status = f"Speaking ({self._status_voice_label()})"
        except Exception as exc:
            self.last_error = str(exc)
            self.status = f"Voice error: {exc}"


class SystemTools:
    def __init__(self, settings: NilsSettings):
        self.settings = settings
        self.platform = platform.system().lower()

    def clipboard_text(self) -> str:
        try:
            if self.platform == "windows":
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=True,
                )
                return result.stdout.strip() or "Clipboard is empty."
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
            if self.platform == "windows":
                if re.match(r"^https?://", cleaned):
                    os.startfile(cleaned)
                    return f"Opened {cleaned}"

                path = Path(cleaned).expanduser()
                if path.exists():
                    os.startfile(str(path))
                    return f"Opened {path}"

                subprocess.run(
                    ["cmd", "/c", "start", "", cleaned],
                    check=True,
                    timeout=5,
                )
                return f"Opened {cleaned}"

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
        if self.platform == "windows":
            return "Frontmost window lookup unavailable on Windows"
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
        if self.platform == "windows":
            return "Battery status unavailable on Windows"
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
        settings: NilsSettings,
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
        if platform.system().lower() != "darwin":
            try:
                from PIL import ImageGrab

                grabbed = ImageGrab.grab()
                grabbed.save(image_path)
                return str(image_path)
            except Exception as exc:
                raise RuntimeError(f"screen capture failed: {exc}") from exc
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
