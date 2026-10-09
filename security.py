"""Seguranca do app (F1 do PLANO_PROSPECTADOR).

- Chave de sessao: variavel SECRET_KEY, ou uma chave aleatoria gerada e guardada em DATA_DIR (nunca um valor fixo no codigo).
- Token de diagnostico: so existe se DIAGNOSTICS_TOKEN estiver definido; comparacao em tempo constante.
- Senha de admin obrigatoria: sem ela, so localhost abre; qualquer outro acesso recebe 503.
- Limite de tentativas de login por IP.
"""
import hmac
import os
import secrets
import time

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def get_secret_key():
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        return env
    data_dir = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(data_dir, ".secret_key")
    try:
        if os.path.exists(path):
            key = open(path, encoding="utf-8").read().strip()
            if len(key) >= 32:
                return key
        os.makedirs(data_dir, exist_ok=True)
        key = secrets.token_urlsafe(48)
        with open(path, "w", encoding="utf-8") as f:
            f.write(key)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return key
    except OSError:
        return secrets.token_urlsafe(48)          # sem disco: chave so desta execucao (sessoes caem no reinicio)


def safe_equal(a, b):
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))


def diag_token():
    return os.environ.get("DIAGNOSTICS_TOKEN", "").strip()


DIAG_READONLY_PATHS = ("/api/dia", "/api/fila", "/api/fontes", "/api/esbocos/reavaliar", "/api/resultados", "/api/autopilot/diagnostics", "/api/autopilot/status", "/api/prospect/status", "/api/surgical/status", "/api/directories/status")


def diag_authorized(req):
    """Acesso programatico de monitoramento: so com DIAGNOSTICS_TOKEN definido e igual ao enviado (cabecalho).
    SOMENTE LEITURA: so metodo GET e so nos enderecos de diagnostico (nunca aprova, envia ou altera nada)."""
    token = diag_token()
    if not token:
        return False
    if req.method not in ("GET", "HEAD") or not (req.path.rstrip("/") in DIAG_READONLY_PATHS or req.path.startswith("/api/lead/")):
        return False
    sent = (req.headers.get("X-Diag-Key") or "").strip()
    return bool(sent) and safe_equal(sent, token)


def is_local_request(req):
    host = (req.host or "").split(":")[0].lower()
    return host in _LOCAL_HOSTS


def open_access_blocked(req, admin_pass):
    """True quando NAO ha senha de admin e o acesso nao e local (o app nao pode ficar aberto na internet)."""
    return (not admin_pass) and not is_local_request(req)


# ---- limite de tentativas de login (em memoria; suficiente para 1 processo) ----
_FAILS = {}
MAX_FAILS, WINDOW = 5, 600


def login_blocked(ip):
    now = time.time()
    n, first = _FAILS.get(ip, (0, now))
    if now - first > WINDOW:
        _FAILS.pop(ip, None)
        return False
    return n >= MAX_FAILS


def register_login_failure(ip):
    now = time.time()
    n, first = _FAILS.get(ip, (0, now))
    if now - first > WINDOW:
        n, first = 0, now
    _FAILS[ip] = (n + 1, first)


def clear_login_failures(ip):
    _FAILS.pop(ip, None)


def client_ip(req):
    fwd = (req.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return fwd or (req.remote_addr or "?")
