/* WC26 DESK — static dashboard over data/*.json (no build step) */

const $app = document.getElementById("app");
const cache = new Map();
let INDEX = null;

async function fetchJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  const json = await res.json();
  cache.set(path, json);
  return json;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const units = (n) => `${(+n).toFixed(2).replace(/\.00$/, "")}u`;
const pct = (n) => `${Math.round(n * 100)}%`;
const kickoffLocal = (iso) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" });
const stageLabel = (f) =>
  (f.group || f.stage || "").replace(/_/g, " ").replace(/GROUP STAGE/i, "").trim() || "WC26";

const MARKET_LABEL = {
  h2h: (l, names) => names?.[l.selection] || l.selection,
  totals: (l) => `${l.selection} ${l.line} goals`,
  btts: (l) => `BTTS: ${l.selection}`,
};
function legLabel(leg, ticket) {
  const names = ticket
    ? { home: ticket.home, draw: "Draw", away: ticket.away }
    : { home: "Home", draw: "Draw", away: "Away" };
  return (MARKET_LABEL[leg.market] || ((l) => l.selection))(leg, names);
}

/* ---------- data assembly ---------- */

async function loadDay(date) {
  const ids = (INDEX.tickets || {})[date] || [];
  const [fixtures, odds, slips, tickets] = await Promise.all([
    INDEX.fixtures.includes(date) ? fetchJSON(`data/fixtures/${date}.json`) : null,
    INDEX.odds.includes(date) ? fetchJSON(`data/odds/${date}.json`) : null,
    INDEX.betslips.includes(date) ? fetchJSON(`data/betslips/${date}.json`) : null,
    Promise.all(ids.map((id) => fetchJSON(`data/tickets/${date}/${id}.json`).catch(() => null))),
  ]);
  return {
    date,
    fixtures: fixtures?.matches || [],
    odds: Object.fromEntries((odds?.matches || []).map((m) => [m.match_id, m])),
    slips: slips?.slips || [],
    tickets: Object.fromEntries(tickets.filter(Boolean).map((t) => [t.match_id, t])),
  };
}

function picksByMatch(slips) {
  const map = {};
  for (const slip of slips)
    for (const leg of slip.legs)
      (map[leg.match_id] = map[leg.match_id] || []).push(leg);
  return map;
}

/* ---------- renderers ---------- */

function matchCard(fix, ticket, picks, i) {
  const t = ticket;
  const probs = t?.prediction?.probs;
  const probBar = probs
    ? `<div class="prob-bar">
         <div class="p-home" style="width:${probs.home * 100}%"></div>
         <div class="p-draw" style="width:${probs.draw * 100}%"></div>
         <div class="p-away" style="width:${probs.away * 100}%"></div>
       </div>
       <div class="prob-legend">
         <span><b>${pct(probs.home)}</b> ${esc(fix.home)}</span>
         <span><b>${pct(probs.draw)}</b> draw</span>
         <span><b>${pct(probs.away)}</b> ${esc(fix.away)}</span>
       </div>`
    : `<div class="conf">analysis pending…</div>`;
  const factors = (t?.analysis?.key_factors || []).slice(0, 3)
    .map((f) => `<li>${esc(f)}</li>`).join("");
  const pickChips = (picks || []).map((l) =>
    `<span class="pick-chip">${esc(legLabel(l, t))} <span class="odds">@${+l.odds || "?"}</span></span>`).join("");
  return `<article class="match-card rise" style="animation-delay:${i * 60}ms">
    <div class="mc-top"><span>${esc(stageLabel(fix))}</span><span>${kickoffLocal(fix.kickoff_utc)}</span></div>
    <div class="mc-teams">
      <div class="vs">${esc(fix.home)} <span style="color:var(--ink-dim)">v</span> ${esc(fix.away)}</div>
      ${t ? `<div class="score-pred">predicted <b>${esc(t.prediction.predicted_score)}</b></div>` : ""}
    </div>
    ${probBar}
    ${t?.analysis?.summary ? `<p class="mc-summary">${esc(t.analysis.summary)}</p>` : ""}
    ${factors ? `<ul class="mc-factors">${factors}</ul>` : ""}
    ${pickChips ? `<div class="mc-picks">${pickChips}</div>` : ""}
    ${t ? `<div class="conf">confidence ${pct(t.prediction.confidence)}</div>` : ""}
  </article>`;
}

