---
name: settle
description: Fetch results and settle pending betting slips - updates slip statuses and rebuilds the ledger. Use when the user says /settle. Optional argument - a date YYYY-MM-DD to fetch results for (defaults to yesterday UTC).
---

# Settle

DATE = the argument date, or yesterday's UTC date.

1. `python3 scripts/fetch_results.py DATE`
   - Exit 2 (no token): web-research fallback — find final scores for DATE's World Cup matches (fifa.com, bbc.com/sport) and write `data/results/DATE.json` per the schema in CLAUDE.md, using the same `match_id`s as `data/fixtures/DATE.json`.
2. **Stats enrichment** (only needed if any pending leg on DATE uses cards/red_card/corners): for each match in `data/results/DATE.json`, web-research the official match report (FIFA, BBC, ESPN) and fill `home_cards, away_cards, home_reds, away_reds, home_corners, away_corners` + `stats_sources`. Leave a field `null` if you cannot verify it from a real source — settle.py voids dependent legs, which is the correct outcome. Never guess.
3. **Futures resolution** (only when a futures market has officially resolved — group winners after June 27, knockout/to-reach markets as they decide, winner July 19): verify the official outcome (FIFA), then set each affected position's `status` to `won`/`lost` and `resolved_at` in `data/futures.json`.
4. `python3 scripts/settle.py`
5. `python3 scripts/build_index.py`
6. `git add data/ && git commit -m "settle: DATE" && git push`
7. Report: each settled slip (picks, won/lost/void, payout), futures changes, updated bankroll, ROI, and hit rate from `data/ledger.json`. Note how the analysts' predicted outcomes compared with the actual results in `data/tickets/DATE/`.
