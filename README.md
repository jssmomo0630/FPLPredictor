# Fantasy Premier League (FPL) Prediction Model

A comprehensive linear regression prediction model for Fantasy Premier League using historical performance data and advanced statistics.

## Quick Start (Updated Scripts)

- Historical data (vaastav):
  - `python download_history_data.py --seasons 2020-21 2021-22 2022-23 2023-24 2024-25`
  - Optional: `--per-gw` to fetch gw1.csv..gw38.csv; `--clean` to remove existing folders first
- Current season (FPL API):
  - `python download_current_season.py` (defaults to 2026-27)
  - Optional: `--season 2026-27 --max-gw 10`
- Run the current forecast pipeline: `python run_fpl_pipeline.py --refresh`
- A fresh checkout does not require a committed `data/` directory. The pipeline
  automatically downloads missing compact historical inputs from a pinned
  vaastav revision into `data/<season>/vaastav/`, then refreshes the current
  season from the official FPL API.
- Use `--refresh-history` only when intentionally replacing every cached
  historical input. Override the immutable source with `--vaastav-ref <sha>`.
- Before GW1 it produces `data/gw1_2026-27_predictions.csv`; after finalized
  gameweek data exists it produces `data/blended_next_gw_predictions.csv`.
- It then writes the exact 15-player squad and lineup to
  `data/optimal_squad.csv` and `data/optimal_squad.json`.
- The legacy `use_fpl_model.py` remains for comparison but is no longer the
  recommended entry point.

### Read-only deadline and availability check

Use the public FPL endpoints to inspect the next deadline and the latest
published 15-player squad:

```bash
python check_fpl_status.py --entry-id 1234567 --timezone America/Los_Angeles
```

Alternatively, set `FPL_ENTRY_ID` and optionally `FPL_TIMEZONE`. The command
writes `artifacts/fpl_status.json` and returns one of these advisory decisions:

- `run_recommendation` inside the 24-hour and 6-hour deadline windows
- `send_status_update` when a squad player is flagged outside those windows
- `no_action` during normal monitoring
- `season_complete` when no future gameweek remains

This monitor is intentionally read-only. It does not authenticate with FPL and
does not submit transfers, activate chips, change the captain, or alter the
lineup. The public picks endpoint exposes the squad only after a gameweek's
deadline, so pending private changes, current bank, exact selling prices, and
the live free-transfer balance must come from a separate authenticated input
before a recommendation can account for them. Later automation stages will
email suggestions for the manager to review and apply manually.

### Advisory pipeline and email

The public status JSON can drive a multi-gameweek transfer and lineup advisory:

```bash
python run_fpl_pipeline.py --refresh --experimental-transfers \
  --current-squad artifacts/fpl_status.json --free-transfers 1
python build_fpl_advice.py
python summarize_fpl_advice.py
python send_fpl_email.py --advice artifacts/fpl_advice.json \
  --summary artifacts/fpl_summary.json --preview-dir artifacts/advice_email_preview
```

The upcoming deadline gameweek is inferred from the status JSON, rather than
assuming that the next target is immediately after the latest finalized week.
The locked public bank is used automatically. Because the public API does not
expose the live free-transfer count or true selling prices, both assumptions
are recorded prominently in the output and email.

`summarize_fpl_advice.py` always writes a deterministic fallback. If
`GEMINI_API_KEY` is present it asks `gemini-3.5-flash-lite` to turn only the
structured recommendation facts into concise commentary; an API failure never
blocks the deterministic email. SMTP delivery occurs only with an explicit
`--send` flag and the `SMTP_USERNAME`, `SMTP_APP_PASSWORD`, and `EMAIL_TO`
secrets. All recommendations remain advisory and must be applied manually.

Outputs:
- Current season merged file: `data/<season>/merged_gw_enhanced.csv`
- Squad JSON: `squads/squad_<timestamp>.json`

All canonical tables, feature tables, predictions, evaluations, official API
snapshots, and optimized squads are reproducible pipeline outputs. They may be
kept locally for debugging or cached in CI, but they are not required in a
fresh source checkout.

## 🎯 Overview

This project provides a data-driven approach to FPL player selection by:
- Collecting data from trusted FPL sources
- Creating comprehensive player features
- Training multiple regression models
- Predicting player performance for the current season

