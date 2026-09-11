# FPL Improvement Roadmap

This document retains historical validation results from development snapshots.
Player counts, scores, and trial configurations below are not current live
results. See [README.md](README.md) for the supported workflow and setup.

## Goal

Produce opening-squad, weekly lineup, captain, and transfer recommendations
whose estimates use only information available before the relevant deadline.

## Principles

- The player identifier is FPL `element`; names are display data only.
- The model predicts future points, never the score of the same completed match.
- Training, validation, and backtests are chronological.
- Historic rulesets remain explicit. BPS and defensive-contribution data are not
  silently assumed comparable between seasons.
- A recommendation must beat a simple, documented baseline before it replaces it.

## Milestones

### 0. Data contract — complete for player-gameweek and 2026/27 fixtures

**Deliverables**

- `normalize_gameweeks.py`: canonical player-gameweek table from vaastav and
  official FPL sources.
- `data/canonical_fixtures.csv`: one row per team per fixture from the official API.

**Acceptance criteria**

- No duplicate `(season, element, gameweek)` rows.
- Player, position, and team are represented by stable FPL IDs.
- Double gameweeks retain `fixture_count`.
- Source/ruleset/field-availability metadata is retained.

### 1. Leakage-safe forecast dataset — complete

**Deliverables**

- A builder which derives only lagged player features and future-point targets
  for 1-, 3-, and 5-GW horizons.
- A feature allow-list that excludes same-GW outcomes.

**Acceptance criteria**

- The row targeting GW *t* contains no values from GW *t* or later.
- Final incomplete horizons are null, not zero.
- Dataset construction is deterministic and validates chronological ordering.

**Implemented**

- `build_forecast_dataset.py` produced `data/forecast_dataset.csv` from all
  available historical/current data. A direct spot check confirms its GW10
  three-GW points feature equals the mean from GWs 7–9 only.

### 2. Baselines and walk-forward evaluation — complete

**Deliverables**

- Baselines: last-five points per appearance and a fixture-adjusted version.
- Season-by-season walk-forward evaluation and a machine-readable report.

**Acceptance criteria**

- Train only on seasons/GWs earlier than the evaluation row.
- Report MAE, calibration, rank correlation, top-player hit rate, squad points,
  and captain regret.
- Any model used for recommendations beats the baseline on held-out seasons.

**Current baseline**

- Complete 2025/26 vaastav archive downloaded under `data/2025-26/vaastav/`:
  29,757 raw rows, 841 players, and all 38 gameweeks.
- Its GW1–26 overlap has exactly the same 19,807 player-GW keys as the saved
  official API snapshot. Total points agree on 99.97% of rows; the six changed
  rows reflect later finalized corrections in the archive.
- The trailing-five-GW baseline is evaluated across GW2–38 for both 2024/25 and
  2025/26. Results are stored in `data/baseline_evaluation.json` with explicit
  source and evaluation coverage fields.
- `normalize_fixtures.py` creates a validated two-team-per-fixture schedule for
  2020/21–2026/27. `build_fixture_features.py` calculates prior-five-GW team and
  opponent strength, home/away, rest, blank/double-GW, and official FDR fields.
- The season-held-out fixture-aware Ridge benchmark improves MAE by 1.65% and
  6.13%, RMSE by 7.03% and 7.28%, top-10 points capture by about 11.9%, and
  captain regret by 10.54% and 12.50% on 2024/25 and 2025/26 respectively.
- Overall rank correlation falls by 3.05% and 4.51%, and 2025/26 is
  under-calibrated because its defensive-contribution rules were unseen in the
  earlier training seasons. These are explicit targets for the next model, not
  hidden by accepting the aggregate-error improvement.

### 3. Pre-season / GW1 prior — complete

**Deliverables**

- A separate prior based on prior-season per-90 rates, expected stats, team
  strength, player role, price, transfers, and projected minutes.
- A documented blend from prior to in-season forecast after enough starts.

**Acceptance criteria**

- Works with zero current-season gameweeks.
- New signings and promoted-team players are explicitly flagged rather than
  assigned fabricated current-season form.

**Implemented**

- `build_gw1_dataset.py` creates 3,091 historical GW1 training rows across five
  target seasons using stable player `code`, prior-season player rates, team
  strength, price, position, and the first five fixtures.
- For 2026/27, 568 selectable players are scored; 445 have matched prior-player
  history, 91 are on promoted teams, and nine position changes are recorded.
- `train_gw1_prior.py` evaluates Ridge, histogram gradient boosting, and random
  forest chronologically on 2023/24–2025/26. Ridge supplies calibrated expected
  points; a 75% prior-strength / 25% Ridge context score is used for selection
  because it preserves held-out top-player capture more reliably.
- Availability adjusts expected points and projected minutes. Current penalty
  and set-piece order are retained in the prediction output but are not treated
  as trained features because equivalent historical preseason snapshots do not
  exist.
- `blend_forecasts.py` moves from the prior to the in-season model using
  `current_minutes / (current_minutes + 450)`, capped at 85% in-season weight.
  Missing in-season predictions retain the prior rather than becoming zero.

### 4. Fixture, availability, and rule-aware forecast model — complete

**Deliverables**

- Fixture-horizon, home/away, rest, blank/double-GW, injury, suspension, and
  start-probability features.
- Versioned scoring/ruleset handling for defensive contribution and BPS changes.

**Acceptance criteria**

- Provisional FPL data is never used in finalized training/backtest targets.
- Fixture data joins without duplicating player-GW outcomes.

