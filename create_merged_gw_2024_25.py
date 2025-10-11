#!/usr/bin/env python3
"""
Create Merged GW Data for 2024-25
=================================

This script merges all individual gameweek files for the 2024-25 season
into a single merged_gw.csv file for analysis.

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import os
import glob

def create_merged_gw_2024_25():
    """Create merged_gw.csv for 2024-25 season."""
    print("🔄 Creating merged_gw.csv for 2024-25 season...")
    
    # Path to gameweek files
    gws_path = "data/2024-25/gws/"
    
    if not os.path.exists(gws_path):
        print(f"❌ Gameweek directory not found: {gws_path}")
        return False
    
    # Get all gameweek files
    gw_files = glob.glob(f"{gws_path}gw*.csv")
    gw_files.sort()  # Sort by filename
    
    if not gw_files:
        print(f"❌ No gameweek files found in {gws_path}")
        return False
    
    print(f"📁 Found {len(gw_files)} gameweek files")
    
    # Load and merge all gameweek data
    all_gw_data = []
    
    for gw_file in gw_files:
        try:
            # Extract gameweek number from filename
            gw_num = int(gw_file.split('gw')[1].split('.')[0])
            
            # Load gameweek data
            gw_data = pd.read_csv(gw_file)
            
            # Add gameweek column if not present
            if 'round' not in gw_data.columns:
                gw_data['round'] = gw_num
            
            print(f"✅ Loaded GW{gw_num}: {len(gw_data)} records")
            all_gw_data.append(gw_data)
            
        except Exception as e:
            print(f"❌ Error loading {gw_file}: {e}")
            continue
    
    if not all_gw_data:
        print("❌ No gameweek data loaded")
        return False
    
    # Merge all gameweek data
    print("🔄 Merging gameweek data...")
    merged_data = pd.concat(all_gw_data, ignore_index=True)
    
    # Sort by gameweek and player
    if 'round' in merged_data.columns and 'name' in merged_data.columns:
        merged_data = merged_data.sort_values(['round', 'name'])
    
    # Save merged data
    output_file = "data/2024-25/merged_gw.csv"
    merged_data.to_csv(output_file, index=False)
    
    print(f"✅ Saved merged data to {output_file}")
    print(f"📊 Total records: {len(merged_data)}")
    print(f"📊 Total gameweeks: {merged_data['round'].nunique()}")
    print(f"📊 Total players: {merged_data['name'].nunique()}")
    
    # Show sample data
    print(f"\n📋 Sample data:")
    print(merged_data.head())
    
    return True

def main():
    """Main function."""
    success = create_merged_gw_2024_25()
    
    if success:
        print(f"\n✅ Successfully created merged_gw.csv for 2024-25 season!")
    else:
        print(f"\n❌ Failed to create merged_gw.csv")

if __name__ == "__main__":
    main() 