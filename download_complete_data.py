#!/usr/bin/env python3
"""
Download Complete FPL Data
==========================

This script downloads complete FPL data from Vaastav's repository including:
- players_raw.csv
- merged_gw.csv
- Individual gameweek files (gw1.csv, gw2.csv, etc.)

Author: FPL Prediction Team
Date: July 2025
"""

import os
import shutil
import requests
import pandas as pd
from datetime import datetime

def delete_existing_data():
    """Delete existing data folders."""
    print("🗑️ Deleting existing data...")
    
    seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25']
    
    for season in seasons:
        season_path = f"data/{season}"
        if os.path.exists(season_path):
            try:
                shutil.rmtree(season_path)
                print(f"✅ Deleted {season} folder")
            except Exception as e:
                print(f"❌ Error deleting {season}: {e}")

def download_season_data(season):
    """Download complete data for a specific season."""
    print(f"\n🔄 Downloading {season} season data...")
    
    base_url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
    season_path = f"data/{season}"
    
    # Create season directory and gws subdirectory
    os.makedirs(season_path, exist_ok=True)
    os.makedirs(f"{season_path}/gws", exist_ok=True)
    
    downloaded_files = []
    
    # Download players_raw.csv
    try:
        url = f"{base_url}/{season}/players_raw.csv"
        file_path = f"{season_path}/players_raw.csv"
        
        print(f"📥 Downloading players_raw.csv...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ Downloaded players_raw.csv ({len(response.content):,} bytes)")
        downloaded_files.append("players_raw.csv")
        
    except Exception as e:
        print(f"❌ Error downloading players_raw.csv: {e}")
    
    # Download merged_gw.csv
    try:
        url = f"{base_url}/{season}/gws/merged_gw.csv"
        file_path = f"{season_path}/merged_gw.csv"
        
        print(f"📥 Downloading merged_gw.csv...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ Downloaded merged_gw.csv ({len(response.content):,} bytes)")
        downloaded_files.append("merged_gw.csv")
        
    except Exception as e:
        print(f"❌ Error downloading merged_gw.csv: {e}")
    
    # Download individual gameweek files (gw1.csv to gw38.csv)
    print(f"📥 Downloading individual gameweek files...")
    gw_files_downloaded = 0
    
    for gw_num in range(1, 39):  # GW1 to GW38
        try:
            url = f"{base_url}/{season}/gws/gw{gw_num}.csv"
            file_path = f"{season_path}/gws/gw{gw_num}.csv"
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            gw_files_downloaded += 1
            
            # Show progress every 10 gameweeks
            if gw_num % 10 == 0:
                print(f"  ✅ Downloaded GW{gw_num} ({len(response.content):,} bytes)")
                
        except Exception as e:
            # Some seasons might not have all 38 gameweeks
            if gw_num <= 30:  # Only show error for first 30 gameweeks
                print(f"  ⚠️ GW{gw_num} not available")
            break
    
    print(f"✅ Downloaded {gw_files_downloaded} gameweek files")
    downloaded_files.append(f"{gw_files_downloaded} gameweek files")
    
    return downloaded_files

def download_all_seasons():
    """Download complete data for all seasons."""
    print("🚀 Starting complete download of all seasons...")
    
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
    
    for season, files in results.items():
        print(f"\n📊 {season}:")
        season_path = f"data/{season}"
        
        if os.path.exists(season_path):
            # Check players_raw.csv
            players_file = f"{season_path}/players_raw.csv"
            if os.path.exists(players_file):
                size = os.path.getsize(players_file)
                print(f"  ✅ players_raw.csv ({size:,} bytes)")
            
            # Check merged_gw.csv
            merged_file = f"{season_path}/merged_gw.csv"
            if os.path.exists(merged_file):
                size = os.path.getsize(merged_file)
                print(f"  ✅ merged_gw.csv ({size:,} bytes)")
            
            # Check gameweek files
            gws_path = f"{season_path}/gws"
            if os.path.exists(gws_path):
                gw_files = [f for f in os.listdir(gws_path) if f.startswith('gw') and f.endswith('.csv')]
                print(f"  ✅ {len(gw_files)} gameweek files")
                
                # Show some examples
                if gw_files:
                    gw_files.sort()
                    print(f"    Examples: {gw_files[0]} to {gw_files[-1]}")

def show_data_summary():
    """Show a comprehensive summary of the downloaded data."""
    print("\n📋 COMPLETE DATA SUMMARY:")
    print("=" * 60)
    
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
            
            # Check individual gameweek files
            gws_path = f"{season_path}/gws"
            if os.path.exists(gws_path):
                gw_files = [f for f in os.listdir(gws_path) if f.startswith('gw') and f.endswith('.csv')]
                print(f"  📊 Individual GW files: {len(gw_files)}")
                
                # Show sample of first few gameweeks
                if gw_files:
                    gw_files.sort()
                    sample_files = gw_files[:5]
                    print(f"    Sample: {', '.join(sample_files)}")

def main():
    """Main function."""
    print("📥 Complete FPL Data Download")
    print("=" * 40)
    print(f"Timestamp: {datetime.now()}")
    
    # Step 1: Delete existing data
    delete_existing_data()
    
    # Step 2: Download all seasons with complete data
    results = download_all_seasons()
    
    # Step 3: Verify downloads
    verify_downloads(results)
    
    # Step 4: Show comprehensive data summary
    show_data_summary()
    
    print(f"\n✅ Complete data download finished!")
    print(f"🎯 You now have:")
    print(f"   - players_raw.csv for each season")
    print(f"   - merged_gw.csv for each season")
    print(f"   - Individual gameweek files (gw1.csv, gw2.csv, etc.)")
    print(f"   - Ready for player matching analysis and squad generation")

if __name__ == "__main__":
    main() 