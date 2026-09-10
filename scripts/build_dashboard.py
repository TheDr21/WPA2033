#!/usr/bin/env python3
"""
build_dashboard.py -- render parsed game data into docs/index.html.

Self-contained: data is embedded as JSON, so the page works from file:// and
from GitHub Pages with no server and no fetch. Rerun after every ingest.

Reads data/game_meta.csv if present. Nothing in a GameChanger box score says
whether a game counted, so game_type lives in that sidecar and is maintained by
hand. Rows marked scrimmage/exhibition/friendly are excluded from season trends
unless the page has nothing else to show.

Usage:
    python3 scripts/build_dashboard.py --team LadyDukesWPA2033 \
        --label "Lady Dukes WPA 2033" --outdir docs/
"""

import argparse
import json
import pathlib

import pandas as pd

EXHIBITION = ["scrimmage", "exhibition", "friendly"]

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__LABEL__</title>
<link rel="icon" href="logo.png" type="image/png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,400;0,500;0,600;0,800;1,400&display=swap" rel="stylesheet">
<style>
  :root {
    /* sampled from the club mark: royal #1B40CA on black */
    --ink:    #08090c;
    --panel:  #10131a;
    --rule:   #1f2532;
    --chalk:  #f2f4f8;
    --dim:    #7c8598;
    --brand:  #1b40ca;
    --royal:  #5b81ff;   /* the royal, lifted for legibility on black */
    --seam:   #e2574a;
    --pad:    clamp(1rem, 4vw, 2.5rem);
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; background: var(--ink); color: var(--chalk);
    font-family: Archivo, "Helvetica Neue", Arial, sans-serif;
    font-size: 16px; line-height: 1.5; font-variant-numeric: tabular-nums;
  }
  .wrap { max-width: 72rem; margin: 0 auto; padding: var(--pad); }

  header { border-bottom: 2px solid var(--rule); }
  .crest { display: flex; align-items: center; gap: clamp(0.9rem, 3vw, 1.5rem); }
  .crest img { width: clamp(76px, 15vw, 128px); height: auto; flex: none; }
  h1 { font-size: clamp(1.7rem, 5.2vw, 2.8rem); font-weight: 800;
       letter-spacing: -0.026em; line-height: 1.03; margin: 0; }
  .season { color: var(--dim); font-size: 0.92rem; font-style: italic; margin-top: 0.3rem; }

  nav { display: flex; gap: 0.15rem; margin-top: 1.2rem; overflow-x: auto; scrollbar-width: none; }
  nav::-webkit-scrollbar { display: none; }
  nav a { color: var(--dim); text-decoration: none; font-size: 0.92rem; font-weight: 500;
          padding: 0.5rem 0.9rem; border-bottom: 2px solid transparent; white-space: nowrap; }
  nav a:hover { color: var(--chalk); }
  nav a[aria-current="page"] { color: var(--chalk); border-bottom-color: var(--royal); font-weight: 600; }
  nav a:focus-visible { outline: 2px solid var(--royal); outline-offset: -2px; }

  section[hidden] { display: none; }
  h2 { font-size: 1.02rem; font-weight: 600; margin: 2.1rem 0 0.85rem; }
  section > h2:first-child { margin-top: 1.7rem; }
  .note { color: var(--dim); font-size: 0.87rem; margin: -0.4rem 0 1rem; max-width: 56ch; }

  .tally { display: flex; flex-wrap: wrap; gap: 0.35rem 2.1rem; margin-top: 1.2rem; }
  #scope:not(:empty) { margin-top: 1.6rem; }
  .tally div { display: flex; align-items: baseline; gap: 0.4rem; }
  .tally b { font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; }
  .tally span { color: var(--dim); font-size: 0.88rem; }
  .tally .bad b { color: var(--seam); }
  .tally .good b { color: var(--royal); }

  .trends { display: grid; gap: 0.9rem; grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr)); }
  .card { background: var(--panel); border: 1px solid var(--rule); padding: 0.95rem 1.05rem 0.8rem; }
  .card h3 { margin: 0; font-size: 0.88rem; font-weight: 600; }
  .card .sub { color: var(--dim); font-size: 0.78rem; margin-bottom: 0.55rem; }
  .card svg { width: 100%; height: 96px; display: block; }
  .legend { display: flex; gap: 0.9rem; margin-top: 0.4rem; font-size: 0.75rem; color: var(--dim); }
  .legend i { display: inline-block; width: 0.7rem; height: 0.15rem; vertical-align: middle; margin-right: 0.3rem; }

  .boards { display: grid; gap: 0.9rem; grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); }
  .board { background: var(--panel); border: 1px solid var(--rule); padding: 0.9rem 1rem 1rem; }
  .board .when { color: var(--dim); font-size: 0.8rem; margin-bottom: 0.6rem;
                 display: flex; justify-content: space-between; gap: 0.6rem; align-items: center; }
  .tag { border: 1px solid var(--rule); padding: 0.05rem 0.4rem; font-size: 0.72rem; color: var(--dim); }
  .board table { width: 100%; border-collapse: collapse; }
  .board th, .board td { text-align: right; padding: 0.25rem 0.1rem; font-size: 0.92rem;
                         border-right: 1px solid var(--rule); }
  .board th { color: var(--dim); font-weight: 500; font-size: 0.75rem; }
  .board th:first-child, .board td:first-child {
    text-align: left; width: 42%; border-right: 2px solid var(--rule);
    padding-right: 0.55rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .board .rhe { border-right: none; font-weight: 600; }
  .board td.r { font-size: 1.1rem; font-weight: 800; }
  .board tr.us td.r { color: var(--royal); }
  .board tr.us td:first-child { font-weight: 600; }
  .board td.e-bad { color: var(--seam); }

  .filter { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0 0 0.9rem; }
  .filter button { font: inherit; font-size: 0.84rem; color: var(--chalk); background: transparent;
    border: 1px solid var(--rule); padding: 0.32rem 0.75rem; cursor: pointer; }
  .filter button:hover { border-color: var(--dim); }
  .filter button[aria-pressed="true"] {
    background: var(--brand); border-color: var(--brand); color: #fff; font-weight: 600; }
  .filter button:focus-visible { outline: 2px solid var(--royal); outline-offset: 2px; }

  .pick { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin: 0 0 0.9rem; }
  .pick label { color: var(--dim); font-size: 0.82rem; }
  .pick select {
    font: inherit; font-size: 0.86rem; color: var(--chalk); background: var(--panel);
    border: 1px solid var(--rule); padding: 0.36rem 0.6rem; max-width: 100%;
    font-variant-numeric: tabular-nums; }
  .pick select:hover { border-color: var(--dim); }
  .pick select:focus-visible { outline: 2px solid var(--royal); outline-offset: 1px; }
  .pick optgroup { background: var(--ink); color: var(--dim); font-style: normal; }
  .pick option { background: var(--panel); color: var(--chalk); }
  .pick .count { color: var(--dim); font-size: 0.8rem; }

  .scroll { overflow-x: auto; }
  table.stat { width: 100%; border-collapse: collapse; font-size: 0.9rem; min-width: 42rem; }
  table.stat th, table.stat td { padding: 0.4rem 0.5rem; text-align: right; white-space: nowrap; }
  table.stat th { color: var(--dim); font-weight: 500; font-size: 0.76rem;
                  border-bottom: 1px solid var(--rule); }
  table.stat td { border-bottom: 1px solid rgba(31,37,50,0.75); }
  table.stat .who { text-align: left; width: 1%; }
  table.stat .num { color: var(--dim); text-align: right; width: 1%; padding-right: 0.15rem; }
  table.stat tbody tr:hover td { background: rgba(31,37,50,0.6); }
  table.stat .lead { color: var(--royal); font-weight: 600; }
  table.stat .flag { color: var(--seam); }
  table.stat tfoot td { border-bottom: none; border-top: 2px solid var(--rule); font-weight: 600; }
  .empty { color: var(--dim); padding: 1.3rem 0; max-width: 52ch; text-align: left; }

  .lineup-grid { display: grid; gap: 1rem; grid-template-columns: minmax(0,1.6fr) minmax(0,1fr);
                 align-items: start; }
  @media (max-width: 46rem) { .lineup-grid { grid-template-columns: 1fr; } }
  #order { min-width: 0; }
  #order td.slot { color: var(--dim); width: 1%; }
  #order .move { display: flex; gap: 0.2rem; justify-content: flex-end; }
  #order .move button { font: inherit; font-size: 0.72rem; line-height: 1; color: var(--chalk);
    background: transparent; border: 1px solid var(--rule); padding: 0.2rem 0.4rem; cursor: pointer; }
  #order .move button:hover:not(:disabled) { border-color: var(--royal); }
  #order .move button:disabled { opacity: 0.3; cursor: default; }
  #order .move button:focus-visible { outline: 2px solid var(--royal); outline-offset: 1px; }
  #order tr.benched td { opacity: 0.42; }
  #order .sit { color: var(--dim); }
  #proj .big { font-size: 2.1rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1.1; }
  #proj .big span { font-size: 0.85rem; font-weight: 400; color: var(--dim); letter-spacing: 0; }
  #proj ul { list-style: none; padding: 0; margin: 0.9rem 0 0; font-size: 0.85rem; }
  #proj li { display: flex; justify-content: space-between; gap: 0.7rem; padding: 0.25rem 0;
             border-top: 1px solid var(--rule); }
  #proj li b { font-weight: 600; }
  #proj .hint { color: var(--dim); font-size: 0.8rem; margin-top: 0.9rem; line-height: 1.45; }

  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--rule);
           color: var(--dim); font-size: 0.8rem; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="crest">
    <img src="logo.png" alt="__LABEL__ club mark" width="512" height="512">
    <div>
      <h1>__LABEL__</h1>
      <div class="season">__SEASON__</div>
    </div>
  </div>
  <nav id="tabs"></nav>
