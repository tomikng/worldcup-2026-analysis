---
name: daily-run
description: Run the full World Cup daily pipeline - settle yesterday, fetch today's fixtures, research odds, analyze every match in parallel, build betting tickets, update the dashboard index, commit and push. Use when the user says /daily-run or a scheduled routine fires. Optional argument - a date YYYY-MM-DD (defaults to today UTC).
---

# Daily Run

Execute the pipeline below in order. TODAY = the argument date, or today's UTC date. YESTERDAY = the day before TODAY. Read CLAUDE.md for schemas, staking policy, and guardrails before starting.

## 1. Settle yesterday

- `python3 scripts/fetch_results.py YESTERDAY`
  - Exit 2 (no token): fall back to web research — find every final score for YESTERDAY's World Cup matches (fifa.com, bbc.com/sport) and write `data/results/YESTERDAY.json` per schema, matching the `match_id`s used in `data/fixtures/YESTERDAY.json`.
- `python3 scripts/settle.py`
- Skip this step entirely on the first run of the tournament (no betslips exist yet).

## 2. Fetch today's fixtures

- `python3 scripts/fetch_fixtures.py TODAY`
  - Exit 2: web-research fallback — write `data/fixtures/TODAY.json` per schema with stable `wc-<n>` match ids.
- If there are no matches today (rest day), run `python3 scripts/build_index.py`, commit `daily: TODAY (rest day)`, push, and stop.

## 3. Fetch Polymarket prices

- `python3 scripts/fetch_polymarket.py TODAY` (per-match prices)
- `python3 scripts/fetch_polymarket.py --futures` (tournament/group winner snapshot)
- Non-zero exit: continue the pipeline without Polymarket data; note it in the summary.

## 3b. Research odds

Spawn the `odds-researcher` agent: "Collect odds for all fixtures in data/fixtures/TODAY.json and write data/odds/TODAY.json. Cross-check h2h against data/polymarket/TODAY.json".

## 4. Analyze every match (parallel)

Spawn one `match-analyst` agent PER fixture, all in parallel. Give each agent: its fixture object (verbatim JSON), its odds entry from `data/odds/TODAY.json` (or "no odds found"), and the output path `data/tickets/TODAY/<match_id>.json`.

## 5. Build betting tickets

After ALL analysts finish, spawn the `ticket-builder` agent: "Build data/betslips/TODAY.json from the tickets in data/tickets/TODAY/, data/odds/TODAY.json, and data/polymarket/TODAY.json".

## 5b. Futures review

Spawn the `futures-analyst` agent: "Review data/polymarket/futures.json against the team's model and today's standings; open qualifying positions in data/futures.json within the remaining budget".

## 6. Validate, index, publish

- Validate outputs: every fixture has a ticket file; probs sum to 1.0 (±0.01); every betslip leg's odds exist in the odds file (or, for `exchange: "polymarket"` legs, the price+url exist in the polymarket file); stat-market legs (cards/red_card/corners) only where the ticket has a matching `market_probs` entry; total staked ≤ 60; futures stakes within budget. Fix or re-spawn the responsible agent if not.
- `python3 scripts/build_index.py`
- `git add data/ && git commit -m "daily: TODAY" && git push`

## 7. Report

End with a short summary: matches analyzed, picks made (selection @ odds, stake), total staked, current bankroll from `data/ledger.json`, and yesterday's settlement outcome if any.
