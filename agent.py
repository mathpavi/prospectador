import time
import re
import random
import requests
import os
import math
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import google.generativeai as genai
import json
import logging
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# List of domains to ignore (directories, social media, portals, news, global tech, travel aggregators)
IGNORED_DOMAINS = [
    # Social & Media Networks
    'facebook.com', 'instagram.com', 'linkedin.com', 'youtube.com', 'twitter.com', 'x.com',
    'pinterest.com', 'tiktok.com', 'reddit.com', 'quora.com', 'medium.com', 'tumblr.com', 
    'discord.com', 'telegram.org', 'whatsapp.com', 'threads.net',
    
    # Portals, Directories & Company Lookups
    'apontador.com.br', 'telelistas.net', 'guiamais.com.br', 'solutudo.com.br', 'econodata.com.br',
    'casadosdados.com.br', 'cnpj.info', 'empresascnpj.com', 'transparencia.cc', 'jusbrasil.com.br',
    'guiadefatos.com.br', 'cnpj.biz', 'infocnpj.com.br', 'consultacnpj.com', 'habito.com.br', 
    'empresasdobrasil.com', 'empresas.rio', 'portaldaempresa.com', 'situacaocadastral.info',
    'speedio.com.br', 'receitaws.com.br', 'cnpjaqui.com.br', 'empresasaqui.com',
    
    # News & Media Giants
    'cnn.com', 'cnnbrasil.com.br', 'msn.com', 'msnow.com', 'globo.com', 'g1.globo.com', 
    'uol.com.br', 'terra.com.br', 'r7.com', 'estadao.com.br', 'folha.uol.com.br', 'folha.com',
    'bbc.com', 'reuters.com', 'bloomberg.com', 'forbes.com', 'foxnews.com', 'nytimes.com', 
    'washingtonpost.com', 'theguardian.com', 'dailymail.co.uk', 'techcrunch.com', 'theverge.com', 
    'infomoney.com.br', 'exame.com', 'valor.globo.com', 'gazetadopovo.com.br', 'jovempan.com.br', 
    'metropoles.com', 'poder360.com.br', 'cartacapital.com.br', 'veja.abril.com.br', 'istoedinheiro.com.br',
    'abril.com.br', 'canaltech.com.br', 'tecmundo.com.br', 'olhardigital.com.br',
    
    # Travel, Flight & Hotel Aggregators
    'decolar.com', 'despegar.com', 'trivago.com', 'trivago.com.br', 'booking.com', 'airbnb.com', 
    'airbnb.com.br', 'tripadvisor.com', 'tripadvisor.com.br', 'kayak.com', 'kayak.com.br', 
    'expedia.com', 'expedia.com.br', 'hoteis.com', 'hotels.com', 'skyscanner.com', 'skyscanner.com.br', 
    '123milhas.com', 'maxmilhas.com.br', 'voegol.com.br', 'latamairlines.com', 'voeazul.com.br', 
    'cvc.com.br', 'agoda.com', 'hostelworld.com', 'viator.com', 'getyourguide.com', 'decolar.com.br',
    
    # Price Comparators, E-commerce & Marketplaces
    'buscape.com.br', 'zoom.com.br', 'bondfaro.com.br', 'mercadolivre.com.br', 'mercadolibre.com', 
    'amazon.com', 'amazon.com.br', 'ebay.com', 'shopee.com.br', 'shopee.com', 'aliexpress.com', 
    'magazineluiza.com.br', 'americanas.com.br', 'submarino.com.br', 'casasbahia.com.br', 
    'pontofrio.com.br', 'extra.com.br', 'carrefour.com.br', 'kabum.com.br', 'shein.com', 
    'temu.com', 'walmart.com', 'target.com', 'bestbuy.com', 'costco.com', 'homedepot.com', 
    'lowes.com', 'ikea.com', 'leroymerlin.com.br', 'elo7.com.br', 'enjoei.com.br',
    
    # Global Generic SaaS, Video/Design & Cloud Giants
    'biteable.com', 'canva.com', 'adobe.com', 'renderforest.com', 'invideo.io', 'animoto.com', 
    'powtoon.com', 'loom.com', 'vimeo.com', 'wistia.com', 'figma.com', 'notion.so', 'miro.com', 
    'trello.com', 'monday.com', 'asana.com', 'clickup.com', 'hubspot.com', 'salesforce.com', 
    'zendesk.com', 'intercom.com', 'mailchimp.com', 'rdstation.com', 'hotmart.com', 'kiwify.com.br', 
    'eduzz.com', 'shopify.com', 'nuvemshop.com.br', 'wix.com', 'squarespace.com', 'godaddy.com', 
    'hostgator.com.br', 'hostinger.com', 'locaweb.com.br', 'cloudflare.com', 'microsoft.com', 
    'google.com', 'apple.com', 'netflix.com', 'spotify.com', 'github.com', 'gitlab.com',
    'stackoverflow.com', 'wikipedia.org', 'wikimedia.org',
    
    # Job, Review & Classified Portals
    'reclameaqui.com.br', 'trustpilot.com', 'yelp.com', 'bbb.org', 'glassdoor.com', 'glassdoor.com.br', 
    'indeed.com', 'indeed.com.br', 'catho.com.br', 'vagas.com.br', 'infojobs.com.br', 'gupy.io', 
    'solides.com.br', 'olx.com.br', 'craigslist.org', 'quintoandar.com.br', 'zapimoveis.com.br', 
    'vivareal.com.br', 'imovelweb.com.br', 'webmotors.com.br', 'icarros.com.br',
    
    # Education & Institutional
    'sebrae.com.br', 'sebraers.com.br', 'senai.br', 'sesi.org.br', 'fiesp.com.br', 'senac.br',
    'getninjas.com.br', 'habitissimo.com.br', 'starofservice.com.br', 'cronoshare.com.br'
]

def ddg_text_search(query, max_results=20):
    """
    Runs DuckDuckGo text search with fallback to HTML backend if API is rate-limited.
    """
    # 1. Try 'auto' (API) backend first
    try:
        with DDGS() as ddgs:
            res = ddgs.text(query, max_results=max_results, backend='auto')
            res_list = list(res) if res else []
            if res_list:
                return res_list
    except Exception as e:
        logger.warning(f"DDG auto backend failed for query '{query}': {e}")
        
    # 2. Try 'html' backend as a fallback
    try:
        with DDGS() as ddgs:
            res = ddgs.text(query, max_results=max_results, backend='html')
            res_list = list(res) if res else []
            if res_list:
                return res_list
    except Exception as e:
        logger.warning(f"DDG html backend failed for query '{query}': {e}")
        
    return []

# Keywords in domain names to block immediately
FORBIDDEN_DOMAIN_KEYWORDS = [
    # Portals, directories, and corporate listings
    'cnpj', 'transparencia', 'econodata', 'casadosdados', 'apontador', 'telelistas', 'guiamais', 
    'solutudo', 'cadastro', 'lista', 'guiacomercial', 'encontra', 'leads', 'speedio', 
    'situacao-cadastral', 'diretorio', 'catalogo', 'catalog', 'biz', 'queme', 'infocnpj',
    'infoisinfo', 'moovit', 'guias', 'listas',
    
    # News, blogs, and media
    'noticia', 'jornal', 'revista', 'blog', 'portal', 'forum', 'wikipedia', 'news', 'press', 
    'imprensa', 'media', 'g1', 'r7', 'globo', 'uol', 'terra', 'estadao', 'folha', 'infomoney', 
    'exame', 'valor', 'canaltech', 'tecmundo', 'olhardigital', 'radio', 'tv', 'broadcasting',
    'difusora', 'fm', 'webradio', 'msn', 'msnow', 'cnn', 'bbc', 'reuters', 'bloomberg',
    
    # Aggregators, comparators, travel & tickets
    'compare', 'comparador', 'cotacao', 'seguro', 'simulador', 'preco', 'tarifas', 'banco', 'tabela',
    'decolar', 'despegar', 'trivago', 'booking', 'tripadvisor', 'airbnb', 'kayak', 'expedia', 
    'passagem', 'passagens', 'hospedagem', 'hotel', 'hoteis', 'voo', 'voos', 'milhas', 'turismo', 
    'viagem', 'viagens', 'buscape', 'zoom', 'bondfaro', 'cupom', 'desconto',
    
    # SaaS, video tools, templates
    'biteable', 'canva', 'renderforest', 'invideo', 'animoto', 'powtoon', 'loom', 'figma',
    'software', 'download', 'template', 'templates', 'appstore', 'googleplay',
    
    # Government, education, associations, federations
    'sebrae', 'senai', 'sesi', 'fiesp', 'fiergs', 'firjan', 'iel', 'cni', 'fecomercio', 
    'federacao', 'sindicato', 'associacao', 'prefeitura', 'governo',
    
    # E-commerce, marketplaces, and online shops
    'shopping', 'marketplace', 'loja', 'store', 'shop', 'mercado-livre', 'mercadolivre', 
    'shopee', 'magazinevoce', 'magazineluiza', 'americanas', 'submarino', 'amazon', 
    'leroymerlin', 'elo7', 'aliexpress', 'shein', 'kabum', 'temu',
    
    # Job search portals
    'catho', 'vagas', 'emprego', 'infojobs', 'indeed', 'gupy', 'solides', 'glassdoor'
]

# Thread-safe log store for real-time progress updates in the UI
job_logs = []

STATE_NAMES = {
    'AC': ['Acre'], 'AL': ['Alagoas'], 'AP': ['Amapá', 'Amapa'], 'AM': ['Amazonas'], 
    'BA': ['Bahia'], 'CE': ['Ceará', 'Ceara'], 'DF': ['Distrito Federal'], 'ES': ['Espírito Santo', 'Espirito Santo'], 
    'GO': ['Goiás', 'Goias'], 'MA': ['Maranhão', 'Maranhao'], 'MT': ['Mato Grosso'], 'MS': ['Mato Grosso do Sul'], 
    'MG': ['Minas Gerais', 'Minas'], 'PA': ['Pará', 'Para'], 'PB': ['Paraíba', 'Paraiba'], 'PR': ['Paraná', 'Parana'], 
    'PE': ['Pernambuco'], 'PI': ['Piauí', 'Piaui'], 'RJ': ['Rio de Janeiro'], 'RN': ['Rio Grande do Norte'], 
    'RS': ['Rio Grande do Sul'], 'RO': ['Rondônia', 'Rondonia'], 'RR': ['Roraima'], 'SC': ['Santa Catarina'], 
    'SP': ['São Paulo', 'Sao Paulo'], 'SE': ['Sergipe'], 'TO': ['Tocantins']
}

def check_location_match(text, state_uf, allowed_cities=None):
    if not text:
        return False
    text_lower = text.lower()
    
    # 1. City check (takes precedence if allowed_cities is provided)
    if allowed_cities:
        city_matched = False
        for city in allowed_cities:
            if city.lower() in text_lower:
                city_matched = True
                break
        # If the city matches, we return True immediately (assumes state is correct since city matches)
        # This avoids false negatives where a local page mentions the city but not the state abbreviation (e.g. "RS")
        return city_matched
        
    # 2. State check (only if allowed_cities is not provided/empty)
    if state_uf:
        state_uf = state_uf.upper().strip()
        state_matched = False
        # Word boundary check for state abbreviation (e.g. \brs\b)
        if re.search(r'\b' + re.escape(state_uf.lower()) + r'\b', text_lower):
            state_matched = True
        else:
            # Check for full state names
            names = STATE_NAMES.get(state_uf, [])
            for name in names:
                if name.lower() in text_lower:
                    state_matched = True
                    break
        return state_matched
            
    return True

def add_log(message):
    logger.info(message)
    job_logs.append({
        'time': datetime.now().strftime('%H:%M:%S'),
        'message': message
    })
    # Keep logs size manageable
    if len(job_logs) > 500:
        job_logs.pop(0)

from datetime import datetime

def extract_base_domain(url):
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return ''

