import yaml
import json
import os
from datetime import datetime

def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

def load_state():
    if os.path.exists('state.json'):
        with open('state.json', 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    with open('state.json', 'w') as f:
        json.dump(state, f)

def fetch_new_games(username, last_game_time):
    
    pass

def analyze_games(games):
    
    pass

def generate_report(analysis):
   
    pass

def send_report(report, config):
    
    pass

def main():
    config = load_config()
    state = load_state()
    last_game_time = state.get('last_game_time')
    games = fetch_new_games(config['chesscom_username'], last_game_time)
    if not games:
        print('No new games to analyze.')
        return
    analysis = analyze_games(games)
    report = generate_report(analysis)
    send_report(report, config)
    
    latest_time = max(game['end_time'] for game in games)
    state['last_game_time'] = latest_time
    save_state(state)

if __name__ == '__main__':
    main() 