"""T3 do PLANO_PROSPECTADOR: le a caixa de entrada (IMAP) e transforma o que chega em fatos do funil.

- RESPOSTAS de leads -> estagio ('respondeu' / 'interessado' / 'perdido' / 'descadastrou') + evento `email_replied`; "SAIR" bloqueia o e-mail.
- REJEICOES tardias (MAILER-DAEMON) -> hard bounce bloqueia o e-mail e marca o lead 'invalido'; soft bounce so registra.
- RESPOSTAS AUTOMATICAS (ferias, fora do escritorio) -> so registra; nao conta como resposta.
- Somente LEITURA da caixa (BODY.PEEK: nao marca como lida, nao apaga nada). Cada mensagem so e processada uma vez (Message-ID).
- Desligado por padrao: configuracao `imap_enabled` = 0/1. Usa o mesmo usuario/senha do SMTP; servidor em `imap_host`.
"""
import email
import imaplib
import json
import re
import time
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr

import database

FREE_MAIL = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "bol.com.br", "uol.com.br", "terra.com.br", "icloud.com", "live.com", "msn.com"}
UPGRADABLE = (None, "", "novo", "contatado", "respondeu")      # nunca rebaixa um lead que ja esta mais adiante no funil

RE_AUTO_SUBJ = re.compile(r"resposta autom[aá]tica|out of office|fora do escrit[oó]rio|auto.?reply|automatic reply|ausente|f[eé]rias", re.I)
RE_BOUNCE_SUBJ = re.compile(r"undeliver|delivery status|mail delivery|returned mail|failure notice|falha na entrega|n[aã]o foi poss[ií]vel entregar|mensagem n[aã]o entregue|delivery has failed", re.I)
RE_UNSUB = re.compile(r"\bsair\b|\bremov(a|er|am|endo)\b|descadastr|n[aã]o (quero|desejo|queremos) (mais )?receber|pare de (enviar|mandar)|cancel(e|ar) (o )?(envio|inscri)|unsubscribe|\bspam\b|me (tire|retire|exclua)", re.I)
RE_NEGATIVE = re.compile(r"sem interesse|n[aã]o (tenho|temos|h[aá]) interesse|n[aã]o (precisamos|preciso|queremos|quero)|j[aá] (temos|tenho) (um )?(site|empresa|agencia|ag[eê]ncia)|agrade[cç]o,? mas|n[aã]o [eé] o momento|no momento n[aã]o", re.I)
RE_POSITIVE = re.compile(r"tenho interesse|temos interesse|interessad|gostei|pode (me )?(enviar|mandar|ligar|apresentar|mostrar)|vamos (conversar|marcar|falar)|podemos (conversar|marcar|falar)|quanto custa|qual (o )?(valor|pre[cç]o)|or[cç]amento|proposta|me (ligue|liga|chame|chama)", re.I)
RE_QUOTE_START = re.compile(r"^(em .{5,80} escreveu:|on .{5,80} wrote:|-{2,}\s*(mensagem original|original message)|de:\s|from:\s|_{5,})", re.I)


