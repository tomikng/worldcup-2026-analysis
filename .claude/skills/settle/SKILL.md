---
name: settle
description: Fetch results and settle pending betting slips - updates slip statuses and rebuilds the ledger. Use when the user says /settle. Optional argument - a date YYYY-MM-DD to fetch results for (defaults to yesterday UTC).
---

# Settle

DATE = the argument date, or yesterday's UTC date.

1. `python3 scripts/fetch_results.py DATE`
   - Exit 2 (no token): web-research fallback — find final scores for DATE's World Cup matches (fifa.com, bbc.com/sport) and write `data/results/DATE.json` per the schema in CLAUDE.md, using the same `match_id`s as `data/fixtures/DATE.json`.
2. `python3 scripts/settle.py`
3. `python3 scripts/build_index.py`
4. `git add data/ && git commit -m "settle: DATE" && git push`
5. Report: each settled slip (picks, won/lost/void, payout), updated bankroll, ROI, and hit rate from `data/ledger.json`. Note how the analysts' predicted outcomes compared with the actual results in `data/tickets/DATE/`.
