#!/usr/bin/env python3
"""
FPL Squad Validator
===================

This module validates saved FPL squads against actual gameweek data
to see how well our predictions perform in reality.

Author: FPL Prediction Team
Date: July 2025
"""

import pandas as pd
import json
import os
from datetime import datetime
from difflib import SequenceMatcher

class SquadValidator:
    """Validates FPL squad predictions against actual gameweek data."""
    
    def __init__(self):
        self.squad = None
        self.gw_data = None
        
        # Hard-coded name mappings for common variations
        self.name_mappings = {
            'Enzo': 'Enzo Fernández',
            'M.Salah': 'Mohamed Salah',
            'J.Murphy': 'Jacob Murphy',
            'Strand Larsen': 'Jørgen Strand Larsen',
            'Murillo': 'Murillo Santiago Costa dos Santos',
            'Beto': 'Norberto Bercique Gomes Betuncal',
            'Collins': 'Nathan Collins',
            'Mykolenko': 'Vitalii Mykolenko',
            'Semenyo': 'Antoine Semenyo',
            'Haaland': 'Erling Haaland'
        }
    
    def load_saved_squad(self, filename):
        """Load a previously saved squad from JSON file."""
        try:
            with open(filename, 'r') as f:
                squad_data = json.load(f)
            
            # Reconstruct squad structure
            self.squad = {
                'formation': squad_data.get('formation', '4-4-2'),
                'total_cost': squad_data.get('total_cost', 0),
                'available_transfers': 1,
                'wildcard_available': True
            }
            
            # Load captain and vice-captain information
            self.captain = squad_data.get('captain')
            self.vice_captain = squad_data.get('vice_captain')
            
            # Add players by position
            for position in ['GK', 'DEF', 'MID', 'FWD']:
                if position in squad_data['players']:
                    self.squad[position] = []
                    for player_data in squad_data['players'][position]:
                        # Convert back to model format
                        player = {
                            'name': player_data['name'],
                            'now_cost': player_data['cost'] * 10,  # Convert back to 0.1m units
                            'predicted_points': player_data['predicted_points'],
                            'element_type': player_data['element_type']
                        }
                        self.squad[position].append(player)
            
            # Handle legacy format (no starting_xi/bench in JSON)
            if 'starting_xi' in squad_data and 'bench' in squad_data:
                # New format with explicit starting XI and bench
                self.starting_xi = squad_data['starting_xi']
                self.bench = squad_data['bench']
            else:
                # Legacy format - determine starting XI based on predicted points
                all_players = []
                for position, players in self.squad.items():
                    if isinstance(players, list):
                        all_players.extend(players)
                
                # Sort by predicted points and take top 11 for starting XI
                all_players.sort(key=lambda x: x['predicted_points'], reverse=True)
                self.starting_xi = all_players[:11]
                self.bench = all_players[11:]
            
            print(f"✅ Loaded squad from {filename}")
            print(f"🎯 Starting XI: {len(self.starting_xi)} players")
            print(f"🪑 Bench: {len(self.bench)} players")
            
            if self.captain:
                print(f"👑 Captain: {self.captain['name']}")
            if self.vice_captain:
                print(f"👑 Vice-Captain: {self.vice_captain['name']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error loading squad: {e}")
            return False
    
    def load_gameweek_data(self, gameweek=1, season="2024-25"):
        """Load actual gameweek data for validation."""
        print(f"📊 Loading GW{gameweek} Actual Data...")
        
        try:
            # Load gameweek data
            gw_file = f"data/{season}/gws/gw{gameweek}.csv"
            if os.path.exists(gw_file):
                self.gw_data = pd.read_csv(gw_file)
                self.current_gameweek = gameweek
                self.current_season = season
                print(f"✅ Loaded GW{gameweek} data: {len(self.gw_data)} players")
                return True
            else:
                print(f"⚠️ GW{gameweek} data not found at {gw_file}")
                return False
        except Exception as e:
            print(f"❌ Error loading GW{gameweek} data: {e}")
            return False
    
    def clean_name(self, name):
        """Clean player name for matching."""
        if pd.isna(name):
            return ""
        return str(name).lower().strip()
    
    def fuzzy_match(self, squad_name, gw_names, threshold=0.8):
        """Find the best fuzzy match for a squad player name."""
        best_match = None
        best_score = 0
        
        for gw_name in gw_names:
            score = SequenceMatcher(None, squad_name, gw_name).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gw_name
        
        return best_match, best_score
    
    def match_squad_players(self):
        """Match squad players with gameweek data using multiple strategies."""
        if not self.squad or self.gw_data is None:
            print("❌ Missing squad or gameweek data")
            return None
        
        print("\n" + "="*60)
        print("🔍 PLAYER MATCHING ANALYSIS")
        print("="*60)
        
        # Get all squad players
        all_squad_players = []
        for position, players in self.squad.items():
            if isinstance(players, list):
                all_squad_players.extend(players)
        
        print(f"📋 Squad players to match: {len(all_squad_players)}")
        
        # Prepare gameweek names
        gw_names = self.gw_data['name'].dropna().unique()
        gw_names_clean = [self.clean_name(name) for name in gw_names]
        
        print(f"📊 Gameweek players available: {len(gw_names)}")
        
        # Matching results
        exact_matches = []
        fuzzy_matches = []
        no_matches = []
        
        for player in all_squad_players:
            squad_name = player['name']
            squad_name_clean = self.clean_name(squad_name)
            
            # Strategy 1: Hard-coded mapping
            if squad_name in self.name_mappings:
                mapped_name = self.name_mappings[squad_name]
                if mapped_name in gw_names:
                    exact_matches.append({
                        'squad_name': squad_name,
                        'gw_name': mapped_name,
                        'match_type': 'mapped',
                        'player': player
                    })
                    continue
            
            # Strategy 2: Exact match (case-insensitive)
            exact_match = None
            for gw_name in gw_names:
                if self.clean_name(gw_name) == squad_name_clean:
                    exact_match = gw_name
                    break
            
            if exact_match:
                exact_matches.append({
                    'squad_name': squad_name,
                    'gw_name': exact_match,
                    'match_type': 'exact',
                    'player': player
                })
                continue
            
            # Strategy 3: Fuzzy match (lowered threshold)
            fuzzy_match, score = self.fuzzy_match(squad_name_clean, gw_names_clean, threshold=0.6)
            
            if fuzzy_match:
                # Find the original name
                original_name = None
                for gw_name in gw_names:
                    if self.clean_name(gw_name) == fuzzy_match:
                        original_name = gw_name
                        break
                
                fuzzy_matches.append({
                    'squad_name': squad_name,
                    'gw_name': original_name,
                    'match_type': 'fuzzy',
                    'score': score,
                    'player': player
                })
            else:
                no_matches.append({
                    'squad_name': squad_name,
                    'player': player
                })
        
        # Report results
        print(f"\n📊 MATCHING RESULTS:")
        print(f"🎯 Mapped matches: {len([m for m in exact_matches if m['match_type'] == 'mapped'])}")
        print(f"✅ Exact matches: {len([m for m in exact_matches if m['match_type'] == 'exact'])}")
        print(f"🔍 Fuzzy matches: {len(fuzzy_matches)}")
        print(f"❌ No matches: {len(no_matches)}")
        print(f"📈 Success rate: {((len(exact_matches) + len(fuzzy_matches)) / len(all_squad_players) * 100):.1f}%")
        
        # Show mapped matches
        mapped_matches = [m for m in exact_matches if m['match_type'] == 'mapped']
        if mapped_matches:
            print(f"\n🎯 MAPPED MATCHES ({len(mapped_matches)}):")
            for match in mapped_matches:
                print(f"  Squad: {match['squad_name']} → GW: {match['gw_name']}")
        
        # Show exact matches
        exact_only = [m for m in exact_matches if m['match_type'] == 'exact']
        if exact_only:
            print(f"\n✅ EXACT MATCHES ({len(exact_only)}):")
            for match in exact_only:
                print(f"  Squad: {match['squad_name']} → GW: {match['gw_name']}")
        
        # Show fuzzy matches
        if fuzzy_matches:
            print(f"\n🔍 FUZZY MATCHES ({len(fuzzy_matches)}):")
            for match in fuzzy_matches:
                print(f"  Squad: {match['squad_name']} → GW: {match['gw_name']} (score: {match['score']:.2f})")
        
        # Show unmatched players
        if no_matches:
            print(f"\n❌ UNMATCHED PLAYERS ({len(no_matches)}):")
            for match in no_matches:
                print(f"  Squad: {match['squad_name']} (Position: {match['player']['element_type']})")
            
            # Show potential matches for unmatched players
            print(f"\n🔍 POTENTIAL MATCHES FOR UNMATCHED PLAYERS:")
            for match in no_matches:
                squad_name = match['squad_name']
                squad_name_clean = self.clean_name(squad_name)
                
                print(f"\n  Squad: {squad_name}")
                print(f"  Potential GW matches:")
                
                # Find potential matches with lower threshold
                potential_matches = []
                for gw_name in gw_names:
                    gw_name_clean = self.clean_name(gw_name)
                    score = SequenceMatcher(None, squad_name_clean, gw_name_clean).ratio()
                    if score > 0.3:  # Lower threshold for suggestions
                        potential_matches.append((gw_name, score))
                
                # Sort by score and show top 3
                potential_matches.sort(key=lambda x: x[1], reverse=True)
                for gw_name, score in potential_matches[:3]:
                    print(f"    - {gw_name} (score: {score:.2f})")
        
        return {
            'exact_matches': exact_matches,
            'fuzzy_matches': fuzzy_matches,
            'no_matches': no_matches,
            'total_squad': len(all_squad_players),
            'success_rate': (len(exact_matches) + len(fuzzy_matches)) / len(all_squad_players) * 100
        }
    
    def validate_squad_against_gameweek(self):
        """Compare predicted squad performance against actual gameweek data."""
        if not self.squad or not hasattr(self, 'gw_data'):
            print("❌ Missing squad or gameweek data")
            return None
        
        print("\n" + "="*60)
        print(f"🔍 SQUAD VALIDATION AGAINST GW{self.current_gameweek}")
        print("="*60)
        
        # First, match players
        matching_results = self.match_squad_players()
        
        if not matching_results:
            return None
        
        # Get all matched players
        all_matches = matching_results['exact_matches'] + matching_results['fuzzy_matches']
        
        if not all_matches:
            print("❌ No players could be matched for validation")
            return None
        
        print(f"\n📊 VALIDATION RESULTS:")
        print(f"✅ Players found: {len(all_matches)}")
        print(f"❌ Players not found: {len(matching_results['no_matches'])}")
        
        # Analyze predicted vs actual points
        validation_data = []
        starting_xi_score = 0
        bench_score = 0
        captain_bonus = 0
        
        for match in all_matches:
            squad_player = match['player']
            gw_name = match['gw_name']
            
            # Find the player in gameweek data
            gw_player = self.gw_data[self.gw_data['name'] == gw_name].iloc[0]
            
            predicted_points = squad_player['predicted_points']
            actual_points = gw_player['total_points']
            
            # Check if player is in starting XI or bench
            is_starting_xi = squad_player['name'] in [p['name'] for p in self.starting_xi]
            
            # Check if this player is captain or vice-captain
            is_captain = self.captain and squad_player['name'] == self.captain['name']
            is_vice_captain = self.vice_captain and squad_player['name'] == self.vice_captain['name']
            
            validation_data.append({
                'name': gw_name,
                'predicted_points': predicted_points,
                'actual_points': actual_points,
                'difference': actual_points - predicted_points,
                'match_type': match['match_type'],
                'is_starting_xi': is_starting_xi,
                'is_captain': is_captain,
                'is_vice_captain': is_vice_captain,
                'element_type': squad_player['element_type']
            })
            
            # Add to squad score based on position and captain status
            if is_starting_xi:
                if is_captain:
                    # Captain gets double points
                    captain_bonus = actual_points
                    starting_xi_score += actual_points * 2
                    print(f"👑 Captain {gw_name}: {actual_points} × 2 = {actual_points * 2} pts")
                elif is_vice_captain:
                    # Vice-captain gets normal points (only doubled if captain doesn't play)
                    starting_xi_score += actual_points
                    print(f"👑 Vice-Captain {gw_name}: {actual_points} pts (normal)")
                else:
                    # Regular starting XI player
                    starting_xi_score += actual_points
            else:
                # Bench player
                bench_score += actual_points
        
        # Calculate squad statistics
        if validation_data:
            df = pd.DataFrame(validation_data)
            
            # Squad score calculations
            starting_xi_players = df[df['is_starting_xi'] == True]
            bench_players = df[df['is_starting_xi'] == False]
            
            print(f"\n📈 SQUAD SCORE ANALYSIS:")
            print(f"🎯 Starting XI Score: {starting_xi_score:.1f} points")
            print(f"🪑 Bench Score: {bench_score:.1f} points")
            print(f"📊 Total Squad Score: {starting_xi_score + bench_score:.1f} points")
            
            if len(starting_xi_players) > 0:
                print(f"🎯 Starting XI Players Found: {len(starting_xi_players)}")
                print(f"  Average Starting XI Points: {starting_xi_players['actual_points'].mean():.1f}")
            
            if len(bench_players) > 0:
                print(f"🪑 Bench Players Found: {len(bench_players)}")
                print(f"  Average Bench Points: {bench_players['actual_points'].mean():.1f}")
            
            print(f"\n📈 PREDICTION ACCURACY:")
            print(f"  Mean Absolute Error: {df['difference'].abs().mean():.2f}")
            print(f"  Root Mean Square Error: {((df['difference'] ** 2).mean() ** 0.5):.2f}")
            print(f"  Correlation: {df['predicted_points'].corr(df['actual_points']):.3f}")
            
            # Add detailed player breakdown by position (Starting XI only)
            print(f"\n📊 STARTING XI BREAKDOWN:")
            position_map = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'}
            
            # Group starting XI players by position
            starting_xi_df = df[df['is_starting_xi'] == True]
            for position_id in [1, 2, 3, 4]:
                position_name = position_map[position_id]
                position_players = starting_xi_df[starting_xi_df['element_type'] == position_id]
                
                if len(position_players) > 0:
                    print(f"\n{position_name}:")
                    for _, row in position_players.iterrows():
                        player_name = row['name']
                        actual_points = row['actual_points']
                        is_captain = row['is_captain']
                        is_vice_captain = row['is_vice_captain']
                        
                        # Add captain/vice-captain indicators
                        if is_captain:
                            print(f"  {player_name}: {actual_points} × 2 = {actual_points * 2} (C)")
                        elif is_vice_captain:
                            print(f"  {player_name}: {actual_points} (VC)")
                        else:
                            print(f"  {player_name}: {actual_points}")
            
            # Show bench players separately
            bench_df = df[df['is_starting_xi'] == False]
            if len(bench_df) > 0:
                print(f"\n🪑 BENCH PLAYERS:")
                for _, row in bench_df.iterrows():
                    player_name = row['name']
                    actual_points = row['actual_points']
                    print(f"  {player_name}: {actual_points}")
            
            print(f"\n🏆 BEST PREDICTIONS:")
            best_predictions = df.iloc[df['difference'].abs().argsort()[:3]]
            for _, row in best_predictions.iterrows():
                position = "🎯" if row['is_starting_xi'] else "🪑"
                print(f"  {position} {row['name']}: Predicted {row['predicted_points']:.1f}, Actual {row['actual_points']:.1f} (Diff: {row['difference']:+.1f})")
            
            print(f"\n❌ WORST PREDICTIONS:")
            worst_predictions = df.iloc[df['difference'].abs().argsort()[-3:]]
            for _, row in worst_predictions.iterrows():
                position = "🎯" if row['is_starting_xi'] else "🪑"
                print(f"  {position} {row['name']}: Predicted {row['predicted_points']:.1f}, Actual {row['actual_points']:.1f} (Diff: {row['difference']:+.1f})")
        
        return matching_results

def main():
    """Main function to run squad validation."""
    import sys
    
    # Get command line arguments
    squad_file = sys.argv[1] if len(sys.argv) > 1 else None
    gameweek = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    season = sys.argv[3] if len(sys.argv) > 3 else "2024-25"
    
    print("🎯 FPL Squad Validator")
    print("=" * 50)
    
    if not squad_file:
        print("❌ Please provide a squad file to validate")
        print(f"💡 Usage: python squad_validator.py <squad_file.json> [gameweek] [season]")
        print(f"💡 Example: python squad_validator.py squads/squad_20241201_143022.json 1 2024-25")
        print(f"💡 Example: python squad_validator.py squads/squad_20241201_143022.json 2 2024-25")
        return
    
    # Initialize validator
    validator = SquadValidator()
    
    # Load squad
    if not validator.load_saved_squad(squad_file):
        return
    
    # Load gameweek data
    if not validator.load_gameweek_data(gameweek, season):
        return
    
    # Run validation
    results = validator.validate_squad_against_gameweek()
    
    if results:
        print(f"\n✅ Validation complete!")
        print(f"📊 Success rate: {results['success_rate']:.1f}%")
    else:
        print(f"\n❌ Validation failed!")

if __name__ == "__main__":
    main() 