import hashlib
import hmac
import os
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
import database
import email_msg
import mockup_runner
import qualify
import security
import validators
from datetime import datetime

REJECT_PREFIX = "REJEITADO: "      # o piloto trata mensagens com este prefixo como erro de validacao (sem recuo de rede)


# ---------------------------------------------------------------------------------------------
# Descadastro (E1): link assinado, rodape com identificacao e cabecalhos de um clique
# ---------------------------------------------------------------------------------------------
def public_base_url():
    return (os.environ.get('UNSUBSCRIBE_BASE_URL') or os.environ.get('MOCKUP_BASE_URL')
            or database.get_setting('public_base_url', '') or 'https://preview.paviani.net').rstrip('/')


def _sign(prospect_id, email):
    key = security.get_secret_key().encode('utf-8')
    return hmac.new(key, f"{prospect_id}:{(email or '').strip().lower()}".encode('utf-8'), hashlib.sha256).hexdigest()[:24]


def make_unsub_token(prospect_id, email):
    return f"{prospect_id}.{_sign(prospect_id, email)}"


def verify_unsub_token(token):
    """Devolve (prospect_id, email) se o token for valido para o e-mail ATUAL do prospect; senao (None, None)."""
    try:
        pid_s, sig = (token or '').split('.', 1)
        pid = int(pid_s)
    except (ValueError, AttributeError):
        return None, None
    prospect = database.get_prospect(pid)
    email = (prospect or {}).get('contact_email') or ''
    if not email or not hmac.compare_digest(sig, _sign(pid, email)):
        return None, None
    return pid, email


def build_footer(prospect_id, email):
    name = database.get_setting('sender_name', 'Matheus Paviani')
    company = database.get_setting('sender_company', '')
    address = database.get_setting('sender_address', '')
    doc = database.get_setting('sender_cnpj', '')
    url = f"{public_base_url()}/u/{make_unsub_token(prospect_id, email)}"
    lines = ["", "", "-----", name + (f" | {company}" if company else "")]
    if address:
        lines.append(address)
    if doc:
        lines.append(f"CNPJ {doc}")
    lines.append(f"Se preferir não receber mais mensagens minhas, responda SAIR ou acesse: {url}")
    return "\n".join(lines), url


def _smtp_domain(user):
    return user.rsplit('@', 1)[1] if user and '@' in user else None


def send_email_via_smtp(to_email, subject, body, extra_headers=None):
    # Load settings from database
    host = database.get_setting('smtp_host', '')
    port_str = database.get_setting('smtp_port', '465')
    user = database.get_setting('smtp_user', '')
    password = database.get_setting('smtp_password', '')
    security_mode = database.get_setting('smtp_security', 'SSL')
    sender_name = database.get_setting('sender_name', 'Matheus Paviani')

    if not host or not user or not password:
        raise Exception("Dados de SMTP incompletos nas configurações do sistema.")

    try:
        port = int(port_str)
    except:
        port = 465

    # Create email
    msg = MIMEMultipart()
    msg['From'] = f"{sender_name} <{user}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=_smtp_domain(user))
    for k, v in (extra_headers or {}).items():
        msg[k] = v

    # Body
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    server = None
    try:
        if security_mode == 'SSL':
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if security_mode == 'STARTTLS':
                server.ehlo()
                server.starttls()
                server.ehlo()

        server.login(user, password)
        server.sendmail(user, to_email, msg.as_string())
        return True
    except Exception as e:
        raise e
    finally:
        if server:
            try:
                server.quit()
            except:
                pass

def test_smtp_settings(host, port_str, user, password, security, sender_name, test_email=None):
    try:
        port = int(port_str)
    except:
        return False, "Porta SMTP inválida."

    recipient = test_email.strip() if (test_email and test_email.strip()) else user
    if not recipient:
        return False, "Nenhum destinatário de teste especificado."

    msg = MIMEMultipart()
    msg['From'] = f"{sender_name} <{user}>"
    msg['To'] = recipient
    msg['Subject'] = "Super Prospectador Paviani - Teste de Conexão SMTP"
    msg.attach(MIMEText("Parabéns! Suas configurações de SMTP estão funcionando perfeitamente.", 'plain', 'utf-8'))

    server = None
    try:
        if security == 'SSL':
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if security == 'STARTTLS':
                server.ehlo()
                server.starttls()
                server.ehlo()

        server.login(user, password)
        server.sendmail(user, recipient, msg.as_string())
        return True, "Conexão de teste SMTP realizada e e-mail enviado com sucesso!"
    except Exception as e:
        return False, f"Erro de conexão SMTP: {str(e)}"
    finally:
        if server:
            try:
                server.quit()
            except:
                pass


