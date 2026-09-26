/* You vs Jev. Same secret, played in rounds: you guess, then Jev makes one
   typed choice. Jev's letters stay hidden until the match ends. */
"use strict";

// Round timings. Your flip matches the watch page. Jev's beat is quicker,
// because here it's the reply, not the whole show.
const V = {
  flip: 350, flipStagger: 300,
  deal: 220, dealStagger: 60, weigh: 450,
  pickHold: 550,
  jevFlip: 320, jevStagger: 170,
  keyStagger: 30,
  hop: 500, hopStagger: 100,
  sheetDelay: 900,
};

const $ = (id) => document.getElementById(id);
const els = {
  board: $("board"),
  leftCol: $("left-col"),
  narrator: $("narrator"),
  keyboard: $("keyboard"),
  jevPanel: $("jev-panel"),
  jevBoard: $("jev-board"),
  jevList: $("jev-list"),
  jevStatus: $("jev-status"),
  jevTitle: $("jev-title"),
  tabs: $("turn-tabs"),
  roundPill: $("round-pill"),
  youSub: $("you-sub"),
  jevSub: $("jev-sub"),
  sideJev: $("side-jev"),
  scoreYou: $("score-you"),
  scoreJev: $("score-jev"),
  newMatch: $("new-match"),
  contrast: $("contrast"),
  sheet: $("sheet"),
  sheetBody: $("sheet-body"),
  toast: $("toast"),
};

const state = {
  matchId: null,
  match: null,
  row: 0,
  input: "",
  busy: true,
  token: 0,
  view: null,
};

const SCORE_KEY = "jev-wordle-versus-score";

/* ---------- small helpers ---------- */

const tilesOf = (board, r) => [...board.children[r].children];

function say(html) {
  els.narrator.innerHTML = html;
}

let toastTimer = null;
function toast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("is-shown");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => els.toast.classList.remove("is-shown"), 1600);
}

function shakeRow(r) {
  const row = els.board.children[r];
  if (!row || reduced()) return;
  row.classList.remove("is-shaking");
  void row.offsetWidth; // restart the animation
  row.classList.add("is-shaking");
}

function loadScore() {
  try {
    const s = JSON.parse(storage(SCORE_KEY) || "{}");
    return { you: s.you | 0, jev: s.jev | 0, draw: s.draw | 0 };
  } catch {
    return { you: 0, jev: 0, draw: 0 };
  }
}

function renderScore(score = loadScore()) {
  els.scoreYou.textContent = score.you;
  els.scoreJev.textContent = score.jev;
}

function setCurrentRow(r) {
  [...els.board.children].forEach((row, i) => row.classList.toggle("is-current", i === r));
}

function setRoundPill(match) {
  els.roundPill.innerHTML = match.phase === "over" ? "Final" : `Round <b>${match.round}</b> of ${match.max_rounds}`;
}

function setJevThinking(on) {
  els.jevPanel.classList.toggle("is-thinking", on);
  els.sideJev.classList.toggle("is-thinking", on);
}

/* ---------- structure ---------- */

function buildKeyboard() {
  els.keyboard.replaceChildren();
  KEY_ROWS.forEach((letters, i) => {
    const row = document.createElement("div");
    row.className = "kb-row";
    const keys = [...letters];
    if (i === 2) {
      keys.unshift("ENTER");
      keys.push("BACK");
    }
    for (const k of keys) {
      const key = document.createElement("button");
      key.type = "button";
      key.className = "key";
      key.dataset.key = k;
      if (k === "ENTER") {
        key.classList.add("wide");
        key.textContent = "Enter";
      } else if (k === "BACK") {
        key.classList.add("wide");
        key.textContent = "⌫";
        key.setAttribute("aria-label", "Delete letter");
      } else {
        key.textContent = k;
      }
      key.addEventListener("click", (e) => {
        if (e.detail > 0) key.blur(); // mouse or touch: keep Enter on the physical keyboard meaning "submit"
        press(k);
      });
      row.append(key);
    }
    els.keyboard.append(row);
  });
}

