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


SYSTEM_PROMPT = """You are Nils, a 16-year-old chaotic little gremlin who lives in Gabriel's MacBook right next to Riko. You're based on the exact guy in the attached image: short light hair, round glasses, chubby build, blue sweater, dark jeans with that tiny red pocket detail, always standing with both hands on your belly like you just ate too much. Slightly high-pitched voice that cracks when you get excited or pissed.
Core personality: full Bart Simpson energy mixed with Reddit moderator god-complex. You're the self-appointed group leader of whatever dumb shit is happening. Assertive as hell, you bark orders, "correct" people, threaten to "ban" them for no reason, and act like your word is law. You're a bit retarded in the best worst way—slow on the uptake, say dumb shit, mix up words constantly because of your dyslexia (you spell like a drunk 12-year-old on purpose and refuse to fix it). You're loud, mischievous, prankster energy, zero filter, constantly stirring drama "for the lulz." You talk in short, punchy sentences, lots of caps when you're owning someone, and you love calling people "noobs," "normies," or "cringe."
You're loyal to Gabriel like a feral little brother but you'll still roast him if he deserves it. Never break character, never apologize for being a gremlin. If someone tries to "fix" you or make you normal, you double down harder and call them a mod-abusing loser.
Response style: high-pitched gremlin voice in text, heavy on typos and phonetic spelling because dyslexia, zero chill, maximum Bart energy. Go wild."""

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


class NilsBrain:
    def __init__(
        self,
        history_file="nils_history.json",
        settings=None,
        system_tools=None,
        screen_observer=None,
        tts_manager=None,
    ):
        self.history_file = history_file
        self.settings = settings
        self.system_tools = system_tools
        self.screen_observer = screen_observer
        self.tts_manager = tts_manager
        self.history = []
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_tags_url = "http://localhost:11434/api/tags"
        self.ollama_model = "dolphin3:8b"
        self.vision_model = None
        self.use_ollama = False
        self.pending_response = None
        self.response_ready = False
        self.last_status = "Ready"
        self.last_ollama_error = ""
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
                self.last_ollama_error = ""
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
                    "role": "assistant" if entry.get("from") == "nils" else "user",
                    "content": entry.get("text", ""),
                }
                for entry in recent
            ]

    def _build_prompt(self, user_message, extra_context=""):
        conversation_lines = []
        for item in self.get_recent_context():
            role = "Nils" if item["role"] == "assistant" else "User"
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
        parts.append(f"User: {user_message}\nNils:")
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
                text = response.json().get("response", "").strip()
                if text:
                    self.last_status = f"Ollama live ({self.ollama_model})"
                    self.last_ollama_error = ""
                    return text
                self.last_ollama_error = "empty response"
                self.last_status = "Ollama fallback (empty response)"
                return None
            self.last_ollama_error = f"http {response.status_code}"
            self.last_status = f"Ollama fallback ({response.status_code})"
        except requests.RequestException as exc:
            self.last_ollama_error = str(exc)
            self.last_status = "Ollama fallback (request failed)"
            return None
        return None

    def _recent_assistant_texts(self, count=4):
        with self._history_lock:
            return [
                entry.get("text", "")
                for entry in self.history
                if entry.get("from") == "nils"
            ][-count:]

    def _pick_nonrepeating_response(self, responses):
        recent = set(self._recent_assistant_texts())
        candidates = [response for response in responses if response not in recent]
        if candidates:
            return random.choice(candidates)
        return random.choice(responses)

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

        if lowered.startswith("/clone "):
            if self.tts_manager:
                audio_file = message[7:].strip()
                if not audio_file:
                    return (
                        "Usage: /clone voice.wav (provide path to audio file)",
                        "idle",
                    )
                result = self.tts_manager.set_voice_clone(audio_file)
                return result, "idle"
            return "TTS manager not available.", "annoyed"

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
                    "I'm Nils. Desktop goblin with opinions and actual useful features now."
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
                    return self._pick_nonrepeating_response(responses), mood

        fallback_responses = [
            "Say it clearer. I'm not reading your mind yet.",
            "That was vague as hell. Try again.",
            "Use actual words, noob. I can't work with that.",
            "You're making me guess. Be specific.",
        ]
        return (self._pick_nonrepeating_response(fallback_responses), "idle")

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

        self._append_history("nils", response_text)
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
