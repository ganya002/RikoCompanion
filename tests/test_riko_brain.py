import unittest
from unittest import mock

from riko_brain import NilsBrain


class FakeSystemTools:
    def quick_status(self):
        return "Battery: 91%\nFrontmost: Safari - ChatGPT"

    def clipboard_text(self):
        return "clipboard text"

    def open_target(self, target):
        return f"Opened {target}"

    def run_shell(self, command):
        return f"Exit 0\n{command}"


class FakeScreenObserver:
    def describe_screen(self):
        return "Safari is open with a chat page."


class NilsBrainTests(unittest.TestCase):
    def test_history_roles_follow_sender(self):
        brain = NilsBrain(history_file="does-not-exist.json")
        brain.history = [
            {"from": "user", "text": "hey"},
            {"from": "nils", "text": "yo"},
        ]
        context = brain.get_recent_context()
        self.assertEqual(context[0]["role"], "user")
        self.assertEqual(context[1]["role"], "assistant")

    def test_command_router_handles_screen_request(self):
        brain = NilsBrain(
            history_file="does-not-exist.json",
            system_tools=FakeSystemTools(),
            screen_observer=FakeScreenObserver(),
        )
        response = brain._handle_command("/screen")
        self.assertEqual(response[0], "Safari is open with a chat page.")

    def test_command_router_handles_shell_request(self):
        brain = NilsBrain(
            history_file="does-not-exist.json",
            system_tools=FakeSystemTools(),
            screen_observer=FakeScreenObserver(),
        )
        response = brain._handle_command("/shell pwd")
        self.assertEqual(response[0], "Exit 0\npwd")

    def test_rule_response_avoids_recent_repeat(self):
        brain = NilsBrain(history_file="does-not-exist.json")
        brain.history = [
            {"from": "nils", "text": "Hey cutie. Behave."},
        ]

        with mock.patch("riko_brain.random.choice", side_effect=lambda seq: seq[0]):
            response, _ = brain._rule_based_response("hey")

        self.assertNotEqual(response, "Hey cutie. Behave.")


if __name__ == "__main__":
    unittest.main()
