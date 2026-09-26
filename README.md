# Jev Wordle

Wordle, played live by Jev, TypeSafe's System One model. Every turn, the game
builds a short list of strong candidate words, asks Jev once to choose between
them, shows the probability Jev gave every option, and then plays Jev's pick.
The tiles flip exactly as in the real game.

The colours are deterministic Wordle rules, so the only open question each
turn is which word gets played. That's the decision Jev makes, and it's shown
in full before the tiles flip.

## What this is, and what it isn't

- **It's not an information-theory-optimal solver.** Jev chooses from a short
  list of words picked by a standard letter-frequency heuristic. It doesn't
  search all 12,972 words for the guess with the most expected information.
- **The shortlist is what gives Jev a fair shot at playing well.** The
  heuristic hands over a strong, varied hand every turn: the best
  letter-score word, likely answers once few remain, and words with
  deliberately different letters. It never picks the answer for Jev.
- **Jev's pick from that shortlist is the real, unscripted part.** One
  `choice` call per turn, and Jev's `choice` is played as returned. Nothing
  re-ranks it, overrides it or retries until it's "good".
- **Jev never sees the secret word.** It sees what a spectator sees: the
  guesses so far, their colours, how many common words still fit, and each
  option's factual note.

## Two modes

- **Watch Jev** (`/`): Jev plays alone. Every turn shows the full shortlist,
  Jev's probability for each word, its pick, and the tiles flipping.
- **You vs Jev** (`/versus`): you and Jev chase the same secret word, in
  rounds. You type a guess, then Jev plays its own guess for that round, using
  the same one-call choice as Watch Jev. Solving in fewer guesses wins, and
  solving in the same round is a draw. It's fair both ways: Jev never sees your
  board, and you see only Jev's colours and how it weighed its options, never
  its letters or notes. Everything is revealed when the match ends, including
  Jev's reasoning for every round. Your wins, Jev's wins and draws are kept in
  this browser for the session.

## How one turn works

1. The game filters the full 12,972-word list down to the words consistent
   with every colour seen so far. It re-scores each candidate against each
   past guess, which gets duplicate letters right in every case.
2. `candidate_picker.py` builds a shortlist of up to 6 common words (details
   below) and writes a factual note for each one, for example: *"Tests 3
   letters SHOUT doesn't (D, G, B); can't be the answer (breaks a clue)."*
3. **One request** goes to Jev: a single `choice` question. The options are
   the words, each word's note is its criterion, and the instructions are
   *"Choose the strongest next guess given each option's noted strategic
   value."*
4. Jev returns its choice, a probability for every option, and a confidence
   figure.
5. The browser deals the options onto the rack, grows the probability bars,
   highlights Jev's pick, flies its letters into the grid, and flips the
   tiles. If Jev's call fails after one retry, the heuristic's top word is
   played instead, and the turn is clearly labelled as not Jev's decision.

### The shortlist heuristic (PRD section 3)

