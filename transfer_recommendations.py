#!/usr/bin/env python3
"""
FPL Transfer Recommendations and Current Season Integration
========================================================

This script demonstrates:
1. Transfer recommendations after gameweek completion
2. Current season performance integration after 5 gameweeks
3. Form analysis and squad optimization

Usage:
    python transfer_recommendations.py [gameweek_number]
"""

import sys
import json
from datetime import datetime
from fpl_prediction_model import FPLPredictionModel

def load_current_squad(squad_file=None):
    """Load current squad from saved file or create example squad."""
    
    if squad_file:
        try:
            with open(squad_file, 'r') as f:
                squad_data = json.load(f)
            
            # Convert squad data to model format
            squad = {
                'GK': [],
                'DEF': [],
                'MID': [],
                'FWD': [],
                'total_cost': squad_data.get('total_cost', 0),
                'formation': squad_data.get('formation', '4-4-2')
            }
            
            # Add players by position
            for position, players in squad_data.get('players', {}).items():
                for player in players:
                    squad[position].append({
                        'name': player['name'],
                        'now_cost': player['cost'] * 10,  # Convert to 0.1m units
                        'predicted_points': player['predicted_points'],
                        'element_type': player['element_type']
                    })
            
            print(f"✅ Loaded squad from {squad_file}")
            return squad
            
        except FileNotFoundError:
            print(f"⚠️ Squad file {squad_file} not found")
    
    # Create example squad for demonstration
    print("📋 Creating example squad for demonstration...")
    
    example_squad = {
        'GK': [
            {'name': 'Flekken', 'now_cost': 45, 'predicted_points': 158.4, 'element_type': 1},
            {'name': 'Henderson', 'now_cost': 46, 'predicted_points': 146.7, 'element_type': 1}
        ],
        'DEF': [
            {'name': 'Milenković', 'now_cost': 52, 'predicted_points': 139.4, 'element_type': 2},
            {'name': 'Murillo', 'now_cost': 47, 'predicted_points': 138.3, 'element_type': 2},
            {'name': 'Collins', 'now_cost': 46, 'predicted_points': 138.0, 'element_type': 2},
            {'name': 'Mykolenko', 'now_cost': 44, 'predicted_points': 137.5, 'element_type': 2},
            {'name': 'Wan-Bissaka', 'now_cost': 45, 'predicted_points': 131.1, 'element_type': 2}
        ],
        'MID': [
            {'name': 'M.Salah', 'now_cost': 136, 'predicted_points': 275.2, 'element_type': 3},
            {'name': 'Palmer', 'now_cost': 105, 'predicted_points': 171.2, 'element_type': 3},
            {'name': 'J.Murphy', 'now_cost': 52, 'predicted_points': 152.9, 'element_type': 3},
            {'name': 'Semenyo', 'now_cost': 57, 'predicted_points': 144.7, 'element_type': 3},
            {'name': 'Enzo', 'now_cost': 47, 'predicted_points': 143.6, 'element_type': 3}
        ],
        'FWD': [
            {'name': 'Haaland', 'now_cost': 149, 'predicted_points': 144.8, 'element_type': 4},
            {'name': 'Strand Larsen', 'now_cost': 52, 'predicted_points': 139.4, 'element_type': 4},
            {'name': 'Beto', 'now_cost': 48, 'predicted_points': 90.6, 'element_type': 4}
        ],
        'total_cost': 971,
        'formation': '4-4-2'
    }
    
    return example_squad

def display_squad(squad, title="Current Squad"):
    """Display squad information."""
    
    print(f"\n{'='*60}")
    print(f"🏆 {title}")
    print(f"{'='*60}")
    
    total_cost = sum(player['now_cost'] for position in ['GK', 'DEF', 'MID', 'FWD'] 
                    for player in squad.get(position, [])) / 10
    total_points = sum(player['predicted_points'] for position in ['GK', 'DEF', 'MID', 'FWD'] 
                      for player in squad.get(position, []))
    
    print(f"💰 Total Cost: £{total_cost:.1f}m / £100.0m ({total_cost/100*100:.1f}%)")
    print(f"📊 Total Predicted Points: {total_points:.1f}")
    print(f"📈 Average Points per Player: {total_points/15:.1f}")
    
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad and squad[position]:
            print(f"\n{position}:")
            for player in squad[position]:
                cost = player['now_cost'] / 10
                points = player['predicted_points']
                print(f"  {player['name']:<20} £{cost:>5.1f}m {points:>6.1f} pts")

def analyze_transfer_recommendations(model, current_squad, transfers_available=1):
    """Analyze and display transfer recommendations."""
    
    print(f"\n🔄 TRANSFER RECOMMENDATIONS ({transfers_available} free transfer{'s' if transfers_available > 1 else ''})")
    print("-" * 60)
    
    # Get transfer suggestions
    transfer_suggestions = model.suggest_transfers(current_squad, transfers_available)
    
    if not transfer_suggestions or not transfer_suggestions['suggestions']:
        print("  No transfer suggestions available")
        print("  💡 This could mean:")
        print("     - Your squad is already optimized")
        print("     - No better alternatives within budget")
        print("     - Need to use wildcard for major changes")
        return None
    
    print("Recommended Transfers:")
    print("-" * 40)
    
    for i, transfer in enumerate(transfer_suggestions['suggestions'], 1):
        out_player = transfer['out']
        in_player = transfer['in']
        points_gain = transfer['points_gain']
        cost_change = transfer['cost_change']
        position = transfer['position']
        
        print(f"{i}. {position}: {out_player} → {in_player}")
        print(f"   Points Gain: +{points_gain:.1f}")
        print(f"   Cost Change: £{cost_change/10:.1f}m")
        print(f"   Priority Score: {transfer['priority']:.2f}")
        print()
    
    print(f"Expected Points Gain: +{transfer_suggestions['expected_points_gain']:.1f}")
    print(f"Transfers Used: {transfer_suggestions['transfers_used']}")
    
    return transfer_suggestions