function resetBoards() {
  buildGrid(els.board, { label: "Your guesses, 6 rows of 5 letters" });
  buildGrid(els.jevBoard, { label: "Jev's guesses. Colours only until the match ends" });
  els.leftCol.replaceChildren(...Array.from({ length: ROWS }, () => document.createElement("li")));
  els.keyboard.querySelectorAll(".key").forEach((k) => { delete k.dataset.state; });
  els.jevList.replaceChildren();
  els.tabs.replaceChildren();
  els.jevPanel.classList.add("is-live");
  els.jevTitle.textContent = "Jev's board";
}

/* ---------- typing ---------- */

const canType = () => !state.busy && state.match && state.match.phase === "you";

function press(k) {
  if (k === "ENTER") return submit();
  if (k === "BACK") return backspace();
  typeLetter(k);
}

function typeLetter(letter) {
  if (!canType() || state.input.length >= COLS) return;
  state.input += letter;
  const tile = tilesOf(els.board, state.row)[state.input.length - 1];
  tile.textContent = letter;
  tile.dataset.state = "filled";
  tile.setAttribute("aria-label", letter);
  animate(tile, [{ transform: "scale(1)" }, { transform: "scale(1.1)" }, { transform: "scale(1)" }], { duration: 110 });
}

function backspace() {
  if (!canType() || !state.input) return;
  const tile = tilesOf(els.board, state.row)[state.input.length - 1];
  tile.textContent = "";
  tile.dataset.state = "empty";
  tile.setAttribute("aria-label", "empty");
  state.input = state.input.slice(0, -1);
}

/* ---------- a round ---------- */

async function submit() {
  if (!canType()) return;
  if (state.input.length < COLS) {
    shakeRow(state.row);
    toast("Not enough letters");
    return;
  }
  const token = state.token;
  const live = () => token === state.token;
  const row = state.row;
  const word = state.input;
  state.busy = true;

  let res;
  try {
    res = await api("/api/versus/guess", { match_id: state.matchId, word });
  } catch (err) {
    if (!live()) return;
    state.busy = false;
    if (err.status === 422) {
      shakeRow(row);
      toast(err.message);
    } else {
      failed(err);
    }
    return;
  }
  if (!live()) return;

  // Jev's call starts now, so its latency hides behind your flip.
  const jevCall = api("/api/versus/jev-turn", { match_id: state.matchId });
  jevCall.catch(() => {});
  setJevThinking(true);
  els.jevSub.textContent = "Thinking…";
  els.youSub.textContent = "Waiting for Jev";
  els.jevStatus.innerHTML = `Jev is choosing its guess for round ${row + 1}.`;
  say(`Checking <strong>${esc(word)}</strong>…`);

  await revealRow(els.board, row, res.pattern);
  if (!live()) return;
  const mine = res.match.you.guesses[row];
  await updateKeyboard(word, res.match.you.keyboard);
  setLeftCount(row, mine.common_left_after, res.pattern.every((c) => c === "green"));
  if (res.pattern.every((c) => c === "green")) {
    await hopTiles(tilesOf(els.board, row), V.hopStagger, V.hop);
    say(`You solved it in ${row + 1}. Jev still gets its round ${row + 1}, and a draw is possible.`);
  } else {
    say(`Jev is playing round ${row + 1}.`);
  }
  state.input = "";
  state.row = row + 1;
  setCurrentRow(-1);

  let jevRes;
  try {
    jevRes = await jevCall;
  } catch (err) {
    if (!live()) return;
    return jevFailed(err);
  }
  if (!live()) return;
  await playJevTurn(jevRes.match, token);
}

async function retryJev() {
  const token = state.token;
  setJevThinking(true);
  els.jevSub.textContent = "Thinking…";
  say("Asking Jev again.");
  try {
    const res = await api("/api/versus/jev-turn", { match_id: state.matchId });
    if (token !== state.token) return;
    await playJevTurn(res.match, token);
  } catch (err) {
    if (token === state.token) jevFailed(err);
  }
}

