#!/usr/bin/env python3
"""
Player Consistency Analysis
==========================

This script analyzes player name consistency across FPL seasons 2020-2025
to understand how many players match between different years.

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import os
from itertools import combinations

def load_season_players(season):
    """Load all unique players from a specific season."""
    try:
        # Load from merged_gw.csv for complete season data
        merged_file = f"data/{season}/merged_gw.csv"
        if os.path.exists(merged_file):
            df = pd.read_csv(merged_file)
            players = set(df['name'].dropna().unique())
            return players
        else:
            print(f"❌ No merged_gw.csv found for {season}")
            return set()
    except Exception as e:
        print(f"❌ Error loading {season}: {e}")
        return set()

def analyze_player_consistency():
    """Analyze player consistency across all seasons."""
    print("🎯 Player Consistency Analysis (2020-2025)")
    print("=" * 60)
    
    seasons = ['2020-21', '2021-22', '2022-23', '2023-24', '2024-25']
    
    # Load players from each season
    season_players = {}
    for season in seasons:
        players = load_season_players(season)
        season_players[season] = players
        print(f"📊 {season}: {len(players)} unique players")
    
    print(f"\n📈 SEASON-BY-SEASON COMPARISON:")
    print("-" * 40)
    
    # Compare each pair of seasons
    for i, (season1, season2) in enumerate(combinations(seasons, 2)):
        players1 = season_players[season1]
        players2 = season_players[season2]
        
        # Find exact matches
        exact_matches = players1.intersection(players2)
        
        # Calculate match rate
        match_rate = (len(exact_matches) / len(players1)) * 100 if players1 else 0
        
        print(f"\n{season1} vs {season2}:")
        print(f"  📊 {season1}: {len(players1)} players")
        print(f"  📊 {season2}: {len(players2)} players")
        print(f"  ✅ Exact matches: {len(exact_matches)}")
        print(f"  📈 Match rate: {match_rate:.1f}%")
        
        # Show some examples of matching players
        if exact_matches:
            sample_matches = sorted(list(exact_matches))[:10]
            print(f"  🎯 Sample matches: {', '.join(sample_matches)}")
    
    print(f"\n🔍 OVERALL CONSISTENCY ANALYSIS:")
    print("-" * 40)
    
    # Find players that appear in all seasons
    all_seasons_players = set.intersection(*season_players.values())
    print(f"📊 Players in ALL seasons: {len(all_seasons_players)}")
    
    if all_seasons_players:
        print(f"🎯 Examples: {', '.join(sorted(list(all_seasons_players))[:10])}")
    
    # Find players that appear in at least 4 seasons
    players_in_4_plus = set()
    for player in set.union(*season_players.values()):
        count = sum(1 for players in season_players.values() if player in players)
        if count >= 4:
            players_in_4_plus.add(player)
    
    print(f"📊 Players in 4+ seasons: {len(players_in_4_plus)}")
    
    # Find players that appear in at least 3 seasons
    players_in_3_plus = set()
    for player in set.union(*season_players.values()):
        count = sum(1 for players in season_players.values() if player in players)
        if count >= 3:
            players_in_3_plus.add(player)
    
    print(f"📊 Players in 3+ seasons: {len(players_in_3_plus)}")
    
    # Analyze by position (using most recent season for position data)
    print(f"\n📊 POSITION ANALYSIS:")
    print("-" * 30)
    
    try:
        # Load position data from 2024-25 season
        players_df = pd.read_csv("data/2024-25/players_raw.csv")
        position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
        
        for pos_id in [1, 2, 3, 4]:
            pos_name = position_map[pos_id]
            pos_players = set(players_df[players_df['element_type'] == pos_id]['web_name'].unique())
            
            # Find how many of these players appear in multiple seasons
            pos_in_all = all_seasons_players.intersection(pos_players)
            pos_in_4_plus = players_in_4_plus.intersection(pos_players)
            pos_in_3_plus = players_in_3_plus.intersection(pos_players)
            
            print(f"{pos_name}: {len(pos_in_all)} in all, {len(pos_in_4_plus)} in 4+, {len(pos_in_3_plus)} in 3+ out of {len(pos_players)} total")
            
    except Exception as e:
        print(f"Could not analyze by position: {e}")
    
    # Show season-by-season retention rates
    print(f"\n📈 SEASON RETENTION RATES:")
    print("-" * 35)
    
    for i, season in enumerate(seasons[:-1]):
        current_players = season_players[season]
        next_season = seasons[i + 1]
        next_players = season_players[next_season]
        
        retained = current_players.intersection(next_players)
        retention_rate = (len(retained) / len(current_players)) * 100 if current_players else 0
        
        print(f"{season} → {next_season}: {len(retained)}/{len(current_players)} players retained ({retention_rate:.1f}%)")
    
    # Save detailed results
    save_consistency_results(season_players, all_seasons_players, players_in_4_plus, players_in_3_plus)
    
    return {
        'season_players': season_players,
        'all_seasons_players': all_seasons_players,
        'players_in_4_plus': players_in_4_plus,
        'players_in_3_plus': players_in_3_plus
    }

def save_consistency_results(season_players, all_seasons_players, players_in_4_plus, players_in_3_plus):
    """Save detailed consistency results to file."""
    print(f"\n💾 Saving detailed results...")
    
    results = {
        'players_in_all_seasons': sorted(list(all_seasons_players)),
        'players_in_4_plus_seasons': sorted(list(players_in_4_plus)),
        'players_in_3_plus_seasons': sorted(list(players_in_3_plus)),
        'season_breakdown': {}
    }
    
    # Add season-by-season breakdown
    for season, players in season_players.items():
        results['season_breakdown'][season] = sorted(list(players))
    
    import json
    with open('player_consistency_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"✅ Results saved to player_consistency_results.json")

def main():
    """Main function."""
    results = analyze_player_consistency()
    
    if results:
        print(f"\n🎯 SUMMARY:")
        print(f"Total seasons analyzed: 5 (2020-21 to 2024-25)")
        print(f"Players in all seasons: {len(results['all_seasons_players'])}")
        print(f"Players in 4+ seasons: {len(results['players_in_4_plus'])}")
        print(f"Players in 3+ seasons: {len(results['players_in_3_plus'])}")
        
        # Assess data quality for hybrid approach
        total_players_2024_25 = len(results['season_players']['2024-25'])
        players_with_history = len(results['players_in_3_plus'])
        coverage_rate = (players_with_history / total_players_2024_25) * 100 if total_players_2024_25 > 0 else 0
        
        print(f"\n📊 HYBRID APPROACH ASSESSMENT:")
        print(f"2024-25 players: {total_players_2024_25}")
        print(f"Players with 3+ seasons history: {players_with_history}")
        print(f"Coverage rate: {coverage_rate:.1f}%")
        
        if coverage_rate >= 70:
            print(f"✅ Excellent coverage! Hybrid approach should work very well.")
        elif coverage_rate >= 50:
            print(f"⚠️ Good coverage. Hybrid approach should work with some limitations.")
        elif coverage_rate >= 30:
            print(f"⚠️ Moderate coverage. Hybrid approach may have significant limitations.")
        else:
            print(f"❌ Low coverage. Hybrid approach may not be very effective.")
    else:
        print(f"❌ Analysis failed")

if __name__ == "__main__":
    main() 