</header>

<section id="tab-overview">
  <div class="filter" id="scope"></div>
  <div class="tally" id="tally"></div>
  <h2>Trends</h2>
  <p class="note" id="trend-note"></p>
  <div class="trends" id="trends"></div>
</section>

<section id="tab-games" hidden>
  <h2>Line scores</h2>
  <div class="boards" id="boards"></div>
</section>

<section id="tab-batting" hidden>
  <h2>Batting</h2>
  <div class="pick" id="filter-bat"></div>
  <div class="scroll"><table class="stat" id="bat"></table></div>
</section>

<section id="tab-pitching" hidden>
  <h2>Pitching</h2>
  <div class="pick" id="filter-pit"></div>
  <div class="scroll"><table class="stat" id="pit"></table></div>
</section>

<section id="tab-lineup" hidden>
  <h2>Lineup projection</h2>
  <p class="note" id="lineup-note"></p>
  <div class="filter" id="lineup-scope"></div>
  <div class="lineup-grid">
    <div><table class="stat" id="order"></table></div>
    <div class="card" id="proj"></div>
  </div>
</section>

<section id="tab-opponents" hidden>
  <h2>Opponents faced</h2>
  <p class="note">Built from the same box scores as our own numbers, so it fills
    in on its own as games go in.</p>
  <div class="scroll"><table class="stat" id="opp"></table></div>