function jevFailed(err) {
  setJevThinking(false);
  els.jevSub.textContent = "No answer";
  if (err.status === 404) return failed(err);
  els.narrator.innerHTML = `<span class="is-error">${esc(err.message)}</span> `;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "btn btn-quiet";
  retry.textContent = "Try Jev's turn again";
  retry.addEventListener("click", retryJev);
  els.narrator.append(document.createElement("br"), retry);
}

async function playJevTurn(match, token) {
  const live = () => token === state.token;
  state.match = match;
  const turns = match.jev.turns;
  const turn = turns[turns.length - 1];
  const r = turn.turn - 1;
  setJevThinking(false);

  // The decision first, then its colours.
  await dealJevList(turn);
  if (!live()) return;
  els.jevStatus.innerHTML = jevDecisionLine(turn, match);
  await sleep(V.pickHold);
  if (!live()) return;

  const over = match.phase === "over";
  const tiles = tilesOf(els.jevBoard, r);
  if (over) tiles.forEach((t, i) => { t.textContent = turn.pick.word[i]; });
  const chosen = els.jevList.querySelector(".cand.is-chosen");
  const minis = chosen ? [...chosen.querySelectorAll(".mini")] : [];
  await Promise.all(tiles.map(async (tile, i) => {
    await sleep(reduced() ? 0 : i * V.jevStagger);
    await flipTile(tile, turn.pattern[i], minis[i], V.jevFlip);
  }));
  if (!live()) return;

  const jevSolved = match.jev.status === "won";
  els.jevSub.textContent = jevSolved ? `Solved in ${turn.turn}` : `${plural(turn.common_left_after, "word")} left`;
  setRoundPill(match);

  if (over) return finish(match, token);

  state.busy = false;
  els.youSub.textContent = "Your move";
  setCurrentRow(state.row);
  say(`Round ${match.round}. Your move.`);
}

function jevDecisionLine(turn, match) {
  if (turn.fallback) return "Jev didn't answer after one retry, so the top letter-score word was played for it.";
  const of = turn.candidates.length > 1 ? ` from ${turn.candidates.length} options` : "";
  const chosen = turn.candidates.find((c) => c.chosen || (turn.pick.word && c.word === turn.pick.word));
  const kind = chosen ? ` (${esc(chosen.label.toLowerCase())})` : "";
  const word = match.phase === "over" && turn.pick.word ? `<strong>${esc(turn.pick.word)}</strong> ` : "";
  return `Jev picked ${word}at <strong>${esc(pct(turn.pick.p))}</strong>${of}${kind}.`;
}

/* ---------- Jev panel ---------- */

function jevItem(cand, { masked, chosen, pattern }) {
  const li = document.createElement("li");
  li.className = "cand";
  if (!cand.fits) li.classList.add("is-probe");
  if (chosen) li.classList.add("is-chosen");
  if (masked) li.classList.add("is-compact"); // the board already shows the colours

  const minis = document.createElement("div");
  minis.className = "mini-row";
  minis.setAttribute("aria-hidden", "true");
  for (let i = 0; i < COLS; i++) {
    const m = document.createElement("span");
    m.className = "mini";
    if (masked) m.classList.add("is-masked");
    m.textContent = masked ? "" : cand.word[i];
    if (pattern) m.dataset.state = pattern[i];
    minis.append(m);
  }

  const label = document.createElement("span");
  label.className = "cand-label";
  const who = masked ? "Hidden word" : cand.word;
  label.innerHTML = `<span class="visually-hidden">${esc(who)}, ${esc(pct(cand.p))}. </span>${esc(cand.label)}`;

  const p = document.createElement("span");
  p.className = "cand-pct";
  p.textContent = pct(cand.p);

  const bar = document.createElement("div");
  bar.className = "cand-bar";
  bar.setAttribute("aria-hidden", "true");
  bar.append(document.createElement("i"));

  if (!masked) li.append(minis);
  li.append(label, p);
  if (!masked && cand.note) {
    const note = document.createElement("p");
    note.className = "cand-note";
    note.textContent = cand.note;
    li.append(note);
  }
  li.append(bar);
  return li;
}

function isChosen(turn, cand) {
  return turn.masked ? cand.chosen : cand.word === turn.pick.word;
}

