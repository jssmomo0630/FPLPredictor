#!/usr/bin/env python3
"""
Clean and Download All FPL Data
===============================

This script cleans all existing data and downloads fresh FPL data
from Vaastav's GitHub repository for seasons 2020-2025.

Author: FPL Prediction Team
Date: July 2025
"""

import os
import shutil
import requests
import pandas as pd
from datetime import datetime

def clean_data_folder():
    """Clean all existing data folders for 2020-2025 seasons."""
    print("🧹 Cleaning existing data folders...")
    
    seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25']
    
    for season in seasons:
        season_path = f"data/{season}"
        if os.path.exists(season_path):
            try:
                shutil.rmtree(season_path)
                print(f"✅ Cleaned {season}")
            except Exception as e:
                print(f"❌ Error cleaning {season}: {e}")
        else:
            print(f"ℹ️ {season} folder not found (already clean)")

def download_season_data(season):
    """Download data for a specific season from Vaastav's repository."""
    print(f"\n🔄 Downloading {season} season data...")
    
    base_url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
    season_path = f"data/{season}"
    
    # Create season directory
    os.makedirs(season_path, exist_ok=True)
    
    # Files to download
    files_to_download = [
        f"{base_url}/{season}/players_raw.csv",
        f"{base_url}/{season}/gws/merged_gw.csv"
    ]
    
    downloaded_files = []
    
    for url in files_to_download:
        try:
            # Extract filename from URL
            filename = url.split('/')[-1]
            file_path = f"{season_path}/{filename}"
            
            print(f"📥 Downloading {filename}...")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            print(f"✅ Downloaded {filename} ({len(response.content):,} bytes)")
            downloaded_files.append(filename)
            
        except Exception as e:
            print(f"❌ Error downloading {url}: {e}")
    
    return downloaded_files

def download_all_seasons():
    """Download data for all seasons 2020-2025."""
    print("🚀 Starting download of all seasons...")
    
    seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25']
    results = {}
    
    for season in seasons:
        try:
            files = download_season_data(season)
            results[season] = files
        except Exception as e:
            print(f"❌ Error processing {season}: {e}")
            results[season] = []
    
    return results

def verify_downloads(results):
    """Verify that all downloads were successful."""
    print("\n🔍 Verifying downloads...")
    
    total_files = 0
    successful_files = 0
    
    for season, files in results.items():
        print(f"\n📊 {season}:")
        if files:
            for file in files:
                file_path = f"data/{season}/{file}"
                if os.path.exists(file_path):
                    size = os.path.getsize(file_path)
                    print(f"  ✅ {file} ({size:,} bytes)")
                    successful_files += 1
                else:
                    print(f"  ❌ {file} (missing)")
                total_files += 1
        else:
            print(f"  ❌ No files downloaded")
    
    print(f"\n📈 SUMMARY:")
    print(f"Total files expected: {total_files}")
    print(f"Successfully downloaded: {successful_files}")
    print(f"Success rate: {(successful_files/total_files)*100:.1f}%" if total_files > 0 else "0%")
    
    return successful_files == total_files

def show_data_summary():
    """Show a summary of the downloaded data."""
    print("\n📋 DATA SUMMARY:")
    print("=" * 50)
    
    seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25']
    
    for season in seasons:
        season_path = f"data/{season}"
        if os.path.exists(season_path):
            print(f"\n{season}:")
            
            # Check players_raw.csv
            players_file = f"{season_path}/players_raw.csv"
            if os.path.exists(players_file):
                try:
                    players_df = pd.read_csv(players_file)
                    print(f"  📊 Players: {len(players_df)}")
                except:
                    print(f"  ❌ Players file corrupted")
            
            # Check merged_gw.csv
            merged_file = f"{season_path}/merged_gw.csv"
            if os.path.exists(merged_file):
                try:
                    merged_df = pd.read_csv(merged_file)
                    print(f"  📊 Gameweek records: {len(merged_df):,}")
                    print(f"  📊 Unique players: {merged_df['name'].nunique()}")
                    print(f"  📊 Gameweeks: {merged_df['round'].nunique()}")
                except:
                    print(f"  ❌ Merged GW file corrupted")

def main():
    """Main function."""
    print("🧹 FPL Data Clean and Download")
    print("=" * 40)
    print(f"Timestamp: {datetime.now()}")
    
    # Step 1: Clean existing data
    clean_data_folder()
    
    # Step 2: Download all seasons
    results = download_all_seasons()
    
    # Step 3: Verify downloads
    success = verify_downloads(results)
    
    # Step 4: Show data summary
    show_data_summary()
    
    if success:
        print(f"\n✅ All data downloaded successfully!")
        print(f"🎯 You can now run player matching analysis and hybrid squad generation.")
    else:
        print(f"\n⚠️ Some downloads failed. Check the output above for details.")

if __name__ == "__main__":
    main() 