def clean_company_name(title, domain):
    # Try to extract a clean company name from the page title
    if not title:
        # Fallback to domain name without extension
        parts = domain.split('.')
        return parts[0].capitalize()
    
    # Get domain base name (e.g. "solleymetalurgica" from "solleymetalurgica.com.br")
    domain_base = domain.split('.')[0].lower()
    if domain_base.startswith('www'):
        domain_base = domain_base[3:]
        
    # Split title by common separators
    separators = [r'\|', r'\-', r'\–', r'\—', r'\:']
    pattern = '|'.join(separators)
    parts = re.split(pattern, title)
    
    # Clean the parts
    cleaned_parts = []
    for part in parts:
        part = part.strip()
        if part:
            cleaned_parts.append(part)
            
    if not cleaned_parts:
        return domain.split('.')[0].capitalize()
        
    # Choose the part that matches the domain base best
    if len(cleaned_parts) == 1:
        name = cleaned_parts[0]
    else:
        best_part = cleaned_parts[0]
        best_score = -99.0
        
        for part in cleaned_parts:
            part_lower = part.lower()
            
            # De-prioritize common page/action words
            is_page_word = any(w in part_lower for w in ['home', 'início', 'inicio', 'principal', 'inicial', 'contato', 'sobre', 'quem somos', 'serviços', 'servicos', 'index', 'nossos serviços', 'nossos servicos'])
            
            overlap_score = 0
            clean_part_letters = re.sub(r'[^a-z0-9]', '', part_lower)
            
            # If domain base is a substring of clean part, or vice-versa
            if clean_part_letters and domain_base:
                if domain_base in clean_part_letters or clean_part_letters in domain_base:
                    overlap_score += 15
                    
            # Count common letters
            intersection_len = len(set(clean_part_letters) & set(domain_base))
            overlap_score += intersection_len
            
            if is_page_word:
                overlap_score -= 20
                
            if overlap_score > best_score:
                best_score = overlap_score
                best_part = part
                
        name = best_part

    # Suffix/prefix stripping
    name = re.sub(r'(?i)\b(Ltda|S/?A|Eireli|MEI|ME|EPP)\b\.?', '', name).strip()
    name = re.sub(r'(?i)^\s*(Home|Início|Inicio|Principal|Inicial|Site Oficial|Bem-vindo|Welcome)\s*[-\|]?\s*', '', name).strip()
    name = re.sub(r'(?i)\s*[-\|]?\s*(Home|Início|Inicio|Principal|Inicial|Site Oficial|Bem-vindo|Welcome)\s*$', '', name).strip()
    
    # Clean leading prepositions/conjunctions
    name = re.sub(r'(?i)^e\s+', '', name).strip()
    name = re.sub(r'(?i)^de\s+', '', name).strip()
    name = re.sub(r'(?i)^em\s+', '', name).strip()
    
    # If the resulting name is too short or generic, fallback to domain base
    if len(name) < 3 or name.lower() in ['home', 'inicio', 'principal', 'inicial', 'advogado', 'metalurgica', 'industria', 'site']:
        parts = domain.split('.')
        name = parts[0].capitalize()
        
    return name

def is_blog_or_article_url(url):
    try:
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        
        # Exclude common blog and article path segments
        blog_indicators = [
            '/blog/', '/noticias/', '/noticia/', '/artigo/', '/artigos/', 
            '/post/', '/posts/', '/novidades/', '/materia/', '/materias/', 
            '/categoria/', '/category/', '/tag/', '/tags/', '/conteudo/', 
            '/comorefazer/', '/dicas/', '/como-', '/o-que-', '/qual-'
        ]
        for ind in blog_indicators:
            if ind in path_lower:
                return True
                
        # If the path is deep and contains hyphens (slug), it is likely a blog post/article
        path_segments = [s for s in parsed.path.split('/') if s]
        if len(path_segments) >= 2:
            allowed_pages = ['contato', 'contact', 'sobre', 'about', 'servicos', 'services', 'quem-somos', 'home', 'index']
            last_segment = path_segments[-1]
            if '-' in last_segment and not any(ap in last_segment for ap in allowed_pages):
                return True
    except:
        pass
    return False

def is_valid_company_title(title, snippet):
    if not title:
        return True
    title_lower = title.lower()
    
    # Forbidden keywords in title that indicate it is not a direct company site
    forbidden_title_keywords = [
        'sindicato', 'federação', 'federacao', 'associação', 'associacao', 'prefeitura', 'governo',
        'vagas', 'vaga de', 'emprego', 'empregos', 'trabalhe conosco', 'notícia', 'noticia', 'notícias',
        'jornal', 'revista', 'diário', 'diario', 'portal de', 'blog', 'fórum', 'forum', 'tcc', 'monografia',
        'história de', 'historico', 'histórico', 'estudo de caso', 'artigo', 'quais são', 'o que é',
        'como fazer', 'dicas de', 'guia de', 'lista de', 'catálogo de', 'catalogo de', 'cnpj da empresa',
        'dados da empresa', 'casadosdados', 'econodata', 'cnpj.biz', 'consultacnpj'
    ]
    
    for kw in forbidden_title_keywords:
        if kw in title_lower:
            return False
            
    return True

def is_valid_company_website(url):
    domain = extract_base_domain(url)
    if not domain:
        return False
        
    domain_lower = domain.lower()
    
    # Block government, educational and generic non-profit domains
    if any(domain_lower.endswith(ext) for ext in ['.gov.br', '.edu.br', '.org.br', '.gov', '.edu', '.org']):
        return False
        
    # Check if domain contains forbidden keywords
    for kw in FORBIDDEN_DOMAIN_KEYWORDS:
        if kw in domain_lower:
            return False
            
    # Check if domain is in ignored list or is a subdomain of ignored domains
    for d in IGNORED_DOMAINS:
        if domain_lower == d or domain_lower.endswith('.' + d):
            return False
            
    # Check if it has a file extension like .pdf or .zip
    if any(url.lower().endswith(ext) for ext in ['.pdf', '.zip', '.jpg', '.png', '.jpeg', '.gif', '.xml', '.txt']):
        return False
        
    # Check if URL looks like a blog article or post
    if is_blog_or_article_url(url):
        return False
        
    return True

def is_rejected_pattern(company_name, domain):
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT company_name, website FROM prospects WHERE status = 'rejected'")
        rows = cursor.fetchall()
        conn.close()
        
        name_lower = company_name.lower().strip()
        domain_lower = domain.lower().strip()
        
        for row in rows:
            rej_name = row['company_name'].lower().strip()
            rej_web = row['website'].lower().strip()
            
            rej_domain = extract_base_domain(rej_web)
            if rej_domain and (rej_domain == domain_lower or domain_lower.endswith('.' + rej_domain)):
                return True
                
            if rej_name == name_lower:
                return True
                
            # Filter indicators to learn from
            indicators = [
                'agência', 'agencia', 'jornal', 'portal', 'placar', 'jogo', 'lista de', 'guia de',
                'notícias', 'noticias', 'soluções industriais', 'solucoes industriais', 'empresaqui',
                'resultado', 'advocacia', 'advogados', 'associação', 'associacao', 'sindicato', 'federação', 'federacao'
            ]
            for ind in indicators:
                if ind in rej_name and ind in name_lower:
                    return True
                    
        return False
    except Exception as e:
        logger.error(f"Erro ao verificar padrão de rejeitados: {e}")
        return False

def is_huge_corporation(domain, page_text, title):
    large_brands = [
        'gm', 'generalmotors', 'chevrolet', 'betanin', 'astoria', 'tramontina', 
        'marcopolo', 'randon', 'fras-le', 'grendene', 'vulcabras', 'embraco', 
        'weg', 'gerdau', 'romi', 'ambev', 'nestle', 'petrobras', 'valeo', 
        'bosch', 'siemens', 'marilan', 'bauducco', 'unilever', 'fiat', 'ford', 
        'toyota', 'honda', 'renault', 'scania', 'volvo', 'mercedes', 'stellantis',
        'klabin', 'suzano', 'braskem', 'uol', 'terra', 'globo', 'jbs', 'friboi',
        'sadia', 'perdigao', 'brf', 'aurora', 'mrv', 'tupy', 'usiminas', 'csn',
        'oxiteno', 'bradesco', 'itau', 'santander', 'bb', 'caixa'
    ]
    domain_lower = domain.lower()
    for brand in large_brands:
        if brand == domain_lower or f".{brand}." in f".{domain_lower}." or domain_lower.startswith(f"{brand}."):
            return True
            
    text_lower = page_text.lower()
    title_lower = title.lower()
    
    enterprise_indicators = [
        'capital aberto', 'ações na b3', 'relação com investidores', 
        'ri.gerdau', 'ri.marcopolo', 'multinacional', 'global leader', 
        'portal do candidato', 'investidores', 'nossas marcas', 
        'grupo econômico', 'conselho de administração', 'relatório anual', 
        'demonstrações financeiras', 'valores mobiliários'
    ]
    for brand in large_brands:
        if f" {brand} " in f" {title_lower} " or title_lower.startswith(f"{brand} "):
            return True
            
    for indicator in enterprise_indicators:
        if indicator in text_lower:
            return True
            
    return False

def is_invalid_industry_site(url, title, page_text):
    text_lower = page_text.lower()
    title_lower = title.lower()
    
    # Check if it's a blog, directory or news site
    news_words = [
        'portal de notícias', 'portal de noticias', 'jornal', 'blog de', 'notícias de', 
        'revista', 'informe', 'coluna', 'guia de turismo', 'notícias', 'noticias', 'g1', 'r7',
        'brasil de fato', 'jornalismo', 'repórter', 'reporter', 'artigo', 'noticiário', 'noticiario', 'resultado'
    ]
    for w in news_words:
        if w in title_lower or re.search(rf'\b{w}\b', text_lower[:800], re.IGNORECASE):
            return True
            
    directory_words = [
        'lista de empresas', 'guia de empresas', 'catálogo de', 'encontre empresas', 
        'telefone de', 'endereço de', 'guiamais', 'apontador', 'econodata', 
        'casadosdados', 'cnpj', 'transparencia', 'empresas.rio', 'solutudo',
        'situação cadastral', 'situacao cadastral', 'quadro societário', 'quadro societario',
        'capital social', 'dados da empresa', 'cnpj da empresa',
        'encontre profissionais', 'contratar profissionais', 'profissionais cadastrados',
        'prestadores de serviço', 'prestador de serviço', 'peça orçamentos', 
        'receba orçamentos', 'solicite orçamentos', 'lista empresas', 'empresaqui',
        'locaisdobrasil', 'solucoesindustriais', 'soluções industriais', 'marcenarias', 'sindicato', 'catálogo', 'catalogo'
    ]
    for w in directory_words:
        if w in title_lower or re.search(rf'\b{w}\b', text_lower[:800], re.IGNORECASE):
            return True
            
    marketplace_words = [
        'shopping', 'marketplace', 'encontre ofertas', 'comparar preços', 
        'compre online', 'carrinho de compras', 'loja virtual', 'mercado livre',
        'frete grátis', 'frete gratis', 'adicionar ao carrinho', 'comprar agora'
    ]
    for w in marketplace_words:
        if w in title_lower or re.search(rf'\b{w}\b', text_lower[:1500], re.IGNORECASE):
            return True
            
    # Check if it's a web development, marketing, or design agency (as they are not prospects)
    agency_words = [
        'agência digital', 'agencia digital', 'agência de marketing', 'agencia de marketing',
        'marketing digital', 'criação de sites', 'criacao de sites', 'desenvolvimento web',
        'desenvolvimento de sites', 'software house', 'agência web', 'agencia web', 'agência de publicidade',
        'agencia de publicidade', 'consultoria de ti', 'desenvolvimento de sistemas'
    ]
    for w in agency_words:
        if w in title_lower or re.search(rf'\b{w}\b', text_lower[:1000], re.IGNORECASE):
            return True
            
    return False


MUNICIPIOS_DB = []