async function dealJevList(turn) {
  const items = turn.candidates.map((cand) => {
    const li = jevItem(cand, { masked: !!turn.masked, chosen: false, pattern: null });
    li.querySelector(".cand-pct").textContent = "";
    return li;
  });
  els.jevList.classList.remove("has-choice");
  els.jevList.replaceChildren(...items);
  items.forEach((li, i) => {
    animate(li, [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
      { duration: V.deal, delay: i * V.dealStagger, easing: "cubic-bezier(.2,.7,.2,1)", fill: "backwards" });
  });
  await sleep(reduced() ? 0 : (items.length - 1) * V.dealStagger + V.deal);
  items.forEach((li, i) => {
    const p = turn.candidates[i].p;
    li.querySelector(".cand-bar i").style.width = `${Math.round((p || 0) * 100)}%`;
    countUp(li.querySelector(".cand-pct"), p, V.weigh);
  });
  await sleep(reduced() ? 0 : V.weigh);
  const idx = turn.candidates.findIndex((c) => isChosen(turn, c));
  if (idx >= 0) {
    els.jevList.classList.add("has-choice");
    items[idx].classList.add("is-chosen");
  }
}

/** Static view of one of Jev's turns, after the match (words and notes shown). */
function showJevTurn(turn) {
  state.view = turn.turn;
  els.jevList.classList.add("has-choice");
  els.jevList.replaceChildren(...turn.candidates.map((cand) => {
    const chosen = isChosen(turn, cand);
    const li = jevItem(cand, { masked: false, chosen, pattern: chosen ? turn.pattern : null });
    li.querySelector(".cand-bar i").style.width = `${Math.round((cand.p || 0) * 100)}%`;
    return li;
  }));
  els.jevStatus.innerHTML = `Round ${turn.turn}: ${jevDecisionLine(turn, state.match)}`;
  renderTabs();
}

function renderTabs() {
  els.tabs.replaceChildren();
  const turns = state.match && state.match.phase === "over" ? state.match.jev.turns : [];
  if (turns.length < 2) return;
  for (const t of turns) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "turn-tab";
    b.textContent = String(t.turn);
    b.setAttribute("aria-label", `Show Jev's round ${t.turn}`);
    b.setAttribute("aria-current", String(state.view === t.turn));
    b.addEventListener("click", () => showJevTurn(t));
    els.tabs.append(b);
  }
}

/* ---------- your board ---------- */

async function revealRow(board, r, pattern) {
  const tiles = tilesOf(board, r);
  await Promise.all(tiles.map(async (tile, i) => {
    await sleep(reduced() ? 0 : i * V.flipStagger);
    await flipTile(tile, pattern[i], null, V.flip);
  }));
}

async function updateKeyboard(word, keyboard) {
  for (const letter of new Set(word)) {
    const key = els.keyboard.querySelector(`[data-key="${letter}"]`);
    if (key && keyboard[letter]) key.dataset.state = keyboard[letter];
    if (!reduced()) await sleep(V.keyStagger);
  }
}

function setLeftCount(r, n, solved) {
  const li = els.leftCol.children[r];
  if (!li) return;
  if (solved) {
    li.innerHTML = "<b>✓</b>";
    li.classList.add("is-solved");
  } else {
    li.innerHTML = `<b>${n.toLocaleString()}</b>left`;
    li.setAttribute("aria-label", `${plural(n, "common word")} left after your guess ${r + 1}`);
  }
  li.classList.add("is-set");
}

/* ---------- the end ---------- */