## 📊 FPL Scoring Rules Summary

### **Attacking Points**
- **Goal scored**: +4 points (midfielders/forwards), +6 points (defenders), +5 points (goalkeepers)
- **Assist**: +3 points
- **Clean sheet**: +1 point (midfielders), +4 points (defenders), +4 points (goalkeepers)
- **Clean sheet bonus**: +3 points (defenders/goalkeepers), +1 point (midfielders)

### **Defensive Points**
- **Clean sheet**: +4 points (defenders/goalkeepers), +1 point (midfielders)
- **Goals conceded**: -1 point per 2 goals conceded (defenders/goalkeepers)
- **Saves**: +1 point per 3 saves (goalkeepers only)

### **Other Points**
- **Appearance**: +2 points for playing 60+ minutes, +1 point for playing less than 60 minutes
- **Yellow card**: -1 point
- **Red card**: -3 points
- **Own goal**: -2 points
- **Penalty miss**: -2 points

### **Bonus Points System**
- 3 points for the best performing player in the match
- 2 points for the second best
- 1 point for the third best
- Based on BPS (Bonus Points System) which considers goals, assists, clean sheets, passes completed, crosses, tackles, recovery of possession, saves

## 🔧 Installation

1. **Clone the repository**:
```bash
git clone <repository-url>
cd fpl-prediction
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

## 📈 Data Sources

### **Primary Sources**
1. **Official FPL API**: `https://fantasy.premierleague.com/api/`
   - `/bootstrap-static/` - Complete static data
   - `/element-summary/{element_id}/` - Individual player data
   - `/event/{event_id}/live/` - Live gameweek data

2. **Historical Data**: vaastav's FPL repository
   - GitHub: `https://github.com/vaastav/Fantasy-Premier-League`
   - Provides historical player and gameweek data

### **Alternative Sources**
- **Understat**: Advanced statistics and xG data
- **FBRef**: Comprehensive football statistics
- **WhoScored**: Detailed player performance metrics

## Usage

### Step 1: Collect Data
Option A — Historical data (vaastav):
```bash
python download_history_data.py --seasons 2020-21 2021-22 2022-23 2023-24 2024-25
# Optional: also fetch per‑GW files
python download_history_data.py --per-gw
# Optional: clean existing season folders first
python download_history_data.py --clean
```

Option B — Current season (FPL API):
```bash
python download_current_season.py            # defaults to season 2026-27
# Or specify season / GW cap
python download_current_season.py --season 2026-27 --max-gw 10
```

### Step 2: Run the Current Forecast Pipeline
```bash
python run_fpl_pipeline.py --refresh
```

This will:
- Refresh official player and fixture data
- Rebuild leakage-safe historical features
- Use the GW1 prior before finalized gameweeks exist
- Switch to the fixture- and availability-aware in-season model afterward
- Write the current player forecast under `data/`
- Optimise the 15-player squad, legal starting XI, ordered bench, captain, and
  vice-captain with OR-Tools

The optimiser enforces the £100.0m budget, exact position quotas, legal XI, and
three-player-per-club limit. Its bench objective assumes 15%, 5%, and 2%
autosub-use probabilities for bench positions 1–3, plus 5% for the reserve
goalkeeper and vice-captain fallback. These assumptions are configurable in
`optimize_squad.py` and recorded in `data/optimal_squad.json`.

The old `python use_fpl_model.py` command remains available only for legacy
comparison.

### Experimental Free-Transfer Planner

The multi-gameweek planner accepts the actual available free-transfer count
(1–5), bank, and a current 15-player squad snapshot:

```bash
python run_fpl_pipeline.py --experimental-transfers --current-squad squads/current_squad.json --free-transfers 3 --bank 0.5
```

It models rolling transfers, four-point hits, bank conservation, legal squads,
and future lineups. Starting MID/FWD players facing an opposing starting GK/DEF
receive a small 0.15-point soft penalty; this preference is configurable with
`--opponent-conflict-penalty` and never acts as a hard exclusion because fixture
difficulty is already included in the forecasts. Any remaining overlaps are
listed in the JSON report. Output is written to `data/transfer_plan.csv` and
`data/transfer_plan.json`.

