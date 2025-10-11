#!/usr/bin/env python3
"""
Download individual gameweek data for 2025-26 season from FPL API
"""

import requests
import json
import os
import pandas as pd
from datetime import datetime

def download_gameweek_data(gameweek_number, season_dir="data/2025-26"):
    """Download data for a specific gameweek from FPL API"""
    
    # Create gws directory if it doesn't exist
    gws_dir = f"{season_dir}/gws"
    os.makedirs(gws_dir, exist_ok=True)
    
    # FPL API endpoint for gameweek live data
    url = f"https://fantasy.premierleague.com/api/event/{gameweek_number}/live/"
    
    print(f"Downloading Gameweek {gameweek_number} data...")
    print(f"URL: {url}")
    
    try:
        # Make request to FPL API
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        print(f"Successfully downloaded GW{gameweek_number} data!")
        print(f"Data size: {len(response.content) / 1024:.1f} KB")
        
        # Save raw JSON data
        json_path = f"{gws_dir}/gw{gameweek_number}_live.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved raw data to: {json_path}")
        
        # Extract player performance data
        elements = data.get('elements', [])
        
        if elements:
            # Convert to DataFrame
            df = pd.DataFrame(elements)
            
            # Add gameweek identifier
            df['gameweek'] = gameweek_number
            df['season'] = '2025-26'
            
            # Save as CSV
            csv_path = f"{gws_dir}/gw{gameweek_number}.csv"
            df.to_csv(csv_path, index=False)
            print(f"Saved CSV data to: {csv_path} ({len(df)} players)")
            
            # Show sample of the data
            if len(df) > 0:
                print(f"Sample columns: {list(df.columns[:10])}")
                # Check if total_points column exists and show count
                if 'total_points' in df.columns:
                    players_with_points = len(df[df['total_points'] > 0])
                    print(f"Players with points: {players_with_points}")
                else:
                    print("Note: total_points column not found in gameweek data")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading GW{gameweek_number} data: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON for GW{gameweek_number}: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error for GW{gameweek_number}: {e}")
        return False

def download_multiple_gameweeks(gameweeks, season_dir="data/2025-26"):
    """Download data for multiple gameweeks"""
    
    print("=== FPL 2025-26 Gameweek Data Downloader ===")
    print(f"Timestamp: {datetime.now()}")
    print(f"Downloading gameweeks: {gameweeks}")
    print(f"Saving to: {season_dir}/gws/")
    print()
    
    successful_downloads = []
    failed_downloads = []
    
    for gw in gameweeks:
        print(f"\n--- Gameweek {gw} ---")
        success = download_gameweek_data(gw, season_dir)
        
        if success:
            successful_downloads.append(gw)
        else:
            failed_downloads.append(gw)
    
    # Summary
    print(f"\n=== Download Summary ===")
    print(f"Successfully downloaded: {len(successful_downloads)} gameweeks")
    if successful_downloads:
        print(f"  Gameweeks: {successful_downloads}")
    
    if failed_downloads:
        print(f"Failed downloads: {len(failed_downloads)} gameweeks")
        print(f"  Gameweeks: {failed_downloads}")
    
    return successful_downloads, failed_downloads

def create_merged_gw_file(gameweeks, season_dir="data/2025-26"):
    """Create a merged gameweek file combining all downloaded gameweeks"""
    
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
        
        return merged_path
    else:
        print("No data to merge")
        return None

if __name__ == "__main__":
    # Check current season status to determine which gameweeks to download
    print("Checking current season status...")
    try:
        import requests
        response = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/')
        data = response.json()
        events = data['events']
        
        # Find finished and current gameweeks
        finished_gws = [e['id'] for e in events if e.get('finished')]
        current_gw = next((e['id'] for e in events if e.get('is_current')), None)
        
        # Download all finished gameweeks plus current one
        gameweeks_to_download = finished_gws.copy()
        if current_gw and current_gw not in gameweeks_to_download:
            gameweeks_to_download.append(current_gw)
        
        gameweeks_to_download = sorted(gameweeks_to_download)
        
        print(f"Finished gameweeks: {finished_gws}")
        print(f"Current gameweek: {current_gw}")
        print(f"Will download gameweeks: {gameweeks_to_download}")
        
    except Exception as e:
        print(f"Error checking season status: {e}")
        print("Falling back to downloading gameweeks 1-6")
        gameweeks_to_download = [1, 2, 3, 4, 5, 6]
    
    successful, failed = download_multiple_gameweeks(gameweeks_to_download)
    
    if successful:
        # Create merged file
        merged_file = create_merged_gw_file(successful)
        
        print(f"\nDownload completed!")
        print(f"Successfully downloaded {len(successful)} gameweeks")
        print("The 2025-26 gameweek data is now ready for analysis.")
    else:
        print(f"\nNo gameweeks were successfully downloaded.")
        print("Please check your internet connection and try again.")
