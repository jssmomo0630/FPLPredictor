#!/usr/bin/env python3
"""
Fantasy Premier League Data Collector
Downloads data from official FPL API and other trusted sources
"""

import requests
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FPLDataCollector:
    def __init__(self):
        self.base_url = "https://fantasy.premierleague.com/api"
        self.data_dir = "data"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Create data directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)
        
    def get_bootstrap_static(self):
        """Get complete static data from FPL API"""
        try:
            url = f"{self.base_url}/bootstrap-static/"
            logger.info("Fetching bootstrap static data...")
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Save raw JSON
            with open(f"{self.data_dir}/bootstrap_static.json", 'w') as f:
                json.dump(data, f, indent=2)
            
            # Extract and save individual components
            components = {
                'events': data.get('events', []),
                'game_settings': data.get('game_settings', []),
                'phases': data.get('phases', []),
                'teams': data.get('teams', []),
                'total_players': data.get('total_players', 0),
                'elements': data.get('elements', [])  # Player data
            }
            
            for name, component_data in components.items():
                if component_data:
                    df = pd.DataFrame(component_data)
                    df.to_csv(f"{self.data_dir}/{name}.csv", index=False)
                    logger.info(f"Saved {name}.csv with {len(df)} records")
            
            return data
            
        except Exception as e:
            logger.error(f"Error fetching bootstrap static data: {e}")
            return None
    
    def get_player_details(self, player_id):
        """Get detailed player data"""
        try:
            url = f"{self.base_url}/element-summary/{player_id}/"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching player {player_id}: {e}")
            return None
    
    def get_live_gameweek_data(self, gameweek):
        """Get live data for a specific gameweek"""
        try:
            url = f"{self.base_url}/event/{gameweek}/live/"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching gameweek {gameweek} data: {e}")
            return None
    
    def get_team_data(self, team_id):
        """Get team-specific data"""
        try:
            url = f"{self.base_url}/entry/{team_id}/"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching team {team_id}: {e}")
            return None
    
    def download_historical_data(self):
        """Download historical FPL data from vaastav's repository"""
        try:
            # Historical data URLs (from vaastav's repository)
            base_url = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"
            seasons = ["2020-21", "2021-22", "2022-23", "2023-24"]
            
            for season in seasons:
                season_dir = f"{self.data_dir}/{season}"
                os.makedirs(season_dir, exist_ok=True)
                
                # Download player data
                player_url = f"{base_url}/{season}/players_raw.csv"
                try:
                    df = pd.read_csv(player_url)
                    df.to_csv(f"{season_dir}/players_raw.csv", index=False)
                    logger.info(f"Downloaded {season} player data")
                except Exception as e:
                    logger.warning(f"Could not download {season} player data: {e}")
                
                # Download gameweek data
                for gw in range(1, 39):  # Assuming max 38 gameweeks
                    gw_url = f"{base_url}/{season}/gws/gw{gw}.csv"
                    try:
                        df = pd.read_csv(gw_url)
                        df.to_csv(f"{season_dir}/gw{gw}.csv", index=False)
                    except:
                        break  # Stop if gameweek doesn't exist
                
                logger.info(f"Downloaded {season} data")
                
        except Exception as e:
            logger.error(f"Error downloading historical data: {e}")
    
    def get_understat_data(self):
        """Get advanced statistics from Understat (requires additional setup)"""
        logger.info("Understat integration requires additional setup")
        # This would require selenium or similar for scraping
        pass
    
    def create_player_features(self):
        """Create comprehensive player features dataset"""
        try:
            # Load current player data
            players_df = pd.read_csv(f"{self.data_dir}/elements.csv")
            
            # Create additional features
            players_df['value_per_point'] = players_df['now_cost'] / players_df['total_points'].replace(0, 1)
            players_df['form_per_cost'] = players_df['form'] / players_df['now_cost'].replace(0, 1)
            players_df['points_per_game_per_cost'] = players_df['points_per_game'] / players_df['now_cost'].replace(0, 1)
            
            # Position-specific features
            players_df['is_attacker'] = players_df['element_type'].isin([3, 4])  # Midfielders and Forwards
            players_df['is_defender'] = players_df['element_type'].isin([2])  # Defenders
            players_df['is_goalkeeper'] = players_df['element_type'].isin([1])  # Goalkeepers
            
            # Save enhanced dataset
            players_df.to_csv(f"{self.data_dir}/players_enhanced.csv", index=False)
            logger.info("Created enhanced player features dataset")
            
            return players_df
            
        except Exception as e:
            logger.error(f"Error creating player features: {e}")
            return None
    
    def run_full_collection(self):
        """Run complete data collection"""
        logger.info("Starting FPL data collection...")
        
        # 1. Get current season data
        bootstrap_data = self.get_bootstrap_static()
        if bootstrap_data:
            logger.info("Successfully downloaded current season data")
        
        # 2. Create enhanced features
        self.create_player_features()
        
        # 3. Download historical data
        self.download_historical_data()
        
        # 4. Create summary report
        self.create_summary_report()
        
        logger.info("Data collection completed!")
    
    def create_summary_report(self):
        """Create a summary report of collected data"""
        try:
            report = {
                'collection_date': datetime.now().isoformat(),
                'data_sources': [
                    'Official FPL API',
                    'Historical data from vaastav repository'
                ],
                'files_created': []
            }
            
            # List all created files
            for root, dirs, files in os.walk(self.data_dir):
                for file in files:
                    if file.endswith(('.csv', '.json')):
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        report['files_created'].append({
                            'file': file_path,
                            'size_bytes': file_size,
                            'size_mb': round(file_size / 1024 / 1024, 2)
                        })
            
            # Save report
            with open(f"{self.data_dir}/collection_report.json", 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info("Created collection summary report")
            
        except Exception as e:
            logger.error(f"Error creating summary report: {e}")

if __name__ == "__main__":
    collector = FPLDataCollector()
    collector.run_full_collection() 