This feature is deliberately experimental: five chronological 2025/26 replay
windows using a direct per-target Ridge forecast scored 605 points for the
multi-week strategy versus 608 for the one-week baseline. It is therefore not
run by default. True selling prices are used when present in the squad input;
otherwise the report clearly records the current-price fallback. Chips and
predicted price changes are not active yet.

## 🚀 Usage

### **Step 1: Collect Data**
```bash
python fpl_data_collector.py
```

This will:
- Download current season data from the official FPL API
- Download historical data from trusted sources
- Create enhanced player features
- Generate a collection report

### **Step 2: Run Prediction Model**
```bash
python fpl_prediction_model.py
```

This will:
- Load and prepare the collected data
- Create comprehensive features for prediction
- Train multiple regression models (Linear, Ridge, Lasso, Random Forest)
- Analyze feature importance
- Generate predictions for current season players
- Create visualizations and reports

## 📋 Features Used in Prediction

### **Basic Player Features**
- Position (Goalkeeper, Defender, Midfielder, Forward)
- Cost and value metrics
- Form and points per game
- Minutes played and starts

### **Performance Features**
- Goals and assists per game
- Clean sheets and goals conceded per game
- Bonus points and BPS
- Cards (yellow/red)

### **Advanced Metrics**
- Influence, Creativity, Threat (ICT) index
- Expected goals and assists (xG, xA)
- Team performance metrics
- Historical performance trends

### **Derived Features**
- Value per point
- Form per cost
- Points per game per cost
- ICT metrics per minute
- Team average performance

## 📊 Model Performance

The system trains multiple models and selects the best performing one:

1. **Linear Regression**: Basic linear relationship
2. **Ridge Regression**: Linear with L2 regularization
3. **Lasso Regression**: Linear with L1 regularization
4. **Random Forest**: Non-linear ensemble method

### **Evaluation Metrics**
- **R² Score**: Coefficient of determination
- **RMSE**: Root Mean Square Error
- **MAE**: Mean Absolute Error
- **Cross-validation**: 5-fold cross-validation

## 📁 Output Files

### **Data Files**
- `data/<season>/players_raw.csv`: Current season player data from bootstrap
- `data/<season>/events.csv`, `teams.csv`, `element_types.csv`: Bootstrap components
- `data/<season>/gws/gwN.csv`: Flattened per‑GW stats (current season)
- `data/<season>/merged_gw_enhanced.csv`: Merged current-season GW stats for modeling
- `data/bootstrap_static.json`: Raw API data (top-level; optional)
- `data/download_summary.json`: Historical download summary (optional)

### **Prediction Files**
- `squads/squad_<timestamp>.json`: Optimal squad + captain/vice

## 🎯 Key Insights

### **Most Important Features** (typically)
1. **Form**: Recent performance trend
2. **Points per game**: Historical performance
3. **Minutes played**: Playing time
4. **Goals/assists per game**: Attacking output
5. **Clean sheets per game**: Defensive performance
6. **Value per point**: Cost efficiency
7. **ICT index**: Advanced performance metrics

### **Position-Specific Insights**
- **Forwards**: Goals and assists are crucial
- **Midfielders**: Goals, assists, and clean sheets
- **Defenders**: Clean sheets and goals conceded
- **Goalkeepers**: Saves and clean sheets

## 🤖 Model Details and Improvements

### Current Model Architecture

The prediction engine is built on a robust, data-driven architecture:

- **Position-Specific Models**: The system trains distinct models for each player position (Goalkeeper, Defender, Midfielder, Forward) to capture the unique performance drivers of each role.
- **Regression Analysis**: It evaluates a suite of regression algorithms—`Linear Regression`, `Ridge`, `Lasso`, and `RandomForestRegressor`—and selects the best-performing model for each position based on validation R² scores.
- **Weighted Historical Data**: Models are trained on several years of historical data, with more recent seasons given higher weights to ensure predictions are relevant to current player performance levels.
- **Rich Feature Set**: A wide array of features are used for training, including:
  - **Performance Stats**: Goals, assists, clean sheets, saves, etc.
  - **Advanced Metrics**: The FPL's Influence, Creativity, Threat (ICT) index.
  - **Derived Stats**: Points per 90 minutes, goals per 90, etc.
  - **Player Form**: A rolling average of points over the last 3 and 5 gameweeks.
