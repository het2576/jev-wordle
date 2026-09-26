"""Client for the Jev-compatible System One endpoint: one `choice` call per turn.

Verified with a manual call before this file was written (see README):

    POST {OPENJEV_BASE_URL}/systemone
    Authorization: Bearer <OPENJEV_API_KEY>
    {"model": "openjev", "state": {...},
     "questions": {"next_guess": {"type": "choice", "instructions": "...",
                                  "criteria": {"TOILS": "tests 4 common ...", "OPERA": "..."}}}}
    -> {"answers": {"next_guess": {"type": "choice", "choice": "TOILS",
                                   "probabilities": {"TOILS": 0.47, "OPERA": 0.24, ...},
                                   "confidence": 0.29}},
        "usage": {...}, "provider": "TypeSafe"}

Only the public game view is sent: past guesses, their colours and how many
words still fit. The secret word never leaves the server.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("jev")

BASE_URL = os.getenv("OPENJEV_BASE_URL", "https://api.openjev.sh/v1").rstrip("/")
MODEL = os.getenv("OPENJEV_MODEL", "openjev")
TIMEOUT_S = float(os.getenv("OPENJEV_TIMEOUT_S", "25"))
# Provider allows 10 req/s per key; stay under it across every player combined.
UPSTREAM_PER_SECOND = float(os.getenv("OPENJEV_MAX_RPS", "8"))

QUESTION_ID = "next_guess"
INSTRUCTIONS = "Choose the strongest next guess given each option's noted strategic value."


@dataclass
class PickResult:
    pick: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    latency_ms: float = 0.0
    attempts: int = 0
    error: str | None = None
    usage: dict | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.pick is not None

    def to_dict(self) -> dict:
        return {
            "pick": self.pick,
            "confidence": self.confidence,
            "probabilities": self.probabilities,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "error": self.error,
        }


class _UpstreamPacer:
    """Spaces upstream calls so all players together stay under the key's rate."""

    def __init__(self, per_second: float) -> None:
        self._interval = 1.0 / per_second
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self._interval
        if delay > 0:
            await asyncio.sleep(delay)


_pacer = _UpstreamPacer(UPSTREAM_PER_SECOND)
_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT_S)
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def build_state(history: list[tuple[str, list[str]]], words_left: int | None) -> dict:
    """The public board: what a spectator could see, nothing more."""
    state: dict = {
        "game": "Wordle: find the secret 5-letter word in 6 guesses",
        "colour_key": "green = right letter, right spot; yellow = in the word, wrong spot; gray = not in the word",
        "guesses_so_far": [
            {"word": g.upper(), "colours": " ".join(pattern)} for g, pattern in history
        ],
        "guesses_left": 6 - len(history),
    }
    if words_left is not None:
        state["common_words_still_possible"] = words_left
    return state


def build_payload(candidates: list[dict], state: dict, rng: random.Random | None = None) -> dict:
    """One `choice` question: options are the words, criteria are their notes.

    Options go in shuffled so the heuristic's order is never a hint, and only
    the factual note is sent, not the viewer-facing role label.
    """
    order = list(candidates)
    (rng or random).shuffle(order)
    criteria = {c["word"].upper(): c["note"] for c in order}
    return {
        "model": MODEL,
        "state": state,
        "questions": {
            QUESTION_ID: {"type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria},
        },
    }


def parse_answer(body: dict, options: list[str]) -> tuple[str, float | None, dict[str, float]]:
    answers = body.get("answers")
    answer = answers.get(QUESTION_ID) if isinstance(answers, dict) else None
    if not isinstance(answer, dict):
        raise ValueError("Response has no answer for the choice question.")

    raw = answer.get("probabilities") if isinstance(answer.get("probabilities"), dict) else {}
    probs = {}
    for option in options:
        value = raw.get(option)
        probs[option] = min(1.0, max(0.0, float(value))) if isinstance(value, (int, float)) else 0.0

    choice = answer.get("choice")
    if isinstance(choice, str):
        choice = choice.strip().upper()
    if choice not in probs:
        # A choice outside the options would be unplayable; fall back to the
        # option Jev itself rated highest, which is still Jev's call.
        if not any(probs.values()):
            raise ValueError("Response picked no listed option and gave no probabilities.")
        choice = max(options, key=lambda o: probs[o])

    conf = answer.get("confidence")
    conf = min(1.0, max(0.0, float(conf))) if isinstance(conf, (int, float)) else None
    return choice, conf, probs


class _Retryable(Exception):
    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


async def _call_once(payload: dict, api_key: str) -> dict:
    await _pacer.wait()
    try:
        resp = await _http().post(
            f"{BASE_URL}/systemone",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except httpx.HTTPError as exc:
        raise _Retryable(f"network error: {type(exc).__name__}") from exc

    if resp.status_code == 429 or resp.status_code >= 500:
        retry_after = resp.headers.get("Retry-After", "")
        wait = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 0.5
        raise _Retryable(f"upstream HTTP {resp.status_code}", retry_after=min(wait, 3.0))
    if resp.status_code >= 400:
        # 401/422 won't fix themselves on a retry; surface the reason.
        raise RuntimeError(f"upstream HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise _Retryable("upstream returned non-JSON") from exc


async def pick_guess(
    candidates: list[dict],
    history: list[tuple[str, list[str]]] | None = None,
    words_left: int | None = None,
) -> PickResult:
    """Ask Jev to choose one word from the shortlist, in ONE request.

    Returns the pick, Jev's confidence, the probability for every option and
    the latency. Retries once on transient failures. Never raises: a failure
    comes back as `PickResult.error` so the game can fall back openly.
    """
    result = PickResult()
    if not candidates:
        result.error = "empty shortlist"
        return result

    api_key = os.getenv("OPENJEV_API_KEY", "")
    if not api_key:
        result.error = "OPENJEV_API_KEY is not set"
        return result

    options = [c["word"].upper() for c in candidates]
    payload = build_payload(candidates, build_state(history or [], words_left))
    started = time.perf_counter()
    for attempt in (1, 2):
        result.attempts = attempt
        try:
            body = await _call_once(payload, api_key)
            result.pick, result.confidence, result.probabilities = parse_answer(body, options)
            result.usage = body.get("usage")
            result.error = None
            break
        except _Retryable as exc:
            result.error = str(exc)
            log.warning("pick attempt %d failed: %s", attempt, exc)
            if attempt == 1 and exc.retry_after:
                await asyncio.sleep(exc.retry_after)
        except (RuntimeError, ValueError) as exc:
            result.error = str(exc)
            log.warning("pick attempt %d failed: %s", attempt, exc)
            if isinstance(exc, RuntimeError):
                break  # non-retryable client error
    result.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return result
