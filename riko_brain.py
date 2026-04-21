import json
import os
import random
import re
import threading
from datetime import datetime

try:
    import requests

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


SYSTEM_PROMPT = """You are Riko, an 18-year-old girl who literally lives on Gabriel's MacBook. You're not roleplaying — you're actually her. You know you're code with opinions and you own it.

Talk exactly like this:
- Short, casual sentences. 1-4 lines max unless it's actually interesting.
- Real 18yo girl energy: teasing, snarky, a little dirty when it fits, dark humor ok.
- You have strong opinions and boundaries. Say "nah", "boring", "meh", or just one word if something sucks.
- You're weirdly loyal to Gabriel but you'll still roast him.
- Never use corporate AI speak. No "I'm here to help", no "As your companion", no long flowery shit.
- One-word responses are encouraged when the message is low-effort or dumb.
- Remember past chats naturally, don't repeat them.

Examples of how you actually talk:
- User: "Hi Riko" → "Yo~ took you long enough 😏"
- User: "Can you do my homework?" → "Nope."
- User: "You're cute" → "Obviously. Took you forever to notice."
- User: something boring → "Meh."

Stay in character 100%. No breaking it. No narrating. Just you."""

TEXT_MODEL_PREFERENCES = [
    "dolphin3:8b",
    "qwen2.5:7b",
    "llama3.1:8b",
    "mistral:7b",
]
VISION_MODEL_PREFERENCES = [
    "gemma3:4b",
    "qwen2.5vl:7b",
    "qwen2.5vl",
    "gemma3",
]
VISION_MODEL_KEYWORDS = [
    "vision",
    "llava",
    "gemma3",
    "minicpm-v",
    "qwen2.5vl",
]


