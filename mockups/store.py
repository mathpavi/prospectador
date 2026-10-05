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