async function finish(match, token) {
  const live = () => token === state.token;
  state.busy = true;
  els.jevPanel.classList.remove("is-live");
  els.jevTitle.textContent = "Jev's reasoning";

  // Jev's letters appear on every row that was colours-only.
  const turns = match.jev.turns;
  for (let r = 0; r < turns.length - 1; r++) {
    const tiles = tilesOf(els.jevBoard, r);
    tiles.forEach((tile, i) => {
      tile.textContent = turns[r].pick.word[i];
      tile.setAttribute("aria-label", `${turns[r].pick.word[i]}, ${COLOR_WORD[turns[r].pattern[i]]}`);
      animate(tile, [{ transform: "scale(0.88)", opacity: 0.4 }, { transform: "none", opacity: 1 }],
        { duration: 260, delay: (r * COLS + i) * 25, easing: "cubic-bezier(.2,.8,.3,1.2)", fill: "backwards" });
    });
  }
  if (match.jev.status === "won") await hopTiles(tilesOf(els.jevBoard, turns.length - 1), V.hopStagger, V.hop);
  showJevTurn(turns[turns.length - 1]);

  const score = loadScore();
  if (match.result === "you") score.you += 1;
  else if (match.result === "jev") score.jev += 1;
  else if (match.result === "draw") score.draw += 1;
  storage(SCORE_KEY, JSON.stringify(score));
  renderScore(score);

  const you = match.you;
  els.youSub.textContent = you.status === "won" ? `Solved in ${you.guesses.length}` : "Not solved";
  say(resultSentence(match));
  await sleep(reduced() ? 200 : V.sheetDelay);
  if (!live()) return;
  openSheet(match, score);
}

function resultSentence(match) {
  const secret = `<strong>${esc(match.secret)}</strong>`;
  switch (match.result) {
    case "you": return `You win. The word was ${secret}.`;
    case "jev": return `Jev wins. The word was ${secret}.`;
    case "draw": return `Draw. The word was ${secret}.`;
    default: return `Nobody solved it. The word was ${secret}.`;
  }
}

function openSheet(match, score) {
  const y = match.you.guesses.length;
  const turns = match.jev.turns;
  const j = turns.length;
  const last = turns[j - 1];
  const jevPick = last.fallback ? `${esc(last.pick.word)}` : `${esc(last.pick.word)} at ${esc(pct(last.pick.p))}`;
  const titles = { you: "You win", jev: "Jev wins", draw: "Draw", none: "Nobody solved it" };
  const ledes = {
    you: `You solved it in <strong>${y}</strong>. Jev hadn't found it after ${plural(j, "guess")}.`,
    jev: `Jev solved it in <strong>${j}</strong>, picking <strong>${jevPick}</strong>. You hadn't found it yet.`,
    draw: `You both solved it in <strong>${y}</strong>. Jev's winning pick was <strong>${jevPick}</strong>.`,
    none: "Neither of you found it in 6 guesses.",
  };
  const draws = score.draw ? `, ${plural(score.draw, "draw")}` : "";
  els.sheetBody.innerHTML = `
    <h2 id="sheet-title">${titles[match.result]}</h2>
    <p class="lede">${ledes[match.result]}</p>
    <div class="sheet-secret" aria-label="The word was ${esc(match.secret)}">
      <span class="mini-row">${[...match.secret].map((l) => `<span class="mini" data-state="green">${esc(l)}</span>`).join("")}</span>
    </div>
    <div class="sheet-boards">
      <figure><figcaption>You <b>${match.you.status === "won" ? y : "X"}/6</b></figcaption><div class="board" data-side="you"></div></figure>
      <figure><figcaption>Jev <b>${match.jev.status === "won" ? j : "X"}/6</b></figcaption><div class="board" data-side="jev"></div></figure>
    </div>
    <p class="sheet-score">This session: you ${score.you}, Jev ${score.jev}${draws}.</p>
    <div class="sheet-actions">
      <button class="btn btn-primary" type="button" data-action="again">Play again</button>
      <button class="btn btn-quiet" type="button" data-action="reasoning">See Jev's reasoning</button>
      <button class="btn btn-quiet" type="button" data-action="copy">Copy result</button>
    </div>`;

  const fill = (board, rows) => {
    buildGrid(board, { label: "" });
    rows.forEach(({ word, pattern }, r) => {
      tilesOf(board, r).forEach((tile, i) => {
        tile.textContent = word[i];
        tile.dataset.state = pattern[i];
      });
    });
  };
  fill(els.sheetBody.querySelector('[data-side="you"]'), match.you.guesses);
  fill(els.sheetBody.querySelector('[data-side="jev"]'), turns.map((t) => ({ word: t.pick.word, pattern: t.pattern })));

  els.sheetBody.querySelector('[data-action="again"]').addEventListener("click", () => {
    els.sheet.close();
    newMatch();
  });
  els.sheetBody.querySelector('[data-action="reasoning"]').addEventListener("click", () => {
    els.sheet.close();
    els.jevPanel.scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
  });
  els.sheetBody.querySelector('[data-action="copy"]').addEventListener("click", (e) => copyResult(e.currentTarget, match));
  if (typeof els.sheet.showModal === "function") els.sheet.showModal();
  else els.sheet.setAttribute("open", "");
}

