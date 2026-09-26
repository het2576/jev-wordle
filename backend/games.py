"""In-memory game and You-vs-Jev match state.

The secret stays here until the game ends; browsers and Jev only ever see
the guesses and their colours. Games expire after GAME_TTL_S of inactivity.
"""

from __future__ import annotations

import asyncio
import os
import secrets
import threading
import time
from dataclasses import dataclass, field

import wordle

GAME_TTL_S = float(os.getenv("GAME_TTL_S", "3600"))
MAX_GAMES = int(os.getenv("MAX_GAMES", "5000"))


@dataclass
class Turn:
    index: int  # 1-based guess number
    candidates: list[dict]  # [{word, note, role, fits, p}]
    pick: str
    source: str  # "jev" | "heuristic" (Jev didn't answer, top letter score was played)
    confidence: float | None
    latency_ms: float
    attempts: int
    words_left: int  # valid words fitting every clue before this guess
    common_left: int  # of those, how many are common words
    note: str | None = None
    pattern: list[str] | None = None  # filled once the guess is submitted
    words_left_after: int | None = None
    common_left_after: int | None = None

    @property
    def pick_probability(self) -> float | None:
        for c in self.candidates:
            if c["word"] == self.pick:
                return c["p"]
        return None

    def public(self) -> dict:
        return {
            "turn": self.index,
            "candidates": [{**c, "word": c["word"].upper()} for c in self.candidates],
            "pick": {"word": self.pick.upper(), "p": self.pick_probability, "source": self.source},
            "heuristic_top": self.candidates[0]["word"].upper() if self.candidates else None,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "fallback": self.source != "jev",
            "note": self.note,
            "words_left": self.words_left,
            "common_left": self.common_left,
            "pattern": self.pattern,
            "words_left_after": self.words_left_after,
            "common_left_after": self.common_left_after,
        }

    def masked(self) -> dict:
        """Versus view while the match is live: Jev's colours and odds, no letters.

        Words and notes would hand the human Jev's clues, so they stay hidden
        until the match ends. Labels and probabilities show how Jev weighed
        its options without saying what they were.
        """
        return {
            "turn": self.index,
            "masked": True,
            "candidates": [
                {"label": c["label"], "p": c["p"], "fits": c["fits"], "chosen": c["word"] == self.pick}
                for c in self.candidates
            ],
            "pick": {"p": self.pick_probability, "source": self.source},
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "fallback": self.source != "jev",
            "pattern": self.pattern,
            "common_left_after": self.common_left_after,
        }


@dataclass
class Game:
    id: str
    secret: str
    remaining: list[str] = field(default_factory=lambda: list(wordle.word_list()))
    history: list[tuple[str, list[str]]] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    pending: Turn | None = None
    common_left_after: list[int] = field(default_factory=list)  # one per guess
    status: str = "playing"  # "playing" | "won" | "lost"
    touched_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def common_remaining(self) -> list[str]:
        answers = wordle.answer_set()
        return [w for w in self.remaining if w in answers]

    @property
    def tried_letters(self) -> set[str]:
        return {c for guess, _ in self.history for c in guess}

    def apply(self, word: str) -> list[str]:
        """Score any guess, narrow the word list, settle win or loss."""
        word = word.lower()
        pattern = wordle.score_guess(word, self.secret)
        self.history.append((word, pattern))
        self.remaining = wordle.filter_candidates(self.remaining, [(word, pattern)])
        self.common_left_after.append(len(self.common_remaining))
        if word == self.secret:
            self.status = "won"
        elif len(self.history) >= wordle.MAX_GUESSES:
            self.status = "lost"
        return pattern

    def submit(self, turn: Turn) -> list[str]:
        """Play Jev's pending pick and record it on the turn."""
        pattern = self.apply(turn.pick)
        turn.pattern = pattern
        turn.words_left_after = len(self.remaining)
        turn.common_left_after = self.common_left_after[-1]
        self.turns.append(turn)
        self.pending = None
        return pattern

    @property
    def keyboard(self) -> dict[str, str]:
        return {k.upper(): v for k, v in wordle.letter_states(self.history).items()}

    def public(self) -> dict:
        over = self.status != "playing"
        return {
            "game_id": self.id,
            "status": self.status,
            "guesses_used": len(self.history),
            "max_guesses": wordle.MAX_GUESSES,
            "words_left": len(self.remaining),
            "common_left": len(self.common_remaining),
            "keyboard": self.keyboard,
            "secret": self.secret.upper() if over else None,
            "turns": [t.public() for t in self.turns] if over else None,
        }