- **Fixture Difficulty Adjustment**: Player point predictions are adjusted for the upcoming gameweek based on the official FPL Fixture Difficulty Rating (FDR) of their opponent.
- **Optimal Squad Selection**: The system identifies the best possible 15-player squad by testing multiple valid FPL formations (e.g., 4-4-2, 3-5-2). The final squad is the one with the highest total predicted points, inclusive of a captain bonus. The selection algorithm uses a greedy approach that prioritizes premium players (£8.0m+) and those with high captaincy potential.

### Model Correction: Addressing Data Leakage

During a recent review, a critical data leakage issue was identified and corrected. The model was being trained on features that were direct derivatives of the target variable (`total_points`), leading to inflated and unrealistic predictions.

**The Problem:**
The following features were found to be leaking information from the target variable:
- `bps`: The Bonus Points System (BPS) score is highly correlated with `total_points` and is calculated using many of the same underlying stats.
- `points_per_90`: A direct transformation of `total_points`.
- `avg_points_per_match`: Another direct transformation of `total_points`.
- `influence`, `creativity`, `threat`, `ict_index`: These are composite metrics from the FPL API that are also highly correlated with `total_points`.

Using these features caused the model to learn a simple mapping between them and the target, rather than learning the complex relationships between a player's actions (goals, assists, etc.) and their FPL score. This resulted in abnormally high predictions for some players.

**The Solution:**
To address this, the following changes were made:
1.  **Feature Removal**: The leaky features (`bps`, `points_per_90`, `avg_points_per_match`, `influence`, `creativity`, `threat`, and `ict_index`) were removed from the training data.
2.  **Model Retraining**: The position-specific models were retrained using a cleaned feature set.

This correction has resulted in more realistic and reliable predictions, ensuring that the model's recommendations are based on a sound statistical foundation.

### Recommended Future Improvements

To further enhance prediction accuracy and provide more sophisticated recommendations, the following improvements could be implemented:

1.  **Integrate Advanced Models**:
    - **Gradient Boosting**: Experiment with `XGBoost`, `LightGBM`, or `CatBoost`. These models are often top performers in tabular data competitions and can capture more complex, non-linear relationships between features.
    - **Neural Networks**: A simple feed-forward neural network could uncover even deeper patterns in player data.

2.  **Incorporate Expected Statistics (xG/xA)**:
    - The code is already set up to include Expected Goals (xG) and Expected Assists (xA). Integrating a reliable data feed for these stats (e.g., from Understat or FBRef) would provide a powerful leading indicator of future attacking returns.

3.  **Optimize Squad Selection**:
    - **Knapsack Solver**: The current greedy approach to squad selection is fast but may not be globally optimal. The problem can be framed as a variation of the multiple-choice knapsack problem. Using a dedicated solver (like Google's OR-Tools) could find a provably optimal squad that maximizes points under the budget and formation constraints.

4.  **Enhance Feature Engineering**:
    - **Dynamic Player Form**: Replace fixed 3/5-gameweek rolling averages with an **Exponentially Weighted Moving Average (EWMA)**. This would give more weight to a player's most recent performances, creating a more responsive measure of form.
    - **Look-Ahead Fixture Difficulty**: Instead of just considering the next fixture, create a feature that scores the difficulty of the next 3-5 upcoming matches. This would help identify players with a favorable run of games.

5.  **Automate Player Status**:
    - Integrate a real-time data source for player availability. This would allow the model to automatically discount or exclude players who are injured, suspended, or have a low probability of starting the next match.

6.  **Smarter Transfer Suggestions**:
    - Evolve the transfer suggestion logic to be multi-week aware. Instead of just suggesting a transfer for immediate point gains, the model could simulate outcomes over several future gameweeks to recommend transfers that provide the best long-term value and set the team up for future moves.

## 🤝 Contributing

Contributions are welcome! Please feel free to:
- Add new features
- Improve model performance
- Add new data sources
- Enhance visualizations
- Fix bugs

## 📄 License

This project is licensed under the MIT License.

## ⚠️ Disclaimer

This tool is for educational and entertainment purposes only. FPL performance is inherently unpredictable, and past performance does not guarantee future results. Always do your own research and make informed decisions.

## 📞 Support

For questions or issues, please:
1. Check the documentation
2. Review the code comments
3. Open an issue on GitHub
4. Contact the maintainers

---

**Happy FPL managing!** ⚽🎯 