def classify_smtp_error(e):
    """'hard' (endereco inexistente), 'policy' (bloqueio por spam/reputacao do remetente), 'soft' (temporario) ou 'other'."""
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        pairs = list(e.recipients.values())
        code, text = (pairs[0][0], pairs[0][1]) if pairs else (0, b'')
    elif isinstance(e, smtplib.SMTPResponseException):
        code, text = e.smtp_code, e.smtp_error
    else:
        return 'other'
    text = (text.decode('utf-8', 'ignore') if isinstance(text, bytes) else str(text)).lower()
    if 400 <= code < 500:
        return 'soft'
    if 500 <= code < 600:
        if re.search(r"5\.7\.|spam|blocked|blacklist|reputation|policy|denied|rejected due", text):
            return 'policy'
        if re.search(r"5\.1\.|user unknown|no such user|does not exist|invalid recipient|mailbox (unavailable|not found)|unknown user|bad recipient", text):
            return 'hard'
        return 'hard' if code in (550, 551, 553, 501) else 'other'
    return 'other'


def _sender_info():
    return {"name": database.get_setting("sender_name", "Matheus Paviani"),
            "whatsapp": database.get_setting("sender_whatsapp", ""),
            "portfolio": database.get_setting("sender_portfolio", "")}


class LaneSkip(Exception):
    """Lead na faixa 'descartar': nao deve receber e-mail."""


def finalize_email(prospect, subject, body):
    """E4/M1, NO MOMENTO DO ENVIO: (assunto, corpo, url_do_esboco|None, regenerado).
    1) corpo antigo com promessa falsa ("desenvolvi um estudo visual"...) e regenerado com o modelo honesto;
    2) FAIXAS (lanes.py): descartar (levanta LaneSkip), personalizada (e-mail consultivo, sem esboco) ou direta (esboco + preco na 1a mensagem);
    3) o marcador {{ESBOCO}} vira o link do esboco (gerado na hora, se preciso) ou uma oferta honesta se nao houver esboco."""
    import lanes
    from mockups import store
    regenerated = False
    template_mode = database.get_setting("email_generation_mode", "template") != "ai"
    if template_mode and email_msg.is_legacy_body(body):
        subject, body = email_msg.build_email(prospect, _sender_info())
        regenerated = True
    url = None
    if template_mode and lanes.enabled() and prospect.get("id"):
        url = mockup_runner.ensure_mockup(prospect)                 # gera ou reaproveita o esboco: o veredito do juiz decide a faixa
        lane, why = lanes.classify(prospect, store.latest(prospect["id"]), mockup_runner.state(prospect))
        database.update_prospect(prospect["id"], {"lane": lane})
        database.add_event(prospect["id"], "lane_assigned", why, {"lane": lane})
        if lane == "descartar":
            raise LaneSkip(why)
        if lane == "personalizada":
            subject, body = email_msg.build_consultive(prospect, _sender_info(), database.get_setting("price_custom_from", "2500"))
            return subject, body, None, True
        if email_msg.PRECO_TOKEN not in body:                        # e-mail ja gravado antes dos precos: refaz no modelo atual (mesmos fatos)
            subject, body = email_msg.build_email(prospect, _sender_info())
            regenerated = True
        price = email_msg.price_line(database.get_setting, __import__("random").Random(prospect["id"]))
        body = email_msg.finalize_all(body, email_msg.esboco_paragraph(prospect, url), price)
        return subject, body, url, regenerated
    if email_msg.ESBOCO_TOKEN in body:
        url = mockup_runner.ensure_mockup(prospect)
        body = email_msg.finalize(body, email_msg.esboco_paragraph(prospect, url))
    return subject, body, url, regenerated


def _reject(prospect_id, status, reason, event_type, email=None):
    database.update_prospect(prospect_id, {'status': status, 'error_message': reason})
    database.add_event(prospect_id, event_type, reason, {'email': email})
    raise Exception(REJECT_PREFIX + reason)


