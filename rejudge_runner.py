"""Reavaliacao dos esbocos no ar pelo painel: roda `mockups/rejudge.py` em segundo plano e permite tirar do ar os reprovados."""
import json
import os
import subprocess
import sys
import time

import database

ROOT = os.path.dirname(os.path.abspath(__file__))
_proc = {"p": None}


def _dir():
    return os.environ.get("DATA_DIR", ROOT)


def out_path():
    return os.path.join(_dir(), "reavaliacao_esbocos.json")


def pid_path():
    return os.path.join(_dir(), "reavaliacao_esbocos.pid")


def running():
    p = _proc["p"]
    if p is not None and p.poll() is None:
        return True
    try:
        pid = int(open(pid_path()).read().strip())
    except Exception:  # noqa: BLE001
        return False
    if p is not None and p.pid == pid:
        return False
    return os.name != "nt" and os.path.exists(f"/proc/{pid}")


def start():
    if running():
        return False, "Já existe uma reavaliação em andamento."
    kw = {"start_new_session": True} if os.name != "nt" else {}
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "mockups", "rejudge.py"), "--out", out_path()], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env=dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", DATA_DIR=_dir()), **kw)
    _proc["p"] = p
    open(pid_path(), "w").write(str(p.pid))
    return True, "Reavaliação iniciada."


def status():
    try:
        data = json.load(open(out_path(), encoding="utf-8"))
    except Exception:  # noqa: BLE001
        data = None
    run = running()
    if not data:
        return {"rodando": run, "existe": False}
    from mockups import store
    for it in data["itens"]:
        row = store.get(it["token"])
        it["ja_tirado"] = bool(row and row["status"] != "ready")
        pr = database.get_prospect(it["prospect_id"]) or {}
        it["enviado"] = pr.get("status") == "sent"
    return {"rodando": run, "existe": True, **data}


def revoke(tokens=None, all_failed_unsent=False):
    """Tira do ar (status 'revoked'; a pagina publica passa a mostrar 'indisponivel'). Em massa, so os reprovados que NAO foram enviados por e-mail."""
    from mockups import store
    st = status()
    if not st.get("existe"):
        return 0
    wanted = set(tokens or [])
    n = 0
    for it in st["itens"]:
        if it["ja_tirado"] or it["veredito"] != "reprova":
            continue
        if all_failed_unsent:
            if it["enviado"]:
                continue
        elif it["token"] not in wanted:
            continue
        store.set_status(it["token"], "revoked", "reavaliado: " + (it["motivo"] or "reprovado pelo juiz"))
        database.add_event(it["prospect_id"], "mockup_revoked", "esboco tirado do ar apos reavaliacao: " + (it["motivo"] or ""), {})
        n += 1
    return n
