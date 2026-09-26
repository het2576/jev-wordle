"""Rules, shortlist and routes. Jev is stubbed, so no network or key is needed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import candidate_picker as cp  # noqa: E402
import jev_client  # noqa: E402
import wordle  # noqa: E402

G, Y, X = wordle.GREEN, wordle.YELLOW, wordle.GRAY


# ---------- scoring ----------

@pytest.mark.parametrize(
    "guess, secret, expected",
    [
        ("crane", "crane", [G, G, G, G, G]),
        ("crane", "react", [Y, Y, G, X, Y]),
        ("geese", "those", [X, X, X, G, G]),  # two extra E's, secret's one E is taken by the green
        ("speed", "abide", [X, X, Y, X, Y]),  # two E's guessed, one in secret: one yellow only
        ("hello", "world", [X, X, X, G, Y]),
        ("lolly", "world", [X, G, X, G, X]),
        ("abbey", "kebab", [Y, Y, G, Y, X]),  # doubled B in both
        ("eerie", "elder", [G, Y, Y, X, X]),  # third E has no copy left
    ],
)
def test_score_guess_matches_wordle(guess, secret, expected):
    assert wordle.score_guess(guess, secret) == expected


def test_filter_keeps_secret_and_only_consistent_words():
    secret = "shout"
    history = [(g, wordle.score_guess(g, secret)) for g in ("crane", "pilot")]
    left = wordle.filter_candidates(wordle.word_list(), history)
    assert secret in left
    for word in left:
        for guess, pattern in history:
            assert wordle.score_guess(guess, word) == pattern


def test_word_lists_are_consistent():
    assert len(wordle.answer_list()) == 2315
    assert len(wordle.word_list()) == 12972
    assert wordle.answer_set() <= wordle.valid_words()
    assert wordle.pick_secret() in wordle.answer_set()


def test_letter_states_prefers_best_colour():
    history = [("speed", wordle.score_guess("speed", "abide"))]
    assert wordle.letter_states(history)["e"] == Y
    history.append(("eerie", wordle.score_guess("eerie", "abide")))
    assert wordle.letter_states(history)["e"] == G


# ---------- shortlist ----------

def _shortlist(secret, guesses):
    history = [(g, wordle.score_guess(g, secret)) for g in guesses]
    remaining = wordle.filter_candidates(wordle.word_list(), history)
    tried = {c for g in guesses for c in g}
    return cp.select_candidates(remaining, tried, common_words=wordle.answer_set()), remaining


def test_shortlist_opening_is_capped_varied_and_led_by_top_score():
    picks, remaining = _shortlist("shout", [])
    words = [p["word"] for p in picks]
    assert 3 <= len(picks) <= cp.MAX_SHORTLIST
    assert len(set(words)) == len(words)
    assert picks[0]["role"] == cp.ROLE_TOP
    common = [w for w in remaining if w in wordle.answer_set()]
    best = max(cp.letter_score(w, set()) for w in common)
    assert cp.letter_score(picks[0]["word"], set()) == best
    assert any(p["role"] == cp.ROLE_COVERAGE for p in picks)


def test_shortlist_offers_direct_answers_when_few_remain():
    picks, remaining = _shortlist("shout", ["crane", "pilot"])
    roles = [p["role"] for p in picks]
    assert roles.count(cp.ROLE_ANSWER) in (1, 2)
    for p in picks:
        if p["role"] == cp.ROLE_ANSWER:
            assert p["word"] in remaining and p["fits"]


def test_coverage_words_overlap_top_pick_by_at_most_one_letter():
    picks, _ = _shortlist("shout", ["crane"])
    top = set(picks[0]["word"])
    for p in picks:
        if p["role"] == cp.ROLE_COVERAGE:
            assert len(set(p["word"]) & top) <= 1


def test_every_note_is_nonempty_and_carries_no_ranking_label():
    for guesses in ([], ["crane"], ["crane", "pilot"]):
        picks, _ = _shortlist("shout", guesses)
        for p in picks:
            assert p["note"] and p["label"] == cp.ROLE_LABELS[p["role"]]
            assert p["word"].upper() not in p["note"]
            for label in cp.ROLE_LABELS.values():
                assert label.lower() not in p["note"].lower()
            assert "top pick" not in p["note"].lower()


def test_payload_sends_notes_not_labels_in_shuffled_order():
    import random

    picks, _ = _shortlist("shout", ["crane"])
    orders = set()
    for seed in range(8):
        q = jev_client.build_payload(picks, {}, random.Random(seed))["questions"][jev_client.QUESTION_ID]
        orders.add(tuple(q["criteria"]))
        assert set(q["criteria"].values()) == {p["note"] for p in picks}
    assert len(orders) > 1


def test_single_answer_left_is_offered():
    picks, remaining = _shortlist("tonal", ["atone", "talon"])
    common = [w for w in remaining if w in wordle.answer_set()]
    assert common == ["tonal"]
    assert picks[0]["word"] == "tonal"


# ---------- Jev client parsing ----------

def test_payload_is_one_choice_question_with_notes_as_criteria():
    cands = [{"word": "atone", "note": "a"}, {"word": "shirk", "note": "b"}]
    payload = jev_client.build_payload(cands, jev_client.build_state([], 2315))
    q = payload["questions"][jev_client.QUESTION_ID]
    assert q["type"] == "choice"
    assert q["criteria"] == {"ATONE": "a", "SHIRK": "b"}
    assert q["instructions"] == jev_client.INSTRUCTIONS
    assert set(payload) == {"model", "state", "questions"}


def test_parse_answer_normalises_and_falls_back_to_argmax():
    body = {"answers": {"next_guess": {"choice": "bogus", "probabilities": {"ATONE": 0.3, "SHIRK": 0.7}, "confidence": 0.5}}}
    choice, conf, probs = jev_client.parse_answer(body, ["ATONE", "SHIRK"])
    assert choice == "SHIRK" and conf == 0.5 and probs == {"ATONE": 0.3, "SHIRK": 0.7}


def test_parse_answer_rejects_empty():
    with pytest.raises(ValueError):
        jev_client.parse_answer({"answers": {}}, ["ATONE"])


# ---------- routes ----------

@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient

    import main

    calls = {"n": 0, "fail": False}

    async def fake_pick(candidates, history=None, words_left=None):
        calls["n"] += 1
        if calls["fail"]:
            return jev_client.PickResult(error="upstream HTTP 503", attempts=2)
        # Deterministic stub: favour the last option, so it differs from the heuristic top.
        n = len(candidates)
        probs = {c["word"].upper(): (0.5 if i == n - 1 else 0.5 / max(1, n - 1)) for i, c in enumerate(candidates)}
        if n == 1:
            probs = {candidates[0]["word"].upper(): 1.0}
        pick = candidates[-1]["word"].upper()
        return jev_client.PickResult(pick=pick, confidence=0.4, probabilities=probs, latency_ms=12.0, attempts=1)

    monkeypatch.setattr(jev_client, "pick_guess", fake_pick)
    with TestClient(main.app) as c:
        c.calls = calls
        yield c


def _new(client):
    return client.post("/api/new-game").json()["game_id"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_secret_never_reaches_browser_or_jev(client, monkeypatch):
    import main

    seen = []
    real = jev_client.pick_guess

    async def spy(candidates, history=None, words_left=None):
        seen.append(repr(jev_client.build_state(history or [], words_left)).lower())
        return await real(candidates, history, words_left)

    monkeypatch.setattr(jev_client, "pick_guess", spy)
    body = client.post("/api/new-game").json()
    assert body["secret"] is None and body["status"] == "playing"
    secret = main.store.get(body["game_id"]).secret
    turn = client.post("/api/next-guess", json={"game_id": body["game_id"]}).json()
    if turn["turn"]["pick"]["word"].lower() != secret:
        assert secret.upper() not in str(turn)
    # The secret can appear as an option (it's a common word), never in the state.
    assert seen and all(secret not in state for state in seen)


def test_next_guess_is_idempotent_until_submitted(client):
    gid = _new(client)
    a = client.post("/api/next-guess", json={"game_id": gid}).json()["turn"]
    b = client.post("/api/next-guess", json={"game_id": gid}).json()["turn"]
    assert a == b and client.calls["n"] == 1
    assert a["pick"]["source"] == "jev"
    assert a["pick"]["word"] == a["candidates"][-1]["word"]
    assert all(c["p"] is not None for c in a["candidates"])


def test_submit_only_accepts_the_pending_pick(client):
    gid = _new(client)
    assert client.post("/api/submit-guess", json={"game_id": gid, "word": "crane"}).status_code == 409
    turn = client.post("/api/next-guess", json={"game_id": gid}).json()["turn"]
    other = next(c["word"] for c in turn["candidates"] if c["word"] != turn["pick"]["word"])
    assert client.post("/api/submit-guess", json={"game_id": gid, "word": other}).status_code == 409
    ok = client.post("/api/submit-guess", json={"game_id": gid, "word": turn["pick"]["word"]})
    assert ok.status_code == 200 and len(ok.json()["pattern"]) == 5


def test_full_game_ends_and_reveals_summary(client):
    gid = _new(client)
    for _ in range(wordle.MAX_GUESSES):
        turn = client.post("/api/next-guess", json={"game_id": gid}).json()["turn"]
        body = client.post("/api/submit-guess", json={"game_id": gid, "word": turn["pick"]["word"]}).json()
        if body["game"]["status"] != "playing":
            break
    game = body["game"]
    assert game["status"] in ("won", "lost")
    assert game["secret"] and len(game["turns"]) == game["guesses_used"]
    assert client.post("/api/next-guess", json={"game_id": gid}).status_code == 409


def test_fallback_is_labelled_not_attributed_to_jev(client):
    client.calls["fail"] = True
    gid = _new(client)
    turn = client.post("/api/next-guess", json={"game_id": gid}).json()["turn"]
    assert turn["fallback"] is True
    assert turn["pick"]["source"] == "heuristic"
    assert turn["pick"]["word"] == turn["heuristic_top"]
    assert turn["pick"]["p"] is None and turn["note"]


def test_bad_game_id_is_404(client):
    assert client.post("/api/next-guess", json={"game_id": "nope"}).status_code == 404


def test_rate_limit_returns_429():
    from rate_limit import SlidingWindowLimiter

    limiter = SlidingWindowLimiter(limit=2, window_s=60)
    assert limiter.hit("1.2.3.4")[0] and limiter.hit("1.2.3.4")[0]
    allowed, retry = limiter.hit("1.2.3.4")
    assert not allowed and retry >= 1
    assert limiter.hit("5.6.7.8")[0]


# ---------- You vs Jev ----------

def _match(client):
    return client.post("/api/versus/new").json()


def _secret(match_id):
    import main

    return main.store.get_match(match_id).secret


def test_versus_hides_secret_and_jev_letters_until_over(client):
    m = _match(client)
    assert m["secret"] is None and m["phase"] == "you" and m["round"] == 1
    r = client.post("/api/versus/guess", json={"match_id": m["match_id"], "word": "crane"})
    assert r.status_code == 200 and len(r.json()["pattern"]) == 5
    body = client.post("/api/versus/jev-turn", json={"match_id": m["match_id"]}).json()["match"]
    turn = body["jev"]["turns"][0]
    if body["phase"] != "over":
        assert turn["masked"] and "word" not in str(turn["candidates"]) and "note" not in str(turn)
        assert sum(c["chosen"] for c in turn["candidates"]) == 1
        assert body["secret"] is None


def test_versus_enforces_turn_order_and_real_words(client):
    mid = _match(client)["match_id"]
    assert client.post("/api/versus/jev-turn", json={"match_id": mid}).status_code == 409
    bad = client.post("/api/versus/guess", json={"match_id": mid, "word": "zzzzz"})
    assert bad.status_code == 422 and bad.json()["detail"] == "Not in word list"
    assert client.post("/api/versus/guess", json={"match_id": mid, "word": "crane"}).status_code == 200
    assert client.post("/api/versus/guess", json={"match_id": mid, "word": "slate"}).status_code == 409


def test_versus_you_win_when_only_you_solve(client, monkeypatch):
    mid = _match(client)["match_id"]
    secret = _secret(mid)
    client.post("/api/versus/guess", json={"match_id": mid, "word": secret})
    body = client.post("/api/versus/jev-turn", json={"match_id": mid}).json()["match"]
    assert body["phase"] == "over"
    assert body["result"] in ("you", "draw")  # draw only if Jev also found it in one
    assert body["secret"] == secret.upper()
    assert "word" in body["jev"]["turns"][0]["pick"]  # revealed at the end
    assert client.post("/api/versus/guess", json={"match_id": mid, "word": "crane"}).status_code == 409


def test_versus_runs_six_rounds_then_ends(client):
    mid = _match(client)["match_id"]
    secret = _secret(mid)
    wrong = next(w for w in ("fuzzy", "jazzy", "civic") if w != secret)
    for _ in range(6):
        client.post("/api/versus/guess", json={"match_id": mid, "word": wrong})
        body = client.post("/api/versus/jev-turn", json={"match_id": mid}).json()["match"]
        if body["phase"] == "over":
            break
    assert body["phase"] == "over"
    assert body["result"] in ("jev", "none")
    assert len(body["you"]["guesses"]) == len(body["jev"]["turns"])


def test_settle_round_draw():
    from games import Game, Match

    m = Match(id="m", secret="crane", you=Game(id="a", secret="crane"), jev=Game(id="b", secret="crane"))
    m.you.apply("crane")
    m.jev.apply("crane")
    m.settle_round()
    assert m.phase == "over" and m.result == "draw"
