"""Heuristic shortlist: a strong, varied hand of words for Jev to choose from.

This picks the options, never the answer. Rules (PRD section 3):

- Score words by the standard English frequency of the letters they would
  test for the first time. It's a cheap stand-in for information gain.
- Always include the single highest-scoring word that fits every clue.
- When 15 or fewer common words still fit, add 1-2 of them as direct answers.
- Add 1-2 words with deliberately different letters from the top pick, even
  if they can't be the answer, so there's a real "explore or commit" trade-off.
- Fill with other strong words, up to 6 in total.

Every word shown is a common word (the answer list), so the shortlist reads
naturally. The full 13k list is still what decides which words fit the clues.
Run `python backend/candidate_picker.py` to print a mid-game example.
"""

from __future__ import annotations

from collections import Counter

# Lewand's standard English letter frequencies, percent of running text.
LETTER_FREQ = {
    "e": 12.70, "t": 9.06, "a": 8.17, "o": 7.51, "i": 6.97, "n": 6.75, "s": 6.33,
    "h": 6.09, "r": 5.99, "d": 4.25, "l": 4.03, "c": 2.78, "u": 2.76, "m": 2.41,
    "w": 2.36, "f": 2.23, "g": 2.02, "y": 1.97, "p": 1.93, "b": 1.29, "v": 0.98,
    "k": 0.77, "j": 0.15, "x": 0.15, "q": 0.10, "z": 0.07,
}
VOWELS = set("aeiouy")
MAX_SHORTLIST = 6
DIRECT_ANSWER_THRESHOLD = 15

ROLE_TOP = "top"          # highest letter score among words that fit
ROLE_ANSWER = "answer"    # plausible direct answer
ROLE_COVERAGE = "coverage"  # different letters from the top pick
ROLE_STRONG = "strong"    # next-best letter score, fills the hand

# Shown to viewers only. Jev gets the plain note: in a 40-game test, putting
# "Top letter score:" in front of the note made Jev copy the heuristic's
# ranking 96% of the time (README, "Does Jev actually decide?").
ROLE_LABELS = {
    ROLE_TOP: "Top letter score",
    ROLE_ANSWER: "Possible answer",
    ROLE_COVERAGE: "Different letters",
    ROLE_STRONG: "Strong alternative",
}


def untested(word: str, tried: set[str]) -> list[str]:
    """Distinct letters in `word` not tried yet, most common first."""
    return sorted({c for c in word if c not in tried}, key=lambda c: -LETTER_FREQ[c])


def letter_score(word: str, tried: set[str], weights: dict[str, float] | None = None) -> float:
    """Sum of the frequency of each new letter, counted once per word.

    `weights` scales a letter by how useful testing it would be right now. A
    letter that appears in none of the words still in play would teach us
    nothing, so it's worth nothing, however common it is in English.
    """
    w = weights or {}
    return sum(LETTER_FREQ[c] * w.get(c, 1.0) for c in untested(word, tried))


def split_weights(pool: list[str], tried: set[str]) -> dict[str, float]:
    """How well each untested letter would split the words still in play.

    A letter in half the words halves the list whichever colour comes back
    (weight 1.0). A letter in every word, or in none, splits nothing (0). This
    is 4p(1-p): the same shape as the information from a yes/no question,
    without a full entropy calculation over every colour pattern.
    """
    if len(pool) < 2:
        return {}
    counts = Counter(c for word in pool for c in set(word))
    n = len(pool)
    return {c: 4 * (counts[c] / n) * (1 - counts[c] / n) for c in LETTER_FREQ if c not in tried}


def positional_fit(pool: list[str]) -> dict[str, float]:
    """How typical each word's letter-in-position pattern is for the pool.

    Used to rank plausible answers and to break ties: a word whose letters sit
    where most of the remaining words have them is the likelier answer.
    """
    by_pos = [Counter(w[i] for w in pool) for i in range(5)]
    return {w: sum(by_pos[i][c] for i, c in enumerate(w)) / max(1, len(pool)) for w in pool}


