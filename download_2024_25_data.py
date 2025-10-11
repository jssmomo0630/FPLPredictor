#!/usr/bin/env python3
"""
Download 2024-25 season data from vaastav's repository
"""

import requests
import pandas as pd
import os
import json
from datetime import datetime

def download_2024_25_data():
    """Download 2024-25 season data from vaastav's repository"""
    
    # Create data directory
    os.makedirs("data", exist_ok=True)
    
    # Base URL for raw files from vaastav's repository
    base_url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
    season = "2024-25"
    
    print(f"Downloading {season} FPL data from vaastav's repository...")
    print(f"Base URL: {base_url}")
    print()
    
    season_dir = f"data/{season}"
    os.makedirs(season_dir, exist_ok=True)
    
    # Download players_raw.csv
    players_url = f"{base_url}/{season}/players_raw.csv"
    try:
        print(f"Downloading players data for {season}...")
        players_df = pd.read_csv(players_url)
        players_df.to_csv(f"{season_dir}/players_raw.csv", index=False)
        print(f"✅ Downloaded {len(players_df)} players for {season}")
        
        # Show sample data
        print(f"\nSample players from {season}:")
        print(f"Total players: {len(players_df)}")
        
        # Show top 5 players by total points
        if 'total_points' in players_df.columns:
            top_players = players_df.nlargest(5, 'total_points')[['web_name', 'team', 'total_points', 'element_type', 'now_cost']]
            print("\nTop 5 players by total points:")
            print(top_players.to_string(index=False))
        
        # Show position distribution
        if 'element_type' in players_df.columns:
            pos_counts = players_df['element_type'].value_counts().sort_index()
            print(f"\nPosition distribution:")
            positions = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
            for pos, count in pos_counts.items():
                pos_name = positions.get(pos, f'Pos{pos}')
                print(f"  {pos_name}: {count}")
        
    except Exception as e:
        print(f"❌ Failed to download players for {season}: {e}")
        return False
    
    # Download merged_gw.csv (all gameweeks in one file)
    merged_gw_url = f"{base_url}/{season}/gws/merged_gw.csv"
    try:
        print(f"\nDownloading merged gameweek data for {season}...")
        merged_df = pd.read_csv(merged_gw_url)
        merged_df.to_csv(f"{season_dir}/merged_gw.csv", index=False)
        print(f"✅ Downloaded {len(merged_df)} gameweek records for {season}")
        
        # Show gameweek info
        if 'round' in merged_df.columns:
            unique_gws = merged_df['round'].unique()
            print(f"Gameweeks available: {sorted(unique_gws)}")
        
    except Exception as e:
        print(f"❌ Failed to download merged gameweek data for {season}: {e}")
    
    # Download individual gameweek files
    gws_dir = f"{season_dir}/gws"
    os.makedirs(gws_dir, exist_ok=True)
    
    # Try to download individual gameweek files (up to 38)
    print(f"\nDownloading individual gameweek files...")
    for gw in range(1, 39):
        gw_url = f"{base_url}/{season}/gws/gw{gw}.csv"
        try:
            gw_df = pd.read_csv(gw_url)
            gw_df.to_csv(f"{gws_dir}/gw{gw}.csv", index=False)
            print(f"  Downloaded GW{gw}: {len(gw_df)} players")
        except:
            # Stop if gameweek doesn't exist
            print(f"  No data for GW{gw} (season may not have started yet)")
            break
    
    print(f"\n✅ Completed {season}")
    
    # Create summary
    create_2024_25_summary(season_dir)
    
    return True

def create_2024_25_summary(season_dir):
    """Create a summary of the 2024-25 data"""
    summary = {
        'download_date': datetime.now().isoformat(),
        'data_source': 'vaastav/Fantasy-Premier-League GitHub repository',
        'season': '2024-25',
        'files': []
    }
    
    # Check what files exist
    if os.path.exists(season_dir):
        for file in os.listdir(season_dir):
            file_path = os.path.join(season_dir, file)
            if file.endswith('.csv'):
                try:
                    df = pd.read_csv(file_path)
                    summary['files'].append({
                        'file': file,
                        'rows': len(df),
                        'columns': len(df.columns)
                    })
                except:
                    pass
    
    # Save summary
    with open(f'{season_dir}/download_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"📊 Data summary created: {season_dir}/download_summary.json")

if __name__ == "__main__":
    print("=== 2024-25 FPL Data Downloader ===")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    success = download_2024_25_data()
    
    if success:
        print("\n✅ 2024-25 download completed successfully!")
        print("You can now use this data for current season predictions.")
    else:
        print("\n❌ Download failed. Please check your internet connection and try again.") 