import sqlite3
import os
import json
import math
import zoneinfo
from datetime import datetime, timezone, timedelta

try:
    SAO_PAULO_TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
except Exception:
    SAO_PAULO_TZ = timezone(timedelta(hours=-3))

def get_now():
    return datetime.now(SAO_PAULO_TZ)

def get_now_str():
    return get_now().strftime('%Y-%m-%d %H:%M:%S')

def get_today_start_str():
    return get_now().strftime('%Y-%m-%d 00:00:00')

DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get('DB_PATH', os.path.join(DATA_DIR, 'prospector.db'))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # Create prospects table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prospects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            website TEXT,
            segment TEXT,
            region TEXT,
            status TEXT DEFAULT 'pending',
            detected_issues TEXT,
            contact_email TEXT,
            contact_whatsapp TEXT,
            contact_phone TEXT,
            email_subject TEXT,
            email_body TEXT,
            whatsapp_draft TEXT,
            notes TEXT,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME
        )
    ''')
    
    # Run automatic migrations to add columns if they don't exist
    cursor.execute("PRAGMA table_info(prospects)")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'whatsapp_draft' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN whatsapp_draft TEXT")
    if 'screenshot' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN screenshot TEXT")
    if 'followup_status' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN followup_status TEXT DEFAULT 'pending'")
    if 'followup_sent_at' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN followup_sent_at DATETIME")
    if 'is_surgical' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN is_surgical INTEGER DEFAULT 0")
    if 'surgical_type' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN surgical_type TEXT")
    if 'is_autopilot' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN is_autopilot INTEGER DEFAULT 0")
    if 'cnpj' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN cnpj TEXT")
    if 'faturamento' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN faturamento TEXT")
    if 'porte' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN porte TEXT")
    if 'funcionarios' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN funcionarios TEXT")
    if 'socios' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN socios TEXT")
    if 'redes_sociais' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN redes_sociais TEXT")
    if 'is_international' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN is_international INTEGER DEFAULT 0")
    if 'international_country' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN international_country TEXT")
    if 'reviews_count' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN reviews_count INTEGER DEFAULT 0")
    if 'rating' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN rating REAL DEFAULT 0.0")
    if 'opportunity_score' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN opportunity_score INTEGER DEFAULT 0")
    if 'is_directory' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN is_directory INTEGER DEFAULT 0")
    if 'directory_source' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN directory_source TEXT")
    if 'whatsapp_contacted' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN whatsapp_contacted INTEGER DEFAULT 0")
    if 'whatsapp_contacted_at' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN whatsapp_contacted_at DATETIME")
    if 'whatsapp_custom_draft' not in columns:
        cursor.execute("ALTER TABLE prospects ADD COLUMN whatsapp_custom_draft TEXT")
    # PLANO_PROSPECTADOR T1/Q2: estagio do funil, resultado comercial e qualificacao
    for col, ddl in (('stage', 'TEXT'), ('deal_value', 'REAL'), ('closed_at', 'DATETIME'),
                     ('win_source', 'TEXT'), ('qualification', 'TEXT')):
        if col not in columns:
            cursor.execute(f"ALTER TABLE prospects ADD COLUMN {col} {ddl}")

    
    # Seed default settings if they don't exist
    default_settings = {
        'sender_name': 'Matheus Paviani',
        'sender_whatsapp': '(51) 99766-1506',
        'sender_pitch': 'Criação e modernização de sites modernos, responsivos e de alta conversão para indústrias, com foco em apresentar a qualidade e robustez dos seus serviços.',
        'gemini_api_key': '',
        'gemini_model': 'gemini-2.5-flash-lite',
        'kipflow_api_key': '',   # NUNCA colocar chaves no codigo; cadastre na tela de configuracoes
        'serper_api_key': '',
        'searlo_api_key': '',
        'searlo_daily_budget': '1500',
        'brave_api_key': '',
        'cloro_api_key': '',
        'gosom_api_url': '',
        'smtp_host': 'smtp.hostinger.com',
        'smtp_port': '465',
        'smtp_security': 'SSL',  # SSL, STARTTLS, None
        'smtp_user': '',
        'smtp_password': '',
        'daily_email_limit': '150',
        'email_rules': 'Escreva de forma extremamente personalizada. No assunto, utilize uma abordagem intrigante (ex: "Enquanto analisava a {empresa}, surgiu uma ideia"). Comece o e-mail se apresentando de forma direta e breve. Em seguida, mencione especificamente o site deles e liste os problemas técnicos de forma amigável (ex: Wix, não responsivo, copyright desatualizado). Explique como isso pode impactar a percepção da empresa e mencione que você desenhou um estudo visual rápido mostrando como ficaria o site novo. Chame para uma conversa rápida de 10 minutos.',
        'autopilot_sender_enabled': '0',
        'autopilot_sender_interval_min': '3',
        'autopilot_sender_hours_enabled': '1',
        'autopilot_sender_start_hour': '8',
        'autopilot_sender_end_hour': '18',
        'autopilot_sender_days': '1,2,3,4,5',
        'autopilot_search_enabled': '0',
        'autopilot_search_targets': '[]',
        'autopilot_search_interval_hours': '2',
        'autopilot_search_batch_size': '30',
        'autopilot_auto_approve': '1',
        'autopilot_last_email_sent_at': '',
        'autopilot_last_search_run_at': '',
        'sender_portfolio': 'https://paviani.net/portfolio/',
        # PLANO_PROSPECTADOR E1/Q2: identificacao no rodape do e-mail e verificacao antes do envio
        'sender_company': '',
        'sender_address': '',
        'sender_cnpj': '',
        'public_base_url': '',
        'qualify_before_send': '1',
        'whatsapp_daily_goal': '15',
        # E4/M1: e-mail honesto e variado (template) ou geracao livre antiga (ai); esboco automatico no envio
        'email_generation_mode': 'template',
        'mockup_in_email': '1',
        'mockup_daily_limit': '40',
        # C1: follow-up automatico (desligado ate o usuario ligar)
        'autopilot_auto_rotate': '1',
        'cnpj_site_discovery': '1',
        'serper_daily_budget': '800',
        'autopilot_search_min_gap_min': '2',
        'autopilot_queue_target': '60',
        'autopilot_search_daily_cap': '60',
        'autopilot_cooldown_days': '14',
        'followup_enabled': '0',
        'followup_daily_limit': '8',
        'followup_max_age_days': '30',
        # T3: leitura da caixa de entrada (respostas e rejeicoes)
        'imap_enabled': '0',
        'imap_host': 'imap.hostinger.com',
        # T4: alertas de lead quente e resumo diario (e-mail para voce mesmo)
        'alerts_enabled': '1',
        'alert_email': '',
        'digest_hour': '8'
    }
    
    for key, val in default_settings.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
        
    cursor.execute("DELETE FROM settings WHERE key = 'mockup_base_url'")
    
    # Auto-cleanup any known junk domains/portals that might have been saved in the past
    junk_patterns = [
        '%cnn.com%', '%cnnbrasil.com%', '%decolar.com%', '%despegar.com%', '%buscape.com%', 
        '%trivago.com%', '%biteable.com%', '%msn.com%', '%msnow.com%', '%booking.com%', 
        '%tripadvisor.com%', '%airbnb.com%', '%mercadolivre.com%', '%magazineluiza.com%', 
        '%reclameaqui.com%', '%wikipedia.org%', '%youtube.com%', '%facebook.com/sharer%', 
        '%instagram.com/p/%', '%canva.com%', '%adobe.com%', '%kayak.com%', '%expedia.com%',
        '%skyscanner.com%', '%123milhas.com%', '%maxmilhas.com%', '%hotmart.com%', '%kiwify.com%'
    ]
    for pattern in junk_patterns:
        cursor.execute("DELETE FROM prospects WHERE website LIKE ? OR company_name LIKE ?", (pattern, pattern.replace('%', '')))

    # PLANO_PROSPECTADOR T1/E1: eventos do funil e lista de bloqueio (descadastros, rejeicoes definitivas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id INTEGER,
            type TEXT NOT NULL,
            detail TEXT,
            meta TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_prospect ON events(prospect_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_type_date ON events(type, created_at)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppressions (
            value TEXT PRIMARY KEY,
            kind TEXT DEFAULT 'email',
            reason TEXT,
            prospect_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    _backfill_events(cursor)

    conn.commit()
    conn.close()

def _backfill_events(cursor):
    """Uma unica vez: cria eventos para o que ja aconteceu (envios, falhas, follow-ups), para o historico nao comecar zerado."""
    cursor.execute("SELECT value FROM settings WHERE key = 'events_backfilled'")
    if cursor.fetchone():
        return
    cursor.execute("SELECT id, status, sent_at, error_message, updated_at, followup_status, followup_sent_at, "
                   "whatsapp_contacted, whatsapp_contacted_at FROM prospects")
    for r in cursor.fetchall():
        if r['status'] == 'sent' and r['sent_at']:
            cursor.execute("INSERT INTO events (prospect_id, type, created_at) VALUES (?, 'email_sent', ?)", (r['id'], r['sent_at']))
        elif r['status'] == 'failed':
            cursor.execute("INSERT INTO events (prospect_id, type, detail, created_at) VALUES (?, 'email_failed', ?, ?)",
                           (r['id'], (r['error_message'] or '')[:200], r['updated_at']))
        if r['followup_status'] == 'done' and r['followup_sent_at']:
            cursor.execute("INSERT INTO events (prospect_id, type, created_at) VALUES (?, 'followup_done', ?)", (r['id'], r['followup_sent_at']))
        if r['whatsapp_contacted']:
            cursor.execute("INSERT INTO events (prospect_id, type, created_at) VALUES (?, 'whatsapp_contacted', ?)",
                           (r['id'], r['whatsapp_contacted_at'] or r['updated_at']))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('events_backfilled', ?)", (get_now_str(),))

def get_setting(key, default=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['value']
    return default

def get_all_settings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT key, value FROM settings')
    rows = cursor.fetchall()
    conn.close()
    return {row['key']: row['value'] for row in rows}

def save_settings(settings_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    for key, val in settings_dict.items():
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(val)))
    conn.commit()
    conn.close()

SHARED_DOMAINS = {
    'wixsite.com', 'ueniweb.com', 'wordpress.com', 'blogspot.com', 'github.io',
    'simplesite.com', 'weebly.com', 'jimdofree.com', 'cargo.site', 'webflow.io'
}

def get_registered_domain(host):
    if not host:
        return ""
    host = host.lower().strip()
    if host.startswith('www.'):
        host = host[4:]
        
    parts = host.split('.')
    if len(parts) <= 2:
        return host
        
    second_to_last = parts[-2]
    last = parts[-1]
    
    # Check for common Brazilian double extensions (like .com.br, .ind.br, etc.)
    # or other country code double extensions (like .co.uk)
    if len(last) == 2 and (len(second_to_last) <= 3 or second_to_last in ['com', 'ind', 'net', 'org', 'gov', 'edu', 'co', 'ac']):
        return '.'.join(parts[-3:])
    else:
        return '.'.join(parts[-2:])

def check_domain_exists(domain, full_url=None):
    if not domain:
        return None
    domain = domain.lower().strip()
    if domain.startswith('www.'):
        domain = domain[4:]
        
    reg_domain = get_registered_domain(domain)
    if not reg_domain:
        return None
        
    # Check if this is a social media domain
    is_social = reg_domain in ['facebook.com', 'instagram.com', 'fb.com', 'instagram.com.br']
    is_shared = reg_domain in SHARED_DOMAINS
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, website FROM prospects')
    rows = cursor.fetchall()
    conn.close()
    
    from urllib.parse import urlparse
    for row in rows:
        web = row['website']
        if not web:
            continue
        try:
            # If it's a social media domain, compare the paths (usernames)
            if is_social and full_url:
                parsed_web = urlparse(web.lower().strip())
                parsed_full = urlparse(full_url.lower().strip())
                
                web_reg = get_registered_domain(parsed_web.netloc)
                full_reg = get_registered_domain(parsed_full.netloc)
                
                if web_reg == full_reg:
                    path_web = parsed_web.path.strip('/')
                    path_full = parsed_full.path.strip('/')
                    if path_web == path_full:
                        return row['id']
                continue
                
            parsed = urlparse(web)
            dom = parsed.netloc.lower()
            if not dom:
                temp = web.lower().strip()
                if '/' in temp:
                    temp = temp.split('/')[0]
                dom = temp
            if dom.startswith('www.'):
                dom = dom[4:]
                
            if is_shared:
                if dom == domain:
                    return row['id']
            else:
                row_reg = get_registered_domain(dom)
                if row_reg == reg_domain:
                    # Skip social domains from standard domain matching
                    if reg_domain in ['facebook.com', 'instagram.com', 'fb.com', 'instagram.com.br']:
                        continue
                    return row['id']
        except:
            continue
    return None

def add_prospect(prospect_dict):
    website = prospect_dict.get('website', '')
    domain = ''
    if website:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(website)
            domain = parsed.netloc.lower()
            if not domain:
                temp = website.lower().strip()
                if '/' in temp:
                    temp = temp.split('/')[0]
                domain = temp
            if domain.startswith('www.'):
                domain = domain[4:]
        except:
            domain = ''
            
    is_dir = prospect_dict.get('is_directory', 0)
    directory_domains = ['guiamais.com.br', 'solutudo.com.br', 'apontador.com.br', 'telelistas.net', 'cnpj.biz']
    if domain and not is_dir and not any(d in domain for d in directory_domains):
        existing_id = check_domain_exists(domain, full_url=website)
        if existing_id:
            return existing_id
            
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if company already exists by exact website
    cursor.execute('SELECT id FROM prospects WHERE website = ?', (website,))
    existing = cursor.fetchone()
    if existing:
        conn.close()
        return existing['id']
        
    now = get_now_str()
    
    status = prospect_dict.get('status', 'pending')
    email = prospect_dict.get('contact_email', '')
    notes_value = prospect_dict.get('notes')

    # Q1: e-mail sem sintaxe valida (lixo de CSS/JS/arquivo) nunca entra como contato
    if email:
        import validators
        e_status, e_why, e_norm = validators.check_email(email, check_dns=False)
        if e_status == 'valid':
            email = e_norm
        else:
            notes_value = ((notes_value or '') + f"\n[sistema] e-mail descartado ({e_why}): {email}").strip()
            email = ''

    if status == 'pending' and email:
        try:
            auto_approve = get_setting('autopilot_auto_approve', '0') == '1'
            if auto_approve:
                status = 'approved'
        except:
            pass

    # Q3: aprovacao so passa pelas portas (e-mail valido, nao bloqueado, site proprio). Falhou: fica pendente com motivo.
    if status == 'approved':
        gate_ok, gate_why = approval_gate(dict(prospect_dict, contact_email=email))
        if not gate_ok:
            status = 'pending'
            notes_value = ((notes_value or '') + f"\n[sistema] aprovacao automatica bloqueada: {gate_why}").strip()

    # Q4/Q5: nome de menu/rodape ("Sobre", "Pagina Inicial") vira o nome do dominio; segmento com a mesma grafia ("metalurgica" = "Metalurgica")
    import whatsapp_msg
    company_value = prospect_dict.get('company_name')
    if whatsapp_msg.is_junk_name(company_value):
        company_value = whatsapp_msg.brand_from_domain(prospect_dict.get('website')) or company_value
    segment_value = normalize_segment(prospect_dict.get('segment'))

    cursor.execute('''
        INSERT INTO prospects (
            company_name, website, segment, region, status, 
            detected_issues, contact_email, contact_whatsapp, contact_phone, 
            email_subject, email_body, whatsapp_draft, notes, screenshot, 
            is_surgical, surgical_type, is_autopilot, cnpj, faturamento,
            porte, funcionarios, socios, redes_sociais, is_international,
            international_country, reviews_count, rating, opportunity_score,
            is_directory, directory_source,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        company_value,
        prospect_dict.get('website'),
        segment_value,
        prospect_dict.get('region'),
        status,
        json.dumps(prospect_dict.get('detected_issues', [])),
        email,
        prospect_dict.get('contact_whatsapp'),
        prospect_dict.get('contact_phone'),
        prospect_dict.get('email_subject'),
        prospect_dict.get('email_body'),
        prospect_dict.get('whatsapp_draft'),
        notes_value,
        prospect_dict.get('screenshot'),
        prospect_dict.get('is_surgical', 0),
        prospect_dict.get('surgical_type'),
        prospect_dict.get('is_autopilot', 0),
        prospect_dict.get('cnpj'),
        prospect_dict.get('faturamento'),
        prospect_dict.get('porte'),
        prospect_dict.get('funcionarios'),
        prospect_dict.get('socios'),
        prospect_dict.get('redes_sociais'),
        prospect_dict.get('is_international', 0),
        prospect_dict.get('international_country'),
        prospect_dict.get('reviews_count', 0),
        prospect_dict.get('rating', 0.0),
        prospect_dict.get('opportunity_score', 0),
        prospect_dict.get('is_directory', 0),
        prospect_dict.get('directory_source'),
        now, now
    ))
    
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    add_event(new_id, 'prospect_created', status)
    return new_id

