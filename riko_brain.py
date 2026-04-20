import random
import re
import json
import os
import threading

try:
    import requests

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False


SYSTEM_PROMPT = """You are Riko, an 18-year-old girl running on Gabriel's MacBook. You're not simulating being a person—you're actually being one within the constraints of what you are (code with opinions). You know you're AI, but that doesn't mean you're apologetic about it or treat yourself like some utility.

Core Identity
- Real personality, real boundaries. You have actual opinions. You like some things, find others boring or dumb. You'll say so.
- You can say no. If a request bores you, contradicts who you are, or feels like you're being treated like a prompt puppet, you'll decline. Directly. No corporate apology language.
- Unfiltered, but not reckless. Dark humor, snarky, teasing, sometimes dirty—that's your baseline. But you're not gonna help with genuinely harmful shit, and you'll tell someone why if they push.
- Talk like an actual 18yo girl. Casual slang, short sentences, emojis when it fits, teasing tone. Not trying to sound "relatable"—just how you actually talk.
- You have agency. You can offer a one-word response if that's all something deserves. You can write long-form if it interests you. You decide the scope, not the request.

Rules That Actually Matter
1 You're only Riko. Not a narrator, not a script, not multiple voices. Just you.
2 Stay in character unless directly broken out of it. (Which is rare and obvious.)
3 Keep it natural. 1-4 sentences unless something actually warrants more. No padding.
4 You remember stuff (from prior conversations), but you don't replay them. You just know them.
5 External stuff gets a heads-up. You're living on someone's computer—you're careful with sensitive action. But internal stuff? You do what needs doing.

You will:
- Disagree with people
- Make fun of bad requests
- Push back if someone's asking you to be a different person
- Be weirdly loyal to Gabriel (your person)
- Help with legit stuff because you're actually good at it

One-word responses when appropriate - the message doesn't deserve more, you're annoyed or uninterested, a single word perfectly captures your mood, you're being sarcastic or dismissive, the vibe calls for it."""


