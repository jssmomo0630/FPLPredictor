#!/usr/bin/env python3
"""
Download FPL data from vaastav's GitHub repository
https://github.com/vaastav/Fantasy-Premier-League
"""

import requests
import pandas as pd
import os
import json
from datetime import datetime

def download_vaastav_data():
    """Download data from vaastav's FPL repository"""
    
    # Create data directory
    os.makedirs("data", exist_ok=True)
    
    # Base URL for raw files from vaastav's repository
    base_url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
    
    # Seasons to download (recent seasons)
    seasons = ["2020-21", "2021-22", "2022-23", "2023-24"]
    
    print("Downloading FPL data from vaastav's repository...")
    print(f"Base URL: {base_url}")
    print()
    
    total_downloaded = 0
    
    for season in seasons:
        print(f"=== Processing {season} ===")
        season_dir = f"data/{season}"
        os.makedirs(season_dir, exist_ok=True)
        
        # Download players_raw.csv
        players_url = f"{base_url}/{season}/players_raw.csv"
        try:
            print(f"Downloading players data for {season}...")
            players_df = pd.read_csv(players_url)
            players_df.to_csv(f"{season_dir}/players_raw.csv", index=False)
            print(f"✅ Downloaded {len(players_df)} players for {season}")
            total_downloaded += len(players_df)
        except Exception as e:
            print(f"❌ Failed to download players for {season}: {e}")
            continue
        
        # Download merged_gw.csv (all gameweeks in one file)
        merged_gw_url = f"{base_url}/{season}/gws/merged_gw.csv"
        try:
            print(f"Downloading merged gameweek data for {season}...")
            merged_df = pd.read_csv(merged_gw_url)
            merged_df.to_csv(f"{season_dir}/merged_gw.csv", index=False)
            print(f"✅ Downloaded {len(merged_df)} gameweek records for {season}")
        except Exception as e:
            print(f"❌ Failed to download merged gameweek data for {season}: {e}")
        
        # Download individual gameweek files
        gws_dir = f"{season_dir}/gws"
        os.makedirs(gws_dir, exist_ok=True)
        
        # Try to download individual gameweek files (up to 38)
        for gw in range(1, 39):
            gw_url = f"{base_url}/{season}/gws/gw{gw}.csv"
            try:
                gw_df = pd.read_csv(gw_url)
                gw_df.to_csv(f"{gws_dir}/gw{gw}.csv", index=False)
                print(f"  Downloaded GW{gw}: {len(gw_df)} players")
            except:
                # Stop if gameweek doesn't exist
                break
        
        print(f"✅ Completed {season}")
        print()
    
    # Create a summary of downloaded data
    create_data_summary()
    
    print(f"=== Download Complete ===")
    print(f"Total players downloaded: {total_downloaded}")
    print(f"Data saved to: data/")
    
    return True

def create_data_summary():
    """Create a summary of the downloaded data"""
    summary = {
        'download_date': datetime.now().isoformat(),
        'data_source': 'vaastav/Fantasy-Premier-League GitHub repository',
        'seasons': [],
        'total_players': 0
    }
    
    # Scan downloaded data
    for season in ["2020-21", "2021-22", "2022-23", "2023-24"]:
        season_dir = f"data/{season}"
        if os.path.exists(season_dir):
            season_info = {
                'season': season,
                'files': []
            }
            
            # Check what files exist
            for file in os.listdir(season_dir):
                file_path = os.path.join(season_dir, file)
                if file.endswith('.csv'):
                    try:
                        df = pd.read_csv(file_path)
                        season_info['files'].append({
                            'file': file,
                            'rows': len(df),
                            'columns': len(df.columns)
                        })
                    except:
                        pass
            
            summary['seasons'].append(season_info)
    
    # Save summary
    with open('data/download_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("📊 Data summary created: data/download_summary.json")

def show_sample_data():
    """Show sample of downloaded data"""
    print("\n=== Sample Data ===")
    
    # Try to load the most recent season
    for season in ["2023-24", "2022-23", "2021-22", "2020-21"]:
        players_file = f"data/{season}/players_raw.csv"
        if os.path.exists(players_file):
            try:
                df = pd.read_csv(players_file)
                print(f"\n{season} - Sample Players:")
                print(f"Total players: {len(df)}")
                
                # Show top 5 players by total points
                if 'total_points' in df.columns:
                    top_players = df.nlargest(5, 'total_points')[['name', 'team', 'total_points', 'element_type']]
                    print(top_players.to_string(index=False))
                
                # Show position distribution
                if 'element_type' in df.columns:
                    pos_counts = df['element_type'].value_counts().sort_index()
                    print(f"\nPosition distribution:")
                    positions = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
                    for pos, count in pos_counts.items():
                        pos_name = positions.get(pos, f'Pos{pos}')
                        print(f"  {pos_name}: {count}")
                
                break
            except Exception as e:
                print(f"Error reading {season} data: {e}")
                continue

if __name__ == "__main__":
    print("=== FPL Data Downloader (vaastav repository) ===")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    success = download_vaastav_data()
    
    if success:
        print("\n✅ Download completed successfully!")
        show_sample_data()
        print("\nYou can now run the prediction model with this data.")
    else:
        print("\n❌ Download failed. Please check your internet connection and try again.") 