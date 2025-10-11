# Fantasy Premier League (FPL) Prediction Model - Design Document

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [FPL Scoring Rules](#fpl-scoring-rules)
3. [Formation Logic & Team Structure](#formation-logic--team-structure)
4. [Captain & Vice-Captain Rules](#captain--vice-captain-rules)
5. [Top 10 Most Important Features](#top-10-most-important-features)
6. [Data Sources & Quality](#data-sources--quality)
7. [Model Architecture](#model-architecture)
8. [Implementation Strategy](#implementation-strategy)

---

## 🎯 Project Overview

### **Objective**
Build a comprehensive linear regression prediction model for Fantasy Premier League using historical performance data and advanced statistics to predict player performance for the current season.

### **Key Goals**
- Predict player performance based on historical data
- Identify undervalued players for team selection
- Optimize team formation and captain choices
- Provide data-driven insights for FPL strategy

---

## 📊 FPL Scoring Rules

### **Attacking Points**
- **Goal scored**: 
  - +4 points (midfielders/forwards)
  - +6 points (defenders)
  - +5 points (goalkeepers)
- **Assist**: +3 points
- **Clean sheet**: 
  - +1 point (midfielders)
  - +4 points (defenders)
  - +4 points (goalkeepers)
- **Clean sheet bonus**: 
  - +3 points (defenders/goalkeepers)
  - +1 point (midfielders)

### **Defensive Points**
- **Clean sheet**: 
  - +4 points (defenders/goalkeepers)
  - +1 point (midfielders)
- **Goals conceded**: -1 point per 2 goals conceded (defenders/goalkeepers)
- **Saves**: +1 point per 3 saves (goalkeepers only)

### **Other Points**
- **Appearance**: 
  - +2 points for playing 60+ minutes
  - +1 point for playing less than 60 minutes
- **Yellow card**: -1 point
- **Red card**: -3 points
- **Own goal**: -2 points
- **Penalty miss**: -2 points

### **Bonus Points System**
- **3 points** for the best performing player in the match
- **2 points** for the second best
- **1 point** for the third best
- Based on BPS (Bonus Points System) which considers:
  - Goals, assists, clean sheets
  - Passes completed, crosses, tackles
  - Recovery of possession, saves

### **Captain/Vice-Captain**
- **Captain points are doubled** - This makes expensive players significantly more valuable
- **Vice-captain points are doubled** if captain doesn't play
- **Strategy Impact**: Premium players (£10m+) become much more valuable due to captain potential
- **Example**: Haaland (£14.9m) scoring 20 points = 40 points as captain, justifying high cost

---

## 🏗️ Formation Logic & Team Structure

### **Team Composition Rules**

#### **Total Squad Size: 15 Players**
- **Starting XI**: 11 players (must be selected each gameweek)
- **Bench**: 4 players (substitutes)
- **Total Budget**: £100.0 million

### **Position Limits**

#### **Starting XI Requirements:**
- **Goalkeepers**: 1 player
- **Defenders**: 3-5 players
- **Midfielders**: 3-5 players  
- **Forwards**: 1-3 players

#### **Squad Requirements:**
- **Total players**: Exactly 15 players (11 starting + 4 bench) - This is mandatory
- **Goalkeepers**: 2 players minimum
- **Defenders**: 5 players minimum
- **Midfielders**: 5 players minimum
- **Forwards**: 3 players minimum
- **Note**: FPL requires exactly 15 players - no more, no less

#### **FPL Scoring Rules:**
- **Starting XI**: Only the 11 players in your starting lineup score points
- **Bench Players**: Only score points if they replace a non-playing starter (0 minutes)
- **Automatic Substitution**: If a starter doesn't play, highest-scoring bench player automatically replaces them
- **Strategy Implication**: Prioritize budget for starting XI, use cheap players for bench

### **Valid Formations**

| Formation | Defenders | Midfielders | Forwards |
|-----------|-----------|-------------|----------|
| **3-5-2** | 3 | 5 | 2 |
| **3-4-3** | 3 | 4 | 3 |
| **4-5-1** | 4 | 5 | 1 |
| **4-4-2** | 4 | 4 | 2 |
| **4-3-3** | 4 | 3 | 3 |
| **5-4-1** | 5 | 4 | 1 |
| **5-3-2** | 5 | 3 | 2 |

### **🚨 CRITICAL: FPL Formation Validation Rules**

#### **Starting XI Formation Rules (MUST BE ENFORCED):**
1. **Exactly 1 Goalkeeper** - Only one GK can start
2. **Minimum 3 Defenders** - Must have at least 3 DEF in starting XI
3. **Minimum 2 Midfielders** - Must have at least 2 MID in starting XI  
4. **Minimum 1 Forward** - Must have at least 1 FWD in starting XI
5. **Total 11 Players** - Starting XI must be exactly 11 players
6. **Maximum 3 Players Per Team** - Cannot have more than 3 players from any single team in squad

#### **Formation Validation Logic:**
```python
def validate_formation(starting_xi):
    gk_count = len([p for p in starting_xi if p['element_type'] == 1])
    def_count = len([p for p in starting_xi if p['element_type'] == 2])
    mid_count = len([p for p in starting_xi if p['element_type'] == 3])
    fwd_count = len([p for p in starting_xi if p['element_type'] == 4])
    
    # Validation rules
    if gk_count != 1:
        return False, f"Must have exactly 1 GK, got {gk_count}"
    if def_count < 3:
        return False, f"Must have at least 3 DEF, got {def_count}"
    if mid_count < 2:
        return False, f"Must have at least 2 MID, got {mid_count}"
    if fwd_count < 1:
        return False, f"Must have at least 1 FWD, got {fwd_count}"
    if len(starting_xi) != 11:
        return False, f"Starting XI must have exactly 11 players, got {len(starting_xi)}"
    
    # Team constraint validation
    team_counts = {}
    for player in starting_xi:
        team = player.get('team', 'Unknown')
        team_counts[team] = team_counts.get(team, 0) + 1
        if team_counts[team] > 3:
            return False, f"Too many players from {team}: {team_counts[team]} (max 3 allowed)"
    
    return True, "Valid formation"
```

#### **Current Issue:**
- **Problem**: Squad generation takes top 11 players by predicted points without formation validation
- **Result**: Invalid formations like 2 GK, 2 DEF, 5 MID, 2 FWD
- **Fix Required**: Implement formation validation in squad generation logic

### **Budget Management**

#### **Player Costs:**
- **Starting prices**: £4.0m - £15.0m
- **Price changes**: Based on transfer activity
- **Budget constraint**: Must stay within £100.0m

#### **Value Strategy:**
- **Premium players**: £10.0m+ (captain material) - Highest priority due to captain bonus
- **Mid-priced**: £6.0m-£9.5m (consistent performers) - Core team players
- **Budget options**: £4.0m-£5.5m (bench/rotation) - Fill remaining spots
- **Strategy**: Maximize total points, not points/cost ratio
- **Budget utilization**: Use as much of £100m as possible

### **Transfer Management**

#### **Free Transfer Rules:**
- **Weekly allowance**: 1 free transfer per gameweek
- **Transfer banking**: Can save transfer to next week (max 2 free transfers)
- **Transfer cost**: -4 points for each transfer beyond free allowance
- **Transfer timing**: Must be completed before gameweek deadline

#### **Transfer Strategy Implementation:**
1. **Store available free transfers**: Track current free transfer count
2. **Specify transfer usage**: Allow user to specify number of transfers for current week
3. **Wildcard option**: Enable unlimited transfers when wildcard is active
4. **Transfer optimization**: Recommend optimal transfers based on predicted performance

#### **Transfer Constraints:**
- **Budget compliance**: Transfers must maintain £100.0m budget
- **Formation validity**: Transfers must maintain valid formation
- **Position limits**: Must maintain minimum squad requirements
- **Captain selection**: Can change captain/vice-captain with transfers

---

## 👑 Captain & Vice-Captain Rules

### **Captain Rules**

#### **Basic Captain Selection:**
- **Must choose**: 1 captain from your 15-man squad
- **Point multiplier**: Captain's points are **doubled**
- **Selection timing**: Must be set before gameweek deadline
- **Position**: Can be any position (GK, DEF, MID, FWD)

#### **Captain Points Calculation:**
```
Regular Points: 6 points
Captain Bonus: ×2
Total Captain Points: 12 points
```

### **Vice-Captain Rules**

#### **Basic Vice-Captain Selection:**
- **Must choose**: 1 vice-captain from your 15-man squad
- **Cannot be same player**: Must be different from captain
- **Point multiplier**: Vice-captain points are **doubled** (only if captain doesn't play)
- **Selection timing**: Must be set before gameweek deadline

#### **Vice-Captain Activation:**
- **Primary condition**: Captain doesn't play (0 minutes)
- **Automatic activation**: Vice-captain points doubled instead
- **If captain plays**: Vice-captain gets normal points (no bonus)

### **Triple Captain Chip**

#### **Triple Captain Rules:**
- **Usage**: Can be used once per season
- **Point multiplier**: Captain's points are **tripled** (not doubled)
- **Vice-captain**: Still applies if captain doesn't play
- **Activation**: Must be activated before gameweek deadline

#### **Triple Captain Points Calculation:**
```
Regular Points: 6 points
Triple Captain Bonus: ×3
Total Triple Captain Points: 18 points
```

### **Captain Strategy Examples**

#### **Example 1: Normal Captain**
```
Player: Mohamed Salah
Regular Points: 8 points
Captain Bonus: ×2
Total Points: 16 points
```

#### **Example 2: Captain Doesn't Play**
```
Captain: Erling Haaland (0 minutes)
Vice-Captain: Kevin De Bruyne
Regular Points: 6 points
Vice-Captain Bonus: ×2
Total Points: 12 points
```

#### **Example 3: Triple Captain**
```
Player: Erling Haaland
Regular Points: 10 points
Triple Captain Bonus: ×3
Total Points: 30 points
```

---

## 🎯 FPL Strategy Fundamentals

### **Primary Objective: Maximize Total Points**
- **Goal**: Score the most points possible within £100m budget
- **NOT**: Optimize for points/cost ratio (value)
- **Strategy**: Use expensive players who score more points, as long as budget allows

### **Captain Bonus is Game-Changing**
- **Captain points are doubled** - This justifies expensive premium players
- **Premium players (£10m+) become much more valuable** due to captain potential
- **Example**: Haaland (£14.9m) scoring 20 points = 40 points as captain
- **Strategy**: Always have premium captain options in your team

### **Budget Utilization**
- **Use as much of the £100m budget as possible**
- **Don't leave money on the table**
- **Expensive players with high points > Cheap players with good value**
- **Only use budget players when you can't afford better options**

### **Squad Building Priority**
1. **Premium Captain Options** (£10m+ players with high point potential)
2. **Core Team Players** (£6m-£9m consistent performers)
3. **Budget Fillers** (£4m-£5m for remaining spots)

### **Starting XI vs Bench Strategy**
- **Starting XI**: Allocate 80% of budget for maximum points
- **Bench Players**: Use cheapest viable players (£4.0m-£4.5m) for automatic substitution
- **Bench Priority**: GK (most important), then DEF, then MID/FWD
- **Reasoning**: Bench only scores if starters don't play, so minimize budget waste

---

## 🎯 Top 10 Most Important Features

### **1. Form (Recent Performance Trend)**
**Why Important**: 
- FPL heavily rewards recent performance with bonus points
- Players in good form tend to continue performing well
- Form captures momentum and confidence
- **Scoring Impact**: Form directly correlates with bonus points and consistent returns

### **2. Minutes Played**
**Why Important**:
- Players must play 60+ minutes to get 2 appearance points
- More minutes = more opportunities for goals, assists, clean sheets
- Injured or benched players score 0 points regardless of talent
- **Scoring Impact**: Direct correlation with appearance points and performance opportunities

### **3. Goals Scored**
**Why Important**:
- Goals are the highest-scoring action in FPL
- +4 points for midfielders/forwards, +6 for defenders, +5 for goalkeepers
- Goals often come with bonus points
- **Scoring Impact**: Highest point return per action

### **4. Assists**
**Why Important**:
- +3 points for every assist
- Often accompanies goals (goal involvement)
- Midfielders and forwards rely heavily on assists
- **Scoring Impact**: Second highest point return per action

### **5. Clean Sheets**
**Why Important**:
- +4 points for defenders/goalkeepers, +1 for midfielders
- Defensive players' primary source of points
- Team-based metric (requires defensive unit performance)
- **Scoring Impact**: Essential for defensive players' value

### **6. Expected Goals (xG)**
**Why Important**:
- Predicts future goal-scoring potential
- More reliable than past goals (regression to mean)
- Captures underlying performance quality
- **Scoring Impact**: Forward-looking indicator of goal potential

### **7. ICT Index (Influence, Creativity, Threat)**
**Why Important**:
- Official FPL metric combining three key performance indicators
- Influence: Impact on match events
- Creativity: Chance creation ability
- Threat: Goal-scoring threat
- **Scoring Impact**: Directly correlates with bonus points and overall performance

### **8. Value per Point (Cost Efficiency)**
**Why Important**:
- FPL is about maximizing points within budget constraints
- Cheap players who score well are gold
- Expensive players must justify their cost
- **Scoring Impact**: Determines team selection strategy

### **9. Team Performance**
**Why Important**:
- Clean sheets require team defensive performance
- Goals often come from team attacking patterns
- Team form affects individual player opportunities
- **Scoring Impact**: Contextual factor affecting all other metrics

### **10. Position-Specific Features**
**Why Important**:
- Different positions score points differently
- Goalkeepers: Saves, clean sheets, goals conceded
- Defenders: Clean sheets, goals, assists, goals conceded
- Midfielders: Goals, assists, clean sheets
- Forwards: Goals, assists
- **Scoring Impact**: Position determines scoring opportunities and point values

---

## 📈 Data Sources & Quality

### **Primary Data Sources**

#### **1. Official FPL API**
- **URL**: `https://fantasy.premierleague.com/api/`
- **Endpoints**:
  - `/bootstrap-static/` - Complete static data
  - `/element-summary/{element_id}/` - Individual player data
  - `/event/{event_id}/live/` - Live gameweek data

#### **2. vaastav/Fantasy-Premier-League Repository**
- **GitHub**: `https://github.com/vaastav/Fantasy-Premier-League`
- **Provides**: Historical player and gameweek data
- **Seasons Available**: 2016-17 to 2024-25

### **Data Quality Assessment**

#### **2024-25 Season Data (Current)**
- **Total Players**: 804
- **Expected Stats Available**: 8 columns
- **Data Completeness**: 100% (no missing values)
- **Key Features**:
  - `expected_goals` (correlation with actual goals: r = 0.950)
  - `expected_assists` (correlation with actual assists: r = 0.881)
  - `expected_goal_involvements` (combined metric)

#### **Historical Data (2020-21 to 2023-24)**
- **Total Players**: 3,093 across 4 seasons
- **Gameweek Records**: 106,000+ records
- **Data Consistency**: High across seasons

### **New Features in 2024-25**

#### **🔥 HIGH IMPORTANCE - Expected Stats (8 columns):**
1. **`expected_goals`** - Correlation with actual goals: **r = 0.950**
2. **`expected_assists`** - Correlation with actual assists: **r = 0.881**
3. **`expected_goal_involvements`** - Combined goals + assists
4. **`expected_goals_per_90`** - Per-90 minute expected goals
5. **`expected_assists_per_90`** - Per-90 minute expected assists
6. **`expected_goal_involvements_per_90`** - Per-90 minute combined
7. **`expected_goals_conceded`** - Defensive performance metric
8. **`expected_goals_conceded_per_90`** - Per-90 defensive metric

#### **📝 LOW IMPORTANCE - Administrative (7 columns):**
- `birth_date`, `can_select`, `can_transact`, `has_temporary_code`
- `opta_code`, `region`, `removed`, `team_join_date`

---

## 🏗️ Model Architecture

### **Proposed Model Structure**

#### **1. Position-Specific Models**
- **Separate models** for GK, DEF, MID, FWD
- **Different scoring patterns** require different features
- **Position-specific feature engineering**

#### **2. Feature Engineering Strategy**
- **Rolling averages** for form (last 3-5 gameweeks)
- **Per-90 metrics** for rate-based performance
- **Team performance** as contextual features
- **Expected stats** as primary predictors

#### **3. Model Types to Test**
- **Linear Regression**: Basic linear relationship
- **Ridge Regression**: Linear with L2 regularization
- **Lasso Regression**: Linear with L1 regularization
- **Random Forest**: Non-linear ensemble method

### **Evaluation Metrics**
- **R² Score**: Coefficient of determination
- **RMSE**: Root Mean Square Error
- **MAE**: Mean Absolute Error
- **Cross-validation**: 5-fold cross-validation

---

## 🚀 Implementation Strategy

### **Phase 1: Data Preparation**
1. **Load and clean** all season data (2020-21 to 2024-25)
2. **Feature engineering** with expected stats
3. **Position-specific** data preparation
4. **Train/test split** with temporal validation

### **Phase 2: Model Development**
1. **Baseline models** for each position
2. **Feature selection** using importance analysis
3. **Hyperparameter tuning** for each model type
4. **Ensemble methods** for improved performance

### **Phase 3: Validation & Testing**
1. **Cross-validation** on historical data
2. **Out-of-sample testing** on recent seasons
3. **Performance comparison** across model types
4. **Feature importance analysis**

### **Validation Strategy**
- **Training Set**: 2020-2024 data (4 seasons)
- **Validation Set**: 2024-2025 season data
- **Approach**: Predict squad and formation for 2024-25 season using historical data
- **Validation Method**: Compare predicted performance with actual 2024-25 performance
- **Success Metrics**: 
  - Squad selection accuracy
  - Formation optimization
  - Points prediction accuracy
  - Transfer strategy effectiveness

### **Phase 4: Deployment**
1. **Current season predictions** for 2024-25
2. **Player ranking** by predicted performance
3. **Value analysis** for team selection
4. **Captain recommendations**
5. **Transfer strategy optimization**
6. **Formation validation and compliance**

### **Key Success Metrics**
- **Prediction Accuracy**: R² > 0.7 for each position
- **Feature Importance**: Expected stats in top 5 features
- **Practical Utility**: Identifies undervalued players
- **Model Stability**: Consistent performance across seasons

---

## 📊 Expected Outcomes

### **Model Performance Targets**
- **Overall R²**: > 0.75
- **Position-specific R²**: 
  - Forwards: > 0.80
  - Midfielders: > 0.75
  - Defenders: > 0.70
  - Goalkeepers: > 0.65

### **Business Value**
- **Identify undervalued players** for team selection
- **Optimize captain choices** based on predicted performance
- **Improve team formation** with data-driven insights
- **Enhance transfer strategy** with forward-looking predictions
- **Optimize transfer timing** to maximize free transfer usage
- **Wildcard optimization** for maximum team value

### **Technical Deliverables**
- **Prediction model** with API interface
- **Player ranking system** by predicted performance
- **Team optimization algorithm** within budget constraints
- **Captain recommendation engine**
- **Transfer management system** with free transfer tracking
- **Wildcard optimization** for unlimited transfer scenarios
- **Formation validation** for transfer compliance

---

## ⚠️ Limitations & Considerations

### **Model Limitations**
1. **Data Availability**: Limited to available FPL data
2. **Dynamic Nature**: Football is inherently unpredictable
3. **Injuries/Suspensions**: Not always captured in data
4. **Manager Decisions**: Team selection changes
5. **Fixture Difficulty**: Not directly modeled

### **Future Improvements**
1. **Advanced Features**: Fixture difficulty, weather, injuries
2. **Model Enhancements**: Time series analysis, deep learning
3. **Additional Data Sources**: Understat, FBRef, news sentiment
4. **Real-time Updates**: Live data integration
5. **Expected Stats Integration**: 
   - **Post-Gameweek Analysis**: Use expected stats (xG, xA) for post-gameweek performance analysis
   - **Performance Validation**: Compare actual vs expected performance to identify over/under-performers
   - **Transfer Insights**: Use expected stats to identify players likely to regress or improve
   - **Implementation**: Add expected stats features after each gameweek completion
   - **Note**: Expected stats are only available AFTER gameweek completion, not for pre-gameweek predictions

---

## 📄 Conclusion

This design document outlines a comprehensive approach to building an FPL prediction model that leverages:

- **Comprehensive FPL rules understanding**
- **Advanced expected stats** (xG, xA) with high correlations
- **Position-specific modeling** for accurate predictions
- **Historical data** from 5 seasons (2020-21 to 2024-25)
- **Practical application** for team selection and captain choices

The model aims to provide data-driven insights for FPL managers while maintaining high prediction accuracy and practical utility.

---

## 🔄 Transfer Recommendation System

### **Objective**
Provide intelligent transfer recommendations after each gameweek to optimize squad performance for the next gameweek.

### **Implementation Status: ✅ IMPLEMENTED**

#### **Current Functionality**
- **Transfer Analysis**: Compares current squad players with predicted performance
- **Cost Optimization**: Identifies free or cheaper upgrades
- **Points Gain Calculation**: Estimates expected points improvement
- **Priority Ranking**: Sorts transfers by points gain per cost difference
- **Transfer Limits**: Respects free transfer allowances and wildcard usage

#### **Transfer Recommendation Logic**
```python
def suggest_transfers(self, current_squad, transfers_available=1, use_wildcard=False):
    # Analyze current squad vs predicted performance
    # Find better alternatives within budget constraints
    # Calculate points gain and cost difference
    # Rank by priority (points gain / cost difference)
    # Return top recommendations within transfer limits
```

#### **Usage Example**
```python
# After Gameweek 1, suggest transfers for Gameweek 2
transfers = model.suggest_transfers(current_squad, transfers_available=1)
# Returns: {'suggestions': [...], 'expected_points_gain': 15.2}
```

### **Future Enhancements**
- **Fixture Difficulty Integration**: Consider upcoming fixture difficulty
- **Form Analysis**: Include recent form trends in transfer decisions
- **Injury/Suspension Alerts**: Flag players with availability issues
- **Captain Transfer Options**: Suggest captain changes with transfers

---

## 📈 Current Season Performance Integration

### **Objective**
Integrate 2024-25 season performance data into the model after 5 gameweeks to improve prediction accuracy.

### **Implementation Status: ❌ NOT IMPLEMENTED**

#### **Proposed Implementation**
1. **Data Collection**: Monitor 2024-25 gameweek data after each completion
2. **Performance Threshold**: Wait for 5 gameweeks of data before integration
3. **Model Retraining**: Retrain models with combined historical + current season data
4. **Weighted Learning**: Give higher weight to current season performance
5. **Incremental Updates**: Update predictions weekly after gameweek completion

#### **Implementation Strategy**
```python
def integrate_current_season_performance(self, gameweek_number):
    """
    Integrate current season performance after 5 gameweeks.
    
    Args:
        gameweek_number (int): Current gameweek number
    """
    if gameweek_number < 5:
        return "Insufficient data - need at least 5 gameweeks"
    
    # Load current season gameweek data
    current_gw_data = self.load_gameweek_data(gameweek_number)
    
    # Combine with historical data (weighted)
    combined_data = self.combine_historical_and_current_data(
        historical_weight=0.6,
        current_weight=0.4
    )
    
    # Retrain models with updated data
    self.retrain_models_with_current_data(combined_data)
    
    # Update predictions for remaining season
    updated_predictions = self.predict_current_season()
    
    return updated_predictions
```

#### **Expected Benefits**
- **Improved Accuracy**: Real-time performance data improves predictions
- **Form Recognition**: Identify players in good/bad form early
- **Injury Impact**: Account for injuries and team changes
- **Fixture Difficulty**: Include actual fixture performance data

#### **Data Requirements**
- **Gameweek Data**: Individual gameweek performance files
- **Expected Stats**: Post-gameweek xG, xA data (when available)
- **Team Performance**: Actual vs expected team performance
- **Player Availability**: Injury and suspension tracking

#### **Integration Timeline**
- **Week 1-4**: Use historical data only
- **Week 5**: Begin current season integration (40% weight)
- **Week 6+**: Incremental updates with increasing current season weight
- **Week 10+**: 60% current season, 40% historical data

---

**Document Version**: 1.1  
**Last Updated**: July 2025  
**Next Review**: After current season integration implementation 