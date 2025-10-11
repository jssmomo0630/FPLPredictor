#!/usr/bin/env python3
"""
Get Current FPL Players for 2024-25 Season
==========================================

This script loads and displays the current FPL player list for the 2024-25 season.
"""

import pandas as pd

def get_current_players():
    """Load and display current 2024-25 FPL players."""
    
    try:
        # Load current season data
        players_df = pd.read_csv('data/2024-25/players_raw.csv')
        
        print("🎯 Current FPL Players (2024-25 Season)")
        print("=" * 60)
        
        # Position mapping
        position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        players_df['position'] = players_df['element_type'].map(position_map)
        
        # Display summary
        print(f"Total Players: {len(players_df)}")
        print(f"Goalkeepers: {len(players_df[players_df['element_type'] == 1])}")
        print(f"Defenders: {len(players_df[players_df['element_type'] == 2])}")
        print(f"Midfielders: {len(players_df[players_df['element_type'] == 3])}")
        print(f"Forwards: {len(players_df[players_df['element_type'] == 4])}")
        
        print("\n💰 Price Distribution:")
        print(f"Cheapest: £{players_df['now_cost'].min()/10:.1f}m")
        print(f"Most Expensive: £{players_df['now_cost'].max()/10:.1f}m")
        print(f"Average Price: £{players_df['now_cost'].mean()/10:.1f}m")
        
        # Show top players by position
        print("\n🏆 Top Players by Position:")
        
        for pos_code, pos_name in position_map.items():
            pos_players = players_df[players_df['element_type'] == pos_code].copy()
            pos_players = pos_players.sort_values('now_cost', ascending=False)
            
            print(f"\n{pos_name} (Top 10 by price):")
            for _, player in pos_players.head(10).iterrows():
                price = player['now_cost'] / 10
                print(f"  {player['web_name']} - £{price:.1f}m - {player['team']}")
        
        # Show players by team
        print(f"\n🏟️ Players by Team:")
        team_counts = players_df.groupby('team')['web_name'].count().sort_values(ascending=False)
        for team, count in team_counts.items():
            print(f"  {team}: {count} players")
        
        return players_df
        
    except FileNotFoundError:
        print("❌ 2024-25 player data not found!")
        return None
    except Exception as e:
        print(f"❌ Error loading player data: {e}")
        return None

def filter_available_players(players_df, min_price=40, max_price=150):
    """
    Filter players to only include those likely to be available.
    
    Args:
        players_df: Player dataframe
        min_price: Minimum price in 0.1m units (default 4.0m)
        max_price: Maximum price in 0.1m units (default 15.0m)
    """
    if players_df is None:
        return None
    
    # Filter by reasonable price range
    available = players_df[
        (players_df['now_cost'] >= min_price) & 
        (players_df['now_cost'] <= max_price)
    ].copy()
    
    print(f"\n📊 Available Players (Price £{min_price/10:.1f}m - £{max_price/10:.1f}m):")
    print(f"Total: {len(available)} players")
    
    for pos_code, pos_name in {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}.items():
        pos_count = len(available[available['element_type'] == pos_code])
        print(f"{pos_name}: {pos_count} players")
    
    return available

if __name__ == "__main__":
    # Get current players
    players = get_current_players()
    
    if players is not None:
        # Filter to available players
        available_players = filter_available_players(players)
        
        # Save to CSV for easy reference
        if available_players is not None:
            available_players.to_csv('current_available_players.csv', index=False)
            print(f"\n✅ Saved available players to 'current_available_players.csv'")
            print(f"📄 File contains {len(available_players)} players") 