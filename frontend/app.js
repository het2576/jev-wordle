/* Jev Wordle frontend. The motion sequence and its timings are specified in docs/DESIGN.md. */
"use strict";

// One turn, in order. Holds (read, pickHold) are pacing and survive reduced motion.
const T = {
  deal: 280, dealStagger: 90,
  weighDelay: 120, weigh: 600,
  read: 1400,
  pick: 320, pickHold: 650,
  fly: 420, flyStagger: 70,
  flip: 350, flipStagger: 300,
  settle: 250, keyStagger: 30,
  hop: 500, hopStagger: 100,
  betweenTurns: 900,
};

const $ = (id) => document.getElementById(id);
const els = {
  board: $("board"),
  leftCol: $("left-col"),
  narrator: $("narrator"),
  keyboard: $("keyboard"),
  rack: $("rack"),
  rackTitle: $("rack-title"),
  rackSub: $("rack-sub"),
  rackList: $("rack-list"),
  rackMeta: $("rack-meta"),
  tabs: $("turn-tabs"),
  results: $("results"),
  play: $("play-turn"),
  newGame: $("new-game"),
  auto: $("auto-play"),
  contrast: $("contrast"),
  flight: $("flight-layer"),
};

const state = {
  gameId: null,
  status: "idle", // idle | playing | won | lost | expired
  game: null,
  turns: [],
  busy: false,
  token: 0, // bumps on new game so any running sequence stops
  view: null, // turn number being shown in the rack, or "result"
};

/* ---------- static structure ---------- */

function buildBoard() {
  buildGrid(els.board);
  els.leftCol.replaceChildren(...Array.from({ length: ROWS }, () => document.createElement("li")));
}

function buildKeyboard() {
  els.keyboard.replaceChildren();
  for (const letters of KEY_ROWS) {
    const row = document.createElement("div");
    row.className = "kb-row";
    for (const letter of letters) {
      const key = document.createElement("div");
      key.className = "key";
      key.dataset.key = letter;
      key.textContent = letter;
      row.append(key);
    }
    els.keyboard.append(row);
  }
}

const rowTiles = (r) => [...els.board.children[r].children];

/* ---------- rack rendering ---------- */

function candidateItem(cand, { pattern = null, chosen = false } = {}) {
  const li = document.createElement("li");
  li.className = "cand";
  if (!cand.fits) li.classList.add("is-probe");
  if (chosen) li.classList.add("is-chosen");
  li.dataset.word = cand.word;

  const minis = document.createElement("div");
  minis.className = "mini-row";
  minis.setAttribute("aria-hidden", "true");
  [...cand.word].forEach((letter, i) => {
    const m = document.createElement("span");
    m.className = "mini";
    m.textContent = letter;
    if (pattern) m.dataset.state = pattern[i];
    minis.append(m);
  });

  const pctEl = document.createElement("span");
  pctEl.className = "cand-pct";
  pctEl.textContent = pct(cand.p);

  const label = document.createElement("span");
  label.className = "cand-label";
  label.innerHTML = `<span class="visually-hidden">${esc(cand.word)}, ${esc(pct(cand.p))}. </span>${esc(cand.label)}`;

  const text = document.createElement("p");
  text.className = "cand-note";
  text.textContent = cand.note;

  const bar = document.createElement("div");
  bar.className = "cand-bar";
  bar.setAttribute("aria-hidden", "true");
  const fill = document.createElement("i");
  bar.append(fill);

  li.append(minis, label, pctEl, text, bar);
  return li;
}

function renderGhosts(n = 6) {
  els.rackList.classList.remove("has-choice");
  els.rackList.replaceChildren();
  for (let i = 0; i < n; i++) {
    const li = candidateItem({ word: "     ", p: null, label: "", note: "", fits: true });
    li.classList.add("ghost");
    li.querySelector(".cand-pct").textContent = "";
    els.rackList.append(li);
  }
}

