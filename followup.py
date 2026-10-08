"""C1 do PLANO_PROSPECTADOR: follow-up automatico por e-mail (dias 3, 7 e 14 depois do primeiro e-mail), que PARA sozinho
quando a pessoa responde, descadastra, e-mail e bloqueado, ou o lead muda de estagio.

- Desligado por padrao (configuracao `followup_enabled` = 0/1). Limite proprio por dia (`followup_daily_limit`, padrao 8),
  e somado ao limite diario de e-mails (`daily_email_limit`).
- Honesto e curto: 3 mensagens com enfoques diferentes (lembrete, pergunta, despedida). O link do esboco so entra se ele ainda estiver no ar.
- Nao mexe no status do prospect (continua 'sent'); o historico fica em eventos `followup_sent` (meta: passo).
"""
import random
import zlib
from datetime import datetime

import database
import email_msg
import validators
import whatsapp_msg as wm

SCHEDULE = (3, 7, 14)                       # dias depois do PRIMEIRO e-mail
MIN_GAP_DAYS = 2                            # nunca dois follow-ups em menos de 2 dias
STOP_STAGES = ("respondeu", "interessado", "reuniao", "proposta", "ganho", "perdido", "descadastrou", "invalido")


def _parse(s):
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:  # noqa: BLE001
        return None


def enabled():
    return database.get_setting("followup_enabled", "0") == "1"


def _int_setting(key, default):
    try:
        return int(database.get_setting(key, str(default)))
    except Exception:  # noqa: BLE001
        return default


def sent_today():
    """Follow-ups enviados hoje (contam no limite diario)."""
    conn = database.get_db_connection()
    row = conn.execute("SELECT COUNT(*) c FROM events WHERE type='followup_sent' AND created_at >= ?", (database.get_today_start_str(),)).fetchone()
    conn.close()
    return row["c"] if row else 0


def _followup_history(conn, pid):
    rows = conn.execute("SELECT created_at FROM events WHERE prospect_id=? AND type='followup_sent' ORDER BY id", (pid,)).fetchall()
    return [_parse(r["created_at"]) for r in rows]


def due_list(now=None, max_age_days=None):
    """[{prospect, step, overdue_days}] dos follow-ups devidos agora, o mais atrasado primeiro."""
    now = now or database.get_now().replace(tzinfo=None)
    max_age = max_age_days if max_age_days is not None else _int_setting("followup_max_age_days", 30)
    conn = database.get_db_connection()
    rows = conn.execute("SELECT * FROM prospects WHERE status='sent' AND sent_at IS NOT NULL AND contact_email IS NOT NULL AND contact_email != ''").fetchall()
    out = []
    for r in rows:
        p = dict(r)
        if (p.get("stage") or "novo") in STOP_STAGES:
            continue
        first = _parse(p["sent_at"])
        if not first:
            continue
        age = (now - first).total_seconds() / 86400
        if age > max_age:
            continue
        if validators.check_syntax(p["contact_email"])[0] != "valid":      # lixo como 'logo@2x.png': nunca tentar
            continue
        if conn.execute("SELECT 1 FROM events WHERE prospect_id=? AND type='followup_skipped' LIMIT 1", (p["id"],)).fetchone():
            continue                                                         # ja foi barrado (e-mail invalido/bloqueado): nao insistir
        hist = _followup_history(conn, p["id"])
        n = len(hist)
        if n >= len(SCHEDULE) or age < SCHEDULE[n]:
            continue
        if hist and hist[-1] and (now - hist[-1]).total_seconds() / 86400 < MIN_GAP_DAYS:
            continue
        out.append({"prospect": p, "step": n + 1, "overdue_days": age - SCHEDULE[n]})
    conn.close()
    try:
        out += expiring_list()
    except Exception:  # noqa: BLE001
        pass
    out.sort(key=lambda x: -x["overdue_days"])
    return out