# Alias for compatibility
insert_prospect = add_prospect


# ---------------------------------------------------------------------------------------------
# PLANO_PROSPECTADOR: eventos (T1), lista de bloqueio (E1), estagios e porta de aprovacao (Q3)
# ---------------------------------------------------------------------------------------------
STAGES = ('novo', 'contatado', 'respondeu', 'interessado', 'reuniao', 'proposta', 'ganho', 'perdido', 'descadastrou', 'invalido')
_NOT_A_SITE = ('telelistas', 'guiamais', 'solutudo', 'apontador', 'econodata', 'cnpj.biz', 'casadosdados', 'cnpja', 'facebook',
               'instagram', 'linkedin', 'youtube', 'linktr.ee', 'wa.me', 'tiktok', 'twitter')


def normalize_segment(segment):
    """'metalúrgica' e 'Metalúrgica' (e 'metalúrgica ') passam a ser o mesmo segmento: espacos limpos e 1a letra maiuscula."""
    s = ' '.join((segment or '').split())
    return (s[0].upper() + s[1:]) if s else s


def add_event(prospect_id, event_type, detail=None, meta=None, created_at=None):
    """Registra um evento do funil. Medir NUNCA pode derrubar o fluxo: qualquer erro e engolido."""
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO events (prospect_id, type, detail, meta, created_at) VALUES (?, ?, ?, ?, ?)',
                     (prospect_id, event_type, detail, json.dumps(meta, ensure_ascii=False) if meta is not None else None,
                      created_at or get_now_str()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_events(prospect_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT id, type, detail, meta, created_at FROM events WHERE prospect_id = ? ORDER BY id', (prospect_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_suppression(value, reason='', prospect_id=None, kind=None):
    """Bloqueia um e-mail (ou dominio) para sempre. Respeitada em todo envio."""
    value = (value or '').strip().lower()
    if not value:
        return False
    kind = kind or ('email' if '@' in value else 'domain')
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO suppressions (value, kind, reason, prospect_id, created_at) VALUES (?, ?, ?, ?, ?)',
                 (value, kind, reason, prospect_id, get_now_str()))
    conn.commit()
    conn.close()
    return True


def is_suppressed(email):
    email = (email or '').strip().lower()
    if not email:
        return False
    domain = email.rsplit('@', 1)[1] if '@' in email else email
    conn = get_db_connection()
    row = conn.execute('SELECT 1 FROM suppressions WHERE value IN (?, ?) LIMIT 1', (email, domain)).fetchone()
    conn.close()
    return bool(row)


def set_stage(prospect_id, stage, deal_value=None, note=None, source=None):
    """Muda o estagio do funil (ex.: ganho/perdido) e registra o evento. 'descadastrou' tambem bloqueia o e-mail."""
    if stage not in STAGES:
        raise ValueError(f"estagio invalido '{stage}'. Use um de: {', '.join(STAGES)}")
    prospect = get_prospect(prospect_id)
    if not prospect:
        raise ValueError(f"prospect {prospect_id} nao encontrado")
    now = get_now_str()
    sets, params = ['stage = ?', 'updated_at = ?'], [stage, now]
    if stage in ('ganho', 'perdido'):
        sets.append('closed_at = ?'); params.append(now)
    if deal_value is not None:
        sets.append('deal_value = ?'); params.append(float(deal_value))
    if source:
        sets.append('win_source = ?'); params.append(source)
    params.append(prospect_id)
    conn = get_db_connection()
    conn.execute(f"UPDATE prospects SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    add_event(prospect_id, f'stage:{stage}', note, {'deal_value': deal_value, 'source': source})
    if stage == 'descadastrou' and prospect.get('contact_email'):
        add_suppression(prospect['contact_email'], 'descadastro (estagio)', prospect_id)
    return True


def approval_gate(prospect_dict):
    """Q3: portas para aprovar sem olhar. Devolve (ok, motivo). Rapida e sem rede (o DNS/IA ficam na hora do envio)."""
    import validators
    from urllib.parse import urlparse
    email = (prospect_dict.get('contact_email') or '').strip()
    if not email:
        return False, 'sem e-mail de contato'
    st, why = validators.check_syntax(email)
    if st != 'valid':
        return False, f'e-mail invalido ({why})'
    if is_suppressed(email):
        return False, 'e-mail na lista de bloqueio'
    site_host = urlparse(prospect_dict.get('website') or '').netloc.lower()
    if any(d in site_host for d in _NOT_A_SITE) and not prospect_dict.get('is_directory'):
        return False, 'o site cadastrado e diretorio/rede social, nao o site da empresa'
    return True, ''

def get_prospect(prospect_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM prospects WHERE id = ?', (prospect_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res['detected_issues'] = json.loads(res['detected_issues']) if res['detected_issues'] else []
        return res
    return None

def get_prospects(status_filter=None, is_surgical_filter=None, is_international_filter=None, is_directory_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM prospects'
    params = []
    clauses = []
    
    if status_filter:
        clauses.append('status = ?')
        params.append(status_filter)
        
    if is_surgical_filter is not None:
        clauses.append('is_surgical = ?')
        params.append(int(is_surgical_filter))

    if is_directory_filter is not None:
        clauses.append('is_directory = ?')
        params.append(int(is_directory_filter))
        
    if is_international_filter is not None:
        clauses.append('is_international = ?')
        params.append(int(is_international_filter))
    else:
        clauses.append('is_international = 0')
        
    if clauses:
        query += ' WHERE ' + ' AND '.join(clauses)
        
    query += ' ORDER BY id DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        res = dict(row)
        res['detected_issues'] = json.loads(res['detected_issues']) if res['detected_issues'] else []
        result.append(res)
    return result

def get_prospects_stats(is_surgical_filter=None, is_international_filter=0, is_directory_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    clauses = ['is_international = ?']
    params = [int(is_international_filter)]
    if is_surgical_filter is not None:
        clauses.append('is_surgical = ?')
        params.append(int(is_surgical_filter))
    if is_directory_filter is not None:
        clauses.append('is_directory = ?')
        params.append(int(is_directory_filter))
        
    query = 'SELECT status, COUNT(*) as count FROM prospects WHERE ' + ' AND '.join(clauses) + ' GROUP BY status'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    counts = {r['status']: r['count'] for r in rows}
    total = sum(counts.values())
    
    today_start = get_today_start_str()
    cursor.execute('SELECT COUNT(*) as count FROM prospects WHERE status = "sent" AND sent_at >= ?', (today_start,))
    sent_today_row = cursor.fetchone()
    sent_today = sent_today_row['count'] if sent_today_row else 0
    
    conn.close()
    
    return {
        "total": total,
        "pending": counts.get("pending", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "sent": counts.get("sent", 0),
        "failed": counts.get("failed", 0),
        "sent_today": sent_today,
        "daily_limit": int(get_setting('daily_email_limit', '20'))
    }

def get_prospects_paginated(page=1, limit=24, status_filter=None, search_query=None, is_surgical_filter=None, is_international_filter=0, is_directory_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    clauses = ['is_international = ?']
    params = [int(is_international_filter)]
    
    if is_surgical_filter is not None:
        clauses.append('is_surgical = ?')
        params.append(int(is_surgical_filter))

    if is_directory_filter is not None:
        clauses.append('is_directory = ?')
        params.append(int(is_directory_filter))
        
    if status_filter and status_filter != 'all':
        clauses.append('status = ?')
        params.append(status_filter)
        
    if search_query:
        search_pattern = f'%{search_query.strip()}%'
        clauses.append('(company_name LIKE ? OR website LIKE ? OR contact_email LIKE ? OR contact_phone LIKE ? OR contact_whatsapp LIKE ? OR notes LIKE ? OR cnpj LIKE ?)')
        params.extend([search_pattern] * 7)
        
    where_sql = ' WHERE ' + ' AND '.join(clauses)
    
    # Fast count of matching filtered records
    count_query = 'SELECT COUNT(*) as count FROM prospects' + where_sql
    cursor.execute(count_query, params)
    total_filtered = cursor.fetchone()['count']
    
    # Query only page slice
    query = 'SELECT * FROM prospects' + where_sql + ' ORDER BY id DESC'
    
    if limit is not None and limit > 0:
        offset = (max(1, page) - 1) * limit
        query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    prospects = []
    for row in rows:
        res = dict(row)
        res['detected_issues'] = json.loads(res['detected_issues']) if res['detected_issues'] else []
        prospects.append(res)
        
    return {
        "prospects": prospects,
        "total": total_filtered,
        "page": page,
        "limit": limit or total_filtered,
        "total_pages": math.ceil(total_filtered / limit) if (limit and limit > 0) else 1
    }

def update_prospect(prospect_id, update_dict):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Handle detected_issues conversion to JSON
    if 'detected_issues' in update_dict:
        update_dict['detected_issues'] = json.dumps(update_dict['detected_issues'])
        
    update_dict['updated_at'] = get_now_str()
    
    set_clause = ', '.join([f"{k} = ?" for k in update_dict.keys()])
    values = list(update_dict.values())
    values.append(prospect_id)
    
    cursor.execute(f'UPDATE prospects SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()

def delete_prospect(prospect_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM prospects WHERE id = ?', (prospect_id,))
    conn.commit()
    conn.close()

def get_sent_count_today():
    conn = get_db_connection()
    cursor = conn.cursor()
    today_start = get_today_start_str()
    cursor.execute('SELECT COUNT(id) as count FROM prospects WHERE status = "sent" AND sent_at >= ?', (today_start,))
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0

def get_whatsapp_opportunities(subtab='email_sent', segment=None, search_query=None, min_score=None, page=1, limit=24):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Must have a phone or whatsapp number
    clauses = [
        "((contact_whatsapp IS NOT NULL AND contact_whatsapp != '') OR (contact_phone IS NOT NULL AND contact_phone != ''))"
    ]
    params = []
    
    if subtab == 'email_sent':
        # Email has been sent, now follow-up via WhatsApp
        clauses.append("status = 'sent'")
        clauses.append("(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
    elif subtab == 'no_email':
        # No email address found, WhatsApp is the primary cold outreach channel
        clauses.append("(contact_email IS NULL OR contact_email = '')")
        clauses.append("status != 'sent'")
        clauses.append("(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
    elif subtab == 'contacted':
        # Already contacted via WhatsApp
        clauses.append("whatsapp_contacted = 1")
    elif subtab == 'all_pending':
        # All with WhatsApp not contacted yet
        clauses.append("(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
        
    if segment and segment != 'all':
        clauses.append("segment = ?")
        params.append(segment)
        
    if min_score is not None and str(min_score).isdigit() and int(min_score) > 0:
        clauses.append("opportunity_score >= ?")
        params.append(int(min_score))
        
    if search_query:
        sq = f"%{search_query.strip()}%"
        clauses.append("(company_name LIKE ? OR region LIKE ? OR contact_phone LIKE ? OR contact_whatsapp LIKE ?)")
        params.extend([sq, sq, sq, sq])
        
    where_sql = ' WHERE ' + ' AND '.join(clauses)
    
    count_query = 'SELECT COUNT(*) as count FROM prospects' + where_sql
    cursor.execute(count_query, params)
    total_filtered = cursor.fetchone()['count']
    
    # Priority sorting: highest opportunity score first!
    query = 'SELECT * FROM prospects' + where_sql + ' ORDER BY opportunity_score DESC, id DESC'
    if limit is not None and limit > 0:
        offset = (max(1, page) - 1) * limit
        query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    prospects = []
    for row in rows:
        res = dict(row)
        res['detected_issues'] = json.loads(res['detected_issues']) if res['detected_issues'] else []
        prospects.append(res)
        
    return {
        "prospects": prospects,
        "total": total_filtered,
        "page": page,
        "limit": limit or total_filtered,
        "total_pages": math.ceil(total_filtered / limit) if (limit and limit > 0) else 1
    }

def get_whatsapp_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    wa_filter = "((contact_whatsapp IS NOT NULL AND contact_whatsapp != '') OR (contact_phone IS NOT NULL AND contact_phone != ''))"
    
    # 1. Total with WhatsApp
    cursor.execute(f"SELECT COUNT(*) as count FROM prospects WHERE {wa_filter}")
    total_wa = cursor.fetchone()['count']
    
    # 2. Email sent & pending WhatsApp follow-up
    cursor.execute(f"SELECT COUNT(*) as count FROM prospects WHERE {wa_filter} AND status = 'sent' AND (whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
    email_sent_count = cursor.fetchone()['count']
    
    # 3. No email & pending WhatsApp initial contact
    cursor.execute(f"SELECT COUNT(*) as count FROM prospects WHERE {wa_filter} AND (contact_email IS NULL OR contact_email = '') AND status != 'sent' AND (whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
    no_email_count = cursor.fetchone()['count']
    
    # 4. Already contacted via WhatsApp
    cursor.execute(f"SELECT COUNT(*) as count FROM prospects WHERE {wa_filter} AND whatsapp_contacted = 1")
    contacted_count = cursor.fetchone()['count']
    
    # 5. Distinct segments that have WhatsApp leads
    cursor.execute(f"SELECT DISTINCT segment FROM prospects WHERE {wa_filter} AND segment IS NOT NULL AND segment != '' ORDER BY segment")
    segments = [r['segment'] for r in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_wa": total_wa,
        "email_sent_count": email_sent_count,
        "no_email_count": no_email_count,
        "contacted_count": contacted_count,
        "segments": segments
    }

def mark_whatsapp_contacted(prospect_id, contacted=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    if contacted:
        now_str = get_now_str()
        cursor.execute("UPDATE prospects SET whatsapp_contacted = 1, whatsapp_contacted_at = ?, updated_at = ? WHERE id = ?", (now_str, now_str, prospect_id))
    else:
        cursor.execute("UPDATE prospects SET whatsapp_contacted = 0, whatsapp_contacted_at = NULL, updated_at = ? WHERE id = ?", (get_now_str(), prospect_id))
    conn.commit()
    conn.close()
    return True

def update_whatsapp_custom_draft(prospect_id, draft_text):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE prospects SET whatsapp_custom_draft = ?, updated_at = ? WHERE id = ?", (draft_text, get_now_str(), prospect_id))
    conn.commit()
    conn.close()
    return True


# ---------------------------------------------------------------------------------------------
# PLANO_PROSPECTADOR C9: Central WhatsApp (candidatos sem paginar, contagem do dia, telefones bloqueados)
# ---------------------------------------------------------------------------------------------
def get_whatsapp_candidates(subtab='email_sent', segment=None, search_query=None):
    """Todos os prospects da fila indicada (a paginacao e a ordem por prioridade ficam com quem chama).
    Exclui telefone invalido, quem pediu para parar e telefones na lista de bloqueio."""
    conn = get_db_connection()
    cursor = conn.cursor()
    clauses = ["((contact_whatsapp IS NOT NULL AND contact_whatsapp != '') OR (contact_phone IS NOT NULL AND contact_phone != ''))",
               "(stage IS NULL OR stage NOT IN ('invalido', 'descadastrou'))"]
    params = []
    if subtab == 'email_sent':
        clauses += ["status = 'sent'", "(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)"]
    elif subtab == 'no_email':
        clauses += ["(contact_email IS NULL OR contact_email = '')", "status != 'sent'", "(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)"]
    elif subtab == 'contacted':
        clauses.append("whatsapp_contacted = 1")
    elif subtab == 'all_pending':
        clauses.append("(whatsapp_contacted = 0 OR whatsapp_contacted IS NULL)")
    if segment and segment != 'all':
        clauses.append("segment = ?")
        params.append(segment)
    if search_query:
        sq = f"%{search_query.strip()}%"
        clauses.append("(company_name LIKE ? OR region LIKE ? OR contact_phone LIKE ? OR contact_whatsapp LIKE ?)")
        params.extend([sq, sq, sq, sq])
    cursor.execute('SELECT * FROM prospects WHERE ' + ' AND '.join(clauses), params)
    rows = cursor.fetchall()
    blocked = {r['value'] for r in cursor.execute("SELECT value FROM suppressions WHERE kind = 'phone'").fetchall()}
    conn.close()
    out = []
    for row in rows:
        res = dict(row)
        digits = ''.join(ch for ch in (res.get('contact_whatsapp') or res.get('contact_phone') or '') if ch.isdigit())
        if digits and (digits in blocked or ('55' + digits) in blocked or (digits[2:] in blocked if digits.startswith('55') else False)):
            continue
        res['detected_issues'] = json.loads(res['detected_issues']) if res['detected_issues'] else []
        out.append(res)
    return out


def whatsapp_today_counts():
    """Quantos contatos de WhatsApp foram marcados hoje, no total e por conta (business/personal)."""
    conn = get_db_connection()
    rows = conn.execute("SELECT meta FROM events WHERE type = 'whatsapp_contacted' AND created_at >= ?", (get_today_start_str(),)).fetchall()
    conn.close()
    by_account = {}
    for r in rows:
        try:
            acc = (json.loads(r['meta']) or {}).get('account') or 'sem_conta'
        except Exception:
            acc = 'sem_conta'
        by_account[acc] = by_account.get(acc, 0) + 1
    return {"total": len(rows), "by_account": by_account}


def whatsapp_last_contact_at():
    conn = get_db_connection()
    row = conn.execute("SELECT created_at FROM events WHERE type = 'whatsapp_contacted' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row['created_at'] if row else None