| Slot | Rule | Label viewers see |
|---|---|---|
| 1 | Highest score among the common words that fit every clue. The score is the sum of the standard English frequencies (Lewand's table) of the letters the word would test for the first time. When 300 or fewer words remain, each letter is also weighted by how evenly it splits them (4p(1−p)), so a letter that's in every remaining word, or in none, counts for nothing | Top letter score |
| 2–3 | When 15 or fewer common words still fit: one or two of them as direct answers, ranked by how typical their letter positions are | Possible answer |
| 4–5 | One or two common words that share at most one letter with the top word, chosen for new letters even if they can't be the answer | Different letters |
| rest | The next-strongest fitting words, skipping any that would test exactly the same new letters | Strong alternative |

Every word shown is from the 2,315-word common answer list, so the options
read naturally. The full 12,972-word list still decides what "fits every
clue" means.

Checked offline over 200 random secrets: always playing the top word wins 98%
in 3.69 guesses on average. A **random** pick from the same shortlist still
wins 100%, in 3.99 guesses. So the hand is strong either way, and the useful
question is whether Jev picks better than chance.

## Does Jev actually decide?

These are headless games against the live endpoint, with the same 40 random
secrets for every row:

| Who picks from the shortlist | Wins | Average guesses | Picked the heuristic's top word |
|---|---|---|---|
| Random pick | 40 / 40 | 4.12 | n/a |
| Always the heuristic's top word | 40 / 40 | 3.42 | 100% |
| **Jev, as shipped** (plain notes, shuffled order) | **40 / 40** | **3.48** | **89%** (103 of 116 turns) |
| Jev, note prefixed with its label, heuristic order | 40 / 40 | 3.42 | 97% |
| Jev, prefixed notes, order reversed | 40 / 40 | 3.40 | 99% |

What this shows, honestly:

- **Jev plays much better than chance**, about 0.64 guesses per game better
  than a random pick from the same hand, and close to the heuristic's own top
  pick.
- **Jev has no position bias.** With the list reversed, it still found the
  top letter-score word 99% of the time, so it reads the options rather than
  their order.
- **A label in the note is a nudge.** When each note began with "Top letter
  score:", Jev mostly followed that ranking. That's a label, not a fact, so
  the shipped version sends only the factual note, in shuffled order. Jev then
  departs from the heuristic on about 1 turn in 9. It usually commits early
  to a plausible answer, occasionally picks a strong alternative, and so far
  has never picked a "different letters" exploration word. That's Jev's call,
  at a small cost (3.48 vs 3.42 guesses).
- Forty games is a small sample, so read differences under about 0.15
  guesses as noise.

## Run it locally

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your key in OPENJEV_API_KEY
uvicorn main:app --app-dir backend --port 8000
```

Open http://localhost:8000. The FastAPI app serves the frontend too, so there
is nothing else to start. Press **Play turn 1**, or turn on **Auto-play**.
Keyboard: Enter or Space plays a turn, N starts a new game, A toggles
auto-play. For **You vs Jev**, open http://localhost:8000/versus and type
your guesses with your keyboard or the on-screen keys.

Tests (Jev is stubbed, so no network or key is needed):

```bash
python -m pytest tests
```

To see the hand-checked scoring cases (including duplicate letters) and a
mid-game shortlist:

```bash
python backend/wordle.py
python backend/candidate_picker.py
```

## Deploy (Render)

`render.yaml` describes the service, so deploying takes a few clicks:

1. Push this folder to a GitHub repository. `.env` is git-ignored, so your
   key stays on your machine.
2. On [render.com](https://render.com), choose **New > Blueprint**, pick the
   repository, and apply it.
3. When Render asks for `OPENJEV_API_KEY`, paste your key.
4. Once it's live, share `https://<your-service>.onrender.com` (Watch Jev)
   and `https://<your-service>.onrender.com/versus` (You vs Jev).

Before sharing publicly:

- **It runs as one process on purpose.** Games are in memory, so a restart or
  redeploy ends games in progress. Don't scale to several instances without
  adding shared storage.
- **The free plan sleeps after 15 minutes idle.** The first visit after that
  takes about a minute to wake up. A paid instance stays awake.
- **Every Jev turn is billed to your key.** It costs roughly $0.00002 per call.
  Per-IP limits and a global pace of 8 calls per second cap how fast one
  person, or everyone together, can spend it.
- `TRUST_PROXY_HEADERS=1` is set in `render.yaml`, so each player gets their
  own rate limit instead of everyone sharing the proxy's.

## Architecture

```
Browser (Wordle grid + Jev's shortlist rack)
        |  fetch()
        v
FastAPI backend
  |- wordle.py            scoring, candidate filtering, secret pick
  |- candidate_picker.py  heuristic shortlist + factual notes
  |- jev_client.py        ONE choice call per turn, one retry, never raises
  |- games.py             in-memory games and You-vs-Jev matches; the secret stays here
  |- rate_limit.py        per-IP sliding window, one bucket per route
        |
        v
Jev-compatible endpoint (shape verified with a manual call first)
```

| Route | Does | Per-IP limit |
|---|---|---|
| `GET /health` | Liveness check plus word-list sizes | none |
| `POST /api/new-game` | Picks a secret and returns the empty board (secret hidden) | 15/min |
| `POST /api/next-guess` | `{game_id}`: filters, builds the shortlist, makes one Jev call, returns every option with its probability plus the chosen word. Calling it again before submitting returns the same turn without a second upstream call | 30/min |
| `POST /api/submit-guess` | `{game_id, word}`: scores the pending pick against the secret and returns the colours, updated board and win/loss. Only this turn's pick is accepted, so the secret can't be probed with arbitrary guesses | 60/min |

You vs Jev:

| Route | Does | Per-IP limit |
|---|---|---|
| `POST /api/versus/new` | Starts a match: one secret, two boards | 15/min |
| `POST /api/versus/guess` | `{match_id, word}`: your guess for the round. Returns 422 `Not in word list` for words outside the 12,972-word list | 60/min |
| `POST /api/versus/jev-turn` | `{match_id}`: Jev's guess for the round (one Jev call), then settles the round. While the match is live, Jev's turns come back masked: colours, labels and probabilities only | 30/min |

The server enforces the order (you, then Jev, each round), so neither side can
get ahead.

All limits can be overridden in `.env` (`RATE_LIMIT_NEXT_GUESS=20` and so on).
Upstream calls are also paced globally under the key's 10 requests per second.

Games live in memory, expire after an hour of inactivity, and are lost on
restart. Run a single process, or add shared storage before scaling out.

## Design

The page is built around one repeated beat: the shortlist is dealt onto a
tile rack, the bars show Jev's probabilities, the chosen word lifts, its
letters fly into the grid, and the tiles flip (colour revealed at the
midpoint). The full plan, the motion timings and the critical review are in
[`docs/DESIGN.md`](docs/DESIGN.md). It respects `prefers-reduced-motion`, and
it has a high-contrast (orange and blue) mode.

## Endpoint and credit

- **Provider:** [OpenJEV](https://openjev.tech/docs), a third-party,
  community-run public interface to Jev. It is not operated by TypeSafe. Calls
  go to `POST https://api.openjev.sh/v1/systemone` with
  `Authorization: Bearer <key>`. The request and response shape (a `choice`
  question with `criteria`, answered with `choice`, `probabilities` and
  `confidence`) was confirmed with a manual call before the client was
  written. Responses report `"provider": "TypeSafe"`.
- **Model:** Jev, by TypeSafe. The primary source for how `choice` questions,
  state and confidence work is TypeSafe's official documentation:
  **https://docs.typesafe.ai**.
- **Word lists:** the widely used original Wordle lists, 2,315 answers and
  10,657 further valid guesses, from cfreshman's public gists
  ([answers](https://gist.github.com/cfreshman/a03ef2cba789d8cf00c08f767e0fad7b),
  [allowed guesses](https://gist.github.com/cfreshman/cdcdf777450c5b5301e439061d29694c)).
- Wordle is a trademark of The New York Times Company. This is an independent
  fan project and isn't affiliated with it.
