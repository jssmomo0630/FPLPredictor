#!/usr/bin/env python3
"""
Download Merged GW Data for 2024-25
===================================

This script downloads the merged_gw.csv file for the 2024-25 season
directly from Vaastav's GitHub repository.

Author: FPL Prediction Team
Date: July 2025
"""

import requests
import os

def download_merged_gw_2024_25():
    """Download merged_gw.csv for 2024-25 season from GitHub."""
    print("🔄 Downloading merged_gw.csv for 2024-25 season...")
    
    # GitHub raw URL for the merged_gw.csv file
    url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data/2024-25/gws/merged_gw.csv"
    
    # Output file path
    output_file = "data/2024-25/merged_gw.csv"
    
    try:
        # Download the file
        print(f"📥 Downloading from: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Save the file
        with open(output_file, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ Successfully downloaded merged_gw.csv")
        print(f"📁 Saved to: {output_file}")
        print(f"📊 File size: {len(response.content):,} bytes")
        
        # Show first few lines to verify the data
        print(f"\n📋 First few lines of the file:")
        lines = response.text.split('\n')[:5]
        for i, line in enumerate(lines, 1):
            print(f"  {i}: {line}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Download failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        return False

def main():
    """Main function."""
    success = download_merged_gw_2024_25()
    
    if success:
        print(f"\n✅ Successfully downloaded merged_gw.csv for 2024-25 season!")
        print(f"🎯 You can now use this data for player matching analysis.")
    else:
        print(f"\n❌ Failed to download merged_gw.csv")

if __name__ == "__main__":
    main() 