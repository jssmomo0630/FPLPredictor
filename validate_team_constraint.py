#!/usr/bin/env python3
"""
Validate Team Constraint Implementation
======================================

This script verifies that the generated squad respects the 
maximum 3 players per team constraint.
"""

import json
import pandas as pd
from collections import Counter

def validate_team_constraint(squad_file):
    """Validate that no team has more than 3 players in the squad."""
    
    print(f"🔍 Validating team constraint for: {squad_file}")
    
    # Load squad data
    with open(squad_file, 'r') as f:
        squad_data = json.load(f)
    
    # Load team mapping
    teams_df = pd.read_csv('data/2025-26/teams.csv')
    team_mapping = dict(zip(teams_df['id'], teams_df['name']))
    
    # Extract all players from squad
    all_players = []
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad_data['players']:
            all_players.extend(squad_data['players'][position])
    
    # Count players by team (if team info is available)
    team_counts = Counter()
    
    print(f"\n📊 Squad Composition by Team:")
    print("=" * 50)
    
    # Note: The saved squad might not have team info, so let's load from model predictions
    # For now, let's verify using the model directly
    
    from fpl_prediction_model import FPLPredictionModel
    
    # Initialize model
    model = FPLPredictionModel()
    model.load_data()
    model.train_position_models()
    
    # Get current predictions with team info
    predictions = model.predict_current_season()
    
    # Create a mapping of player names to teams
    name_to_team = {}
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in predictions:
            for _, player in predictions[position].iterrows():
                name_to_team[player['name']] = player['team']
    
    # Count teams in the actual squad
    team_counts = Counter()
    
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        if position in squad_data['players']:
            for player in squad_data['players'][position]:
                player_name = player['name']
                if player_name in name_to_team:
                    team_id = name_to_team[player_name]
                    team_name = team_mapping.get(team_id, f"Team {team_id}")
                    team_counts[team_name] += 1
                    print(f"  {player_name:<20} {position:<3} -> {team_name}")
                else:
                    print(f"  {player_name:<20} {position:<3} -> Team Unknown")
    
    print(f"\n📈 Team Distribution:")
    print("-" * 30)
    
    constraint_violated = False
    for team, count in team_counts.most_common():
        status = "✅" if count <= 3 else "❌ VIOLATION!"
        print(f"  {team:<15} {count} players {status}")
        if count > 3:
            constraint_violated = True
    
    print(f"\n{'❌ TEAM CONSTRAINT VIOLATED!' if constraint_violated else '✅ TEAM CONSTRAINT SATISFIED!'}")
    print(f"Maximum players per team: 3")
    print(f"Actual maximum: {max(team_counts.values()) if team_counts else 0}")
    
    return not constraint_violated

def main():
    """Main function to validate team constraints."""
    
    # Find the most recent squad file
    import os
    import glob
    
    squad_files = glob.glob('squads/squad_*.json')
    if not squad_files:
        print("❌ No squad files found in squads/ directory")
        return
    
    # Get the most recent squad file
    latest_squad = max(squad_files, key=os.path.getctime)
    
    # Validate team constraint
    is_valid = validate_team_constraint(latest_squad)
    
    if is_valid:
        print(f"\n🎉 Team constraint validation PASSED!")
    else:
        print(f"\n💥 Team constraint validation FAILED!")

if __name__ == "__main__":
    main()