def _s(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:  # noqa: BLE001
        return v or ""


def _text(msg):
    """Texto simples da mensagem (so a parte nova, sem as linhas citadas)."""
    parts = []
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
            try:
                parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
    raw = "\n".join(parts)
    out = []
    for line in raw.splitlines():
        if line.lstrip().startswith(">"):
            continue
        if RE_QUOTE_START.match(line.strip()):
            break
        out.append(line)
    return "\n".join(out).strip()


def _all_text(msg):
    chunks = []
    for part in msg.walk():
        if part.get_content_type() in ("text/plain", "message/delivery-status", "message/rfc822", "text/rfc822-headers"):
            try:
                pl = part.get_payload(decode=True)
                if pl:
                    chunks.append(pl.decode("utf-8", "replace"))
                elif part.is_multipart() or isinstance(part.get_payload(), list):
                    for sub in part.get_payload():
                        chunks.append(str(sub))
            except Exception:  # noqa: BLE001
                pass
    return "\n".join(chunks)


def classify(raw_bytes, known_emails=()):
    """{kind, from, subject, message_id, text, recipient, hard} para uma mensagem bruta.
    kind: bounce | autoreply | unsub | negative | positive | reply."""
    msg = email.message_from_bytes(raw_bytes)
    frm = parseaddr(_s(msg.get("From")))[1].lower()
    subj = _s(msg.get("Subject"))
    mid = (msg.get("Message-ID") or "").strip()
    res = {"from": frm, "subject": subj, "message_id": mid, "kind": "reply", "text": "", "recipient": None, "hard": None}

    is_dsn = msg.get_content_type() == "multipart/report" or "delivery-status" in str(msg.get("Content-Type", "")).lower()
    if re.search(r"mailer-daemon|postmaster|mail.delivery", frm) or is_dsn or RE_BOUNCE_SUBJ.search(subj):
        blob = _all_text(msg)
        m = re.search(r"(?:final|original)-recipient:\s*(?:rfc822;)?\s*<?([\w.+-]+@[\w.-]+\.\w+)", blob, re.I)
        rcpt = m.group(1).lower() if m else None
        if not rcpt:
            cands = [e.lower() for e in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", blob)]
            rcpt = next((e for e in cands if e in known_emails), None)
        st = re.search(r"\b([245])\.\d{1,3}\.\d{1,3}\b", blob)
        res.update(kind="bounce", recipient=rcpt, hard=(st.group(1) == "5") if st else bool(re.search(r"user unknown|does not exist|no such user|n[aã]o existe|mailbox not found|invalid recipient", blob, re.I)))
        return res

    auto = str(msg.get("Auto-Submitted", "no")).lower() != "no" or msg.get("X-Autoreply") or msg.get("X-Autorespond") or \
        str(msg.get("Precedence", "")).lower() in ("auto_reply", "bulk", "junk") or RE_AUTO_SUBJ.search(subj)
    text = _text(msg)
    res["text"] = text[:2000]
    if auto:
        res["kind"] = "autoreply"
    elif RE_UNSUB.search(text) and len(text) < 600:
        res["kind"] = "unsub"
    elif RE_NEGATIVE.search(text):
        res["kind"] = "negative"
    elif RE_POSITIVE.search(text):
        res["kind"] = "positive"
    return res


def _prospect_index():
    """({email: prospect_id}, {dominio_proprio: prospect_id}) dos leads que ja receberam e-mail."""
    conn = database.get_db_connection()
    rows = conn.execute("SELECT id, contact_email FROM prospects WHERE contact_email IS NOT NULL AND contact_email != '' AND status IN ('sent','failed','rejected')").fetchall()
    conn.close()
    by_email, by_domain = {}, {}
    for r in rows:
        e = (r["contact_email"] or "").strip().lower()
        by_email[e] = r["id"]
        d = e.rsplit("@", 1)[-1]
        if d and d not in FREE_MAIL:
            by_domain.setdefault(d, r["id"])
    return by_email, by_domain


def _already(mid):
    if not mid:
        return False
    conn = database.get_db_connection()
    row = conn.execute("SELECT 1 FROM events WHERE type IN ('email_replied','email_autoreply','email_bounced','email_bounced_soft') AND meta LIKE ? LIMIT 1", (f'%"mid": {json.dumps(mid)}%',)).fetchone()
    conn.close()
    return bool(row)


def apply(res, by_email, by_domain, dry=False):
    """Aplica o resultado ao funil. Devolve uma frase curta do que foi (ou seria) feito."""
    kind = res["kind"]
    if kind == "bounce":
        pid = by_email.get(res["recipient"] or "")
        if not pid:
            return "rejeicao de e-mail que nao e de nenhum lead (ignorada)"
        if dry:
            return f"[simulacao] rejeicao {'definitiva' if res['hard'] else 'temporaria'} de {res['recipient']} (lead {pid})"
        if res["hard"]:
            database.add_suppression(res["recipient"], "rejeicao definitiva (caixa de entrada)", pid)
            database.add_event(pid, "email_bounced", res["subject"][:200], {"email": res["recipient"], "mid": res["message_id"], "late": True})
            if (database.get_prospect(pid).get("stage") or "novo") in UPGRADABLE:
                database.set_stage(pid, "invalido", note="e-mail rejeitado")
            return f"rejeicao definitiva: {res['recipient']} bloqueado, lead {pid} marcado invalido"
        database.add_event(pid, "email_bounced_soft", res["subject"][:200], {"email": res["recipient"], "mid": res["message_id"]})
        return f"rejeicao temporaria registrada (lead {pid})"

    pid = by_email.get(res["from"]) or by_domain.get(res["from"].rsplit("@", 1)[-1] if "@" in res["from"] else "")
    if not pid:
        return "mensagem de remetente que nao e lead (ignorada)"
    meta = {"from": res["from"], "mid": res["message_id"], "kind": kind}
    if kind == "autoreply":
        if not dry:
            database.add_event(pid, "email_autoreply", res["subject"][:200], meta)
        return f"{'[simulacao] ' if dry else ''}resposta automatica (lead {pid}): so registrada"
    prospect = database.get_prospect(pid)
    cur = prospect.get("stage") or "novo"
    note = res["text"][:160].replace("\n", " ")
    if dry:
        return f"[simulacao] {kind} do lead {pid}: '{note[:70]}'"
    database.add_event(pid, "email_replied", note, meta)
    if kind == "unsub":
        database.add_suppression(prospect.get("contact_email") or res["from"], "pediu para sair por e-mail", pid)
        database.set_stage(pid, "descadastrou", note="pediu para sair (resposta por e-mail)")
        return f"lead {pid} pediu para sair: bloqueado"
    if cur in UPGRADABLE or cur == "respondeu":
        if kind == "negative":
            database.set_stage(pid, "perdido", note="sem interesse (resposta por e-mail)")
        elif kind == "positive":
            database.set_stage(pid, "interessado", note="resposta positiva por e-mail")
            database.add_event(pid, "lead_hot", note, {"via": "email"})
        elif cur != "respondeu":
            database.set_stage(pid, "respondeu", note="respondeu por e-mail")
    return f"lead {pid}: {kind}"


def imap_fetch(days=14, limit=300):
    """Le a caixa (somente leitura). Devolve [raw_bytes]. Levanta Exception se nao conseguir conectar."""
    host = database.get_setting("imap_host", "imap.hostinger.com")
    user = database.get_setting("smtp_user", "")
    pwd = database.get_setting("smtp_password", "")
    if not (user and pwd):
        raise Exception("sem usuario/senha de e-mail configurados")
    M = imaplib.IMAP4_SSL(host, 993, timeout=30)
    try:
        M.login(user, pwd)
        M.select("INBOX", readonly=True)
        since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        typ, data = M.search(None, "SINCE", since)
        ids = (data[0].split() if data and data[0] else [])[-limit:]
        out = []
        for i in ids:
            typ, d = M.fetch(i, "(BODY.PEEK[])")
            if typ == "OK" and d and isinstance(d[0], tuple):
                out.append(d[0][1])
        return out
    finally:
        try:
            M.logout()
        except Exception:  # noqa: BLE001
            pass


def check_inbox(fetch=imap_fetch, dry=False, days=14):
    """Processa a caixa. Devolve {'lidas', 'novas', 'acoes': [frases]}. Nunca processa a mesma mensagem duas vezes."""
    raws = fetch(days=days) if fetch is imap_fetch else fetch()
    by_email, by_domain = _prospect_index()
    known = set(by_email)
    stats = {"lidas": len(raws), "novas": 0, "acoes": []}
    for raw in raws:
        try:
            res = classify(raw, known)
        except Exception:  # noqa: BLE001
            continue
        if _already(res["message_id"]):
            continue
        a = apply(res, by_email, by_domain, dry=dry)
        if "ignorada" not in a:
            stats["novas"] += 1
            stats["acoes"].append(a)
    return stats


_last = {"t": 0.0}


def maybe_check(min_interval_s=600):
    """Chamada pelo piloto automatico: se ligado, confere a caixa no maximo a cada 10 minutos. Nunca levanta excecao."""
    try:
        if database.get_setting("imap_enabled", "0") != "1" or time.time() - _last["t"] < min_interval_s:
            return None
        _last["t"] = time.time()
        return check_inbox()
    except Exception as e:  # noqa: BLE001
        return {"erro": str(e)[:200]}
