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
import asyncio
import chess.polyglot
from collections import Counter

# Load config
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
    """
    Fetch new games for the user since last_game_time (epoch seconds).
    If last_game_time is None, only fetch games from the past day.
    Returns a list of dicts with at least: pgn, end_time, time_class, rules, etc.
    """
    # If no last_game_time, default to one day ago
    if last_game_time is None:
        one_day_ago = int(time.time()) - 1 * 24 * 60 * 60
        last_game_time = one_day_ago
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    headers = {"User-Agent": "chess-analyzer-bot/1.0 (contact: your@email.com)"}
    resp = requests.get(archives_url, headers=headers)
    resp.raise_for_status()
    archives = resp.json()["archives"]
    new_games = []
    for archive_url in reversed(archives):  # newest last
        month_resp = requests.get(archive_url, headers=headers)
        month_resp.raise_for_status()
        games = month_resp.json().get("games", [])
        for game in games:
            end_time = game.get("end_time")
            if not end_time:
                continue
            if end_time <= last_game_time:
                continue
            # Only include standard chess games
            if game.get("rules") != "chess":
                continue
            # Only include finished games with PGN
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
    return sorted(new_games, key=lambda g: g["end_time"])  # oldest first

def analyze_games(games):
    """
    Analyze each game using Stockfish. Returns a list of dicts with analysis per game.
    Each dict includes: opening, blunders, mistakes, inaccuracies, best moves, accuracy, ratings, move numbers, etc.
    """
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
        blunder_moves = []
        mistake_moves = []
        inaccuracy_moves = []
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
                    blunder_moves.append(i+1)
                elif diff <= -100:
                    mistakes += 1
                    mistake_moves.append(i+1)
                elif diff <= -50:
                    inaccuracies += 1
                    inaccuracy_moves.append(i+1)
                elif diff >= 0:
                    best_moves += 1
            prev_score = score_after
        # Opening detection using python-chess ECO
        try:
            opening_obj = chess.openings.find(board, limit=12)
            opening = opening_obj.name
            eco = opening_obj.eco
        except Exception:
            opening = game.headers.get("Opening", "Unknown")
            eco = game.headers.get("ECO", "?")
        # Ratings
        white_rating = game.headers.get("WhiteElo") or game_data.get("white_rating")
        black_rating = game.headers.get("BlackElo") or game_data.get("black_rating")
        # Result
        result = game.headers.get("Result", game_data.get("result", "?"))
        analyzed.append({
            "url": game_data["url"],
            "white": game_data["white"],
            "black": game_data["black"],
            "white_rating": white_rating,
            "black_rating": black_rating,
            "result": result,
            "end_time": game_data["end_time"],
            "opening": opening,
            "eco": eco,
            "blunders": blunders,
            "mistakes": mistakes,
            "inaccuracies": inaccuracies,
            "best_moves": best_moves,
            "total_moves": len(moves),
            "blunder_moves": blunder_moves,
            "mistake_moves": mistake_moves,
            "inaccuracy_moves": inaccuracy_moves,
            "time_class": game_data.get("time_class", "?"),
        })
    engine.quit()
    return analyzed