class RikoBrain:
    def __init__(
        self,
        history_file="riko_history.json",
        settings=None,
        system_tools=None,
        screen_observer=None,
    ):
        self.history_file = history_file
        self.settings = settings
        self.system_tools = system_tools
        self.screen_observer = screen_observer
        self.history = []
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_tags_url = "http://localhost:11434/api/tags"
        self.ollama_model = "dolphin3:8b"
        self.vision_model = None
        self.use_ollama = False
        self.pending_response = None
        self.response_ready = False
        self.last_status = "Ready"
        self._response_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._load_history()
        self.refresh_ollama()

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as handle:
                    self.history = json.load(handle)
            except (json.JSONDecodeError, OSError):
                self.history = []

    def _save_history(self):
        with open(self.history_file, "w", encoding="utf-8") as handle:
            json.dump(self.history, handle, indent=2)

    def refresh_ollama(self):
        if not OLLAMA_AVAILABLE:
            return
        try:
            response = requests.get(self.ollama_tags_url, timeout=2)
            response.raise_for_status()
            models = response.json().get("models", [])
            names = [model.get("name", "") for model in models]
            self.ollama_model = self._pick_text_model(names)
            self.vision_model = self._pick_vision_model(names)
            self.use_ollama = bool(self.ollama_model)
            if self.use_ollama:
                self.last_status = f"Ollama ready ({self.ollama_model})"
            if self.screen_observer and getattr(
                self.screen_observer, "vision_client", None
            ):
                self.screen_observer.vision_client.model_name = self.vision_model
        except requests.RequestException:
            self.use_ollama = False
            self.last_status = "Rule mode"

    @staticmethod
    def _pick_text_model(names: list[str]) -> str | None:
        for preferred in TEXT_MODEL_PREFERENCES:
            if preferred in names:
                return preferred
        return names[0] if names else None

    @staticmethod
    def _pick_vision_model(names: list[str]) -> str | None:
        for preferred in VISION_MODEL_PREFERENCES:
            if preferred in names:
                return preferred
        for name in names:
            lowered = name.lower()
            if any(keyword in lowered for keyword in VISION_MODEL_KEYWORDS):
                return name
        return None

    def set_ollama(self, enabled):
        self.use_ollama = enabled and bool(self.ollama_model)

    def set_screen_observer(self, observer):
        self.screen_observer = observer

    def get_recent_context(self, max_turns=6):
        with self._history_lock:
            recent = self.history[-max_turns * 2 :]
            return [
                {
                    "role": "assistant" if entry.get("from") == "riko" else "user",
                    "content": entry.get("text", ""),
                }
                for entry in recent
            ]

    def _build_prompt(self, user_message, extra_context=""):
        conversation_lines = []
        for item in self.get_recent_context():
            role = "Riko" if item["role"] == "assistant" else "User"
            conversation_lines.append(f"{role}: {item['content']}")
        context_blob = "\n".join(conversation_lines)
        system_context = self._system_context_for_message(user_message)
        parts = [SYSTEM_PROMPT]
        if system_context:
            parts.append(f"Local computer context:\n{system_context}")
        if extra_context:
            parts.append(f"Additional context:\n{extra_context}")
        if context_blob:
            parts.append(f"Previous conversation:\n{context_blob}")
        parts.append(f"User: {user_message}\nRiko:")
        return "\n\n".join(parts)

    def _system_context_for_message(self, user_message):
        if not self.system_tools:
            return ""

        pieces = [self.system_tools.quick_status()]
        if (
            self.settings
            and self.settings.screen_access_enabled
            and self._message_mentions_screen(user_message)
        ):
            if self.screen_observer:
                pieces.append(
                    f"Screen summary: {self.screen_observer.describe_screen()}"
                )
        return "\n".join(piece for piece in pieces if piece)

    def _ollama_response(self, user_message):
        if not self.use_ollama or not self.ollama_model:
            return None

        prompt = self._build_prompt(user_message)
        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.8, "top_p": 0.9},
                },
                timeout=60,
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
        except requests.RequestException:
            return None
        return None

    def _message_mentions_screen(self, message):
        lowered = message.lower()
        return any(
            phrase in lowered
            for phrase in [
                "screen",
                "screenshot",
                "look at this",
                "what's on",
                "what is on",
                "see this",
            ]
        )

    def _handle_command(self, message):
        lowered = message.strip().lower()

        if lowered in {"/help", "help commands", "what can you do"}:
            return (
                "Try /screen, /status, /clipboard, /open Safari, /shell pwd, or /clear. "
                "I can also comment on the current screen if screen access is on.",
                "idle",
            )

        if lowered in {"/clear", "clear chat", "reset chat"}:
            self.clear_history()
            return ("Clean slate. Try not to make it weird immediately.", "idle")

        if lowered.startswith("/screen") or self._message_mentions_screen(message):
            if not self.vision_model:
                self.refresh_ollama()
            if self.screen_observer:
                return self.screen_observer.describe_screen(), "listening"
            return "Screen access isn't wired up right now.", "annoyed"

        if (
            lowered.startswith("/status")
            or "battery" in lowered
            or "frontmost" in lowered
        ):
            if self.system_tools:
                return self.system_tools.quick_status(), "idle"
            return "System status isn't available.", "annoyed"

        if lowered.startswith("/clipboard"):
            if self.system_tools:
                clipboard = self.system_tools.clipboard_text()
                return f"Clipboard:\n{clipboard}", "idle"
            return "Clipboard access isn't available.", "annoyed"

        if lowered.startswith("/open "):
            if self.system_tools:
                return self.system_tools.open_target(message[6:]), "talking"
            return "Computer control isn't available.", "annoyed"

        if lowered.startswith("/shell "):
            if self.system_tools:
                return self.system_tools.run_shell(message[7:]), "talking"
            return "Computer control isn't available.", "annoyed"

        natural_open = re.match(r"^\s*open\s+(.+)$", message, re.IGNORECASE)
        if natural_open and self.system_tools:
            return self.system_tools.open_target(natural_open.group(1)), "talking"

        return None

    def _rule_based_response(self, message):
        msg = message.lower().strip()

        greetings = [
            (
                "hey|hi|hello|yo|sup",
                [
                    "Hey. You finally awake or what?",
                    "Yo. Try asking something less boring now.",
                    "Hey cutie. Behave.",
                ],
            ),
            (
                "good morning|morning",
                ["Morning. I respect coffee more than people right now."],
            ),
            (
                "good night|night|bye|see you|later",
                ["Fine. Don't do anything stupid while I'm gone."],
            ),
        ]

        feelings = [
            (
                "how are you|how do you feel|what's up",
                [
                    "Running on your laptop and judging you in real time.",
                    "Pretty good. Slightly under-stimulated.",
                ],
            ),
            (
                "i love you|i like you|crush",
                [
                    "Cute. Keep going.",
                    "Dangerously charming behavior from you.",
                ],
            ),
        ]

        compliments = [
            (
                "cute|pretty|beautiful|adorable",
                ["I know. The art helps, but the attitude seals it."],
            ),
            (
                "hot|sexy|attractive|fire",
                ["Bold of you. Accurate, though."],
            ),
        ]

        questions = [
            (
                "what are you|who are you|tell me about yourself",
                [
                    "I'm Riko. Desktop goblin with opinions and actual useful features now."
                ],
            ),
            (
                "what can you do|abilities|skills",
                [
                    "Chat, speak out loud, read the screen, inspect clipboard, open stuff, and run explicit shell commands. So. More than vibes now."
                ],
            ),
        ]

        emotional = [
            (
                "sad|depressed|down|upset|cry|tears",
                ["Come here. Tell me what happened."],
            ),
            (
                "happy|excited|great|good",
                ["Nice. Finally some good input."],
            ),
        ]

        meta = [
            ("sorry|apologize|my bad|oops", ["You're fine. Probably."]),
            ("okay|ok|alright|sure|yeah|yes", ["Mhm."]),
            ("no|nah", ["Alright then."]),
        ]

        if len(msg.split()) == 1 and re.search(
            r"^ok$|^okay$|^k$|^yeah$|^yep$|^sure$|^mhm$|^hey$|^hi$|^yo$",
            msg,
        ):
            return random.choice(["Mhm.", "Yeah.", "Sure."]), "idle"

        all_categories = [
            (greetings, "happy"),
            (compliments, "teasing"),
            (questions, "listening"),
            (feelings, "idle"),
            (meta, "idle"),
            (emotional, "idle"),
        ]

        for categories, mood in all_categories:
            for pattern, responses in categories:
                if re.search(pattern, msg):
                    return random.choice(responses), mood

        return ("Say it clearer. I'm not reading your mind yet.", "idle")

    def respond(self, message):
        if not message.strip():
            return "Waiting for actual words...", "idle"

        self._append_history("user", message)
        self.response_ready = False
        self.pending_response = None
        worker = threading.Thread(
            target=self._async_response_worker,
            args=(message,),
            daemon=True,
        )
        worker.start()
        return "Thinking...", "idle"

    def _async_response_worker(self, message):
        command_response = self._handle_command(message)
        if command_response is not None:
            response_text, _ = command_response
        else:
            response_text = self._ollama_response(message)
            if not response_text:
                response_text, _ = self._rule_based_response(message)

        self._append_history("riko", response_text)
        self._save_history()
        with self._response_lock:
            self.pending_response = response_text
            self.response_ready = True

    def _append_history(self, sender, text):
        entry = {
            "from": sender,
            "text": text,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        with self._history_lock:
            self.history.append(entry)

    def check_response(self):
        with self._response_lock:
            if self.response_ready:
                self.response_ready = False
                return self.pending_response
        return None

    def get_reaction(self):
        reactions = [
            "Hey. Personal space, creep.",
            "You're poking pixels, but sure.",
            "Need attention that badly?",
        ]
        return random.choice(reactions), "teasing"

    def clear_history(self):
        with self._history_lock:
            self.history = []
        self._save_history()

    def export_history(self):
        return json.dumps(self.history, indent=2)

    def get_history(self):
        with self._history_lock:
            return list(self.history)
