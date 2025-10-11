#!/usr/bin/env python3
"""
Use FPL Prediction Model for Squad Selection
===========================================

This script uses the trained FPL prediction model to:
1. Get current player predictions
2. Select optimal squad
3. Save squad for validation
4. Suggest transfers
5. Provide captain recommendations
"""

import pandas as pd
import json
import os
import sys
from datetime import datetime
from fpl_prediction_model import FPLPredictionModel

# Ensure UTF-8 output for player names with accents
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def load_and_predict():
    """Load the trained model and make predictions."""
    
    print("[TARGET] Loading FPL Prediction Model...")
    
    # Initialize and load the model
    model = FPLPredictionModel()
    model.load_data()
    model.train_position_models()
    
    return model

def get_predictions(model):
    """Get predictions for current season players."""
    
    print("\n[PRED] Getting 2024-25 Season Predictions...")
    
    predictions = model.predict_current_season()
    
    if not predictions:
        print("[X] No predictions available")
        return None
    
    # Display top predictions by position
    for position, pred_df in predictions.items():
        print(f"\n[TROPHY] Top 10 {position} Predictions:")
        print("-" * 50)
        
        for _, player in pred_df.head(10).iterrows():
            name = player['name']
            cost = player['now_cost'] / 10  # Convert to millions
            pred_points = player['predicted_points']
            value_ratio = player['value_per_predicted_point']
            
            print(f"  {name:<20} GBP{cost:>5.1f}m  {pred_points:>6.1f} pts  Value: {value_ratio:>6.2f}")
    
    return predictions

def validate_formation(starting_xi):
    """Validate that starting XI follows FPL formation rules."""
    gk_count = len([p for p in starting_xi if p['element_type'] == 1])
    def_count = len([p for p in starting_xi if p['element_type'] == 2])
    mid_count = len([p for p in starting_xi if p['element_type'] == 3])
    fwd_count = len([p for p in starting_xi if p['element_type'] == 4])
    
    # FPL formation validation rules
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
    
    return True, "Valid formation"

def select_optimal_squad(model, budget=100.0, formation='4-4-2'):
    """Select optimal squad with clear starting XI display."""
    print("[BALL] Selecting optimal squad...")
    
    # Get predictions
    predictions = get_predictions(model)
    if predictions is None:
        print("[X] No predictions available")
        return None
    
    # Optimize squad (try all formations to find best with captain consideration)
    squad = model.optimize_squad(budget=100.0, formation=None)
    if squad is None:
        print("[X] Failed to optimize squad")
        return None
    
    # Debug: print squad structure
    print(f"Squad keys: {list(squad.keys())}")
    for key, value in squad.items():
        if isinstance(value, list):
            print(f"{key}: {len(value)} players")
        else:
            print(f"{key}: {value}")
    
    # Display squad with clear starting XI vs bench
    print("\n" + "="*60)
    print("[TROPHY] OPTIMAL FPL SQUAD")
    print("="*60)
    
    # Starting XI (first 11 players by predicted points)
    all_players = []
    for position, players in squad.items():
        if isinstance(players, list):  # Check if it's a list of players
            all_players.extend(players)
        elif position in ['total_cost', 'formation']:  # Skip metadata
            continue
    
    # Get the actual formation from the squad
    actual_formation = squad.get('formation', formation)
    def_count, mid_count, fwd_count = map(int, actual_formation.split('-'))
    gk_count = 1  # Always 1 GK in starting XI
    
    print(f"[TARGET] Formation {actual_formation} requires: {gk_count} GK, {def_count} DEF, {mid_count} MID, {fwd_count} FWD")
    
    # Select starting XI following formation rules
    starting_xi = []
    bench = []
    
    # Group players by position
    gk_players = [p for p in all_players if p['element_type'] == 1]
    def_players = [p for p in all_players if p['element_type'] == 2]
    mid_players = [p for p in all_players if p['element_type'] == 3]
    fwd_players = [p for p in all_players if p['element_type'] == 4]
    
    # Sort each group by predicted points
    gk_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    def_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    mid_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    fwd_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    
    # Prioritize premium players (GBP8m+) for starting XI - same logic as optimization
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
    
    # Select starting XI according to formation - prioritize premium players
    selected_gk = gk_players[:gk_count]  # 1 GK
    selected_def = prioritize_premium_for_starting(def_players, def_count)
    selected_mid = prioritize_premium_for_starting(mid_players, mid_count)
    selected_fwd = prioritize_premium_for_starting(fwd_players, fwd_count)

    starting_xi.extend(selected_gk)
    starting_xi.extend(selected_def)
    starting_xi.extend(selected_mid)
    starting_xi.extend(selected_fwd)
    
    # Validate formation
    is_valid, message = validate_formation(starting_xi)
    if not is_valid:
        print(f"[X] Formation validation failed: {message}")
        return None
    
    print(f"[OK] Formation validation passed: {message}")
    
    # Remaining players go to bench (exclude anyone already in starting XI)
    selected_ids = {id(player) for player in starting_xi}
    for group in (gk_players, def_players, mid_players, fwd_players):
        for player in group:
            if id(player) not in selected_ids:
                bench.append(player)
    
    # Calculate total cost and points
    total_cost = sum(player['now_cost'] for player in all_players) / 10
    total_points = sum(player['predicted_points'] for player in all_players)
    
    # Get captain info if available
    captain_info = squad.get('captain_info')
    total_with_captain = squad.get('total_points_with_captain', total_points)
    
    print(f"[MONEY] Total Cost: GBP{total_cost:.1f}m / GBP100.0m ({total_cost/100*100:.1f}%)")
    print(f"[STATS] Base Predicted Points: {total_points:.1f}")
    
    if captain_info:
        print(f"[CROWN] Captain: {captain_info['name']} (GBP{captain_info['cost']:.1f}m, {captain_info['captain_points']:.1f} pts as captain)")
        print(f"[TREND] Total with Captain Bonus: {total_with_captain:.1f}")
    else:
        print(f"[TREND] Average Points per Player: {total_points/15:.1f}")
    
    print("\n[TARGET] STARTING XI:")
    print("-" * 40)
    for i, player in enumerate(starting_xi, 1):
        cost = player['now_cost'] / 10
        points = player['predicted_points']
        position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        pos = position_map.get(player['element_type'], '?')
        
        # Highlight captain
        captain_marker = "[CROWN]" if captain_info and player['name'] == captain_info['name'] else "  "
        
        print(f"{captain_marker}{i:2d}. {player['name']:<20} {pos} GBP{cost:>5.1f}m {points:>6.1f} pts")
    
    print("\n[BENCH] BENCH:")
    print("-" * 40)
    for i, player in enumerate(bench, 1):
        cost = player['now_cost'] / 10
        points = player['predicted_points']
        position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        pos = position_map.get(player['element_type'], '?')
        print(f"{i:2d}. {player['name']:<20} {pos} GBP{cost:>5.1f}m {points:>6.1f} pts")
    
    # Suggest captain
    captain = suggest_captain(predictions, squad)
    if captain:
        print(f"\n[CROWN] CAPTAIN SUGGESTION: {captain['name']} ({captain['predicted_points']*2:.1f} pts as captain)")
    
    return squad

