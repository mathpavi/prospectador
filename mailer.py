import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import database
from datetime import datetime

def send_email_via_smtp(to_email, subject, body):
    # Load settings from database
    host = database.get_setting('smtp_host', '')
    port_str = database.get_setting('smtp_port', '465')
    user = database.get_setting('smtp_user', '')
    password = database.get_setting('smtp_password', '')
    security = database.get_setting('smtp_security', 'SSL')
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
    
    # Body
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    server = None
    try:
        if security == 'SSL':
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if security == 'STARTTLS':
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
        
    # Send
    try:
        send_email_via_smtp(email_to, subject, body)
        
        # Update database on success
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        database.update_prospect(prospect_id, {
            'status': 'sent',
            'sent_at': now_str,
            'error_message': None
        })
        return True, "E-mail enviado!"
    except Exception as e:
        error_msg = str(e)
        database.update_prospect(prospect_id, {
            'status': 'failed',
            'error_message': error_msg
        })
        raise Exception(f"Falha no envio do e-mail: {error_msg}")
