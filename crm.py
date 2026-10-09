"""Ficha do lead (linha do tempo) e tela de Resultados: tudo que o sistema registra, em portugues e sem precisar de comando.

Somente leitura. Alimenta /api/lead/<id> e /api/resultados.
"""
import json
import re
import time
from datetime import datetime, timedelta

import database

LABELS = {
    "prospect_created": ("Lead cadastrado", "🆕"), "site_checked": ("Site procurado", "🔎"), "site_search_empty": ("Busca de site sem resultado (vai tentar de novo)", "🔎"),
    "lane_assigned": ("Faixa de abordagem definida", "🧭"), "lane_skipped": ("Barrado pela faixa 'descartar'", "⛔"),
    "cnpj_approved": ("Aprovado para envio", "✅"), "cnpj_approve_blocked": ("Aprovação barrada pelas checagens", "⛔"),
    "mockup_generated": ("Esboço gerado", "🖼️"), "mockup_review": ("Esboço não liberado (revisão)", "🖼️"), "mockup_revoked": ("Esboço tirado do ar após reavaliação", "🖼️"),
    "email_sent": ("E-mail enviado", "✉️"), "followup_sent": ("Follow-up enviado", "↩️"), "followup_skipped": ("Follow-up barrado", "⛔"),
    "followup_failed": ("Falha no follow-up", "⚠️"), "expiry_notice_sent": ("Aviso de que o esboço vai vencer", "⏳"),
    "email_failed": ("Falha no envio", "⚠️"), "email_deferred": ("Envio adiado pelo provedor", "⏳"), "email_bounced": ("E-mail rejeitado (não existe)", "❌"),
    "email_bounced_soft": ("Rejeição temporária", "⚠️"), "email_blocked": ("Bloqueado antes do envio", "⛔"), "email_blocked_by_provider": ("Provedor bloqueou o envio", "⛔"),
    "email_invalid": ("E-mail inválido", "⛔"), "email_not_qualified": ("Fora do perfil (não enviado)", "⛔"), "email_regenerated": ("Texto do e-mail refeito", "✍️"),
    "email_replied": ("Respondeu ao e-mail", "💬"), "email_autoreply": ("Resposta automática (férias etc.)", "🤖"), "lead_hot": ("Resposta com interesse", "🔥"),
    "link_clicked": ("Clicou no link do portfólio", "👆"), "whatsapp_contacted": ("Contato por WhatsApp", "📱"), "whatsapp_outcome": ("Resultado do WhatsApp", "📱"),
    "qualified": ("Qualificado", "✅"), "qualification_rejected": ("Fora do perfil", "⛔"), "name_fixed": ("Nome da empresa corrigido", "✍️"),
    "alert_sent": ("Alerta enviado a você", "🔔"),
}
STAGE_LABELS = {"novo": "Novo", "contatado": "Contatado", "respondeu": "Respondeu", "interessado": "Interessado", "reuniao": "Reunião", "proposta": "Proposta",
                "ganho": "Ganho", "perdido": "Perdido", "descadastrou": "Pediu para sair", "invalido": "Inválido"}
LANE_LABELS = {"direta": "Direta", "personalizada": "Personalizada", "descartar": "Descartada"}


def label(etype, detail=None):
    if etype.startswith("stage:"):
        return f"Estágio: {STAGE_LABELS.get(etype[6:], etype[6:])}", "🏷️"
    return LABELS.get(etype, (etype.replace("_", " ").capitalize(), "•"))


def _fmt(ts):
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
    except Exception:  # noqa: BLE001
        return str(ts or "")


def timeline(pid):
    out = []
    for e in database.get_events(pid):
        if e["type"] in ("alert_sent", "site_search_empty"):
            continue
        txt, icon = label(e["type"], e.get("detail"))
        det = "" if e["type"] in ("prospect_created", "lead_hot") else (e.get("detail") or "")[:240]
        out.append({"quando": _fmt(e["created_at"]), "icone": icon, "texto": txt, "detalhe": det})
    return out


