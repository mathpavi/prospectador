"""Servidor LOCAL so para testar a rota /p/<token>/ (nao e usado na VPS).  python mockups/serve_dev.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

from mockups.blueprint import bp  # noqa: E402

app = Flask(__name__)
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055)
