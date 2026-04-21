import tempfile
import unittest
from pathlib import Path

from riko_services import RikoSettings, SystemTools, wrap_text


class RikoServicesTests(unittest.TestCase):
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
            settings = RikoSettings(
                tts_enabled=False,
                screen_access_enabled=False,
                command_access_enabled=True,
                voice="af_bella",
                tts_speed=1.1,
            )
            settings.save(str(path))
            loaded = RikoSettings.load(str(path))
            self.assertEqual(loaded.voice, "af_bella")
            self.assertFalse(loaded.tts_enabled)
            self.assertAlmostEqual(loaded.tts_speed, 1.1)


if __name__ == "__main__":
    unittest.main()