def save_squad(squad, filename=None):
    """Save the squad to a JSON file for validation."""
    if not squad:
        print("[X] No squad to save")
        return None
        
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"squad_{timestamp}.json"
    
    # Create squads directory if it doesn't exist
    squads_dir = "squads"
    if not os.path.exists(squads_dir):
        os.makedirs(squads_dir)
        print(f"[FOLDER] Created {squads_dir}/ directory")
    
    # Full path for the squad file
    squad_path = os.path.join(squads_dir, filename)
    
    # Determine starting XI vs bench using formation-aware logic
    all_players = []
    for position, players in squad.items():
        if isinstance(players, list):  # Check if it's a list of players
            all_players.extend(players)
        elif position in ['total_cost', 'formation']:  # Skip metadata
            continue
    
    # Parse formation requirements
    formation = squad.get('formation', '4-4-2')
    def_count, mid_count, fwd_count = map(int, formation.split('-'))
    gk_count = 1  # Always 1 GK in starting XI
    
    # Group players by position
    gk_players = [p for p in all_players if p['element_type'] == 1]
    def_players = [p for p in all_players if p['element_type'] == 2]
    mid_players = [p for p in all_players if p['element_type'] == 3]
    fwd_players = [p for p in all_players if p['element_type'] == 4]
    
    # Sort each group by predicted points
    gk_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    def_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    mid_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    fwd_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    
    # Select starting XI according to formation
    selected_gk = gk_players[:gk_count]
    selected_def = def_players[:def_count]
    selected_mid = mid_players[:mid_count]
    selected_fwd = fwd_players[:fwd_count]
    
    starting_xi = []
    starting_xi.extend(selected_gk)  # 1 GK
    starting_xi.extend(selected_def)  # DEF per formation
    starting_xi.extend(selected_mid)  # MID per formation
    starting_xi.extend(selected_fwd)  # FWD per formation
    
    # Remaining players go to bench without duplicating starters
    bench = []
    selected_ids = {id(player) for player in starting_xi}
    for group in (gk_players, def_players, mid_players, fwd_players):
        for player in group:
            if id(player) not in selected_ids:
                bench.append(player)
    
    # Prepare squad data for saving
    squad_data = {
        'timestamp': datetime.now().isoformat(),
        'formation': squad.get('formation', '4-4-2'),
        'total_cost': squad.get('total_cost', 0),
        'players': {},
        'starting_xi': [],
        'bench': [],
        'captain': None,
        'vice_captain': None
    }
    
    # Select captain and vice-captain (top 2 players by predicted points)
    all_squad_players = []
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad:
            all_squad_players.extend(squad[position])
    
    # Sort by predicted points for captain selection
    all_squad_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    
    # Select captain and vice-captain
    if len(all_squad_players) >= 2:
        captain = all_squad_players[0]
        vice_captain = all_squad_players[1]
        
        squad_data['captain'] = {
            'name': captain['name'],
            'cost': captain['now_cost'] / 10,
            'predicted_points': captain['predicted_points'],
            'element_type': captain['element_type']
        }
        
        squad_data['vice_captain'] = {
            'name': vice_captain['name'],
            'cost': vice_captain['now_cost'] / 10,
            'predicted_points': vice_captain['predicted_points'],
            'element_type': vice_captain['element_type']
        }
        
        print(f"[CROWN] Captain: {captain['name']} ({captain['predicted_points']*2:.1f} pts as captain)")
        print(f"[CROWN] Vice-Captain: {vice_captain['name']} ({vice_captain['predicted_points']*2:.1f} pts if captain doesn't play)")
    
    # Add players by position
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad:
            squad_data['players'][position] = []
            for player in squad[position]:
                player_data = {
                    'name': player['name'],
                    'cost': player['now_cost'] / 10,
                    'predicted_points': player['predicted_points'],
                    'element_type': player['element_type']
                }
                squad_data['players'][position].append(player_data)
                
                # Add to starting XI or bench based on predicted points ranking
                if player['name'] in [p['name'] for p in starting_xi]:
                    squad_data['starting_xi'].append(player_data)
                else:
                    squad_data['bench'].append(player_data)
    
    # Save to file
    with open(squad_path, 'w') as f:
        json.dump(squad_data, f, indent=2)
    
    print(f"[OK] Squad saved to {squad_path}")
    print(f"[IDEA] Validate with: python squad_validator.py {squad_path}")
    return squad_path

