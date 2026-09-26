"""Core Wordle rules: scoring a guess, filtering candidates, picking a secret.

Words are handled in lowercase internally and shown uppercase in the UI.
Run `python backend/wordle.py` to print the hand-checked scoring cases.
"""

from __future__ import annotations

import random
from collections import Counter
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
WORD_LENGTH = 5
MAX_GUESSES = 6

GREEN, YELLOW, GRAY = "green", "yellow", "gray"
Pattern = tuple[str, ...]


def _load(name: str) -> tuple[str, ...]:
    words = (line.strip().lower() for line in (DATA / name).read_text().splitlines())
    return tuple(sorted({w for w in words if len(w) == WORD_LENGTH and w.isalpha()}))


@lru_cache(maxsize=1)
def word_list() -> tuple[str, ...]:
    """Every valid guess (12,972 words, answers included)."""
    return _load("word_list.txt")


@lru_cache(maxsize=1)
def answer_list() -> tuple[str, ...]:
    """The 2,315 common words a secret is drawn from."""
    return _load("answer_list.txt")


@lru_cache(maxsize=1)
def valid_words() -> frozenset[str]:
    return frozenset(word_list())


@lru_cache(maxsize=1)
def answer_set() -> frozenset[str]:
    return frozenset(answer_list())


def score_guess(guess: str, secret: str) -> list[str]:
    """Colour each letter of `guess` against `secret`, exactly like Wordle.

    Greens are settled first. A letter is then yellow only while the secret
    still has an unmatched copy of it, so a doubled letter in the guess
    against a single one in the secret gives one coloured tile, not two.
    """
    guess, secret = guess.lower(), secret.lower()
    pattern = [GRAY] * WORD_LENGTH
    unmatched = Counter()
    for i, (g, s) in enumerate(zip(guess, secret)):
        if g == s:
            pattern[i] = GREEN
        else:
            unmatched[s] += 1
    for i, g in enumerate(guess):
        if pattern[i] != GREEN and unmatched[g] > 0:
            pattern[i] = YELLOW
            unmatched[g] -= 1
    return pattern


def filter_candidates(words, guess_history) -> list[str]:
    """Every word that would have produced the same colours for every past guess.

    `guess_history` is a list of (guess, pattern) pairs. Re-scoring against
    each candidate is the only filter that gets duplicate letters right in
    every case, and it's quick enough for 13k words.
    """
    history = [(g.lower(), tuple(p)) for g, p in guess_history]
    return [w for w in words if all(tuple(score_guess(g, w)) == p for g, p in history)]


def pick_secret(rng: random.Random | None = None) -> str:
    """A random common word for a new game."""
    return (rng or random).choice(answer_list())


def letter_states(guess_history) -> dict[str, str]:
    """Best-known state of every letter tried so far (green beats yellow beats gray)."""
    rank = {GRAY: 0, YELLOW: 1, GREEN: 2}
    states: dict[str, str] = {}
    for guess, pattern in guess_history:
        for letter, colour in zip(guess.lower(), pattern):
            if letter not in states or rank[colour] > rank[states[letter]]:
                states[letter] = colour
    return states


if __name__ == "__main__":
    G, Y, X = GREEN, YELLOW, GRAY
    SYMBOL = {GREEN: "G", YELLOW: "Y", GRAY: "-"}
    cases = [
        ("crane", "crane", [G, G, G, G, G]),
        ("crane", "react", [Y, Y, G, X, Y]),
        # Two E's guessed, one E in the secret, not in either guessed spot: one yellow.
        ("geese", "those", [X, X, X, G, G]),
        ("speed", "abide", [X, X, Y, X, Y]),
        # Two L's guessed, one in the secret: the green one takes it, the other is gray.
        ("hello", "world", [X, X, X, G, Y]),
        ("lolly", "world", [X, G, X, G, X]),
        # Doubled letter in the secret, single in the guess.
        ("abbey", "kebab", [Y, Y, G, Y, X]),
    ]
    for guess, secret, expected in cases:
        got = score_guess(guess, secret)
        mark = "ok " if got == expected else "BAD"
        print(f"{mark} {guess.upper()} vs {secret.upper()}: {' '.join(SYMBOL[c] for c in got)}")
    history = [("crane", score_guess("crane", "shout")), ("pilot", score_guess("pilot", "shout"))]
    left = filter_candidates(answer_list(), history)
    print(f"after CRANE, PILOT against SHOUT: {len(left)} answers left: {' '.join(left[:12])}")
