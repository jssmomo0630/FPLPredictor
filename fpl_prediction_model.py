#!/usr/bin/env python3
"""
Fantasy Premier League (FPL) Prediction Model
=============================================

This module implements a comprehensive prediction model for FPL based on the design document.
Features include:
- Position-specific models (GK, DEF, MID, FWD)
- Expected stats integration (xG, xA)
- Transfer management system
- Formation validation
- Historical data training (2020-2024)
- 2024-25 season validation

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class FPLPredictionModel:
    """
    Comprehensive FPL prediction model with position-specific modeling,
    transfer management, and formation validation.
    """
    
    def __init__(self):
        """Initialize the FPL prediction model."""
        self.models = {
            'GK': None,
            'DEF': None,
            'MID': None,
            'FWD': None
        }
        self.scalers = {
            'GK': StandardScaler(),
            'DEF': StandardScaler(),
            'MID': StandardScaler(),
            'FWD': StandardScaler()
        }
        self.feature_importance = {}
        self.training_data = {}
        self.validation_data = {}
        self.transfer_manager = TransferManager()
        self.position_calibration = {}
        self.position_target_p95 = {}
        
    def load_data(self, data_path='data/'):
        """
        Load and prepare data from multiple seasons.
        
        Args:
            data_path (str): Path to data directory
        """
        print("[REFRESH] Loading FPL data from multiple seasons...")
        
        # Load historical data (2020-2026) with weighted importance
        self.historical_data = {}
        seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25', '2025-26']
        season_weights = [0.05, 0.05, 0.15, 0.25, 0.35, 0.2]  # 2025-26 gets 0.2 weight, historical gets 0.8 total
        
        for i, season in enumerate(seasons):
            try:
                season_path = f"{data_path}{season}/"
                players_df = pd.read_csv(f"{season_path}players_raw.csv")
                
                # Special handling for 2025-26 season (use enhanced data)
                if season == '2025-26':
                    gw_data = pd.read_csv(f"{season_path}merged_gw_enhanced.csv")
                else:
                    gw_data = pd.read_csv(f"{season_path}merged_gw.csv")
                
                # Handle position and element_type mapping
                if season == '2025-26':
                    # 2025-26 data already has element_type and now_cost from enhancement
                    if 'element_type' not in gw_data.columns:
                        position_to_element_type = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
                        gw_data['element_type'] = gw_data['position'].map(position_to_element_type)
                    if 'now_cost' not in gw_data.columns:
                        gw_data['now_cost'] = 50  # Default cost
                else:
                    # Historical data: Create element_type mapping from position column
                    position_to_element_type = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
                    gw_data['element_type'] = gw_data['position'].map(position_to_element_type)
                    # Add player cost information using average historical cost as fallback
                    avg_cost = players_df['now_cost'].dropna().mean()
                    if pd.isna(avg_cost):
                        avg_cost = 50  # Reasonable fallback if historical cost missing
                    gw_data['now_cost'] = avg_cost
                
                # Add season identifier and weight
                players_df['season'] = season
                gw_data['season'] = season
                players_df['season_weight'] = season_weights[i]
                gw_data['season_weight'] = season_weights[i]
                
                self.historical_data[season] = {
                    'players': players_df,
                    'gameweeks': gw_data,
                    'weight': season_weights[i]
                }
                data_source = "enhanced" if season == '2025-26' else "standard"
                print(f"[OK] Loaded {season} data: {len(players_df)} players, {len(gw_data)} gameweek records (weight: {season_weights[i]}, source: {data_source})")
                
            except Exception as e:
                print(f"[WARN]  {season} data error: {e}")
        
        # Load current season data (2025-26)
        try:
            current_path = f"{data_path}2025-26/"
            self.current_players = pd.read_csv(f"{current_path}players_raw.csv")
            print(f"[OK] Loaded 2025-26 data: {len(self.current_players)} players")
        except FileNotFoundError:
            print("[WARN]  2025-26 data not found")
            self.current_players = None
    
    def prepare_features(self, df, position=None):
        """
        Prepare features for the prediction model.
        
        Args:
            df (pd.DataFrame): Player data
            position (str): Position filter (GK, DEF, MID, FWD)
            
        Returns:
            pd.DataFrame: Feature matrix
        """
        print(f"[TOOLS] Preparing features for {position if position else 'all'} positions...")
        
        # Filter by position if specified
        if position:
            # Convert position string to numeric code
            position_map = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
            position_code = position_map.get(position, position)
            df = df[df['element_type'] == position_code].copy()
            
            # Remove rows with missing element_type (failed name matching)
            df = df.dropna(subset=['element_type'])
        
        # Basic features
        features = [
            'minutes', 'goals_scored', 'assists', 'clean_sheets',
            'goals_conceded', 'own_goals', 'penalties_saved',
            'penalties_missed', 'yellow_cards', 'red_cards',
            'saves', 'bonus', 'bps', 'influence', 'creativity',
            'threat', 'ict_index', 'total_points'
        ]
        
        # NOTE: Expected stats (xG, xA) are only available AFTER gameweek completion
        # For pre-gameweek predictions, we cannot use these features
        # TODO: Implement expected stats integration for post-gameweek analysis
        # expected_features = [
        #     'expected_goals', 'expected_assists', 'expected_goal_involvements',
        #     'expected_goals_per_90', 'expected_assists_per_90',
        #     'expected_goal_involvements_per_90', 'expected_goals_conceded',
        #     'expected_goals_conceded_per_90'
        # ]
        # 
        # available_expected = [f for f in expected_features if f in df.columns]
        # if available_expected:
        #     features.extend(available_expected)
        #     print(f"[OK] Added {len(available_expected)} expected stats features")
        # else:
        #     print(f"[WARN] No expected stats in training data - will handle in prediction")
        
        # Create derived features (handle division by zero)
        minutes_safe = df['minutes'].replace(0, 1)
        df['goals_per_90'] = (df['goals_scored'] / minutes_safe * 90).fillna(0)
        df['assists_per_90'] = (df['assists'] / minutes_safe * 90).fillna(0)
        df['points_per_90'] = (df['total_points'] / minutes_safe * 90).fillna(0)
        
        # Rolling and cumulative scoring features
        df['matches_played'] = df.groupby('name').cumcount() + 1
        df['cumulative_points'] = df.groupby('name')['total_points'].cumsum()
        df['avg_points_per_match'] = (df['cumulative_points'] / df['matches_played'].replace(0, 1)).fillna(0)
        
        if 'was_home' in df.columns:
            # Ensure numeric indicator 1 for home, 0 for away
            home_indicator = df['was_home']
            # Normalize possible string booleans
            if home_indicator.dtype == 'O':
                home_indicator = home_indicator.replace({'True': True, 'False': False, 'true': True, 'false': False})
            home_indicator = home_indicator.fillna(False).astype(bool).astype(int)
        else:
            home_indicator = pd.Series(0, index=df.index, dtype=int)
        away_indicator = (1 - home_indicator).astype(int)
        
        df['home_matches_played'] = home_indicator.groupby(df['name']).cumsum()
        df['away_matches_played'] = away_indicator.groupby(df['name']).cumsum()
        df['home_points_cumsum'] = (df['total_points'] * home_indicator).groupby(df['name']).cumsum()
        df['away_points_cumsum'] = (df['total_points'] * away_indicator).groupby(df['name']).cumsum()
        df['home_points_avg'] = (df['home_points_cumsum'] / df['home_matches_played'].replace(0, 1)).fillna(0)
        df['away_points_avg'] = (df['away_points_cumsum'] / df['away_matches_played'].replace(0, 1)).fillna(0)
        
        df['clean_sheets_cumulative'] = df.groupby('name')['clean_sheets'].cumsum()
        df['clean_sheet_rate'] = (df['clean_sheets_cumulative'] / df['matches_played'].replace(0, 1)).fillna(0)
        df['def_clean_sheet_rate'] = df['clean_sheet_rate'] * (df['element_type'] == 2).astype(int)
        
        # Add form features (rolling averages)
        df['form_3gw'] = df.groupby('name')['total_points'].rolling(3, min_periods=1).mean().reset_index(0, drop=True)
        df['form_5gw'] = df.groupby('name')['total_points'].rolling(5, min_periods=1).mean().reset_index(0, drop=True)
        
        # Add team performance features
        df['team_goals_scored'] = df.groupby(['season', 'round', 'team'])['goals_scored'].transform('sum')
        df['team_goals_conceded'] = df.groupby(['season', 'round', 'team'])['goals_conceded'].transform('sum')
        
        # Select final features
        final_features = [
            'minutes', 'goals_scored', 'assists', 'clean_sheets', 'goals_conceded',
            'saves', 'bonus', 'bps', 'influence', 'creativity', 'threat', 'ict_index',
            'goals_per_90', 'assists_per_90', 'points_per_90', 'avg_points_per_match',
            'form_3gw', 'form_5gw', 'team_goals_scored', 'team_goals_conceded',
            'home_points_avg', 'away_points_avg', 'clean_sheet_rate', 'def_clean_sheet_rate'
        ]
        
        # NOTE: Expected stats are commented out for now
        # Add expected features if available
        # final_features.extend(available_expected)
        
        # Remove rows with missing target variable
        df = df.dropna(subset=['total_points'])
        
        # Fill NaN values in features with 0
        for feature in final_features:
            if feature in df.columns:
                df[feature] = df[feature].fillna(0)
        
        return df[final_features + ['total_points', 'name', 'element_type', 'now_cost', 'season', 'season_weight']]
    
    def train_position_models(self):
        """Train separate models for each position using 2020-2024 data only."""
        print("[TRAIN] Training position-specific models using 2020-2024 data...")
        
        # Combine all historical data (2020-2024 for training)
        all_data = []
        for season, data in self.historical_data.items():
            season_data = data['gameweeks'].copy()
            # Season column is already added in load_data method
            all_data.append(season_data)
        
        combined_data = pd.concat(all_data, ignore_index=True)
        
        # Train models for each position
        positions = ['GK', 'DEF', 'MID', 'FWD']
        # Reset calibration per training run
        self.position_calibration = {}
        
        for position in positions:
            print(f"\n[TARGET] Training {position} model...")
            
            # Prepare features for this position
            position_data = self.prepare_features(combined_data, position)
            
            if len(position_data) == 0:
                print(f"[WARN] No data available for {position}")
                continue
            
            # Split data (temporal split - use 2020-2023 for training, 2023-24 for validation)
            train_data = position_data[position_data['season'].isin(['2020-21', '2021-22', '2022-23'])]
            val_data = position_data[position_data['season'] == '2023-24']
            
            if len(train_data) == 0 or len(val_data) == 0:
                print(f"[WARN] Insufficient data for {position}")
                continue
            
            # Prepare training data with sample weights
            X_train = train_data.drop(['total_points', 'name', 'element_type', 'now_cost', 'season', 'season_weight'], axis=1)
            y_train = train_data['total_points']
            
            # Create sample weights based on season importance
            sample_weights = train_data['season_weight'].values
            
            # Prepare validation data
            X_val = val_data.drop(['total_points', 'name', 'element_type', 'now_cost', 'season', 'season_weight'], axis=1)
            y_val = val_data['total_points']
            
            # Scale features
            X_train_scaled = self.scalers[position].fit_transform(X_train)
            X_val_scaled = self.scalers[position].transform(X_val)
            
            # Train multiple models
            models = {
                'Linear': LinearRegression(),
                'Ridge': Ridge(alpha=1.0),
                'Lasso': Lasso(alpha=0.1),
                'RandomForest': RandomForestRegressor(n_estimators=100, random_state=42)
            }
            
            best_score = -np.inf
            best_model = None
            
            for name, model in models.items():
                # Cross-validation on training data with sample weights
                cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring='r2', fit_params={'sample_weight': sample_weights})
                mean_cv_score = cv_scores.mean()
                
                # Validation set evaluation
                model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
                y_pred = model.predict(X_val_scaled)
                val_r2 = r2_score(y_val, y_pred)
                
                print(f"  {name}: CV R^2 = {mean_cv_score:.3f}, Val R^2 = {val_r2:.3f}")
                
                if val_r2 > best_score:
                    best_score = val_r2
                    best_model = model
            
            # Store best model
            self.models[position] = best_model
            self.training_data[position] = {
                'X_train': X_train_scaled,
                'y_train': y_train,
                'X_val': X_val_scaled,
                'y_val': y_val,
                'feature_names': X_train.columns.tolist()
            }

            # Position-level mean calibration to correct skew (use validation set)
            y_val_pred = best_model.predict(X_val_scaled)
            actual_p95 = np.percentile(y_val, 95) if len(y_val) > 0 else 0
            pred_p95 = np.percentile(y_val_pred, 95) if len(y_val_pred) > 0 else 0
            if pred_p95 > 0:
                self.position_calibration[position] = actual_p95 / pred_p95
            else:
                self.position_calibration[position] = 1.0
            self.position_target_p95[position] = actual_p95
            
            # Feature importance
            if hasattr(best_model, 'feature_importances_'):
                self.feature_importance[position] = dict(zip(X_train.columns, best_model.feature_importances_))
            elif hasattr(best_model, 'coef_'):
                self.feature_importance[position] = dict(zip(X_train.columns, np.abs(best_model.coef_)))
            
            print(f"[OK] {position} model trained with Val R^2 = {best_score:.3f}")
    
    def validate_on_2024_25(self):
        """Validate model performance on 2024-25 season data."""
        if self.current_players is None:
            print("[WARN] No 2024-25 data available for validation")
            return None
        
        print("[SEARCH] Validating model performance on 2024-25 season...")
        
        validation_results = {}
        
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if self.models[position] is None:
                continue
            
            # Prepare 2024-25 data for this position
            position_data = self.current_players[self.current_players['element_type'] == position].copy()
            
            if len(position_data) == 0:
                continue
            
            # Prepare features (same as training)
            position_data = self.prepare_features(position_data, position)
            
            if len(position_data) == 0:
                continue
            
            # Prepare features for prediction
            X_val = position_data.drop(['total_points', 'name', 'element_type', 'now_cost'], axis=1, errors='ignore')
            
            # Scale features
            X_val_scaled = self.scalers[position].transform(X_val)
            
            # Make predictions
            y_pred = self.models[position].predict(X_val_scaled)
            
            # Calculate validation metrics
            if 'total_points' in position_data.columns:
                y_true = position_data['total_points']
                val_r2 = r2_score(y_true, y_pred)
                val_rmse = np.sqrt(mean_squared_error(y_true, y_pred))
                val_mae = mean_absolute_error(y_true, y_pred)
            else:
                val_r2 = val_rmse = val_mae = None
            
            validation_results[position] = {
                'predictions': y_pred,
                'R2': val_r2,
                'RMSE': val_rmse,
                'MAE': val_mae,
                'data': position_data
            }
            
            print(f"[OK] {position} validation: R^2 = {val_r2:.3f}, RMSE = {val_rmse:.3f}, MAE = {val_mae:.3f}")
        
        return validation_results
    
    def predict_current_season(self):
        """Predict performance for current season (2025-26)."""
        if self.current_players is None:
            print("[WARN] No current season data available")
            return None
        
        print("[PRED] Predicting 2025-26 season performance...")
        predictions = {}

        # Build current-season position anchors from actual points_per_game (helps de-skew positions)
        self.current_position_p95 = {}
        try:
            for pos_name, pos_code in {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}.items():
                pos_df = self.current_players[self.current_players['element_type'] == pos_code].copy()
                if len(pos_df) == 0:
                    continue
                ppg = pd.to_numeric(pos_df.get('points_per_game', np.nan), errors='coerce')
                if ppg.isna().all():
                    # fallback: total_points per appearance proxy
                    matches_est = (pos_df['minutes'] / 90).replace(0, np.nan)
                    ppg = pos_df.get('total_points', 0) / matches_est.replace(0, np.nan)
                ppg = ppg.replace([np.inf, -np.inf], np.nan).fillna(0)
                anchor_p95 = np.percentile(ppg, 95) if len(ppg) > 0 else None
                if anchor_p95 and anchor_p95 > 0:
                    self.current_position_p95[pos_name] = anchor_p95
        except Exception as e:
            print(f"[WARN] Unable to compute current-season anchors: {e}")
        
        # Pre-compute home/away and clean sheet rates from current season gameweek data
        agg_home_away = pd.DataFrame()
        current_season = '2025-26'
        try:
            from pathlib import Path
            gw_path = Path(f"data/{current_season}/merged_gw_enhanced.csv")
            if not gw_path.exists():
                gw_path = Path(f"data/{current_season}/merged_gw.csv")
            if gw_path.exists():
                gw_df = pd.read_csv(gw_path)
                if 'element' in gw_df.columns:
                    matches = gw_df.groupby('element')['total_points'].count()
                    clean_sheet_sum = gw_df.groupby('element')['clean_sheets'].sum()
                    clean_sheet_rate = (clean_sheet_sum / matches.replace(0, np.nan)).fillna(0)
                    
                    home_mask = gw_df['was_home'] == 1 if 'was_home' in gw_df.columns else pd.Series(False, index=gw_df.index)
                    away_mask = gw_df['was_home'] == 0 if 'was_home' in gw_df.columns else pd.Series(False, index=gw_df.index)
                    
                    home_points_sum = gw_df[home_mask].groupby('element')['total_points'].sum()
                    home_matches = gw_df[home_mask].groupby('element')['total_points'].count()
                    away_points_sum = gw_df[away_mask].groupby('element')['total_points'].sum()
                    away_matches = gw_df[away_mask].groupby('element')['total_points'].count()
                    
                    all_elements = matches.index
                    agg_home_away = pd.DataFrame(index=all_elements)
                    agg_home_away['home_points_avg'] = (home_points_sum / home_matches.replace(0, np.nan)).reindex(all_elements).fillna(0)
                    agg_home_away['away_points_avg'] = (away_points_sum / away_matches.replace(0, np.nan)).reindex(all_elements).fillna(0)
                    agg_home_away['clean_sheet_rate_from_gw'] = clean_sheet_rate.reindex(all_elements).fillna(0)

                    # Recent form features (last 3 and 5 gameweeks) and recent minutes
                    if 'gameweek' in gw_df.columns and 'total_points' in gw_df.columns:
                        gw_sorted = gw_df.sort_values(['element', 'gameweek'])
                        form_3 = gw_sorted.groupby('element')['total_points'].rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
                        form_5 = gw_sorted.groupby('element')['total_points'].rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)
                        mins_5 = gw_sorted.groupby('element')['minutes'].rolling(5, min_periods=1).sum().reset_index(level=0, drop=True) if 'minutes' in gw_sorted.columns else pd.Series(0, index=gw_sorted.index)
                        gw_sorted = gw_sorted.assign(form_3gw_calc=form_3, form_5gw_calc=form_5, minutes_5gw_calc=mins_5)
                        last_rows = gw_sorted.groupby('element').tail(1)[['element', 'form_3gw_calc', 'form_5gw_calc', 'minutes_5gw_calc', 'gameweek']]
                        last_rows = last_rows.set_index('element')
                        # Attach rolling features to aggregates so we can merge once later
                        agg_home_away = agg_home_away.join(last_rows, how='left')
        except Exception as e:
            print(f"[WARN] Unable to build home/away aggregates: {e}")
        
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if self.models[position] is None:
                continue
            
            # Get current season players for this position
            position_map = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
            position_code = position_map[position]
            
            position_data = self.current_players[self.current_players['element_type'] == position_code].copy()
            
            if len(position_data) == 0:
                continue
            
            # Create basic features for prediction (using available data)
            # We'll use historical averages and current season stats where available
            position_data['name'] = position_data['web_name']
            position_data['total_points'] = position_data.get('total_points', 0)
            
            # Add basic features that are available
            position_data['minutes'] = position_data.get('minutes', 90)  # Assume full game
            position_data['goals_scored'] = position_data.get('goals_scored', 0)
            position_data['assists'] = position_data.get('assists', 0)
            position_data['clean_sheets'] = position_data.get('clean_sheets', 0)
            position_data['goals_conceded'] = position_data.get('goals_conceded', 0)
            position_data['saves'] = position_data.get('saves', 0)
            position_data['bonus'] = position_data.get('bonus', 0)
            position_data['bps'] = position_data.get('bps', 0)
            position_data['influence'] = position_data.get('influence', 0)
            position_data['creativity'] = position_data.get('creativity', 0)
            position_data['threat'] = position_data.get('threat', 0)
            position_data['ict_index'] = position_data.get('ict_index', 0)

            # Scale season aggregates to per-match to match per-GW training scale
            matches_from_minutes = (position_data['minutes'] / 90).replace([np.inf, -np.inf], np.nan)
            starts_series = position_data['starts'] if 'starts' in position_data.columns else pd.Series(0, index=position_data.index)
            matches_est = pd.concat([matches_from_minutes, starts_series], axis=1).max(axis=1)
            matches_est = matches_est.replace([np.inf, -np.inf], np.nan).fillna(1).clip(lower=1)

            per_match_cols = [
                'goals_scored', 'assists', 'clean_sheets', 'goals_conceded', 'saves',
                'bonus', 'bps', 'influence', 'creativity', 'threat', 'ict_index'
            ]
            for col in per_match_cols:
                if col in position_data.columns:
                    position_data[col] = position_data[col] / matches_est

            # Average minutes per match (cap at 90)
            position_data['minutes'] = (position_data['minutes'] / matches_est).clip(upper=90)

            # No per-match normalization here; keep season aggregates consistent with training scale
            
            # Create derived features
            minutes_safe = position_data['minutes'].replace(0, 1)
            position_data['goals_per_90'] = (position_data['goals_scored'] / minutes_safe * 90).fillna(0)
            position_data['assists_per_90'] = (position_data['assists'] / minutes_safe * 90).fillna(0)
            # Use points_per_game directly for points_per_90 and avg_points_per_match to avoid inflating low-minute players
            ppg_series = pd.to_numeric(position_data.get('points_per_game', np.nan), errors='coerce').fillna(0)
            position_data['points_per_90'] = ppg_series
            position_data['avg_points_per_match'] = ppg_series
            
            matches_est = (position_data['minutes'] / 90).replace(0, np.nan)
            if 'starts' in position_data.columns:
                matches_est = matches_est.fillna(position_data['starts'])
            position_data['matches_played_est'] = matches_est.replace(0, np.nan)
            
            clean_sheet_rate_est = position_data['clean_sheets'] / position_data['matches_played_est']
            position_data['clean_sheet_rate'] = clean_sheet_rate_est.replace([np.inf, -np.inf], 0).fillna(0)
            
            if not agg_home_away.empty and 'id' in position_data.columns:
                position_data = position_data.merge(agg_home_away, left_on='id', right_index=True, how='left')
            if 'home_points_avg' not in position_data.columns:
                position_data['home_points_avg'] = position_data['avg_points_per_match']
            else:
                position_data['home_points_avg'] = position_data['home_points_avg'].fillna(position_data['avg_points_per_match'])
            if 'away_points_avg' not in position_data.columns:
                position_data['away_points_avg'] = position_data['avg_points_per_match']
            else:
                position_data['away_points_avg'] = position_data['away_points_avg'].fillna(position_data['avg_points_per_match'])
            
            if 'clean_sheet_rate_from_gw' in position_data.columns:
                position_data['clean_sheet_rate'] = position_data['clean_sheet_rate'].where(
                    position_data['clean_sheet_rate'] > 0,
                    position_data['clean_sheet_rate_from_gw']
                )
                position_data.drop(columns=['clean_sheet_rate_from_gw'], inplace=True, errors='ignore')
            position_data['clean_sheet_rate'] = position_data['clean_sheet_rate'].replace([np.inf, -np.inf], 0).fillna(0)
            position_data['def_clean_sheet_rate'] = np.where(
                position_data['element_type'] == 2,
                position_data['clean_sheet_rate'],
                0
            )
            
            # Add true recent form features if available from current season GW data
            if 'form_3gw_calc' in position_data.columns:
                position_data['form_3gw'] = position_data['form_3gw_calc']
            else:
                # Fallback to per-match average points (avoid using season totals which skew scale)
                position_data['form_3gw'] = position_data.get('avg_points_per_match', 0)
            if 'form_5gw_calc' in position_data.columns:
                position_data['form_5gw'] = position_data['form_5gw_calc']
            else:
                position_data['form_5gw'] = position_data.get('avg_points_per_match', 0)
            # Drop intermediate columns if present
            position_data.drop(columns=[c for c in ['form_3gw_calc', 'form_5gw_calc'] if c in position_data.columns], inplace=True, errors='ignore')
            
            # Add team performance features (simplified)
            position_data['team_goals_scored'] = position_data['goals_scored']
            position_data['team_goals_conceded'] = position_data['goals_conceded']
            
            # Select features for prediction (same as training)
            # Use only the features that were used during training
            feature_columns = [
                'minutes', 'goals_scored', 'assists', 'clean_sheets', 'goals_conceded',
                'saves', 'bonus', 'bps', 'influence', 'creativity', 'threat', 'ict_index',
                'goals_per_90', 'assists_per_90', 'points_per_90', 'avg_points_per_match',
                'form_3gw', 'form_5gw', 'team_goals_scored', 'team_goals_conceded',
                'home_points_avg', 'away_points_avg', 'clean_sheet_rate', 'def_clean_sheet_rate'
            ]
            
            # NOTE: Expected stats (xG, xA) are only available AFTER gameweek completion
            # For pre-gameweek predictions, we cannot use these features
            # TODO: Implement expected stats integration for post-gameweek analysis
            # expected_features = [
            #     'expected_goals', 'expected_assists', 'expected_goal_involvements',
            #     'expected_goals_conceded'
            # ]
            
            # Prepare features for prediction
            # Only use features that exist in both training and prediction data
            final_features = []
            for feature in feature_columns:
                if feature in position_data.columns:
                    final_features.append(feature)
                else:
                    # If feature not available, add zeros
                    position_data[feature] = 0
                    final_features.append(feature)
            
            X_pred = position_data[final_features].fillna(0)
            
            # Scale features
            X_pred_scaled = self.scalers[position].transform(X_pred)
            
            # Make predictions
            y_pred = self.models[position].predict(X_pred_scaled)
            
            # Remove cost-based boosting; rely on model features and recent form
            # Optionally, future work: blend with historical baseline if recent minutes are extremely low
            
            # Create prediction dataframe (include team information)
            pred_df = position_data[['name', 'element_type', 'now_cost', 'team']].copy()
            pred_df['predicted_points'] = y_pred

            # Floor predictions by actual form so premiums don't collapse (e.g., Haaland vs Watkins)
            if 'avg_points_per_match' in position_data.columns:
                form_ppg = position_data['avg_points_per_match'].fillna(0).values
                pred_df['predicted_points'] = np.maximum(pred_df['predicted_points'].values, form_ppg)

            # Minutes-volume damping to suppress tiny-sample spikes (all positions)
            minutes_total = self.current_players[self.current_players['element_type'] == position_code]['minutes'].fillna(0)
            minutes_total = minutes_total.reindex(position_data.index).fillna(0)
            minutes_factor_total = (minutes_total / 900).clip(0.2, 1.0)  # need ~10 full games for full weight
            pred_df['predicted_points'] = pred_df['predicted_points'] * minutes_factor_total

            # Recompute per-90/value after form floor and minutes damping
            pred_df['predicted_points_per_90'] = (pred_df['predicted_points'] / position_data['minutes'] * 90).fillna(0)
            pred_df['value_per_predicted_point'] = pred_df['predicted_points'] / (pred_df['now_cost'] / 10)

            predictions[position] = pred_df.sort_values('predicted_points', ascending=False)
        
        return predictions
    
    def optimize_squad(self, budget=100.0, formation=None):
        """
        Optimize squad selection within budget and formation constraints.
        Tests multiple formations to find the optimal one.
        
        Args:
            budget (float): Total budget in millions
            formation (str): Specific formation string (e.g., '4-4-2') or None to test all
            
        Returns:
            dict: Optimized squad with transfer information
        """
        print(f"[BALL] Optimizing squad with GBP{budget}m budget...")
        
        # Get predictions
        predictions = self.predict_current_season()
        if not predictions:
            return None
        
        # If specific formation is requested, use it
        if formation:
            return self._optimize_single_formation(budget, formation, predictions)
        
        # Try different formations to find the best one
        valid_formations = [
            ('3-5-2', 3, 5, 2),
            ('3-4-3', 3, 4, 3),
            ('4-5-1', 4, 5, 1),
            ('4-4-2', 4, 4, 2),
            ('4-3-3', 4, 3, 3),
            ('5-4-1', 5, 4, 1),
            ('5-3-2', 5, 3, 2)
        ]
        
        best_squad = None
        best_points = 0
        best_formation = None
        
        for formation_name, def_count, mid_count, fwd_count in valid_formations:
            print(f"\n[SEARCH] Testing formation: {formation_name}")
            
            squad = self._optimize_single_formation(budget, formation_name, predictions)
            
            if squad:
                # Calculate total points INCLUDING captain double points
                total_points_with_captain, captain_info = self.calculate_squad_total_points(squad, formation_name)
                
                base_points = 0
                for position in ['GK', 'DEF', 'MID', 'FWD']:
                    if position in squad and squad[position]:
                        base_points += sum(player['predicted_points'] for player in squad[position])
                
                captain_name = captain_info['name'] if captain_info else 'Unknown'
                captain_pts = captain_info['captain_points'] if captain_info else 0
                
                print(f"[OK] {formation_name}: GBP{squad['total_cost']/10:.1f}m, {base_points:.1f} base pts")
                print(f"   Captain: {captain_name} ({captain_pts:.1f} pts), Total: {total_points_with_captain:.1f} pts")
                
                if total_points_with_captain > best_points:
                    best_points = total_points_with_captain
                    best_squad = squad.copy()
                    best_squad['captain_info'] = captain_info
                    best_squad['total_points_with_captain'] = total_points_with_captain
                    best_formation = formation_name
        
        if not best_squad:
            print("[X] Failed to create valid squad")
            return None
        
        print(f"\n[TROPHY] Best formation: {best_formation}")
        print(f"[MONEY] Total cost: GBP{best_squad['total_cost']/10:.1f}m / GBP{budget:.1f}m ({best_squad['total_cost']/10/budget*100:.1f}% used)")
        
        if 'captain_info' in best_squad and best_squad['captain_info']:
            captain = best_squad['captain_info']
            print(f"[CROWN] Captain: {captain['name']} (GBP{captain['cost']:.1f}m, {captain['captain_points']:.1f} pts as captain)")
        
        print(f"[STATS] Total points with captain: {best_points:.1f}")
        
        return best_squad
    
    def _optimize_single_formation(self, budget, formation, predictions):
        """
        Optimize squad for a specific formation.
        
        Args:
            budget (float): Total budget in millions
            formation (str): Formation string (e.g., '4-4-2')
            predictions (dict): Player predictions by position
            
        Returns:
            dict: Optimized squad for the formation
        """
        print(f"[BALL] Optimizing squad with {formation} formation and GBP{budget}m budget...")
        
        # Parse formation
        def_count, mid_count, fwd_count = map(int, formation.split('-'))
        gk_count = 1
        
        # Calculate minimum costs for each position first
        position_min_costs = {}
        for pos in ['GK', 'DEF', 'MID', 'FWD']:
            if pos in predictions:
                position_min_costs[pos] = predictions[pos]['now_cost'].min()
        
        # Initialize squad
        squad = {
            'GK': [],
            'DEF': [],
            'MID': [],
            'FWD': [],
            'total_cost': 0,
            'formation': formation,
            'available_transfers': 1,
            'wildcard_available': True
        }
        
        # Calculate minimum squad cost first
        fpl_requirements = {'GK': 2, 'DEF': 5, 'MID': 5, 'FWD': 3}
        min_squad_cost = sum(position_min_costs[pos] * fpl_requirements[pos] for pos in fpl_requirements.keys() if pos in predictions)
        
        print(f"[MONEY] Minimum squad cost: GBP{min_squad_cost/10:.1f}m")
        print(f"[MONEY] Budget available for upgrades: GBP{(budget*10 - min_squad_cost)/10:.1f}m")
        
        # Use 70% of total budget for starting XI, 30% for bench (more conservative distribution)
        starting_budget = budget * 0.70  # GBP70m for starting XI  
        bench_budget = budget * 0.30     # GBP30m for bench
        
        print(f"[MONEY] Budget Allocation:")
        print(f"  Starting XI: GBP{starting_budget:.1f}m")
        print(f"  Bench: GBP{bench_budget:.1f}m")
        
        # Select players for each position (starting XI) with budget reservation
        position_order = [('GK', gk_count), ('DEF', def_count), ('MID', mid_count), ('FWD', fwd_count)]
        
        for i, (position, count) in enumerate(position_order):
            if position not in predictions:
                continue
            
            print(f"\n[TARGET] Selecting {position} players (need {count}):")
            
            # Simple budget calculation: ensure minimum budget for remaining players
            budget_in_units = starting_budget * 10
            used_so_far = squad['total_cost']
            
            # Calculate minimum cost for remaining starting XI players
            remaining_positions = position_order[i+1:]
            min_remaining_cost = sum(position_min_costs[pos] * cnt for pos, cnt in remaining_positions if pos in predictions)
            
            # Reserve minimum for this position
            min_this_position = position_min_costs[position] * count
            
            # Available budget (ensure at least minimum for remaining)
            available_budget = budget_in_units - used_so_far - min_remaining_cost
            
            print(f"  Budget analysis:")
            print(f"    Starting budget: GBP{starting_budget:.1f}m ({budget_in_units} units)")
            print(f"    Used so far: GBP{used_so_far/10:.1f}m ({used_so_far} units)")
            print(f"    Reserve for remaining: GBP{min_remaining_cost/10:.1f}m ({min_remaining_cost} units)")
            print(f"    Available for {position}: GBP{available_budget/10:.1f}m ({available_budget} units)")
            
            # Ensure we have at least minimum budget
            if available_budget < min_this_position:
                print(f"  [WARN] Insufficient budget! Need at least GBP{min_this_position/10:.1f}m, have GBP{available_budget/10:.1f}m")
                available_budget = min_this_position  # Use minimum required
            
            # Get top players by predicted points
            top_players = predictions[position].head(count * 3)  # Consider top 3x needed
            
            # Select best combination within available budget
            selected = self._select_optimal_players(top_players, count, available_budget, squad)
            
            squad[position].extend(selected)
            squad['total_cost'] += sum(player['now_cost'] for player in selected)
        
        # Add remaining players to complete FPL squad requirements (15 total players)
        # FPL requirements: 2 GK, 5 DEF, 5 MID, 3 FWD
        fpl_requirements = {
            'GK': 2,   # 1 starter + 1 bench
            'DEF': 5,  # 3-5 starters + 2-0 bench
            'MID': 5,  # 2-5 starters + 3-0 bench
            'FWD': 3   # 1-3 starters + 2-0 bench
        }
        
        print(f"\n[BENCH] Completing squad to meet FPL requirements:")
        
        for position, required_count in fpl_requirements.items():
            if position not in predictions:
                continue
            
            current_count = len(squad[position])
            needed_count = required_count - current_count
            
            if needed_count > 0:
                print(f"\n[TARGET] Adding {position} players (need {needed_count} more to reach {required_count}):")
                
                # Get remaining budget players (exclude already selected)
                selected_names = [p['name'] for p in squad[position]]
                remaining_players = predictions[position][~predictions[position]['name'].isin(selected_names)]
                
                # For bench players, prefer cheaper options but don't be too restrictive
                if position == 'GK' or current_count >= 3:  # Bench GK or bench players
                    # Try to find cheap players first, but if none available, use any player
                    cheap_players = remaining_players[remaining_players['now_cost'] <= 50]  # GBP5.0m or less
                    if len(cheap_players) > 0:
                        remaining_players = cheap_players
                        print(f"  Using cheap bench players (GBP5.0m or less)")
                    else:
                        print(f"  No cheap {position} players available, using any available player")
                
                if len(remaining_players) == 0:
                    print(f"  [WARN] No {position} players available")
                    continue
                
                # Use remaining budget
                remaining_budget = (budget * 10) - squad['total_cost']
                print(f"  Remaining budget: {remaining_budget} units (GBP{remaining_budget/10:.1f}m)")
                
                # Select players
                selected = self._select_optimal_players(remaining_players, needed_count, remaining_budget, squad)
                
                squad[position].extend(selected)
                squad['total_cost'] += sum(player['now_cost'] for player in selected)
        
        # Validate squad
        is_valid, message = self.validate_formation(squad)
        if not is_valid:
            print(f"[X] Squad validation failed: {message}")
            return None
        
        print(f"\n[OK] Squad optimization complete!")
        print(f"[MONEY] Total cost: GBP{squad['total_cost']/10:.1f}m / GBP{budget:.1f}m")
        print(f"[STATS] Formation: {squad['formation']}")
        
        return squad
    
    def calculate_squad_total_points(self, squad, formation='4-4-2'):
        """
        Calculate total squad points including captain double points.
        
        Args:
            squad (dict): Squad dictionary with players by position
            formation (str): Formation string (e.g., '4-4-2')
            
        Returns:
            tuple: (total_points, captain_info)
        """
        # Parse formation
        def_count, mid_count, fwd_count = map(int, formation.split('-'))
        gk_count = 1
        
        # Get all players
        all_players = []
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position in squad:
                all_players.extend(squad[position])
        
        # Group players by position
        position_groups = {
            'GK': [p for p in all_players if p['element_type'] == 1],
            'DEF': [p for p in all_players if p['element_type'] == 2],
            'MID': [p for p in all_players if p['element_type'] == 3],
            'FWD': [p for p in all_players if p['element_type'] == 4]
        }
        
        # Sort each group by predicted points
        for pos in position_groups:
            position_groups[pos].sort(key=lambda x: x['predicted_points'], reverse=True)
        
        # Select starting XI according to formation - prioritize premium players
        starting_xi = []
        starting_xi.extend(position_groups['GK'][:gk_count])
        
        # For each position, prioritize premium players (GBP8m+) for starting XI
        def prioritize_premium_for_starting(players, count):
            if len(players) <= count:
                return players
            
            # Separate premium and non-premium players
            premium = [p for p in players if p['now_cost'] >= 80]  # GBP8m+
            non_premium = [p for p in players if p['now_cost'] < 80]
            
            # Always include premium players first, then fill with best non-premium
            selected = premium[:count]  # Take all premium players (up to count)
            remaining_slots = count - len(selected)
            
            if remaining_slots > 0:
                selected.extend(non_premium[:remaining_slots])
            
            return selected
        
        starting_xi.extend(prioritize_premium_for_starting(position_groups['DEF'], def_count))
        starting_xi.extend(prioritize_premium_for_starting(position_groups['MID'], mid_count))
        starting_xi.extend(prioritize_premium_for_starting(position_groups['FWD'], fwd_count))
        
        # Remaining players go to bench
        bench = []
        bench.extend(position_groups['GK'][gk_count:])
        bench.extend(position_groups['DEF'][def_count:])
        bench.extend(position_groups['MID'][mid_count:])
        bench.extend(position_groups['FWD'][fwd_count:])
        
        # Find captain (prioritize premium players GBP8m+, then highest predicted points)
        if starting_xi:
            # Prioritize premium players (>GBP8m) for captaincy
            premium_players = [p for p in starting_xi if p['now_cost'] >= 80]  # GBP8m+
            
            if premium_players:
                captain = max(premium_players, key=lambda x: x['predicted_points'])
            else:
                captain = max(starting_xi, key=lambda x: x['predicted_points'])
            
            # Calculate total points with captain bonus
            total_points = sum(p['predicted_points'] for p in starting_xi)
            total_points += captain['predicted_points']  # Captain gets double points
            total_points += sum(p['predicted_points'] for p in bench) * 0.1  # Bench contributes 10% (for auto-subs)
            
            captain_info = {
                'name': captain['name'],
                'predicted_points': captain['predicted_points'],
                'captain_points': captain['predicted_points'] * 2,
                'cost': captain['now_cost'] / 10
            }
            
            return total_points, captain_info
        else:
            return 0, None
    
    def _select_optimal_players(self, players_df, count, remaining_budget, current_squad=None):
        """Select optimal players within budget constraint - prioritize captain potential."""
        players_list = players_df.to_dict('records')
        
        print(f"    Selecting {count} players with budget GBP{remaining_budget/10:.1f}m")
        
        # Get current team counts to enforce max 3 players per team
        current_team_counts = {}
        if current_squad:
            for position in ['GK', 'DEF', 'MID', 'FWD']:
                for player in current_squad.get(position, []):
                    team = player.get('team', 'Unknown')
                    current_team_counts[team] = current_team_counts.get(team, 0) + 1
        
        # Calculate captain-adjusted value for each player
        # Consider that the best player in the squad will be captain (2x points)
        for player in players_list:
            base_points = player['predicted_points']
            cost = player['now_cost']
            
            # Premium player bonus - strongly favor expensive players for starting XI
            premium_bonus = 0
            if cost >= 145:  # GBP14.5m+ (like Salah, Haaland)
                premium_bonus = 15
            elif cost >= 100:  # GBP10m+ (like Isak)
                premium_bonus = 10
            elif cost >= 80:   # GBP8m+
                premium_bonus = 5
            
            # Captain potential bonus (higher points = more likely to be captain)
            captain_bonus = base_points * 0.2 if base_points > 20 else 0
            
            # Adjusted points strongly favor premium players
            player['captain_adjusted_points'] = base_points + captain_bonus + premium_bonus
            player['captain_adjusted_value'] = player['captain_adjusted_points'] / (cost / 10) if cost > 0 else 0
        
        # Sort by captain-adjusted points (descending) to prioritize premium players with captain potential
        sorted_players = sorted(players_list, key=lambda x: x['captain_adjusted_points'], reverse=True)
        
        selected = []
        used_budget = 0
        
        # First pass: select premium players (>=GBP10m) but limit to 1-2 per position to preserve budget
        premium_players = [p for p in sorted_players if p['now_cost'] >= 100]  # >=GBP10m
        regular_players = [p for p in sorted_players if p['now_cost'] < 100]   # <GBP10m
        
        # Prioritize premium players but limit to avoid budget exhaustion
        premium_count = 0
        max_premium = min(2, count)  # Max 2 premium players per position
        
        for player in premium_players:
            if len(selected) >= count or premium_count >= max_premium:
                break
            
            # Check team constraint
            player_team = player.get('team', 'Unknown')
            if current_team_counts.get(player_team, 0) >= 3:
                print(f"      Skipped {player['name']} - Team {player_team} already has 3 players")
                continue
            
            player_cost = player['now_cost']
            # Ensure enough budget remains for remaining regular players
            min_cost_remaining = min([p['now_cost'] for p in regular_players], default=50) * (count - len(selected) - 1)
            if player_cost <= remaining_budget - min_cost_remaining:
                selected.append(player)
                used_budget += player_cost
                remaining_budget -= player_cost
                premium_count += 1
                # Update team count
                current_team_counts[player_team] = current_team_counts.get(player_team, 0) + 1
                print(f"      Selected PREMIUM: {player['name']} - GBP{player_cost/10:.1f}m - {player['predicted_points']:.1f} pts (Team: {player_team})")
        
        # Second pass: fill remaining spots with regular players
        for player in regular_players:
            if len(selected) >= count:
                break
            
            # Check team constraint
            player_team = player.get('team', 'Unknown')
            if current_team_counts.get(player_team, 0) >= 3:
                print(f"      Skipped {player['name']} - Team {player_team} already has 3 players")
                continue
            
            player_cost = player['now_cost']
            if player_cost <= remaining_budget:
                selected.append(player)
                used_budget += player_cost
                remaining_budget -= player_cost
                # Update team count
                current_team_counts[player_team] = current_team_counts.get(player_team, 0) + 1
                print(f"      Selected: {player['name']} - GBP{player_cost/10:.1f}m - {player['predicted_points']:.1f} pts (Team: {player_team})")
        
        # Third pass: upgrade with remaining budget (prioritize premium upgrades)
        if remaining_budget > 0:
            print(f"      Remaining budget: GBP{remaining_budget/10:.1f}m - attempting upgrades...")
            
            # Try to upgrade to premium players first
            for upgrade_player in premium_players:
                if upgrade_player in selected or remaining_budget <= 0:
                    continue
                    
                upgrade_cost = upgrade_player['now_cost']
                
                # Try to replace a cheaper player with this premium upgrade
                for i, current_player in enumerate(selected):
                    current_cost = current_player['now_cost']
                    cost_difference = upgrade_cost - current_cost
                    
                    if cost_difference <= remaining_budget and upgrade_player['predicted_points'] > current_player['predicted_points']:
                        # Make the upgrade
                        selected[i] = upgrade_player
                        remaining_budget -= cost_difference
                        used_budget += cost_difference
                        print(f"      Upgraded to PREMIUM: {current_player['name']} (GBP{current_cost/10:.1f}m) -> {upgrade_player['name']} (GBP{upgrade_cost/10:.1f}m)")
                        break
        
        total_cost = sum(player['now_cost'] for player in selected)
        total_points = sum(player['predicted_points'] for player in selected)
        
        print(f"    Final selection: {len(selected)} players")
        print(f"    Total cost: GBP{total_cost/10:.1f}m, Total points: {total_points:.1f}")
        total_available = remaining_budget + total_cost
        percentage = (total_cost / total_available * 100) if total_available > 0 else 0
        print(f"    Budget used: {total_cost/10:.1f}/{total_available/10:.1f}m ({percentage:.1f}%)")
        
        # If we didn't select enough players due to budget, try to get the cheapest available
        if len(selected) < count:
            print(f"    [WARN] Only selected {len(selected)} players, need {count}. Trying to add cheapest players...")
            
            # Get remaining players sorted by cost (ascending)
            remaining_players = [p for p in players_list if p not in selected]
            remaining_players.sort(key=lambda x: x['now_cost'])
            
            for player in remaining_players:
                if len(selected) >= count:
                    break
                
                # Check team constraint
                player_team = player.get('team', 'Unknown')
                if current_team_counts.get(player_team, 0) >= 3:
                    continue
                
                if player['now_cost'] <= remaining_budget:
                    selected.append(player)
                    remaining_budget -= player['now_cost']
                    current_team_counts[player_team] = current_team_counts.get(player_team, 0) + 1
                    print(f"      Added cheap player: {player['name']} - GBP{player['now_cost']/10:.1f}m (Team: {player_team})")
            
            # FAILSAFE: If still not enough players, force add the cheapest ones regardless of budget
            if len(selected) < count:
                print(f"    [WARN] FAILSAFE: Still need {count - len(selected)} more players. Force adding cheapest...")
                
                # Get all players for this position from predictions (not just top list)
                all_position_players = []
                for _, player in players_df.iterrows():
                    if player['name'] not in [p['name'] for p in selected]:
                        all_position_players.append(player.to_dict())
                
                # Sort by cost (ascending) and take the cheapest
                all_position_players.sort(key=lambda x: x['now_cost'])
                
                # Try to respect team constraints even in failsafe mode
                added = 0
                for player in all_position_players:
                    if added >= count - len(selected):
                        break
                    
                    player_team = player.get('team', 'Unknown')
                    # Only force if we really need to (prefer not violating team constraint)
                    if current_team_counts.get(player_team, 0) < 3 or len(selected) + added < count - 2:
                        selected.append(player)
                        if current_team_counts.get(player_team, 0) < 3:
                            current_team_counts[player_team] = current_team_counts.get(player_team, 0) + 1
                        print(f"      FORCED: {player['name']} - GBP{player['now_cost']/10:.1f}m (Team: {player_team}) (required for valid squad)")
                        added += 1
        
        return selected
    
    def suggest_transfers(self, current_squad, transfers_available=1, use_wildcard=False):
        """
        Suggest optimal transfers based on predicted performance.
        
        Args:
            current_squad (dict): Current squad information
            transfers_available (int): Number of free transfers available
            use_wildcard (bool): Whether to use wildcard (unlimited transfers)
            
        Returns:
            dict: Transfer suggestions with expected points gain
        """
        print(f"[REFRESH] Suggesting transfers ({transfers_available} available, wildcard: {use_wildcard})...")
        
        if use_wildcard:
            # Complete squad rebuild
            return self.optimize_squad()
        
        # Get current predictions
        predictions = self.predict_current_season()
        if not predictions:
            return None
        
        # Analyze current squad vs predicted performance
        transfer_suggestions = []
        
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position not in predictions:
                continue
            
            current_players = current_squad.get(position, [])
            
            for current_player in current_players:
                # Find better alternatives
                alternatives = predictions[position][predictions[position]['name'] != current_player['name']]
                
                for _, alternative in alternatives.iterrows():
                    points_gain = alternative['predicted_points'] - current_player['predicted_points']
                    cost_difference = alternative['now_cost'] - current_player['now_cost']
                    
                    if points_gain > 0 and cost_difference <= 0:  # Free or cheaper upgrade
                        transfer_suggestions.append({
                            'position': position,
                            'out': current_player['name'],
                            'in': alternative['name'],
                            'points_gain': points_gain,
                            'cost_change': cost_difference,
                            'priority': points_gain / max(abs(cost_difference), 1)
                        })
        
        # Sort by priority and limit to available transfers
        transfer_suggestions.sort(key=lambda x: x['priority'], reverse=True)
        
        return {
            'suggestions': transfer_suggestions[:transfers_available],
            'transfers_used': min(len(transfer_suggestions), transfers_available),
            'expected_points_gain': sum(t['points_gain'] for t in transfer_suggestions[:transfers_available])
        }
    
    def validate_formation(self, squad):
        """Validate squad formation and constraints according to FPL rules."""
        # FPL Formation Rules for Starting XI
        starting_xi_rules = {
            'GK': {'min': 1, 'max': 1},      # Exactly 1 GK
            'DEF': {'min': 3, 'max': 5},     # Minimum 3 DEF
            'MID': {'min': 2, 'max': 5},     # Minimum 2 MID (corrected from 3)
            'FWD': {'min': 1, 'max': 3}      # Minimum 1 FWD
        }
        
        # FPL Squad Rules (15 total players)
        squad_rules = {
            'GK': {'min': 2, 'max': 2},      # Exactly 2 GK total
            'DEF': {'min': 5, 'max': 5},     # Exactly 5 DEF total
            'MID': {'min': 5, 'max': 5},     # Exactly 5 MID total
            'FWD': {'min': 3, 'max': 3}      # Exactly 3 FWD total
        }
        
        # Check total squad size (must be exactly 15)
        total_players = sum(len(squad[pos]) for pos in ['GK', 'DEF', 'MID', 'FWD'])
        if total_players != 15:
            return False, f"Invalid total squad size: {total_players} players (need exactly 15)"
        
        # Check squad composition rules (15 players total)
        for position, rules in squad_rules.items():
            count = len(squad[position])
            if count != rules['min']:
                return False, f"Invalid {position} squad count: {count} (need exactly {rules['min']})"
        
        # For formation validation, we need to check if a valid starting XI can be formed
        # Parse the formation from squad metadata (e.g., '4-4-2')
        formation = squad.get('formation', '4-4-2')
        def_count, mid_count, fwd_count = map(int, formation.split('-'))
        gk_count = 1  # Always 1 GK in starting XI
        
        # Check if we can form the required starting XI formation
        starting_xi_requirements = {
            'GK': gk_count,
            'DEF': def_count,
            'MID': mid_count,
            'FWD': fwd_count
        }
        
        # Validate we have enough players for the starting XI
        for position, required in starting_xi_requirements.items():
            available = len(squad[position])
            if available < required:
                return False, f"Not enough {position} players for formation {formation}: have {available}, need {required}"
        
        # Count total starting XI players
        starting_xi_count = sum(starting_xi_requirements.values())
        if starting_xi_count != 11:
            return False, f"Invalid starting XI size: {starting_xi_count} players (need exactly 11)"
        
        # Check team constraint: maximum 3 players per team
        team_counts = {}
        all_players = []
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            all_players.extend(squad[position])
        
        for player in all_players:
            team = player.get('team', 'Unknown')
            team_counts[team] = team_counts.get(team, 0) + 1
            if team_counts[team] > 3:
                return False, f"Too many players from team {team}: {team_counts[team]} (max 3 allowed)"
        
        # All validations passed
        return True, "Valid FPL formation and squad"
    
    def evaluate_model_performance(self):
        """Evaluate model performance across all positions."""
        print("[STATS] Evaluating model performance...")
        
        results = {}
        
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position not in self.training_data:
                continue
            
            data = self.training_data[position]
            y_pred = self.models[position].predict(data['X_val'])
            
            results[position] = {
                'R2': r2_score(data['y_val'], y_pred),
                'RMSE': np.sqrt(mean_squared_error(data['y_val'], y_pred)),
                'MAE': mean_absolute_error(data['y_val'], y_pred)
            }
        
        return results
    
    def plot_feature_importance(self, position='MID'):
        """Plot feature importance for a specific position."""
        if position not in self.feature_importance:
            print(f"[WARN] No feature importance data for {position}")
            return
        
        importance = self.feature_importance[position]
        sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
        
        features, scores = zip(*sorted_features)
        
        plt.figure(figsize=(12, 6))
        plt.barh(features, scores)
        plt.title(f'Top 10 Feature Importance - {position}')
        plt.xlabel('Importance Score')
        plt.tight_layout()
        plt.show()
    
    def generate_report(self):
        """Generate comprehensive model report."""
        print("[CLIPBOARD] Generating comprehensive model report...")
        
        # Model performance
        performance = self.evaluate_model_performance()
        
        # Predictions for current season
        predictions = self.predict_current_season()
        
        # Optimized squad
        squad = self.optimize_squad()
        
        report = {
            'model_performance': performance,
            'predictions': predictions,
            'optimized_squad': squad,
            'feature_importance': self.feature_importance
        }
        
        return report

    def load_gameweek_data(self, gameweek_number, season='2025-26'):
        """
        Load specific gameweek data for current season.
        
        Args:
            gameweek_number (int): Gameweek number to load
            season (str): Season to load data from (default: '2025-26')
            
        Returns:
            pd.DataFrame: Gameweek data for specified gameweek
        """
        try:
            gw_file = f"data/{season}/gws/gw{gameweek_number}.csv"
            gw_data = pd.read_csv(gw_file)
            
            # Add gameweek identifier if not present
            if 'gameweek' not in gw_data.columns:
                gw_data['gameweek'] = gameweek_number
            if 'season' not in gw_data.columns:
                gw_data['season'] = season
            
            print(f"[OK] Loaded Gameweek {gameweek_number} ({season}) data: {len(gw_data)} records")
            return gw_data
            
        except FileNotFoundError:
            print(f"[WARN] Gameweek {gameweek_number} ({season}) data not found")
            return None
        except Exception as e:
            print(f"[X] Error loading gameweek {gameweek_number} ({season}): {e}")
            return None
    
    def get_available_gameweeks(self, season='2025-26'):
        """
        Get list of available gameweeks for a season.
        
        Args:
            season (str): Season to check (default: '2025-26')
            
        Returns:
            list: List of available gameweek numbers
        """
        import glob
        
        gws_dir = f"data/{season}/gws"
        if not os.path.exists(gws_dir):
            print(f"[WARN] Gameweeks directory not found: {gws_dir}")
            return []
        
        # Find all gameweek CSV files
        gw_files = glob.glob(f"{gws_dir}/gw*.csv")
        available_gws = []
        
        for gw_file in gw_files:
            try:
                # Extract gameweek number from filename
                filename = os.path.basename(gw_file)
                if filename.startswith('gw') and filename.endswith('.csv') and not filename.endswith('_enhanced.csv'):
                    gw_num = int(filename.replace('gw', '').replace('.csv', ''))
                    available_gws.append(gw_num)
            except ValueError:
                continue
        
        available_gws.sort()
        print(f"[OK] Found {len(available_gws)} available gameweeks for {season}: {available_gws}")
        return available_gws
    
    def combine_historical_and_current_data(self, historical_weight=0.6, current_weight=0.4):
        """
        Combine historical data with current season data using weighted approach.
        
        Args:
            historical_weight (float): Weight for historical data (0.0-1.0)
            current_weight (float): Weight for current season data (0.0-1.0)
            
        Returns:
            pd.DataFrame: Combined dataset with weighted importance
        """
        print(f"[REFRESH] Combining data: Historical ({historical_weight:.1%}), Current ({current_weight:.1%})")
        
        # Prepare historical data (2020-2024)
        historical_data = []
        for season, data in self.historical_data.items():
            season_data = data['gameweeks'].copy()
            season_data['data_weight'] = data['weight'] * historical_weight
            historical_data.append(season_data)
        
        combined_historical = pd.concat(historical_data, ignore_index=True)
        
        # Prepare current season data (if available)
        current_data = []
        if hasattr(self, 'current_season_gw_data'):
            for gw_data in self.current_season_gw_data.values():
                gw_data_copy = gw_data.copy()
                gw_data_copy['data_weight'] = current_weight
                current_data.append(gw_data_copy)
        
        if current_data:
            combined_current = pd.concat(current_data, ignore_index=True)
            # Combine historical and current data
            combined_data = pd.concat([combined_historical, combined_current], ignore_index=True)
            print(f"[OK] Combined data: {len(combined_historical)} historical + {len(combined_current)} current records")
        else:
            combined_data = combined_historical
            print(f"[OK] Using historical data only: {len(combined_historical)} records")
        
        return combined_data
    
    def integrate_current_season_performance(self, gameweek_number):
        """
        Integrate current season performance after 5 gameweeks.
        
        Args:
            gameweek_number (int): Current gameweek number
            
        Returns:
            dict: Updated predictions or status message
        """
        print(f"[TREND] Integrating current season performance (Gameweek {gameweek_number})...")
        
        if gameweek_number < 5:
            message = f"Insufficient data - need at least 5 gameweeks, got {gameweek_number}"
            print(f"[WARN] {message}")
            return {"status": "insufficient_data", "message": message}
        
        # Load current season gameweek data (all available gameweeks up to current)
        available_gws = self.get_available_gameweeks('2025-26')
        current_gws = [gw for gw in available_gws if gw <= gameweek_number]
        
        self.current_season_gw_data = {}
        for gw in current_gws:
            gw_data = self.load_gameweek_data(gw, '2025-26')
            if gw_data is not None:
                self.current_season_gw_data[gw] = gw_data
        
        if not self.current_season_gw_data:
            message = "No current season gameweek data available"
            print(f"[WARN] {message}")
            return {"status": "no_data", "message": message}
        
        print(f"[OK] Loaded {len(self.current_season_gw_data)} gameweeks of current season data")
        
        # Calculate weights based on gameweek number
        # Use 0.8 weight for historical data and 0.2 weight for 2025-26 data as requested
        if gameweek_number <= 10:
            historical_weight = 0.8
            current_weight = 0.2
        else:
            # As season progresses, gradually increase current season weight
            historical_weight = 0.7
            current_weight = 0.3
        
        # Combine historical and current data
        combined_data = self.combine_historical_and_current_data(
            historical_weight=historical_weight,
            current_weight=current_weight
        )
        
        # Retrain models with updated data
        self.retrain_models_with_current_data(combined_data)
        
        # Update predictions for remaining season
        updated_predictions = self.predict_current_season()
        
        return {
            "status": "success",
            "gameweeks_loaded": len(self.current_season_gw_data),
            "historical_weight": historical_weight,
            "current_weight": current_weight,
            "updated_predictions": updated_predictions
        }
    
    def retrain_models_with_current_data(self, combined_data):
        """
        Retrain models with combined historical and current season data.
        
        Args:
            combined_data (pd.DataFrame): Combined dataset with weighted importance
        """
        print("[TRAIN] Retraining models with current season data...")
        
        positions = ['GK', 'DEF', 'MID', 'FWD']
        
        for position in positions:
            print(f"\n[TARGET] Retraining {position} model...")
            
            # Prepare features for this position
            position_data = self.prepare_features(combined_data, position)
            
            if len(position_data) == 0:
                print(f"[WARN] No data available for {position}")
                continue
            
            # Get sample weights from original combined data
            # We need to match the position data back to the combined data to get weights
            position_names = position_data['name'].unique()
            weight_data = combined_data[combined_data['name'].isin(position_names)]
            
            # Create sample weights array matching the position_data order
            sample_weights = []
            for _, row in position_data.iterrows():
                # Find matching row in combined_data to get the weight
                matching_rows = weight_data[weight_data['name'] == row['name']]
                if not matching_rows.empty:
                    # Use the first matching weight (they should be the same for the same player)
                    sample_weights.append(matching_rows.iloc[0]['data_weight'])
                else:
                    # Default weight if no match found
                    sample_weights.append(1.0)
            
            sample_weights = np.array(sample_weights)
            
            # Prepare features and target
            X = position_data.drop(['total_points', 'name', 'element_type', 'now_cost', 'season', 'season_weight'], axis=1, errors='ignore')
            y = position_data['total_points']
            
            # Scale features
            X_scaled = self.scalers[position].fit_transform(X)
            
            # Train multiple models with sample weights
            models = {
                'Linear': LinearRegression(),
                'Ridge': Ridge(alpha=1.0),
                'Lasso': Lasso(alpha=0.1),
                'RandomForest': RandomForestRegressor(n_estimators=100, random_state=42)
            }
            
            best_score = -np.inf
            best_model = None
            
            for name, model in models.items():
                # Cross-validation with sample weights
                cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring='r2', fit_params={'sample_weight': sample_weights})
                mean_cv_score = cv_scores.mean()
                
                # Train model with sample weights
                model.fit(X_scaled, y, sample_weight=sample_weights)
                
                print(f"  {name}: CV R^2 = {mean_cv_score:.3f}")
                
                if mean_cv_score > best_score:
                    best_score = mean_cv_score
                    best_model = model
            
            # Store best model
            self.models[position] = best_model
            
            # Update feature importance
            if hasattr(best_model, 'feature_importances_'):
                self.feature_importance[position] = dict(zip(X.columns, best_model.feature_importances_))
            elif hasattr(best_model, 'coef_'):
                self.feature_importance[position] = dict(zip(X.columns, np.abs(best_model.coef_)))
            
            print(f"[OK] {position} model retrained with CV R^2 = {best_score:.3f}")
    
    def get_current_season_form(self, player_name, gameweek_number):
        """
        Get current season form for a specific player.
        
        Args:
            player_name (str): Player name
            gameweek_number (int): Current gameweek number
            
        Returns:
            dict: Form statistics for the player
        """
        if not hasattr(self, 'current_season_gw_data'):
            return None
        
        player_gw_data = []
        
        for gw, gw_data in self.current_season_gw_data.items():
            if gw <= gameweek_number:
                player_data = gw_data[gw_data['name'] == player_name]
                if not player_data.empty:
                    player_gw_data.append(player_data.iloc[0])
        
        if not player_gw_data:
            return None
        
        # Calculate form statistics
        total_points = sum(p['total_points'] for p in player_gw_data)
        avg_points = total_points / len(player_gw_data)
        recent_form = sum(p['total_points'] for p in player_gw_data[-3:]) / min(3, len(player_gw_data))
        
        return {
            'gameweeks_played': len(player_gw_data),
            'total_points': total_points,
            'avg_points': avg_points,
            'recent_form': recent_form,
            'form_trend': 'improving' if recent_form > avg_points else 'declining'
        }


class TransferManager:
    """Manages FPL transfer rules and constraints."""
    
    def __init__(self):
        self.free_transfers = 1
        self.wildcard_available = True
        self.bench_boost_available = True
        self.triple_captain_available = True
    
    def use_transfers(self, count):
        """Use specified number of transfers."""
        if count > self.free_transfers:
            return False, f"Not enough free transfers. Available: {self.free_transfers}, Requested: {count}"
        
        self.free_transfers -= count
        return True, f"Used {count} transfers. Remaining: {self.free_transfers}"
    
    def add_transfer(self):
        """Add a free transfer (max 2)."""
        if self.free_transfers < 2:
            self.free_transfers += 1
            return True, f"Added transfer. Total: {self.free_transfers}"
        return False, "Maximum transfers reached (2)"
    
    def use_wildcard(self):
        """Use wildcard chip."""
        if not self.wildcard_available:
            return False, "Wildcard not available"
        
        self.wildcard_available = False
        return True, "Wildcard used"
    
    def get_transfer_cost(self, transfers_used):
        """Calculate transfer cost in points."""
        if transfers_used <= self.free_transfers:
            return 0
        return (transfers_used - self.free_transfers) * -4


def main():
    """Main function to run the FPL prediction model."""
    print("[TARGET] FPL Prediction Model - Starting...")
    
    # Initialize model
    model = FPLPredictionModel()
    
    # Load data
    model.load_data()
    
    # Train models using 2020-2024 data
    model.train_position_models()
    
    # Validate on 2024-25 data
    validation_results = model.validate_on_2024_25()
    
    # Generate predictions and report
    report = model.generate_report()
    
    # Print results
    print("\n" + "="*50)
    print("[STATS] MODEL PERFORMANCE (2023-24 Validation)")
    print("="*50)
    
    for position, metrics in report['model_performance'].items():
        print(f"\n{position}:")
        for metric, value in metrics.items():
            print(f"  {metric}: {value:.3f}")
    
    print("\n" + "="*50)
    print("[SEARCH] 2024-25 SEASON VALIDATION")
    print("="*50)
    
    if validation_results:
        for position, results in validation_results.items():
            if results['R2'] is not None:
                print(f"\n{position}:")
                print(f"  R^2: {results['R2']:.3f}")
                print(f"  RMSE: {results['RMSE']:.3f}")
                print(f"  MAE: {results['MAE']:.3f}")
    else:
        print("[WARN] No validation results available")
    
    print("\n" + "="*50)
    print("[BALL] OPTIMIZED SQUAD")
    print("="*50)
    
    if report['optimized_squad']:
        squad = report['optimized_squad']
        print(f"Formation: {squad['formation']}")
        print(f"Total Cost: GBP{squad['total_cost']/10:.1f}m")
        print(f"Available Transfers: {squad['available_transfers']}")
        
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position in squad and squad[position]:
                print(f"\n{position}:")
                for player in squad[position]:
                    print(f"  {player['name']} - GBP{player['now_cost']/10:.1f}m - {player['predicted_points']:.1f} pts")
    
    print("\n" + "="*50)
    print("[TARGET] TOP PREDICTIONS BY POSITION")
    print("="*50)
    
    for position, predictions in report['predictions'].items():
        print(f"\n{position} (Top 5):")
        for _, player in predictions.head().iterrows():
            print(f"  {player['name']} - GBP{player['now_cost']/10:.1f}m - {player['predicted_points']:.1f} pts")
    
    print("\n[OK] FPL Prediction Model Complete!")


if __name__ == "__main__":
    main() 
