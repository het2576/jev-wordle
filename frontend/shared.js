/* Shared by the watch page (app.js) and You vs Jev (versus.js): rules of the
   board, API calls, formatting and the tile flip. Loaded first as a classic
   script, so these are plain globals. */
"use strict";

const ROWS = 6;
const COLS = 5;
const KEY_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
const COLOR_WORD = { green: "green", yellow: "yellow", gray: "gray" };
const RANK = { gray: 0, yellow: 1, green: 2 };

const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const reduced = () => motionQuery.matches;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function pct(p) {
  if (p === null || p === undefined) return "–";
  if (p > 0 && p < 0.01) return "<1%";
  return `${Math.round(p * 100)}%`;
}

function plural(n, word) {
  return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
}

function storage(key, value) {
  try {
    if (value === undefined) return window.localStorage.getItem(key);
    window.localStorage.setItem(key, value);
  } catch {
    return null;
  }
  return null;
}

async function api(path, body) {
  let res;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw Object.assign(new Error("Can't reach the game server. Check that it's running, then try again."), { status: 0 });
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : `The server returned HTTP ${res.status}.`;
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return data;
}

function animate(el, keyframes, options) {
  if (reduced() || !el.animate) return Promise.resolve();
  return el.animate(keyframes, options).finished.catch(() => {});
}

function countUp(el, target, duration) {
  if (target === null || target === undefined || reduced()) {
    el.textContent = pct(target);
    return;
  }
  const start = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - k, 3);
    el.textContent = pct(target * eased);
    if (k < 1) requestAnimationFrame(step);
    else el.textContent = pct(target);
  };
  requestAnimationFrame(step);
}

/** 3D flip on the Y axis. The colour switches at 90°, edge-on, like the real game. */
async function flipTile(tile, colour, mini, duration = 350) {
  const settle = () => {
    tile.dataset.state = colour;
    const letter = tile.textContent.trim();
    tile.setAttribute("aria-label", letter ? `${letter}, ${COLOR_WORD[colour]}` : COLOR_WORD[colour]);
    if (mini) {
      mini.dataset.state = colour;
      mini.classList.remove("is-lifted");
    }
  };
  if (reduced()) return settle();
  const half = duration / 2;
  await animate(tile, [{ transform: "perspective(480px) rotateY(0deg)" }, { transform: "perspective(480px) rotateY(90deg)" }], { duration: half, easing: "ease-in" });
  settle();
  await animate(tile, [{ transform: "perspective(480px) rotateY(-90deg)" }, { transform: "perspective(480px) rotateY(0deg)" }], { duration: half, easing: "ease-out" });
}

/** Six rows of five empty tiles inside `board`. */
function buildGrid(board, { label = "Guesses, 6 rows of 5 letters" } = {}) {
  board.replaceChildren();
  board.setAttribute("aria-label", label);
  for (let r = 0; r < ROWS; r++) {
    const row = document.createElement("div");
    row.className = "row";
    row.setAttribute("role", "row");
    for (let c = 0; c < COLS; c++) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.setAttribute("role", "gridcell");
      tile.setAttribute("aria-label", "empty");
      tile.dataset.state = "empty";
      row.append(tile);
    }
    board.append(row);
  }
}

async function hopTiles(tiles, stagger = 100, duration = 500) {
  await Promise.all(tiles.map(async (tile, i) => {
    await sleep(i * stagger);
    await animate(tile, [
      { transform: "translateY(0)" },
      { transform: "translateY(-22px)", offset: 0.4 },
      { transform: "translateY(0)", offset: 0.7 },
      { transform: "translateY(-6px)", offset: 0.85 },
      { transform: "translateY(0)" },
    ], { duration, easing: "ease-out" });
  }));
}

function initContrastToggle(input) {
  if (storage("jev-wordle-contrast") === "1") {
    input.checked = true;
    document.body.classList.add("contrast");
  }
  input.addEventListener("change", () => {
    document.body.classList.toggle("contrast", input.checked);
    storage("jev-wordle-contrast", input.checked ? "1" : "0");
  });
}
