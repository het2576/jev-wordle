# Jev Wordle design plan

The hook is one beat, repeated up to six times: Jev is handed a shortlist of
words, weighs them, picks one, and the picked word *physically travels* into
the grid, where its tiles flip to reveal the verdict. Everything on screen
either builds that beat or stays out of its way.

## Subject, audience, job

- **Subject:** Wordle, the most widely known daily word puzzle, played by a
  model making one typed choice per turn.
- **Audience:** people watching a 60–90 s screen recording with the sound off
  (LinkedIn, X), and developers who open the page afterwards.
- **Primary job:** make Jev's decision legible before its consequence. A
  viewer should be able to pause any frame and say "these were the options,
  this is what Jev thought of each, this is what it picked, this is what
  happened."

## Direction: the rack

Wordle's own vocabulary is square letter tiles, so the design borrows the one
object every word-game player already knows for "words you're holding but
haven't played": a tile rack. Every shortlist word is shown as a strip of
five small tiles, the same object as a grid row, just smaller and
unrevealed. When Jev picks, those tiles lift off the rack and land in the
grid. The panel and the board stop being two widgets and become one system.

Everything else stays flat, calm and recognisably Wordle.

### Color

| Token | Hex | Role |
|---|---|---|
| Grape night | `#1C1726` | page ground. A deliberately coloured dark, not a tinted black |
| Slate plum | `#262033` | panel surface, keys |
| Plum line | `#3D3450` | hairlines, empty tile borders |
| Green | `#4FA06A` | right letter, right spot. A cooler emerald than the official app |
| Yellow | `#D4A73A` | in the word, wrong spot. A marigold, a touch warmer than the official app |
| Gray | `#433B52` | not in the word. Tinted to the ground so it recedes |
| Iris | `#A48BFF` | Jev only: the thinking pulse, the chosen card, the chosen bar |
| Ink | `#F4F0FA` / dim `#A99FBC` | text |

The semantic green, yellow and gray keep Wordle's meaning and value order
(green darkest-saturated, yellow brightest, gray lowest), so muscle memory
still works. Iris is the only accent and it always means "this is Jev". It
never appears on a tile, so it can't be confused with a result.

A **high-contrast** toggle swaps green for orange `#F5793A` and yellow for
blue `#85C0F9`, the same pairing the real game uses for colour-blind players.

### Type

- **Jost**, one geometric family throughout (a Futura revival). 700 for
  tiles and the wordmark, 500 for UI, 400 for notes. Futura's round O and
  pointed A and M give the tiles more character than a grotesque would,
  while staying as legible as the original.
- Scale (px): 13, 15, 17, 21, 32 (grid tile letters), 44 (result
  headline). Numbers use tabular figures so percentages don't jitter while
  the bars fill.
- Sentence case everywhere. Uppercase only where the game itself is
  uppercase: letters on tiles and keys.

### Layout

Desktop (≥ 960 px): the board and keyboard sit centred in the left column,
and the rack is on the right, top-aligned with the board. The eye moves from
the rack to the board, and the letters travel the same way.

```
 ▦ Jev Wordle                          [New game]  Auto-play (o)  Contrast
 ───────────────────────────────────────────────────────────────────────
         ┌───────────────────┐            Turn 3                1 2 [3]
         │ T A L O N │  5    │            Jev is choosing between 6 words
         │ A T O N E │ 2315  │   ┌────────────────────────────────────┐
         │ □ □ □ □ □ │       │   │ [T][O][N][A][L]              35%   │
         │ □ □ □ □ □ │       │   │ Top letter score               │
         │ □ □ □ □ □ │       │   │ Tests 1 new letter (L)…        │
         │ □ □ □ □ □ │       │   │ ▬▬▬▬▬▬▬▬▬▬▬▬░░░░░░░░░░░░░░░░░ │
         └───────────────────┘   │ [W][R][I][N][G]  (dashed)     2%   │
     Jev picked TALON at 35%.    │ …                                  │
                                 └────────────────────────────────────┘
     [Q][W][E][R][T][Y][U][I][O][P]     Answered in 454 ms. Confidence 22%.
       [A][S][D][F][G][H][J][K][L]
     [Enter][Z][X][C][V][B][N][M][⌫]    [ Play turn 4 ]
```