def expiring_list(now_ts=None, within_days=2.5):
    """C3: esbocos prontos que vencem nos proximos dias, de leads que ainda estao em conversa e nao foram avisados."""
    import time
    from mockups import store
    now_ts = now_ts or time.time()
    out = []
    conn = database.get_db_connection()
    for m in store.list_all():
        if m.get("status") != "ready" or not m.get("prospect_id"):
            continue
        left = (m["expires_at"] - now_ts) / 86400
        if not (0 < left <= within_days):
            continue
        p = conn.execute("SELECT * FROM prospects WHERE id=?", (m["prospect_id"],)).fetchone()
        if not p or p["status"] != "sent" or not p["contact_email"] or (p["stage"] or "novo") in STOP_STAGES:
            continue
        done = conn.execute("SELECT 1 FROM events WHERE prospect_id=? AND type='expiry_notice_sent' AND meta LIKE ? LIMIT 1", (p["id"], f'%"token": "{m["token"]}"%')).fetchone()
        sent_mail = conn.execute("SELECT 1 FROM events WHERE prospect_id=? AND type IN ('email_sent','followup_sent') LIMIT 1", (p["id"],)).fetchone()
        if done or not sent_mail:
            continue
        out.append({"prospect": dict(p), "step": "aviso", "token": m["token"], "expires_at": m["expires_at"], "overdue_days": 100 - left})
    conn.close()
    return out


def build_expiry(prospect, sender, url, expires_at):
    from datetime import datetime as _dt
    company = wm.clean_company_name(prospect.get("company_name"), prospect.get("website"))
    pn = wm.partner_first_name(prospect.get("socios"))
    wa = (sender.get("whatsapp") or "").strip()
    full = (sender.get("name") or "Matheus Paviani").strip()
    when = _dt.fromtimestamp(expires_at).strftime("%d/%m")
    rng = random.Random(zlib.crc32(f"{prospect.get('id')}|exp".encode("utf-8")))
    subject = rng.choice([f"O esboço da {company} sai do ar em {when}", f"Aviso: esboço da {company} disponível até {when}"])
    nl = chr(10)
    body = (nl * 2).join([
        f"Olá, {pn}," if pn else "Olá,",
        f"Só um aviso: o esboço do site da {company} fica disponível até {when} e depois sai do ar automaticamente." + nl + str(url),
        "Se quiser mais alguns dias para ver com calma, ou pedir ajustes, é só me responder" + (f" aqui ou no WhatsApp {wa}." if wa else " por aqui.") + " Posso manter no ar por mais uma semana.",
        "Abraço," + nl + full])
    return subject, body


def can_send_today():
    cap = _int_setting("followup_daily_limit", 8)
    total = _int_setting("daily_email_limit", 20)
    done = sent_today()
    return done < cap and (database.get_sent_count_today() + done) < total


def _mockup_url(pid):
    try:
        import mockup_runner
        return mockup_runner._url_for(pid)
    except Exception:  # noqa: BLE001
        return None


def build_followup(prospect, step, sender, mockup_url=None):
    """(assunto, corpo) do passo 1, 2 ou 3. Estavel por prospect+passo. Sem afirmar nada que nao seja verdade."""
    rng = random.Random(zlib.crc32(f"{prospect.get('id')}|{prospect.get('company_name')}|fu{step}".encode("utf-8")))
    pick = lambda opts: opts[rng.randrange(len(opts))]  # noqa: E731
    company = wm.clean_company_name(prospect.get("company_name"), prospect.get("website"))
    pn = wm.partner_first_name(prospect.get("socios"))
    wa = (sender.get("whatsapp") or "").strip()
    sname = wm.first_name(sender.get("name")) or "Matheus"
    full = (sender.get("name") or "Matheus Paviani").strip()
    own_site = wm.has_own_site(prospect)
    orig = (prospect.get("email_subject") or "").strip()
    subject = f"Retomando: {orig}" if orig else f"Sobre o site da {company}"
    greeting = pick([f"Olá, {pn}," if pn else "Olá,", f"Oi, {pn}, tudo bem?" if pn else "Oi, tudo bem?"])
    reach = f"Se preferir, me chame no WhatsApp {wa}." if wa else "Se preferir, é só responder este e-mail."
    exit_line = "Se não for o momento, sem problema: é só me avisar."
    link = ""
    if mockup_url:
        link = pick([f"O esboço que preparei continua disponível por enquanto:\n{mockup_url}", f"Caso queira rever, o esboço ainda está no ar:\n{mockup_url}"])
    if step == 1:
        intro = pick([f"Passando só para retomar meu e-mail sobre o site da {company}.", f"Retomo rapidamente meu e-mail de alguns dias atrás sobre o site da {company}.",
                      f"Escrevo de novo, sem querer insistir, sobre o site da {company}."])
        blocks = [greeting, intro, link, f"Se fizer sentido conversar, é só responder aqui{' ou chamar no WhatsApp ' + wa if wa else ''}.", exit_line]
    elif step == 2:
        q = pick([f"Uma pergunta rápida: quando um cliente novo procura a {company} pelo celular, o que ele encontra hoje?",
                  f"Uma pergunta rápida: o site da {company} já ajuda a receber pedidos de orçamento pelo celular?"]) if own_site else \
            f"Uma pergunta rápida: quando um cliente novo procura a {company} na internet, o que ele encontra hoje?"
        blocks = [greeting, q, "Posso te mostrar em 10 minutos como isso poderia ficar, sem compromisso.", link, reach]
    else:
        blocks = [greeting, pick(["Esta é minha última mensagem sobre o assunto, para não incomodar.", "Vou encerrar por aqui para não ocupar sua caixa de entrada."]),
                  link, f"Se mais adiante fizer sentido ter um site novo ou melhorar o atual, é só me chamar{' no WhatsApp ' + wa if wa else ' por aqui'}.", "Obrigado pela atenção!"]
    body = "\n\n".join(b for b in blocks if b)
    body += f"\n\n{pick(['Abraço,', 'Um abraço,', 'Atenciosamente,'])}\n{full}"
    return subject, body


