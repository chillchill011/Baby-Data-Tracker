web: gunicorn bot:app -w 1 --bind 0.0.0.0:$PORT --timeout 120 --log-level info --on-starting 'bot.on_starting'