def suggest_captain(predictions, squad):
    """Suggest captain and vice-captain based on predictions."""
    
    if not squad or not predictions:
        return None
    
    print(f"\n[CROWN] Captain Recommendations:")
    print("-" * 30)
    
    # Get all players in squad
    squad_players = []
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad:
            squad_players.extend(squad[position])
    
    # Sort by predicted points (captain bonus makes expensive players more valuable)
    squad_players.sort(key=lambda x: x['predicted_points'], reverse=True)
    
    print("Top 5 Captain Options:")
    for i, player in enumerate(squad_players[:5], 1):
        name = player['name']
        pred_points = player['predicted_points']
        captain_points = pred_points * 2
        cost = player['now_cost'] / 10
        
        print(f"  {i}. {name:<20} GBP{cost:>5.1f}m {pred_points:>6.1f} pts (Captain: {captain_points:>6.1f} pts)")
    
    return squad_players[0] if squad_players else None

def suggest_transfers(model, current_squad, transfers_available=1):
    """Suggest optimal transfers."""
    
    print(f"\n[REFRESH] Transfer Suggestions ({transfers_available} free transfer{'s' if transfers_available > 1 else ''}):")
    print("-" * 50)
    
    transfer_suggestions = model.suggest_transfers(current_squad, transfers_available)
    
    if not transfer_suggestions or not transfer_suggestions['suggestions']:
        print("  No transfer suggestions available")
        return None
    
    print("Recommended Transfers:")
    for i, transfer in enumerate(transfer_suggestions['suggestions'], 1):
        out_player = transfer['out']
        in_player = transfer['in']
        points_gain = transfer['points_gain']
        cost_change = transfer['cost_change']
        
        print(f"  {i}. {out_player} -> {in_player}")
        print(f"     Points Gain: +{points_gain:.1f}")
        print(f"     Cost Change: GBP{cost_change/10:.1f}m")
    
    print(f"\nExpected Points Gain: +{transfer_suggestions['expected_points_gain']:.1f}")
    
    return transfer_suggestions

def main():
    """Main function to run the FPL model predictions."""
    
    print("[TARGET] FPL Model Squad Selection Tool")
    print("=" * 50)
    
    # Load model and get predictions
    model = load_and_predict()
    predictions = get_predictions(model)
    
    if not predictions:
        print("[X] Could not get predictions")
        return
    
    # Select optimal squad
    squad = select_optimal_squad(model, budget=100.0, formation='4-4-2')
    
    if not squad:
        print("[X] Could not select squad")
        return
    
    # Save squad for validation
    squad_file = save_squad(squad)
    
    # Suggest captain
    captain = suggest_captain(predictions, squad)
    
    # Suggest transfers
    transfers = suggest_transfers(model, squad, transfers_available=1)
    
    print(f"\n[OK] FPL Model Analysis Complete!")
    print(f"[STATS] Use these recommendations to optimize your FPL team!")
    print(f"[SEARCH] Squad saved for validation: {squad_file}")

if __name__ == "__main__":
    main() 
