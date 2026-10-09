"""Rotas PUBLICAS (sem login) do descadastro: /u/<token>   (E1 do PLANO_PROSPECTADOR)

- GET  mostra uma pagina de confirmacao (scanners de e-mail abrem links por conta propria: GET nunca descadastra).
- POST descadastra (botao da pagina OU clique unico do provedor de e-mail, RFC 8058, cabecalho List-Unsubscribe-Post).
O token e assinado (HMAC) e so vale para o e-mail atual do prospect.
"""
from flask import Blueprint, Response, redirect, request

import database
import mailer

bp = Blueprint("public_routes", __name__)

_PAGE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{title}</title>
<body style="font:16px/1.6 system-ui,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;background:#f6f4ef;color:#1b1a18;padding:24px">
<main style="max-width:440px;text-align:center"><h1 style="font-size:1.3rem;margin:0 0 10px">{title}</h1>{body}</main></body></html>"""


def _page(title, body, status=200):
    resp = Response(_PAGE.format(title=title, body=body), status=status, mimetype="text/html")
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _mask(email):
    local, _, domain = (email or "").partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


@bp.route("/u/<token>", methods=["GET", "POST"])
def unsubscribe(token):
    pid, email = mailer.verify_unsub_token(token)
    if not pid:
        return _page("Link inválido", "<p style='color:#625b53'>Este link não é válido ou já foi substituído. "
                     "Se quiser deixar de receber mensagens, responda ao e-mail com a palavra SAIR.</p>", 404)
    if request.method == "POST":
        if not database.is_suppressed(email):
            database.set_stage(pid, "descadastrou", note="link de descadastro", source="link")
        return _page("Pronto, você não receberá mais mensagens",
                     f"<p style='color:#625b53'>O endereço <b>{_mask(email)}</b> foi removido da nossa lista.</p>")
    return _page("Deixar de receber mensagens?",
                 f"<p style='color:#625b53'>Confirme para remover <b>{_mask(email)}</b> da nossa lista.</p>"
                 "<form method='post'><button style='font:inherit;padding:.8em 1.6em;border:0;border-radius:999px;"
                 "background:#1b1a18;color:#fff;cursor:pointer'>Confirmar descadastro</button></form>")


@bp.route("/r/<token>")
def click(token):
    """Link do portfolio nos e-mails: registra o clique (evento link_clicked) e redireciona. Token assinado; robos e pre-visualizadores nao contam."""
    import crm
    from mockups.blueprint import BOT_RE
    target = database.get_setting("sender_portfolio", "") or "https://paviani.net/portfolio/"
    pid = crm.verify_click_token(token)
    if pid and not BOT_RE.search(request.headers.get("User-Agent", "")):
        database.add_event(pid, "link_clicked", target, {})
    resp = redirect(target, code=302)
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp
