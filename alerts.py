"""T4 do PLANO_PROSPECTADOR: avisa quando um lead esquenta e manda um resumo diario por e-mail (para VOCE, nao para leads).

Leads quentes (alerta imediato, uma vez por motivo):
  - respondeu com interesse (evento `lead_hot`, vindo da leitura da caixa de entrada ou do WhatsApp);
  - abriu o esboco (1a abertura) e voltou a abrir (3 ou mais aberturas): quem volta a ver o esboco esta pensando em contratar.
Resumo diario (uma vez por dia, na hora de `digest_hour`): o que aconteceu nas ultimas 24 h e o que fazer hoje.

Configuracao: `alerts_enabled` (1/0, padrao 1), `alert_email` (padrao: o e-mail do SMTP), `digest_hour` (padrao 8).
Tudo e engolido em caso de erro: avisar nunca pode derrubar o piloto.
"""
import json
import time
from datetime import datetime, timedelta

import database

_last = {"t": 0.0}


def enabled():
    return database.get_setting("alerts_enabled", "1") == "1"


def _to():
    return (database.get_setting("alert_email", "") or database.get_setting("smtp_user", "")).strip()


def notify(subject, body):
    """Envia um e-mail para voce mesmo. Devolve True/False."""
    import mailer
    to = _to()
    if not to:
        return False
    try:
        mailer.send_email_via_smtp(to, subject, body)
        return True
    except Exception:  # noqa: BLE001
        return False


def _alerted(conn, kind, key):
    return bool(conn.execute("SELECT 1 FROM events WHERE type='alert_sent' AND meta LIKE ? LIMIT 1", (f'%"k": {json.dumps(f"{kind}:{key}")}%',)).fetchone())


def _mark(pid, kind, key):
    database.add_event(pid, "alert_sent", kind, {"k": f"{kind}:{key}"})


def _line(p):
    ph = p.get("contact_whatsapp") or p.get("contact_phone") or ""
    return f"{p.get('company_name')}  |  {p.get('contact_email') or '-'}  |  {ph}"


def check_hot(now=None):
    """Envia os alertas imediatos pendentes. Devolve a lista de frases enviadas."""
    sent = []
    since = ((now or datetime.now()) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn = database.get_db_connection()
    hot = conn.execute("SELECT id, prospect_id, detail, created_at FROM events WHERE type='lead_hot' AND created_at >= ? ORDER BY id", (since,)).fetchall()
    todo = [(r["prospect_id"], "resposta", str(r["id"]), r["detail"]) for r in hot if not _alerted(conn, "resposta", str(r["id"]))]
    try:
        from mockups import store
        for m in store.list_all():
            if not m.get("prospect_id") or m.get("status") != "ready" or not m.get("views"):
                continue
            if (m.get("last_view_at") or 0) < time.time() - 2 * 86400:
                continue
            level = "volta" if m["views"] >= 3 else "abriu"
            if not _alerted(conn, f"esboco_{level}", m["token"]):
                todo.append((m["prospect_id"], f"esboco_{level}", m["token"], f"{m['views']} abertura(s)"))
    except Exception:  # noqa: BLE001
        pass
    conn.close()
    for pid, kind, key, detail in todo:
        p = database.get_prospect(pid)
        if not p or (p.get("stage") or "") in ("descadastrou", "invalido", "ganho", "perdido"):
            continue
        titulo = {"resposta": "respondeu com interesse", "esboco_abriu": "abriu o esboço", "esboco_volta": "voltou a ver o esboço"}[kind]
        body = (f"{p['company_name']} {titulo}.\n\n{_line(p)}\nSegmento: {p.get('segment') or '-'}\n"
                + (f"Detalhe: {detail}\n" if detail else "")
                + "\nO melhor momento para chamar é agora (WhatsApp ou ligação).")
        if notify(f"Lead quente: {p['company_name']} {titulo}", body):
            _mark(pid, kind, key)
            sent.append(f"{p['company_name']}: {titulo}")
    return sent


def digest_text(now=None):
    now = now or datetime.now()
    since = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    conn = database.get_db_connection()
    cnt = lambda t: conn.execute("SELECT COUNT(*) c FROM events WHERE type=? AND created_at >= ?", (t, since)).fetchone()["c"]  # noqa: E731
    stage = lambda s: conn.execute("SELECT COUNT(*) c FROM events WHERE type=? AND created_at >= ?", (f"stage:{s}", since)).fetchone()["c"]  # noqa: E731
    d = {"enviados": cnt("email_sent"), "followups": cnt("followup_sent"), "respostas": cnt("email_replied"), "quentes": cnt("lead_hot"),
         "rejeitados": cnt("email_bounced"), "whatsapp": cnt("whatsapp_contacted"), "esbocos": cnt("mockup_generated")}
    hot = conn.execute("SELECT DISTINCT prospect_id FROM events WHERE type='lead_hot' AND created_at >= ?", (since,)).fetchall()
    pend = conn.execute("SELECT COUNT(*) c FROM prospects WHERE stage='interessado'").fetchone()["c"]
    stages = {r["s"]: r["c"] for r in conn.execute("SELECT COALESCE(stage,'novo') s, COUNT(*) c FROM prospects GROUP BY 1")}
    ch = {s: stage(s) for s in ("ganho", "perdido", "descadastrou")}
    conn.close()
    views = []
    try:
        from mockups import store
        for m in store.list_all():
            if m.get("views") and (m.get("last_view_at") or 0) >= time.time() - 86400:
                views.append(f"  - {m['company']}: {m['views']} abertura(s)")
    except Exception:  # noqa: BLE001
        pass
    names = []
    for r in hot:
        p = database.get_prospect(r["prospect_id"])
        if p:
            names.append("  - " + _line(p))
    L = [f"Resumo do prospectador, últimas 24 h ({now.strftime('%d/%m/%Y')})", "",
         f"E-mails enviados: {d['enviados']}  |  follow-ups: {d['followups']}  |  esboços gerados: {d['esbocos']}",
         f"Respostas por e-mail: {d['respostas']}  |  interessados: {d['quentes']}  |  rejeitados: {d['rejeitados']}  |  WhatsApp manual: {d['whatsapp']}",
         f"Mudanças de estágio: ganho {ch['ganho']} · perdido {ch['perdido']} · descadastrou {ch['descadastrou']}", ""]
    if names:
        L += ["Responderam com interesse (chame hoje):"] + names + [""]
    if views:
        L += ["Esboços abertos:"] + views + [""]
    L += [f"Interessados aguardando seu retorno: {pend}",
          "Funil agora: " + ", ".join(f"{k} {v}" for k, v in sorted(stages.items(), key=lambda kv: -kv[1]))]
    return "\n".join(L)


def maybe_run(min_interval_s=300, now=None):
    """Chamada pelo piloto: alertas imediatos (a cada 5 min) e resumo diario (1x por dia, depois de `digest_hour`)."""
    try:
        if not enabled() or time.time() - _last["t"] < min_interval_s:
            return None
        _last["t"] = time.time()
        out = {"alertas": check_hot(now)}
        now = now or datetime.now()
        try:
            hour = int(database.get_setting("digest_hour", "8"))
        except Exception:  # noqa: BLE001
            hour = 8
        today = now.strftime("%Y-%m-%d")
        if now.hour >= hour and database.get_setting("digest_last_date", "") != today:
            if notify(f"Resumo diário do prospectador ({now.strftime('%d/%m')})", digest_text(now)):
                database.save_settings({"digest_last_date": today})
                out["resumo"] = True
        return out
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)[:200]}
