#!/usr/bin/env python3
"""
Simple script to download bootstrap data from official FPL API
"""

import requests
import json
import os
from datetime import datetime

def download_bootstrap_data():
    """Download bootstrap static data from FPL API"""
    
    # Create data directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    # FPL API endpoint
    url = "https://fantasy.premierleague.com/api/bootstrap-static/"
    
    print("Downloading bootstrap data from FPL API...")
    print(f"URL: {url}")
    
    try:
        # Make request to FPL API
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Parse JSON response
        data = response.json()
        
        print(f"Successfully downloaded data!")
        print(f"Data size: {len(response.content) / 1024:.1f} KB")
        
        # Save raw JSON data
        with open("data/bootstrap_static.json", "w") as f:
            json.dump(data, f, indent=2)
        print("Saved raw data to: data/bootstrap_static.json")
        
        # Extract and save key components
        components = {
            'events': data.get('events', []),
            'teams': data.get('teams', []),
            'elements': data.get('elements', []),  # Player data
            'element_types': data.get('element_types', []),  # Position data
            'game_settings': data.get('game_settings', []),
            'phases': data.get('phases', [])
        }
        
        # Save each component as CSV
        for name, component_data in components.items():
            if component_data:
                import pandas as pd
                df = pd.DataFrame(component_data)
                df.to_csv(f"data/{name}.csv", index=False)
                print(f"Saved {name}.csv with {len(df)} records")
        
        # Print summary
        print("\n=== Data Summary ===")
        print(f"Total players: {len(data.get('elements', []))}")
        print(f"Total teams: {len(data.get('teams', []))}")
        print(f"Total events (gameweeks): {len(data.get('events', []))}")
        print(f"Current gameweek: {data.get('events', [{}])[-1].get('id', 'N/A') if data.get('events') else 'N/A'}")
        
        # Show some player examples
        elements = data.get('elements', [])
        if elements:
            print(f"\n=== Sample Players ===")
            for i, player in enumerate(elements[:5]):
                print(f"{i+1}. {player.get('web_name', 'Unknown')} - {player.get('team', 'Unknown')} - {player.get('total_points', 0)} points")
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading data: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

if __name__ == "__main__":
    print("=== FPL Bootstrap Data Downloader ===")
    print(f"Timestamp: {datetime.now()}")
    print()
    
    data = download_bootstrap_data()
    
    if data:
        print("\n✅ Download completed successfully!")
        print("You can now run the prediction model with this fresh data.")
    else:
        print("\n❌ Download failed. Please check your internet connection and try again.") 