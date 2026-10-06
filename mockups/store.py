"""Registro dos esboços publicados. Banco PROPRIO (mockups.db), sem tocar no prospector.db."""
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def data_dir():
    d = os.environ.get("MOCKUP_DATA_DIR") or os.path.join(os.environ.get("DATA_DIR", os.path.join(HERE, "_data")), "mockups")
    os.makedirs(d, exist_ok=True)
    return d


def _conn():
    c = sqlite3.connect(os.path.join(data_dir(), "mockups.db"), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("""create table if not exists mockups(
        token text primary key, prospect_id integer, company text, template text,
        status text not null,              -- ready | review | revoked
        reason text, data_score integer,
        created_at integer, expires_at integer,
        views integer default 0, first_view_at integer, last_view_at integer)""")
    return c


def create(token, prospect_id, company, template, status, reason="", data_score=0, days=21):
    now = int(time.time())
    with _conn() as c:
        c.execute("insert into mockups(token,prospect_id,company,template,status,reason,data_score,created_at,expires_at) values(?,?,?,?,?,?,?,?,?)",
                  (token, prospect_id, company, template, status, reason, data_score, now, now + days * 86400))


def get(token):
    with _conn() as c:
        r = c.execute("select * from mockups where token=?", (token,)).fetchone()
    return dict(r) if r else None


def set_status(token, status, reason=""):
    with _conn() as c:
        c.execute("update mockups set status=?, reason=? where token=?", (status, reason, token))


def record_view(token):
    now = int(time.time())
    with _conn() as c:
        c.execute("update mockups set views=views+1, last_view_at=?, first_view_at=coalesce(first_view_at,?) where token=?", (now, now, token))


def list_all():
    with _conn() as c:
        return [dict(r) for r in c.execute("select * from mockups order by created_at desc")]


def recent_attempt(prospect_id, days=7):
    """True se ja houve tentativa de esboco para este prospect nos ultimos `days` dias (pronta OU em revisao): nao insistir."""
    since = int(time.time()) - days * 86400
    with _conn() as c:
        return bool(c.execute("select 1 from mockups where prospect_id=? and created_at>? limit 1", (prospect_id, since)).fetchone())


def created_last_24h():
    """Quantos esbocos foram gerados nas ultimas 24 h (limite diario de custo e de carga)."""
    with _conn() as c:
        return c.execute("select count(*) from mockups where created_at>?", (int(time.time()) - 86400,)).fetchone()[0]


def ready_tokens(prospect_ids):
    """{prospect_id: token} dos esbocos PRONTOS e dentro da validade (o mais recente de cada prospect)."""
    ids = [int(i) for i in prospect_ids if i is not None]
    if not ids:
        return {}
    now = int(time.time())
    out = {}
    with _conn() as c:
        for i in range(0, len(ids), 500):                      # limite de variaveis do SQLite
            chunk = ids[i:i + 500]
            q = ",".join("?" * len(chunk))
            for r in c.execute(f"select prospect_id, token from mockups where status='ready' and expires_at>? and prospect_id in ({q}) "
                               "order by created_at asc", [now] + chunk):
                out[r["prospect_id"]] = r["token"]               # o mais recente sobrescreve
    return out
