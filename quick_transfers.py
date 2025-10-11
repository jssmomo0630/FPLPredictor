#!/usr/bin/env python3
"""
Quick transfer recommendations using your squad
"""

import json
from fpl_prediction_model import FPLPredictionModel

def load_your_squad():
    """Load your specific squad"""
    with open("squads/squad_20250802_104843.json", 'r') as f:
        squad_data = json.load(f)
    
    # Convert to model format
    squad = {
        'GK': [],
        'DEF': [],
        'MID': [],
        'FWD': [],
        'total_cost': squad_data.get('total_cost', 0),
        'formation': squad_data.get('formation', '4-4-2')
    }
    
    for position, players in squad_data.get('players', {}).items():
        for player in players:
            squad[position].append({
                'name': player['name'],
                'now_cost': player['cost'] * 10,  # Convert to 0.1m units
                'predicted_points': player['predicted_points'],
                'element_type': player['element_type']
            })
    
    return squad

def main():
    print("🎯 Quick Transfer Recommendations")
    print("=" * 40)
    
    # Load model
    print("Loading model...")
    model = FPLPredictionModel()
    model.load_data()
    
    # Load your squad
    squad = load_your_squad()
    
    print(f"\nYour Current Squad (£{squad['total_cost']/10:.1f}m):")
    for position in ['GK', 'DEF', 'MID', 'FWD']:
        print(f"\n{position}:")
        for player in squad[position]:
            print(f"  {player['name']} - £{player['now_cost']/10:.1f}m")
    
    # Get transfer suggestions
    print(f"\n🔄 Getting transfer recommendations (2 free transfers)...")
    try:
        suggestions = model.suggest_transfers(squad, transfers_available=2)
        
        if suggestions and suggestions.get('suggestions'):
            print(f"\n💡 Transfer Recommendations:")
            for i, transfer in enumerate(suggestions['suggestions'], 1):
                print(f"{i}. {transfer['position']}: {transfer['out']} → {transfer['in']}")
                print(f"   Points gain: +{transfer['points_gain']:.1f}")
                print(f"   Cost change: £{transfer['cost_change']/10:.1f}m")
        else:
            print("No specific transfer suggestions available from model")
            print("Your squad may already be well optimized!")
            
    except Exception as e:
        print(f"Error getting suggestions: {e}")
        print("Model transfer function may need updates for 2025-26 data")

if __name__ == "__main__":
    main()

