#!/usr/bin/env python3
"""
Process downloaded 2025-26 gameweek data to flatten the nested stats structure
"""

import json
import pandas as pd
import os
from datetime import datetime

def process_gameweek_data(gameweek_number, season_dir="data/2025-26"):
    """Process a gameweek JSON file to create properly formatted CSV"""
    
    gws_dir = f"{season_dir}/gws"
    json_path = f"{gws_dir}/gw{gameweek_number}_live.json"
    csv_path = f"{gws_dir}/gw{gameweek_number}.csv"
    
    if not os.path.exists(json_path):
        print(f"JSON file not found: {json_path}")
        return False
    
    print(f"Processing Gameweek {gameweek_number}...")
    
    try:
        # Load JSON data
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        elements = data.get('elements', [])
        print(f"Found {len(elements)} players in GW{gameweek_number}")
        
        # Process each player
        processed_players = []
        
        for element in elements:
            player_data = {
                'element': element.get('id'),  # Player ID
                'gameweek': gameweek_number,
                'season': '2025-26'
            }
            
            # Flatten the stats dictionary
            stats = element.get('stats', {})
            for stat_key, stat_value in stats.items():
                player_data[stat_key] = stat_value
            
            # Add other fields
            player_data['explain'] = str(element.get('explain', ''))
            player_data['modified'] = element.get('modified', '')
            
            processed_players.append(player_data)
        
        # Create DataFrame
        df = pd.DataFrame(processed_players)
        
        # Ensure we have the key columns
        if 'total_points' not in df.columns:
            df['total_points'] = 0
        
        # Save processed CSV
        df.to_csv(csv_path, index=False)
        print(f"Saved processed data to: {csv_path}")
        print(f"Columns: {list(df.columns)}")
        
        # Show summary statistics
        if 'total_points' in df.columns:
            total_points = df['total_points'].sum()
            players_with_points = len(df[df['total_points'] > 0])
            print(f"Total points in GW{gameweek_number}: {total_points}")
            print(f"Players with points: {players_with_points}")
            
            # Show top performers
            if players_with_points > 0:
                top_performers = df.nlargest(5, 'total_points')[['element', 'total_points', 'minutes', 'goals_scored', 'assists']]
                print(f"Top 5 performers in GW{gameweek_number}:")
                for _, player in top_performers.iterrows():
                    print(f"  Player {player['element']}: {player['total_points']} pts ({player.get('minutes', 0)} mins, {player.get('goals_scored', 0)} goals, {player.get('assists', 0)} assists)")
        
        return True
        
    except Exception as e:
        print(f"Error processing GW{gameweek_number}: {e}")
        return False

def process_all_downloaded_gameweeks(season_dir="data/2025-26"):
    """Process all downloaded gameweek JSON files"""
    
    print("=== Processing 2025-26 Gameweek Data ===")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    gws_dir = f"{season_dir}/gws"
    
    # Find all JSON files
    json_files = []
    if os.path.exists(gws_dir):
        for file in os.listdir(gws_dir):
            if file.endswith('_live.json'):
                gw_num = file.replace('gw', '').replace('_live.json', '')
                try:
                    json_files.append(int(gw_num))
                except ValueError:
                    pass
    
    json_files.sort()
    print(f"Found gameweek JSON files for: {json_files}")
    
    successful_processing = []
    failed_processing = []
    
    for gw in json_files:
        success = process_gameweek_data(gw, season_dir)
        if success:
            successful_processing.append(gw)
        else:
            failed_processing.append(gw)
        print()
    
    print(f"=== Processing Summary ===")
    print(f"Successfully processed: {len(successful_processing)} gameweeks")
    if successful_processing:
        print(f"  Gameweeks: {successful_processing}")
    
    if failed_processing:
        print(f"Failed processing: {len(failed_processing)} gameweeks")
        print(f"  Gameweeks: {failed_processing}")
    
    return successful_processing

def create_merged_gw_file(gameweeks, season_dir="data/2025-26"):
    """Create a merged gameweek file combining all processed gameweeks"""
    
    print(f"\nCreating merged gameweek file...")
    
    all_data = []
    gws_dir = f"{season_dir}/gws"
    
    for gw in gameweeks:
        csv_path = f"{gws_dir}/gw{gw}.csv"
        
        try:
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                all_data.append(df)
                print(f"  Added GW{gw}: {len(df)} records")
            else:
                print(f"  Warning: GW{gw}.csv not found")
        except Exception as e:
            print(f"  Error reading GW{gw}: {e}")
    
    if all_data:
        # Combine all gameweek data
        merged_df = pd.concat(all_data, ignore_index=True)
        
        # Save merged file
        merged_path = f"{season_dir}/merged_gw.csv"
        merged_df.to_csv(merged_path, index=False)
        
        print(f"Created merged file: {merged_path}")
        print(f"Total records: {len(merged_df)}")
        print(f"Gameweeks included: {sorted(merged_df['gameweek'].unique())}")
        print(f"Columns: {list(merged_df.columns)}")
        
        return merged_path
    else:
        print("No data to merge")
        return None

if __name__ == "__main__":
    # Process all downloaded gameweeks
    processed_gws = process_all_downloaded_gameweeks()
    
    if processed_gws:
        # Create merged file
        merged_file = create_merged_gw_file(processed_gws)
        
        print(f"\nProcessing completed!")
        print(f"Successfully processed {len(processed_gws)} gameweeks")
        print("The 2025-26 gameweek data is now properly formatted for analysis.")
    else:
        print(f"\nNo gameweeks were successfully processed.")
        print("Please ensure JSON files are downloaded first.")

