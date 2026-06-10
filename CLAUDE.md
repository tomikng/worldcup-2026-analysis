# World Cup 2026 AI Analysis Team

An automated agent team that analyzes every 2026 FIFA World Cup match (June 11 – July 19, 2026, 104 matches), produces per-match analysis tickets, composes daily betting-ticket recommendations with **virtual stakes only**, and tracks its own performance.

## Hard guardrails

- **Never place, automate, or facilitate real-money bets.** All stakes are virtual units against a simulated bankroll. Recommendations are analysis, not financial advice.
- **Never invent data.** Every odds value must come from a fetched source recorded in `sources`. If odds can't be found for a market, omit that market.
- **The ledger is append-only truth.** Never hand-edit `data/ledger.json`; it is rebuilt by `scripts/settle.py`.
- Timestamps are always UTC ISO-8601 (`2026-06-11T19:00:00Z`). A **matchday** `YYYY-MM-DD` covers kickoffs from 06:00 UTC that day to 05:59 UTC the next day — North-America evening games that cross UTC midnight belong to the previous (local) matchday.

## Pipeline (what /daily-run does)

1. Settle yesterday: `python3 scripts/fetch_results.py <yesterday>` then `python3 scripts/settle.py`
2. Fetch today: `python3 scripts/fetch_fixtures.py <today>`
3. `odds-researcher` agent → `data/odds/<today>.json`
4. One `match-analyst` agent per fixture (parallel) → `data/tickets/<today>/<match_id>.json`
5. `ticket-builder` agent → `data/betslips/<today>.json`
6. `python3 scripts/build_index.py` (regenerates `data/index.json` for the dashboard)
7. Commit (`daily: YYYY-MM-DD`) and push — the dashboard on GitHub Pages updates on push.

## Data sources (free tier)

- **Fixtures/results:** football-data.org v4, competition code `WC`, header `X-Auth-Token` from `FOOTBALL_DATA_TOKEN` (in gitignored `.env`). 10 req/min. If the token is missing, the scripts exit with code 2 and agents fall back to web research (fifa.com, bbc.com/sport) writing the identical schema.
- **Odds:** no free odds API covers the World Cup — the `odds-researcher` agent web-researches public odds pages (oddschecker.com, covers.com, oddsportal.com, bookmaker public sites) and records the sources used.

## JSON schemas (data/)

All files written by scripts or agents MUST match these shapes exactly.

### fixtures/YYYY-MM-DD.json
```json
{"date": "2026-06-11", "source": "football-data.org", "fetched_at": "<iso>",
 "matches": [{"match_id": "fd-12345", "kickoff_utc": "<iso>", "stage": "GROUP_STAGE",
              "group": "GROUP_A", "home": "Mexico", "away": "South Africa", "venue": "Estadio Azteca"}]}
```
`match_id` is `fd-<football-data id>`; web-research fallback uses `wc-<seq>` slugs but must stay stable across files.

### results/YYYY-MM-DD.json
```json
{"date": "2026-06-11", "source": "football-data.org", "fetched_at": "<iso>",
 "matches": [{"match_id": "fd-12345", "home": "Mexico", "away": "South Africa",
              "home_goals": 2, "away_goals": 1, "status": "FINISHED"}]}
```
`status`: `FINISHED` | `POSTPONED` | `CANCELLED`. Goals are full-time (after extra time in knockouts; note shootout in `notes` if any — h2h market in knockout stage settles on the result after ET, draw possible only in group stage).

### odds/YYYY-MM-DD.json
```json
{"date": "2026-06-11", "collected_at": "<iso>",
 "matches": [{"match_id": "fd-12345",
   "h2h": {"home": 2.10, "draw": 3.30, "away": 3.60},
   "totals": {"line": 2.5, "over": 1.95, "under": 1.85},
   "btts": {"yes": 2.05, "no": 1.75},
   "sources": ["https://..."]}]}
```
Decimal odds. Omit any market not found; never guess.

