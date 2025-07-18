web: gunicorn -w 1 -k gevent --bind 0.0.0.0:$PORT --timeout 120 --log-level info --on-starting 'bot.on_starting' bot:app
