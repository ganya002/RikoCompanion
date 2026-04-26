import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import riko_services
from riko_services import NilsSettings, SystemTools, TTSManager, wrap_text


class NilsServicesTests(unittest.TestCase):
    def test_wrap_text_keeps_words_under_width(self):
        lines = wrap_text(
            "Riko can actually speak now",
            lambda text: (len(text) * 8, 10),
            80,
        )
        self.assertGreater(len(lines), 1)
        self.assertEqual(" ".join(lines), "Riko can actually speak now")

    def test_blocked_shell_patterns_reject_dangerous_commands(self):
        self.assertTrue(SystemTools._is_blocked_command("rm -rf /"))
        self.assertTrue(SystemTools._is_blocked_command("shutdown now"))
        self.assertFalse(SystemTools._is_blocked_command("pwd"))

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "config.json"
            settings = NilsSettings(
                tts_enabled=False,
                screen_access_enabled=False,
                command_access_enabled=True,
                voice="af_bella",
                tts_speed=1.1,
            )
            settings.save(str(path))
            loaded = NilsSettings.load(str(path))
            self.assertEqual(loaded.voice, "af_bella")
            self.assertFalse(loaded.tts_enabled)
            self.assertAlmostEqual(loaded.tts_speed, 1.1)

    def test_set_voice_clone_copies_sidecar_transcript(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            audio = tmp_path / "sample.wav"
            transcript = tmp_path / "sample.txt"
            audio.write_bytes(b"fake wav")
            transcript.write_text("hello from the ref clip", encoding="utf-8")

            manager = TTSManager(
                NilsSettings(),
                model_dir=str(tmp_path / "models"),
                tmp_dir=str(tmp_path / "tmp"),
                default_ref_audio=str(tmp_path / "missing.wav"),
                default_ref_text=str(tmp_path / "missing.txt"),
            )

            status = manager.set_voice_clone(str(audio))

            self.assertIn("ICL mode", status)
            self.assertEqual(
                (tmp_path / "models" / "voice_clone.txt").read_text(encoding="utf-8"),
                "hello from the ref clip",
            )

    def test_set_voice_clone_auto_transcribes_when_sidecar_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            audio = tmp_path / "sample.wav"
            audio.write_bytes(b"fake wav")

            manager = TTSManager(
                NilsSettings(),
                model_dir=str(tmp_path / "models"),
                tmp_dir=str(tmp_path / "tmp"),
                default_ref_audio=str(tmp_path / "missing.wav"),
                default_ref_text=str(tmp_path / "missing.txt"),
            )

            with mock.patch.object(
                manager,
                "_auto_transcribe_reference",
                return_value="generated transcript",
            ) as auto_transcribe:
                status = manager.set_voice_clone(str(audio))

            auto_transcribe.assert_called_once_with(audio)
            self.assertIn("auto-transcribed", status)
            self.assertEqual(
                (tmp_path / "models" / "voice_clone.txt").read_text(encoding="utf-8"),
                "generated transcript",
            )

    def test_speak_uses_xvector_mode_without_transcript(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            default_ref = tmp_path / "nils-ref.wav"
            default_ref.write_bytes(b"fake wav")
            settings = NilsSettings()
            manager = TTSManager(
                settings,
                model_dir=str(tmp_path / "models"),
                tmp_dir=str(tmp_path / "tmp"),
                default_ref_audio=str(default_ref),
                default_ref_text=str(tmp_path / "nils-ref.txt"),
            )

            fake_engine = mock.Mock()
            fake_engine.generate_voice_clone.return_value = ([[0.0, 0.0]], 24000)
            manager._engine = fake_engine

            fake_music = mock.Mock()
            fake_mixer = mock.Mock()
            fake_mixer.get_init.return_value = True
            fake_mixer.music = fake_music

            with mock.patch.object(riko_services, "QWEN_AVAILABLE", True), mock.patch.object(
                riko_services, "sf"
            ) as fake_sf, mock.patch.dict(
                "sys.modules", {"pygame": mock.Mock(mixer=fake_mixer)}
            ):
                manager._speak_legacy("test line")

            fake_engine.generate_voice_clone.assert_called_once()
            self.assertEqual(
                fake_engine.generate_voice_clone.call_args.kwargs["ref_audio"],
                str(default_ref),
            )
            self.assertTrue(
                fake_engine.generate_voice_clone.call_args.kwargs["x_vector_only_mode"]
            )
            self.assertIsNone(
                fake_engine.generate_voice_clone.call_args.kwargs["ref_text"]
            )
            fake_sf.write.assert_called_once()

    def test_speak_uses_clone_ref_when_clone_voice_selected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            default_ref = tmp_path / "nils-ref.wav"
            clone_ref = tmp_path / "clone.wav"
            default_ref.write_bytes(b"default wav")
            clone_ref.write_bytes(b"clone wav")

            settings = NilsSettings(voice="clone")
            manager = TTSManager(
                settings,
                model_dir=str(tmp_path / "models"),
                tmp_dir=str(tmp_path / "tmp"),
                default_ref_audio=str(default_ref),
                default_ref_text=str(tmp_path / "nils-ref.txt"),
            )
            manager.set_voice_clone(str(clone_ref))

            fake_engine = mock.Mock()
            fake_engine.generate_voice_clone.return_value = ([[0.0, 0.0]], 24000)
            manager._engine = fake_engine

            fake_music = mock.Mock()
            fake_mixer = mock.Mock()
            fake_mixer.get_init.return_value = True
            fake_mixer.music = fake_music

            with mock.patch.object(riko_services, "QWEN_AVAILABLE", True), mock.patch.object(
                riko_services, "sf"
            ) as fake_sf, mock.patch.dict(
                "sys.modules", {"pygame": mock.Mock(mixer=fake_mixer)}
            ):
                manager._speak_legacy("test line")

            self.assertEqual(
                fake_engine.generate_voice_clone.call_args.kwargs["ref_audio"],
                str(tmp_path / "models" / "voice_clone.wav"),
            )
            fake_sf.write.assert_called_once()

    def test_auto_transcribe_reference_stops_after_first_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            audio = tmp_path / "sample.wav"
            audio.write_bytes(b"fake wav")

            manager = TTSManager(
                NilsSettings(),
                model_dir=str(tmp_path / "models"),
                tmp_dir=str(tmp_path / "tmp"),
                default_ref_audio=str(tmp_path / "missing.wav"),
                default_ref_text=str(tmp_path / "missing.txt"),
            )

            prepared = tmp_path / "prepared.wav"
            with mock.patch.object(
                manager, "_prepare_transcription_audio", return_value=prepared
            ), mock.patch.object(
                manager,
                "_transcribe_with_mlx_whisper",
                return_value="hello world",
            ) as mlx_transcribe, mock.patch.object(
                manager,
                "_transcribe_with_openai_whisper",
                return_value="should not be used",
            ) as whisper_transcribe:
                transcript = manager._auto_transcribe_reference(audio)

            self.assertEqual(transcript, "hello world")
            mlx_transcribe.assert_called_once_with(prepared)
            whisper_transcribe.assert_not_called()

    def test_run_transcriber_command_parses_json_output(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )
        completed = subprocess.CompletedProcess(
            args=["python3"],
            returncode=0,
            stdout='{"text": "hi there"}\n',
            stderr="",
        )

        with mock.patch.object(riko_services.subprocess, "run", return_value=completed):
            transcript = manager._run_transcriber_command(["python3", "-c", "pass"])

        self.assertEqual(transcript, "hi there")

    def test_transcribe_uses_current_python_executable(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        with mock.patch.object(manager, "_run_transcriber_command", return_value="ok") as runner:
            manager._transcribe_with_mlx_whisper(Path("/tmp/audio.wav"))

        self.assertEqual(runner.call_args.args[0][0], sys.executable)

    def test_split_text_into_chunks_prefers_punctuation_boundaries(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        text = (
            "This is the first sentence, and it should stay together. "
            "This is the second sentence, which should become its own chunk. "
            "Finally, this is the third sentence."
        )
        chunks = manager._split_text_into_chunks(text, target_len=60, max_len=90)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(chunks[0].endswith(".") or chunks[0].endswith(","))
        self.assertFalse(chunks[0].endswith("together"))
        self.assertTrue(all(len(chunk) <= 90 for chunk in chunks))

    def test_split_long_segment_falls_back_to_words(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        segment = "one two three four five six seven eight nine ten"
        pieces = manager._split_long_segment(segment, max_len=14)

        self.assertGreater(len(pieces), 1)
        self.assertTrue(all(len(piece) <= 14 for piece in pieces))

    def test_normalize_generated_audio_uses_first_waveform(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        audio = manager._normalize_generated_audio([[[0.1, 0.2], [0.3, 0.4]]])

        self.assertEqual(audio, [[0.1, 0.2], [0.3, 0.4]])

    def test_normalize_generated_audio_transposes_channels_first(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        audio = manager._normalize_generated_audio([[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]])

        self.assertEqual(audio, [[0.1, 0.4], [0.2, 0.5], [0.3, 0.6]])

    def test_normalize_generated_audio_rejects_empty_audio(self):
        manager = TTSManager(
            NilsSettings(),
            default_ref_audio="/tmp/missing.wav",
            default_ref_text="/tmp/missing.txt",
        )

        with self.assertRaisesRegex(ValueError, "no audio samples"):
            manager._normalize_generated_audio([])


if __name__ == "__main__":
    unittest.main()