def demonstrate_current_season_integration(model, gameweek_number):
    """Demonstrate current season performance integration."""
    
    print(f"\n📈 CURRENT SEASON PERFORMANCE INTEGRATION (Gameweek {gameweek_number})")
    print("-" * 60)
    
    # Check if we have enough data
    if gameweek_number < 5:
        print(f"⚠️ Need at least 5 gameweeks for integration, got {gameweek_number}")
        print("   Using historical data only for predictions")
        return None
    
    # Integrate current season performance
    integration_result = model.integrate_current_season_performance(gameweek_number)
    
    if integration_result['status'] == 'success':
        print(f"✅ Successfully integrated current season data")
        print(f"   Gameweeks loaded: {integration_result['gameweeks_loaded']}")
        print(f"   Historical weight: {integration_result['historical_weight']:.1%}")
        print(f"   Current weight: {integration_result['current_weight']:.1%}")
        
        # Show updated predictions
        updated_predictions = integration_result['updated_predictions']
        if updated_predictions:
            print(f"\n🔄 Updated Predictions (with current season data):")
            for position, pred_df in updated_predictions.items():
                print(f"\n{position} (Top 3):")
                for _, player in pred_df.head(3).iterrows():
                    name = player['name']
                    cost = player['now_cost'] / 10
                    pred_points = player['predicted_points']
                    print(f"  {name:<20} £{cost:>5.1f}m {pred_points:>6.1f} pts")
        
        return integration_result
    
    else:
        print(f"❌ Integration failed: {integration_result['message']}")
        return None

def analyze_player_form(model, player_name, gameweek_number):
    """Analyze current season form for a specific player."""
    
    print(f"\n📊 PLAYER FORM ANALYSIS: {player_name}")
    print("-" * 40)
    
    form_data = model.get_current_season_form(player_name, gameweek_number)
    
    if form_data:
        print(f"Gameweeks Played: {form_data['gameweeks_played']}")
        print(f"Total Points: {form_data['total_points']:.1f}")
        print(f"Average Points: {form_data['avg_points']:.1f}")
        print(f"Recent Form (Last 3 GWs): {form_data['recent_form']:.1f}")
        print(f"Form Trend: {form_data['form_trend']}")
        
        # Form interpretation
        if form_data['form_trend'] == 'improving':
            print("💚 Player is in improving form - consider keeping")
        else:
            print("🔴 Player form is declining - consider transfer")
    else:
        print(f"⚠️ No form data available for {player_name}")

def main():
    """Main function to demonstrate transfer recommendations and current season integration."""
    
    # Parse command line arguments
    gameweek_number = 1
    if len(sys.argv) > 1:
        try:
            gameweek_number = int(sys.argv[1])
        except ValueError:
            print("⚠️ Invalid gameweek number, using Gameweek 1")
    
    print("🎯 FPL Transfer Recommendations & Current Season Integration")
    print("=" * 60)
    print(f"📅 Current Gameweek: {gameweek_number}")
    
    # Initialize model
    print("\n🔄 Loading FPL Prediction Model...")
    model = FPLPredictionModel()
    model.load_data()
    model.train_position_models()
    
    # Load current squad
    current_squad = load_current_squad("squads/squad_20250802_104843.json")
    display_squad(current_squad)
    
    # Analyze transfer recommendations
    transfer_suggestions = analyze_transfer_recommendations(model, current_squad, transfers_available=2)
    
    # Demonstrate current season integration
    integration_result = demonstrate_current_season_integration(model, gameweek_number)
    
    # Analyze form for key players
    print(f"\n📊 FORM ANALYSIS")
    print("-" * 30)
    
    key_players = ['M.Salah', 'Haaland', 'Palmer']
    for player in key_players:
        analyze_player_form(model, player, gameweek_number)
    
    # Summary
    print(f"\n{'='*60}")
    print("📋 SUMMARY")
    print(f"{'='*60}")
    
    if transfer_suggestions:
        print(f"✅ Transfer recommendations available")
        print(f"   Expected points gain: +{transfer_suggestions['expected_points_gain']:.1f}")
    else:
        print(f"ℹ️ No transfer recommendations (squad may be optimized)")
    
    if integration_result and integration_result['status'] == 'success':
        print(f"✅ Current season integration successful")
        print(f"   Using {integration_result['current_weight']:.1%} current season data")
    else:
        print(f"ℹ️ Using historical data only (insufficient current season data)")
    
    print(f"\n💡 Next Steps:")
    print(f"   1. Review transfer recommendations")
    print(f"   2. Consider form analysis for key players")
    print(f"   3. Update squad after gameweek completion")
    print(f"   4. Re-run analysis for next gameweek")
    
    print(f"\n✅ Analysis complete for Gameweek {gameweek_number}!")

if __name__ == "__main__":
    main() 