def load_municipios_database():
    global MUNICIPIOS_DB
    if MUNICIPIOS_DB:
        return MUNICIPIOS_DB
        
    db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'municipios.json')
    uf_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'estados.json')
    
    # Verify if files exist, if not, download them
    if not os.path.exists(db_file):
        add_log("Baixando base de dados de municípios...")
        try:
            r = requests.get('https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/json/municipios.json', timeout=15)
            with open(db_file, 'wb') as f:
                f.write(r.content)
        except Exception as e:
            add_log(f"Erro ao baixar base de municípios: {e}")
            
    if not os.path.exists(uf_file):
        add_log("Baixando base de dados de estados...")
        try:
            r = requests.get('https://raw.githubusercontent.com/kelvins/municipios-brasileiros/main/json/estados.json', timeout=15)
            with open(uf_file, 'wb') as f:
                f.write(r.content)
        except Exception as e:
            add_log(f"Erro ao baixar base de estados: {e}")
            
    # Load and merge
    try:
        if os.path.exists(db_file) and os.path.exists(uf_file):
            with open(db_file, 'r', encoding='utf-8-sig') as f:
                m_list = json.load(f)
            with open(uf_file, 'r', encoding='utf-8-sig') as f:
                uf_list = json.load(f)
                
            uf_map = {uf['codigo_uf']: uf['uf'] for uf in uf_list}
            
            MUNICIPIOS_DB = []
            for m in m_list:
                codigo_uf = m.get('codigo_uf')
                uf_sigla = uf_map.get(codigo_uf, '')
                MUNICIPIOS_DB.append({
                    'nome': m.get('nome'),
                    'uf': uf_sigla,
                    'lat': float(m.get('latitude')),
                    'lon': float(m.get('longitude'))
                })
            add_log(f"Base geográfica carregada: {len(MUNICIPIOS_DB)} municípios.")
    except Exception as e:
        add_log(f"Erro ao ler bases geográficas: {e}")
        
    return MUNICIPIOS_DB

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def search_google_raw(query, max_results=20):
    import urllib.parse
    
    url = f"https://www.google.com.br/search?q={urllib.parse.quote(query)}&num={max_results}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    html = ""
    try:
        from curl_cffi import requests as crequests
        r = crequests.get(url, headers=headers, impersonate="chrome120", timeout=10)
        html = r.text
    except Exception as ex:
        add_log(f"curl_cffi falhou, tentando requests padrão: {ex}")
        cookies = {'CONSENT': 'YES+cb.20210328-17-p0.en+FX+435'}
        r = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        html = r.text
        
    soup = BeautifulSoup(html, 'html.parser')
    
    if "enablejs" in html or "Atualize o navegador" in html or (soup.title and "Google Search" in soup.title.text and len(soup.find_all('a')) < 5):
        raise Exception("Google bloqueou a requisição (detectou bot ou JS check)")
        
    results = []
    for link_tag in soup.find_all('a', href=True):
        href = link_tag['href']
        url_clean = None
        if '/url?q=' in href:
            url_clean = href.split('/url?q=')[1].split('&')[0]
            url_clean = urllib.parse.unquote(url_clean)
        elif href.startswith('http') and 'google.com' not in href:
            url_clean = href
            
        if url_clean and url_clean.startswith('http'):
            if any(bad in url_clean for bad in ['support.google.com', 'accounts.google.com', 'maps.google.com', 'youtube.com']):
                continue
            
            h3 = link_tag.find('h3')
            title = h3.get_text() if h3 else link_tag.get_text()
            
            snippet = ""
            parent = link_tag.find_parent('div')
            if parent:
                sibling = parent.find_next_sibling('div')
                if sibling:
                    snippet = sibling.get_text()
                    
            results.append({
                'url': url_clean,
                'title': title.strip(),
                'snippet': snippet.strip()
            })
            
    return results

SEGMENT_VARIATIONS = {
    'metalúrgica': [
        'metalúrgica', 'serralheria', 'estruturas metálicas', 'usinagem', 
        'esquadrias', 'caldeiraria', 'corte e dobra', 'fundição', 
        'solda', 'corte a laser', 'tornearia', 'estamparia de metais', 
        'galvanização', 'pintura eletrostática', 'ferramentaria', 
        'corte plasma', 'jateamento de metais', 'dobra de tubos', 
        'trefilação', 'forjaria', 'calandragem', 'oxicorte',
        'esquadrias de alumínio', 'esquadrias de ferro', 'grades e portões',
        'estruturas de aço', 'dobragem de chapas', 'corte de chapas',
        'soldagem mig', 'soldagem tig', 'acabamento de metais',
        'metalização', 'tratamento de superfícies metálicas'
    ],
    'advogado': [
        'advogado', 'advogados', 'escritório de advocacia', 'advocacia', 
        'assessoria jurídica', 'advogado civil', 'advogado trabalhista', 
        'advogado tributarista', 'defesa jurídica'
    ],
    'lavagem': [
        'lavagem', 'lava car', 'lava rápido', 'estética automotiva', 
        'lavagem ecológica', 'higienização automotiva', 'polimento automotivo', 
        'lava jato'
    ],
    'manicure': [
        'manicure', 'pedicure', 'unhas em gel', 'alongamento de unhas', 
        'salão de beleza', 'studio de unhas', 'esmalteria'
    ]
}

def is_industrial_segment(segment):
    segment_lower = segment.lower()
    
    # Non-industrial/service indicators
    service_indicators = {
        'advogado', 'advocacia', 'médico', 'medico', 'médica', 'medica', 'clínica', 'clinica', 
        'consultório', 'consultorio', 'dentista', 'odontologia', 'arquiteto', 'arquitetura',
        'contabilidade', 'contador', 'imobiliária', 'imobiliaria', 'corretor', 'estética', 'estetica',
        'salão', 'salao', 'escola', 'curso', 'faculdade', 'restaurante', 'hotel', 'pousada', 'academia'
    }
    
    # If any service indicator is in the segment, it's NOT industrial
    if any(indicator in segment_lower for indicator in service_indicators):
        return False
        
    # Default industrial indicators
    industrial_indicators = {
        'indústria', 'industria', 'fábrica', 'fabrica', 'fabricação', 'fabricacao', 'metalúrgica', 
        'metalurgica', 'usinagem', 'repuxo', 'caldeiraria', 'soldagem', 'plásticos', 'plasticos', 
        'móveis', 'moveis', 'química', 'quimica', 'têxtil', 'textil', 'alimentos', 'embalagens', 
        'confecção', 'confeccao', 'ferramentaria', 'fundição', 'fundicao'
    }
    
    if any(indicator in segment_lower for indicator in industrial_indicators):
        return True
        
    return True

def search_companies(segment, region, max_results=10, location_query=None):
    loc = location_query if location_query else region
    # Clean any hyphens or descriptions from the location string to avoid search engine negative operator (-) issues
    loc = loc.replace(' - ', ' ').replace(' -', ' ').replace('- ', ' ')
    if '(+' in loc:
        loc = re.sub(r'\(\+\d+km\)', '', loc)
    loc = loc.strip()
    
    websites = []
    seen_domains = set()
    
    target_candidates_count = max(50, min(200, max_results * 4))
    
    is_industrial = is_industrial_segment(segment)
    
    # 1. Resolve segment variations
    seg_clean = segment.lower().strip()
    seg_vars = [segment]
    for key, var_list in SEGMENT_VARIATIONS.items():
        if key in seg_clean or seg_clean in key:
            seg_vars = var_list
            break
            
    # 2. Build the queries
    # Pick the main segment, plus up to 2 other random variations to keep searches fresh
    selected_seg_vars = [segment]
    other_vars = [v for v in seg_vars if v.lower() != seg_clean]
    if other_vars:
        selected_seg_vars.extend(random.sample(other_vars, min(len(other_vars), 2)))
        
    queries = []
    zones = ["", "centro", "zona norte", "zona sul", "zona leste"]
    
    if is_industrial:
        # Base industrial queries with segment variations
        for sv in selected_seg_vars:
            for zone in zones[:3]: # base, centro, zona norte
                zone_str = f" {zone}" if zone else ""
                queries.append(f'indústria "{sv}" "{loc}{zone_str}" -noticias -portal -vagas -empregos')
                queries.append(f'fábrica de "{sv}" "{loc}{zone_str}" -noticias -portal -vagas -empregos')
        
        # Add fallback queries
        queries.append(f'site:ind.br "{segment}" {loc}')
        queries.append(f'site:ind.br {loc}')
    else:
        # Service queries
        for sv in selected_seg_vars:
            for zone in zones: # all zones (centro, norte, sul, leste)
                zone_str = f" {zone}" if zone else ""
                queries.append(f'"{sv}" "{loc}{zone_str}" -noticias -portal -vagas -empregos')
                queries.append(f'"{sv}" em "{loc}{zone_str}" -noticias -portal -vagas -empregos')
                
        # site:com.br fallback queries
        queries.append(f'site:com.br "{segment}" {loc}')
        queries.append(f'site:com.br "{segment}" em {loc}')
    
    add_log(f'Executando busca no DuckDuckGo com {len(queries)} variações de consulta...')
    
    for idx, q in enumerate(queries):
        if len(websites) >= target_candidates_count:
            break
            
        add_log(f'Executando consulta DuckDuckGo {idx+1}/{len(queries)}: {q}...')
        try:
            results = ddg_text_search(q, max_results=40)
            for r in results:
                    url = r.get('href', '')
                    if not url:
                        continue
                        
                    try:
                        parsed = urlparse(url)
                        root_url = f"{parsed.scheme}://{parsed.netloc}/"
                    except Exception:
                        root_url = url
                        
                    if is_valid_company_website(root_url) and is_valid_company_title(r.get('title', ''), r.get('body', '')):
                        domain = extract_base_domain(root_url)
                        reg_domain = database.get_registered_domain(domain)
                        is_shared = reg_domain in database.SHARED_DOMAINS
                        check_key = domain if is_shared else reg_domain
                        
                        if check_key not in seen_domains and not database.check_domain_exists(domain):
                            seen_domains.add(check_key)
                            websites.append({
                                'url': root_url,
                                'title': r.get('title', ''),
                                'snippet': r.get('body', '')
                            })
                            
                    if len(websites) >= target_candidates_count:
                        break
        except Exception as e:
            if "No results found" in str(e):
                add_log(f'Consulta DuckDuckGo {idx+1} finalizada (sem resultados adicionais).')
            else:
                add_log(f'Aviso na consulta DuckDuckGo {idx+1}: {e}')
            
    # Fallback query if absolutely no sites were found
    if not websites:
        add_log('Nenhum site encontrado com as consultas principais. Tentando busca fallback ampla...')
        try:
            query_alt = f'{segment} {loc}'
            results = ddg_text_search(query_alt, max_results=30)
            for r in results:
                    url = r.get('href', '')
                    if not url:
                        continue
                    try:
                        parsed = urlparse(url)
                        root_url = f"{parsed.scheme}://{parsed.netloc}/"
                    except Exception:
                        root_url = url
                        
                    if is_valid_company_website(root_url) and is_valid_company_title(r.get('title', ''), r.get('body', '')):
                        domain = extract_base_domain(root_url)
                        reg_domain = database.get_registered_domain(domain)
                        is_shared = reg_domain in database.SHARED_DOMAINS
                        check_key = domain if is_shared else reg_domain
                        
                        if check_key not in seen_domains and not database.check_domain_exists(domain):
                            seen_domains.add(check_key)
                            websites.append({
                                'url': root_url,
                                'title': r.get('title', ''),
                                'snippet': r.get('body', '')
                            })
        except Exception as ex:
            add_log(f'Falha na busca fallback: {ex}')
            
    add_log(f'Encontrados {len(websites)} sites potenciais no total.')
    return websites

CNAE_MAPPING = {
    "metalúrgica": [2511000, 2539001, 2539002, 2540400, 2420200, 2513600, 2521700, 2522500, 2531401, 2531402, 2532201, 2532202, 2541200, 2542100, 2543900, 2592601, 2592602, 2593400, 2599301, 2599302, 2599399],
    "usinagem": [2539001, 2539002],
    "caldeiraria": [2513600],
    "serralheria": [2511000, 2542100],
    "soldagem": [2539001, 2539002],
    "estamparia": [2531401, 2531402],
    "fundição": [2451200, 2452100],
    "tratamento": [2532201, 2532202]
}

ESTADOS_BRASIL = {
    "AC": "ACRE", "AL": "ALAGOAS", "AP": "AMAPA", "AM": "AMAZONAS",
    "BA": "BAHIA", "CE": "CEARA", "DF": "DISTRITO FEDERAL", "ES": "ESPIRITO SANTO",
    "GO": "GOIAS", "MA": "MARANHAO", "MT": "MATO GROSSO", "MS": "MATO GROSSO DO SUL",
    "MG": "MINAS GERAIS", "PA": "PARA", "PB": "PARAIBA", "PR": "PARANA",
    "PE": "PERNAMBUCO", "PI": "PIAUI", "RJ": "RIO DE JANEIRO", "RN": "RIO GRANDE DO NORTE",
    "RS": "RIO GRANDE DO SUL", "RO": "RONDONIA", "RR": "RORAIMA", "SC": "SANTA CATARINA",
    "SP": "SAO PAULO", "SE": "SERGIPE", "TO": "TOCANTINS"
}