function renderEmptyRack(message) {
  els.rackList.classList.remove("has-choice");
  const li = document.createElement("li");
  li.className = "rack-empty";
  li.textContent = message;
  els.rackList.replaceChildren(li);
}

function turnSubline(turn) {
  if (turn.turn === 1) return `Turn 1. No clues yet, so any of the ${turn.common_left.toLocaleString()} common words could be the answer.`;
  if (turn.common_left === 1) return `Turn ${turn.turn}. Only one common word still fits the clues.`;
  return `Turn ${turn.turn}. ${plural(turn.common_left, "common word")} still fit the clues.`;
}

function metaLine(turn) {
  if (turn.fallback) return `No answer from Jev after ${plural(turn.attempts, "attempt")}.`;
  const conf = turn.confidence === null ? "" : ` Confidence ${pct(turn.confidence)}.`;
  return `Answered in ${Math.round(turn.latency_ms).toLocaleString()} ms.${conf}`;
}

/** Static render of a turn already played (used for review). */
function showTurn(turn) {
  state.view = turn.turn;
  els.rackTitle.textContent = "Jev's shortlist";
  els.results.hidden = true;
  els.rackList.hidden = false;
  els.rackSub.hidden = false;
  els.rackSub.textContent = turnSubline(turn);
  els.rackList.replaceChildren();
  els.rackList.classList.add("has-choice");
  for (const cand of turn.candidates) {
    const chosen = cand.word === turn.pick.word;
    const li = candidateItem(cand, { chosen, pattern: chosen ? turn.pattern : null });
    li.querySelector(".cand-bar i").style.width = `${Math.round((cand.p || 0) * 100)}%`;
    els.rackList.append(li);
  }
  els.rackMeta.textContent = metaLine(turn);
  renderTabs();
}

function renderTabs() {
  els.tabs.replaceChildren();
  const over = state.status === "won" || state.status === "lost";
  const items = state.turns.map((t) => ({ key: t.turn, label: String(t.turn), aria: `Show turn ${t.turn}` }));
  if (over) items.push({ key: "result", label: "✓", aria: "Show the result" });
  if (items.length < 2 && !over) return;
  for (const item of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "turn-tab";
    b.textContent = item.label;
    b.setAttribute("aria-label", item.aria);
    b.setAttribute("aria-current", String(state.view === item.key));
    b.disabled = state.busy;
    b.addEventListener("click", () => {
      if (state.busy) return;
      if (item.key === "result") showResults(state.game);
      else showTurn(state.turns.find((t) => t.turn === item.key));
    });
    els.tabs.append(b);
  }
}

/* ---------- motion helpers ---------- */

async function dealRack(turn) {
  state.view = turn.turn;
  els.rackTitle.textContent = "Jev's shortlist";
  els.results.hidden = true;
  els.rackList.hidden = false;
  els.rackSub.hidden = false;
  els.rackList.classList.remove("has-choice");
  els.rackSub.textContent = turnSubline(turn);
  const items = turn.candidates.map((cand) => {
    const li = candidateItem(cand);
    li.querySelector(".cand-pct").textContent = "";
    li.style.opacity = reduced() ? "1" : "0";
    return li;
  });
  els.rackList.replaceChildren(...items);

  // 1. Deal: rows fade in and rise, one after another.
  items.forEach((li, i) => {
    setTimeout(() => {
      li.style.opacity = "";
      animate(li, [
        { opacity: 0, transform: "translateY(6px)" },
        { opacity: 1, transform: "none" },
      ], { duration: T.deal, easing: "cubic-bezier(.2,.7,.2,1)" });
    }, reduced() ? 0 : i * T.dealStagger);
  });
  await sleep(reduced() ? 0 : (items.length - 1) * T.dealStagger + T.deal + T.weighDelay);

  // 2. Weigh: every bar grows together, percentages count up with them.
  items.forEach((li, i) => {
    const p = turn.candidates[i].p;
    li.querySelector(".cand-bar i").style.width = `${Math.round((p || 0) * 100)}%`;
    countUp(li.querySelector(".cand-pct"), p, T.weigh);
  });
  await sleep(reduced() ? 0 : T.weigh);
  return items;
}