def _mockup_info(pid):
    try:
        from mockups import store
        import mailer
        m = store.latest(pid)
        if not m:
            return None
        ts = lambda v: datetime.fromtimestamp(v).strftime("%d/%m %H:%M") if v else ""  # noqa: E731
        info = {"status": m["status"], "motivo": m.get("reason") or "", "aberturas": m.get("views") or 0, "primeira": ts(m.get("first_view_at")),
                "ultima": ts(m.get("last_view_at")), "vence": ts(m.get("expires_at")), "token": m["token"], "expirado": (m.get("expires_at") or 0) < time.time()}
        if m["status"] == "ready":
            info["url"] = f"{mailer.public_base_url()}/p/{m['token']}/"
        return info
    except Exception:  # noqa: BLE001
        return None


def lead_sheet(pid):
    p = database.get_prospect(pid)
    if not p:
        return None
    ev = database.get_events(pid)
    count = lambda t: sum(1 for e in ev if e["type"] == t)  # noqa: E731
    mk = _mockup_info(pid)
    return {
        "id": pid, "empresa": p.get("company_name"), "segmento": p.get("segment") or "", "regiao": p.get("region") or "", "site": p.get("website") or "",
        "email": p.get("contact_email") or "", "telefone": p.get("contact_phone") or "", "whatsapp": p.get("contact_whatsapp") or "",
        "estagio": p.get("stage") or "novo", "estagio_nome": STAGE_LABELS.get(p.get("stage") or "novo", "Novo"), "status": p.get("status"),
        "faixa": p.get("lane") or "", "faixa_nome": LANE_LABELS.get(p.get("lane") or "", ""), "enviado_em": _fmt(p.get("sent_at")) if p.get("sent_at") else "",
        "assunto": p.get("email_subject") or "", "corpo": p.get("email_body") or "", "notas": (p.get("notes") or "")[:600],
        "contagens": {"emails": count("email_sent"), "followups": count("followup_sent"), "respostas": count("email_replied"), "cliques": count("link_clicked"),
                      "aberturas_esboco": (mk or {}).get("aberturas", 0)},
        "esboco": mk, "linha_do_tempo": list(reversed(timeline(pid))),
    }


# ---------------------------------------------------------------------------------------- resultados ----
def _since(days):
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _ids(conn, types, since):
    q = "SELECT DISTINCT prospect_id FROM events WHERE created_at >= ? AND type IN (%s)" % ",".join("?" * len(types))
    return {r[0] for r in conn.execute(q, [since] + list(types))}