### tickets/YYYY-MM-DD/<match_id>.json (analysis ticket)
```json
{"match_id": "fd-12345", "date": "2026-06-11", "home": "Mexico", "away": "South Africa",
 "kickoff_utc": "<iso>", "stage": "GROUP_STAGE", "group": "GROUP_A", "venue": "...",
 "analysis": {"summary": "2-4 sentences", "home_form": "...", "away_form": "...",
              "h2h": "...", "injuries_news": ["..."], "key_factors": ["..."]},
 "prediction": {"probs": {"home": 0.45, "draw": 0.28, "away": 0.27},
                "predicted_score": "2-1", "confidence": 0.65},
 "value_notes": "where model probs diverge from market implied probs",
 "sources": ["https://..."], "generated_at": "<iso>"}
```
`probs` must sum to 1.0 (±0.01). `confidence` ∈ [0,1].

### betslips/YYYY-MM-DD.json
```json
{"date": "2026-06-11",
 "slips": [{"slip_id": "2026-06-11-S1", "type": "single", "stake": 10.0,
   "legs": [{"match_id": "fd-12345", "market": "h2h", "selection": "home",
             "line": null, "odds": 2.10, "model_prob": 0.52, "edge": 0.094,
             "rationale": "one sentence"}],
   "combined_odds": 2.10, "status": "pending", "payout": null, "settled_at": null,
   "rationale": "one sentence for the slip"}]}
```
- `market`: `h2h` (selection `home|draw|away`), `totals` (selection `over|under`, `line` required), `btts` (selection `yes|no`).
- `type`: `single` (1 leg) or `accumulator` (2–5 legs). Slip ids: `<date>-S<n>` singles, `<date>-ACC` accumulator.
- `combined_odds` = product of leg odds. `status`: `pending|won|lost|void` — only `scripts/settle.py` changes it.

### Staking policy (ticket-builder)
- Bankroll starts at 1000 units. Recommend only legs with positive edge: `model_prob − 1/odds ≥ 0.05`.
- Single stakes: 5 units (edge 0.05–0.08), 10 (0.08–0.15), 15 (0.15–0.25), 20 (>0.25). Accumulator: flat 5 units, max one per day, 2–4 legs.
- Max total daily stake: 60 units. Zero qualifying edges → write the file with `"slips": []`; never force a bet.

### ledger.json
Rebuilt from scratch by `settle.py` from all betslip files (idempotent). Shape:
```json
{"starting_bankroll": 1000.0, "bankroll": 987.5, "updated_at": "<iso>",
 "stats": {"total_staked": 0, "total_returned": 0, "profit": 0, "roi": 0,
           "slips_won": 0, "slips_lost": 0, "slips_void": 0, "slips_pending": 0,
           "hit_rate": 0, "by_market": {"h2h": {"staked": 0, "returned": 0, "won": 0, "lost": 0}}},
 "history": [{"date": "2026-06-11", "bankroll": 990.0}]}
```

## Settlement rules (settle.py is the only authority)

- h2h: group stage = 90-min result; knockout = result after extra time (draw impossible).
- totals: total goals vs `line` (over wins if total > line, under if total < line; exactly on a .0 line = void push).
- btts: both teams scored ≥1.
- `POSTPONED`/`CANCELLED` match → leg void. Void single → stake returned. Void leg in accumulator → that leg's odds become 1.0. Any lost leg → slip lost, payout 0. All legs won/void → payout = stake × adjusted combined odds.
- Bankroll = starting − total settled stakes + total payouts. Pending stakes are deducted (committed) the day placed.

## Conventions

- Python 3.14, stdlib only (urllib, json, argparse) — no pip dependencies; tests use pytest.
- Scripts are idempotent and safe to re-run; exit 0 success, 1 error, 2 missing-token.
- Run tests: `python3 -m pytest tests/ -q`.
- Dashboard is static (repo root `index.html` + `assets/`), served by GitHub Pages, reads `data/*.json` via relative fetch using `data/index.json` as the directory of available dates.
