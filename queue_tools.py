"""Fila de envio no painel: o que antes era `tools/diagnostico_fila.py`, `tools/followups.py` e `tools/ler_caixa.py`, agora como funcoes usadas pela tela.

`snapshot()` conta onde estao os leads; `approve_pending()` e `retry_temporary_failures()` agem; `next_in_queue()` lista os proximos a sair.
Leads do CNPJ ainda sem site verificado NAO entram na aprovacao manual: passam pela descoberta de site (site_finder).
"""
import re

import database
import validators

TRANSIENT = re.compile(r"timed out|timeout|connection|conex|forçado|forcado|reset|temporar|try again|(?<!\d)4[25]\d(?!\d)|4\.\d\.\d|greylist", re.I)
PERMANENT = re.compile(r"(?<!\d)5\d\d(?!\d)|5\.\d\.\d|does not exist|no such user|user unknown|n[aã]o existe|invalid", re.I)


def _suppressed():
    conn = database.get_db_connection()
    try:
        return {r[0].lower() for r in conn.execute("SELECT value FROM suppressions")}
    finally:
        conn.close()


def _group(p, supp):
    st = p["status"]
    email = (p["contact_email"] or "").strip()
    if st == "sent":
        return "enviado"
    if st == "approved":
        return "na_fila"
    if p["directory_source"] == "cnpj_receita" and st == "pending":
        return "cnpj_aguardando_site"
    if not email:
        return "sem_email_com_telefone" if (p["contact_whatsapp"] or p["contact_phone"] or "").strip() else "sem_contato"
    if validators.check_syntax(email)[0] != "valid":
        return "email_ruim"
    if email.lower() in supp or email.lower().rsplit("@", 1)[-1] in supp:
        return "bloqueado"
    if st == "rejected":
        return "rejeitado"
    if st == "failed":
        return "falhou_temporaria" if (TRANSIENT.search(p["error_message"] or "") and not PERMANENT.search(p["error_message"] or "")) else "falhou"
    if st == "pending":
        return "pendente_ok" if database.approval_gate(dict(p))[0] else "pendente_barrado"
    return "outro"


def snapshot():
    """{'grupos': {...}, 'aprovaveis': [ids], 'temporarias': [ids]}"""
    supp = _suppressed()
    conn = database.get_db_connection()
    rows = conn.execute("SELECT id, status, contact_email, contact_whatsapp, contact_phone, error_message, directory_source, website, is_directory FROM prospects "
                        "WHERE coalesce(is_international,0)=0").fetchall()
    conn.close()
    grupos, aprov, temp = {}, [], []
    for p in rows:
        g = _group(p, supp)
        grupos[g] = grupos.get(g, 0) + 1
        if g == "pendente_ok":
            aprov.append(p["id"])
        elif g == "falhou_temporaria":
            temp.append(p["id"])
    return {"grupos": grupos, "aprovaveis": aprov, "temporarias": temp}


def approve_pending():
    """Aprova os pendentes (que nao sao do CNPJ) com e-mail valido que passam em todas as portas. Nao envia nada. Devolve quantos."""
    ids = snapshot()["aprovaveis"]
    conn = database.get_db_connection()
    conn.executemany("UPDATE prospects SET status='approved', updated_at=datetime('now') WHERE id=? AND status='pending'", [(i,) for i in ids])
    conn.commit()
    conn.close()
    for i in ids:
        database.add_event(i, "approved_manual", "aprovado pelo painel", {})
    return len(ids)


def retry_temporary_failures():
    ids = snapshot()["temporarias"]
    conn = database.get_db_connection()
    conn.executemany("UPDATE prospects SET status='approved', error_message=NULL, updated_at=datetime('now') WHERE id=? AND status='failed'", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return len(ids)


def next_in_queue(n=15):
    import mockup_runner
    import prioritize
    leads = database.get_prospects(status_filter="approved")
    leads.sort(key=lambda x: (-prioritize.email_priority(x), x.get("created_at", "")))
    names = {"ready": "pronto", "pending": "a gerar", "tried": "sem esboço", "na": "não se aplica"}
    out = []
    for p in leads[:n]:
        out.append({"id": p["id"], "empresa": p["company_name"], "segmento": p.get("segment") or "", "cidade": (p.get("region") or "").split(" - ")[0],
                    "faixa": p.get("lane") or "", "esboco": names.get(mockup_runner.state(p), "")})
    return {"total": len(leads), "proximos": out}


def remove_from_queue(pid):
    p = database.get_prospect(pid)
    if not p or p.get("status") != "approved":
        return False
    database.update_prospect(pid, {"status": "pending"})
    database.add_event(pid, "queue_removed", "tirado da fila pelo painel", {})
    return True


def followups_due(n=10):
    import followup
    try:
        due = followup.due_list()
    except Exception:  # noqa: BLE001
        due = []
    return {"ligado": followup.enabled(), "total": len(due), "enviados_hoje": followup.sent_today(),
            "lista": [{"id": d["prospect"]["id"], "empresa": d["prospect"]["company_name"], "passo": d["step"], "atraso_dias": round(d["overdue_days"], 1) if isinstance(d["overdue_days"], (int, float)) else 0}
                      for d in due[:n]]}


def read_inbox(dry=False):
    import inbox
    try:
        st = inbox.check_inbox(dry=dry)
        return {"ok": True, "lidas": st["lidas"], "novas": st["novas"], "acoes": st["acoes"][:20], "simulacao": dry}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": str(e)[:200]}