def search_companies_kipflow(segment, city_name, state_uf, limit=10):
    add_log(f"Iniciando busca KipFlow para Segmento='{segment}', Cidade='{city_name}', Estado='{state_uf}', Limite={limit}")
    
    api_key = database.get_setting('kipflow_api_key', '')
    if not api_key:
        add_log("Erro: Chave de API do KipFlow não configurada!")
        return []
        
    url = "https://api.kipflow.io/companies/v1/search"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    and_conditions = [
        { "$or": [ { "situacao_cadastral": "ATIVA" } ] }
    ]
    
    if state_uf:
        uf_name = ESTADOS_BRASIL.get(state_uf.upper().strip(), state_uf.upper().strip())
        and_conditions.append({ "$or": [ { "uf": uf_name } ] })
        
    if city_name and city_name != "Estado Inteiro" and city_name.strip() != "":
        and_conditions.append({ "$or": [ { "municipio": city_name.upper().strip() } ] })
        
    # Map segment to CNAE codes
    cnae_list = []
    seg_lower = segment.lower()
    for key, cnaes in CNAE_MAPPING.items():
        if key in seg_lower:
            cnae_list.extend(cnaes)
            
    if not cnae_list:
        # Default to metalurgica subclasses
        cnae_list = CNAE_MAPPING["metalúrgica"]
        
    or_cnaes = []
    for code in cnae_list:
        or_cnaes.append({ "cnae_principal_subclasse": code })
        
    if or_cnaes:
        and_conditions.append({ "$or": or_cnaes })
        
    payload = {
        "$filter": {
            "$and": and_conditions
        },
        "$page": 0,
        "$size": 50,
        "datasets": ["basic", "online_presence"]
    }
    
    companies = []
    seen_domains = set()
    page = 0
    max_pages = 5
    
    try:
        while len(companies) < limit and page < max_pages:
            payload["$page"] = page
            add_log(f"Consultando página {page} do KipFlow...")
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            if response.status_code != 200:
                add_log(f"Erro KipFlow API (status {response.status_code}): {response.text}")
                break
                
            data = response.json()
            if not data.get("success"):
                add_log(f"Erro retornado pela API KipFlow: {data.get('error')}")
                break
                
            results = data.get("data", [])
            if not results:
                add_log("Fim dos resultados no KipFlow.")
                break
                
            for item in results:
                sites = item.get("sites")
                if not sites:
                    continue
                for s in sites:
                    site_url = s.get("site")
                    if not site_url:
                        continue
                    # Clean and format url
                    site_url = site_url.strip().lower()
                    if not site_url.startswith("http://") and not site_url.startswith("https://"):
                        site_url = "https://" + site_url
                    domain = extract_base_domain(site_url)
                    if domain and domain not in seen_domains and not database.check_domain_exists(domain):
                        seen_domains.add(domain)
                        companies.append({
                            "url": site_url,
                            "title": item.get("nome_fantasia") or item.get("razao_social") or segment,
                            "snippet": item.get("cnae_principal_desc_subclasse") or "",
                            "cnpj": item.get("cnpj")
                        })
                        if len(companies) >= limit:
                            break
                if len(companies) >= limit:
                    break
            page += 1
    except Exception as e:
        add_log(f"Erro durante a busca avançada no KipFlow: {e}")
        
    add_log(f"Busca KipFlow finalizada. Encontradas {len(companies)} empresas válidas com site.")
    return companies

def enrich_prospect_with_kipflow(prospect_id, api_key=None):
    if not api_key:
        api_key = database.get_setting('kipflow_api_key', '')
    if not api_key:
        add_log("Erro: Chave de API do KipFlow não configurada!")
        return None
        
    prospect = database.get_prospect(prospect_id)
    if not prospect:
        add_log(f"Erro: Lead ID {prospect_id} não encontrado no banco.")
        return None
        
    url = prospect.get('website', '')
    cnpj = prospect.get('cnpj', '')
    
    query_param = ""
    if cnpj:
        query_param = f"cnpj={cnpj.replace('.', '').replace('/', '').replace('-', '').strip()}"
    elif url:
        domain = extract_base_domain(url)
        if domain:
            query_param = f"domain={domain}"
            
    if not query_param:
        add_log(f"Erro: Lead ID {prospect_id} não possui site ou CNPJ para consulta no KipFlow.")
        return None
        
    kipflow_url = f"https://api.kipflow.io/companies/v1/search?{query_param}&datasets=basic,complete,address,online_presence,partners"
    headers = {
        "X-API-Key": api_key
    }
    
    try:
        add_log(f"Enriquecendo lead ID {prospect_id} ({query_param}) via KipFlow...")
        response = requests.get(kipflow_url, headers=headers, timeout=15)
        if response.status_code != 200:
            add_log(f"Erro KipFlow API (status {response.status_code}): {response.text}")
            return None
            
        data = response.json()
        if not data.get("success") or not data.get("data"):
            add_log(f"KipFlow: Nenhuma informação encontrada para {query_param}")
            return None
            
        comp = data["data"]
        
        # Parse fields
        cnpj_val = comp.get("cnpj")
        porte = comp.get("porte")
        faturamento = comp.get("faixa_faturamento_grupo")
        funcionarios = comp.get("faixa_funcionarios_grupo") or comp.get("quantidade_funcionarios_grupo")
        
        # Partners
        partners_list = []
        for p in comp.get("socios", []):
            p_name = p.get("nome")
            p_qual = p.get("qualificacao")
            if p_name:
                partners_list.append({"nome": p_name, "cargo": p_qual})
                
        # Social media networks
        online = comp.get("online_presence", {}) or {}
        instagram = online.get("instagram") or online.get("instagram_url")
        facebook = online.get("facebook") or online.get("facebook_url")
        linkedin = online.get("linkedin") or online.get("linkedin_url")
        
        socials = {
            "instagram": instagram or "",
            "facebook": facebook or "",
            "linkedin": linkedin or ""
        }
        
        # Update dict
        update_dict = {
            "cnpj": cnpj_val,
            "porte": porte,
            "faturamento": faturamento,
            "funcionarios": str(funcionarios) if funcionarios else None,
            "socios": json.dumps(partners_list, ensure_ascii=False),
            "redes_sociais": json.dumps(socials, ensure_ascii=False)
        }
        
        database.update_prospect(prospect_id, update_dict)
        add_log(f"Lead ID {prospect_id} enriquecido com sucesso via KipFlow (CNPJ: {cnpj_val})")
        
        # Return merged dict
        prospect.update(update_dict)
        return prospect
    except Exception as e:
        add_log(f"Erro ao enriquecer lead ID {prospect_id} com KipFlow: {e}")
        return None

def capture_screenshot(url, filename):
    import os
    screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'screenshots')
    os.makedirs(screenshots_dir, exist_ok=True)
    output_path = os.path.join(screenshots_dir, filename)
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            page.goto(url, timeout=15000, wait_until='load')
            page.wait_for_timeout(2000)
            page.screenshot(path=output_path, full_page=False)
            browser.close()
        add_log(f"Screenshot capturado com sucesso para: {url}")
        return output_path
    except Exception as e:
        add_log(f"Aviso: Não foi possível capturar screenshot de {url}: {e}")
        return None