def send_prospect_email(prospect_id, bypass_limit=False):
    # 1. Enforce throttle
    if not bypass_limit:
        sent_today = database.get_sent_count_today()
        try:
            limit = int(database.get_setting('daily_email_limit', '20'))
        except:
            limit = 20

        if sent_today >= limit:
            raise Exception(f"Limite diário de envio atingido ({limit} e-mails/dia).")

    prospect = database.get_prospect(prospect_id)
    if not prospect:
        raise Exception("Prospect não encontrado.")

    email_to = prospect.get('contact_email')
    subject = prospect.get('email_subject')
    body = prospect.get('email_body')

    if not email_to or not subject or not body:
        error_msg = ""
        if not email_to:
            error_msg = "Este prospect não possui e-mail de contato."
        else:
            error_msg = "Assunto ou corpo do e-mail está vazio."

        database.update_prospect(prospect_id, {
            'status': 'failed',
            'error_message': error_msg
        })
        raise Exception(error_msg)

    # 2. Portas antes de enviar (Q1 e-mail valido, E1 lista de bloqueio, Q2 empresa real do segmento)
    e_status, e_why, email_norm = validators.check_email(email_to, check_dns=True)
    if e_status == 'invalid':
        _reject(prospect_id, 'rejected', f"e-mail invalido ({e_why})", 'email_invalid', email_to)
    email_to = email_norm
    if database.is_suppressed(email_to):
        _reject(prospect_id, 'rejected', "e-mail na lista de bloqueio (descadastro ou rejeicao anterior)", 'email_blocked', email_to)
    q_ok, q_why = qualify.qualify_prospect(prospect)
    if not q_ok:
        _reject(prospect_id, 'rejected', f"fora do perfil: {q_why}", 'email_not_qualified', email_to)

    # 2b. E4/M1: corpo finalizado (esboco automatico ou oferta honesta; corpo antigo com promessa falsa e regenerado)
    try:
        subject, body, mockup_url, regenerated = finalize_email(prospect, subject, body)
    except LaneSkip as skip:
        _reject(prospect_id, 'rejected', f"faixa 'descartar': {skip}", 'lane_skipped', email_to)

    # 3. Corpo com rodape de identificacao/descadastro e cabecalhos de descadastro de um clique
    footer, unsub_url = build_footer(prospect_id, email_to)
    smtp_user = database.get_setting('smtp_user', '')
    headers = {}
    if unsub_url.startswith('https://'):
        headers['List-Unsubscribe'] = f"<{unsub_url}>" + (f", <mailto:{smtp_user}?subject=SAIR>" if smtp_user else "")
        headers['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

    # Send
    try:
        send_email_via_smtp(email_to, subject, body + footer, extra_headers=headers)

        # Update database on success
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        database.update_prospect(prospect_id, {
            'status': 'sent',
            'sent_at': now_str,
            'error_message': None,
            'email_subject': subject,       # guarda o texto FINAL enviado (com o link do esboco, se houve)
            'email_body': body
        })
        database.add_event(prospect_id, 'email_sent', subject, {'email': email_to, 'mockup': bool(mockup_url), 'regenerated': regenerated})
        try:
            if (prospect.get('stage') or 'novo') == 'novo':
                database.set_stage(prospect_id, 'contatado', note='primeiro e-mail enviado')
        except Exception:
            pass
        return True, "E-mail enviado!"
    except Exception as e:
        error_msg = str(e)
        kind = classify_smtp_error(e)
        database.update_prospect(prospect_id, {
            'status': 'failed',
            'error_message': error_msg
        })
        if kind == 'hard':          # endereco inexistente: nunca mais tentar
            database.add_suppression(email_to, 'rejeicao definitiva (hard bounce)', prospect_id)
            database.add_event(prospect_id, 'email_bounced', error_msg[:200], {'email': email_to})
        elif kind == 'policy':      # provedor bloqueou por spam/reputacao: sinal de alerta para o remetente
            database.add_event(prospect_id, 'email_blocked_by_provider', error_msg[:200], {'email': email_to})
        elif kind == 'soft':
            database.add_event(prospect_id, 'email_deferred', error_msg[:200], {'email': email_to})
        else:
            database.add_event(prospect_id, 'email_failed', error_msg[:200], {'email': email_to})
        raise Exception(f"Falha no envio do e-mail: {error_msg}")
