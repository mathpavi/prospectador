"""Rota publica dos esboços:  /p/<token>/

Para ligar ao app (SO NO DIA DE SUBIR), em app.py:
    from mockups.blueprint import bp as mockups_bp
    app.register_blueprint(mockups_bp)
"""
import os
import re
import time

from flask import Blueprint, Response, abort, redirect, send_from_directory

from . import store

bp = Blueprint("mockups", __name__)

PREVIEW_HOST = os.environ.get("PREVIEW_HOST", "preview.paviani.net").lower()


def preview_gate(req):
    """Porteiro para o before_request do app.
    - None      -> segue o fluxo normal (login etc.)
    - "public"  -> /p/... e publico, dispensa login
    - Response  -> 404: no host de preview so existe /p/... (o painel nunca fica exposto por la)
    Este teste vem ANTES de qualquer outra regra, inclusive do token de diagnostico."""
    host = (req.host or "").split(":")[0].lower()
    if host == PREVIEW_HOST and not req.path.startswith("/p/"):
        return Response("Not Found", status=404, mimetype="text/plain")
    if req.path.startswith("/p/"):
        return "public"
    return None

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{12,40}$")
# robos e pre-visualizadores de link nao contam como "abertura" de verdade
BOT_RE = re.compile(r"bot|crawl|spider|whatsapp|facebookexternalhit|slack|telegram|linkedin|preview|curl|wget|python-requests|headless|monitor", re.I)
ALLOWED_FILES = {"thumb.png"}

EXPIRED = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Proposta encerrada</title>
<body style="font:16px/1.6 system-ui;display:grid;place-items:center;min-height:100vh;margin:0;background:#0d0f11;color:#ebe8e1;text-align:center;padding:24px">
<div><h1 style="font-size:1.4rem;margin:0 0 8px">Esta proposta visual foi encerrada</h1>
<p style="color:#9b9b95;margin:0">Para ver novamente, fale com a Paviani.</p></div></body></html>"""


def _headers(resp):
    resp.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def _load(token):
    if not TOKEN_RE.match(token):
        abort(404)
    m = store.get(token)
    if not m or m["status"] != "ready":
        abort(404)
    if m["expires_at"] < time.time():
        return m, _headers(Response(EXPIRED, status=410, mimetype="text/html"))
    return m, None


@bp.route("/p/<token>")
def no_slash(token):
    return redirect(f"/p/{token}/", code=301)


@bp.route("/p/<token>/")
def page(token):
    m, gone = _load(token)
    if gone:
        return gone
    ua = ""
    from flask import request
    ua = request.headers.get("User-Agent", "")
    if not BOT_RE.search(ua):
        store.record_view(token)
    d = os.path.join(store.data_dir(), token)
    resp = send_from_directory(d, "index.html", mimetype="text/html")
    return _headers(resp)


@bp.route("/p/<token>/<path:filename>")
def asset(token, filename):
    m, gone = _load(token)
    if gone:
        return gone
    d = os.path.join(store.data_dir(), token)
    if filename in ALLOWED_FILES:
        return _headers(send_from_directory(d, filename))
    if filename.startswith("img/") and re.fullmatch(r"img/[A-Za-z0-9._-]+", filename):
        return _headers(send_from_directory(d, filename))
    abort(404)