**Implemented**

- `download_current_season.py` uses the official event `data_checked` flag as
  the finalized-data gate. Finished-but-unchecked gameweeks can be downloaded
  explicitly for inspection, but are excluded from the merged training input.
- `normalize_gameweeks.py` retains a `ruleset` and defensive-contribution
  availability flag. The 2025/26 defensive-contribution regime and 2026/27 BPS
  regime are distinct from earlier seasons rather than silently pooled.
- `build_fixture_features.py` generates features for future scheduled rounds,
  including home/away, rest, fixture count, blank/double-GW state, FDR, and
  lagged team/opponent strength without duplicating player-gameweek outcomes.
- `build_inseason_candidates.py` constructs the next-GW player rows from
  finalized history and applies current API availability and recent start-rate
  information. `train_inseason_model.py` trains chronologically and outputs
  both calibrated expected points and a ranking-oriented selection score.
- A 2025/26 as-of-GW9 simulation for GW10 improved the trailing-five baseline
  from MAE 1.3951 to 1.3134, RMSE 2.3401 to 2.1743, and Spearman rank
  correlation 0.6856 to 0.7304. The blended selection score improved top-10
  points capture from 43.8% to 52.9%.
- `run_fpl_pipeline.py` is now the unified entry point. It automatically emits
  the GW1 prior when no finalized current-season gameweeks exist, then switches
  to and blends the in-season forecast once finalized data becomes available.
- The 2026/27 BPS ruleset is explicitly marked, but no historical effect is
  fitted until finalized 2026/27 observations exist.

### 5. Squad and captain optimiser — complete

**Deliverables**

- OR-Tools integer optimisation for the 15-player squad, starting XI, bench,
  captain, and vice-captain.

**Acceptance criteria**

- Enforces budget, positions, legal formations, and three-player club limit.
- Objective uses expected starting-XI and captain points; bench value comes only
  from a stated availability/substitution assumption.

**Implemented**

- `optimize_squad.py` uses OR-Tools CP-SAT to jointly select the 15-player
  squad, legal starting XI, three ordered outfield substitutes, reserve
  goalkeeper, captain, and vice-captain.
- It enforces the £100.0m budget, 2/5/5/3 squad position quotas, one starting
  goalkeeper, minimum 3/2/1 DEF/MID/FWD, 11 starters, and no more than three
  players from one club.
- Starting-XI and captain value use availability-adjusted expected points.
  Bench-use probabilities now derive from selected starters' nonappearance
  risks when available, with fixed probabilities retained as a fallback or
  explicit override. Assumptions and the prediction-input SHA-256 are saved
  with the result. The numerical GW1 experiment below predates this update.
- On the 2026/27 GW1 prediction snapshot, CP-SAT proved the £100.0m, 5-3-2
  solution optimal with objective 59.6675. The same-input deterministic greedy
  upgrade benchmark scored 52.8898, so the exact optimiser improved the stated
  objective by 6.7777 points (12.81%).
- `run_fpl_pipeline.py` now generates `data/optimal_squad.csv`,
  `data/optimal_squad.json`, and `data/squad_optimizer_evaluation.json` after
  either the preseason or in-season forecast branch.

### 6. Multi-week transfers and operations — core implemented, recommendations gated

**Deliverables**

- Multi-week transfer planner including free transfers, hits, chips, price risk,
  and fixture horizon.
- Data-quality checks and a repeatable refresh command.

**Acceptance criteria**

- Supports the 2026/27 two chip sets and up to five rolled free transfers.
- Produces a reproducible recommendation with input snapshot timestamps.

**Implemented / validation status**

- `build_transfer_forecasts.py` expands the current forecast over a configurable
  fixture horizon using relative fixture count, FDR, and home/away effects. This
  is transparent but remains a heuristic until direct per-GW horizon models are
  validated.
- `plan_transfers.py` jointly optimises transfers, bank, legal squads, lineups,
  benches, captains, vice-captains, four-point hits, and free-transfer rolls up
  to the current five-transfer cap. It accepts the actual available transfer
  count and records whether true selling prices or current-price fallbacks were
  used.
- `test_transfer_planner.py` confirms the free-transfer state progresses 2 → 3
  → 4 → 5 → 5 when no moves are made. A live GW2–5 trial with two free
  transfers produced a legal no-hit plan within the configured solve limit.
- `evaluate_transfer_planner.py` chronologically replayed five independent
  three-GW windows from completed 2025/26 data. Replacing heuristic horizon
  scaling with a separately fitted chronological Ridge forecast for each target
  improved the result to 605 realized points versus 608 for a repeatedly
  replanned one-week baseline.
- The CLI retains `--experimental-transfers` because validation remains limited.
  GitHub Actions explicitly enables it for advisory runs. Automation now uses
  public squad status, inferred free transfers, a rolling five-GW horizon,
  guarded chip recommendations, and a 120-second main solver limit.
- Chip recommendations respect half-season sets and expiry; actual activation
  remains manual. Price-change forecasts are not implemented.
- Deadline monitoring, email previews/delivery, optional Gemini commentary,
  and cached recommendation deduplication are implemented. Live Gemini API
  verification remains pending key setup.

## Current execution order

1. Improve multi-GW calibration and transfer-value uncertainty beyond the
   current direct chronological Ridge forecasts.
2. Expand replay coverage to assess the current advisory against the one-week
   baseline on untouched validation windows.
3. Evaluate the existing chip recommendations and consider price-change
   forecasts only when the underlying forecast quality supports them.