</section>

<footer id="foot"></footer>
</div>

<script id="payload" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("payload").textContent);
const US = D.team;
const short = t => D.short[t] || t;
const rate = v => (v === null || v === undefined || !isFinite(v)) ? "\u2013" : v.toFixed(3).replace(/^0/, "");
const pct = v => (v === null || v === undefined || !isFinite(v)) ? "\u2013" : Math.round(v * 100) + "%";

/* ---------------- tabs ---------------- */
const TABS = [["overview", "Overview"], ["games", "Games"], ["batting", "Batting"],
              ["pitching", "Pitching"], ["lineup", "Lineup"], ["opponents", "Opponents"]];
const nav = document.getElementById("tabs");
nav.innerHTML = TABS.map(([id, t]) => `<a href="#${id}" data-t="${id}">${t}</a>`).join("");
function showTab(id) {
  if (!TABS.some(t => t[0] === id)) id = "overview";
  TABS.forEach(([t]) => {
    document.getElementById("tab-" + t).hidden = (t !== id);
    const a = nav.querySelector(`[data-t="${t}"]`);
    if (t === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
}
addEventListener("hashchange", () => showTab(location.hash.slice(1)));

/* ---------------- game sets ---------------- */
const meta = D.meta || {};
const typeOf = gid => (meta[gid] && meta[gid].game_type) || "";
const isExh = gid => D.exhibition.indexOf(typeOf(gid)) !== -1;

const allMine = D.games.filter(g => g.team === US)
  .sort((a, b) => String(a.date).localeCompare(String(b.date)) || a.game_id.localeCompare(b.game_id));
const counting = allMine.filter(g => !isExh(g.game_id));
const MIXED = counting.length > 0 && counting.length < allMine.length;
/* Scrimmages still tell you plenty at this level, so they're in by default and
   marked rather than dropped. Hollow markers = exhibition. */
let SCOPE = "all";
const scoped = () => SCOPE === "counts" ? counting : allMine;

const sum = (a, k) => a.reduce((s, x) => s + (x[k] || 0), 0);

function renderTally() {
const TREND = scoped();
const w = TREND.filter(g => g.result === "W").length;
const l = TREND.filter(g => g.result === "L").length;
const tie = TREND.filter(g => g.result === "T").length;
const diff = sum(TREND, "R") - sum(TREND, "RA");
document.getElementById("tally").innerHTML = [
  [`${w}\u2013${l}${tie ? "\u2013" + tie : ""}`, TREND.length === 1 ? "game" : "games", ""],
  [sum(TREND, "R"), "runs scored", ""],
  [sum(TREND, "RA"), "runs allowed", ""],
  [(diff > 0 ? "+" : "") + diff, "run differential", diff >= 0 ? "good" : "bad"],
  [sum(TREND, "E"), "errors", sum(TREND, "E") > TREND.length * 2 ? "bad" : ""],
].map(([v, k, cls]) => `<div class="${cls}"><b>${v}</b><span>${k}</span></div>`).join("");

const exh = allMine.length - counting.length;
document.getElementById("trend-note").textContent = SCOPE === "counts"
  ? `${counting.length} counting game${counting.length === 1 ? "" : "s"}. ${exh} scrimmage${exh === 1 ? "" : "s"} set aside.`
  : `All ${allMine.length} games${exh ? `, including ${exh} scrimmage${exh === 1 ? "" : "s"}` : ""}` +
    (exh && allMine.length <= 25 ? " \u2014 hollow markers below." :
     allMine.length > 25 ? ". Charts show a 5-game rolling average over the raw line." : ".");
}

/* ---------------- charts ---------------- */
const W = 300, H = 96, PADL = 24, PADB = 16, PADT = 8;
const px = (i, n) => PADL + (n <= 1 ? (W - PADL) / 2 : i * (W - PADL - 6) / (n - 1));
const py = (v, lo, hi) => (hi === lo) ? (H - PADB + PADT) / 2
  : H - PADB - (v - lo) / (hi - lo) * (H - PADB - PADT);

const axis = (lo, hi, fmt) =>
  `<line x1="${PADL}" y1="${H - PADB}" x2="${W}" y2="${H - PADB}" stroke="var(--rule)"/>
   <text x="0" y="${(py(hi, lo, hi) + 4).toFixed(1)}" fill="var(--dim)" font-size="9">${fmt(hi)}</text>
   <text x="0" y="${(py(lo, lo, hi) + 4).toFixed(1)}" fill="var(--dim)" font-size="9">${fmt(lo)}</text>`;

const DENSE = 25;   /* games, past which raw per-game marks stop helping */
const lineSeries = (vals, lo, hi, colour, exhFlags) => {
  const n = vals.length, dense = n > DENSE;
  const path = v => v.map((x, i) => `${px(i, n).toFixed(1)},${py(x, lo, hi).toFixed(1)}`).join(" ");
  if (dense) {
    /* raw drops back to a faint trace; the rolling mean carries the story */
    return `<polyline points="${path(vals)}" fill="none" stroke="${colour}"
        stroke-width="1" opacity="0.28" stroke-linejoin="round"/>
      <polyline points="${path(roll(vals, 5))}" fill="none" stroke="${colour}"
        stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>`;
  }
  const dots = vals.map((v, i) => {
    const hollow = exhFlags && exhFlags[i];
    return `<circle cx="${px(i, n).toFixed(1)}" cy="${py(v, lo, hi).toFixed(1)}"
      r="${hollow ? 3.1 : 2.6}" fill="${hollow ? "var(--ink)" : colour}"
      stroke="${colour}" stroke-width="${hollow ? 1.5 : 0}"/>`;
  }).join("");
  return `<polyline points="${path(vals)}" fill="none" stroke="${colour}" stroke-width="1.8"
    stroke-linejoin="round" stroke-linecap="round"/>${dots}`;
};

const bars = (vals, hi, colour, exhFlags) => {
  const n = vals.length, dense = n > DENSE;
  const bw = Math.max(1.2, Math.min(26, (W - PADL - 6) / n * (dense ? 0.9 : 0.6)));
  return vals.map((v, i) => {
    const x = px(i, n) - bw / 2, y = py(v, 0, hi), h = Math.max(1, H - PADB - y);
    const hollow = !dense && exhFlags && exhFlags[i];
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}"
      height="${h.toFixed(1)}" fill="${hollow ? "none" : colour}"
      opacity="${dense ? 0.75 : 1}"
      stroke="${colour}" stroke-width="${hollow ? 1.3 : 0}"/>`;
  }).join("");
};

/* Past a handful of games one label per point turns into a grey smear, so
   thin to roughly six evenly spaced ticks and always keep the last one. */
const labels = (texts) => {
  const n = texts.length, step = Math.max(1, Math.ceil(n / 6));
  return texts.map((s, i) => {
    if (i !== n - 1 && (i % step || n - 1 - i < step / 2)) return "";
    const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
    const x = Math.min(Math.max(px(i, n), PADL), W);
    return `<text x="${x.toFixed(1)}" y="${H - 3}" fill="var(--dim)" font-size="9"
      text-anchor="${anchor}">${s}</text>`;
  }).join("");
};

/* A k-game rolling mean. Per-game dots are the signal early and noise late. */
const roll = (vals, k) => vals.map((_, i) => {
  const a = vals.slice(Math.max(0, i - k + 1), i + 1);
  return a.reduce((s, v) => s + v, 0) / a.length;
});

const card = (title, sub, inner, legend) =>
  `<div class="card"><h3>${title}</h3><div class="sub">${sub}</div>
   <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${title}">${inner}</svg>${legend || ""}</div>`;

function perGame(gid) {
  const b = D.batting.filter(r => r.game_id === gid && r.team === US);
  const p = D.pitching.filter(r => r.game_id === gid && r.team === US);
  const s = k => b.reduce((a, r) => a + (r[k] || 0), 0);
  const pa = s("AB") + s("BB") + s("HBP") + s("SF");
  const pitches = p.reduce((a, r) => a + (r.pitches || 0), 0);
  const strikes = p.reduce((a, r) => a + (r.strikes || 0), 0);
  return { obp: pa ? (s("H") + s("BB") + s("HBP")) / pa : 0,
           k: pa ? s("SO") / pa : 0,
           bb: p.reduce((a, r) => a + (r.BB || 0), 0),
           strikePct: pitches ? strikes / pitches : 0 };
}

const tick = g => String(g.date).slice(5).replace("-", "/");

function renderTrends() {
  const TREND = scoped();
  if (!TREND.length) {
    document.getElementById("trends").innerHTML =
      `<p class="empty">No counting games on file yet. Switch to All games, or set
       game_type in data/game_meta.csv once real games start.</p>`;
    return;
  }
  const gs = TREND.map(g => Object.assign({ g, exh: isExh(g.game_id) }, perGame(g.game_id)));
  const flags = gs.map(x => x.exh);
  const lab = gs.map(x => tick(x.g));
  const maxR = Math.max(3, ...gs.map(x => Math.max(x.g.R, x.g.RA)));
  const maxFree = Math.max(4, ...gs.map(x => x.bb + x.g.E));
  /* A hot night can put team OBP over .600; a fixed ceiling clipped the line
     clean off the canvas, which read as missing data rather than a good game. */
  const maxOBP = Math.max(0.6, Math.ceil(Math.max(...gs.map(x => x.obp)) * 10) / 10);

  document.getElementById("trends").innerHTML = [
    card("Runs scored and allowed", "per game",
      axis(0, maxR, v => v)
        + lineSeries(gs.map(x => x.g.RA), 0, maxR, "var(--seam)", flags)
        + lineSeries(gs.map(x => x.g.R), 0, maxR, "var(--royal)", flags)
        + labels(lab),
      `<div class="legend"><span><i style="background:var(--royal)"></i>scored</span>
        <span><i style="background:var(--seam)"></i>allowed</span>
        ${gs.length > 25 ? `<span>heavy line = 5-game average</span>`
          : flags.some(Boolean) ? `<span>hollow = scrimmage</span>` : ""}</div>`),
    card("Team on-base", "OBP by game",
      axis(0, maxOBP, v => v.toFixed(3).replace(/^0/, ""))
        + lineSeries(gs.map(x => x.obp), 0, maxOBP, "var(--royal)", flags) + labels(lab)),
    card("Strike percentage", "of all pitches thrown",
      axis(0, 1, v => Math.round(v * 100) + "%")
        + lineSeries(gs.map(x => x.strikePct), 0, 1, "var(--royal)", flags) + labels(lab)),
    card("Free bases given away", "walks issued plus errors committed",
      axis(0, maxFree, v => v)
        + bars(gs.map(x => x.bb + x.g.E), maxFree, "var(--seam)", flags) + labels(lab)),
  ].join("");
}

/* scope control -- only worth showing once there is actually a mix */
const sc = document.getElementById("scope");
if (MIXED) {
  sc.innerHTML = [["all", "All games"], ["counts", "Counting only"]].map(([v, t], i) =>
    `<button type="button" data-v="${v}" aria-pressed="${i === 0}">${t}</button>`).join("");
  sc.addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    [...sc.querySelectorAll("button")].forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    SCOPE = b.dataset.v;
    renderTally(); renderTrends();
  });
}
renderTally(); renderTrends();

/* ---------------- line scores ---------------- */
const byGame = {};
D.games.forEach(g => (byGame[g.game_id] = byGame[g.game_id] || []).push(g));
const gameIds = allMine.map(g => g.game_id);

document.getElementById("boards").innerHTML = gameIds.map(gid => {
  const rows = byGame[gid];
  const innings = Math.max(...rows.map(r => String(r.by_inning).split("-").length));
  const head = Array.from({ length: innings }, (_, i) => `<th>${i + 1}</th>`).join("");
  const body = rows.map(r => {
    const cs = String(r.by_inning).split("-");
    const cells = cs.map(v => `<td>${v}</td>`).join("") + "<td>\u2013</td>".repeat(innings - cs.length);
    return `<tr class="${r.team === US ? "us" : ""}"><td>${short(r.team)}</td>${cells}
      <td class="rhe r">${r.R}</td><td class="rhe">${r.H}</td>
      <td class="rhe ${r.E >= 3 ? "e-bad" : ""}">${r.E}</td></tr>`;
  }).join("");
  const me = rows.find(r => r.team === US);
  const ty = typeOf(gid);
  return `<div class="board">
    <div class="when"><span>${rows[0].date} \u00b7 ${me.site.toLowerCase()} vs ${short(me.opponent)}</span>
      ${ty ? `<span class="tag">${ty}</span>` : ""}</div>
    <table><thead><tr><th></th>${head}<th>R</th><th>H</th><th>E</th></tr></thead>
    <tbody>${body}</tbody></table></div>`;
}).join("");

/* ---------------- filters ---------------- */
const gameLabel = gid => {
  const me = byGame[gid].find(r => r.team === US);
  const them = byGame[gid].find(r => r.team !== US);
  return `${me.result} ${me.R}\u2013${me.RA} ${short(them.team)}`;
};
function mountFilter(el, onPick) {
  /* A dropdown rather than a row of chips: at 100 games the chips wrap into a
     wall. Games are newest first, grouped by month, since the game you want is
     almost always the one you just played. */
  const groups = {};
  [...gameIds].reverse().forEach(gid => {
    const g = byGame[gid].find(r => r.team === US);
    const d = new Date(String(g.date) + "T12:00:00");
    const key = d.toLocaleString("en-US", { month: "long", year: "numeric" });
    (groups[key] = groups[key] || []).push({ gid, g, d });
  });
  const opt = (v, t) => `<option value="${v}">${t}</option>`;
  const html = [
    opt("all", `All games (${gameIds.length})`),
    MIXED ? opt("counts", `Counting only (${counting.length})`) : "",
    ...Object.entries(groups).map(([month, list]) =>
      `<optgroup label="${month}">${list.map(({ gid, g, d }) => {
        const day = d.toLocaleString("en-US", { month: "short", day: "numeric" });
        const them = byGame[gid].find(r => r.team !== US);
        const ty = typeOf(gid);
        return opt(gid, `${day} \u00b7 ${g.result} ${g.R}\u2013${g.RA} vs ${short(them.team)}` +
                        (isExh(gid) ? " (scrim)" : ty ? ` (${ty})` : ""));
      }).join("")}</optgroup>`),
  ].join("");
  el.innerHTML = `<label for="${el.id}-sel">Show</label>
    <select id="${el.id}-sel">${html}</select>
    <span class="count" id="${el.id}-count"></span>`;
  const sel = el.querySelector("select");
  const note = el.querySelector(".count");
  const fire = () => {
    const n = gameIds.filter(g => inScope(g, sel.value)).length;
    note.textContent = sel.value === "all" || sel.value === "counts"
      ? `${n} game${n === 1 ? "" : "s"}` : "";
    onPick(sel.value);
  };
  sel.addEventListener("change", fire);
  fire();
}

const inScope = (gid, scope) =>
  scope === "all" ? true : scope === "counts" ? !isExh(gid) : gid === scope;

function agg(rows, keys, extra) {
  const by = {};
  rows.forEach(r => {
    const k = r.jersey;
    if (!by[k]) {
      by[k] = { jersey: k, player: r.player, G: 0 };
      keys.forEach(x => by[k][x] = 0);
    }
    const a = by[k]; a.G++;
    if (String(r.player).length > String(a.player).length) a.player = r.player;
    keys.forEach(x => a[x] += r[x] || 0);
    if (extra) extra(a, r);
  });
  return Object.values(by);
}

/* ---------------- batting ---------------- */
function renderBat(scope) {
  const rows = agg(
    D.batting.filter(r => r.team === US && inScope(r.game_id, scope)),
    ["AB", "R", "H", "RBI", "BB", "SO", "HBP", "SF", "SB", "E"],
    (a, r) => a.XBH = (a.XBH || 0) + (r["2B"] || 0) + (r["3B"] || 0) + (r.HR || 0)
  ).sort((a, b) => b.AB - a.AB || a.jersey - b.jersey);
  const el = document.getElementById("bat");
  if (!rows.length) { el.innerHTML = `<caption class="empty">No batting rows for this game.</caption>`; return; }
  const cols = ["G", "AB", "R", "H", "XBH", "RBI", "BB", "SO", "SB", "E"];
  const calc = a => { const pa = a.AB + a.BB + a.HBP + a.SF;
    return { avg: a.AB ? a.H / a.AB : null, obp: pa ? (a.H + a.BB + a.HBP) / pa : null,
             kp: pa ? a.SO / pa : null }; };
  const tot = {};
  rows.forEach(a => [...cols, "HBP", "SF"].forEach(c => tot[c] = (tot[c] || 0) + (a[c] || 0)));
  const tc = calc(tot);
  el.innerHTML = `<thead><tr><th class="num">#</th><th class="who">Batter</th>
    ${cols.map(c => `<th>${c}</th>`).join("")}<th>AVG</th><th>OBP</th><th>K rate</th></tr></thead>
  <tbody>${rows.map(a => { const c = calc(a); return `<tr>
    <td class="num">${a.jersey}</td><td class="who">${a.player}</td>
    ${cols.map(k => `<td class="${k === "E" && a.E > 0 ? "flag" : ""}">${a[k] || 0}</td>`).join("")}
    <td class="${c.avg >= 0.333 ? "lead" : ""}">${rate(c.avg)}</td>
    <td class="${c.obp >= 0.5 ? "lead" : ""}">${rate(c.obp)}</td>
    <td class="${c.kp >= 0.4 ? "flag" : ""}">${pct(c.kp)}</td></tr>`; }).join("")}</tbody>
  <tfoot><tr><td class="num"></td><td class="who">Team</td>
    ${cols.map(c => `<td>${c === "G" ? gameIds.filter(g => inScope(g, scope)).length : tot[c]}</td>`).join("")}
    <td>${rate(tc.avg)}</td><td>${rate(tc.obp)}</td><td>${pct(tc.kp)}</td></tr></tfoot>`;
}

/* ---------------- pitching ---------------- */
function renderPit(scope) {
  const rows = agg(
    D.pitching.filter(r => r.team === US && inScope(r.game_id, scope)),
    ["IP", "BF", "H", "R", "ER", "BB", "SO", "pitches", "strikes"]
  ).sort((a, b) => b.IP - a.IP);
  const el = document.getElementById("pit");
  if (!rows.length) { el.innerHTML = `<caption class="empty">Nobody pitched in this game.</caption>`; return; }
  el.innerHTML = `<thead><tr><th class="num">#</th><th class="who">Pitcher</th>
    <th>G</th><th>IP</th><th>BF</th><th>H</th><th>R</th><th>ER</th><th>BB</th><th>SO</th>
    <th>P</th><th>Strike%</th><th>P/BF</th><th>WHIP</th></tr></thead>
  <tbody>${rows.map(a => {
    const sp = a.pitches ? a.strikes / a.pitches : null;
    const ip = Math.max(a.IP, 0.1);
    return `<tr><td class="num">${a.jersey}</td><td class="who">${a.player}</td>
    <td>${a.G}</td><td>${a.IP.toFixed(1)}</td><td>${a.BF}</td><td>${a.H}</td><td>${a.R}</td>
    <td>${a.ER}</td><td class="${a.BB / ip >= 2 ? "flag" : ""}">${a.BB}</td>
    <td class="${a.SO / ip >= 2 ? "lead" : ""}">${a.SO}</td><td>${a.pitches}</td>
    <td class="${sp !== null && sp < 0.5 ? "flag" : sp >= 0.6 ? "lead" : ""}">${pct(sp)}</td>
    <td>${a.BF ? (a.pitches / a.BF).toFixed(1) : "\u2013"}</td>
    <td>${a.IP ? ((a.BB + a.H) / a.IP).toFixed(2) : "\u2013"}</td></tr>`;
  }).join("")}</tbody>`;
}

/* ---------------- opponents ---------------- */
(function renderOpp() {
  const el = document.getElementById("opp");
  const teams = {};
  D.games.filter(g => g.team !== US).forEach(g => {
    if (!teams[g.team]) teams[g.team] = { team: g.team, G: 0, R: 0, H: 0, E: 0, W: 0 };
    const a = teams[g.team]; a.G++; a.R += g.R; a.H += g.H; a.E += g.E;
    if (g.result === "W") a.W++;
  });
  const rows = Object.values(teams).sort((a, b) => b.G - a.G);
  if (!rows.length) {
    el.innerHTML = `<caption class="empty">No opponents on file. Drop a box score into
      data/raw/boxscores and rerun the parser.</caption>`;
    return;
  }
  el.innerHTML = `<thead><tr><th class="who">Team</th><th>Games</th><th>Record vs us</th>
    <th>Runs</th><th>Hits</th><th>Errors</th><th>Batters logged</th><th>Pitchers logged</th></tr></thead>
  <tbody>${rows.map(a => {
    const b = new Set(D.batting.filter(r => r.team === a.team).map(r => r.jersey)).size;
    const p = new Set(D.pitching.filter(r => r.team === a.team).map(r => r.jersey)).size;
    return `<tr><td class="who">${short(a.team)}</td><td>${a.G}</td>
      <td>${a.W}\u2013${a.G - a.W}</td><td>${a.R}</td><td>${a.H}</td><td>${a.E}</td>
      <td>${b}</td><td>${p}</td></tr>`;
  }).join("")}</tbody>`;
})();


/* ---------------- lineup projection ---------------- */
/* A Monte Carlo over the order. Each batter's per-PA outcome rates come from
   their own line, regressed toward the team rate -- with 20-odd plate
   appearances on file, raw rates would swing the projection wildly on one
   lucky double. PRIOR is the weight of that regression in PA. */
const PRIOR = 25, INNINGS = 6, SIMS = 1500;
let LSCOPE = "all", ORDER = null, SITTING = new Set();

function batterRates(scope) {
  const rows = agg(
    D.batting.filter(r => r.team === US && inScope(r.game_id, scope)),
    ["AB", "H", "BB", "SO", "HBP", "SF", "RBI", "R"],
    (a, r) => a.XBH = (a.XBH || 0) + (r["2B"] || 0) + (r["3B"] || 0) + (r.HR || 0)
  );
  const T = rows.reduce((t, a) => {
    ["AB", "H", "BB", "HBP", "SF"].forEach(k => t[k] += a[k] || 0);
    t.XBH += a.XBH || 0; return t;
  }, { AB: 0, H: 0, BB: 0, HBP: 0, SF: 0, XBH: 0 });
  const tPA = T.AB + T.BB + T.HBP + T.SF || 1;
  const tm = { bb: (T.BB + T.HBP) / tPA, xbh: T.XBH / tPA, s1: (T.H - T.XBH) / tPA };

  return rows.map(a => {
    const pa = a.AB + a.BB + a.HBP + a.SF;
    const mix = (own, team) => (own + team * PRIOR) / (pa + PRIOR);
    const bb = mix(a.BB + a.HBP, tm.bb);
    const xbh = mix(a.XBH || 0, tm.xbh);
    const s1 = mix(a.H - (a.XBH || 0), tm.s1);
    return { jersey: a.jersey, player: a.player, PA: pa,
             obp: pa ? (a.H + a.BB + a.HBP) / pa : 0,
             bb, s1, xbh, out: Math.max(0, 1 - bb - s1 - xbh) };
  }).filter(r => r.PA > 0);
}

function simulate(order) {
  if (!order.length) return { rpg: 0, dist: {} };
  let total = 0, spot = 0;
  const scores = [];
  for (let g = 0; g < SIMS; g++) {
    let runs = 0; spot = 0;
    for (let inn = 0; inn < INNINGS; inn++) {
      let outs = 0, b = [0, 0, 0];   /* occupancy of 1st, 2nd, 3rd */
      while (outs < 3) {
        const p = order[spot % order.length]; spot++;
        const r = Math.random();
        if (r < p.bb + p.s1) {                 /* walk or single: force one */
          runs += b[2]; b[2] = b[1]; b[1] = b[0]; b[0] = 1;
        } else if (r < p.bb + p.s1 + p.xbh) {  /* extra-base: clear two bases */
          runs += b[2] + b[1]; b[2] = b[0]; b[1] = 1; b[0] = 0;
        } else outs++;
      }
    }
    total += runs; scores.push(runs);
  }
  scores.sort((a, b) => a - b);
  return { rpg: total / SIMS,
           lo: scores[Math.floor(SIMS * 0.15)],
           hi: scores[Math.floor(SIMS * 0.85)] };
}

function bestOrder(pool) {
  /* Greedy: highest on-base first is the standard heuristic and beats
     hand-sorting almost every time at this level. */
  return [...pool].sort((a, b) => (b.bb + b.s1 + b.xbh) - (a.bb + a.s1 + a.xbh));
}

function renderLineup() {
  const pool = batterRates(LSCOPE);
  const el = document.getElementById("order"), pr = document.getElementById("proj");
  if (!pool.length) {
    el.innerHTML = `<caption class="empty">No batters in this scope yet.</caption>`;
    pr.innerHTML = ""; return;
  }
  if (!ORDER || ORDER.some(j => !pool.find(p => p.jersey === j))
             || pool.some(p => ORDER.indexOf(p.jersey) === -1)) {
    ORDER = bestOrder(pool).map(p => p.jersey);
    SITTING = new Set();
  }
  const byJ = Object.fromEntries(pool.map(p => [p.jersey, p]));
  const active = ORDER.filter(j => !SITTING.has(j)).map(j => byJ[j]);

  el.innerHTML = `<thead><tr><th class="slot">#</th><th class="who">Batter</th>
    <th>PA</th><th>OBP</th><th>XBH rate</th><th></th></tr></thead>
  <tbody>${ORDER.map((j, i) => {
    const p = byJ[j], sat = SITTING.has(j);
    const slot = sat ? "\u2013" : active.findIndex(a => a.jersey === j) + 1;
    return `<tr class="${sat ? "benched" : ""}">
      <td class="slot">${slot}</td>
      <td class="who">${p.player} <span class="sit">#${p.jersey}</span></td>
      <td>${p.PA}</td><td>${rate(p.obp)}</td><td>${pct(p.xbh)}</td>
      <td class="move">
        <button type="button" data-up="${i}" ${i === 0 ? "disabled" : ""} aria-label="Move ${p.player} up">\u2191</button>
        <button type="button" data-down="${i}" ${i === ORDER.length - 1 ? "disabled" : ""} aria-label="Move ${p.player} down">\u2193</button>
        <button type="button" data-sit="${j}" aria-label="${sat ? "Add" : "Bench"} ${p.player}">${sat ? "in" : "sit"}</button>
      </td></tr>`;
  }).join("")}</tbody>`;

  const mine = simulate(active);
  const opt = simulate(bestOrder(active));
  const gain = opt.rpg - mine.rpg;
  pr.innerHTML = `<h3>Projected offense</h3>
    <div class="sub">${SIMS.toLocaleString()} simulated ${INNINGS}-inning games</div>
    <div class="big">${mine.rpg.toFixed(1)} <span>runs per game</span></div>
    <ul>
      <li><span>Typical range</span><b>${mine.lo}\u2013${mine.hi}</b></li>
      <li><span>Batting ${active.length}</span><b>${active.length ? active[0].player : "\u2013"} leading off</b></li>
      <li><span>Best on-base order</span><b>${opt.rpg.toFixed(1)}</b></li>
      <li><span>On the table</span><b class="${gain > 0.3 ? "flag" : ""}">${gain > 0 ? "+" : ""}${gain.toFixed(1)}</b></li>
    </ul>
    <p class="hint">Rates are regressed toward the team average using a ${PRIOR}-PA
      prior, so nobody's projection swings on one lucky double. The gap between
      your order and the on-base order is usually under a run \u2014 lineup order
      matters far less than who is in it.</p>`;
}

document.getElementById("order").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.up !== undefined) {
    const i = +b.dataset.up; [ORDER[i - 1], ORDER[i]] = [ORDER[i], ORDER[i - 1]];
  } else if (b.dataset.down !== undefined) {
    const i = +b.dataset.down; [ORDER[i + 1], ORDER[i]] = [ORDER[i], ORDER[i + 1]];
  } else if (b.dataset.sit !== undefined) {
    const j = +b.dataset.sit;
    SITTING.has(j) ? SITTING.delete(j) : SITTING.add(j);
  }
  renderLineup();
});

