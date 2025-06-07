import yaml
import json
import os
from datetime import datetime
import requests
import chess
import chess.pgn
import chess.engine
import io
from telegram import Bot
import time

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

    if last_game_time is None:
        one_day_ago = int(time.time()) - 1 * 24 * 60 * 60
        last_game_time = one_day_ago
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    headers = {"User-Agent": "chess-analyzer-bot/1.0 (contact: your@email.com)"}
    resp = requests.get(archives_url, headers=headers)
    resp.raise_for_status()
    archives = resp.json()["archives"]
    new_games = []
    for archive_url in reversed(archives):  
        month_resp = requests.get(archive_url, headers=headers)
        month_resp.raise_for_status()
        games = month_resp.json().get("games", [])
        for game in games:
            end_time = game.get("end_time")
            if not end_time:
                continue
            if end_time <= last_game_time:
                continue
        
            if game.get("rules") != "chess":
                continue
            
            if "pgn" not in game:
                continue
            new_games.append({
                "pgn": game["pgn"],
                "end_time": end_time,
                "time_class": game.get("time_class"),
                "rules": game.get("rules"),
                "white": game.get("white", {}).get("username"),
                "black": game.get("black", {}).get("username"),
                "url": game.get("url"),
                "result": game.get("white", {}).get("result"),
            })
    return sorted(new_games, key=lambda g: g["end_time"])  

def analyze_games(games):

    stockfish_path = "stockfish/stockfish-ubuntu-x86-64-avx2"
    engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
    analyzed = []
    for game_data in games:
        pgn = game_data["pgn"]
        game = chess.pgn.read_game(io.StringIO(pgn))
        board = game.board()
        moves = list(game.mainline_moves())
        move_analysis = []
        prev_score = None
        blunders = mistakes = inaccuracies = best_moves = 0
        for i, move in enumerate(moves):
            info = engine.analyse(board, chess.engine.Limit(depth=15))
            score = info["score"].white().score(mate_score=10000)
            
            board.push(move)
        
            info_after = engine.analyse(board, chess.engine.Limit(depth=15))
            score_after = info_after["score"].white().score(mate_score=10000)
       
            if prev_score is not None:
                diff = (score_after - prev_score) if (i % 2 == 0) == (game.headers["White"] == game_data["white"]) else (prev_score - score_after)
     
                if diff <= -300:
                    blunders += 1
                elif diff <= -100:
                    mistakes += 1
                elif diff <= -50:
                    inaccuracies += 1
                elif diff >= 0:
                    best_moves += 1
            prev_score = score_after

        opening = game.headers.get("Opening", "Unknown")
        eco = game.headers.get("ECO", "?")
        analyzed.append({
            "url": game_data["url"],
            "white": game_data["white"],
            "black": game_data["black"],
            "result": game_data["result"],
            "end_time": game_data["end_time"],
            "opening": opening,
            "eco": eco,
            "blunders": blunders,
            "mistakes": mistakes,
            "inaccuracies": inaccuracies,
            "best_moves": best_moves,
            "total_moves": len(moves),
        })
    engine.quit()
    return analyzed

def generate_report(analysis):

    if not analysis:
        return "No new games analyzed."

    total_blunders = sum(g["blunders"] for g in analysis)
    total_mistakes = sum(g["mistakes"] for g in analysis)
    total_inaccuracies = sum(g["inaccuracies"] for g in analysis)
    total_best = sum(g["best_moves"] for g in analysis)
    total_moves = sum(g["total_moves"] for g in analysis)
    opening_counts = {}
    for g in analysis:
        key = f"{g['opening']} ({g['eco']})"
        opening_counts[key] = opening_counts.get(key, 0) + 1
    most_common_opening = max(opening_counts, key=opening_counts.get)

    report = ["**Chess.com Daily Report**\n"]
    report.append(f"Games analyzed: {len(analysis)}\n")
    report.append(f"Total moves: {total_moves}")
    report.append(f"Blunders: {total_blunders} | Mistakes: {total_mistakes} | Inaccuracies: {total_inaccuracies} | Best moves: {total_best}\n")
    report.append(f"Most common opening: {most_common_opening}\n")

    for g in analysis:
        date_str = datetime.utcfromtimestamp(g["end_time"]).strftime('%Y-%m-%d')
        report.append(f"\n---\n**Game vs {g['black'] if g['white']=='1Levick3' else g['white']}** on {date_str}")
        report.append(f"[View on Chess.com]({g['url']})")
        report.append(f"Opening: {g['opening']} ({g['eco']})")
        report.append(f"Result: {g['result']}")
        report.append(f"Blunders: {g['blunders']} | Mistakes: {g['mistakes']} | Inaccuracies: {g['inaccuracies']} | Best moves: {g['best_moves']}")

        if g['blunders'] > 0:
            report.append("Tip: Review the critical moments where you lost material or missed tactics.")
        elif g['mistakes'] > 0:
            report.append("Tip: Double-check your moves for simple threats before playing.")
        elif g['inaccuracies'] > 0:
            report.append("Tip: Try to improve your positional understanding in the opening and middlegame.")
        else:
            report.append("Great game! Keep it up.")


    report.append("\n---\n**General Improvement Tips:**")
    if total_blunders > 0:
        report.append("- Practice tactics to reduce blunders.")
    if total_mistakes > 0:
        report.append("- Review your games to understand your mistakes.")
    if total_inaccuracies > 0:
        report.append("- Study opening principles and typical middlegame plans.")
    report.append("- Use puzzles and endgame trainers to sharpen your skills.")

    return '\n'.join(report)

def send_report(report, config):

    if config.get("delivery_method") != "telegram":
        print("Only Telegram delivery is implemented.")
        return
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set in environment.")
        return
    bot = Bot(token=token)

    max_len = 4000
    parts = [report[i:i+max_len] for i in range(0, len(report), max_len)]
    for part in parts:
        bot.send_message(chat_id=chat_id, text=part, parse_mode='Markdown')

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