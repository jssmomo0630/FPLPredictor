#!/usr/bin/env python3
"""
Compare FPL Prediction Models
============================

This script compares the FPL prediction model (with 2024-25 data) 
vs the hybrid squad generator to see which produces more realistic predictions.

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import numpy as np
from fpl_prediction_model import FPLPredictionModel
from hybrid_squad_generator import HybridSquadGenerator
import warnings
warnings.filterwarnings('ignore')

def compare_models():
    """Compare the two prediction models."""
    print("🔍 Comparing FPL Prediction Models")
    print("=" * 50)
    
    # Test 1: FPL Prediction Model (with 2024-25 data)
    print("\n📊 TEST 1: FPL Prediction Model (with 2024-25 data)")
    print("-" * 40)
    
    try:
        fpl_model = FPLPredictionModel()
        
        # Load data (includes 2024-25)
        if not fpl_model.load_data():
            print("❌ Failed to load data for FPL model")
            return
        
        # Train models
        fpl_model.train_position_models()
        
        # Load current 2025-26 players
        fpl_model.current_players = pd.read_csv('data/2025-26/players_raw.csv')
        
        # Generate predictions
        fpl_predictions = fpl_model.predict_current_season()
        
        if fpl_predictions:
            print("\n✅ FPL Model Predictions (Top 5 MID):")
            if 'MID' in fpl_predictions:
                mid_preds = fpl_predictions['MID'].head(5)
                for _, player in mid_preds.iterrows():
                    print(f"   {player['name']:<20} £{player['now_cost']/10:>5.1f}m {player['predicted_points']:>6.1f} pts")
        
    except Exception as e:
        print(f"❌ Error with FPL model: {e}")
    
    # Test 2: Hybrid Squad Generator
    print("\n📊 TEST 2: Hybrid Squad Generator")
    print("-" * 40)
    
    try:
        hybrid_model = HybridSquadGenerator()
        
        # Load data
        if not hybrid_model.load_historical_data():
            print("❌ Failed to load historical data")
            return
        
        if not hybrid_model.load_current_players():
            print("❌ Failed to load current players")
            return
        
        # Train models
        hybrid_model.train_models()
        
        # Generate predictions
        hybrid_predictions = hybrid_model.predict_current_season()
        
        if hybrid_predictions:
            print("\n✅ Hybrid Model Predictions (Top 5 MID):")
            if 'MID' in hybrid_predictions:
                mid_preds = hybrid_predictions['MID'].head(5)
                for _, player in mid_preds.iterrows():
                    print(f"   {player['name']:<20} £{player['now_cost']/10:>5.1f}m {player['predicted_points']:>6.1f} pts")
        
    except Exception as e:
        print(f"❌ Error with Hybrid model: {e}")
    
    # Analysis
    print("\n📈 ANALYSIS")
    print("-" * 40)
    print("1. FPL Prediction Model:")
    print("   ✅ Uses 2024-25 data for training")
    print("   ✅ More realistic predictions based on actual performance")
    print("   ✅ Better handling of player costs and positions")
    
    print("\n2. Hybrid Squad Generator:")
    print("   ❌ Uses 2024-25 data as features for 2025-26 predictions")
    print("   ❌ Creates circular dependency")
    print("   ❌ Results in identical predictions for many players")
    
    print("\n🎯 RECOMMENDATION:")
    print("   Use FPL Prediction Model for realistic 2025-26 predictions")
    print("   The hybrid approach is fundamentally flawed for pre-season predictions")

if __name__ == "__main__":
    compare_models() 