def analyze_website(url, segment, region, state_uf=None, allowed_cities=None):
    add_log(f'Analisando site: {url}')
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    
    issues = []
    contact_email = None
    contact_whatsapp = None
    contact_phone = None
    domain = extract_base_domain(url)
    
    # 1. Check if subdomain
    domain_parts = domain.split('.')
    is_subdomain = False
    if domain.endswith('.br'):
        if len(domain_parts) > 3:
            is_subdomain = True
    else:
        if len(domain_parts) > 2:
            is_subdomain = True
            
    if is_subdomain:
        issues.append('Subdomínio')
        
    # 2. Check if HTTPS
    if url.startswith('http://'):
        issues.append('Inseguro (HTTP)')
        
    # Fetch content
    html_content = ""
    final_url = url
    load_time = 0.0
    try:
        response = requests.get(url, headers=headers, timeout=6, allow_redirects=True)
        if response.status_code != 200:
            add_log(f"Ignorando {url} pois retornou HTTP status {response.status_code}")
            return None
            
        load_time = response.elapsed.total_seconds()
        response.encoding = response.apparent_encoding or 'utf-8'
        html_content = response.text
        final_url = response.url
        
        # Re-check domain validity after redirects (e.g. redirects to Facebook, directories, or blog)
        if not is_valid_company_website(final_url):
            add_log(f"Ignorando {url} pois redirecionou para um domínio/URL inválido: {final_url}")
            return None
            
        if final_url.startswith('http://') and 'Inseguro (HTTP)' not in issues:
            issues.append('Inseguro (HTTP)')
    except Exception as e:
        add_log(f'Não foi possível acessar {url} (Site offline ou erro de conexao): {e}')
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    page_text = soup.get_text()
    
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    # Filter out 404, error, and forbidden pages
    title_lower = title.lower()
    error_titles = [
        "404", "not found", "não encontrado", "nao encontrado", "erro", "error", 
        "forbidden", "acesso negado", "acesso proibido", "manutenção", "manutencao", 
        "temporariamente indisponível", "suspenso", "account suspended", "site suspenso"
    ]
    if not title or any(et in title_lower for et in error_titles):
        add_log(f"Ignorando {url} pois o título indica página de erro ou indisponível: '{title}'")
        return None
        
    # Filter out huge corporations
    if is_huge_corporation(domain, page_text, title):
        add_log(f"Ignorando {url} pois parece ser uma grande corporação/empresa de grande porte.")
        return None
        
    # Filter out news, directory and informative portals
    if is_invalid_industry_site(url, title, page_text):
        add_log(f"Ignorando {url} pois parece ser um portal, blog ou diretório.")
        return None
        
    # Check if the website actually relates to the segment to avoid capturing completely unrelated industries
    segment_lower = segment.lower()
    segment_keywords = [w.strip() for w in re.split(r'[\s/]+', segment_lower) if len(w.strip()) > 3 and w.strip() not in ['de', 'para', 'com', 'sem', 'sob', 'geral']]
    
    page_text_lower = page_text.lower()
    
    synonyms = {
        'móveis': ['moveis', 'mobiliário', 'mobiliario', 'móvel', 'movel', 'marcenaria', 'estofados', 'sofa', 'sofá', 'cozinhas', 'dormitórios', 'closets', 'wood', 'madeira', 'esquadrias'],
        'metalúrgica': ['metalurgica', 'metalurgia', 'ferro', 'aço', 'aco', 'usinagem', 'repuxo', 'estampagem', 'solda', 'caldeiraria', 'metal', 'metais', 'indústria metalúrgica', 'esquadrias', 'portões', 'estruturas metálicas'],
        'usinagem': ['torno', 'fresa', 'cnc', 'metalurgica', 'peças', 'pecas', 'usinagem'],
        'estofados': ['estofaria', 'sofá', 'sofa', 'poltrona', 'cadeiras', 'tapeçaria', 'tapecaria', 'colchão', 'colchao']
    }
    
    extended_keywords = list(segment_keywords)
    for kw in segment_keywords:
        if kw in synonyms:
            extended_keywords.extend(synonyms[kw])
    extended_keywords.append(segment_lower)
    
    has_segment_match = False
    for kw in extended_keywords:
        if kw in page_text_lower or kw in title_lower:
            has_segment_match = True
            break
            
    if not has_segment_match and segment_keywords:
        add_log(f"Ignorando {url} pois o conteúdo não parece relacionado ao segmento '{segment}'.")
        return None
    
    # Clean company name
    company_name = clean_company_name(title, domain)
    
    # Check if this matches a pattern of rejected/archived leads to filter out unwanted sites
    if is_rejected_pattern(company_name, domain):
        add_log(f"Ignorando {url} ({company_name}) pois corresponde a um padrão de lead arquivado/rejeitado.")
        return None
    
    # 3. Detect Wix
    is_wix = False
    if 'wixsite' in final_url or 'wix.com' in html_content or '_wix' in html_content:
        is_wix = True
    else:
        meta_gen = soup.find('meta', attrs={'name': 'generator'})
        if meta_gen and 'wix' in meta_gen.get('content', '').lower():
            is_wix = True
            
    if is_wix:
        issues.append('Feito no Wix')
        
    is_wp = False
    if 'wp-content' in html_content or 'wp-includes' in html_content:
        is_wp = True
        
    # 5. Check Responsiveness
    viewport = soup.find('meta', attrs={'name': 'viewport'})
    if not viewport or 'width=device-width' not in viewport.get('content', '').lower():
        issues.append('Não Responsivo (Sem tag Viewport)')
        
    # 6. Check Outdated Copyright
    current_year = datetime.now().year
    copyright_years = re.findall(r'(?:©|Copyright|Copiright)\s*(?:20\d{2})', page_text, re.IGNORECASE)
    
    outdated_year = None
    for cy in copyright_years:
        year_match = re.search(r'20\d{2}', cy)
        if year_match:
            year = int(year_match.group())
            if year < current_year - 2:
                outdated_year = year
                break
                
    if outdated_year:
        issues.append(f'Copyright desatualizado ({outdated_year})')
        
    # 7. Check page load time
    if load_time > 2.5:
        issues.append(f'Site Lento ({load_time:.1f}s)')
        
    # 8. Check SEO Description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if not meta_desc or not meta_desc.get('content', '').strip():
        issues.append('Sem Descrição SEO')
        
    # 9. Check H1 Heading
    if not soup.find('h1'):
        issues.append('Sem Título H1')
        
    # 10. Check Open Graph Image (WhatsApp Sharing preview)
    og_img = soup.find('meta', attrs={'property': 'og:image'})
    if not og_img or not og_img.get('content', '').strip():
        issues.append('Sem Prévia no WhatsApp')
        
    # 11. Check Favicon
    favicon = soup.find('link', rel=lambda x: x and 'icon' in x.lower())
    if not favicon:
        issues.append('Sem Favicon (Ícone)')
    elif favicon and ('wix' in favicon.get('href', '').lower() or 'wordpress' in favicon.get('href', '').lower() or 'wp-content' in favicon.get('href', '').lower()):
        issues.append('Favicon Genérico')
        
    # 12. Check Obsolete Frames
    if soup.find('frame') or soup.find('frameset'):
        issues.append('Uso de Frames (Obsoleto)')
        
    # 13. Check Placeholder text
    if 'lorem ipsum' in page_text.lower() or 'inserir texto' in page_text.lower():
        issues.append('Texto Provisório')
        
    # 14. Check Insecure Form Actions
    insecure_form = False
    for f in soup.find_all('form', action=True):
        if f['action'].startswith('http://'):
            insecure_form = True
            break
    if insecure_form:
        issues.append('Formulário Inseguro')
        
    # Search for contact info on homepage
    emails = find_emails_in_text(html_content)
    whatsapp_links = find_whatsapp_links(html_content, soup)
    phones = find_phones_in_text(page_text)
    
    if emails:
        contact_email = emails[0]
    if whatsapp_links:
        contact_whatsapp = whatsapp_links[0]
    if phones:
        contact_phone = phones[0]
        
    full_site_text = page_text
    sub_text_crawled = ""
    
    # If no email/whatsapp found on home page, try to scan contact subpages
    if not contact_email or not contact_whatsapp:
        contact_subpage_url = find_contact_page_url(final_url, soup)
        if contact_subpage_url:
            add_log(f'Buscando contatos na página de contato: {contact_subpage_url}')
            try:
                sub_resp = requests.get(contact_subpage_url, headers=headers, timeout=5)
                sub_resp.encoding = sub_resp.apparent_encoding or 'utf-8'
                sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                sub_text_crawled = sub_soup.get_text()
                full_site_text += "\n" + sub_text_crawled
                
                sub_emails = find_emails_in_text(sub_resp.text)
                sub_whatsapp = find_whatsapp_links(sub_resp.text, sub_soup)
                sub_phones = find_phones_in_text(sub_text_crawled)
                
                if not contact_email and sub_emails:
                    contact_email = sub_emails[0]
                if not contact_whatsapp and sub_whatsapp:
                    contact_whatsapp = sub_whatsapp[0]
                if not contact_phone and sub_phones:
                    contact_phone = sub_phones[0]
            except Exception as e:
                add_log(f'Erro ao ler página de contato {contact_subpage_url}: {e}')

    # Location check
    is_location_valid = check_location_match(full_site_text, state_uf, allowed_cities)
    if not is_location_valid:
        # If the check failed, try to crawl the contact page if we haven't done it yet
        if not sub_text_crawled:
            contact_subpage_url = find_contact_page_url(final_url, soup)
            if contact_subpage_url:
                try:
                    sub_resp = requests.get(contact_subpage_url, headers=headers, timeout=5)
                    sub_resp.encoding = sub_resp.apparent_encoding or 'utf-8'
                    sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                    sub_text_crawled = sub_soup.get_text()
                    full_site_text += "\n" + sub_text_crawled
                    is_location_valid = check_location_match(full_site_text, state_uf, allowed_cities)
                except:
                    pass
                    
    if not is_location_valid and (state_uf or allowed_cities):
        add_log(f"Ignorando {url} pois não corresponde à localização especificada ({state_uf} | Cidades: {allowed_cities}).")
        return None

    notes = []
    if is_wix:
        notes.append("Site hospedado ou desenvolvido na plataforma Wix (geralmente mais lento e com limitações de SEO).")
    if 'Não Responsivo (Sem tag Viewport)' in issues:
        notes.append("O site não possui a tag meta viewport. Isso significa que ele não se adapta a telas de celulares.")
    if outdated_year:
        notes.append(f"Copyright do rodapé indica ano de {outdated_year}, demonstrando abandono do site.")
    if is_subdomain:
        notes.append("O site roda em um subdomínio, o que reduz a credibilidade da marca.")
    if 'Inseguro (HTTP)' in issues:
        notes.append("O site não possui HTTPS configurado, exibindo aviso de 'Não seguro' no navegador.")
    if not is_wix and not is_wp:
        notes.append("Site parece usar código HTML estático antigo, sem frameworks modernos.")
        
    if any('Site Lento' in x for x in issues):
        slow_tag = next((x for x in issues if 'Site Lento' in x), None)
        notes.append(f"O site é lento ({slow_tag.split(' ')[-1] if slow_tag else ''}), o que pode fazer com que potenciais clientes desistam do acesso.")
    if 'Sem Descrição SEO' in issues:
        notes.append("O site não tem uma descrição de busca (Meta Description) configurada, o que prejudica seu ranqueamento no Google.")
    if 'Sem Título H1' in issues:
        notes.append("Falta a tag de cabeçalho principal H1, o que dificulta que os mecanismos de busca entendam o tema da página.")
    if 'Sem Prévia no WhatsApp' in issues:
        notes.append("Falta a imagem de prévia (Open Graph) para compartilhamento em redes sociais como o WhatsApp.")
    if 'Sem Favicon (Ícone)' in issues or 'Favicon Genérico' in issues:
        notes.append("O site não possui um ícone personalizado para a aba do navegador (favicon), o que reduz o profissionalismo da marca.")
    if 'Uso de Frames (Obsoleto)' in issues:
        notes.append("O site usa frames obsoletos para carregar conteúdo, uma tecnologia antiga não suportada por dispositivos móveis modernos.")
    if 'Texto Provisório' in issues:
        notes.append("Detectamos textos provisórios de rascunho (Lorem Ipsum) no conteúdo do site, passando a impressão de abandono ou site inacabado.")
    if 'Formulário Inseguro' in issues:
        notes.append("Os formulários de contato transmitem dados de forma insegura (HTTP simples), o que faz o navegador exibir avisos de segurança ao usuário.")
        
    # Capture screenshot using Playwright
    import time
    screenshot_filename = f"{domain}_{int(time.time())}.png"
    screenshot_path = capture_screenshot(final_url, screenshot_filename)
    
    return {
        'company_name': company_name,
        'website': final_url,
        'segment': segment,
        'region': region,
        'status': 'pending',
        'detected_issues': issues,
        'contact_email': contact_email or '',
        'contact_whatsapp': contact_whatsapp or '',
        'contact_phone': contact_phone or '',
        'notes': '\n'.join(notes),
        'screenshot': screenshot_filename if screenshot_path else ''
    }

def validate_email_dns(email):
    if not email or '@' not in email:
        return False
    domain = email.split('@')[-1].strip()
    try:
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ['8.8.8.8', '1.1.1.1']
        resolver.timeout = 3.0
        resolver.lifetime = 3.0
        answers = resolver.resolve(domain, 'MX')
        if answers:
            return True
    except Exception:
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['8.8.8.8', '1.1.1.1']
            resolver.timeout = 2.0
            resolver.lifetime = 2.0
            answers = resolver.resolve(domain, 'A')
            if answers:
                return True
        except Exception:
            pass
    return False