- **Words-left column:** a small dim number beside each played row shows how
  many common words still fit after it: 2315 → 5 → 1. That's the whole
  game's progress in one glance, and a screenshot tells the story.
- **Narrator line** under the board, in present tense ("Jev picked TALON at
  35%, the top letter-score word"). With the sound off, it's the
  commentator.
- **Rack rows, not cards:** the shortlist is one panel divided by hairlines.
  Only the chosen word lifts out as a raised card. No per-item shadows or
  boxes.
- **Dashed mini tiles** mark a word that can't be the answer (it breaks a
  clue). That's the "explore vs commit" trade-off, readable without reading
  the note.
- Mobile (< 960 px): board, then narrator, then rack, then a compact keyboard.
  Tile size is fluid (clamp 44–62 px). There's a 16 px side gutter and no
  horizontal scroll.

## Motion: one turn as one sequence

Rough timings at normal pace. Holds are pacing, not decoration, so they stay
under reduced motion.

| # | Stage | Timing | What moves |
|---|---|---|---|
| 0 | Ask | while the call is in flight (~0.5–1.2 s) | Rack border breathes in iris (1.4 s cycle). Ghost rows sit at 30% opacity. Narrator: "Asking Jev to choose between the shortlist." |
| 1 | Deal | 280 ms per row, 90 ms stagger | Rows fade in and rise 6 px, top to bottom. Six rows land in ~0.75 s |
| 2 | Weigh | 600 ms, starts 120 ms after the last row | All probability bars grow from 0 together, ease-out. Percent labels count up with them |
| 3 | Read | 1.4 s hold | Nothing moves. Time to read the notes |
| 4 | Pick | 320 ms, then a 650 ms hold | The chosen row lifts (−3 px, scale 1.02) with an iris ring. The others dim to 45%. Narrator names the pick |
| 5 | Play | 420 ms per letter, 70 ms stagger | Each mini tile's letter flies from the rack to its grid tile (a FLIP transform). The grid tile pops 1 → 1.08 → 1 as it lands |
| 6 | Reveal | 350 ms per tile, 300 ms stagger | 3D flip on the Y axis. Colour switches at 90°, the midpoint, then the tile turns back. The chosen rack row's mini tiles colour in with it |
| 7 | Settle | 250 ms, after the last flip | Keyboard keys take their new colours in guess order (30 ms stagger). The words-left number appears |
| 8 | Result | on a win: tiles hop in sequence (100 ms stagger) | Results view replaces the rack |

A turn takes about 6.5 s plus latency, slow enough to follow and quick enough
not to drag in a recording. Auto-play waits 900 ms between turns.

**Reduced motion:** stages 1, 2, 4 and 7 become instant state changes, and
stages 5 and 6 place the letter and colour without the flight or the flip.
The Read and Pick holds remain.

## Win and loss

- **Win:** "Solved in 3". Below it: the probability Jev gave the winning
  word, then a recap with one line per turn: coloured mini tiles, the
  probability of the pick, which kind of option it was (top letter score,
  possible answer…), and words left after it. Actions: "New game", "Copy
  result" (the classic emoji grid plus Jev's probabilities).
- **Loss:** "Out of guesses. The word was SHOUT", with SHOUT drawn in green
  mini tiles. It gets the same recap, plus the full final shortlist with
  every probability, so the viewer can see whether the answer was on the
  rack and what Jev thought of it. A loss is a finding, not a dead end.

## Review against the brief

**Does it feel like a premium word game or a functional prototype?** The first
draft was a prototype in four places. Here's what changed:

1. **The shortlist was a list of cards.** Six identical rounded boxes with a
   word, a paragraph and a bar is the SaaS card kit, and it reads as a
   dashboard next to a game. **Revised:** words became tile strips on a rack,
   the same object as the grid, and the chosen strip's letters physically fly
   into the row. That's now the one memorable moment, and it's what the demo
   leads with.
2. **Loading was a spinner.** A spinner says "the page is waiting," not "Jev
   is thinking." **Revised:** the rack border breathes in Jev's iris colour
   while the call is in flight, and the narrator says what's being asked.
   Latency now reads as deliberation.