function slipCard(slip, ticketsById, i) {
  const legs = slip.legs.map((l) => {
    const t = ticketsById[l.match_id];
    return `<div class="leg">
      <div class="leg-pick"><span>${esc(legLabel(l, t))}</span><span class="lodds">@${+l.odds || "?"}</span></div>
      ${t ? `<div class="leg-match">${esc(t.home)} v ${esc(t.away)}</div>` : ""}
      ${l.rationale ? `<div class="leg-why">${esc(l.rationale)}</div>` : ""}
    </div>`;
  }).join("");
  const ret = slip.status === "pending"
    ? `<span>to return <b>${units(slip.stake * slip.combined_odds)}</b></span>`
    : slip.status === "lost"
      ? `<span class="lost-amt">returned <b>0u</b></span>`
      : `<span>returned <b>${units(slip.payout)}</b></span>`;
  return `<article class="slip rise" style="animation-delay:${i * 60}ms">
    <div class="slip-head">
      <span class="slip-id">${esc(slip.slip_id)}</span>
      <span class="slip-type">${esc(slip.type)}</span>
      <span class="status ${esc(slip.status)}">${esc(slip.status)}</span>
    </div>
    <div class="slip-legs">${legs}</div>
    <div class="slip-foot">
      <span>stake <b>${units(slip.stake)}</b> @ ${+slip.combined_odds || "?"}</span>${ret}
    </div>
  </article>`;
}