def find_emails_in_text(text):
    # Standard email regex
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    raw_emails = re.findall(email_pattern, text)
    
    clean_emails = []
    for email in raw_emails:
        email = email.lower().strip()
        # Filter out static resource emails or noise
        if any(email.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.webp', '.svg']):
            continue
        if any(bad in email for bad in ['wix', 'wordpress', 'sentry', 'example', 'test', 'domain', 'email@email']):
            continue
        if email not in clean_emails:
            if validate_email_dns(email):
                clean_emails.append(email)
            else:
                add_log(f"E-mail {email} descartado por falha na validação de DNS (sem registros MX/A).")
            
    return clean_emails

def find_whatsapp_links(html, soup):
    links = []
    # Try finding wa.me or api.whatsapp.com in links
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'wa.me' in href or 'api.whatsapp.com' in href or 'whatsapp.com/send' in href:
            # Clean number from link
            match = re.search(r'(?:phone|send\?phone=)?(\d{10,13})', href)
            if match:
                num = match.group(1)
                # Format to Brazilian whatsapp if needed, or keep it
                links.append(num)
            else:
                links.append(href)
                
    # Also look for whatsapp numbers in page text
    whatsapp_text = re.findall(r'(?:whats|whatsapp|zap|wpp)[:\s-]*\+?55\s?\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}', html, re.IGNORECASE)
    for w in whatsapp_text:
        num = re.sub(r'\D', '', w)
        if len(num) >= 10:
            links.append(num)
            
    return list(set(links))

def find_phones_in_text(text):
    # Regex for Brazilian phone numbers: (XX) XXXX-XXXX or (XX) XXXXX-XXXX
    phone_pattern = r'\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}'
    phones = re.findall(phone_pattern, text)
    clean_phones = []
    for p in phones:
        cleaned = p.strip()
        if len(re.sub(r'\D', '', cleaned)) >= 10:
            clean_phones.append(cleaned)
    return list(set(clean_phones))

def find_contact_page_url(base_url, soup):
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().lower()
        if any(k in text for k in ['contato', 'contact', 'fale conosco', 'fale-conosco', 'localização', 'onde estamos']):
            return urljoin(base_url, href)
    # Check common paths
    for path in ['/contato', '/contato.html', '/contato.php', '/fale-conosco', '/contact']:
        test_url = urljoin(base_url, path)
        try:
            r = requests.head(test_url, timeout=3, allow_redirects=True)
            if r.status_code == 200:
                return test_url
        except:
            pass
    return None

def generate_slug(name):
    import unicodedata
    import re
    nfkd_form = unicodedata.normalize('NFKD', name)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('ASCII')
    slug = re.sub(r'[^a-z0-9]+', '-', only_ascii.lower()).strip('-')
    return slug

def generate_prospect_email(prospect):
    # Load settings
    api_key = database.get_setting('gemini_api_key', '')
    sender_name = database.get_setting('sender_name', 'Matheus Paviani')
    sender_whatsapp = database.get_setting('sender_whatsapp', '(51) 99766-1506')
    sender_pitch = database.get_setting('sender_pitch', 'Criação e modernização de sites...')
    sender_portfolio = database.get_setting('sender_portfolio', 'https://paviani.net/portfolio/')
    email_rules = database.get_setting('email_rules', '')
    
    # If no API key configured, use standard fallback template
    if not api_key:
        return generate_prospect_email_fallback(prospect, sender_name, sender_whatsapp, sender_pitch, sender_portfolio)

    # Load screenshot if exists
    screenshot_file = prospect.get('screenshot', '')
    img = None
    if screenshot_file:
        import os
        screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'screenshots')
        screenshot_path = os.path.join(screenshots_dir, screenshot_file)
        if os.path.exists(screenshot_path):
            try:
                from PIL import Image
                img = Image.open(screenshot_path)
            except Exception as ex:
                add_log(f"Aviso: Não foi possível abrir o screenshot para enviar ao Gemini: {ex}")

    # Call Gemini API
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        issues_list = ", ".join(prospect['detected_issues'])
        
        if prospect.get('surgical_type') == 'no_site':
            prompt = f"""
            Você é um copywriter de vendas experiente e trabalha prospectando clientes de desenvolvimento de sites para {sender_name}.
            Sua tarefa é redigir um e-mail de vendas amigável, direto, informal e altamente personalizado para a empresa "{prospect['company_name']}", além de uma mensagem curta para WhatsApp.
            
            Dados da empresa:
            - Nome: {prospect['company_name']}
            - Website/Rede Social: {prospect['website']}
            - Segmento/Indústria: {prospect['segment']}
            - Região: {prospect['region']}
            - Situação comercial: Esta empresa NÃO possui um site próprio institucional. Ela utiliza apenas redes sociais (como Facebook ou Instagram) ou páginas de listagens para sua presença digital.
            - Notas de análise: {prospect['notes']}
            
            Dados do remetente (você):
            - Nome: {sender_name}
            - WhatsApp: {sender_whatsapp}
            - Portfólio: {sender_portfolio}
            - Serviço oferecido: {sender_pitch}
            
            Regras cruciais para escrever o e-mail (siga exatamente este estilo amigável e pessoal):
            1. Assunto: Escolha uma variação curta (ex: "Ideia para a {prospect['company_name']}", "Sobre a {prospect['company_name']}", "Uma observação sobre a {prospect['company_name']}").
            2. Saudação: Comece com "Olá, tudo bem?" ou "Olá [Nome do contato], tudo bem?".
            3. Elogio Sincero Baseado em Fatos (Primeiro Parágrafo): Apresente-se ("Meu nome é {sender_name}"). Diga que chegou até a empresa pelo Google/Redes Sociais e te chamou atenção algum ponto positivo deles (ex: avaliações excelentes na internet, tradição em {prospect['segment']}, o portfólio bacana exposto ou a qualidade do trabalho). Elogie isso como um diferencial forte da empresa deles.
            4. A Oportunidade Visual (Segundo Parágrafo): Diga: "Foi por isso que reparei numa oportunidade: no perfil de vocês, notei que não possuem um site institucional com domínio próprio da empresa. Depender apenas de redes sociais esconde a autoridade que a {prospect['company_name']} tem."
            5. Pitch Comercial e Estudo Visual (Terceiro Parágrafo): NÃO envie nenhum link pronto para a pessoa olhar. Use exatamente a seguinte ideia e frase:
               "Por isso, desenvolvi um estudo visual mostrando como a empresa poderia se apresentar hoje: site moderno, responsivo e com destaque para seus serviços de {prospect['segment']}. Fiz esse material especificamente para vocês."
            6. Chamada para Ação Simples e Apresentação (Quarto Parágrafo): Use exatamente a seguinte ideia e frase:
               "Se vocês tiverem 10 minutos, posso apresentar essa ideia sem compromisso."
            7. Assinatura simples no final com Nome, WhatsApp e link do Portfólio ({sender_portfolio}).
            8. Regras adicionais informadas pelo usuário: {email_rules}
            
            Regras para a mensagem curta de WhatsApp:
            - Apresente-se e seja amigável. Diga que notou que não possuem site próprio e que preparou uma proposta visual de como ficaria a presença digital de forma profissional. Pergunte se pode apresentar em 5 minutos, sem enviar links.
            
            Retorne estritamente um objeto JSON com três propriedades: "subject" (o assunto do e-mail), "body" (o texto do e-mail) e "whatsapp" (o texto da mensagem curta para WhatsApp). Não adicione nenhuma formatação markdown fora do JSON (como ```json ou ```). Retorne APENAS o JSON puro.
            """
        else:
            prompt = f"""
            Você é um copywriter de vendas experiente e trabalha prospectando clientes de desenvolvimento de sites para {sender_name}.
            Sua tarefa é redigir um e-mail de vendas amigável, direto, informal e altamente personalizado para a empresa "{prospect['company_name']}", além de uma mensagem curta para WhatsApp.
            
            Dados da empresa:
            - Nome: {prospect['company_name']}
            - Website: {prospect['website']}
            - Segmento/Indústria: {prospect['segment']}
            - Região: {prospect['region']}
            - Falhas técnicas encontradas no site: {issues_list}
            - Notas de análise: {prospect['notes']}
            
            Dados do remetente (você):
            - Nome: {sender_name}
            - WhatsApp: {sender_whatsapp}
            - Portfólio: {sender_portfolio}
            - Serviço oferecido: {sender_pitch}
            
            Regras cruciais para escrever o e-mail (siga exatamente este estilo amigável e pessoal):
            1. Assunto: Escolha uma variação curta (ex: "Uma ideia para o site da {prospect['company_name']}", "Sobre o site da {prospect['company_name']}", "Enquanto analisava o site da {prospect['company_name']}, surgiu uma ideia").
            2. Saudação: Comece com "Olá, tudo bem?" ou "Olá [Nome do contato], tudo bem?".
            3. Elogio Sincero Baseado em Fatos (Primeiro Parágrafo): Apresente-se ("Meu nome é {sender_name}"). Diga que chegou até eles pelo Google e te chamou atenção algum ponto positivo (ex: a excelente avaliação no Google Maps com 5.0 estrelas, o portfólio robusto ou a credibilidade dos serviços). Elogie isso como sinal de uma empresa séria e de qualidade.
            4. A Oportunidade Visual (Segundo Parágrafo): Diga: "Ao abrir o site atual, percebi uma oportunidade: a página está com alguns pontos que acabam atrapalhando a primeira impressão [liste as falhas do site traduzidas para termos simples de negócios de forma gentil, ex: fotos que não abrem bem no celular, layout antigo, aviso de não seguro na barra de endereços], o que faz o site passar menos credibilidade do que a {prospect['company_name']} merece."
            5. Pitch Comercial e Estudo Visual (Terceiro Parágrafo): NÃO envie nenhum link pronto (como mockups ou links de comparação) para a pessoa olhar. Use exatamente a seguinte ideia e frase:
               "Por isso, desenvolvi um estudo visual mostrando como a empresa poderia se apresentar hoje: site moderno, responsivo e com destaque para seus serviços de {prospect['segment']}. Fiz esse material especificamente para vocês."
            6. Chamada para Ação Simples e Apresentação (Quarto Parágrafo): Use exatamente a seguinte ideia e frase:
               "Se vocês tiverem 10 minutos, posso apresentar essa ideia sem compromisso."
            7. Assinatura simples no final com Nome, WhatsApp e link do Portfólio ({sender_portfolio}).
            8. Regras adicionais informadas pelo usuário: {email_rules}
            
            Regras para a mensagem curta de WhatsApp:
            - Apresente-se e seja amigável. Diga que analisou o site deles, notou alguns pontos de melhoria no celular/layout e que preparou uma proposta visual com um design mais moderno. Pergunte se pode apresentar em 5 minutos, sem enviar links.
            
            Retorne estritamente um objeto JSON com três propriedades: "subject" (o assunto do e-mail), "body" (o texto do e-mail) e "whatsapp" (o texto da mensagem curta para WhatsApp). Não adicione nenhuma formatação markdown fora do JSON (como ```json ou ```). Retorne APENAS o JSON puro.
            """
        
        if img:
            response = model.generate_content(
                [prompt, img],
                generation_config={"response_mime_type": "application/json"}
            )
        else:
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
        
        data = json.loads(response.text.strip())
        return data.get('subject', ''), data.get('body', ''), data.get('whatsapp', '')
        
    except Exception as e:
        add_log(f"Erro ao gerar e-mail com a API do Gemini: {e}. Usando template padrão.")
        return generate_prospect_email_fallback(prospect, sender_name, sender_whatsapp, sender_pitch, sender_portfolio)

def generate_prospect_email_fallback(prospect, sender_name, sender_whatsapp, sender_pitch, sender_portfolio='https://paviani.net/portfolio/'):
    if prospect.get('surgical_type') == 'no_site':
        subjects = [
            f"Uma sugestão para a {prospect['company_name']}",
            f"Ideia de site para a {prospect['company_name']}",
            f"Sobre a presença da {prospect['company_name']}"
        ]
        subject = random.choice(subjects)
        whatsapp_draft = f"Olá, tudo bem? Meu nome é {sender_name}. Gostei muito do perfil de vocês nas buscas, mas reparei numa oportunidade: vocês ainda não têm um site próprio. Elaborei uma proposta visual rápida de como ficaria a presença digital de vocês no celular. Se tiver 5 minutos, posso te apresentar?"
        
        body = f"""Olá, tudo bem?

Meu nome é {sender_name}. Cheguei até a {prospect['company_name']} e gostei muito de ver a qualidade dos serviços de {prospect['segment']} de vocês — é um diferencial muito forte.

Foi por isso que reparei numa oportunidade: no perfil atual, vocês não possuem um site institucional com domínio próprio. Depender de redes sociais acaba limitando a credibilidade com clientes industriais e grandes parceiros que pesquisam vocês na internet.

Por isso, desenvolvi um estudo visual mostrando como a empresa poderia se apresentar hoje: site moderno, responsivo e com destaque para seus serviços de {prospect['segment']}. Fiz esse material especificamente para vocês.

Se vocês tiverem 10 minutos, posso apresentar essa ideia sem compromisso.

--
{sender_name}
WhatsApp: {sender_whatsapp}
Portfólio: {sender_portfolio}"""
        return subject, body, whatsapp_draft

    subjects = [
        f"Uma ideia para o site da {prospect['company_name']}",
        f"Enquanto analisava o site da {prospect['company_name']}, surgiu uma ideia",
        f"Sobre o site da {prospect['company_name']}"
    ]
    subject = random.choice(subjects)
    
    # Layman translations of flaws
    issues_text_parts = []
    for issue in prospect.get('detected_issues', []):
        if 'Wix' in issue:
            issues_text_parts.append("um erro na formatação por ser feito em uma plataforma que deixa a página pesada (Wix)")
        elif 'Responsivo' in issue:
            issues_text_parts.append("imagens e formatação que não abrem bem pelo celular")
        elif 'Copyright' in issue:
            match = re.search(r'\d{4}', issue)
            yr = match.group() if match else "anos atrás"
            issues_text_parts.append(f"um design desatualizado com o copyright parado em {yr}")
        elif 'Subdomínio' in issue:
            issues_text_parts.append("o uso de um endereço provisório gratuito em vez de um domínio próprio")
        elif 'Inseguro' in issue:
            issues_text_parts.append("um aviso de 'Não Seguro' na barra do navegador")
            
    if issues_text_parts:
        flaws_desc = " e ".join(issues_text_parts[:2])
        opportunity_desc = f"a página está com alguns pontos que atrapalham a primeira impressão ({flaws_desc}), o que faz o site passar menos credibilidade do que vocês merecem"
    else:
        opportunity_desc = "o site tem um visual mais tradicional, que poderia ser modernizado para acompanhar os padrões atuais e destacar a qualidade dos seus serviços"
        
    whatsapp_draft = f"Olá, tudo bem? Meu nome é {sender_name}. Dei uma olhada no site da {prospect['company_name']} e vi que ele tem um bom posicionamento, mas reparei numa oportunidade de melhoria. Montei uma proposta visual com um design bem mais moderno e adaptado para celulares. Posso te apresentar rápido sem compromisso?"
    
    body = f"""Olá, tudo bem?

Meu nome é {sender_name}. Cheguei até a {prospect['company_name']} pelo Google e me chamou a atenção a qualidade e a seriedade do trabalho de vocês em {prospect['segment']} — é um diferencial muito forte.

Ao abrir o site, percebi uma oportunidade: {opportunity_desc}.

Por isso, desenvolvi um estudo visual mostrando como a empresa poderia se apresentar hoje: site moderno, responsivo e com destaque para seus serviços de {prospect['segment']}. Fiz esse material especificamente para vocês.

Se vocês tiverem 10 minutos, posso apresentar essa ideia sem compromisso.

--
{sender_name}
WhatsApp: {sender_whatsapp}
Portfólio: {sender_portfolio}"""

    return subject, body, whatsapp_draft

def get_state_full_name(state_uf):
    if not state_uf:
        return ""
    state_uf = state_uf.upper().strip()
    names = STATE_NAMES.get(state_uf, [])
    return names[0] if names else state_uf

