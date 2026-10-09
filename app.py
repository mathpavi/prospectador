from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import sqlite3
import database
import agent
import mailer
import agent_international
import threading
import time
import os
from datetime import datetime
import json

import security
import prioritize
import followup
import inbox
import alerts
import painel
import crm
import queue_tools
import cnpj_runner
import rejudge_runner
import rotation
import site_finder
import mockup_runner
from mockups.blueprint import bp as mockups_bp, preview_gate
from public_routes import bp as public_bp
from whatsapp_routes import bp as whatsapp_bp, apply_generated_drafts

app = Flask(__name__)
# F1: chave de sessao vem do ambiente ou e gerada e guardada em DATA_DIR (nunca um valor fixo no codigo)
app.secret_key = security.get_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',   # defina COOKIE_SECURE=1 na VPS (HTTPS)
)
app.register_blueprint(mockups_bp)   # rota publica /p/<token>/ dos esbocos de site
app.register_blueprint(public_bp)    # rota publica /u/<token> de descadastro
app.register_blueprint(whatsapp_bp)  # Central WhatsApp: oportunidades priorizadas, contatado, resultado

# Initialize DB on startup
database.init_db()

def get_admin_password():
    # Priority: Environment variable -> Database setting
    env_pass = os.environ.get('ADMIN_PASSWORD')
    if env_pass is not None:
        return env_pass
    return database.get_setting('admin_password', '')

def is_diag_authorized():
    # F1: so existe com DIAGNOSTICS_TOKEN definido no ambiente, enviado no cabecalho X-Diag-Key
    return security.diag_authorized(request)

@app.before_request
def require_auth():
    # Esbocos (/p/) e descadastro (/u/) sao publicos; no host de preview so existem essas rotas
    _gate = preview_gate(request)
    if _gate == "public":
        return None
    if _gate is not None:
        return _gate

    # Allow programmatic diagnostics & monitoring with secure token
    if is_diag_authorized():
        return None

    admin_pass = get_admin_password()
    # F1: sem senha de admin o painel so abre em localhost; na internet fica bloqueado
    if security.open_access_blocked(request, admin_pass):
        return ("Acesso bloqueado: defina a senha de administrador (variavel ADMIN_PASSWORD) para usar o painel.", 503)
    if not admin_pass:
        return None

    # Allow static files and login endpoints
    if request.path.startswith('/static') or request.path == '/login' or request.path == '/favicon.ico':
        return None
        
    if not session.get('authenticated'):
        if request.path.startswith('/api/'):
            return jsonify({"error": "Não autorizado. Faça login primeiro."}), 401
        return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    admin_pass = get_admin_password()
    if not admin_pass:
        return redirect('/')
        
    error = None
    if request.method == 'POST':
        ip = security.client_ip(request)
        if security.login_blocked(ip):
            return render_template('login.html', error="Muitas tentativas. Aguarde alguns minutos e tente de novo."), 429
        password = request.form.get('password', '')
        if security.safe_equal(password, admin_pass):
            security.clear_login_failures(ip)
            session['authenticated'] = True
            return redirect('/')
        else:
            security.register_login_failure(ip)
            error = "Senha incorreta. Tente novamente."

    return render_template('login.html', error=error)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('authenticated', None)
    return redirect('/login')

# --- Funil (T1 do PLANO_PROSPECTADOR): estagio/resultado de cada prospect e historico de eventos ---
@app.route('/api/prospects/<int:prospect_id>/stage', methods=['POST'])
def api_set_prospect_stage(prospect_id):
    data = request.get_json(silent=True) or {}
    try:
        database.set_stage(prospect_id, data.get('stage', ''), data.get('deal_value'), data.get('note'), data.get('source'))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})