function bankrollCurve(history, starting) {
  if (!history.length) return `<p class="empty">No settled days yet.</p>`;
  const pts = [{ date: "start", bankroll: starting }, ...history];
  const w = 720, h = 180, pad = 28;
  const vals = pts.map((p) => p.bankroll);
  const min = Math.min(...vals) - 5, max = Math.max(...vals) + 5;
  const x = (i) => pad + (i * (w - 2 * pad)) / Math.max(pts.length - 1, 1);
  const y = (v) => h - pad - ((v - min) * (h - 2 * pad)) / (max - min || 1);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.bankroll).toFixed(1)}`).join(" ");
  const base = y(starting);
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Bankroll over time">
    <line x1="${pad}" y1="${base}" x2="${w - pad}" y2="${base}" stroke="var(--card-edge)" stroke-dasharray="4 4"/>
    <path d="${path}" fill="none" stroke="var(--lime)" stroke-width="2.5" stroke-linejoin="round"/>
    ${pts.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.bankroll)}" r="3" fill="var(--lime)">
      <title>${p.date}: ${p.bankroll}u</title></circle>`).join("")}
    <text x="${pad}" y="${h - 8}" fill="var(--ink-dim)" font-size="10" font-family="var(--mono)">${pts[1]?.date || ""}</text>
    <text x="${w - pad}" y="${h - 8}" fill="var(--ink-dim)" font-size="10" font-family="var(--mono)" text-anchor="end">${pts.at(-1).date}</text>
  </svg>`;
}

/* ---------- views ---------- */

async function viewToday() {
  const date = INDEX.fixtures.at(-1);
  if (!date) return emptyState("No fixtures yet", "The first /daily-run will populate today’s matches.");
  const day = await loadDay(date);
  if (!day.fixtures.length) return emptyState(`Rest day (${date})`, "No matches scheduled.");
  const picks = picksByMatch(day.slips);
  const staked = day.slips.reduce((s, x) => s + x.stake, 0);
  return `<div class="section-head">
      <h2>Matchday — ${date}</h2>
      <span class="sub">${day.fixtures.length} matches · ${day.slips.length} slips · ${units(staked)} staked</span>
    </div>
    <div class="match-grid">
      ${day.fixtures.map((f, i) => matchCard(f, day.tickets[f.match_id], picks[f.match_id], i)).join("")}
    </div>`;
}

async function viewSlips() {
  const dates = [...INDEX.betslips].reverse();
  if (!dates.length) return emptyState("No betslips yet", "Slips appear after the first /daily-run finds value.");
  const sections = [];
  for (const date of dates) {
    const day = await loadDay(date);
    if (!day.slips.length) continue;
    sections.push(`<div class="section-head"><h2>${date}</h2>
        <span class="sub">${day.slips.length} slip(s)</span></div>
      <div class="slip-grid">${day.slips.map((s, i) => slipCard(s, day.tickets, i)).join("")}</div>`);
  }
  return sections.join("") || emptyState("No bets placed", "The team found no qualifying edges yet — discipline over action.");
}

async function viewRecord() {
  if (!INDEX.has_ledger) return emptyState("No track record yet", "The ledger builds once slips settle.");
  const ledger = await fetchJSON("data/ledger.json");
  const s = ledger.stats;
  const acc = await predictionAccuracy();
  const cls = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
  const stats = [
    ["Bankroll", `${ledger.bankroll}u`, cls(ledger.bankroll - ledger.starting_bankroll)],
    ["Profit", `${s.profit > 0 ? "+" : ""}${s.profit}u`, cls(s.profit)],
    ["ROI", pct(s.roi), cls(s.roi)],
    ["Hit rate", pct(s.hit_rate), ""],
    ["Record", `${s.slips_won}W–${s.slips_lost}L–${s.slips_void}V`, ""],
    ["Pending", `${s.slips_pending}`, ""],
    ["1X2 accuracy", acc.total ? `${acc.correct}/${acc.total}` : "—", ""],
  ].map(([k, v, c]) => `<div class="stat rise"><div class="k">${k}</div><div class="v ${c}">${v}</div></div>`).join("");
  const markets = Object.entries(s.by_market).map(([m, v]) => {
    const pl = (v.returned - v.staked).toFixed(2);
    return `<tr><td>${m}</td><td>${v.won}W–${v.lost}L</td><td>${v.staked}u</td>
      <td>${v.returned}u</td><td class="${cls(+pl)}">${+pl > 0 ? "+" : ""}${pl}u</td></tr>`;
  }).join("");
  return `<div class="stat-grid">${stats}</div>
    <div class="curve-wrap rise"><h3>Bankroll curve</h3>${bankrollCurve(ledger.history, ledger.starting_bankroll)}</div>
    <div class="tbl-wrap rise"><h3>By market (singles)</h3>
      <table><thead><tr><th>Market</th><th>Record</th><th>Staked</th><th>Returned</th><th>P/L</th></tr></thead>
      <tbody>${markets}</tbody></table></div>`;
}

async function predictionAccuracy() {
  let correct = 0, total = 0;
  for (const date of INDEX.results) {
    const ids = (INDEX.tickets || {})[date] || [];
    if (!ids.length) continue;
    try {
      const results = await fetchJSON(`data/results/${date}.json`);
      const byId = Object.fromEntries(results.matches.map((m) => [m.match_id, m]));
      for (const id of ids) {
        const r = byId[id];
        if (!r || r.status !== "FINISHED") continue;
        const t = await fetchJSON(`data/tickets/${date}/${id}.json`).catch(() => null);
        const p = t?.prediction?.probs;
        if (!p) continue;
        const predicted = Object.entries(p).sort((a, b) => b[1] - a[1])[0][0];
        const actual = r.home_goals > r.away_goals ? "home" : r.away_goals > r.home_goals ? "away" : "draw";
        total++;
        if (predicted === actual) correct++;
      }
    } catch { /* missing day file — skip */ }
  }
  return { correct, total };
}

async function viewMatches() {
  const dates = Object.keys(INDEX.tickets || {}).sort().reverse();
  if (!dates.length) return emptyState("No analyses yet", "Analysis tickets appear after the first /daily-run.");
  return dates.map((date, di) => {
    const n = INDEX.tickets[date].length;
    return `<details class="day rise" style="animation-delay:${di * 40}ms" data-date="${date}" ${di === 0 ? "open" : ""}>
      <summary>${date}<span class="count">${n} match analyses</span></summary>
      <div class="match-grid" data-host></div>
    </details>`;
  }).join("");
}

async function hydrateDay(el) {
  const host = el.querySelector("[data-host]");
  if (host.dataset.loaded) return;
  host.dataset.loaded = "1";
  host.innerHTML = `<div class="loading">Loading…</div>`;
  const day = await loadDay(el.dataset.date);
  const picks = picksByMatch(day.slips);
  const fixtures = day.fixtures.length
    ? day.fixtures
    : Object.values(day.tickets); // fixtures file missing — tickets carry teams/kickoff
  host.innerHTML = fixtures.map((f, i) => matchCard(f, day.tickets[f.match_id], picks[f.match_id], i)).join("")
    || `<div class="empty">No data for this day.</div>`;
}

function emptyState(title, sub) {
  return `<div class="empty rise"><strong>${esc(title)}</strong>${esc(sub)}</div>`;
}

/* ---------- shell ---------- */

const VIEWS = { today: viewToday, slips: viewSlips, record: viewRecord, matches: viewMatches };

async function route() {
  const view = (location.hash || "#today").slice(1);
  const fn = VIEWS[view] || viewToday;
  document.querySelectorAll(".tabs a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === (VIEWS[view] ? view : "today")));
  $app.innerHTML = `<div class="loading">Loading…</div>`;
  try {
    $app.innerHTML = await fn();
  } catch (e) {
    $app.innerHTML = emptyState("Could not load data", String(e.message || e));
  }
  $app.querySelectorAll("details.day").forEach((d) => {
    d.addEventListener("toggle", () => d.open && hydrateDay(d));
    if (d.open) hydrateDay(d);
  });
}

async function bankrollChip() {
  if (!INDEX.has_ledger) return;
  try {
    const ledger = await fetchJSON("data/ledger.json");
    document.getElementById("chip-bankroll").textContent = `${ledger.bankroll}u`;
    const d = +(ledger.bankroll - ledger.starting_bankroll).toFixed(2);
    const el = document.getElementById("chip-delta");
    el.textContent = d === 0 ? "" : `${d > 0 ? "▲ +" : "▼ "}${d}u`;
    el.className = `chip-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}`;
  } catch { /* chip stays blank */ }
}

(async function boot() {
  try {
    INDEX = await fetchJSON("data/index.json");
  } catch (e) {
    $app.innerHTML = emptyState("No data yet", "Run /daily-run to generate the first matchday data.");
    return;
  }
  bankrollChip();
  window.addEventListener("hashchange", route);
  route();
})();
