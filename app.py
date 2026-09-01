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

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-prospector-paviani-secret-key-2026')

# Initialize DB on startup
database.init_db()

def get_admin_password():
    # Priority: Environment variable -> Database setting
    env_pass = os.environ.get('ADMIN_PASSWORD')
    if env_pass is not None:
        return env_pass
    return database.get_setting('admin_password', '')

DIAG_TOKEN = os.environ.get('DIAGNOSTICS_TOKEN', 'paviani-diag-token-2026')

def is_diag_authorized():
    token = request.headers.get('X-Diag-Key') or request.args.get('diag_key')
    return bool(token and token.strip() == DIAG_TOKEN)

@app.before_request
def require_auth():
    # Allow programmatic diagnostics & monitoring with secure token
    if is_diag_authorized():
        return None

    admin_pass = get_admin_password()
    # If no password configured, access is open
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
        password = request.form.get('password', '')
        if password == admin_pass:
            session['authenticated'] = True
            return redirect('/')
        else:
            error = "Senha incorreta. Tente novamente."
            
    return render_template('login.html', error=error)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('authenticated', None)
    return redirect('/login')

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
        
    approved_leads = database.get_prospects(status_filter='approved')
    if not approved_leads:
        autopilot_status["sender_status"] = "no_leads"
        return
        
    approved_leads.sort(key=lambda x: x.get('created_at', ''))
    target_lead = approved_leads[0]
    
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
        is_validation_error = "não possui e-mail" in error_msg or "vazio" in error_msg
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
    last_search_str = database.get_setting('autopilot_last_search_run_at', '')
    if not last_search_str:
        return True, ""
        
    try:
        last_search = datetime.strptime(last_search_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=database.SAO_PAULO_TZ)
    except Exception:
        return True, ""
        
    try:
        interval_hours = int(database.get_setting('autopilot_search_interval_hours', '12'))
    except Exception:
        interval_hours = 12
        
    elapsed = (database.get_now() - last_search).total_seconds() / 3600.0
    if elapsed < interval_hours:
        return False, f"Intervalo de buscas não atingido ({elapsed:.1f} horas)"
        
    return True, ""

def autopilot_run_next_search(force=False):
    if not force and database.get_setting('autopilot_search_enabled', '0') != '1':
        autopilot_status["search_status"] = "disabled"
        return
        
    if not force:
        ok, _ = check_search_interval()
        if not ok:
            autopilot_status["search_status"] = "waiting_interval"
            return
        
    targets_str = database.get_setting('autopilot_search_targets', '[]')
    try:
        targets = json.loads(targets_str)
    except:
        targets = []
        
    if not targets:
        autopilot_status["search_status"] = "no_targets"
        return
        
    try:
        current_idx = int(database.get_setting('autopilot_search_target_index', '0'))
    except:
        current_idx = 0
        
    if current_idx >= len(targets):
        current_idx = 0
        
    target = targets[current_idx]
    next_idx = (current_idx + 1) % len(targets)
    database.save_settings({'autopilot_search_target_index': str(next_idx)})
    
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
    autopilot_log(f"Iniciando busca automática do Autopilot: Segmento='{segment}', Região='{region}' (Alvo: {search_limit} leads, Tipo: {search_type})...")
    
    try:
        now_str = database.get_now_str()
        database.save_settings({'autopilot_last_search_run_at': now_str})
        
        state_uf, city_name = agent.parse_autopilot_region(region)
            
        if search_type == 'maps_only' or target.get('is_surgical', False):
            agent.run_surgical_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, surgical_type='both', is_autopilot=1)
        elif search_type == 'kipflow':
            agent.run_prospecting_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, is_autopilot=1, source_mode="kipflow")
        else:
            agent.run_prospecting_job(segment, region, max_results=search_limit, state_uf=state_uf, city_name=city_name, radius_km=radius_km, is_autopilot=1, source_mode="organic")
            
        autopilot_log(f"✅ Busca automática do Autopilot concluída com sucesso!")
        log_autopilot_activity("Busca Automática", f"Busca concluída para '{segment}' em '{region}' (Qtd: {search_limit}, Fonte: {search_type})", "success")
    except Exception as e:
        autopilot_log(f"❌ Erro na busca automática: {e}")
        log_autopilot_activity("Busca Automática", f"Falha na busca para '{segment}' em '{region}': {str(e)}", "error")
    finally:
        autopilot_status["search_status"] = "idle"

def background_autopilot_scheduler():
    while True:
        try:
            autopilot_send_next_email()
        except Exception as e:
            pass
            
        try:
            autopilot_run_next_search()
        except Exception as e:
            pass
            
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
            
        recent_prospects = database.get_prospects()[:10]
        prospects_summary = []
        for p in recent_prospects:
            prospects_summary.append({
                "id": p.get("id"),
                "company_name": p.get("company_name"),
                "website": p.get("website"),
                "email": p.get("email"),
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
    return jsonify(prospects)

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
    
    if is_surgical == 'all':
        is_surgical_filter = None
    elif is_surgical is not None:
        try:
            is_surgical_filter = int(is_surgical)
        except:
            is_surgical_filter = 0
    else:
        is_surgical_filter = 0 # Default to standard prospects
        
    prospects = database.get_prospects(status_filter, is_surgical_filter)
    
    # Calculate counters based on surgical filter
    all_prospects = database.get_prospects(is_surgical_filter=is_surgical_filter)
    stats = {
        "total": len(all_prospects),
        "pending": len([p for p in all_prospects if p['status'] == 'pending']),
        "approved": len([p for p in all_prospects if p['status'] == 'approved']),
        "rejected": len([p for p in all_prospects if p['status'] == 'rejected']),
        "sent": len([p for p in all_prospects if p['status'] == 'sent']),
        "failed": len([p for p in all_prospects if p['status'] == 'failed']),
        "sent_today": database.get_sent_count_today(),
        "daily_limit": int(database.get_setting('daily_email_limit', '20'))
    }
    
    return jsonify({
        "prospects": prospects,
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

# Start Autopilot thread for production/Gunicorn
try:
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug or os.environ.get('DATA_DIR'):
        autopilot_thread = threading.Thread(target=background_autopilot_scheduler)
        autopilot_thread.daemon = True
        autopilot_thread.start()
        print("[Autopilot] Thread do Piloto Automático iniciada com sucesso.")
except Exception as e:
    print(f"[Autopilot] Aviso ao iniciar thread: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Super Prospectador Paviani está ligando na porta {port}...")
    app.run(host='0.0.0.0', debug=False if os.environ.get('PORT') else True, port=port)
