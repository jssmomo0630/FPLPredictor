# Fantasy Premier League (FPL) Prediction Model

A comprehensive linear regression prediction model for Fantasy Premier League using historical performance data and advanced statistics.

## Quick Start (Updated Scripts)

- Historical data (vaastav):
  - `python download_history_data.py --seasons 2020-21 2021-22 2022-23 2023-24 2024-25`
  - Optional: `--per-gw` to fetch gw1.csv..gw38.csv; `--clean` to remove existing folders first
- Current season (FPL API):
  - `python download_current_season.py` (defaults to 2025-26)
  - Optional: `--season 2025-26 --max-gw 10`
- Run model and get squad: `python use_fpl_model.py`

Outputs:
- Current season merged file: `data/<season>/merged_gw_enhanced.csv`
- Squad JSON: `squads/squad_<timestamp>.json`

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
python download_current_season.py            # defaults to season 2025-26
# Or specify season / GW cap
python download_current_season.py --season 2025-26 --max-gw 10
```

### Step 2: Run Prediction Model
```bash
python use_fpl_model.py
```

This will:
- Load historical data and the latest current-season data
- Train position-specific models
- Generate predictions and select an optimal squad
- Save the squad JSON under `squads/`

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

## 🔍 Model Limitations

1. **Data Availability**: Limited to available FPL data
2. **Dynamic Nature**: Football is unpredictable
3. **Injuries/Suspensions**: Not always captured in data
4. **Manager Decisions**: Team selection changes
5. **Fixture Difficulty**: Not directly modeled

## 📈 Future Improvements

1. **Advanced Features**:
   - Fixture difficulty ratings
   - Head-to-head statistics
   - Weather conditions
   - Injury/suspension data

2. **Model Enhancements**:
   - Time series analysis
   - Ensemble methods
   - Deep learning models
   - Real-time updates

3. **Additional Data Sources**:
   - Understat integration
   - FBRef data
   - Social media sentiment
   - News analysis

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
