1. Make a virtualenv: python -m venv .venv
   Activate: .venv\Scripts\activate (Windows) or source .venv/bin/activate (mac/linux)

2. Install:
   pip install -r requirements.txt

3. Copy .env.example -> .env and fill required values (TELEGRAM_BOT_TOKEN, ADMIN_USER_IDS, ANNOUNCE_CHANNEL_ID).

4. Run API:
   uvicorn app.webserver:app --host 0.0.0.0 --port 8000

5. In a new terminal run the bot:
   python -m app.bot

6. If testing webhooks locally, expose via ngrok:
   ngrok http 8000
   update APP_BASE_URL in .env to the ngrok https url and restart services

7. Use in Telegram:
   /start, /pay, /mytickets
   Admin: /start_draw, /participants, /announce_winners @username, /end_draw