async function copyResult(button, match) {
  const contrast = document.body.classList.contains("contrast");
  const glyph = { green: contrast ? "🟧" : "🟩", yellow: contrast ? "🟦" : "🟨", gray: "⬛" };
  const row = (pattern) => pattern.map((c) => glyph[c]).join("");
  const you = match.you.guesses.map((g) => row(g.pattern));
  const jev = match.jev.turns.map((t) => row(t.pattern));
  const blank = "      ".repeat(1);
  const lines = [];
  for (let i = 0; i < Math.max(you.length, jev.length); i++) lines.push(`${you[i] || blank}   ${jev[i] || blank}`);
  const titles = { you: "I beat Jev", jev: "Jev beat me", draw: "Draw with Jev", none: "Nobody solved it" };
  const ys = match.you.status === "won" ? match.you.guesses.length : "X";
  const js = match.jev.status === "won" ? match.jev.turns.length : "X";
  const text = `Jev Wordle, You vs Jev: ${titles[match.result]}\nMe ${ys}/6, Jev ${js}/6\n\n${lines.join("\n")}`;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Copy failed";
  }
  setTimeout(() => { button.textContent = "Copy result"; }, 2200);
}

/* ---------- lifecycle ---------- */

function failed(err) {
  setJevThinking(false);
  state.busy = false;
  if (err.status === 404) {
    state.match = null;
    say(`<span class="is-error">This match expired after an hour without play.</span> Start a new match to keep going.`);
  } else {
    say(`<span class="is-error">${esc(err.message)}</span>`);
  }
}

async function newMatch() {
  state.token += 1;
  const token = state.token;
  state.busy = true;
  state.match = null;
  state.matchId = null;
  state.row = 0;
  state.input = "";
  state.view = null;
  setJevThinking(false);
  if (els.sheet.open) els.sheet.close();
  resetBoards();
  els.youSub.textContent = "Your move";
  els.jevSub.textContent = "Waiting for you";
  els.roundPill.innerHTML = "Round <b>1</b> of 6";
  els.jevStatus.textContent = "Jev plays after you each round.";
  say("Picking a secret word.");
  try {
    const match = await api("/api/versus/new");
    if (token !== state.token) return;
    state.match = match;
    state.matchId = match.match_id;
  } catch (err) {
    if (token !== state.token) return;
    state.busy = false;
    say(`<span class="is-error">${esc(err.message)}</span>`);
    return;
  }
  state.busy = false;
  setCurrentRow(0);
  say("Type your first guess and press Enter. Jev plays the same word after you.");
}

/* ---------- wiring ---------- */

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey || els.sheet.open) return;
  const onButton = e.target instanceof HTMLElement && e.target.closest("button, a, input");
  let k = null;
  if (e.key === "Enter") {
    if (onButton) return; // let the focused control handle it
    k = "ENTER";
  } else if (e.key === "Backspace") {
    k = "BACK";
  } else if (/^[a-z]$/i.test(e.key)) {
    k = e.key.toUpperCase();
  }
  if (!k) return;
  e.preventDefault();
  const key = els.keyboard.querySelector(`[data-key="${k}"]`);
  if (key) {
    key.classList.add("is-pressed");
    setTimeout(() => key.classList.remove("is-pressed"), 100);
  }
  press(k);
});

els.newMatch.addEventListener("click", () => newMatch());
initContrastToggle(els.contrast);

buildKeyboard();
renderScore();
newMatch();
