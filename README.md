# Chess.com Daily Analyzer

This project analyzes your daily chess.com games and sends you a personalized improvement report via Telegram.

## Features
- Fetches your latest chess.com games
- Analyzes with Stockfish
- Summarizes openings, mistakes, and improvement tips
- Sends a daily report to your Telegram
- Runs automatically via GitHub Actions

## Setup
1. **Clone the repo and install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure your username and delivery method in `config.yaml`:**
   ```yaml
   chesscom_username: 1Levick3
   delivery_method: telegram
   ```
3. **Create a Telegram Bot:**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Use `/newbot` to create a bot and get the token
   - Start a chat with your bot and send any message
   - Use [this tool](https://t.me/userinfobot) or an API call to get your chat ID
4. **Add your Telegram token and chat ID as GitHub secrets:**
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`

## GitHub Actions Automation
- The workflow in `.github/workflows/daily.yml` runs the analysis every day.
- Push your code to GitHub, set up the secrets, and you're done!

## Customization
- The script can be extended to support email delivery or more advanced analysis.

## TODO
- Implement fetch, analyze, report, and send modules in `main.py`. 