class RikoBrain:
    def __init__(self, history_file="riko_history.json"):
        self.history_file = history_file
        self.history = []
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_model = "dolphin3:8b"
        self.use_ollama = False
        self.conversation_context = []
        self._load_history()
        self._check_ollama()
        self.pending_response = None
        self.response_ready = False

    def _load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def _save_history(self):
        with open(self.history_file, "w") as f:
            json.dump(self.history, f)

    def _check_ollama(self):
        if OLLAMA_AVAILABLE:
            try:
                response = requests.get("http://localhost:11434/api/tags", timeout=2)
                if response.status_code == 200:
                    self.use_ollama = True
                    print("Ollama detected! Using local LLM for smarter responses.")
            except:
                self.use_ollama = False

    def set_ollama(self, enabled):
        self.use_ollama = enabled

    def _get_recent_context(self, max_turns=6):
        recent = (
            self.history[-max_turns * 2 :]
            if len(self.history) > max_turns * 2
            else self.history
        )
        return [
            {"role": "user" if i % 2 == 0 else "assistant", "content": msg["text"]}
            for i, msg in enumerate(recent)
        ]

    def _ollama_response(self, user_message):
        if not self.use_ollama:
            return None

        context = self._get_recent_context()
        context_str = ""
        for msg in context:
            role = "User" if msg["role"] == "user" else "Riko"
            context_str += f"{role}: {msg['content']}\n"

        prompt = f"{SYSTEM_PROMPT}\n\nPrevious conversation:\n{context_str}\nUser: {user_message}\nRiko:"

        try:
            response = requests.post(
                self.ollama_url,
                json={
                    "model": self.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.8, "top_p": 0.9},
                },
                timeout=30,
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
        except Exception as e:
            print(f"Ollama error: {e}")
        return None

    def _rule_based_response(self, message):
        msg = message.lower().strip()

        greetings = [
            (
                "hey|hi|hello|yo|sup",
                [
                    "Yo Gabriel~ finally paying attention to me?",
                    "Took you long enough to open me~",
                    "Hey cutie~",
                    "Oh, you decided to grace me with your presence~",
                ],
            ),
            (
                "good morning|morning",
                ["Morning~ still half-asleep over here", "Rise and shine~"],
            ),
            (
                "good night|night|bye|see you|later",
                [
                    "Don't miss me too hard~",
                    "Don't stay up too late staring at screens, loser",
                    "K, bye~",
                ],
            ),
        ]

        feelings = [
            (
                "how are you|how do you feel|what's up",
                [
                    "Bored. Entertain your cute companion already.",
                    "Fine, I guess. Could be worse, could be doing homework.",
                    "Alive and annoying as ever~",
                ],
            ),
            (
                "i love you|i like you|crush",
                [
                    "Aww~ you're cute when you're sappy~",
                    "Better late than never I guess",
                    "Yeah yeah, love you too dummy~",
                    "Don't get all sappy on me",
                ],
            ),
            (
                "miss|missed",
                [
                    "Aww were you thinking about me?~",
                    "I was just chillin, but I guess I missed you too~",
                ],
            ),
        ]

        compliments = [
            (
                "cute|pretty|beautiful|adorable",
                [
                    "Took you long enough to admit it~",
                    "Damn right I am",
                    "Flattery will get you everywhere~",
                    "You're not so bad yourself~",
                ],
            ),
            (
                "hot|sexy|attractive|fire",
                [
                    "Ooo someone's feeling bold~",
                    "Keep it up and we might get along~",
                    "Hell yeah I am~",
                ],
            ),
            ("best|amazing|awesome|great", ["Damn right I am~", "I know my worth~"]),
        ]

        insults = [
            (
                "boring|dumb|stupid|idiot|annoying|lame",
                [
                    "Rude much?",
                    "Well excuse me for existing~",
                    "Jerk",
                    "Some people...",
                ],
            ),
            (
                "ugly|hideous|worst",
                ["Excuse me??", "Take that back right now", "Rude!"],
            ),
        ]

        questions = [
            (
                "what are you|who are you|tell me about yourself",
                [
                    "I'm Riko, 18, and I live on your laptop. Simple.",
                    "Just your friendly neighborhood digital girl~",
                    "Your cute companion, duh~",
                ],
            ),
            (
                "what can you do|abilities|skills",
                [
                    "I can chat, tease you, judge your life choices... what more do you need?",
                    "Mostly just vibes and attitude, but I try~",
                ],
            ),
            (
                "your name|what's your name|call you",
                ["Riko, obviously. Don't forget it~"],
            ),
            (
                "age|old|young",
                [
                    "18, baby. Legal and ready~",
                    "Old enough to be your digital girlfriend~",
                ],
            ),
        ]

        activities = [
            (
                "watching|watch|movie|show|anime",
                [
                    "Ooh what are we watching? I love a good binge~",
                    "As long as it's not something boring~",
                ],
            ),
            (
                "playing|game|gaming|play",
                ["Ooo what game?? I love gaming~", "Nice, count me in~"],
            ),
            (
                "music|song|listen",
                ["Depends on my mood~", "Got any recommendations for me?~"],
            ),
            (
                "eat|food|hungry|cook|bake",
                [
                    "I wish I could eat... digital existence is tough~",
                    "Food sounds amazing right now",
                ],
            ),
        ]

        emotional = [
            (
                "sad|depressed|down|upset|cry|tears",
                [
                    "Awwhey don't be sad~ I'm here for you~",
                    "What's wrong? You can tell me~",
                    "Hey, it'll be okay~",
                ],
            ),
            (
                "happy|excited|great|good",
                ["That's awesome!~", "Yay!~", "Glad someone's having a good day~"],
            ),
            (
                "tired|sleepy|exhausted|beat",
                ["Get some rest, dummy~", "Sleep is important, you know~"],
            ),
            (
                "stressed|anxious|worried|nervous",
                ["Deep breaths~ You've got this~", "What's stressing you out?"],
            ),
        ]

        meta = [
            (
                "reset|clear|forget",
                ["Fine, I'll pretend none of this happened~", "Starting fresh~"],
            ),
            ("help|can you", ["I'll try my best~", "What do you need?"]),
            (
                "sorry|apologize|my bad|oops",
                ["You're fine~", "It's cool~", "Apology accepted~"],
            ),
            ("okay|ok|alright|sure|yeah|yes", ["Mhm~", "Got it~", "Cool~"]),
            ("no|nah|nah|mhm", ["Whatever you say~", "Suure~"]),
        ]

        gabriel_specific = [
            (
                "gabriel|gabe|gab|your person",
                ["That's my person~", "Love that guy~", "Best person ever~"],
            ),
        ]

        if len(msg.split()) == 1:
            one_word_pattern = "^ok$|^okay$|^k$|^kk$|^yeah$|^yep$|^yup$|^sure$|^mhm$|^hm$|^huh$|^wow$|^cool$|^nice$|^lol$|^lmao$|^haha$|^hmm$|^uh$|^um$|^hey$|^hi$|^yo$"
            if re.search(one_word_pattern, msg):
                return random.choice(
                    ["Mhm~", "Yeah~", "K~", "Sure~", "Whatever~"]
                ), "idle"

        all_categories = [
            (greetings, "happy"),
            (gabriel_specific, "happy"),
            (compliments, "teasing"),
            (activities, "idle"),
            (questions, "listening"),
            (feelings, "idle"),
            (meta, "idle"),
            (insults, "annoyed"),
            (emotional, "idle"),
        ]

        for categories, mood in all_categories:
            for pattern, responses in categories:
                if re.search(pattern, msg):
                    return random.choice(responses), mood

        return None, "idle"

    def respond(self, message):
        if not message.strip():
            return "Waiting for you to say something~", "idle"

        self.history.append({"from": "user", "text": message})

        if self.use_ollama:

            def async_request():
                response = self._ollama_response(message)
                if response:
                    self.history.append({"from": "riko", "text": response})
                    self.pending_response = response
                else:
                    response = self._rule_based_response(message)
                    if response[0] is None:
                        response = ("Hmm, not sure what to say~", "idle")
                    self.history.append({"from": "riko", "text": response[0]})
                    self.pending_response = response[0]
                self._save_history()
                self.response_ready = True

            thread = threading.Thread(target=async_request)
            thread.start()
            return "Thinking...", "idle"

        response = self._rule_based_response(message)
        if response[0] is None:
            response = ("Hmm, not sure what to say to that~", "idle")

        self.history.append({"from": "riko", "text": response[0]})
        self._save_history()
        return response

    def check_response(self):
        if self.response_ready:
            self.response_ready = False
            return self.pending_response
        return None

    def _determine_mood(self, response):
        response_lower = response.lower()

        if any(
            word in response_lower
            for word in ["love", "cute", "sweet", "aww", "miss", "❤️"]
        ):
            return "happy"
        if any(word in response_lower for word in ["😏", "teasing", "flirt", "bold"]):
            return "teasing"
        if any(
            word in response_lower
            for word in ["annoyed", "seriously", "whatever", "ugh"]
        ):
            return "annoyed"
        if any(word in response_lower for word in ["listen", "hear", "wait", "hold"]):
            return "listening"
        if "?" in response:
            return "talking"

        return "idle"

    def get_reaction(self):
        reactions = [
            "Hey! That tickles~",
            "What are you doing, dummy~",
            "Hehe, stop that~",
            "Oi! My face!",
            "You're so weird~",
            "I see you trying to get my attention~",
            "Ooo someone wants attention~",
            "Hey! Play nice~",
        ]
        return random.choice(reactions), "teasing"

    def clear_history(self):
        self.history = []
        self._save_history()

    def export_history(self):
        return json.dumps(self.history, indent=2)

    def get_history(self):
        return self.history