async function flyLetters(li, rowIndex, word) {
  const minis = [...li.querySelectorAll(".mini")];
  const tiles = rowTiles(rowIndex);
  const land = (i) => {
    tiles[i].textContent = word[i];
    tiles[i].dataset.state = "filled";
    tiles[i].setAttribute("aria-label", word[i]);
    minis[i].classList.add("is-lifted");
  };
  if (reduced()) {
    [...word].forEach((_, i) => land(i));
    return;
  }
  const fontSize = getComputedStyle(tiles[0]).fontSize;
  await Promise.all(minis.map(async (mini, i) => {
    await sleep(i * T.flyStagger);
    const a = mini.getBoundingClientRect();
    const b = tiles[i].getBoundingClientRect();
    const flyer = document.createElement("div");
    flyer.className = "flyer";
    flyer.textContent = word[i];
    Object.assign(flyer.style, {
      left: `${b.left}px`, top: `${b.top}px`, width: `${b.width}px`, height: `${b.height}px`, fontSize,
    });
    els.flight.append(flyer);
    mini.classList.add("is-lifted");
    const s = a.width / b.width;
    const dx = a.left + a.width / 2 - (b.left + b.width / 2);
    const dy = a.top + a.height / 2 - (b.top + b.height / 2);
    await animate(flyer, [
      { transform: `translate(${dx}px, ${dy}px) scale(${s})` },
      { transform: "translate(0, -6px) scale(1.06)", offset: 0.82 },
      { transform: "none" },
    ], { duration: T.fly, easing: "cubic-bezier(.3,.6,.25,1)" });
    land(i);
    flyer.remove();
    animate(tiles[i], [{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 110 });
  }));
}

async function revealRow(rowIndex, pattern, li) {
  const tiles = rowTiles(rowIndex);
  const minis = li ? [...li.querySelectorAll(".mini")] : [];
  await Promise.all(tiles.map(async (tile, i) => {
    await sleep(reduced() ? 0 : i * T.flipStagger);
    await flipTile(tile, pattern[i], minis[i], T.flip);
  }));
}

async function updateKeyboard(word, keyboard) {
  const letters = [...new Set(word)];
  for (const letter of letters) {
    const key = els.keyboard.querySelector(`[data-key="${letter}"]`);
    if (key && keyboard[letter]) key.dataset.state = keyboard[letter];
    if (!reduced()) await sleep(T.keyStagger);
  }
}

function setLeftCount(rowIndex, turn, solved) {
  const li = els.leftCol.children[rowIndex];
  if (!li) return;
  if (solved) {
    li.innerHTML = "<b>✓</b>";
    li.classList.add("is-solved");
    li.setAttribute("aria-label", "solved");
  } else {
    const n = turn.common_left_after;
    li.innerHTML = `<b>${n.toLocaleString()}</b>left`;
    li.setAttribute("aria-label", `${plural(n, "common word")} left after guess ${rowIndex + 1}`);
  }
  li.classList.add("is-set");
}

function hopRow(rowIndex) {
  return hopTiles(rowTiles(rowIndex), T.hopStagger, T.hop);
}

/* ---------- narration ---------- */

function say(html) {
  els.narrator.innerHTML = html;
}

function sayError(message) {
  els.narrator.innerHTML = `<span class="is-error">${esc(message)}</span>`;
}

function pickSentence(turn) {
  const word = `<strong>${esc(turn.pick.word)}</strong>`;
  if (turn.fallback) {
    return `Jev didn't answer after one retry, so the top letter-score word, ${word}, is played instead.`;
  }
  const chosen = turn.candidates.find((c) => c.word === turn.pick.word);
  const at = `at ${pct(turn.pick.p)}`;
  if (turn.candidates.length === 1) return `Jev plays ${word}, the only word left.`;
  if (turn.pick.word === turn.heuristic_top) return `Jev picks ${word} ${at}, the top letter-score word.`;
  const kind = chosen ? chosen.label.toLowerCase() : "another option";
  return `Jev picks ${word} ${at} (${esc(kind)}) over the top letter-score word, ${esc(turn.heuristic_top)}.`;
}

function outcomeSentence(turn, game) {
  const word = `<strong>${esc(turn.pick.word)}</strong>`;
  if (game.status === "won") return `${word} is the word. Solved in ${game.guesses_used}.`;
  const g = turn.pattern.filter((c) => c === "green").length;
  const y = turn.pattern.filter((c) => c === "yellow").length;
  const hits = g || y ? `${g} green, ${y} yellow` : "no letters in the word";
  if (game.status === "lost") return `${word}: ${hits}. Out of guesses.`;
  const left = turn.common_left_after === 1 ? "Only one common word fits now." : `${plural(turn.common_left_after, "common word")} still fit.`;
  return `${word}: ${hits}. ${left}`;
}

/* ---------- turn sequence ---------- */

function setBusy(busy) {
  state.busy = busy;
  els.play.disabled = busy;
  els.tabs.querySelectorAll("button").forEach((b) => { b.disabled = busy; });
}

function updatePlayButton() {
  if (state.status === "playing") {
    els.play.textContent = `Play turn ${state.turns.length + 1}`;
  } else {
    els.play.textContent = "New game";
  }
}

async function playTurn() {
  if (state.busy) return;
  if (state.status !== "playing") return newGame();
  const token = state.token;
  const live = () => token === state.token;
  setBusy(true);

  // 0. Ask
  const rowIndex = state.turns.length;
  els.rack.classList.add("is-thinking");
  renderGhosts();
  renderTabs();
  els.rackSub.textContent = rowIndex === 0 ? "Building the shortlist and asking Jev to choose." : "Narrowing the word list, building the shortlist, asking Jev.";
  els.rackMeta.textContent = "Waiting for Jev…";
  say(`Asking Jev to choose the next guess.`);

  let turn;
  try {
    ({ turn } = await api("/api/next-guess", { game_id: state.gameId }));
  } catch (err) {
    if (!live()) return;
    return turnFailed(err);
  }
  if (!live()) return;
  els.rack.classList.remove("is-thinking");

  // 1–2. Deal and weigh
  say(`Jev is weighing ${plural(turn.candidates.length, "word")}.`);
  els.rackMeta.textContent = metaLine(turn);
  const items = await dealRack(turn);
  if (!live()) return;

  // 3. Read
  await sleep(turn.candidates.length > 1 ? T.read : T.read / 2);
  if (!live()) return;

  // 4. Pick
  const chosen = items.find((li) => li.dataset.word === turn.pick.word);
  els.rackList.classList.add("has-choice");
  chosen.classList.add("is-chosen");
  say(pickSentence(turn));
  await sleep(T.pick + T.pickHold);
  if (!live()) return;

  // 5. Play: letters fly while the guess is scored in parallel.
  const submitting = api("/api/submit-guess", { game_id: state.gameId, word: turn.pick.word });
  submitting.catch(() => {}); // handled below; avoids an unhandled rejection during the flight
  await flyLetters(chosen, rowIndex, turn.pick.word);
  if (!live()) return;

  let result;
  try {
    result = await submitting;
  } catch (err) {
    if (!live()) return;
    rowTiles(rowIndex).forEach((t) => { t.textContent = ""; t.dataset.state = "empty"; t.setAttribute("aria-label", "empty"); });
    return turnFailed(err);
  }
  if (!live()) return;

  // 6. Reveal
  const played = result.turn;
  await revealRow(rowIndex, result.pattern, chosen);
  if (!live()) return;

  // 7. Settle
  await sleep(reduced() ? 0 : 60);
  const game = result.game;
  state.game = game;
  state.status = game.status;
  state.turns.push(played);
  setLeftCount(rowIndex, played, game.status === "won");
  await updateKeyboard(played.pick.word, game.keyboard);
  say(outcomeSentence(played, game));
  if (!live()) return;

  // 8. Result
  if (game.status !== "playing") {
    if (game.status === "won") await hopRow(rowIndex);
    await sleep(reduced() ? 300 : 700);
    if (!live()) return;
    setBusy(false);
    updatePlayButton();
    showResults(game);
    return;
  }

  setBusy(false);
  updatePlayButton();
  renderTabs();
  if (els.auto.checked) {
    await sleep(T.betweenTurns);
    if (live() && els.auto.checked && !state.busy) playTurn();
  }
}

function turnFailed(err) {
  els.rack.classList.remove("is-thinking");
  setBusy(false);
  if (err.status === 404) {
    state.status = "expired";
    renderEmptyRack("This game expired after an hour without play. Start a new game to keep going.");
    sayError("This game expired. Start a new game.");
    els.play.textContent = "New game";
  } else {
    renderEmptyRack("Nothing was played this turn. Try the turn again.");
    sayError(err.message);
    els.play.textContent = `Try turn ${state.turns.length + 1} again`;
  }
  els.rackMeta.textContent = "";
  els.auto.checked = false;
  renderTabs();
}

/* ---------- results ---------- */

function miniRow(word, pattern) {
  return `<span class="mini-row" aria-hidden="true">${[...word].map((l, i) =>
    `<span class="mini"${pattern ? ` data-state="${pattern[i]}"` : ""}>${esc(l)}</span>`).join("")}</span>`;
}

function recapItem(turn, won) {
  const chosen = turn.candidates.find((c) => c.word === turn.pick.word);
  const how = turn.fallback
    ? "Heuristic pick, Jev didn't answer"
    : turn.candidates.length === 1
      ? "The only option left"
      : `${esc(chosen ? chosen.label : "Pick")}, 1 of ${turn.candidates.length}`;
  const left = won ? "solved" : `${turn.common_left_after.toLocaleString()} left`;
  return `<li>
    ${miniRow(turn.pick.word, turn.pattern)}
    <span class="recap-what"><b>${esc(turn.pick.word)} at ${esc(pct(turn.pick.p))}</b><br>${how}</span>
    <span class="recap-left">${left}</span>
  </li>`;
}

function showResults(game) {
  if (!game || game.status === "playing") return;
  state.view = "result";
  els.rackTitle.textContent = "Result";
  const turns = game.turns || state.turns;
  const last = turns[turns.length - 1];
  const won = game.status === "won";
  els.rackList.hidden = true;
  els.rackSub.hidden = true;
  els.results.hidden = false;

  let html;
  if (won) {
    const winLine = last.fallback
      ? `The winning word was played by the heuristic because Jev didn't answer that turn.`
      : `Jev chose <strong>${esc(last.pick.word)}</strong> with <strong>${esc(pct(last.pick.p))}</strong> probability on the winning turn${last.candidates.length > 1 ? `, out of ${last.candidates.length} options` : ""}.`;
    html = `<h3>Solved in ${game.guesses_used}</h3><p class="lede">${winLine}</p>`;
  } else {
    const onRack = last.candidates.find((c) => c.word === game.secret);
    const rackLine = onRack
      ? `It was on the final shortlist, and Jev gave it ${esc(pct(onRack.p))}.`
      : `It wasn't on the final shortlist.`;
    html = `<h3>Out of guesses</h3>
      <p class="lede">The word was <strong>${esc(game.secret)}</strong>. ${rackLine}</p>
      <div class="secret-row">${miniRow(game.secret, Array(COLS).fill("green"))}</div>`;
  }
  html += `<ol class="recap">${turns.map((t, i) => recapItem(t, won && i === turns.length - 1)).join("")}</ol>`;
  if (!won) html += `<h4>Final shortlist</h4><ol class="rack-list final-list has-choice"></ol>`;
  html += `<div class="results-actions">
      <button class="btn btn-quiet" type="button" data-action="copy">Copy result</button>
    </div>`;
  els.results.innerHTML = html;

  if (!won) {
    const list = els.results.querySelector(".final-list");
    for (const cand of last.candidates) {
      const chosen = cand.word === last.pick.word;
      const li = candidateItem(cand, { chosen, pattern: chosen ? last.pattern : null });
      li.querySelector(".cand-bar i").style.width = `${Math.round((cand.p || 0) * 100)}%`;
      list.append(li);
    }
  }
  els.results.querySelector('[data-action="copy"]').addEventListener("click", (e) => copyResult(e.currentTarget, game, turns));
  els.rackMeta.textContent = "";
  renderTabs();
}

async function copyResult(button, game, turns) {
  const contrast = document.body.classList.contains("contrast");
  const glyph = { green: contrast ? "🟧" : "🟩", yellow: contrast ? "🟦" : "🟨", gray: "⬛" };
  const score = game.status === "won" ? game.guesses_used : "X";
  const lines = turns.map((t) => `${t.pattern.map((c) => glyph[c]).join("")}  ${t.fallback ? "heuristic" : `Jev ${pct(t.pick.p)}`}`);
  const text = `Jev Wordle ${score}/6\n\n${lines.join("\n")}`;
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = "Copied";
  } catch {
    button.textContent = "Copy failed. Select the recap instead";
  }
  setTimeout(() => { button.textContent = "Copy result"; }, 2200);
}