@app.route('/api/fila')
def api_fila():
    # Fila de envio: onde estao os leads, proximos a sair, follow-ups devidos e estado da caixa de entrada (substitui diagnostico_fila/followups/ler_caixa)
    try:
        snap = queue_tools.snapshot()
        return jsonify({"grupos": snap["grupos"], "aprovaveis": len(snap["aprovaveis"]), "temporarias": len(snap["temporarias"]),
                        "fila": queue_tools.next_in_queue(15), "followups": queue_tools.followups_due(10),
                        "caixa_ligada": database.get_setting('imap_enabled', '0') == '1'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/fila/aprovar', methods=['POST'])
def api_fila_aprovar():
    return jsonify({"success": True, "aprovados": queue_tools.approve_pending()})

@app.route('/api/fila/reenviar', methods=['POST'])
def api_fila_reenviar():
    return jsonify({"success": True, "devolvidos": queue_tools.retry_temporary_failures()})

@app.route('/api/fila/remover/<int:prospect_id>', methods=['POST'])
def api_fila_remover(prospect_id):
    return jsonify({"success": queue_tools.remove_from_queue(prospect_id)})

@app.route('/api/caixa/ler', methods=['POST'])
def api_caixa_ler():
    dry = bool((request.get_json(silent=True) or {}).get('simular'))
    return jsonify(queue_tools.read_inbox(dry=dry))

@app.route('/api/fontes')
def api_fontes():
    # Fontes de leads: CNPJ da Receita (importacao e descoberta de site) e a busca automatica na internet
    try:
        busca = rotation.summary()
        try:
            alerts_p = json.loads(database.get_setting('search_provider_alerts', '{}') or '{}')
        except Exception:
            alerts_p = {}
        now_s = time.strftime("%Y-%m-%d %H:%M")
        return jsonify({"cnpj": cnpj_runner.status(),
                        "busca": {"ligada": database.get_setting('autopilot_search_enabled', '0') == '1', "buscas_hoje": rotation.searches_today(),
                                  "teto_dia": database.get_setting('autopilot_search_daily_cap', '60'), "estoque_fila": rotation.stock(),
                                  "meta_fila": database.get_setting('autopilot_queue_target', '60'), "em_descanso": busca["em_descanso"][:12],
                                  "buscadores_fora": [{"nome": k, "motivo": v.get("motivo"), "ate": v.get("ate")} for k, v in alerts_p.items() if v.get("ate", "") >= now_s],
                                  "aviso": rotation.stall_message()}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/fontes/cnpj/importar', methods=['POST'])
def api_fontes_cnpj_importar():
    limite = (request.get_json(silent=True) or {}).get('limite', 3000)
    try:
        ok, msg = cnpj_runner.start(int(limite))
    except Exception as e:
        return jsonify({"success": False, "message": f"Não consegui iniciar: {e}"}), 500
    return jsonify({"success": ok, "message": msg})

@app.route('/api/esbocos/reavaliar', methods=['GET'])
def api_reavaliar_status():
    return jsonify(rejudge_runner.status())

@app.route('/api/esbocos/reavaliar', methods=['POST'])
def api_reavaliar_start():
    ok, msg = rejudge_runner.start()
    return jsonify({"success": ok, "message": msg})

@app.route('/api/esbocos/revogar', methods=['POST'])
def api_esbocos_revogar():
    data = request.get_json(silent=True) or {}
    n = rejudge_runner.revoke(tokens=data.get('tokens'), all_failed_unsent=bool(data.get('todos_nao_enviados')))
    return jsonify({"success": True, "tirados": n})

@app.route('/api/esboco/prorrogar', methods=['POST'])
def api_esboco_prorrogar():
    from mockups import store
    data = request.get_json(silent=True) or {}
    m = store.latest(int(data.get('prospect_id', 0)))
    if not m or m.get('status') != 'ready':
        return jsonify({"success": False, "message": "Este lead não tem esboço no ar."}), 400
    new = store.extend(m['token'], max(1, min(60, int(data.get('dias', 7)))))
    database.add_event(m['prospect_id'], 'mockup_extended', f"esboco prorrogado ate {datetime.fromtimestamp(new):%d/%m}", {})
    return jsonify({"success": True, "vence": datetime.fromtimestamp(new).strftime('%d/%m/%Y')})

@app.route('/api/lead/<int:prospect_id>')
def api_lead_sheet(prospect_id):
    # Ficha do lead: contatos, e-mail enviado, esboco (aberturas) e linha do tempo em portugues
    try:
        sheet = crm.lead_sheet(prospect_id)
        return (jsonify(sheet), 200) if sheet else (jsonify({"error": "lead nao encontrado"}), 404)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/resultados')
def api_resultados():
    # Resultados da campanha: enviados, esboco aberto, cliques, respostas, interessados, ganhos, por faixa/segmento/cidade
    try:
        days = max(1, min(180, request.args.get('dias', 30, type=int)))
        return jsonify(crm.resultados(days))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/dia')
def api_dia():
    # U1: Painel do Dia (quem chamar hoje, saude do sistema, funil)
    try:
        d = painel.build()
        d['piloto'] = painel.piloto(autopilot_status)
        return jsonify(d)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/prospects/<int:prospect_id>/events')
def api_prospect_events(prospect_id):
    return jsonify(database.get_events(prospect_id))

# Global states for background tasks
search_lock = threading.Lock()
is_searching = False
search_params = {}

surgical_search_lock = threading.Lock()
is_surgical_searching = False
surgical_search_params = {}

international_search_lock = threading.Lock()
is_international_searching = False
international_search_params = {}

directory_search_lock = threading.Lock()
is_directory_searching = False
directory_search_params = {}

queue_lock = threading.Lock()
is_sending_queue = False
queue_status = {"current": 0, "total": 0, "status": "idle", "logs": []}

import_lock = threading.Lock()
is_importing = False
import_status = {"current": 0, "total": 0, "status": "idle", "logs": []}

@app.route('/')
def index():
    return render_template('index.html')

# Settings Endpoints
@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        settings = database.get_all_settings()
        # Remove passwords for safety, but indicate if set
        if settings.get('smtp_password'):
            settings['smtp_password_set'] = True
            settings['smtp_password'] = '********'
        else:
            settings['smtp_password_set'] = False
            settings['smtp_password'] = ''
        return jsonify(settings)
    else:
        data = request.json
        # Handle password update if password is obfuscated
        if data.get('smtp_password') == '********':
            # Remove password key so we don't save the asterisks
            data.pop('smtp_password')
            
        database.save_settings(data)
        return jsonify({"message": "Configurações salvas com sucesso!"})

# Database Backup & Restore Endpoints
@app.route('/api/backup/download', methods=['GET'])
def api_backup_download():
    if os.path.exists(database.DB_PATH):
        return send_file(
            database.DB_PATH,
            as_attachment=True,
            download_name=f"prospector_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            mimetype='application/x-sqlite3'
        )
    return jsonify({"error": "Banco de dados não encontrado"}), 404

@app.route('/api/backup/restore', methods=['POST'])
def api_backup_restore():
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400
        
    file = request.files['file']
    if not file.filename or not (file.filename.endswith('.db') or file.filename.endswith('.sqlite') or file.filename.endswith('.sqlite3')):
        return jsonify({"error": "Formato inválido. Envie um arquivo .db ou .sqlite"}), 400
        
    temp_path = database.DB_PATH + '.tmp'
    try:
        # Save to a temporary location first, then test
        file.save(temp_path)
        
        # Verify it's a valid sqlite3 db
        test_conn = sqlite3.connect(temp_path)
        test_cursor = test_conn.cursor()
        test_cursor.execute("SELECT COUNT(*) FROM prospects")
        count = test_cursor.fetchone()[0]
        test_conn.close()
        
        # Replace the main db file safely
        if os.path.exists(database.DB_PATH):
            os.replace(temp_path, database.DB_PATH)
        else:
            os.rename(temp_path, database.DB_PATH)
            
        # Re-initialize DB migrations to be 100% sure schema is updated
        database.init_db()
        
        return jsonify({
            "message": f"Banco de dados restaurado com sucesso! {count} leads carregados.",
            "leads_count": count
        })
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": f"Falha ao restaurar banco de dados: {str(e)}"}), 500

# SMTP Test Endpoint
@app.route('/api/smtp/test', methods=['POST'])
def api_smtp_test():
    data = request.json
    # If using obfuscated password, load the existing one from database
    password = data.get('smtp_password')
    if password == '********':
        password = database.get_setting('smtp_password', '')
        
    success, msg = mailer.test_smtp_settings(
        host=data.get('smtp_host', ''),
        port_str=data.get('smtp_port', '465'),
        user=data.get('smtp_user', ''),
        password=password,
        security=data.get('smtp_security', 'SSL'),
        sender_name=data.get('sender_name', 'Matheus Paviani'),
        test_email=data.get('test_email', '')
    )
    return jsonify({"success": success, "message": msg})

def background_search_worker(segment, region, max_results, state_uf, city_name, radius_km, source_mode="organic"):
    global is_searching
    try:
        agent.run_prospecting_job(segment, region, max_results, state_uf, city_name, radius_km, source_mode=source_mode)
    except Exception as e:
        agent.add_log(f"Erro geral no processamento da busca: {e}")
    finally:
        with search_lock:
            is_searching = False

# Surgical Prospector Worker Thread
def background_surgical_search_worker(segment, region, max_results, state_uf, city_name, radius_km, surgical_type):
    global is_surgical_searching
    try:
        agent.run_surgical_job(segment, region, max_results, state_uf, city_name, radius_km, surgical_type)
    except Exception as e:
        agent.add_log(f"Erro geral no processamento da busca cirúrgica: {e}")
    finally:
        with surgical_search_lock:
            is_surgical_searching = False

# =========================================================
# PILOTO AUTOMÁTICO (AUTOPILOT) SYSTEM
# =========================================================
from datetime import timedelta

autopilot_status = {
    "sender_status": "idle",
    "search_status": "idle",
    "logs": ["[Piloto Automático] Sistema de monitoramento inicializado."]
}

def autopilot_log(msg):
    log_line = f"[{database.get_now().strftime('%H:%M:%S')}] {msg}"
    autopilot_status["logs"].append(log_line)
    if len(autopilot_status["logs"]) > 50:
        autopilot_status["logs"].pop(0)

def check_commercial_hours():
    try:
        hours_enabled = database.get_setting('autopilot_sender_hours_enabled', '1') == '1'
        start_hour = int(database.get_setting('autopilot_sender_start_hour', '8'))
        end_hour = int(database.get_setting('autopilot_sender_end_hour', '18'))
        days_str = database.get_setting('autopilot_sender_days', '1,2,3,4,5')
        allowed_days = [int(d) for d in days_str.split(',') if d]
    except Exception:
        hours_enabled = True
        start_hour = 8
        end_hour = 18
        allowed_days = [1, 2, 3, 4, 5]
        
    now = database.get_now()
    current_day = now.weekday() + 1
    current_hour = now.hour
    
    if current_day not in allowed_days:
        return False, f"Hoje não é dia de envio permitido ({current_day})"
        
    if hours_enabled and not (start_hour <= current_hour < end_hour):
        return False, f"Fora do horário comercial (Hora atual: {current_hour}h)"
        
    return True, "Horário comercial válido" if hours_enabled else "Envio 24h ativado"

def check_sending_interval():
    last_sent_str = database.get_setting('autopilot_last_email_sent_at', '')
    if not last_sent_str:
        return True, ""
        
    try:
        last_sent = datetime.strptime(last_sent_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=database.SAO_PAULO_TZ)
    except Exception:
        return True, ""
        
    try:
        interval_min = int(database.get_setting('autopilot_sender_interval_min', '20'))
    except Exception:
        interval_min = 20
        
    elapsed = (database.get_now() - last_sent).total_seconds() / 60.0
    if elapsed < interval_min:
        return False, f"Intervalo não atingido ({elapsed:.1f} min decorridos)"
        
    return True, ""

def log_autopilot_activity(activity_type, detail, status="success"):
    entry = {
        "timestamp": database.get_now().strftime('%d/%m/%Y %H:%M:%S'),
        "type": activity_type,
        "detail": detail,
        "status": status
    }
    try:
        with open("autopilot_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except:
        pass

def get_autopilot_history(limit=10):
    if not os.path.exists("autopilot_history.jsonl"):
        return []
    try:
        with open("autopilot_history.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
        history = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                history.append(json.loads(line))
                if len(history) >= limit:
                    break
        return history
    except:
        return []

def autopilot_send_next_email(force=False):
    if not force and database.get_setting('autopilot_sender_enabled', '0') != '1':
        autopilot_status["sender_status"] = "disabled"
        return
        
    if not force:
        ok, reason = check_commercial_hours()
        if not ok:
            autopilot_status["sender_status"] = "outside_hours"
            return
            
        ok, reason = check_sending_interval()
        if not ok:
            autopilot_status["sender_status"] = "waiting_interval"
            return
        
    try:
        limit = int(database.get_setting('daily_email_limit', '20'))
    except:
        limit = 20
    sent_today = database.get_sent_count_today()
    if sent_today >= limit:
        autopilot_status["sender_status"] = "limit_reached"
        return
        
    # C1: follow-up (dias 3, 7 e 14) tem prioridade sobre prospeccao nova: conversa quente primeiro
    try:
        fu = followup.next_due()
    except Exception as e:
        fu = None
        autopilot_log(f"⚠️ Falha ao procurar follow-ups: {e}")
    if fu:
        fp = fu['prospect']
        autopilot_status["sender_status"] = "sending"
        autopilot_log(f"Follow-up ({fu['step']}) para: {fp['company_name']} ({fp['contact_email']})...")
        try:
            followup.send_followup(fp['id'], fu['step'])
            database.save_settings({'autopilot_last_email_sent_at': database.get_now_str()})
            autopilot_log(f"✅ Follow-up {fu['step']} enviado para {fp['company_name']}!")
            log_autopilot_activity("Follow-up", f"Follow-up {fu['step']} enviado para {fp['company_name']}", "success")
        except Exception as e:
            autopilot_log(f"❌ Falha no follow-up de {fp['company_name']}: {e}")
            log_autopilot_activity("Follow-up", f"Falha no follow-up de {fp['company_name']}: {e}", "error")
            if mailer.REJECT_PREFIX not in str(e):
                database.save_settings({'autopilot_last_email_sent_at': database.get_now_str()})
                return
            # follow-up barrado por validacao (e-mail invalido/bloqueado): nao trava o envio; segue para os leads novos
        else:
            return

    approved_leads = database.get_prospects(status_filter='approved')
    if not approved_leads:
        autopilot_status["sender_status"] = "no_leads"
        return
        
    # C8: o melhor potencial primeiro (e-mail do dominio da empresa, dono conhecido, segmento do nucleo...), com bonus de espera
    approved_leads.sort(key=lambda x: (-prioritize.email_priority(x), x.get('created_at', '')))
    target_lead = approved_leads[0]
    try:
        # esbocos gerados ANTES do envio: prefere o primeiro lead da fila que ja esta pronto (ou nao precisa de esboco); o e-mail sai na hora
        if mockup_runner.prefetch_enabled():
            for cand in approved_leads[:30]:
                if mockup_runner.state(cand) in ('ready', 'na', 'tried'):
                    target_lead = cand
                    break
    except Exception:
        pass
    
    autopilot_status["sender_status"] = "sending"
    autopilot_log(f"Enviando e-mail automático para: {target_lead['company_name']} ({target_lead['contact_email']})...")
    
    try:
        mailer.send_prospect_email(target_lead['id'], bypass_limit=False)
        now_str = database.get_now_str()
        database.save_settings({'autopilot_last_email_sent_at': now_str})
        autopilot_log(f"✅ E-mail enviado com sucesso para {target_lead['company_name']}!")
        
        log_autopilot_activity("Disparo de E-mail", f"E-mail enviado para {target_lead['company_name']} ({target_lead['contact_email']})", "success")
        
        log_entry = {
            "timestamp": database.get_now().isoformat(),
            "type": "autopilot_sent",
            "prospect_id": target_lead['id'],
            "company_name": target_lead['company_name'],
            "email": target_lead['contact_email'],
            "status": "success"
        }
        with open("search_debug.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        error_msg = str(e)
        autopilot_log(f"❌ Falha no envio para {target_lead['company_name']}: {error_msg}")
        log_autopilot_activity("Disparo de E-mail", f"Falha no envio para {target_lead['company_name']}: {error_msg}", "error")
        
        # Apply sending cooldown backoff only for network/SMTP/mailer limits, not for validation errors
        is_validation_error = "não possui e-mail" in error_msg or "vazio" in error_msg or mailer.REJECT_PREFIX in error_msg
        if not is_validation_error:
            now_str = database.get_now_str()
            database.save_settings({'autopilot_last_email_sent_at': now_str})
            autopilot_log("⚠️ Falha de rede/SMTP detected. Aguardando intervalo de recuo (backoff) antes do próximo disparo.")
            
        log_entry = {
            "timestamp": database.get_now().isoformat(),
            "type": "autopilot_sent",
            "prospect_id": target_lead['id'],
            "company_name": target_lead['company_name'],
            "email": target_lead.get('contact_email') or '',
            "status": "failed",
            "error_msg": error_msg
        }
        with open("search_debug.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

def check_search_interval():
    """Portao da busca (rotation.search_gate): guiado pelo estoque de leads com e-mail, nao por relogio. Devolve (ok, motivo, codigo)."""
    try:
        ok, code, why = rotation.search_gate()
        return ok, why, code
    except Exception as e:
        return True, f"portao indisponivel ({e})", "ok"

def autopilot_run_next_search(force=False):
    if not force and database.get_setting('autopilot_search_enabled', '0') != '1':
        autopilot_status["search_status"] = "disabled"
        return
        
    if not force:
        ok, _why, code = check_search_interval()
        if not ok:
            autopilot_status["search_status"] = code
            autopilot_status["search_reason"] = _why
            return
        
    targets_str = database.get_setting('autopilot_search_targets', '[]')
    try:
        targets = json.loads(targets_str)
    except:
        targets = []
        
    try:
        current_idx = int(database.get_setting('autopilot_search_target_index', '0'))
    except:
        current_idx = 0
    if targets and current_idx >= len(targets):
        current_idx = 0

    # rotacao automatica: pula alvos saturados e, se todos estiverem, usa o catalogo automatico (nunca fica parado)
    target, origem, next_idx = rotation.choose(targets, current_idx)
    if not target:
        autopilot_status["search_status"] = "no_targets"
        return
    database.save_settings({'autopilot_search_target_index': str(next_idx)})
    try:
        rotation.note_search_started()
    except Exception:
        pass
    
    segment = target.get('segment')
    region = target.get('region')
    radius_km = int(target.get('radius_km', 0))
    search_type = target.get('type', 'organic')
    
    try:
        batch_size = int(database.get_setting('autopilot_search_batch_size', '30'))
    except:
        batch_size = 30
    search_limit = int(target.get('limit', batch_size)) if target.get('limit') else batch_size
    
    autopilot_status["search_status"] = "searching"
    autopilot_log(f"Iniciando busca automática do Autopilot: Segmento='{segment}', Região='{region}' (Alvo: {search_limit} leads, Tipo: {search_type}{', alvo AUTOMÁTICO' if origem == 'automatico' else ''})...")
    
    t_start = time.time()
    search_error = None
    try:
        log_mark = (len(agent.job_logs), len(agent.directory_logs))
    except Exception:
        log_mark = (0, 0)
    try:
        now_str = database.get_now_str()
        database.save_settings({'autopilot_last_search_run_at': now_str})
        started_at = now_str
        
        state_uf, city_name = agent.parse_autopilot_region(region)
            
        if search_type == 'directory':
            selected_dirs = target.get('directories') or ['guiamais', 'solutudo', 'apontador', 'telelistas', 'cnpj_biz']
            only_no_site = target.get('only_without_website', True)
            prio_wa = target.get('prioritize_whatsapp', True)
            agent.run_directories_job(
                segment=segment,
                region=region,
                state_uf=state_uf,
                city_name=city_name,
                max_results=search_limit,
                selected_directories=selected_dirs,
                only_without_website=only_no_site,
                prioritize_whatsapp=prio_wa,
                is_autopilot=1
            )
        elif search_type == 'maps_only' or target.get('is_surgical', False):
            agent.run_surgical_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, surgical_type='both', is_autopilot=1)
        elif search_type == 'kipflow':
            agent.run_prospecting_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, is_autopilot=1, source_mode="kipflow")
        else:
            agent.run_prospecting_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, is_autopilot=1, source_mode="organic")
            
        autopilot_log(f"✅ Busca automática do Autopilot concluída com sucesso!")
        log_autopilot_activity("Busca Automática", f"Busca concluída para '{segment}' em '{region}' (Qtd: {search_limit}, Fonte: {search_type})", "success")
    except Exception as e:
        search_error = str(e) or type(e).__name__
        autopilot_log(f"❌ Erro na busca automática: {e}")
        log_autopilot_activity("Busca Automática", f"Falha na busca para '{segment}' em '{region}': {str(e)}", "error")
    finally:
        autopilot_status["search_status"] = "idle"

    # mede o que a busca rendeu e decide se o alvo esta saturado (rotation.py)
    try:
        conn = database.get_db_connection()
        row = conn.execute(
            "SELECT COUNT(*) n, "
            "SUM(CASE WHEN contact_email IS NOT NULL AND contact_email != '' THEN 1 ELSE 0 END) e, "
            "SUM(CASE WHEN (contact_email IS NULL OR contact_email = '') AND contact_whatsapp IS NOT NULL AND contact_whatsapp != '' THEN 1 ELSE 0 END) w "
            "FROM prospects WHERE is_autopilot = 1 AND created_at >= ?", (started_at,)).fetchone()
        conn.close()
        novos, com_email, so_wa = int(row['n'] or 0), int(row['e'] or 0), int(row['w'] or 0)
        err = search_error
        if not err and novos == 0 and (time.time() - t_start) < 20:
            err = "a busca terminou em segundos sem nada (provável falha de API ou cota)"
        if not err and novos == 0:
            try:     # linhas de log da propria busca que parecem erro (API fora, cota, chave) = falha, nao saturacao
                msgs = [x.get('message', '') for x in list(agent.job_logs)[log_mark[0]:]] + [x.get('message', '') for x in list(agent.directory_logs)[log_mark[1]:]]
                n_err, sample = rotation.log_errors(msgs)
                if n_err >= 3:
                    err = f"{n_err} erros no log da busca (ex.: {sample})"
            except Exception:
                pass
        if rotation.enabled():
            sat, why = rotation.record_run(target, novos, com_email, so_wa, error=err)
            rotation.set_retry_soon(bool(sat) or bool(err))
            autopilot_log(f"📊 Busca '{segment}'/{region}/{search_type}: {novos} novos, {com_email} com e-mail, {so_wa} só WhatsApp." +
                          (f" ⏸ Alvo em descanso: {why}. Próxima busca já vai para outro alvo." if sat else (f" ⚠ {why}" if err else "")))
    except Exception as e:
        autopilot_log(f"⚠️ Não consegui medir o rendimento da busca: {e}")

_site_disc = {"t": 0.0}


def autopilot_site_discovery():
    """Leads do CNPJ da Receita: procura o site de cada um (lote pequeno por vez) e aprova os verificados com e-mail, conforme o estoque da fila.
    So roda quando a fila esta abaixo da meta (com a fila cheia nao ha pressa)."""
    if database.get_setting('cnpj_site_discovery', '1') != '1' or time.time() - _site_disc["t"] < 20:
        return
    _site_disc["t"] = time.time()
    try:
        target = int(database.get_setting('autopilot_queue_target', '60') or 60)
    except Exception:
        target = 60
    if rotation.stock() >= target:
        return
    if site_finder.backlog() == 0 and site_finder.approve_waiting(max(0, target - rotation.stock())) == 0:
        return
    autopilot_status["search_status"] = "searching"
    try:
        st = site_finder.process_batch(limit=8)
        if st["site"] or st["sem_site"] or st["aprovados"] or st["duplicado"]:
            autopilot_log(f"🔎 CNPJ: {st['site']} com site, {st['sem_site']} sem site, {st['duplicado']} duplicados, {st['aprovados']} aprovados para envio ({st['restantes']} ainda por verificar).")
    finally:
        autopilot_status["search_status"] = "idle"


def background_mockup_prefetch():
    """Gera os esbocos da fila em segundo plano (thread propria), para o envio nao esperar 2-3 minutos por e-mail."""
    while True:
        did = None
        try:
            if mockup_runner.prefetch_enabled():
                leads = database.get_prospects(status_filter='approved')
                leads.sort(key=lambda x: (-prioritize.email_priority(x), x.get('created_at', '')))
                did = mockup_runner.prefetch_next(leads, ahead=10)
                if did:
                    autopilot_log(f"🖼️ Esboço preparado com antecedência para o lead {did}.")
        except Exception as e:
            autopilot_log(f"❌ Erro na etapa 'esboços antecipados': {type(e).__name__}: {str(e)[:160]}")
        time.sleep(5 if did else 30)


def background_autopilot_search_scheduler():
    """Busca de leads em thread PROPRIA: uma busca longa nunca mais atrasa o envio de e-mails (nem o contrario)."""
    last_msg = {"t": None}
    while True:
        autopilot_status["search_heartbeat"] = time.time()
        try:
            autopilot_site_discovery()
        except Exception as e:
            msg = f"Erro na etapa 'sites do CNPJ': {type(e).__name__}: {str(e)[:200]}"
            if last_msg["t"] != msg:
                last_msg["t"] = msg
                autopilot_log(f"❌ {msg}")
        try:
            autopilot_run_next_search()
        except Exception as e:
            msg = f"Erro na etapa 'busca': {type(e).__name__}: {str(e)[:200]}"
            if last_msg["t"] != msg:
                last_msg["t"] = msg
                autopilot_log(f"❌ {msg}")
        autopilot_status["search_heartbeat"] = time.time()
        time.sleep(15)

def background_autopilot_scheduler():
    last_err = {}

    def beat(step):
        # sinal de vida: o Painel do Dia mostra ha quanto tempo o piloto respondeu e em que etapa esta (diagnostico de travamento)
        autopilot_status["step"] = step
        autopilot_status["heartbeat"] = time.time()

    def fail(step, e):
        # erro NUNCA mais some em silencio: vai para o log do piloto (sem repetir a mesma mensagem em sequencia)
        msg = f"Erro na etapa '{step}': {type(e).__name__}: {str(e)[:200]}"
        if last_err.get(step) != msg:
            last_err[step] = msg
            autopilot_log(f"❌ {msg}")

    while True:
        beat("envio")
        try:
            autopilot_send_next_email()
        except Exception as e:
            fail("envio", e)

        beat("caixa de entrada")
        try:
            r = inbox.maybe_check()      # T3: respostas e rejeicoes (so se imap_enabled=1; no maximo a cada 10 min)
            if r and r.get('acoes'):
                for line in r['acoes'][:10]:
                    autopilot_log(f"📬 Caixa de entrada: {line}")
            if r and r.get('erro'):
                fail("caixa de entrada", Exception(r['erro']))
        except Exception as e:
            fail("caixa de entrada", e)

        beat("alertas")
        try:
            alerts.maybe_run()           # T4: alerta de lead quente (imediato) e resumo diario por e-mail
        except Exception as e:
            fail("alertas", e)

        beat("aguardando")
        time.sleep(10)

# Settings Autopilot Save
@app.route('/api/autopilot/settings', methods=['POST'])
def api_autopilot_settings():
    data = request.json or {}
    settings = {}
    fields = [
        'autopilot_sender_enabled',
        'autopilot_sender_interval_min',
        'autopilot_sender_hours_enabled',
        'autopilot_sender_start_hour',
        'autopilot_sender_end_hour',
        'autopilot_sender_days',
        'autopilot_search_enabled',
        'autopilot_search_targets',
        'autopilot_search_interval_hours',
        'autopilot_search_batch_size',
        'daily_email_limit',
        'autopilot_auto_approve'
    ]
    for field in fields:
        if field in data:
            settings[field] = str(data[field])
            
    database.save_settings(settings)
    autopilot_log("Configurações do Piloto Automático atualizadas.")
    return jsonify({"success": True, "message": "Configurações do Autopilot salvas!"})

# Autopilot Status
@app.route('/api/autopilot/status', methods=['GET'])
def api_autopilot_status():
    last_sent_str = database.get_setting('autopilot_last_email_sent_at', '')
    next_send_time = None
    
    sender_enabled = database.get_setting('autopilot_sender_enabled', '0') == '1'
    approved_count = len(database.get_prospects(status_filter='approved'))
    
    if sender_enabled:
        if approved_count == 0:
            next_send_time = "Sem leads aprovados na fila"
        else:
            ok, reason = check_commercial_hours()
            if not ok:
                next_send_time = "No próximo horário comercial"
            elif last_sent_str:
                try:
                    last_sent = datetime.strptime(last_sent_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=database.SAO_PAULO_TZ)
                    interval_min = int(database.get_setting('autopilot_sender_interval_min', '20'))
                    next_send = last_sent + timedelta(minutes=interval_min)
                    if next_send < database.get_now():
                        next_send_time = "Imediato (Aguardando tick do agendador)"
                    else:
                        next_send_time = next_send.strftime('%d/%m/%Y %H:%M:%S')
                except:
                    next_send_time = "Imediato"
            else:
                next_send_time = "Imediato"
    else:
        next_send_time = "Disparador Desativado"
        
    return jsonify({
        "sender_status": autopilot_status["sender_status"],
        "search_status": autopilot_status["search_status"],
        "logs": autopilot_status["logs"],
        "approved_count": approved_count,
        "next_send_time": next_send_time,
        "history": get_autopilot_history()
    })

# Autopilot Diagnostics Endpoint
@app.route('/api/autopilot/diagnostics', methods=['GET', 'POST'])
def api_autopilot_diagnostics():
    try:
        now = database.get_now()
        now_str = database.get_now_str()
        
        last_search_str = database.get_setting('autopilot_last_search_run_at', '')
        try:
            interval_hours = int(database.get_setting('autopilot_search_interval_hours', '2'))
        except Exception:
            interval_hours = 2
            
        elapsed_hours = None
        next_search_eta = None
        if last_search_str:
            try:
                last_search = datetime.strptime(last_search_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=database.SAO_PAULO_TZ)
                elapsed_hours = round((now - last_search).total_seconds() / 3600.0, 2)
                remaining_hours = round(max(0.0, interval_hours - elapsed_hours), 2)
                next_search_eta = f"{remaining_hours}h restantes"
            except Exception:
                pass

        targets_str = database.get_setting('autopilot_search_targets', '[]')
        try:
            targets = json.loads(targets_str)
        except Exception:
            targets = []
            
        try:
            current_target_index = int(database.get_setting('autopilot_search_target_index', '0'))
        except Exception:
            current_target_index = 0
            
        recent_prospects = database.get_prospects()[:15]
        prospects_summary = []
        for p in recent_prospects:
            prospects_summary.append({
                "id": p.get("id"),
                "company_name": p.get("company_name"),
                "website": p.get("website"),
                "email": p.get("contact_email") or p.get("email"),
                "phone": p.get("contact_phone") or p.get("phone"),
                "whatsapp": p.get("contact_whatsapp") or p.get("whatsapp"),
                "tech_stack": p.get("tech_stack"),
                "segment": p.get("segment"),
                "region": p.get("region"),
                "status": p.get("status"),
                "created_at": p.get("created_at")
            })

        recent_activity = get_autopilot_history()[:15]
        
        return jsonify({
            "server_time": now_str,
            "timezone": "America/Sao_Paulo (UTC-3)",
            "autopilot_search_enabled": database.get_setting('autopilot_search_enabled', '0'),
            "autopilot_sender_enabled": database.get_setting('autopilot_sender_enabled', '0'),
            "autopilot_auto_approve": database.get_setting('autopilot_auto_approve', '0'),
            "autopilot_search_interval_hours": interval_hours,
            "autopilot_search_batch_size": database.get_setting('autopilot_search_batch_size', '30'),
            "autopilot_sender_interval_min": database.get_setting('autopilot_sender_interval_min', '3'),
            "autopilot_last_search_run_at": last_search_str,
            "elapsed_hours": elapsed_hours,
            "next_search_eta": next_search_eta,
            "search_status": autopilot_status["search_status"],
            "sender_status": autopilot_status["sender_status"],
            "targets_count": len(targets),
            "current_target_index": current_target_index,
            "targets": targets,
            "serper_configured": bool(database.get_setting('serper_api_key', '')),
            "brave_configured": bool(database.get_setting('brave_api_key', '')),
            "cloro_configured": bool(database.get_setting('cloro_api_key', '')),
            "recent_logs": autopilot_status["logs"][-30:],
            "recent_activity": recent_activity,
            "recent_prospects": prospects_summary
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

# Force Autopilot Run Search
@app.route('/api/autopilot/force-search', methods=['POST'])
def api_autopilot_force_search():
    if autopilot_status["search_status"] == "searching":
        return jsonify({"success": False, "message": "Já existe uma busca automática em andamento."})
    
    # We clear the last search timestamp to let the next scheduler tick run or just trigger it immediately
    database.save_settings({'autopilot_last_search_run_at': ''})
    threading.Thread(target=lambda: autopilot_run_next_search(force=True)).start()
    return jsonify({"success": True, "message": "Busca automática forçada com sucesso!"})

# Force Autopilot Run Send
@app.route('/api/autopilot/force-send', methods=['POST'])
def api_autopilot_force_send():
    if autopilot_status["sender_status"] == "sending":
        return jsonify({"success": False, "message": "Já existe um disparo em andamento."})
        
    threading.Thread(target=lambda: autopilot_send_next_email(force=True)).start()
    return jsonify({"success": True, "message": "Disparo automático forçado com sucesso!"})

# Importer Worker Thread
def background_lead_importer(items, auto_approve=False):
    global is_importing, import_status
    try:
        def progress_cb(current, total, msg):
            import_status["current"] = current
            import_status["total"] = total
            import_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            if len(import_status["logs"]) > 50:
                import_status["logs"].pop(0)
                
        agent.import_and_verify_leads(items, auto_approve=auto_approve, progress_callback=progress_cb)
        import_status["status"] = "completed"
        import_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] ✅ Importação de leads concluída com sucesso!")
    except Exception as e:
        import_status["status"] = "failed"
        import_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] ❌ Erro geral na importação: {e}")
    finally:
        with import_lock:
            is_importing = False

# Import Leads Endpoint
@app.route('/api/leads/import', methods=['POST'])
def api_leads_import():
    global is_importing, import_status
    
    with import_lock:
        if is_importing:
            return jsonify({"error": "Já existe uma importação em andamento."}), 400
        is_importing = True
        
    data = request.json or {}
    items_raw = data.get('leads', '')
    auto_approve = data.get('auto_approve', False)
    
    items = [line.strip() for line in items_raw.split('\n') if line.strip()]
    
    import_status = {
        "current": 0,
        "total": len(items),
        "status": "running",
        "logs": [f"[{time.strftime('%H:%M:%S')}] Iniciando processamento de {len(items)} itens..."]
    }
    
    thread = threading.Thread(target=background_lead_importer, args=(items, auto_approve))
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Importação de leads iniciada!", "status": import_status})

# Import Leads Status
@app.route('/api/leads/import/status', methods=['GET'])
def api_leads_import_status():
    global is_importing, import_status
    return jsonify({
        "is_importing": is_importing,
        "status": import_status
    })

# Run Prospector Endpoint
@app.route('/api/prospect/run', methods=['POST'])
def api_prospect_run():
    global is_searching, search_params
    
    with search_lock:
        if is_searching:
            return jsonify({"error": "Já existe uma busca em andamento."}), 400
            
        is_searching = True
        
    data = request.json
    segment = data.get('segment', '')
    region = data.get('region', '')
    state_uf = data.get('state_uf', '')
    city_name = data.get('city_name', '')
    source_mode = data.get('source_mode', 'organic')
    try:
        radius_km = int(data.get('radius_km', 0))
    except:
        radius_km = 0
        
    try:
        max_results = int(data.get('max_results', 5))
    except:
        max_results = 5
        
    # Save search context for display
    search_params = {
        "segment": segment,
        "region": region,
        "state_uf": state_uf,
        "city_name": city_name,
        "radius_km": radius_km,
        "max_results": max_results,
        "source_mode": source_mode,
        "start_time": time.strftime('%d/%m/%Y %H:%M:%S')
    }
    
    # Clear logs for new run
    agent.job_logs.clear()
    agent.add_log("Preparando motor de busca...")
    
    # Start thread
    thread = threading.Thread(
        target=background_search_worker, 
        args=(segment, region, max_results, state_uf, city_name, radius_km, source_mode)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Busca iniciada!", "params": search_params})

# Get Prospector Search Logs & Status
@app.route('/api/prospect/status', methods=['GET'])
def api_prospect_status():
    global is_searching, search_params
    return jsonify({
        "is_searching": is_searching,
        "params": search_params,
        "logs": agent.job_logs
    })

# Run Surgical Prospector Endpoint
@app.route('/api/surgical/run', methods=['POST'])
def api_surgical_run():
    global is_surgical_searching, surgical_search_params
    
    with surgical_search_lock:
        if is_surgical_searching:
            return jsonify({"error": "Já existe uma busca cirúrgica em andamento."}), 400
            
        is_surgical_searching = True
        
    data = request.json
    segment = data.get('segment', '')
    region = data.get('region', '')
    state_uf = data.get('state_uf', '')
    city_name = data.get('city_name', '')
    surgical_type = data.get('surgical_type', 'both')
    try:
        radius_km = int(data.get('radius_km', 0))
    except:
        radius_km = 0
        
    try:
        max_results = int(data.get('max_results', 5))
    except:
        max_results = 5
        
    surgical_search_params = {
        "segment": segment,
        "region": region,
        "state_uf": state_uf,
        "city_name": city_name,
        "radius_km": radius_km,
        "max_results": max_results,
        "surgical_type": surgical_type,
        "start_time": time.strftime('%d/%m/%Y %H:%M:%S')
    }
    
    agent.job_logs.clear()
    agent.add_log("Preparando motor de busca cirúrgica...")
    
    thread = threading.Thread(
        target=background_surgical_search_worker, 
        args=(segment, region, max_results, state_uf, city_name, radius_km, surgical_type)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Busca cirúrgica iniciada!", "params": surgical_search_params})

# Get Surgical Search Logs & Status
@app.route('/api/surgical/status', methods=['GET'])
def api_surgical_status():
    global is_surgical_searching, surgical_search_params
    return jsonify({
        "is_searching": is_surgical_searching,
        "params": surgical_search_params,
        "logs": agent.job_logs
    })

def background_directory_search_worker(segment, region, state_uf, city_name, max_results, selected_directories, only_without_website, prioritize_whatsapp):
    global is_directory_searching
    try:
        agent.run_directories_job(
            segment=segment,
            region=region,
            state_uf=state_uf,
            city_name=city_name,
            max_results=max_results,
            selected_directories=selected_directories,
            only_without_website=only_without_website,
            prioritize_whatsapp=prioritize_whatsapp
        )
    except Exception as e:
        agent.add_directory_log(f"Erro crítico no motor de diretórios: {e}")
    finally:
        with directory_search_lock:
            is_directory_searching = False

# Run Directory Prospector Endpoint
@app.route('/api/directories/run', methods=['POST'])
def api_directories_run():
    global is_directory_searching, directory_search_params
    
    with directory_search_lock:
        if is_directory_searching:
            return jsonify({"error": "Já existe uma varredura em diretórios em andamento."}), 400
        is_directory_searching = True
        
    data = request.json or {}
    segment = data.get('segment', '')
    region = data.get('region', '')
    state_uf = data.get('state_uf', '')
    city_name = data.get('city_name', '')
    selected_directories = data.get('directories', ['all'])
    only_without_website = data.get('only_without_website', True)
    prioritize_whatsapp = data.get('prioritize_whatsapp', True)
    
    try:
        max_results = int(data.get('max_results', 10))
    except:
        max_results = 10
        
    directory_search_params = {
        "segment": segment,
        "region": region,
        "state_uf": state_uf,
        "city_name": city_name,
        "directories": selected_directories,
        "only_without_website": only_without_website,
        "prioritize_whatsapp": prioritize_whatsapp,
        "max_results": max_results,
        "start_time": time.strftime('%d/%m/%Y %H:%M:%S')
    }
    
    agent.directory_logs.clear()
    agent.add_directory_log("Preparando motor de busca em diretórios locais...")
    
    thread = threading.Thread(
        target=background_directory_search_worker,
        args=(segment, region, state_uf, city_name, max_results, selected_directories, only_without_website, prioritize_whatsapp)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Varredura em diretórios iniciada!", "params": directory_search_params})

# Directory Status & Logs Endpoint
@app.route('/api/directories/status', methods=['GET'])
def api_directories_status():
    global is_directory_searching, directory_search_params
    return jsonify({
        "is_searching": is_directory_searching,
        "params": directory_search_params,
        "logs": agent.directory_logs
    })

# Directory Cancel Endpoint
@app.route('/api/directories/cancel', methods=['POST'])
def api_directories_cancel():
    agent.cancel_directory_job()
    return jsonify({"message": "Cancelamento solicitado com sucesso."})

def background_international_search_worker(segment, country_code, city_name, limit, source_mode):
    global is_international_searching
    try:
        agent_international.run_international_prospecting_job(segment, country_code, city_name, limit, source_mode)
    except Exception as e:
        agent_international.add_log(f"Erro crítico no motor de busca internacional: {e}")
    finally:
        with international_search_lock:
            is_international_searching = False

# Run International Prospector Endpoint
@app.route('/api/international/run', methods=['POST'])
def api_international_run():
    global is_international_searching, international_search_params
    
    with international_search_lock:
        if is_international_searching:
            return jsonify({"error": "Já existe uma busca internacional em andamento."}), 400
            
        is_international_searching = True
        
    data = request.json or {}
    segment = data.get('segment', '')
    country_code = data.get('country_code', '')
    city_name = data.get('city_name', '')
    source_mode = data.get('source_mode', 'auto')
    try:
        limit = int(data.get('limit', 10))
    except:
        limit = 10
        
    international_search_params = {
        "segment": segment,
        "country_code": country_code,
        "city_name": city_name,
        "source_mode": source_mode,
        "limit": limit,
        "start_time": time.strftime('%d/%m/%Y %H:%M:%S')
    }
    
    agent_international.clear_logs()
    agent_international.add_log("Preparando motor de busca internacional...")
    
    thread = threading.Thread(
        target=background_international_search_worker,
        args=(segment, country_code, city_name, limit, source_mode)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Busca internacional iniciada!", "params": international_search_params})

# Get International Search Logs & Status
@app.route('/api/international/status', methods=['GET'])
def api_international_status():
    global is_international_searching, international_search_params
    return jsonify({
        "is_searching": is_international_searching,
        "params": international_search_params,
        "logs": agent_international.get_logs()
    })

# List International Prospects
@app.route('/api/international/prospects', methods=['GET'])
def api_international_prospects():
    status_filter = request.args.get('status')
    prospects = database.get_prospects(status_filter=status_filter, is_international_filter=1)
    return jsonify(apply_generated_drafts(prospects))     # mensagem de WhatsApp gerada (nao o rascunho fixo antigo)

# Get International Stats
@app.route('/api/international/stats', methods=['GET'])
def api_international_stats():
    all_prospects = database.get_prospects(is_international_filter=1)
    stats = {
        "total": len(all_prospects),
        "pending": len([p for p in all_prospects if p['status'] == 'pending']),
        "approved": len([p for p in all_prospects if p['status'] == 'approved']),
        "rejected": len([p for p in all_prospects if p['status'] == 'rejected']),
        "sent": len([p for p in all_prospects if p['status'] == 'sent']),
        "failed": len([p for p in all_prospects if p['status'] == 'failed'])
    }
    return jsonify(stats)

# Leads Management Endpoints
@app.route('/api/prospects', methods=['GET'])
def api_prospects():
    status_filter = request.args.get('status')
    is_surgical = request.args.get('is_surgical')
    is_directory = request.args.get('is_directory')
    origin = request.args.get('origin')
    search_query = request.args.get('q') or request.args.get('search')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 24, type=int)
    
    if request.args.get('limit') == 'all' or request.args.get('all') == 'true':
        limit = None
        
    is_surgical_filter = None
    is_directory_filter = None

    if origin == 'directory' or is_directory == '1':
        is_directory_filter = 1
    elif origin == 'surgical' or is_surgical == '1':
        is_surgical_filter = 1
    elif origin == 'standard' or (is_surgical == '0' and is_directory != '1'):
        is_surgical_filter = 0
        is_directory_filter = 0
    elif is_surgical is not None and is_surgical != 'all':
        try:
            is_surgical_filter = int(is_surgical)
        except:
            is_surgical_filter = None
        
    ids_filter = None
    esboco = request.args.get('esboco')
    if esboco in ('ready', 'review'):
        try:
            from mockups import store as mock_store
            ids_filter = mock_store.prospect_ids_with(esboco)
        except Exception:
            ids_filter = []
    paginated = database.get_prospects_paginated(
        page=page,
        limit=limit,
        status_filter=status_filter,
        search_query=search_query,
        is_surgical_filter=is_surgical_filter,
        is_international_filter=0,
        is_directory_filter=is_directory_filter,
        ids_filter=ids_filter
    )
    
    stats = database.get_prospects_stats(
        is_surgical_filter=is_surgical_filter,
        is_international_filter=0,
        is_directory_filter=is_directory_filter
    )
    
    return jsonify({
        "prospects": apply_generated_drafts(paginated["prospects"]),     # mensagem de WhatsApp gerada (nao o rascunho fixo antigo)
        "total": paginated["total"],
        "page": paginated["page"],
        "limit": paginated["limit"],
        "total_pages": paginated["total_pages"],
        "stats": stats
    })

@app.route('/api/prospects/<int:prospect_id>', methods=['PUT', 'DELETE'])
def api_modify_prospect(prospect_id):
    if request.method == 'DELETE':
        database.delete_prospect(prospect_id)
        return jsonify({"message": "Prospect deletado com sucesso!"})
    else:
        # PUT
        data = request.json
        database.update_prospect(prospect_id, data)
        return jsonify({"message": "Prospect atualizado com sucesso!"})

# Approve All Pending Leads with Email
@app.route('/api/prospects/approve-all', methods=['POST'])
def api_approve_all_pending():
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE prospects 
            SET status = 'approved', updated_at = datetime('now')
            WHERE status = 'pending' 
              AND contact_email IS NOT NULL 
              AND contact_email != ''
              AND is_international = 0
        """)
        count = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"{count} leads com e-mail foram aprovados para a fila de envio!", "approved_count": count})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erro ao aprovar leads: {str(e)}"}), 500

# Enrich Single Prospect with KipFlow
@app.route('/api/prospects/<int:prospect_id>/enrich', methods=['POST'])
def api_enrich_prospect(prospect_id):
    try:
        enriched_prospect = agent.enrich_prospect_with_kipflow(prospect_id)
        if enriched_prospect:
            return jsonify({"success": True, "message": "Lead enriquecido com sucesso!", "data": enriched_prospect})
        else:
            return jsonify({"success": False, "message": "Não foi possível enriquecer o lead. Verifique se a chave da API está correta e se a empresa possui CNPJ/domínio cadastrado no KipFlow."}), 400
    except Exception as e:
        return jsonify({"success": False, "message": f"Erro interno: {str(e)}"}), 500

# Send Single Email
@app.route('/api/prospects/<int:prospect_id>/send', methods=['POST'])
def api_send_single_email(prospect_id):
    data = request.json or {}
    bypass_limit = data.get('bypass_limit', False)
    try:
        success, msg = mailer.send_prospect_email(prospect_id, bypass_limit=bypass_limit)
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# Queue Worker Thread
def background_queue_sender(bypass_limit=False):
    global is_sending_queue, queue_status
    
    approved_leads = database.get_prospects(status_filter='approved')
    sent_today = database.get_sent_count_today()
    try:
        limit = int(database.get_setting('daily_email_limit', '20'))
    except:
        limit = 20
        
    remaining = limit - sent_today
    
    if bypass_limit:
        to_send = approved_leads
    else:
        if remaining <= 0:
            queue_status["status"] = "completed"
            queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] Limite diário de {limit} e-mails já foi atingido.")
            with queue_lock:
                is_sending_queue = False
            return
        to_send = approved_leads[:remaining]
        
    queue_status["total"] = len(to_send)
    queue_status["current"] = 0
    queue_status["status"] = "sending"
    
    queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] Iniciando envio de lote com {len(to_send)} e-mails...")
    
    for lead in to_send:
        # Check if user cancelled or system state changed (optional, but keep it simple)
        queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] Enviando e-mail para: {lead['company_name']} ({lead['contact_email']})...")
        try:
            mailer.send_prospect_email(lead['id'], bypass_limit=bypass_limit)
            queue_status["current"] += 1
            queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] ✅ Enviado com sucesso para {lead['company_name']}!")
        except Exception as e:
            queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] ❌ Falha no envio para {lead['company_name']}: {str(e)}")
            
        # Add random delay between 5 and 15 seconds to look human and avoid spam
        import random
        delay = random.randint(5, 15)
        queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] Aguardando {delay} segundos antes do próximo envio...")
        time.sleep(delay)
        
    queue_status["status"] = "completed"
    queue_status["logs"].append(f"[{time.strftime('%H:%M:%S')}] Envio do lote finalizado. Total enviados com sucesso neste ciclo: {queue_status['current']}/{queue_status['total']}.")
    
    with queue_lock:
        is_sending_queue = False

# Send Queue Endpoint
@app.route('/api/queue/send', methods=['POST'])
def api_send_queue():
    global is_sending_queue, queue_status
    
    with queue_lock:
        if is_sending_queue:
            return jsonify({"error": "Já existe um envio de lote em andamento."}), 400
            
        is_sending_queue = True
        
    data = request.json or {}
    bypass_limit = data.get('bypass_limit', False)
    
    # Reset queue status
    queue_status = {
        "current": 0,
        "total": 0,
        "status": "running",
        "logs": ["Fila de disparo iniciada..."]
    }
    
    thread = threading.Thread(target=background_queue_sender, args=(bypass_limit,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Disparo em lote iniciado!", "status": queue_status})

@app.route('/api/queue/status', methods=['GET'])
def api_get_queue_status():
    global is_sending_queue, queue_status
    return jsonify({
        "is_sending_queue": is_sending_queue,
        "status": queue_status
    })

# WhatsApp Opportunities & Closing Center Endpoints
# (listagem priorizada, mark-contacted e outcome vivem em whatsapp_routes.py: C9 do PLANO_PROSPECTADOR)
@app.route('/api/whatsapp/unmark-contacted/<int:prospect_id>', methods=['POST'])
def api_whatsapp_unmark_contacted(prospect_id):
    database.mark_whatsapp_contacted(prospect_id, False)
    return jsonify({"success": True, "message": "Lead retornado para a fila de WhatsApp!"})

@app.route('/api/whatsapp/save-draft/<int:prospect_id>', methods=['POST'])
def api_whatsapp_save_draft(prospect_id):
    body = request.json or {}
    draft = body.get('draft', '')
    database.update_whatsapp_custom_draft(prospect_id, draft)
    return jsonify({"success": True, "message": "Mensagem personalizada salva!"})

# Start Autopilot thread for production/Gunicorn
try:
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug or os.environ.get('DATA_DIR'):
        autopilot_thread = threading.Thread(target=background_autopilot_scheduler)
        autopilot_thread.daemon = True
        autopilot_thread.start()
        search_thread = threading.Thread(target=background_autopilot_search_scheduler)
        search_thread.daemon = True
        search_thread.start()
        prefetch_thread = threading.Thread(target=background_mockup_prefetch)
        prefetch_thread.daemon = True
        prefetch_thread.start()
        print("[Autopilot] Threads do Piloto Automático (envio e busca) iniciadas com sucesso.")
except Exception as e:
    print(f"[Autopilot] Aviso ao iniciar thread: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Super Prospectador Paviani está ligando na porta {port}...")
    app.run(host='0.0.0.0', debug=False if os.environ.get('PORT') else True, port=port)