def generate_report(analysis):
    """
    Summarize the analysis for all games and format an HTML report for Telegram.
    """
    if not analysis:
        return "No new games analyzed."

    total_blunders = sum(g["blunders"] for g in analysis)
    total_mistakes = sum(g["mistakes"] for g in analysis)
    total_inaccuracies = sum(g["inaccuracies"] for g in analysis)
    total_best = sum(g["best_moves"] for g in analysis)
    total_moves = sum(g["total_moves"] for g in analysis)
    opening_counts = {}
    time_class_counts = {}
    win = loss = draw = 0
    for g in analysis:
        key = f"{g['opening']} ({g['eco']})"
        opening_counts[key] = opening_counts.get(key, 0) + 1
        tc = g.get('time_class', '?')
        time_class_counts[tc] = time_class_counts.get(tc, 0) + 1
        # Win/loss/draw
        if g['white'] == '1Levick3':
            if g['result'] == '1-0': win += 1
            elif g['result'] == '0-1': loss += 1
            elif g['result'] == '1/2-1/2': draw += 1
        elif g['black'] == '1Levick3':
            if g['result'] == '0-1': win += 1
            elif g['result'] == '1-0': loss += 1
            elif g['result'] == '1/2-1/2': draw += 1
    most_common_opening = max(opening_counts, key=opening_counts.get)
    most_common_time_class = max(time_class_counts, key=time_class_counts.get)
    accuracy = (total_best / total_moves * 100) if total_moves else 0

    report = ["<b>Chess.com Daily Report</b>\n"]
    report.append(f"Games analyzed: {len(analysis)}\n")
    report.append(f"Total moves: {total_moves}\n")
    report.append(f"Accuracy: {accuracy:.1f}%\n")
    report.append(f"Blunders: {total_blunders} | Mistakes: {total_mistakes} | Inaccuracies: {total_inaccuracies} | Best moves: {total_best}\n")
    report.append(f"Most common opening: {most_common_opening}\n")
    report.append(f"Most common time control: {most_common_time_class}\n")
    report.append(f"Win/Loss/Draw: {win}/{loss}/{draw}\n")

    for g in analysis:
        date_str = datetime.utcfromtimestamp(g["end_time"]).strftime('%Y-%m-%d')
        opponent = g['black'] if g['white']=='1Levick3' else g['white']
        my_rating = g['white_rating'] if g['white']=='1Levick3' else g['black_rating']
        opp_rating = g['black_rating'] if g['white']=='1Levick3' else g['white_rating']
        report.append(f"\n---\n<b>Game vs {opponent}</b> on {date_str}")
        report.append(f'<a href="{g["url"]}">View on Chess.com</a>')
        report.append(f"Opening: {g['opening']} ({g['eco']})")
        report.append(f"Time control: {g['time_class']}")
        report.append(f"Your rating: {my_rating} | Opponent rating: {opp_rating}")
        report.append(f"Result: {g['result']}")
        report.append(f"Blunders: {g['blunders']} (moves: {g['blunder_moves']}) | Mistakes: {g['mistakes']} (moves: {g['mistake_moves']}) | Inaccuracies: {g['inaccuracies']} (moves: {g['inaccuracy_moves']}) | Best moves: {g['best_moves']}")
        # Simple improvement tip
        if g['blunders'] > 0:
            report.append("Tip: Review the critical moments where you lost material or missed tactics.")
        elif g['mistakes'] > 0:
            report.append("Tip: Double-check your moves for simple threats before playing.")
        elif g['inaccuracies'] > 0:
            report.append("Tip: Try to improve your positional understanding in the opening and middlegame.")
        else:
            report.append("Great game! Keep it up.")

    # General improvement tips
    report.append("\n---\n<b>General Improvement Tips:</b>")
    if total_blunders > total_mistakes and total_blunders > 0:
        report.append("- Focus on tactics training to reduce blunders.")
    if total_mistakes > 0:
        report.append("- Review your games to understand your mistakes.")
    if total_inaccuracies > 0:
        report.append("- Study opening principles and typical middlegame plans.")
    if accuracy < 60:
        report.append("- Aim for more consistent move quality. Slow down and double-check threats.")
    report.append("- Use puzzles and endgame trainers to sharpen your skills.")

    return '\n'.join(report)

async def send_report(report, config):
    """
    Send the report via Telegram using the bot token and chat ID from environment variables.
    """
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
        await bot.send_message(chat_id=chat_id, text=part, parse_mode='HTML')

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
    asyncio.run(send_report(report, config))
    # Update state with latest game time
    latest_time = max(game['end_time'] for game in games)
    state['last_game_time'] = latest_time
    save_state(state)

if __name__ == '__main__':
    main() 