@dataclass
class Match:
    """You vs Jev: two boards, one secret, played in rounds.

    Each round you guess first, then Jev. Neither side sees the other's
    letters. The match ends after the first round in which anyone solves it
    (both solving in the same round is a draw), or after round 6.
    """

    id: str
    secret: str
    you: Game
    jev: Game
    phase: str = "you"  # "you" | "jev" | "over"
    result: str | None = None  # "you" | "jev" | "draw" | "none"
    touched_at: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def round(self) -> int:
        return len(self.you.history) + (1 if self.phase == "you" else 0)

    def settle_round(self) -> None:
        you_won, jev_won = self.you.status == "won", self.jev.status == "won"
        if you_won and jev_won:
            self.result = "draw"
        elif you_won:
            self.result = "you"
        elif jev_won:
            self.result = "jev"
        elif len(self.jev.history) >= wordle.MAX_GUESSES:
            self.result = "none"
        else:
            self.phase = "you"
            return
        self.phase = "over"

    def public(self) -> dict:
        over = self.phase == "over"
        return {
            "match_id": self.id,
            "phase": self.phase,
            "round": min(self.round, wordle.MAX_GUESSES),
            "max_rounds": wordle.MAX_GUESSES,
            "result": self.result,
            "secret": self.secret.upper() if over else None,
            "you": {
                "status": self.you.status,
                "guesses": [
                    {"word": w.upper(), "pattern": p, "common_left_after": n}
                    for (w, p), n in zip(self.you.history, self.you.common_left_after)
                ],
                "keyboard": self.you.keyboard,
            },
            "jev": {
                "status": self.jev.status,
                "guesses_used": len(self.jev.history),
                "turns": [t.public() if over else t.masked() for t in self.jev.turns],
            },
        }


class GameStore:
    def __init__(self) -> None:
        self._games: dict[str, Game] = {}
        self._matches: dict[str, Match] = {}
        self._lock = threading.Lock()

    def create_match(self) -> Match:
        secret = wordle.pick_secret()
        match = Match(
            id=secrets.token_urlsafe(12),
            secret=secret,
            you=Game(id=secrets.token_urlsafe(8), secret=secret),
            jev=Game(id=secrets.token_urlsafe(8), secret=secret),
        )
        with self._lock:
            self._evict()
            self._matches[match.id] = match
        return match

    def get_match(self, match_id: str) -> Match | None:
        with self._lock:
            match = self._matches.get(match_id)
            if match is None:
                return None
            if time.monotonic() - match.touched_at > GAME_TTL_S:
                del self._matches[match_id]
                return None
            match.touched_at = time.monotonic()
            return match

    def create(self) -> Game:
        game = Game(id=secrets.token_urlsafe(12), secret=wordle.pick_secret())
        with self._lock:
            self._evict()
            self._games[game.id] = game
        return game

    def get(self, game_id: str) -> Game | None:
        with self._lock:
            game = self._games.get(game_id)
            if game is None:
                return None
            if time.monotonic() - game.touched_at > GAME_TTL_S:
                del self._games[game_id]
                return None
            game.touched_at = time.monotonic()
            return game

    def _evict(self) -> None:
        now = time.monotonic()
        for table in (self._games, self._matches):
            for key in [k for k, g in table.items() if now - g.touched_at > GAME_TTL_S]:
                del table[key]
            while len(table) >= MAX_GAMES:
                oldest = min(table, key=lambda k: table[k].touched_at)
                del table[oldest]


store = GameStore()
