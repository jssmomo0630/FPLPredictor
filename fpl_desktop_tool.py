#!/usr/bin/env python3
"""
FPL Desktop Tool
================

A simple desktop application for generating and managing FPL squads
using the FPL prediction model.

Features:
- Visual squad display with formation layout
- Generate optimized squads with budget constraints
- Team constraint validation (max 3 players per team)
- Captain and vice-captain recommendations
- Transfer suggestions
- Squad saving/loading

Author: FPL Prediction Team
Date: August 2025
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from datetime import datetime
import threading
from fpl_prediction_model import FPLPredictionModel

class FPLDesktopTool:
    """Main FPL Desktop Tool application."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("FPL Squad Generator v1.0")
        self.root.geometry("1000x700")
        self.root.resizable(True, True)
        
        # Initialize model (will be loaded in background)
        self.model = None
        self.current_squad = None
        self.predictions = None
        
        # Formation options
        self.formations = [
            "3-5-2", "3-4-3", "4-5-1", "4-4-2", 
            "4-3-3", "5-4-1", "5-3-2"
        ]
        
        # Team name mapping (will be loaded from data)
        self.team_mapping = {}
        
        # Setup UI
        self.setup_ui()
        self.setup_menu()
        
        # Load model in background
        self.load_model_async()
    
    def setup_ui(self):
        """Set up the main user interface."""
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights for responsive design
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # === TOP CONTROLS BAR ===
        controls_frame = ttk.LabelFrame(main_frame, text="Squad Configuration", padding="10")
        controls_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Formation selector
        ttk.Label(controls_frame, text="Formation:").grid(row=0, column=0, padx=(0, 5))
        self.formation_var = tk.StringVar(value="4-4-2")
        formation_combo = ttk.Combobox(controls_frame, textvariable=self.formation_var, 
                                     values=self.formations, state="readonly", width=8)
        formation_combo.grid(row=0, column=1, padx=(0, 20))
        formation_combo.bind('<<ComboboxSelected>>', self.on_formation_change)
        
        # Budget display
        ttk.Label(controls_frame, text="Budget:").grid(row=0, column=2, padx=(0, 5))
        self.budget_var = tk.StringVar(value="£0.0m/£100.0m")
        budget_label = ttk.Label(controls_frame, textvariable=self.budget_var, font=("Arial", 10, "bold"))
        budget_label.grid(row=0, column=3, padx=(0, 20))
        
        # Gameweek selector  
        ttk.Label(controls_frame, text="Current GW:").grid(row=0, column=4, padx=(0, 5))
        self.gameweek_var = tk.StringVar(value="1")
        gw_spin = tk.Spinbox(controls_frame, from_=1, to=38, textvariable=self.gameweek_var, 
                           width=5, state="readonly")
        gw_spin.grid(row=0, column=5, padx=(0, 20))
        
        # Generate button
        self.generate_btn = ttk.Button(controls_frame, text="🎯 Generate Squad", 
                                     command=self.generate_squad, style="Accent.TButton")
        self.generate_btn.grid(row=0, column=6, padx=(10, 0))
        
        # === SQUAD DISPLAY AREA ===
        squad_frame = ttk.LabelFrame(main_frame, text="Current Squad", padding="10")
        squad_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        squad_frame.columnconfigure(0, weight=1)
        squad_frame.rowconfigure(0, weight=1)
        
        # Create canvas for formation display
        self.setup_formation_canvas(squad_frame)
        
        # === BOTTOM PANEL ===
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        
        # Left panel - Squad info
        info_frame = ttk.LabelFrame(bottom_frame, text="Squad Information", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        self.info_text = tk.Text(info_frame, height=8, wrap=tk.WORD, font=("Consolas", 9))
        info_scrollbar = ttk.Scrollbar(info_frame, orient="vertical", command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=info_scrollbar.set)
        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        info_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)
        
        # Right panel - Actions
        actions_frame = ttk.LabelFrame(bottom_frame, text="Actions", padding="10")
        actions_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        # Action buttons
        ttk.Button(actions_frame, text="💾 Save Squad", command=self.save_squad).grid(row=0, column=0, sticky=tk.W+tk.E, pady=2)
        ttk.Button(actions_frame, text="📁 Load Squad", command=self.load_squad).grid(row=1, column=0, sticky=tk.W+tk.E, pady=2)
        ttk.Button(actions_frame, text="🔄 Transfer Suggestions", command=self.show_transfers).grid(row=2, column=0, sticky=tk.W+tk.E, pady=2)
        ttk.Button(actions_frame, text="✅ Validate Squad", command=self.validate_squad).grid(row=3, column=0, sticky=tk.W+tk.E, pady=2)
        ttk.Button(actions_frame, text="📊 Export Squad", command=self.export_squad).grid(row=4, column=0, sticky=tk.W+tk.E, pady=2)
        
        actions_frame.columnconfigure(0, weight=1)
        
        # === STATUS BAR ===
        self.status_var = tk.StringVar(value="Ready - Load model to generate squads")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
    def setup_formation_canvas(self, parent):
        """Set up the formation display canvas."""
        canvas_frame = ttk.Frame(parent)
        canvas_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        
        self.formation_canvas = tk.Canvas(canvas_frame, bg="lightgreen", height=400)
        canvas_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.formation_canvas.yview)
        self.formation_canvas.configure(yscrollcommand=canvas_scrollbar.set)
        
        self.formation_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        canvas_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # Initialize empty formation
        self.draw_empty_formation()
        
    def setup_menu(self):
        """Set up the application menu."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Squad", command=self.generate_squad)
        file_menu.add_command(label="Open Squad...", command=self.load_squad)
        file_menu.add_command(label="Save Squad...", command=self.save_squad)
        file_menu.add_separator()
        file_menu.add_command(label="Export to CSV...", command=self.export_squad)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Reload Model", command=self.load_model_async)
        tools_menu.add_command(label="Validate Squad", command=self.validate_squad)
        tools_menu.add_command(label="Transfer Suggestions", command=self.show_transfers)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        
    def draw_empty_formation(self):
        """Draw an empty formation layout."""
        self.formation_canvas.delete("all")
        
        # Draw pitch background
        canvas_width = self.formation_canvas.winfo_width() or 800
        canvas_height = self.formation_canvas.winfo_height() or 400
        
        # Pitch outline
        self.formation_canvas.create_rectangle(50, 50, canvas_width-50, canvas_height-50, 
                                             outline="white", width=2)
        
        # Center circle
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        self.formation_canvas.create_oval(center_x-30, center_y-30, center_x+30, center_y+30, 
                                        outline="white", width=2)
        
        # Placeholder text
        self.formation_canvas.create_text(center_x, center_y, text="Generate a squad to see formation", 
                                        fill="darkgreen", font=("Arial", 14, "bold"))
        
    def load_model_async(self):
        """Load the FPL model in a background thread."""
        self.status_var.set("Loading FPL model... Please wait")
        self.generate_btn.config(state="disabled")
        
        def load_model():
            try:
                self.model = FPLPredictionModel()
                self.model.load_data()
                self.model.train_position_models()
                
                # Load team mapping
                try:
                    import pandas as pd
                    teams_df = pd.read_csv('data/2025-26/teams.csv')
                    self.team_mapping = dict(zip(teams_df['id'], teams_df['name']))
                except:
                    self.team_mapping = {}
                
                # Update UI on main thread
                self.root.after(0, self.on_model_loaded)
                
            except Exception as e:
                self.root.after(0, lambda: self.on_model_error(str(e)))
        
        thread = threading.Thread(target=load_model, daemon=True)
        thread.start()
        
    def on_model_loaded(self):
        """Called when model loading is complete."""
        self.status_var.set("Model loaded successfully - Ready to generate squads!")
        self.generate_btn.config(state="normal")
        self.update_info_display("✅ FPL Model loaded successfully!\n\n" +
                                "📊 Data includes 5 years of historical performance\n" +
                                "🎯 Ready to generate optimized squads\n" +
                                "💡 Click 'Generate Squad' to start\n\n" +
                                "Features:\n" +
                                "• Position-specific ML models\n" +
                                "• Budget optimization (£100m)\n" +
                                "• Formation validation\n" +
                                "• Team constraints (max 3 per team)\n" +
                                "• Captain recommendations")
        
    def on_model_error(self, error_msg):
        """Called when model loading fails."""
        self.status_var.set("Error loading model")
        self.generate_btn.config(state="disabled")
        messagebox.showerror("Model Loading Error", f"Failed to load FPL model:\n\n{error_msg}")
        
    def on_formation_change(self, event=None):
        """Called when formation selection changes."""
        if self.current_squad:
            self.display_squad(self.current_squad)
        
    def generate_squad(self):
        """Generate a new optimized squad."""
        if not self.model:
            messagebox.showwarning("Model Not Ready", "Please wait for the model to load first.")
            return
            
        self.status_var.set("Generating optimal squad... Please wait")
        self.generate_btn.config(state="disabled")
        
        def generate():
            try:
                formation = self.formation_var.get()
                squad = self.model.optimize_squad(budget=100.0, formation=formation)
                
                if squad:
                    self.current_squad = squad
                    self.root.after(0, lambda: self.on_squad_generated(squad))
                else:
                    self.root.after(0, lambda: self.on_generation_error("Failed to generate valid squad"))
                    
            except Exception as e:
                self.root.after(0, lambda: self.on_generation_error(str(e)))
        
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        
    def on_squad_generated(self, squad):
        """Called when squad generation is complete."""
        self.status_var.set("Squad generated successfully!")
        self.generate_btn.config(state="normal")
        
        # Display the squad
        self.display_squad(squad)
        
        # Update budget display
        total_cost = squad['total_cost'] / 10
        self.budget_var.set(f"£{total_cost:.1f}m/£100.0m")
        
        messagebox.showinfo("Squad Generated", 
                          f"✅ New squad generated successfully!\n\n" +
                          f"Formation: {squad['formation']}\n" +
                          f"Total Cost: £{total_cost:.1f}m\n" +
                          f"Players: 15")
        
    def on_generation_error(self, error_msg):
        """Called when squad generation fails."""
        self.status_var.set("Squad generation failed")
        self.generate_btn.config(state="normal")
        messagebox.showerror("Generation Error", f"Failed to generate squad:\n\n{error_msg}")
        
    def display_squad(self, squad):
        """Display the squad in formation layout."""
        # Clear canvas
        self.formation_canvas.delete("all")
        
        canvas_width = self.formation_canvas.winfo_width() or 800
        canvas_height = self.formation_canvas.winfo_height() or 400
        
        # Draw pitch
        self.formation_canvas.create_rectangle(20, 20, canvas_width-20, canvas_height-20, 
                                             outline="white", width=2, fill="lightgreen")
        
        # Get formation layout
        formation = self.formation_var.get()
        def_count, mid_count, fwd_count = map(int, formation.split('-'))
        
        # Position layouts (y-coordinates from top to bottom)
        positions = {
            'GK': [(canvas_width//2, canvas_height - 50)],  # Bottom
            'DEF': self.get_position_layout(def_count, canvas_width, canvas_height - 120),
            'MID': self.get_position_layout(mid_count, canvas_width, canvas_height - 220),
            'FWD': self.get_position_layout(fwd_count, canvas_width, canvas_height - 320)
        }
        
        # Draw players
        for pos, coords_list in positions.items():
            if pos in squad and squad[pos]:
                players = squad[pos]
                for i, (x, y) in enumerate(coords_list):
                    if i < len(players):
                        player = players[i]
                        self.draw_player_card(x, y, player, pos)
        
        # Update info display
        self.update_squad_info(squad)
        
    def get_position_layout(self, count, canvas_width, y):
        """Get x-coordinates for players in a position line."""
        if count == 1:
            return [(canvas_width//2, y)]
        
        spacing = min(150, (canvas_width - 100) / count)
        start_x = (canvas_width - (count-1) * spacing) // 2
        
        return [(start_x + i * spacing, y) for i in range(count)]
        
    def draw_player_card(self, x, y, player, position):
        """Draw a player card on the canvas."""
        # Player circle
        radius = 25
        self.formation_canvas.create_oval(x-radius, y-radius, x+radius, y+radius, 
                                        fill="lightblue", outline="navy", width=2)
        
        # Player name (shortened)
        name = player['name']
        if len(name) > 10:
            name = name.split()[-1]  # Use last name
        
        self.formation_canvas.create_text(x, y-5, text=name, font=("Arial", 8, "bold"))
        
        # Cost
        cost = f"£{player['now_cost']/10:.1f}m"
        self.formation_canvas.create_text(x, y+8, text=cost, font=("Arial", 7))
        
        # Team info
        team_id = player.get('team', 'Unknown')
        team_name = self.team_mapping.get(team_id, f"T{team_id}")
        self.formation_canvas.create_text(x, y+18, text=team_name[:3].upper(), 
                                        font=("Arial", 6), fill="darkgreen")
        
    def update_squad_info(self, squad):
        """Update the squad information display."""
        if not squad:
            return
            
        info_text = "📋 SQUAD DETAILS\n"
        info_text += "=" * 40 + "\n\n"
        
        # Squad summary
        total_cost = squad['total_cost'] / 10
        info_text += f"Formation: {squad['formation']}\n"
        info_text += f"Total Cost: £{total_cost:.1f}m\n"
        info_text += f"Remaining Budget: £{100.0 - total_cost:.1f}m\n\n"
        
        # Players by position
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position in squad and squad[position]:
                info_text += f"{position}:\n"
                for player in squad[position]:
                    name = player['name']
                    cost = player['now_cost'] / 10
                    points = player.get('predicted_points', 0)
                    team_id = player.get('team', 'Unknown')
                    team_name = self.team_mapping.get(team_id, f"Team {team_id}")
                    
                    info_text += f"  • {name:<15} £{cost:>5.1f}m  {points:>5.1f}pts  {team_name}\n"
                info_text += "\n"
        
        # Team distribution
        team_counts = {}
        for position in ['GK', 'DEF', 'MID', 'FWD']:
            if position in squad:
                for player in squad[position]:
                    team_id = player.get('team', 'Unknown')
                    team_name = self.team_mapping.get(team_id, f"Team {team_id}")
                    team_counts[team_name] = team_counts.get(team_name, 0) + 1
        
        info_text += "🏆 TEAM DISTRIBUTION:\n"
        for team, count in sorted(team_counts.items()):
            status = "✅" if count <= 3 else "❌"
            info_text += f"  {status} {team}: {count} players\n"
        
        self.update_info_display(info_text)
        
    def update_info_display(self, text):
        """Update the info text display."""
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, text)
        
    def save_squad(self):
        """Save current squad to file."""
        if not self.current_squad:
            messagebox.showwarning("No Squad", "No squad to save. Generate a squad first.")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"squad_{timestamp}.json"
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfilename=filename,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filepath:
            try:
                with open(filepath, 'w') as f:
                    json.dump(self.current_squad, f, indent=2)
                messagebox.showinfo("Squad Saved", f"Squad saved successfully to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save squad:\n{e}")
                
    def load_squad(self):
        """Load squad from file."""
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="squads"
        )
        
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    saved_squad = json.load(f)
                
                # Convert saved squad format to internal format
                squad = self.convert_saved_squad_format(saved_squad)
                
                if squad:
                    self.current_squad = squad
                    self.display_squad(squad)
                    
                    # Update controls
                    if 'formation' in squad:
                        self.formation_var.set(squad['formation'])
                    if 'total_cost' in squad:
                        total_cost = squad['total_cost'] / 10
                        self.budget_var.set(f"£{total_cost:.1f}m/£100.0m")
                    
                    messagebox.showinfo("Squad Loaded", f"Squad loaded successfully from:\n{filepath}")
                else:
                    messagebox.showerror("Load Error", "Invalid squad file format")
                    
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load squad:\n{e}")
                
    def convert_saved_squad_format(self, saved_squad):
        """Convert saved squad format to internal format."""
        try:
            print(f"Loading squad with keys: {list(saved_squad.keys())}")
            
            # Check if this is already in internal format (has GK, DEF, MID, FWD keys at root)
            if all(key in saved_squad for key in ['GK', 'DEF', 'MID', 'FWD']):
                print("Squad already in internal format")
                return saved_squad
            
            # Convert from use_fpl_model.py format (has 'players' wrapper)
            if 'players' in saved_squad:
                print("Converting from use_fpl_model.py format")
                squad = {
                    'GK': [],
                    'DEF': [],
                    'MID': [],
                    'FWD': [],
                    'formation': saved_squad.get('formation', '4-4-2'),
                    'total_cost': saved_squad.get('total_cost', 0),
                    'available_transfers': 1,
                    'wildcard_available': True
                }
                
                # Convert player format
                for position in ['GK', 'DEF', 'MID', 'FWD']:
                    if position in saved_squad['players']:
                        converted_players = []
                        for player in saved_squad['players'][position]:
                            # Convert from saved format to internal format
                            converted_player = {
                                'name': player.get('name', ''),
                                'element_type': player.get('element_type', self.get_element_type_from_position(position)),
                                'now_cost': int(player.get('cost', 5.0) * 10),  # Convert £5.0m to 50 units
                                'predicted_points': player.get('predicted_points', 0),
                                'team': player.get('team', 1)  # Default team ID
                            }
                            converted_players.append(converted_player)
                            print(f"Converted {player.get('name', '')} - £{player.get('cost', 5.0)}m -> {converted_player['now_cost']} units")
                        
                        squad[position] = converted_players
                
                print(f"Converted squad with {sum(len(squad[pos]) for pos in ['GK', 'DEF', 'MID', 'FWD'])} players")
                return squad
            
            print("Unknown squad format")
            return None
            
        except Exception as e:
            print(f"Error converting squad format: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_element_type_from_position(self, position):
        """Get element_type from position string."""
        mapping = {'GK': 1, 'DEF': 2, 'MID': 3, 'FWD': 4}
        return mapping.get(position, 1)
                
    def show_transfers(self):
        """Show transfer suggestions window."""
        if not self.current_squad:
            messagebox.showwarning("No Squad", "Generate a squad first to see transfer suggestions.")
            return
        messagebox.showinfo("Transfer Suggestions", "Transfer suggestions feature coming soon!")
        
    def validate_squad(self):
        """Validate current squad."""
        if not self.current_squad:
            messagebox.showwarning("No Squad", "No squad to validate. Generate a squad first.")
            return
            
        if not self.model:
            messagebox.showwarning("Model Not Ready", "Model not loaded yet.")
            return
            
        is_valid, message = self.model.validate_formation(self.current_squad)
        
        if is_valid:
            messagebox.showinfo("Validation Result", f"✅ Squad is valid!\n\n{message}")
        else:
            messagebox.showerror("Validation Result", f"❌ Squad is invalid!\n\n{message}")
            
    def export_squad(self):
        """Export squad to various formats."""
        if not self.current_squad:
            messagebox.showwarning("No Squad", "No squad to export. Generate a squad first.")
            return
        messagebox.showinfo("Export Squad", "Export feature coming soon!")
        
    def show_about(self):
        """Show about dialog."""
        about_text = """FPL Squad Generator v1.0

A desktop tool for generating optimized Fantasy Premier League squads using machine learning predictions.

Features:
• ML-based player predictions
• Formation validation
• Budget optimization
• Team constraints
• Captain recommendations

Built with Python and tkinter
© 2025 FPL Prediction Team"""
        
        messagebox.showinfo("About FPL Squad Generator", about_text)
        
    def run(self):
        """Start the application."""
        self.root.mainloop()

def main():
    """Main function to start the desktop application."""
    app = FPLDesktopTool()
    app.run()

if __name__ == "__main__":
    main()