def send_followup(prospect_id, step):
    """Envia o follow-up. Respeita bloqueios. Devolve (True, msg) ou levanta Exception com o motivo."""
    import mailer
    prospect = database.get_prospect(prospect_id)
    if not prospect:
        raise Exception("Prospect nao encontrado.")
    email_to = prospect.get("contact_email")
    status, why, norm = validators.check_email(email_to, check_dns=True)
    if status == "invalid":
        database.add_event(prospect_id, "followup_skipped", f"e-mail invalido ({why})", {"step": step})
        try:
            database.set_stage(prospect_id, "invalido", note=f"e-mail invalido ({why})")
        except Exception:  # noqa: BLE001
            pass
        raise Exception(mailer.REJECT_PREFIX + f"e-mail invalido ({why})")
    email_to = norm
    if database.is_suppressed(email_to):
        database.add_event(prospect_id, "followup_skipped", "e-mail na lista de bloqueio", {"step": step})
        raise Exception(mailer.REJECT_PREFIX + "e-mail na lista de bloqueio")
    url = _mockup_url(prospect_id)
    exp = None
    if step == "aviso":
        from mockups import store
        token = store.ready_tokens([prospect_id]).get(prospect_id)
        m = store.get(token) if token else None
        if not m:
            raise Exception(mailer.REJECT_PREFIX + "esboco ja saiu do ar")
        exp = {"token": token}
        subject, body = build_expiry(prospect, mailer._sender_info(), url, m["expires_at"])
    else:
        subject, body = build_followup(prospect, step, mailer._sender_info(), url)
    footer, unsub_url = mailer.build_footer(prospect_id, email_to)
    smtp_user = database.get_setting("smtp_user", "")
    headers = {}
    if unsub_url.startswith("https://"):
        headers["List-Unsubscribe"] = f"<{unsub_url}>" + (f", <mailto:{smtp_user}?subject=SAIR>" if smtp_user else "")
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    try:
        mailer.send_email_via_smtp(email_to, subject, body + footer, extra_headers=headers)
    except Exception as e:  # noqa: BLE001
        kind = mailer.classify_smtp_error(e)
        if kind == "hard":
            database.add_suppression(email_to, "rejeicao definitiva (hard bounce) no follow-up", prospect_id)
            database.add_event(prospect_id, "email_bounced", str(e)[:200], {"email": email_to, "followup": step})
        else:
            database.add_event(prospect_id, "followup_failed", str(e)[:200], {"email": email_to, "step": step, "kind": kind})
        raise Exception(f"Falha no follow-up: {e}")
    if exp:
        database.add_event(prospect_id, "expiry_notice_sent", subject, {"email": email_to, "token": exp["token"]})
        return True, "Aviso de expiracao enviado."
    database.add_event(prospect_id, "followup_sent", subject, {"email": email_to, "step": step, "mockup": bool(url)})
    return True, f"Follow-up {step} enviado."


def next_due():
    """O proximo follow-up a enviar agora (ou None): ligado, dentro do limite do dia e com algum devido."""
    if not enabled() or not can_send_today():
        return None
    lst = due_list()
    return lst[0] if lst else None
