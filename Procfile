web: gunicorn bot:app -w 1 --worker-class gevent --bind 0.0.0.0:$PORT --timeout 120 --log-level info --on-starting 'bot.on_starting'