def run_prospecting_job(segment, region, max_results, state_uf=None, city_name=None, radius_km=0, is_autopilot=0, source_mode="organic"):
    # Resolve geographic location queries
    location_query = region
    db_region = region
    allowed_cities = []
    
    try:
        radius_km = int(radius_km)
    except:
        radius_km = 0
        
    state_full = get_state_full_name(state_uf) if state_uf else ""
    
    if state_uf:
        state_uf = state_uf.upper().strip()
        if city_name and city_name != "Estado Inteiro" and city_name.strip() != "":
            city_name = city_name.strip()
            allowed_cities.append(city_name)
            # We have a specific city
            if radius_km > 0:
                # Geo-radius search
                load_municipios_database()
                # Find target city coordinates
                target = None
                for m in MUNICIPIOS_DB:
                    if m['uf'] == state_uf and m['nome'].lower() == city_name.lower():
                        target = m
                        break
                
                if target:
                    lat_t, lon_t = target['lat'], target['lon']
                    # Calculate distances
                    candidates = []
                    for m in MUNICIPIOS_DB:
                        if m['uf'] == state_uf: # focus on same state for simplicity and safety
                            dist = haversine_distance(lat_t, lon_t, m['lat'], m['lon'])
                            if dist <= radius_km:
                                candidates.append((dist, m['nome']))
                    
                    # Sort by distance
                    candidates.sort()
                    # Get top 5 cities total (target + 4 closest neighbors)
                    closest_cities = [c[1] for c in candidates[:5]]
                    allowed_cities = closest_cities
                    
                    # Build OR query
                    or_terms = " OR ".join([f'"{city}"' for city in closest_cities])
                    location_query = f'({or_terms}) "{state_full}"'
                    db_region = f'{city_name} - {state_uf} (+{radius_km}km)'
                    add_log(f"Pesquisa por raio de {radius_km}km em {city_name}-{state_uf} expandida para: {or_terms}")
                else:
                    # Target city not found in database, fallback to single city
                    location_query = f'"{city_name}" "{state_full}"'
                    db_region = f'{city_name} - {state_uf}'
                    add_log(f"Aviso: Cidade {city_name}-{state_uf} não encontrada na base de dados. Buscando sem raio.")
            else:
                # No radius
                location_query = f'"{city_name}" "{state_full}"'
                db_region = f'{city_name} - {state_uf}'
        else:
            # Whole state
            location_query = f'"{state_full}"'
            db_region = f'{state_uf}'
            
    add_log(f"Iniciando Job de Prospecção para: Segmento='{segment}', Região='{db_region}', Qtd={max_results} | Provedor={source_mode}")
    add_log(f"Termo de localização para busca: {location_query}")
    
    if source_mode == "kipflow":
        companies = search_companies_kipflow(segment, city_name, state_uf, limit=max_results)
    else:
        companies = search_companies(segment, db_region, max_results, location_query=location_query)
    
    new_prospects_count = 0
    for idx, c in enumerate(companies):
        add_log(f"Processando {idx+1}/{len(companies)}: {c['url']}")
        
        # Analyze website
        p_data = analyze_website(c['url'], segment, db_region, state_uf=state_uf, allowed_cities=allowed_cities)
        if not p_data:
            add_log(f"Ignorando site {c['url']} devido a filtros ou falha de acesso.")
            continue
            
        if 'cnpj' in c:
            p_data['cnpj'] = c['cnpj']
        
        # Double check after redirects to avoid duplicates
        resolved_website = p_data.get('website', '')
        resolved_domain = extract_base_domain(resolved_website)
        existing_id = database.check_domain_exists(resolved_domain)
        if existing_id:
            add_log(f"Ignorando {resolved_website} (Já cadastrado no banco de dados com ID {existing_id}).")
            continue
            
        # Generate custom drafts
        subject, body, whatsapp_draft = generate_prospect_email(p_data)
        p_data['email_subject'] = subject
        p_data['email_body'] = body
        p_data['whatsapp_draft'] = whatsapp_draft
        p_data['is_autopilot'] = is_autopilot
        
        # Save to SQLite database
        p_id = database.add_prospect(p_data)
        new_prospects_count += 1
        add_log(f"Salvo prospect ID {p_id}: {p_data['company_name']} | Website: {p_data['website']}")
        
        if new_prospects_count >= max_results:
            add_log(f"Atingida a quantidade limite de {max_results} prospects válidos e salvos.")
            break
            
    add_log(f"Job concluído com sucesso! {new_prospects_count} prospects adicionados ou atualizados.")
    
    # Log job completion to search_debug.jsonl
    try:
        log_entry = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
            "type": "job_prospecting",
            "params": {
                "segment": segment,
                "region": region,
                "max_results": max_results,
                "state_uf": state_uf,
                "city_name": city_name,
                "radius_km": radius_km
            },
            "results_saved": new_prospects_count,
            "status": "completed"
        }
        with open("search_debug.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write job log: {e}")
        
    return new_prospects_count

def clean_social_company_name(title, url):
    t = title
    if 'instagram.com' in url.lower():
        if '(' in t:
            t = t.split('(')[0]
        if '•' in t:
            t = t.split('•')[0]
    elif 'facebook.com' in url.lower():
        if '|' in t:
            t = t.split('|')[0]
        if '-' in t:
            t = t.split('-')[0]
    elif 'cnpj.biz' in url.lower():
        if '-' in t:
            t = t.split('-')[0]
    elif 'solutudo.com.br' in url.lower():
        if ' em ' in t.lower():
            # e.g. "Metalurgica em Caxias do Sul" -> split by " em " case-insensitive
            parts = re.split(r'\s+em\s+', t, flags=re.IGNORECASE)
            t = parts[0]
        if '-' in t:
            t = t.split('-')[0]
    elif 'guiamais.com.br' in url.lower():
        if '|' in t:
            t = t.split('|')[0]
    elif 'apontador.com.br' in url.lower():
        if '-' in t:
            t = t.split('-')[0]
    elif 'google.com' in url.lower() and '/maps/place/' in url.lower():
        import urllib.parse
        try:
            place_part = url.split('/maps/place/')[1].split('/')[0]
            place_part = urllib.parse.unquote(place_part).replace('+', ' ')
            if '-' in place_part:
                t = place_part.split('-')[0]
            else:
                t = place_part
        except:
            t = title
            
    t = t.strip()
    t = re.sub(r'[^\w\s\-\.\,\&\@]', '', t)
    return t.strip()

def extract_contacts_from_text(text):
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b'
    emails = re.findall(email_pattern, text)
    
    phone_pattern = r'(?:\+?55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\s?\d{4}[-\s]?\d{4}|\d{4}[-\s]?\d{4})\b'
    phones = re.findall(phone_pattern, text)
    
    clean_phones = []
    for p in phones:
        digits = ''.join(c for c in p if c.isdigit())
        if len(digits) in [8, 9, 10, 11, 12, 13]:
            if len(digits) == 11 and digits.startswith('55'):
                digits = digits[2:]
            if len(digits) == 11:
                formatted = f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
            elif len(digits) == 10:
                formatted = f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"
            else:
                formatted = p.strip()
            clean_phones.append(formatted)
            
    return list(set(emails)), list(set(clean_phones))

def has_website_presence(title, snippet, emails):
    text_lower = (title + " " + snippet).lower()
    
    # 1. Check if any extracted email is using a custom domain
    public_providers = {
        'gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'yahoo.com.br', 
        'bol.com.br', 'uol.com.br', 'terra.com.br', 'icloud.com', 'live.com', 
        'aol.com', 'zoho.com', 'outlook.com.br', 'proton.me', 'protonmail.com'
    }
    
    for email in emails:
        parts = email.split('@')
        if len(parts) == 2:
            email_domain = parts[1].strip().lower()
            if email_domain not in public_providers:
                # Custom email domain means they own a domain/website!
                return True
                
    # 2. Check for website links or domain names in title and snippet
    domain_pattern = r'\b(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.[a-zA-Z0-9.-]{2,6})\b'
    domains_found = re.findall(domain_pattern, text_lower)
    
    ignored_domains = {
        'facebook.com', 'instagram.com', 'fb.com', 'youtube.com', 'linkedin.com',
        'linktr.ee', 'wa.me', 'whatsapp.com', 'twitter.com', 'x.com', 'google.com',
        'g.page', 'pinterest.com', 'tiktok.com'
    }
    ignored_domains.update(public_providers)
    
    for d in domains_found:
        d_clean = d.strip().lower()
        if f"@{d_clean}" in text_lower:
            continue
            
        base = database.get_registered_domain(d_clean)
        if base and base not in ignored_domains:
            if not any(d_clean.endswith(ext) for ext in ['.jpg', '.png', '.pdf', '.gif', '.zip']):
                return True
                
    return False

def search_contacts_for_company(company_name, region):
    query = f'"{company_name}" "{region}"'
    emails = []
    phones = []
    try:
        results = ddg_text_search(query, max_results=5)
        for r in results:
                text = r.get('title', '') + " " + r.get('body', '')
                em, ph = extract_contacts_from_text(text)
                emails.extend(em)
                phones.extend(ph)
    except Exception as e:
        add_log(f"Aviso: Falha na busca direcionada de contatos para '{company_name}': {e}")
        
    return list(set(emails)), list(set(phones))

def search_social_profiles(segment, region, max_results=10, maps_only=False):
    # Clean any hyphens or descriptions from the location string to avoid search engine negative operator (-) issues
    loc = region.replace(' - ', ' ').replace(' -', ' ').replace('- ', ' ')
    if '(+' in loc:
        loc = re.sub(r'\(\+\d+km\)', '', loc)
    loc = loc.strip()
    
    results = []
    seen_urls = set()
    
    if maps_only:
        queries = [
            f'site:google.com.br/maps/place {segment} {loc}',
            f'site:google.com/maps/place {segment} {loc}',
            f'site:solutudo.com.br "{segment}" {loc}',
            f'site:guiamais.com.br "{segment}" {loc}',
            f'site:cnpj.biz "{segment}" {loc}',
            f'site:apontador.com.br "{segment}" {loc}'
        ]
        add_log(f"Iniciando busca cirúrgica do Google Maps e Diretórios de Negócios Locais para '{segment}' em '{loc}'...")
    else:
        # 1. Social network queries
        queries = [
            f'site:facebook.com "{segment}" {loc} "gmail.com" OR "hotmail.com" OR "contato" OR "whatsapp"',
            f'site:instagram.com "{segment}" {loc} "gmail.com" OR "hotmail.com" OR "contato" OR "whatsapp"',
            f'site:facebook.com "{segment}" {loc}',
            f'site:instagram.com "{segment}" {loc}'
        ]
        
        # 2. Directory portal queries
        directories = ['cnpj.biz', 'solutudo.com.br', 'guiamais.com.br', 'apontador.com.br']
        for d in directories:
            queries.append(f'site:{d} "{segment}" {loc}')
            
        # 3. Google Maps place queries (unquoted to maximize yield)
        queries.append(f'site:google.com.br/maps/place {segment} {loc}')
        queries.append(f'site:google.com/maps/place {segment} {loc}')
        
        add_log(f"Iniciando busca cirúrgica de redes sociais, diretórios e mapas para '{segment}' em '{loc}'...")
    
    zero_results_count = 0
    for idx, q in enumerate(queries):
        if len(results) >= max_results * 3:
            break
            
        if idx > 0:
            time.sleep(1.5)
            
        add_log(f"Buscando no DuckDuckGo: {q}")
        try:
            ddg_list = ddg_text_search(q, max_results=20)
            if not ddg_list:
                zero_results_count += 1
                
            for r in ddg_list:
                url = r.get('href', '')
                if not url or url in seen_urls:
                    continue
                        
                parsed = urlparse(url)
                path = parsed.path.strip('/')
                path_parts = [p for p in path.split('/') if p]
                
                is_valid = False
                is_directory = False
                
                if 'facebook.com' in parsed.netloc:
                    if len(path_parts) == 1 and path_parts[0] not in ['sharer', 'permalink', 'posts', 'groups', 'events', 'photos', 'videos']:
                        is_valid = True
                    elif len(path_parts) == 2 and path_parts[1] == 'about':
                        is_valid = True
                elif 'instagram.com' in parsed.netloc:
                    if len(path_parts) == 1 and path_parts[0] not in ['p', 'explore', 'reels', 'stories', 'direct']:
                        is_valid = True
                elif any(d in parsed.netloc for d in ['cnpj.biz', 'solutudo.com.br', 'guiamais.com.br', 'apontador.com.br']):
                    if len(path_parts) >= 1:
                        is_valid = True
                        is_directory = True
                elif 'google.com' in parsed.netloc and '/maps/place/' in url:
                    if len(path_parts) >= 1:
                        is_valid = True
                        is_directory = True
                        
                if not is_valid:
                    continue
                    
                seen_urls.add(url)
                results.append({
                    'url': url,
                    'title': r.get('title', ''),
                    'snippet': r.get('body', ''),
                    'is_directory': is_directory
                })
        except Exception as e:
            add_log(f"Erro na busca no DDG para '{q}': {e}")
            zero_results_count += 1
            
    if zero_results_count == len(queries) and not results:
        add_log("Aviso: O DuckDuckGo não retornou nenhum resultado. Isso pode indicar um bloqueio temporário de IP (Rate Limit). Dica: aguarde 3-5 minutos ou reconecte sua VPN/rede para mudar seu endereço IP.")
        
    return results

