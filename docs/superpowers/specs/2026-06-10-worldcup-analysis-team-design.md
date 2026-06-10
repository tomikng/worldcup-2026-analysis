# World Cup 2026 AI Analysis Team — Implementation Plan

## Context

Tomas wants a functioning AI agent team that analyzes every 2026 World Cup match (tournament starts **tomorrow, June 11, 2026**; 104 matches through July 19), produces a structured **analysis ticket** per match, composes daily **betting ticket recommendations** (analysis only — no real-money placement), tracks its own performance with a **virtual paper-trail bankroll**, and surfaces everything on a **hosted dashboard**. It must run automatically on a schedule.

Decisions made with the user:
- **Betting scope:** analysis & recommendations only; virtual stakes, paper-trail tracking with ROI/hit-rate/bankroll curve.
- **Coverage:** every match, every day, full analysis ticket each.
- **Runtime:** Claude Code agents + scheduled cloud routines (via `/schedule`), with manual slash-command triggers as backup.
- **Data budget:** free tiers only.
- **Architecture:** Git-as-database — all data as JSON in the repo; static dashboard auto-deployed on push.

Key data-source findings (verified 2026-06-10):
- **football-data.org free tier includes the FIFA World Cup** (fixtures, standings, delayed results; 10 req/min; free API key required — register at football-data.org). Round-of-32 placeholders and paginated fixtures are quirks to handle.
- **The Odds API free tier no longer covers soccer/World Cup** (NBA/MLB only). Odds must come from **agent web research** (public odds pages: Oddschecker, Covers, bookmaker public pages) and optionally Polymarket's free public API for implied probabilities.

## Architecture

```
GitHub repo (data + code + dashboard)
        ▲ commit/push
Claude Code cloud routine (daily cron)
  1. settle yesterday  →  2. fetch today's fixtures  →  3. analyze each match
  4. research odds     →  5. build betting tickets   →  6. update ledger, push
        ▼ on push
GitHub Pages serves static dashboard reading data/*.json
```

