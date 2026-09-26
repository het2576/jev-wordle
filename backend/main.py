"""Jev Wordle API: game state, the one-call-per-turn Jev choice, and the static frontend.

Run from the repo root:  uvicorn main:app --app-dir backend --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # before importing modules that read env at import time

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import jev_client  # noqa: E402
import wordle  # noqa: E402
from candidate_picker import select_candidates  # noqa: E402
from games import Game, Match, Turn, store  # noqa: E402
from rate_limit import rate_limit  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    wordle.word_list(), wordle.answer_list()  # load the lists once, up front
    yield
    await jev_client.aclose()


app = FastAPI(title="Jev Wordle", lifespan=lifespan)


class GameRequest(BaseModel):
    game_id: str = Field(min_length=1, max_length=64)


class GuessRequest(GameRequest):
    word: str = Field(min_length=5, max_length=5, pattern="^[A-Za-z]{5}$")


class MatchRequest(BaseModel):
    match_id: str = Field(min_length=1, max_length=64)


class MatchGuessRequest(MatchRequest):
    word: str = Field(min_length=5, max_length=5, pattern="^[A-Za-z]{5}$")


def _load(game_id: str) -> Game:
    game = store.get(game_id)
    if game is None:
        raise HTTPException(404, "Game not found or expired. Start a new game.")
    return game


def _ensure_playing(game: Game) -> None:
    if game.status != "playing":
        raise HTTPException(409, "This game is already over. Start a new game.")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "words": len(wordle.word_list()), "answers": len(wordle.answer_list())}


@app.post("/api/new-game", dependencies=[Depends(rate_limit("new_game", 15))])
async def new_game() -> dict:
    game = store.create()
    return game.public()


@app.post("/api/next-guess", dependencies=[Depends(rate_limit("next_guess", 30))])
async def next_guess(req: GameRequest) -> dict:
    """Build the shortlist, ask Jev once, and hold the pick until it's submitted.

    Asking again before submitting returns the same turn, so a retried
    request never spends a second upstream call or changes Jev's answer.
    """
    game = _load(req.game_id)
    _ensure_playing(game)
    async with game.lock:
        if game.pending is None:
            game.pending = await _build_turn(game)
        return {"game": game.public(), "turn": game.pending.public()}


async def _build_turn(game: Game) -> Turn:
    common_left = len(game.common_remaining)
    candidates = select_candidates(game.remaining, game.tried_letters, common_words=wordle.answer_set())
    result = await jev_client.pick_guess(candidates, history=game.history, words_left=common_left)

    note = None
    if result.ok:
        pick, source = result.pick.lower(), "jev"
        probs = {w.lower(): p for w, p in result.probabilities.items()}
    else:
        # Out in the open: the heuristic's own top word is played and the UI
        # says so. It's never shown as Jev's decision.
        pick, source, probs = candidates[0]["word"], "heuristic", {}
        note = "Jev didn't answer after one retry, so this turn plays the top letter-score word instead."

    for c in candidates:
        c["p"] = probs.get(c["word"]) if probs else None

    return Turn(
        index=len(game.history) + 1,
        candidates=candidates,
        pick=pick,
        source=source,
        confidence=result.confidence,
        latency_ms=result.latency_ms,
        attempts=result.attempts,
        words_left=len(game.remaining),
        common_left=common_left,
        note=note,
    )


@app.post("/api/submit-guess", dependencies=[Depends(rate_limit("submit_guess", 60))])
async def submit_guess(req: GuessRequest) -> dict:
    """Score the pending pick against the real secret.

    Only the word Jev (or the labelled fallback) picked this turn is accepted,
    so the secret can't be probed with arbitrary guesses.
    """
    game = _load(req.game_id)
    _ensure_playing(game)
    async with game.lock:
        turn = game.pending
        if turn is None:
            raise HTTPException(409, "No guess is waiting. Ask Jev for the next guess first.")
        if req.word.lower() != turn.pick:
            raise HTTPException(409, f"This turn's guess is {turn.pick.upper()}, not {req.word.upper()}.")
        pattern = game.submit(turn)
        return {"pattern": pattern, "turn": turn.public(), "game": game.public()}


# ---------- You vs Jev ----------

def _load_match(match_id: str) -> Match:
    match = store.get_match(match_id)
    if match is None:
        raise HTTPException(404, "Match not found or expired. Start a new match.")
    return match


@app.post("/api/versus/new", dependencies=[Depends(rate_limit("versus_new", 15))])
async def versus_new() -> dict:
    return store.create_match().public()


@app.post("/api/versus/guess", dependencies=[Depends(rate_limit("versus_guess", 60))])
async def versus_guess(req: MatchGuessRequest) -> dict:
    """Your guess for this round. Only real words count, as in Wordle."""
    match = _load_match(req.match_id)
    async with match.lock:
        if match.phase == "over":
            raise HTTPException(409, "This match is over. Start a new match.")
        if match.phase != "you":
            raise HTTPException(409, "Jev is still playing this round.")
        word = req.word.lower()
        if word not in wordle.valid_words():
            raise HTTPException(422, "Not in word list")
        pattern = match.you.apply(word)
        match.phase = "jev"
        return {"pattern": pattern, "match": match.public()}


@app.post("/api/versus/jev-turn", dependencies=[Depends(rate_limit("versus_jev", 30))])
async def versus_jev_turn(req: MatchRequest) -> dict:
    """Jev's guess for this round: the same one-call choice as the watch mode."""
    match = _load_match(req.match_id)
    async with match.lock:
        if match.phase != "jev":
            raise HTTPException(409, "It's not Jev's turn.")
        turn = await _build_turn(match.jev)
        match.jev.submit(turn)
        match.settle_round()
        return {"match": match.public()}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/versus")
async def versus_page() -> FileResponse:
    return FileResponse(FRONTEND / "versus.html")


app.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
