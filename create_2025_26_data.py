#!/usr/bin/env python3
"""
Create 2025-26 Season Data Structure
===================================

This script creates the data structure for the 2025-26 season using
the current FPL API data. It generates:
- merged_gw.csv with current player data
- Individual gameweek files (gw1.csv, gw2.csv, etc.)
- Summary files

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import os
import json
from datetime import datetime

def create_2025_26_data():
    """Create 2025-26 season data structure."""
    
    print("🔄 Creating 2025-26 season data structure...")
    
    # Load current player data
    players_file = "data/2025-26/players_raw.csv"
    if not os.path.exists(players_file):
        print(f"❌ Players file not found: {players_file}")
        return False
    
    players_df = pd.read_csv(players_file)
    print(f"✅ Loaded {len(players_df)} players")
    
    # Load events data
    events_file = "data/2025-26/events.csv"
    if not os.path.exists(events_file):
        print(f"❌ Events file not found: {events_file}")
        return False
    
    events_df = pd.read_csv(events_file)
    print(f"✅ Loaded {len(events_df)} events")
    
    # Create merged_gw.csv structure
    print("📊 Creating merged_gw.csv...")
    
    # Initialize merged data
    merged_data = []
    
    # For each gameweek, create player records
    for _, event in events_df.iterrows():
        gw_number = event['id']
        gw_name = event['name']
        
        print(f"  Processing {gw_name}...")
        
        # Create a record for each player for this gameweek
        for _, player in players_df.iterrows():
            # Create gameweek record
            gw_record = {
                'name': player['web_name'],
                'position': get_position_name(player['element_type']),
                'team': get_team_name(player['team']),
                'round': gw_number,
                'total_points': 0,  # Will be updated when actual data is available
                'minutes': 0,
                'goals_scored': 0,
                'assists': 0,
                'clean_sheets': 0,
                'goals_conceded': 0,
                'own_goals': 0,
                'penalties_saved': 0,
                'penalties_missed': 0,
                'yellow_cards': 0,
                'red_cards': 0,
                'saves': 0,
                'bonus': 0,
                'bps': 0,
                'influence': 0,
                'creativity': 0,
                'threat': 0,
                'ict_index': 0,
                'starts': 0,
                'expected_goals': 0,
                'expected_assists': 0,
                'expected_goal_involvements': 0,
                'expected_goals_conceded': 0,
                'value': player['now_cost'] / 10,
                'transfers_balance': 0,
                'selected': 0,
                'transfers_in': 0,
                'transfers_out': 0
            }
            
            merged_data.append(gw_record)
    
    # Create merged_gw.csv
    merged_df = pd.DataFrame(merged_data)
    merged_file = "data/2025-26/merged_gw.csv"
    merged_df.to_csv(merged_file, index=False)
    print(f"✅ Created {merged_file} with {len(merged_df)} records")
    
    # Create individual gameweek files
    print("📁 Creating individual gameweek files...")
    gws_dir = "data/2025-26/gws"
    
    for gw_number in range(1, 39):  # GW1 to GW38
        gw_data = merged_df[merged_df['round'] == gw_number]
        if len(gw_data) > 0:
            gw_file = f"{gws_dir}/gw{gw_number}.csv"
            gw_data.to_csv(gw_file, index=False)
            print(f"  Created {gw_file} with {len(gw_data)} players")
    
    # Create summary file
    create_summary_file(players_df, events_df)
    
    print("✅ 2025-26 season data structure created successfully!")
    return True

def get_position_name(element_type):
    """Get position name from element type."""
    position_map = {
        1: 'GK',
        2: 'DEF', 
        3: 'MID',
        4: 'FWD'
    }
    return position_map.get(element_type, 'UNK')

def get_team_name(team_id):
    """Get team name from team ID."""
    teams_file = "data/2025-26/teams.csv"
    if os.path.exists(teams_file):
        teams_df = pd.read_csv(teams_file)
        team = teams_df[teams_df['id'] == team_id]
        if len(team) > 0:
            return team.iloc[0]['name']
    return f"Team_{team_id}"

def create_summary_file(players_df, events_df):
    """Create a summary file for the 2025-26 season."""
    print("📋 Creating summary file...")
    
    summary = {
        'season': '2025-26',
        'created_at': datetime.now().isoformat(),
        'total_players': len(players_df),
        'total_gameweeks': len(events_df),
        'player_positions': players_df['element_type'].value_counts().to_dict(),
        'teams': players_df['team'].value_counts().to_dict(),
        'gameweeks': events_df[['id', 'name', 'deadline_time']].to_dict('records')
    }
    
    summary_file = "data/2025-26/summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✅ Created {summary_file}")

def main():
    """Main function."""
    print("🎯 2025-26 Season Data Creator")
    print("=" * 50)
    
    if create_2025_26_data():
        print("\n✅ Successfully created 2025-26 season data structure!")
        print("📁 Files created:")
        print("  - data/2025-26/merged_gw.csv")
        print("  - data/2025-26/gws/gw1.csv to gw38.csv")
        print("  - data/2025-26/summary.json")
        print("\n🔍 You can now use this data with the hybrid squad generator!")
    else:
        print("\n❌ Failed to create 2025-26 season data structure")

if __name__ == "__main__":
    main() 