/* ---------- game lifecycle ---------- */

async function newGame() {
  state.token += 1;
  const token = state.token;
  els.flight.replaceChildren();
  setBusy(true);
  state.turns = [];
  state.game = null;
  state.view = null;
  state.status = "idle";
  buildBoard();
  buildKeyboard();
  els.rack.classList.remove("is-thinking");
  els.rackTitle.textContent = "Jev's shortlist";
  els.results.hidden = true;
  els.rackList.hidden = false;
  els.rackSub.hidden = false;
  els.rackSub.textContent = "Each turn, Jev picks one word from a short list of strong options. The probability it gives every word appears here before the tiles flip.";
  els.rackMeta.textContent = "";
  renderEmptyRack("Starting a new game…");
  renderTabs();
  say("Picking a secret word.");

  try {
    const game = await api("/api/new-game");
    if (token !== state.token) return;
    state.gameId = game.game_id;
    state.game = game;
    state.status = game.status;
  } catch (err) {
    if (token !== state.token) return;
    setBusy(false);
    state.status = "idle";
    renderEmptyRack("No game is running yet.");
    sayError(err.message);
    els.play.textContent = "New game";
    return;
  }
  setBusy(false);
  updatePlayButton();
  renderEmptyRack(`Play turn 1 to see the words Jev chooses between, and how likely it rates each one.`);
  say(`A secret word from ${(2315).toLocaleString()} common words is set. Jev hasn't seen it.`);
  if (els.auto.checked) {
    await sleep(600);
    if (token === state.token && !state.busy) playTurn();
  }
}

/* ---------- wiring ---------- */

els.play.addEventListener("click", () => playTurn());
els.newGame.addEventListener("click", () => newGame());
els.auto.addEventListener("change", () => {
  if (els.auto.checked && state.status === "playing" && !state.busy) playTurn();
});

document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const onControl = e.target instanceof HTMLElement && e.target.closest("button, input, a");
  if ((e.key === "Enter" || e.key === " ") && !onControl) {
    e.preventDefault();
    if (!state.busy) playTurn();
  } else if (e.key === "n" || e.key === "N") {
    newGame();
  } else if (e.key === "a" || e.key === "A") {
    els.auto.checked = !els.auto.checked;
    els.auto.dispatchEvent(new Event("change"));
  }
});

initContrastToggle(els.contrast);

buildBoard();
buildKeyboard();
newGame();
