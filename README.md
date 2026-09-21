# FPL Predictor

Generate FPL squad, lineup, captain, transfer, and chip suggestions from
historical performance and current public FPL data. GitHub Actions monitors
deadlines and emails new or changed advice. Apply all changes manually in FPL.

## Install and run

Use Python 3.12, matching GitHub Actions:

```sh
git clone https://github.com/jssmomo0630/FPLPredictor.git
cd FPLPredictor
python -m pip install -r requirements.txt
python run_fpl_pipeline.py --refresh
```

This optimizes a squad from scratch. For adjustments to your existing squad,
replace the entry ID below and run:

```sh
python check_fpl_status.py --entry-id 5440748 --timezone America/Los_Angeles
python run_fpl_pipeline.py --refresh --experimental-transfers --current-squad artifacts/fpl_status.json
python build_fpl_advice.py
python summarize_fpl_advice.py
python send_fpl_email.py --advice artifacts/fpl_advice.json --summary artifacts/fpl_summary.json --preview-dir artifacts/advice_email_preview
```

The final command renders a preview. Add `--send` to deliver it with the SMTP
environment variables below. Local and Actions installations share dependencies.

## Data and models

A fresh checkout requires no `data/` directory. The pipeline downloads missing
historical `players_raw.csv` and `merged_gw.csv` inputs from a pinned revision
of [vaastav's dataset](https://github.com/vaastav/Fantasy-Premier-League) into
`data/<season>/vaastav/`, then normalizes them locally.

`--refresh` downloads current data from the official FPL API. Training uses
finalized gameweeks, identified by the official `data_checked` flag.
`fpl_pipeline_config.py` defines the current season (2026-27), historical seasons
(2020-21 through 2025-26), and pinned revision. Review it at season rollover.
`--refresh-history` replaces cached historical inputs; `--vaastav-ref <sha>`
overrides their source.

Before finalized current-season data exists, the pipeline uses a historical GW1
prior. Subsequently it blends that prior with a fixture-aware in-season Ridge
forecast. Ability and opportunity are treated separately: recent appearances,
starts, and 60-minute probabilities update playing opportunity, while a club
change reduces reliance on the previous role.

OR-Tools selects a legal 15-player squad, XI, ordered bench, captain, and
vice-captain under budget and club constraints. Bench-use probabilities derive
from starter nonappearance risk when available. Fixed probabilities remain a
fallback or explicit override; outputs record the assumptions.

## Transfer and chip advice

Automation uses a rolling five-gameweek horizon, shortened at the active chip
set's expiry. It models free-transfer rollover, four-point hits, bank, legal
squads and lineups, and chip opportunities. The main transfer solver has a
120-second limit. `FEASIBLE` means valid but not proven optimal.

A configurable 0.15-point preference discourages starting a MID/FWD against an
opposing starting GK/DEF without excluding that combination. Fixture difficulty
is already represented in forecasts. Longer chip horizons are available through
`plan_transfers.py --chip-horizon` for manual analysis.

The flag remains `--experimental-transfers` because validation is limited.
Five three-gameweek historical replay windows produced 605 realized points
versus 608 for the one-week baseline; this does not establish that the current
planner improves real scores. Actions explicitly enables advisory runs.
Plans are recalculated with fresh fixtures and availability. Predicted price
changes are not modeled.

Advice emails show per-gameweek projected points for the plan versus retaining
the original 15 and reoptimizing lineups/captains, with gross gains, hit costs,
and net gains. The undiscounted horizon total includes all future planned
transfers, not just the immediate moves. These estimates include approximate
bench/vice fallback value but exclude chips and non-point selection preferences.
The keep-squad comparison has a separate five-second solver limit and reports
its status; if it cannot produce a solution, the email marks the comparison
unavailable. Scheduled emails also state which notification condition changed.

### Public squad limitations

No FPL login or authentication token is required. Public picks describe the
latest published post-deadline squad; private transfers since then may be missing.
The published bank is used, and free transfers are inferred from public transfer
and chip history. Selling prices fall back to current prices unless the input
supplies true selling prices. Advice records these limitations.
Use `--free-transfers` and `--bank` for explicit overrides when necessary.

`fetch_entry_squad.py` remains an optional manual snapshot tool. Automation uses
`check_fpl_status.py`.

## GitHub Actions and email

The workflow `.github/workflows/fpl-status-poc.yml` appears as **FPL advisory
monitor**. Scheduled runs use the default branch, `master`.

- A lightweight check runs hourly at minute 17.
- The first recommendation runs when a check enters the 48-hour deadline window.
  Scheduling delays mean delivery is not guaranteed exactly 48 hours before.
- Within that window, forecasting reruns every six hours. An owned player's
  availability change can trigger an earlier run.
- Email is sent for the first recommendation, changed owned-player availability,
  or changed transfers, XI, captaincy, bench, or chip advice.

Unchanged recommendations are suppressed using GitHub Actions cache. Missing
or evicted state can cause the next eligible run to email the recommendation
again. This is best-effort deduplication, not a permanent delivery ledger.

Configure **Settings → Secrets and variables → Actions**:

| Setting | Type | Purpose |
| --- | --- | --- |
| `SMTP_USERNAME` | Secret | Gmail sender address |
| `SMTP_APP_PASSWORD` | Secret | Sender's Google app password |
| `EMAIL_TO` | Secret | Recipient address |
| `GEMINI_API_KEY` | Optional secret | Gemini commentary |
| `FPL_ENTRY_ID` | Optional variable | Entry ID; defaults to `5440748` |

Gmail delivery requires an account eligible for app passwords. Keep credentials
in secrets, not repository files. The workflow timezone is
`America/Los_Angeles`; local checks accept `--timezone` or `FPL_TIMEZONE`.

For a manual test, open **Actions → FPL advisory monitor → Run workflow**, select
`master`, and enable `run_advice`. Leave `send_email` and `use_gemini` disabled
to produce previews without delivery or an AI call. `free_transfers` defaults
to `auto`. Push runs perform lightweight tests and status generation.

### Optional AI commentary

`summarize_fpl_advice.py` sends structured recommendation facts to Gemini for a
brief summary; it does not choose transfers. Without a key, or on a handled API
failure, the deterministic summary is used. Scheduled runs request Gemini only
when email is due; manual runs require `use_gemini`.

The configured default is `gemini-3.5-flash-lite`. Local runs can override it
with `GEMINI_MODEL` or `--model`. Live API verification remains pending key setup.
Gemini is the only implemented AI provider.

## Outputs and source layout

| Output | Purpose |
| --- | --- |
| `artifacts/fpl_status.json` | Deadline, public squad, availability, financial assumptions |
| `data/gw1_<season>_predictions.csv` | Preseason prior |
| `data/blended_next_gw_predictions.csv` | In-season forecasts |
| `data/optimal_squad.csv` and `.json` | Optimized squad from scratch |
| `data/transfer_plan.csv` and `.json` | Adjustments to the supplied squad |
| `artifacts/fpl_advice.json` | Structured advice |
| `artifacts/fpl_summary.json` | Commentary and provider/fallback metadata |
| `artifacts/advice_email_preview/` | Email preview |
| `.fpl-monitor/state.json` | Scheduled-run state |

Actions uploads report and preview files as `fpl-status-report`, retained for
seven days. Local data, reports, and squad snapshots are ignored by Git and
are not required in a fresh checkout.

Active source includes downloaders, normalizers, feature builders, training and
blending, optimization, and status/monitor/email scripts. `run_fpl_pipeline.py`
orchestrates forecasts; the workflow orchestrates monitoring and delivery.

Keep the `evaluate_*.py` scripts: they support validation, the live model imports
feature definitions from `evaluate_fixture_baseline.py`, and the pipeline runs
`evaluate_squad_optimizer.py`. [The roadmap](FPL_IMPROVEMENT_ROADMAP.md) records
milestones and historical experiments. Superseded model, desktop, and one-off
analysis tools remain available in Git history.

## Independent weekly recommendations

Generate a one-gameweek £100m squad, XI, captain/vice, ranked players by position,
and points-per-£m value picks without an entry ID or existing squad:

```sh
python weekly_recommendations.py generate
```

This refreshes official data, selects the next future deadline (even during an
ongoing gameweek), and runs the existing forecast/optimizer pipeline. Each run
saves an immutable timestamped directory under
`artifacts/weekly/<season>/gwNN/` with `recommendation.json` and a Markdown report.
JSON includes every candidate's forecast, selected lineup, input hash, budget,
solver status, and assumptions for future dashboard use. Multiple pre-deadline
versions are preserved; choose the last pre-deadline snapshot for the primary
weekly review. Generation refuses to publish after the target deadline.

After the event is finalized, refresh results and review that same snapshot:

```sh
python download_current_season.py --season 2026-27
python weekly_recommendations.py review --snapshot artifacts/weekly/2026-27/gw06/TIMESTAMP/recommendation.json
```

Replace `TIMESTAMP` with the saved directory name. Reviews require the official
`data_checked` flag, reject missing player outcomes, and preserve the original
forecast. They report player errors/minutes, overall MAE, top-ten realized
points, and a fixed starting-XI score with double captain points. That benchmark
deliberately excludes autosubs/vice fallback and chips, and is labelled separately
from official FPL team scoring. No post-deadline recommendation can be treated
as a genuine pre-deadline forecast. JSON reviews are timestamped alongside picks.

The personal-advice workflow remains separate and manager-specific. The
`Weekly FPL dashboard` workflow archives these public, manager-independent
snapshots on the `weekly-dashboard-data` branch and publishes a GitHub Pages
site. It checks every six hours, but only runs the expensive forecast pipeline
during the 48 hours before the next deadline. When FPL finalizes a gameweek, it
adds a review to each previously frozen forecast.

Build the dependency-free dashboard locally with:

```sh
python build_weekly_dashboard.py --snapshot-root artifacts/weekly
```

The output is written to `artifacts/weekly-dashboard/`. Serve that directory
with any local HTTP server for previewing because the page loads its data with
`fetch`. The published data contains forecasts and public FPL results only; it
does not contain email credentials, API keys, or manager-specific squad data.

## Tests

```sh
python -m unittest discover -p "test_*.py"
```

Tests cover bootstrap, target selection, minutes risk, blending, transfer/chip
constraints, status, deduplication, commentary, and email rendering. They do not
establish future FPL performance or verify live SMTP/Gemini credentials.