def resultados(days=30):
    since = _since(days)
    conn = database.get_db_connection()
    emailed = {r["prospect_id"] for r in conn.execute("SELECT DISTINCT prospect_id FROM events WHERE type='email_sent' AND created_at >= ?", (since,))}
    followups = conn.execute("SELECT COUNT(*) FROM events WHERE type='followup_sent' AND created_at >= ?", (since,)).fetchone()[0]
    replied = _ids(conn, ("email_replied",), since)
    hot = _ids(conn, ("lead_hot", "stage:interessado"), since)
    won = _ids(conn, ("stage:ganho",), since)
    unsub = _ids(conn, ("stage:descadastrou",), since)
    bounced = _ids(conn, ("email_bounced",), since)
    clicked = _ids(conn, ("link_clicked",), since)
    opened = set()
    try:
        from mockups import store
        lim = time.time() - days * 86400
        opened = {m["prospect_id"] for m in store.list_all() if m.get("views") and (m.get("last_view_at") or 0) >= lim and m.get("prospect_id")}
    except Exception:  # noqa: BLE001
        pass
    meta = {}
    for r in conn.execute("SELECT id, company_name, segment, region, lane FROM prospects"):
        meta[r["id"]] = dict(r)
    n = len(emailed)
    pct = lambda x: round(100.0 * len(x & emailed) / n, 1) if n else 0.0  # noqa: E731
    kpi = {"enviados": n, "followups": followups, "esboco_aberto": len(opened & emailed), "cliques": len(clicked & emailed), "respostas": len(replied & emailed),
           "interessados": len(hot & emailed), "ganhos": len(won), "pediram_sair": len(unsub & emailed), "rejeitados": len(bounced & emailed),
           "taxas": {"esboco_aberto": pct(opened), "cliques": pct(clicked), "respostas": pct(replied), "interessados": pct(hot), "pediram_sair": pct(unsub), "rejeitados": pct(bounced)}}

    def group(keyfn):
        g = {}
        for pid in emailed:
            m = meta.get(pid)
            if not m:
                continue
            k = keyfn(m) or "-"
            row = g.setdefault(k, {"nome": k, "enviados": 0, "esboco_aberto": 0, "respostas": 0, "interessados": 0, "ganhos": 0})
            row["enviados"] += 1
            row["esboco_aberto"] += pid in opened
            row["respostas"] += pid in replied
            row["interessados"] += pid in hot
            row["ganhos"] += pid in won
        return sorted(g.values(), key=lambda r: -r["enviados"])[:12]

    por_faixa = group(lambda m: LANE_LABELS.get(m.get("lane") or "", "Sem faixa (antes das faixas)"))
    por_segmento = group(lambda m: m.get("segment"))
    por_cidade = group(lambda m: (m.get("region") or "").split(" - ")[0].strip())
    serie = []
    for i in range(min(days, 14) - 1, -1, -1):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        e = conn.execute("SELECT COUNT(*) FROM events WHERE type='email_sent' AND date(created_at)=?", (d,)).fetchone()[0]
        r = conn.execute("SELECT COUNT(*) FROM events WHERE type='email_replied' AND date(created_at)=?", (d,)).fetchone()[0]
        serie.append({"dia": d[5:], "enviados": e, "respostas": r})
    feed = []
    interesting = ("email_replied", "lead_hot", "link_clicked", "email_bounced", "stage:interessado", "stage:ganho", "stage:descadastrou", "stage:perdido", "stage:reuniao")
    rows = conn.execute("SELECT prospect_id, type, detail, created_at FROM events WHERE created_at >= ? AND type IN (%s) ORDER BY id DESC LIMIT 40" % ",".join("?" * len(interesting)),
                        [since] + list(interesting)).fetchall()
    for r in rows:
        txt, icon = label(r["type"])
        feed.append({"id": r["prospect_id"], "empresa": (meta.get(r["prospect_id"]) or {}).get("company_name", "?"), "icone": icon, "texto": txt,
                     "detalhe": (r["detail"] or "")[:120], "quando": _fmt(r["created_at"])})
    conn.close()
    return {"dias": days, "kpi": kpi, "por_faixa": por_faixa, "por_segmento": por_segmento, "por_cidade": por_cidade, "serie": serie, "atividade": feed}


# ---------------------------------------------------------------------------------------- cliques ----
def _click_sign(pid):
    import hashlib
    import hmac
    import security
    return hmac.new(security.get_secret_key().encode("utf-8"), f"r:{pid}".encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def click_token(pid):
    return f"{pid}.{_click_sign(pid)}"


def verify_click_token(token):
    import hmac
    try:
        pid_s, sig = (token or "").split(".", 1)
        pid = int(pid_s)
    except (ValueError, AttributeError):
        return None
    return pid if hmac.compare_digest(sig, _click_sign(pid)) else None


def track_links(prospect_id, body, base_url, portfolio_url):
    """Troca o link do portfolio no e-mail por um link NOSSO que registra o clique e redireciona. Sem pixel de abertura."""
    if not portfolio_url or portfolio_url not in (body or ""):
        return body
    return body.replace(portfolio_url, f"{base_url.rstrip('/')}/r/{click_token(prospect_id)}")