(function mountLineupScope() {
  const el = document.getElementById("lineup-scope");
  const opts = [["all", "All games"]].concat(MIXED ? [["counts", "Counting only"]] : []);
  if (opts.length > 1) {
    el.innerHTML = opts.map(([v, t], i) =>
      `<button type="button" data-v="${v}" aria-pressed="${i === 0}">${t}</button>`).join("");
    el.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      [...el.querySelectorAll("button")].forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      LSCOPE = b.dataset.v; ORDER = null; renderLineup();
    });
  }
})();
document.getElementById("lineup-note").textContent =
  `Reorder with the arrows, bench anyone with "sit". Projection updates as you go.`;
renderLineup();

mountFilter(document.getElementById("filter-bat"), renderBat);
mountFilter(document.getElementById("filter-pit"), renderPit);
showTab(location.hash.slice(1));
document.getElementById("foot").textContent =
  `${gameIds.length} games on file. Built ${D.built}.`;
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--outdir", default="docs")
    ap.add_argument("--team", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--season", default="")
    args = ap.parse_args()

    d = pathlib.Path(args.data)
    games = pd.read_csv(d / "games.csv")
    bat = pd.read_csv(d / "batting_by_game.csv")
    pit = pd.read_csv(d / "pitching_by_game.csv")

    meta = {}
    mp = d / "game_meta.csv"
    if mp.exists():
        md = pd.read_csv(mp).fillna("")
        meta = {r["game_id"]: {k: r[k] for k in md.columns if k != "game_id"}
                for _, r in md.iterrows()}
        missing = set(games["game_id"]) - set(meta)
        if missing:
            print(f"  note: {len(missing)} game(s) have no row in game_meta.csv")

    # GameChanger truncates at a different point in each table, so #12 can be
    # "L Bruckner" in batting and "L Bruck" in pitching. Resolve one name per
    # jersey per team across every row, and use it everywhere.
    names = {}
    for df in (bat, pit):
        for r in df.itertuples():
            key = (r.team, int(r.jersey))
            if len(str(r.player)) > len(names.get(key, "")):
                names[key] = str(r.player)
    for df in (bat, pit):
        df["player"] = [names[(t, int(j))] for t, j in zip(df["team"], df["jersey"])]

    teams = sorted(set(games["team"]) | set(games["opponent"]))
    shorts = {t: " ".join(t.replace("LadyDukesWPA", "LD ").replace("LadyDukes", "LD ").split())[:18]
              for t in teams}

    season = args.season or (
        f"{games['date'].min()} to {games['date'].max()}"
        if games["date"].min() != games["date"].max() else games["date"].min())

    payload = {
        "team": args.team, "label": args.label, "short": shorts,
        "exhibition": EXHIBITION,
        "built": pd.Timestamp.today().strftime("%b %-d, %Y"),
        "meta": meta,
        "games": games.to_dict("records"),
        "batting": bat.fillna(0).to_dict("records"),
        "pitching": pit.fillna(0).to_dict("records"),
    }

    html = (TEMPLATE
            .replace("__LABEL__", args.label)
            .replace("__SEASON__", season)
            .replace("__DATA__", json.dumps(payload, default=str)))

    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"wrote {out / 'index.html'} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