3. **Progress was only the grid.** Nothing showed how much each guess
   narrowed things down, so a good guess and a lucky one looked the same.
   **Revised:** the words-left column (2315 → 5 → 1) and the dashed tiles
   for words that can't be the answer.
4. **The loss screen was a modal with the answer.** **Revised:** the results
   view replaces the rack in place. It keeps the recap and the final
   shortlist so a loss explains itself.

**Cut after review (Chanel's accessory):** confetti on a win, a stats
row with averages above the board, and a per-card hover lift. The win hop is
Wordle's own and enough. Stats belong in the README benchmark. Hover lift would
have competed with the one lift that means something: Jev's pick.

**Checked against generic defaults:** the ground is a coloured plum, not a
black. The single accent is a soft iris, not acid green or vermilion, and it
is reserved for one meaning. There are no uppercase eyebrow labels, no
middle-dot meta strings, no monospace data labels and no arrow-suffixed
buttons. The radius follows hierarchy: tiles 3 px, keys 6 px, the rack
14 px, buttons fully round.

## Changes made while building

Checked with screenshots at 1440 × 900, 390 × 844 and a sweep from 320 to
1280 px wide:

- **The label moved onto the tile line.** With the label on its own line,
  six rack rows ran past the fold at 900 px. The row now reads `[tiles]
  Label … 71%`, with the note below it, and the whole rack fits beside the
  board.
- **Jev never sees the label.** A 40-game test showed that prefixing the note
  with "Top letter score:" made Jev copy the heuristic's ranking 96% of the
  time. The label is for viewers. Jev gets only the factual note, with options
  in shuffled order (see the README).
- **The header condenses on phones.** Below 760 px, "High contrast" becomes
  "Contrast". Below 470 px, the controls move to their own row.

## Second pass: the theme, and You vs Jev

### Theme

The first build was correct but flat. The second pass keeps every token's
meaning and adds depth where it helps:

- **Tiles and keys are pieces.** Each has a lit top edge and a shaded bottom
  edge (`--piece-edge`), so revealed tiles read as physical game pieces. That
  fits the rack idea. Keys press down 2 px when you hit them.
- **The ground has light.** A soft iris glow falls from above the header, with
  faint green and marigold washes at the edges. It's the three semantic
  colours as atmosphere, never behind a tile.
- **The chrome is quieter and more premium.** The header is frosted glass and
  sticky on desktop, static on phones. The mode switcher is a segmented pill.
  The primary button is an iris gradient with an inner highlight, and panels
  get a lit top edge and a long, soft shadow.
- **What stayed:** one family (Jost), one accent meaning "Jev", Wordle's
  colour semantics, and the rule that iris never touches a tile.

### You vs Jev

```
 You  (You, your move)  2       Round 3 of 6       1  Jev (4 words left) (J)
 ┌ your board, full size ───────┐   ┌ Jev's board ─────────────────┐
 │ C R A N E   127 left         │   │ ■ ■ ■ ■ ■  colours only      │
 │ P I L O T     2 left         │   │ ■ ■ ■ ■ ■                    │
 │ _ _ _ _ _  ← you type here   │   │ Top letter score  ▬▬▬▬▬  73% │
 └──────────────────────────────┘   │ Different letters ▬      5%  │
   Round 3. Your move.               │ fairness note                │
   [Q W E R T Y U I O P]             └──────────────────────────────┘
   [Enter  Z X C V B N M  ⌫]
```

- **Fairness is the design.** Jev's board shows colours only, and its
  shortlist shows labels and odds without words. The words would hand you
  Jev's clues. A line in the panel says exactly what each side can see.
- **Jev's call starts the moment your guess is accepted,** so its latency hides
  behind your own tile flip. Then Jev's beat plays: odds, pick, flip. It's
  quicker than in Watch Jev, because here it's the reply, not the show.
- **The end is one reveal.** Jev's letters pop onto its board, the panel
  becomes "Jev's reasoning" with a tab per round, and a result sheet shows both
  boards side by side, the secret, the session score, and "Play again", "See
  Jev's reasoning" and "Copy result".
- **Errors follow Wordle's voice:** "Not in word list" and "Not enough
  letters" as a toast, with a row shake.
- **On phones,** Jev's panel becomes a compact strip above your board (a tiny
  colours-only board plus its last decision), so your board and keyboard stay
  together.