One combined daily routine (morning, Europe time — after the previous night's North-America matches finish): settle yesterday's slips first, then produce today's analysis. Manual `/daily-run` and `/settle` commands allow on-demand runs.

## Repo structure

```
WorldCup/
├── CLAUDE.md                      # conventions, data schemas, agent guardrails
├── .claude/
│   ├── agents/
│   │   ├── match-analyst.md       # per-match deep analysis subagent
│   │   ├── odds-researcher.md     # web-research odds for the day's matches
│   │   └── ticket-builder.md      # composes the day's betting tickets + stakes
│   └── skills/
│       ├── daily-run/SKILL.md     # /daily-run — full pipeline orchestration
│       └── settle/SKILL.md        # /settle — fetch results, grade, settle ledger
├── scripts/
│   ├── fetch_fixtures.py          # football-data.org → data/fixtures/YYYY-MM-DD.json
│   ├── fetch_results.py           # finished matches → data/results/YYYY-MM-DD.json
│   └── settle.py                  # deterministic settlement math (P/L, ROI, bankroll)
├── data/
│   ├── fixtures/                  # one JSON per day
│   ├── results/                   # one JSON per day
│   ├── tickets/YYYY-MM-DD/        # one analysis-ticket JSON per match
│   ├── betslips/                  # one JSON per day (singles + accumulator)
│   └── ledger.json                # bankroll, all slips with status, running stats
├── dashboard/                     # static SPA (index.html + app.js + style.css)
└── docs/superpowers/specs/        # this design, committed
```

## Components

**1. Data scripts (Python, stdlib + `requests`)**
- `fetch_fixtures.py` / `fetch_results.py` hit football-data.org (`FOOTBALL_DATA_TOKEN` env var, gitignored `.env`). If the token is absent (e.g., in a cloud routine without secrets), the skill instructs the agent to fall back to web research (FIFA/BBC public pages) and write the same JSON schema.
- `settle.py` is pure deterministic math: reads `betslips/` + `results/`, grades each leg, updates `ledger.json` (starting bankroll 1000 units, flat 10-unit base stakes scaled 5–20 by confidence). **Build this with TDD** — it's the one piece where a bug silently corrupts the whole track record.

**2. Agent team (`.claude/agents/`)**
- `match-analyst`: input = one fixture + odds context; does web research (team news, injuries, form, h2h); output = analysis ticket JSON: probabilities (home/draw/away), predicted score, key factors, confidence, value notes. One agent per match, run in parallel.
- `odds-researcher`: gathers best-available decimal odds per match for h2h / totals / BTTS from public odds pages; outputs a normalized odds JSON used by analysts and the ticket builder.
- `ticket-builder`: reads all of today's analysis tickets + odds; picks value bets (model probability vs implied odds edge ≥ threshold), composes singles + one daily accumulator with virtual stakes; writes `betslips/YYYY-MM-DD.json` with status `pending`.

**3. Orchestration skills**
- `/daily-run`: settle yesterday (invoke settle flow) → fetch fixtures → spawn odds-researcher → spawn match-analysts in parallel (up to 6 matches/day in group stage) → spawn ticket-builder → regenerate dashboard data index → commit & push with message `daily: YYYY-MM-DD`.
- `/settle`: fetch results → run `settle.py` → grade prediction accuracy on analysis tickets → commit & push.

**4. Dashboard (static, GitHub Pages)**
- Single-page app, no build step, plain HTML/JS fetching `../data/*.json` by relative path. Pages: **Today** (match cards with analysis + recommendations), **Betslips** (pending/settled, P/L per slip), **Track record** (bankroll curve, ROI, hit rate by market, prediction accuracy), **All matches** (browse past tickets).
- Use the `frontend-design` skill when building it for a polished result.
- Hosted via GitHub Pages on the repo (free, redeploys on every push — fits the git-as-database flow). A small index file `data/index.json` lists available dates so the SPA doesn't need directory listing.

**5. Scheduling**
- Use `/schedule` to create a cloud routine: daily at ~09:00 Europe time, prompt = run `/daily-run`. Requires the repo pushed to GitHub first.
- Document manual fallback: run `/daily-run` in a local session anytime.

## Implementation order

1. **Scaffold:** `git init`, GitHub repo (ask user for repo name/visibility at creation time), CLAUDE.md with schemas + guardrails (responsible-gambling framing: virtual stakes only, never real placement), `.gitignore` (`.env`), commit design doc.
2. **Data layer:** JSON schemas; `fetch_fixtures.py`, `fetch_results.py`; needs user to register a free football-data.org API key — pause and ask for it when reached.
3. **Settlement engine (TDD):** `settle.py` + tests covering win/loss/void legs, accumulators, bankroll math.
4. **Agents + skills:** the three agent definitions, `/daily-run`, `/settle`.
5. **Dashboard:** static SPA + `data/index.json` generation; enable GitHub Pages.
6. **Schedule:** create the cloud routine via `/schedule`.
7. **Live dry run:** execute `/daily-run` for June 11's opening matches end-to-end.

## Verification

- `settle.py` unit tests pass (pytest).
- Run `/daily-run` manually: confirm fixtures fetched for June 11, one analysis ticket per match in `data/tickets/2026-06-11/`, a betslip JSON with stakes and combined odds, ledger updated, push succeeds.
- Open the dashboard locally (`python -m http.server`) and on the GitHub Pages URL: today's matches render with analysis and recommendations.
- Simulate settlement with a fabricated result file → ledger P/L and dashboard track record update correctly; then verify with the real opening-match result on June 12's run.
- Confirm the scheduled routine fires (check first morning's auto-commit).

## Out of scope (explicitly)

- Real-money bet placement or bookmaker account integration.
- Live/in-play odds feeds (free tier doesn't allow; daily snapshots via web research instead).
- Paid data sources — can be slotted in later behind `fetch_*` scripts if desired.
