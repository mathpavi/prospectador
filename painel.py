"""U1 do PLANO_PROSPECTADOR: dados do Painel do Dia (o que fazer hoje, saude do sistema e funil).

`build()` so LE o banco. A tela (aba "Painel do Dia") consome /api/dia e usa o endpoint de estagio ja existente
(/api/prospects/<id>/stage) para os botoes: respondeu, interessado, reuniao, ganho, perdido.
"""
import json
import time
from datetime import datetime, timedelta

import database
import whatsapp_msg as wm

CLOSED = ("ganho", "perdido", "descadastrou", "invalido")
SCORE = {"interessado": 100, "lead_hot": 90, "esboco_volta": 70, "esboco_abriu": 50, "respondeu": 40}
WHY = {"interessado": "Marcado como interessado", "lead_hot": "Respondeu com interesse", "esboco_volta": "Voltou a ver o esboço",
       "esboco_abriu": "Abriu o esboço", "respondeu": "Respondeu"}


def _wa(p):
    digits, mobile, _ = wm.phone_info(p.get("contact_whatsapp") or p.get("contact_phone"))
    return (f"https://wa.me/{digits}" if digits and mobile else ""), (digits if digits else "")


def chamar_hoje(limit=25):
    conn = database.get_db_connection()
    since7 = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    cand = {}

    def add(pid, key, extra=None):
        cur = cand.get(pid)
        if not cur or SCORE[key] > SCORE[cur["key"]]:
            cand[pid] = {"key": key, **(extra or {})}

    for r in conn.execute("SELECT id FROM prospects WHERE stage='interessado'"):
        add(r["id"], "interessado")
    for r in conn.execute("SELECT DISTINCT prospect_id FROM events WHERE type='lead_hot' AND created_at >= ?", (since7,)):
        add(r["prospect_id"], "lead_hot")
    for r in conn.execute("SELECT DISTINCT prospect_id FROM events WHERE type='email_replied' AND created_at >= ?", (since7,)):
        add(r["prospect_id"], "respondeu")
    try:
        from mockups import store
        base = None
        try:
            import mailer
            base = mailer.public_base_url()
        except Exception:  # noqa: BLE001
            pass
        for m in store.list_all():
            if m.get("prospect_id") and m.get("status") == "ready" and m.get("views") and (m.get("last_view_at") or 0) >= time.time() - 3 * 86400:
                add(m["prospect_id"], "esboco_volta" if m["views"] >= 3 else "esboco_abriu",
                    {"views": m["views"], "esboco": f"{base}/p/{m['token']}/" if base else ""})
    except Exception:  # noqa: BLE001
        pass
    out = []
    for pid, c in cand.items():
        p = conn.execute("SELECT * FROM prospects WHERE id=?", (pid,)).fetchone()
        if not p:
            continue
        p = dict(p)
        if (p.get("stage") or "novo") in CLOSED:
            continue
        wa_url, digits = _wa(p)
        last = conn.execute("SELECT detail FROM events WHERE prospect_id=? AND type='email_replied' ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
        out.append({"id": pid, "empresa": wm.clean_company_name(p.get("company_name"), p.get("website")), "segmento": p.get("segment") or "",
                    "email": p.get("contact_email") or "", "whatsapp": wa_url, "telefone": digits, "estagio": p.get("stage") or "novo",
                    "motivo": WHY[c["key"]] + (f" ({c['views']}x)" if c.get("views") else ""), "esboco": c.get("esboco", ""),
                    "resposta": (last["detail"] if last and last["detail"] else ""), "score": SCORE[c["key"]]})
    conn.close()
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def build():
    now = datetime.now()
    since24 = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    since7 = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    today = database.get_today_start_str()
    conn = database.get_db_connection()
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    try:
        limit = int(database.get_setting("daily_email_limit", "20"))
    except Exception:  # noqa: BLE001
        limit = 20
    kpi = {"enviados_hoje": database.get_sent_count_today(), "limite_hoje": limit,
           "followups_hoje": one("SELECT COUNT(*) FROM events WHERE type='followup_sent' AND created_at >= ?", today),
           "respostas_24h": one("SELECT COUNT(*) FROM events WHERE type='email_replied' AND created_at >= ?", since24),
           "whatsapp_hoje": one("SELECT COUNT(*) FROM events WHERE type='whatsapp_contacted' AND created_at >= ?", today),
           "esbocos_24h": one("SELECT COUNT(*) FROM events WHERE type='mockup_generated' AND created_at >= ?", since24),
           "interessados": one("SELECT COUNT(*) FROM prospects WHERE stage='interessado'"),
           "ganhos": one("SELECT COUNT(*) FROM prospects WHERE stage='ganho'")}
    try:
        kpi["meta_whatsapp"] = int(database.get_setting("whatsapp_daily_goal", "15"))
    except Exception:  # noqa: BLE001
        kpi["meta_whatsapp"] = 15
    fila = one("SELECT COUNT(*) FROM prospects WHERE status='approved'")
    pendentes = one("SELECT COUNT(*) FROM prospects WHERE status='pending' AND contact_email IS NOT NULL AND contact_email != ''")
    enviados7 = one("SELECT COUNT(*) FROM events WHERE type IN ('email_sent','followup_sent') AND created_at >= ?", since7)
    rejeit7 = one("SELECT COUNT(*) FROM events WHERE type='email_bounced' AND created_at >= ?", since7)
    funil = {r["s"]: r["c"] for r in conn.execute("SELECT COALESCE(stage,'novo') s, COUNT(*) c FROM prospects GROUP BY 1")}
    conn.close()
    gs = database.get_setting
    sistema = {"piloto_envio": gs("autopilot_sender_enabled", "0") == "1", "piloto_busca": gs("autopilot_search_enabled", "0") == "1",
               "followup": gs("followup_enabled", "0") == "1", "caixa_entrada": gs("imap_enabled", "0") == "1", "alertas": gs("alerts_enabled", "1") == "1",
               "esbocos_no_email": gs("mockup_in_email", "1") == "1", "smtp": bool(gs("smtp_host", "") and gs("smtp_user", "") and gs("smtp_password", "")),
               "fila_aprovados": fila, "pendentes_com_email": pendentes}
    avisos = []
    if not sistema["smtp"]:
        avisos.append("E-mail (SMTP) não configurado: nada será enviado.")
    if sistema["piloto_envio"] and fila == 0:
        avisos.append("Fila de envio vazia: o piloto não tem leads aprovados com e-mail. Aprove leads ou revise os alvos de busca.")
    if pendentes and not sistema["piloto_envio"]:
        avisos.append(f"{pendentes} lead(s) com e-mail aguardando aprovação e o piloto de envio está desligado.")
    if enviados7 >= 20 and rejeit7 / max(enviados7, 1) > 0.05:
        avisos.append(f"Taxa de rejeição alta: {rejeit7} de {enviados7} e-mails nos últimos 7 dias. Revise a qualidade dos e-mails antes de enviar mais.")
    if not sistema["caixa_entrada"]:
        avisos.append("Leitura da caixa de entrada desligada: respostas e rejeições não entram no funil sozinhas.")
    if not sistema["followup"]:
        avisos.append("Follow-up automático desligado: quem não respondeu não é retomado.")
    return {"kpi": kpi, "chamar": chamar_hoje(), "sistema": sistema, "avisos": avisos, "funil": funil, "gerado_em": now.strftime("%H:%M")}