def run_surgical_job(segment, region, max_results, state_uf=None, city_name=None, radius_km=0, surgical_type='both', is_autopilot=0):
    # Resolve geographic location queries
    location_query = region
    db_region = region
    allowed_cities = []
    
    add_log(f"DEBUG INPUT: segment='{segment}', region='{region}', max_results={max_results}, state_uf={repr(state_uf)}, city_name={repr(city_name)}, radius_km={radius_km}, surgical_type='{surgical_type}'")
    
    try:
        radius_km = int(radius_km)
    except:
        radius_km = 0
        
    state_full = get_state_full_name(state_uf) if state_uf else ""
    
    if state_uf:
        state_uf = state_uf.upper().strip()
        if city_name and city_name != "Estado Inteiro" and city_name.strip() != "":
            city_name = city_name.strip()
            allowed_cities.append(city_name)
            if radius_km > 0:
                load_municipios_database()
                target = None
                for m in MUNICIPIOS_DB:
                    if m['uf'] == state_uf and m['nome'].lower() == city_name.lower():
                        target = m
                        break
                
                if target:
                    lat_t, lon_t = target['lat'], target['lon']
                    candidates = []
                    for m in MUNICIPIOS_DB:
                        if m['uf'] == state_uf:
                            dist = haversine_distance(lat_t, lon_t, m['lat'], m['lon'])
                            if dist <= radius_km:
                                candidates.append((dist, m['nome']))
                    
                    candidates.sort()
                    closest_cities = [c[1] for c in candidates[:5]]
                    allowed_cities = closest_cities
                    
                    or_terms = " OR ".join([f'"{city}"' for city in closest_cities])
                    location_query = f'({or_terms}) "{state_full}"'
                    db_region = f'{city_name} - {state_uf} (+{radius_km}km)'
                    add_log(f"Pesquisa cirúrgica por raio de {radius_km}km em {city_name}-{state_uf} expandida para: {or_terms}")
                else:
                    location_query = f'"{city_name}" "{state_full}"'
                    db_region = f'{city_name} - {state_uf}'
            else:
                location_query = f'"{city_name}" "{state_full}"'
                db_region = f'{city_name} - {state_uf}'
        else:
            location_query = f'"{state_full}"'
            db_region = f'{state_uf}'
            
    add_log(f"DEBUG RESOLVED: location_query={repr(location_query)}, db_region={repr(db_region)}")
    add_log(f"Iniciando Job de Prospecção CIRÚRGICA ({surgical_type}) para: Segmento='{segment}', Região='{db_region}', Qtd={max_results}")
    
    new_prospects_count = 0
    
    # 1. Process "No Site" Targets (Social Profiles)
    if surgical_type in ['no_site', 'both', 'maps_only']:
        is_maps_only = (surgical_type == 'maps_only')
        if is_maps_only:
            add_log("Buscando empresas sem site próprio EXCLUSIVAMENTE no Google Maps...")
        else:
            add_log("Buscando empresas sem site próprio nas redes sociais, diretórios e mapas...")
        social_profiles = search_social_profiles(segment, location_query, max_results, maps_only=is_maps_only)
        
        for idx, sp in enumerate(social_profiles):
            if new_prospects_count >= max_results:
                break
                
            url = sp['url']
            title = sp['title']
            snippet = sp['snippet']
            
            parsed = urlparse(url)
            username = parsed.path.strip('/')
            if database.check_domain_exists(parsed.netloc, full_url=url):
                continue
                
            company_name = clean_social_company_name(title, url)
            
            if is_rejected_pattern(company_name, parsed.netloc):
                continue
                
            emails, phones = extract_contacts_from_text(title + " " + snippet)
            
            # If no contacts found, try a quick targeted search for this specific company
            if not emails and not phones:
                add_log(f"Contatos não encontrados no snippet de '{company_name}'. Fazendo busca direcionada de contatos...")
                emails, phones = search_contacts_for_company(company_name, db_region)
            
            # Skip if they already have a website presence (custom email domain or direct links in snippet)
            if has_website_presence(title, snippet, emails):
                add_log(f"Ignorando perfil social {url} pois indica possuir site próprio.")
                continue
            
            email_contact = emails[0] if emails else ""
            phone_contact = phones[0] if phones else ""
            whatsapp_contact = ""
            
            if phone_contact:
                whatsapp_contact = phone_contact
                
            if not email_contact and not whatsapp_contact:
                add_log(f"Ignorando perfil social {url} pois não possui contatos de e-mail ou telefone visíveis.")
                continue
                
            is_dir = sp.get('is_directory', False)
            is_map = ('google.com' in parsed.netloc and '/maps/' in url) or (surgical_type == 'maps_only')
            
            if is_map:
                issues_list = ['Não possui site próprio (Localizado no Google Maps/Cadastro Local)']
                notes_str = f"Presença digital identificada como local registrado no Google Maps / Cadastro Local ({parsed.netloc.replace('www.', '')}). Nenhuma página de domínio próprio encontrada nos mecanismos de busca comerciais."
                log_type = "Sem Site - Google Maps"
            elif is_dir:
                issues_list = ['Não possui site próprio (Listado apenas em diretório comercial)']
                notes_str = f"Presença digital identificada apenas no diretório {parsed.netloc.replace('www.', '')}. Nenhuma página de domínio próprio encontrada nos mecanismos de busca comerciais."
                log_type = "Sem Site - Diretório"
            else:
                issues_list = ['Não possui site próprio (Apenas rede social)']
                notes_str = f"Presença digital identificada apenas no {parsed.netloc.replace('www.', '')}. Nenhuma página de domínio próprio encontrada nos mecanismos de busca comerciais."
                log_type = "Sem Site - Rede Social"
            
            p_data = {
                'company_name': company_name,
                'website': url,
                'segment': segment,
                'region': db_region,
                'status': 'pending',
                'detected_issues': issues_list,
                'contact_email': email_contact,
                'contact_whatsapp': whatsapp_contact,
                'contact_phone': phone_contact,
                'notes': notes_str,
                'screenshot': '',
                'is_surgical': 1,
                'surgical_type': 'maps_only' if is_map else 'no_site',
                'is_autopilot': is_autopilot
            }
            
            subject, body, whatsapp_draft = generate_prospect_email(p_data)
            p_data['email_subject'] = subject
            p_data['email_body'] = body
            p_data['whatsapp_draft'] = whatsapp_draft
            
            p_id = database.add_prospect(p_data)
            new_prospects_count += 1
            add_log(f"Salvo prospect cirúrgico ({log_type}) ID {p_id}: {company_name} | URL: {url}")
            
    # 2. Process "Critical Site" Targets
    if surgical_type in ['critical_site', 'both'] and new_prospects_count < max_results:
        add_log("Buscando empresas com sites que possuem falhas críticas...")
        companies = search_companies(segment, db_region, max_results * 2, location_query=location_query)
        
        for idx, c in enumerate(companies):
            if new_prospects_count >= max_results:
                break
                
            add_log(f"Analisando site {c['url']} para verificar criticidade...")
            p_data = analyze_website(c['url'], segment, db_region, state_uf=state_uf, allowed_cities=allowed_cities)
            if not p_data:
                continue
                
            resolved_website = p_data.get('website', '')
            resolved_domain = extract_base_domain(resolved_website)
            existing_id = database.check_domain_exists(resolved_domain)
            if existing_id:
                continue
                
            issues = p_data.get('detected_issues', [])
            has_wix = any('Wix' in iss for iss in issues)
            has_http = any('não seguro' in iss.lower() or 'inseguro' in iss.lower() or 'http' in iss.lower() for iss in issues)
            has_copyright = any('copyright' in iss.lower() or 'desatualizado' in iss.lower() for iss in issues)
            
            is_critical = len(issues) >= 3 or has_wix or has_http or has_copyright
            
            if not is_critical:
                add_log(f"Ignorando {resolved_website} pois o site possui poucos problemas ({len(issues)} falhas).")
                continue
                
            email_contact = p_data.get('contact_email', '')
            whatsapp_contact = p_data.get('contact_whatsapp', '')
            phone_contact = p_data.get('contact_phone', '')
            
            if not email_contact and not whatsapp_contact and not phone_contact:
                add_log(f"Ignorando site {resolved_website} pois não possui contatos de e-mail ou telefone detectados.")
                continue
                
            p_data['is_surgical'] = 1
            p_data['surgical_type'] = 'critical_site'
            p_data['is_autopilot'] = is_autopilot
            
            subject, body, whatsapp_draft = generate_prospect_email(p_data)
            p_data['email_subject'] = subject
            p_data['email_body'] = body
            p_data['whatsapp_draft'] = whatsapp_draft
            
            p_id = database.add_prospect(p_data)
            new_prospects_count += 1
            add_log(f"Salvo prospect cirúrgico (Site Crítico) ID {p_id}: {p_data['company_name']} | Website: {resolved_website} ({len(issues)} falhas)")
            
    add_log(f"Job cirúrgico concluído com sucesso! {new_prospects_count} prospects adicionados.")
    
    # Log job completion to search_debug.jsonl
    try:
        log_entry = {
            "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S'),
            "type": "job_surgical",
            "params": {
                "segment": segment,
                "region": region,
                "max_results": max_results,
                "state_uf": state_uf,
                "city_name": city_name,
                "radius_km": radius_km,
                "surgical_type": surgical_type
            },
            "results_saved": new_prospects_count,
            "status": "completed"
        }
        with open("search_debug.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to write job log: {e}")
        
    return new_prospects_count

def import_and_verify_leads(items, auto_approve=False, progress_callback=None):
    total = len(items)
    processed = 0
    
    for idx, item in enumerate(items):
        item = item.strip()
        if not item:
            continue
            
        if progress_callback:
            progress_callback(idx, total, f"Processando lead {idx+1}/{total}: {item}")
            
        add_log(f"[Importer] Processando ({idx+1}/{total}): {item}")
        
        # 1. Check if it's a website URL or company name
        is_url = False
        url = item
        if ('://' in item) or ('.' in item and ' ' not in item):
            is_url = True
            if not item.startswith('http://') and not item.startswith('https://'):
                url = 'https://' + item
                
        if is_url:
            # Process website
            try:
                domain = extract_base_domain(url)
                existing_id = database.check_domain_exists(domain)
                if existing_id:
                    add_log(f"[Importer] Ignorando site {url} (Já cadastrado no banco de dados com ID {existing_id}).")
                    continue
                    
                add_log(f"[Importer] Analisando site: {url}")
                p_data = analyze_website(url, segment="Importação Direta", region="Importado", state_uf="Importado", allowed_cities=[])
                if not p_data:
                    add_log(f"[Importer] Falha ao analisar site {url}. Ignorando.")
                    continue
                    
                # Force status
                p_data['status'] = 'approved' if auto_approve else 'pending'
                
                # Generate drafts
                subject, body, whatsapp_draft = generate_prospect_email(p_data)
                p_data['email_subject'] = subject
                p_data['email_body'] = body
                p_data['whatsapp_draft'] = whatsapp_draft
                
                # Save
                p_id = database.add_prospect(p_data)
                add_log(f"[Importer] ✅ Salvo prospect ID {p_id}: {p_data['company_name']} | Website: {p_data['website']}")
            except Exception as e:
                add_log(f"[Importer] Erro ao processar site {url}: {e}")
        else:
            # Process company name
            try:
                add_log(f"[Importer] Buscando informações sobre a empresa '{item}'...")
                search_results = ddg_text_search(f'"{item}"', max_results=3)
                if not search_results:
                    search_results = ddg_text_search(item, max_results=3)
                    
                if not search_results:
                    add_log(f"[Importer] Nenhuma informação encontrada para '{item}'. Ignorando.")
                    continue
                    
                found = False
                for r in search_results:
                    found_url = r.get('href')
                    if not found_url:
                        continue
                        
                    parsed = urlparse(found_url)
                    if any(d in parsed.netloc for d in ['google.com', 'duckduckgo.com', 'bing.com', 'yahoo.com']):
                        continue
                        
                    domain = extract_base_domain(found_url)
                    existing_id = database.check_domain_exists(domain)
                    if existing_id:
                        add_log(f"[Importer] Empresa '{item}' aponta para {found_url} (já cadastrada com ID {existing_id}).")
                        found = True
                        break
                        
                    add_log(f"[Importer] Encontrado link provável para '{item}': {found_url}")
                    
                    p_data = analyze_website(found_url, segment="Importação Direta", region="Importado", state_uf="Importado", allowed_cities=[])
                    if not p_data:
                        emails, phones = extract_contacts_from_text(r.get('body', ''))
                        if emails or phones:
                            p_data = {
                                'company_name': item,
                                'website': found_url,
                                'segment': "Importação Direta",
                                'region': "Importado",
                                'status': 'approved' if auto_approve else 'pending',
                                'detected_issues': ["Site inacessível (contatos extraídos da busca)"],
                                'contact_email': emails[0] if emails else '',
                                'contact_whatsapp': phones[0] if phones else '',
                                'contact_phone': phones[0] if phones else '',
                                'notes': f"Contatos extraídos do snippet do DuckDuckGo: {r.get('body', '')}"
                            }
                        else:
                            continue
                            
                    p_data['status'] = 'approved' if auto_approve else 'pending'
                    subject, body, whatsapp_draft = generate_prospect_email(p_data)
                    p_data['email_subject'] = subject
                    p_data['email_body'] = body
                    p_data['whatsapp_draft'] = whatsapp_draft
                    
                    p_id = database.add_prospect(p_data)
                    add_log(f"[Importer] ✅ Salvo prospect ID {p_id} para '{item}': {p_data['company_name']} | Website: {p_data['website']}")
                    found = True
                    break
                    
                if not found:
                    add_log(f"[Importer] Não foi possível encontrar contatos ou site válido para '{item}'.")
            except Exception as e:
                add_log(f"[Importer] Erro ao processar empresa '{item}': {e}")