def _fmt(letters: list[str]) -> str:
    return ", ".join(c.upper() for c in letters)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def select_candidates(
    remaining_words: list[str],
    guessed_letters: set[str],
    *,
    common_words: frozenset[str] | set[str] | None = None,
    max_size: int = MAX_SHORTLIST,
) -> list[dict]:
    """Build the shortlist: [{word, note, role, label, fits}], strongest-first by role.

    `note` is the factual line Jev reads. `label` names the role for viewers.

    `remaining_words` fit every clue so far (filtered from the full list).
    `common_words` is the answer list: plausible answers come from where the
    two overlap, and coverage words can be any common word, fitting or not.
    """
    tried = {c.lower() for c in guessed_letters}
    remaining = [w.lower() for w in remaining_words]
    common = frozenset(common_words) if common_words is not None else frozenset(remaining)
    plausible = [w for w in remaining if w in common] or remaining
    if not plausible:
        return []

    fit = positional_fit(plausible)
    weights = split_weights(plausible, tried) if len(plausible) <= 300 else None
    remaining_set = set(remaining)

    def score(word: str) -> float:
        return letter_score(word, tried, weights)

    def rank(word: str) -> tuple:
        return (score(word), fit.get(word, 0.0), word)

    shortlist: list[dict] = []
    used: set[str] = set()

    def add(word: str, role: str, note: str) -> None:
        note = note[0].upper() + note[1:]
        shortlist.append({"word": word, "role": role, "label": ROLE_LABELS[role], "note": note, "fits": word in remaining_set})
        used.add(word)

    n_left = len(plausible)
    no_clues = not tried
    if no_clues:
        left_note = "no clues yet, so any common word could be the answer"
    elif n_left == 1:
        left_note = "the only common word that fits every clue"
    else:
        left_note = f"fits every clue ({n_left} common words still do)"

    # 1. The top letter-score word among those that could still be the answer.
    top = max(plausible, key=rank)
    new = untested(top, tried)
    if new and n_left > 1:
        add(top, ROLE_TOP, f"tests {_plural(len(new), 'common untested letter')} ({_fmt(new)}); {left_note}")
    else:
        add(top, ROLE_TOP, left_note)

    # 2. Direct answers once the field is small enough to just go for it.
    if 1 < n_left <= DIRECT_ANSWER_THRESHOLD:
        answers = sorted((w for w in plausible if w not in used), key=lambda w: (-fit[w], w))
        for word in answers[: 2 if n_left > 2 else 1]:
            add(word, ROLE_ANSWER, f"fits every clue, plausible direct answer (1 of {n_left} common words left)")

    # 3. Coverage: letters the top pick doesn't test, fitting or not.
    top_letters = set(top)
    probe_pool = sorted(common)
    coverage_slots = 2 if n_left > 2 else 1
    for _ in range(coverage_slots):
        if len(shortlist) >= max_size or n_left == 1:
            break
        taken = set().union(*(set(item["word"]) for item in shortlist if item["role"] == ROLE_COVERAGE)) if shortlist else set()
        best, best_key = None, None
        for word in probe_pool:
            if word in used:
                continue
            letters = set(word)
            if len(letters & top_letters) > 1 or len(letters & taken) > 1:
                continue
            key = (letter_score(word, tried | top_letters, weights), score(word), word in remaining_set, word)
            if key[0] <= 0:
                continue
            if best_key is None or key > best_key:
                best, best_key = word, key
        if best is None:
            break
        fresh = [c for c in untested(best, tried) if c not in top_letters]
        top_vowels = {c for c in top if c in VOWELS}
        new_vowels = [c for c in fresh if c in VOWELS and c not in top_vowels]
        if new_vowels and len(new_vowels) >= 2:
            lead = f"covers different vowels than {top.upper()} ({_fmt(new_vowels)}), plus {_fmt([c for c in fresh if c not in new_vowels]) or 'nothing else new'}"
        else:
            lead = f"tests {_plural(len(fresh), 'letter')} {top.upper()} doesn't ({_fmt(fresh)})"
        if no_clues:
            tail = ""
        elif best in remaining_set:
            tail = "; also fits every clue"
        else:
            tail = "; can't be the answer (breaks a clue)"
        add(best, ROLE_COVERAGE, lead + tail)

    # 4. Fill with the next strongest plausible words, skipping near-duplicates
    #    that would test exactly the same new letters as something already shown.
    seen_sets = {frozenset(untested(item["word"], tried)) for item in shortlist}
    for word in sorted((w for w in plausible if w not in used), key=rank, reverse=True):
        if len(shortlist) >= max_size:
            break
        new = untested(word, tried)
        key = frozenset(new)
        if key in seen_sets and len(plausible) > max_size:
            continue
        seen_sets.add(key)
        if new:
            suffix = "" if no_clues else "; fits every clue"
            add(word, ROLE_STRONG, f"tests {_plural(len(new), 'untested letter')} ({_fmt(new)}){suffix}")
        else:
            add(word, ROLE_STRONG, "Fits every clue; tests no new letters, so it's purely a shot at the answer")

    return shortlist


if __name__ == "__main__":
    import wordle

    secret = "shout"
    history = []
    for guess in ("crane", "pilot"):
        history.append((guess, wordle.score_guess(guess, secret)))
    for label, hist in (("Turn 1", []), ("Turn 2, after CRANE", history[:1]), ("Turn 3, after CRANE, PILOT", history)):
        remaining = wordle.filter_candidates(wordle.word_list(), hist)
        tried = {c for g, _ in hist for c in g}
        picks = select_candidates(remaining, tried, common_words=wordle.answer_set())
        common = sum(1 for w in remaining if w in wordle.answer_set())
        print(f"\n{label}: {len(remaining)} valid words fit, {common} common")
        for item in picks:
            print(f"  {item['word'].upper()}  [{item['label']}]  {item['note']}")
