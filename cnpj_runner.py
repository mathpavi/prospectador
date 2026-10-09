"""Importacao de CNPJ pelo painel: inicia `tools/importar_cnpj.py` em segundo plano (processo separado, log em DATA_DIR) e informa o andamento.

Uma importacao por vez. O processo sobrevive a fechar o navegador; um deploy/reinicio do servico o encerra (e pode ser retomado: ja lidos ficam registrados).
"""
import os
import re
import sqlite3
import subprocess
import sys
import time

import database

ROOT = os.path.dirname(os.path.abspath(__file__))
_proc = {"p": None}


def _dir():
    return os.environ.get("DATA_DIR", ROOT)


def log_path():
    return os.path.join(_dir(), "importar_cnpj.log")


def pid_path():
    return os.path.join(_dir(), "importar_cnpj.pid")


def _alive(pid):
    p = _proc["p"]
    if p is not None and p.pid == pid:
        return p.poll() is None
    if os.name != "nt":
        return os.path.exists(f"/proc/{pid}")           # depois de reiniciar o servico nao ha objeto Popen: confere pelo /proc (Linux)
    return False


def running():
    try:
        pid = int(open(pid_path()).read().strip())
    except Exception:  # noqa: BLE001
        return False
    return _alive(pid)


def start(limit=3000):
    if running():
        return False, "Já existe uma importação em andamento."
    limit = max(100, min(int(limit), 50000))
    lf = open(log_path(), "ab", buffering=0)
    lf.write(f"\n--- {time.strftime('%H:%M:%S')} importacao iniciada pelo painel (limite {limit}) ---\n".encode("utf-8"))
    kw = {"start_new_session": True} if os.name != "nt" else {}
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "importar_cnpj.py"), "--importar", "--limite", str(limit)], stdout=lf, stderr=subprocess.STDOUT,
                         cwd=ROOT, env=dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8"), **kw)
    _proc["p"] = p
    open(pid_path(), "w").write(str(p.pid))
    return True, "Importação iniciada."


def _tail(n=14):
    try:
        with open(log_path(), "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 6000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except Exception:  # noqa: BLE001
        return []
    return lines[-n:]


def _stage_stats():
    path = os.path.join(_dir(), "cnpj_stage.db")
    if not os.path.exists(path):
        return {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
        out = {"empresas_no_banco": con.execute("SELECT COUNT(*) FROM estab").fetchone()[0],
               "ainda_nao_importadas": con.execute("SELECT COUNT(*) FROM estab WHERE importado=0").fetchone()[0],
               "arquivos_lidos": con.execute("SELECT COUNT(*) FROM done").fetchone()[0]}
        con.close()
        return out
    except Exception:  # noqa: BLE001
        return {}


def status():
    lines = _tail()
    prog = None
    for ln in reversed(lines):
        m = re.search(r"(\d+) de (\d+) MB", ln)
        if m:
            prog = round(100.0 * int(m.group(1)) / max(1, int(m.group(2))))
            break
    last = next((ln for ln in reversed(lines) if " de " not in ln or "MB" not in ln), "")
    import site_finder
    conn = database.get_db_connection()
    leads = conn.execute("SELECT COUNT(*) FROM prospects WHERE directory_source='cnpj_receita'").fetchone()[0]
    aprovados = conn.execute("SELECT COUNT(*) FROM prospects WHERE directory_source='cnpj_receita' AND status='approved'").fetchone()[0]
    enviados = conn.execute("SELECT COUNT(*) FROM prospects WHERE directory_source='cnpj_receita' AND status='sent'").fetchone()[0]
    conn.close()
    return {"rodando": running(), "progresso_download": prog, "ultima_linha": last.strip()[:200], "log": [l for l in lines if " de " not in l or "MB" not in l][-8:],
            "estagio": _stage_stats(), "leads_do_cnpj": leads, "aguardando_site": site_finder.backlog(), "aprovados": aprovados, "enviados": enviados}
