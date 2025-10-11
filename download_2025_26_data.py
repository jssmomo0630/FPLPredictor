#!/usr/bin/env python3
"""
Download 2025-26 season data from FPL API and save to proper directory structure
"""

import requests
import json
import os
import pandas as pd
from datetime import datetime

def download_2025_26_data():
    """Download 2025-26 season data from FPL API and organize properly"""
    
    # Create 2025-26 season directory
    season_dir = "data/2025-26"
    os.makedirs(season_dir, exist_ok=True)
    os.makedirs(f"{season_dir}/gws", exist_ok=True)
    
    # FPL API endpoint
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    
    print("=== FPL 2025-26 Data Downloader ===")
    print(f"Timestamp: {datetime.now()}")
    print(f"Downloading from: {url}")
    print(f"Saving to: {season_dir}/")
    print()
    
    try:
        # Make request to FPL API
        print("Fetching data from FPL API...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        print(f"Successfully downloaded data!")
        print(f"Data size: {len(response.content) / 1024:.1f} KB")
        
        # Save raw JSON data to 2025-26 folder
        json_path = f"{season_dir}/bootstrap_static.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved raw data to: {json_path}")
        
        # Extract and save key components to 2025-26 folder
        components = {
            'events': data.get('events', []),
            'teams': data.get('teams', []),
            'elements': data.get('elements', []),  # Player data -> players_raw.csv
            'element_types': data.get('element_types', []),  # Position data
            'game_settings': data.get('game_settings', []),
            'phases': data.get('phases', [])
        }
        
        # Save each component as CSV in 2025-26 folder
        for name, component_data in components.items():
            if component_data:
                try:
                    df = pd.DataFrame(component_data)
                    
                    # Special handling for elements -> players_raw.csv
                    if name == 'elements':
                        csv_path = f"{season_dir}/players_raw.csv"
                    else:
                        csv_path = f"{season_dir}/{name}.csv"
                    
                    df.to_csv(csv_path, index=False)
                    print(f"Saved {os.path.basename(csv_path)} with {len(df)} records")
                except Exception as e:
                    print(f"Warning: Could not save {name}.csv: {e}")
                    # Continue with other components
        
        # Print detailed summary
        print("\n=== 2025-26 Season Data Summary ===")
        players = data.get('elements', [])
        teams = data.get('teams', [])
        events = data.get('events', [])
        
        print(f"Total players: {len(players)}")
        print(f"Total teams: {len(teams)}")
        print(f"Total events (gameweeks): {len(events)}")
        
        # Find current gameweek
        current_gw = None
        for event in events:
            if event.get('is_current', False):
                current_gw = event.get('id', 'Unknown')
                break
        
        if current_gw is None:
            # If no current gameweek, find the next upcoming one
            for event in events:
                if event.get('is_next', False):
                    current_gw = f"Next: GW{event.get('id', 'Unknown')}"
                    break
        
        print(f"Current gameweek: {current_gw if current_gw else 'Season not started'}")
        
        # Show player position breakdown
        if players:
            position_counts = {}
            for player in players:
                pos_type = player.get('element_type', 0)
                position_counts[pos_type] = position_counts.get(pos_type, 0) + 1
            
            print(f"\nPlayer breakdown by position:")
            position_names = {1: 'Goalkeepers', 2: 'Defenders', 3: 'Midfielders', 4: 'Forwards'}
            for pos_id, count in sorted(position_counts.items()):
                pos_name = position_names.get(pos_id, f'Position {pos_id}')
                print(f"   {pos_name}: {count}")
        
        # Show some sample players
        if players:
            print(f"\nSample players (top 5 by total points):")
            sorted_players = sorted(players, key=lambda x: x.get('total_points', 0), reverse=True)
            for i, player in enumerate(sorted_players[:5]):
                team_name = "Unknown"
                if teams:
                    team_data = next((t for t in teams if t.get('id') == player.get('team')), None)
                    if team_data:
                        team_name = team_data.get('short_name', 'Unknown')
                
                print(f"   {i+1}. {player.get('web_name', 'Unknown')} ({team_name}) - £{player.get('now_cost', 0)/10:.1f}m - {player.get('total_points', 0)} pts")
        
        print(f"\n2025-26 data successfully saved to: {season_dir}/")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading data: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = download_2025_26_data()
    
    if success:
        print("\nDownload completed successfully!")
        print("The 2025-26 player data is now ready for use with the FPL prediction model.")
    else:
        print("\nDownload failed. Please check your internet connection and try again.")
