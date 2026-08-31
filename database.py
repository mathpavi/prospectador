import sqlite3
import os
import json
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
    
    
    # Seed default settings if they don't exist
    default_settings = {
        'sender_name': 'Matheus Paviani',
        'sender_whatsapp': '(51) 99766-1506',
        'sender_pitch': 'Criação e modernização de sites modernos, responsivos e de alta conversão para indústrias, com foco em apresentar a qualidade e robustez dos seus serviços.',
        'gemini_api_key': '',
        'kipflow_api_key': '27faee9a-15f3-4dfb-a1d0-383ac5fef117',
        'serper_api_key': '',
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
        'sender_portfolio': 'https://paviani.net/portfolio/'
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
        
    conn.commit()
    conn.close()

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
            
    if domain:
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
    if status == 'pending' and email:
        try:
            auto_approve = get_setting('autopilot_auto_approve', '0') == '1'
            if auto_approve:
                status = 'approved'
        except:
            pass
            
    cursor.execute('''
        INSERT INTO prospects (
            company_name, website, segment, region, status, 
            detected_issues, contact_email, contact_whatsapp, contact_phone, 
            email_subject, email_body, whatsapp_draft, notes, screenshot, 
            is_surgical, surgical_type, is_autopilot, cnpj, faturamento,
            porte, funcionarios, socios, redes_sociais, is_international,
            international_country, reviews_count, rating, opportunity_score,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        prospect_dict.get('company_name'),
        prospect_dict.get('website'),
        prospect_dict.get('segment'),
        prospect_dict.get('region'),
        status,
        json.dumps(prospect_dict.get('detected_issues', [])),
        prospect_dict.get('contact_email'),
        prospect_dict.get('contact_whatsapp'),
        prospect_dict.get('contact_phone'),
        prospect_dict.get('email_subject'),
        prospect_dict.get('email_body'),
        prospect_dict.get('whatsapp_draft'),
        prospect_dict.get('notes'),
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
        now, now
    ))
    
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

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

def get_prospects(status_filter=None, is_surgical_filter=None, is_international_filter=None):
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
