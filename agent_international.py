import os
import re
import json
import time
import csv
import io
import urllib.request
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
import google.generativeai as genai
import database

GOSOM_TERMINAL_STATUSES = {"ok", "failed"}

# Log handler
logs = []
def add_log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    logs.append(log_line)
    if len(logs) > 50:
        logs.pop(0)

def get_logs():
    return list(logs)

def clear_logs():
    logs.clear()

# Countries Config
COUNTRIES = {
    "US": {
        "name": "Estados Unidos",
        "ddi": "1",
        "cities": ["Orlando", "Miami", "Boston", "Framingham", "Newark", "Harrison", "Los Angeles", "San Diego", "San Francisco", "Everett", "Worcester"],
        "default_query_loc": '("Orlando" OR "Boston" OR "Miami" OR "EUA" OR "USA")'
    },
    "PT": {
        "name": "Portugal",
        "ddi": "351",
        "cities": ["Lisboa", "Porto", "Braga", "Coimbra", "Algarve"],
        "default_query_loc": '("Lisboa" OR "Porto" OR "Braga" OR "Portugal")'
    },
    "GB": {
        "name": "Reino Unido",
        "ddi": "44",
        "cities": ["Londres", "Manchester", "Birmingham", "London"],
        "default_query_loc": '("London" OR "London" OR "UK" OR "Reino Unido")'
    },
    "IE": {
        "name": "Irlanda",
        "ddi": "353",
        "cities": ["Dublin", "Cork", "Galway"],
        "default_query_loc": '("Dublin" OR "Ireland" OR "Irlanda")'
    },
    "CA": {
        "name": "Canadá",
        "ddi": "1",
        "cities": ["Toronto", "Vancouver", "Montreal", "Calgary"],
        "default_query_loc": '("Toronto" OR "Vancouver" OR "Canada" OR "Canadá")'
    }
}

# Segment queries mapping
SEGMENT_TEMPLATES = {
    "cleaning": {
        "title": "Serviços de Limpeza (Cleaners)",
        "terms_list": ["cleaning service", "house cleaning", "maid service", "cleaners", "housekeeping"]
    },
    "handyman": {
        "title": "Reforma e Manutenção (Handyman)",
        "terms_list": ["handyman", "home renovation", "house painting", "painter", "remodeling"]
    }
}

def clean_phone_international(phone_str, ddi):
    """Normalize phone numbers to international format."""
    if not phone_str:
        return ''
    # Remove non-digits
    digits = re.sub(r'\D', '', phone_str)
    if not digits:
        return ''
        
    # Check if number already starts with the DDI
    if digits.startswith(ddi):
        return "+" + digits
        
    # If number starts with 0 (often in Europe/UK), strip it and add DDI
    if digits.startswith('0') and len(digits) > 8:
        digits = digits[1:]
        
    # If digits match a Brazilian number format (started with +55 or has 11 digits starting with 9 etc.)
    if digits.startswith('55'):
        return "+" + digits
        
    # Default: prepend the country DDI
    return "+" + ddi + digits

def extract_contacts_from_html(html, text, url, ddi):
    """Extract emails and phone numbers from HTML/Text."""
    emails = []
    phones = []
    
    # 1. Emails
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    found_emails = email_pattern.findall(text)
    for email in found_emails:
        email = email.lower().strip()
        # Avoid common image or styling extensions matching emails
        if not email.endswith(('.png', '.jpg', '.gif', '.webp', '.css', '.js', 'domain.com')):
            if email not in emails:
                emails.append(email)
                
    # 2. Phones
    # Look for patterns matching: +1 123-456-7890, +351 912 345 678, (123) 456-7890, +55 (51) 99999-9999, etc.
    phone_pattern = re.compile(r'(?:\+?[\d\-\(\)\s]{8,18})')
    candidates = phone_pattern.findall(text)
    
    for cand in candidates:
        cand_clean = re.sub(r'[\s\-\(\)\+]', '', cand)
        # Avoid zip codes, dates, coordinates matching
        if len(cand_clean) >= 9 and len(cand_clean) <= 15:
            # Simple check if there are duplicate or sequential digits
            if cand_clean.isdigit():
                formatted = clean_phone_international(cand_clean, ddi)
                if formatted and formatted not in phones:
                    phones.append(formatted)
                    
    # Fallback to matching WhatsApp/phone links in HTML
    soup = BeautifulSoup(html, 'html.parser')
    for link in soup.find_all('a', href=True):
        href = link['href']
        if 'wa.me/' in href or 'api.whatsapp.com/send' in href:
            match = re.search(r'phone=([^&]+)', href)
            if match:
                phone_num = re.sub(r'\D', '', match.group(1))
                if phone_num:
                    formatted = clean_phone_international(phone_num, ddi)
                    if formatted and formatted not in phones:
                        phones.append(formatted)
        elif href.startswith('tel:'):
            phone_num = re.sub(r'\D', '', href[4:])
            if phone_num:
                formatted = clean_phone_international(phone_num, ddi)
                if formatted and formatted not in phones:
                    phones.append(formatted)
                    
    primary_email = emails[0] if emails else ''
    primary_phone = phones[0] if phones else ''
    
    return primary_email, primary_phone, emails, phones

def query_gemini_international_copy(prospect, country_name):
    """Generate pitch emails and WhatsApp copies for expats using Gemini."""
    api_key = database.get_setting('gemini_api_key', '')
    sender_name = database.get_setting('sender_name', 'Matheus Paviani')
    sender_whatsapp = database.get_setting('sender_whatsapp', '(51) 99766-1506')
    sender_pitch = database.get_setting('sender_pitch', 'Criação e modernização de sites de alta conversão')
    
    rating_val = prospect.get('rating', 0.0)
    reviews_val = prospect.get('reviews_count', 0)
    score_val = prospect.get('opportunity_score', 0)
    
    reputation_text_email = ""
    reputation_text_wa = ""
    if reviews_val > 0:
        reputation_text_email = f"Vi que vocês têm uma reputação incrível de {rating_val} estrelas com {reviews_val} avaliações no Google! Isso mostra que o serviço de vocês é espetacular. "
        reputation_text_wa = f" Vi que vocês têm {reviews_val} reviews no Google com nota {rating_val} - parabéns pelo trabalho!"
        
    # Build fallback before calling Gemini, so API/JSON failures still produce
    # usable copy instead of raising UnboundLocalError.
    email_body = f"""Olá, tudo bem?

Me chamo {sender_name} e sou desenvolvedor de sites para profissionais de destaque. Encontrei o seu perfil de {prospect['segment']} em {prospect['region']} e adorei os serviços de vocês!

{reputation_text_email}Muitos profissionais brasileiros em {country_name} perdem clientes nativos do país porque não possuem um site institucional estruturado em inglês ou bilíngue. Depender apenas de redes sociais ou recomendações limita a sua margem de cobrança.

Desenhei um projeto demonstrativo rápido de como seria um site moderno de alta conversão para a sua marca, trazendo um visual profissional para você atrair americanos/europeus locais e cobrar preços muito mais competitivos.

Poderíamos marcar uma conversa de 10 minutos para eu te apresentar esse estudo?

Um abraço,
{sender_name}
WhatsApp: {sender_whatsapp}"""

    whatsapp_body = f"Olá, tudo bem? Vi seu trabalho de {prospect['segment']} em {prospect['region']}!{reputation_text_wa} Sou o {sender_name}. Trabalho profissionalizando sites de prestadores brasileiros aí em {country_name} para ajudá-los a captar clientes nativos (como americanos/locais) e cobrar preços de 2 a 3 vezes mais altos. Montei uma ideia rápida de site moderno para vocês, gostaria de dar uma olhada?"

    if not api_key:
        return "Nenhum problema técnico crítico identificado (Site simples/Rede social).", email_body, whatsapp_body

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = f"""
        Você é um copywriter de vendas experiente focado em fechar negócios de criação de sites para {sender_name}.
        Sua tarefa é redigir um e-mail de vendas amigável, direto, informal e altamente personalizado para um prestador de serviço brasileiro que atua no exterior, além de uma mensagem curta para WhatsApp.
        
        Dados do Lead:
        - Nome comercial/empresa: {prospect['company_name']}
        - Website/Rede Social: {prospect['website']}
        - Segmento/Serviço: {prospect['segment']}
        - Região: {prospect['region']} ({country_name})
        - Avaliações do Google Maps: {reviews_val} avaliações com nota {rating_val} (Opportunity Score: {score_val}/100)
        - Notas da análise/detalhes: {prospect['notes']}
        
        Dados do Remetente (Você):
        - Nome: {sender_name}
        - WhatsApp: {sender_whatsapp}
        - Pitch do serviço: {sender_pitch}
        
        Instruções de Copywriting e Ângulo de Vendas (Dor Expat):
        1. A dor principal: Em {country_name}, a concorrência local cobra caro. Para um brasileiro cobrar preços premium de clientes locais nativos (americanos, britânicos, portugueses), ele precisa passar 100% de confiança e autoridade. Depender apenas de WhatsApp ou perfil do Instagram passa imagem amadora.
        2. Personalize citando a reputação de reviews real dele do Google (ex: "Vi que vocês têm {reviews_val} avaliações no Google com nota {rating_val}..."), elogiando o trabalho duro deles.
        3. O site profissional (bilíngue ou totalmente em inglês) com fotos reais, depoimentos, e um design moderno de alto padrão permite que eles concorram de igual para igual com empresas nativas do país e cobrem mais caro pelo mesmo serviço.
        4. No assunto do e-mail: Faça uma abordagem curta e intrigante em português (ex: "Sobre o seu serviço de {prospect['segment']} em {prospect['region']}").
        5. O tom deve ser de brasileiro para brasileiro no exterior: amigável, acolhedor, de apoio e sem parecer corporativo formal.
        6. Ofereça apresentar um "estudo visual rápido" ou "uma demonstração de site de alto padrão" desenhada especificamente para eles, sem compromisso, em uma ligação de 10 minutos.
        
        Retorne a resposta EXATAMENTE no formato JSON estruturado a seguir (não insira marcações adicionais markdown como ```json):
        {{
            "notes": "crítica curta e amigável da presença online deles atual (até 3 linhas)",
            "subject": "assunto sugerido para o e-mail",
            "email": "corpo do e-mail de vendas personalizado",
            "whatsapp": "mensagem curta para envio no WhatsApp"
        }}
        """
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        # Strip any formatting blocks if the model ignored instructions
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        
        data = json.loads(text)
        return data.get('notes'), data.get('email'), data.get('whatsapp')
    except Exception as e:
        add_log(f"Aviso: Erro ao gerar copy via Gemini: {e}. Usando fallback.")
        return "Nenhum problema técnico crítico identificado.", email_body, whatsapp_body

def fetch_page_content(url):
    """Retrieve HTML and text content from a web page safely."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            html = response.read()
            # Decode carefully
            try:
                html_decoded = html.decode('utf-8')
            except:
                html_decoded = html.decode('latin-1', errors='ignore')
            soup = BeautifulSoup(html_decoded, 'html.parser')
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text(separator=' ')
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return html_decoded, text
    except Exception as e:
        return "", ""


def fetch_site_evidence(url, max_pages=4):
    """Read homepage plus likely owner/contact pages without paid API calls."""
    html, text = fetch_page_content(url)
    if not html:
        return "", ""
    parsed_root = urllib.parse.urlparse(url)
    chunks_html, chunks_text = [html], [text]
    soup = BeautifulSoup(html, 'html.parser')
    page_hints = ('about', 'about-us', 'team', 'our-story', 'contact', 'sobre', 'quem-somos')
    links = []
    for anchor in soup.find_all('a', href=True):
        absolute = urllib.parse.urljoin(url, anchor['href'])
        parsed = urllib.parse.urlparse(absolute)
        if parsed.netloc.lower() != parsed_root.netloc.lower():
            continue
        if any(hint in parsed.path.lower() for hint in page_hints) and absolute not in links:
            links.append(absolute)
    for page_url in links[:max(0, max_pages - 1)]:
        page_html, page_text = fetch_page_content(page_url)
        if page_html:
            chunks_html.append(page_html)
            chunks_text.append(page_text)
    return " ".join(chunks_html), " ".join(chunks_text)

def is_valid_international_candidate(url, title, snippet):
    url_lower = url.lower()
    title_lower = title.lower()
    snippet_lower = snippet.lower()
    
    # 1. Strictly exclude Brazilian domains
    parsed = urllib.parse.urlparse(url_lower)
    domain = parsed.netloc
    if domain.endswith('.br') or '.com.br' in domain:
        return False
        
    # 2. Exclude software, apps, tech and download keywords
    tech_keywords = [
        'ccleaner', 'piriform', 'download', 'app store', 'google play', 'apk',
        'software', 'pc cleaner', 'registry cleaner', 'mac cleaner', 'cleaner for android',
        'windows cleaner', 'cookie cleaner', 'cache cleaner', 'disk cleaner', 'cleaner pro',
        'cleaner app', 'cleaner online', 'cleaner for chrome', 'extension', 'github', 'npm'
    ]
    if any(kw in url_lower or kw in title_lower or kw in snippet_lower for kw in tech_keywords):
        return False
        
    # 3. Exclude directories unless they are specific profile pages
    directory_keywords = [
        'wikipedia.org', 'yelp.com/search', 'tripadvisor.com', 'glassdoor.com',
        'indeed.com', 'linkedin.com/jobs', 'yellowpages.com/search'
    ]
    if any(dk in url_lower for dk in directory_keywords):
        return False
        
    return True

def detect_brazilian_expat_signals(text_context, url):
    """Detect signs of Brazilian owners or audience in text or URL."""
    text_lower = text_context.lower()
    url_lower = url.lower()
    
    signals = []

    # Sites delivered by Paviani are a known first-party connection for this
    # private prospecting operation, even when visible copy is fully English.
    if 'paviani.net' in text_lower or 'paviani digital media' in text_lower:
        signals.append("Conexão conhecida: site desenvolvido pela Paviani")

    # 0. Explicit Brazil reference in brand, domain or institutional copy.
    if re.search(r'\bbrazil(?:ian|lians)?\b|\bbrasil(?:eiro|eira|eiros|eiras)?\b', f"{text_lower} {url_lower}"):
        signals.append("Referência explícita ao Brasil/Brazil")
    
    # 1. Common Portuguese names/surnames
    common_names = [
        'silva', 'santos', 'souza', 'oliveira', 'pereira', 'lima', 'carvalho', 
        'ferreira', 'rodrigues', 'almeida', 'costa', 'gomes', 'martins', 
        'carlos', 'joao', 'lucas', 'matheus', 'felipe', 'gabriel', 'pedro', 
        'tiago', 'ana', 'maria', 'julia', 'camila', 'aline', 'bruna', 
        'patricia', 'leticia', 'souza', 'melo', 'nascimento', 'barbosa'
    ]
    matched_names = [n for n in common_names if re.search(r'\b' + n + r'\b', text_lower)]
    if matched_names:
        signals.append(f"Nome comum em PT: {', '.join(matched_names[:3])}")
        
    # 2. Portuguese reviews or comments keywords
    review_keywords = [
        'excelente', 'recomendo', 'otimo', 'ótimo', 'maravilhoso', 'perfeito', 
        'obrigado', 'obrigada', 'atendimento', 'serviço', 'limpeza', 'profissional', 
        'trabalho', 'reforma', 'pintura', 'caprichosa', 'super indico', 'super recomendo'
    ]
    matched_reviews = [kw for kw in review_keywords if re.search(r'\b' + kw + r'\b', text_lower)]
    if matched_reviews:
        signals.append("Reviews/Textos em PT")

    # Portuguese interface/contact copy is useful even when the public-facing
    # sales text is English. Require a combination to avoid one-word matches.
    portuguese_ui_markers = [
        'nome', 'telefone', 'estado', 'mensagem', 'enviar', 'quem somos',
        'desenvolvido por', 'todos os direitos reservados'
    ]
    matched_ui = [marker for marker in portuguese_ui_markers if re.search(r'\b' + marker + r'\b', text_lower)]
    if len(matched_ui) >= 2:
        signals.append(f"Interface em português: {', '.join(matched_ui[:4])}")
        
    # 3. Expat or bilingual phrases
    expat_phrases = [
        'falo português', 'falo portugues', 'we speak portuguese', 
        'speak portuguese', 'brazilian owned', 'brazilian-owned', 'brazilian owner',
        'diarista brasileira', 'diaristas brasileiras', 'brazilian cleaner', 
        'brazilian handyman', 'brazilian cleaning', 'brasileiros em', 
        'brasileiro em', 'brasileira em', 'atendimento em português', 
        'atendimento em portugues', 'brazilian contractor', 'brazilian painter'
    ]
    matched_phrases = [p for p in expat_phrases if p in text_lower]
    if matched_phrases:
        signals.append(f"Frase expat: '{matched_phrases[0]}'")
        
    # 4. WhatsApp / phone indicator
    if '+55' in text_lower or 'wa.me/55' in url_lower or 'whatsapp.com/send?phone=55' in url_lower:
        signals.append("WhatsApp brasileiro (+55)")
        
    return signals


def has_brazilian_evidence(signals):
    """A name or targeted-query match alone is not enough evidence."""
    strong_prefixes = (
        'Referência explícita ao Brasil/Brazil', 'Frase expat:',
        'Reviews/Textos em PT', 'Interface em português:', 'WhatsApp brasileiro',
        'Conexão conhecida: site desenvolvido pela Paviani'
    )
    return any(signal.startswith(strong_prefixes) for signal in signals)

def extract_reviews_and_rating(snippet, title):
    """Extract rating and review counts from snippets using regex."""
    rating = 0.0
    reviews_count = 0
    
    combined = f"{title} {snippet}"
    
    # 1. Extract rating (e.g. ★4.9 or 4.9 stars)
    rating_match = re.search(r'(?:★|rating of)\s?([3-5]\.[0-9])', combined, re.IGNORECASE)
    if rating_match:
        rating = float(rating_match.group(1))
    else:
        rating_match_2 = re.search(r'([3-5]\.[0-9])\s?stars', combined, re.IGNORECASE)
        if rating_match_2:
            rating = float(rating_match_2.group(1))
            
    # 2. Extract reviews count (e.g. (126) or 126 reviews)
    reviews_match = re.search(r'\(\s?(\d{1,4})\s?\)', combined)
    if reviews_match:
        reviews_count = int(reviews_match.group(1))
    else:
        reviews_match_2 = re.search(r'(\d{1,4})\s?(?:reviews|avaliações|reviews|avaliacoes)', combined, re.IGNORECASE)
        if reviews_match_2:
            reviews_count = int(reviews_match_2.group(1))
            
    return rating, reviews_count

def calculate_opportunity_score(rating, reviews_count, has_site, is_amateur_site):
    """Calculate the opportunity score from 0 to 100 based on digital gaps."""
    score = 0
    
    # 1. Reputation (quality): up to 30 points
    if rating >= 4.7:
        score += 30
    elif rating >= 4.5:
        score += 20
    elif rating >= 4.0:
        score += 10
        
    # 2. Sweet spot (30-300 reviews): up to 30 points
    if 30 <= reviews_count <= 300:
        score += 30
    elif 10 <= reviews_count < 30:
        score += 20
    elif 300 < reviews_count <= 600:
        score += 15
    elif reviews_count > 0:
        score += 5
        
    # 3. Digital Presence Gap: up to 40 points
    if not has_site:
        score += 40
    elif is_amateur_site:
        score += 30
    else:
        score += 10
        
    return score

def search_companies_serper(segment, city_name, country_code, api_key, limit=10):
    """Search Google Maps via Serper.dev API to find local businesses."""
    import requests
    
    compact_terms = {
        "cleaning": "house cleaning",
        "handyman": "handyman"
    }.get(segment, "cleaning")
    
    # We run 2 distinct queries to maximize coverage:
    # 1. General search (filtered by Brazilian signal check later)
    # 2. Brazilian specific search (direct target)
    queries = [
        f"{compact_terms} {city_name}",
        f"brazilian {compact_terms} {city_name}"
    ]
    
    candidates = []
    seen_urls = set()
    
    url = "https://google.serper.dev/maps"
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    for q in queries:
        add_log(f"Pesquisando via Serper Google Maps API: {q}")
        payload = {
            "q": q,
            "gl": country_code.lower()
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                places = response.json().get("places", [])
                for p in places:
                    web = p.get("website") or p.get("link") or p.get("cid")
                    if not web:
                        continue
                    if not str(web).startswith(('http://', 'https://')):
                        web = f"https://www.google.com/maps?cid={web}"
                        
                    clean_web = web.lower().strip()
                    if clean_web in seen_urls:
                        if q.lower().startswith("brazilian "):
                            for existing in candidates:
                                if existing["url"].lower().strip() == clean_web:
                                    existing["brazilian_query"] = True
                                    break
                        continue
                        
                    seen_urls.add(clean_web)
                    
                    # Convert Serper properties to standard candidate dictionary format
                    candidates.append({
                        "url": web,
                        "title": p.get("title", ""),
                        "rating": float(p.get("rating", 0.0)),
                        "reviews_count": int(p.get("ratingCount", 0)),
                        "phone": p.get("phoneNumber", ""),
                        "emails": [],
                        "brazilian_query": q.lower().startswith("brazilian "),
                        "snippet": f"{p.get('title')} - {p.get('address')}. Média de {p.get('rating')} com {p.get('ratingCount')} avaliações no Google Maps."
                    })
            else:
                add_log(f"Aviso Serper API ({response.status_code}): {response.text}")
        except Exception as e:
            add_log(f"Erro ao consultar Serper API para '{q}': {e}")
            
    return candidates


def search_brazilian_leads_serper(segment, city_name, country_code, api_key, limit=10):
    """Use one targeted web query; local site checks do the remaining filtering."""
    import requests
    term = {"cleaning": 'house cleaning', "handyman": 'handyman'}.get(segment, segment)
    query = f"brazilian {term} {city_name}"
    add_log(f"Pesquisa brasileira focada via Serper: {query}")
    response = requests.post(
        "https://google.serper.dev/search",
        json={"q": query, "gl": country_code.lower(), "num": min(100, max(10, limit * 3))},
        headers={'X-API-KEY': api_key, 'Content-Type': 'application/json'}, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Serper API retornou HTTP {response.status_code}: {response.text[:200]}")
    candidates, seen = [], set()
    for item in response.json().get("organic", []):
        url = item.get("link") or ""
        if not url or url.lower() in seen:
            continue
        if not is_valid_international_candidate(url, item.get("title", ""), item.get("snippet", "")):
            continue
        seen.add(url.lower())
        candidates.append({
            "url": url, "title": item.get("title", ""),
            "snippet": item.get("snippet", ""), "phone": "", "emails": [],
            "rating": 0.0, "reviews_count": 0, "brazilian_query": True,
        })
        if len(candidates) >= limit * 3:
            break
    return candidates


def _gosom_candidate(row, brazilian_query=False):
    """Map one gosom CSV row to the internal candidate contract."""
    website = (row.get("website") or "").strip()
    maps_url = (row.get("link") or row.get("reviews_link") or "").strip()
    url = website or maps_url
    if not url:
        return None

    email_value = row.get("emails") or row.get("email") or ""
    if isinstance(email_value, str):
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', email_value)
    else:
        emails = list(email_value or [])
    try:
        rating = float(row.get("review_rating") or row.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        reviews_count = int(float(row.get("review_count") or row.get("reviews") or 0))
    except (TypeError, ValueError):
        reviews_count = 0

    address = row.get("address") or row.get("complete_address") or ""
    return {
        "url": url, "website": website, "maps_url": maps_url,
        "title": row.get("title") or row.get("name") or "",
        "rating": rating, "reviews_count": reviews_count,
        "phone": row.get("phone") or "", "emails": emails,
        "brazilian_query": brazilian_query,
        "snippet": f"{row.get('category', '')} - {address}. {row.get('descriptions', '')}",
    }


def search_companies_gosom(segment, city_name, country_code, base_url, limit=10,
                           timeout_seconds=360, session=None):
    """Run a job in a self-hosted gosom REST API and normalize its CSV."""
    import requests

    http = session or requests.Session()
    base_url = base_url.rstrip('/')
    term = {"cleaning": "house cleaning", "handyman": "handyman"}.get(segment, segment)
    display_keywords = [f"{term} in {city_name}", f"Brazilian {term} in {city_name}"]
    # gosom preserves custom input IDs in CSV, letting us distinguish a broad
    # result from one returned by the explicit Brazilian query.
    keywords = [f"{display_keywords[0]} #!#general", f"{display_keywords[1]} #!#brazilian"]
    payload = {
        "name": f"paviani-{segment}-{city_name}", "keywords": keywords,
        "lang": "en", "zoom": 15, "depth": max(1, min(3, (limit + 9) // 10)),
        "email": True, "extra_reviews": False,
        "max_time": max(180, min(timeout_seconds, 900)), "fast_mode": False,
        "radius": 10000, "lat": "0", "lon": "0", "proxies": [],
    }
    add_log(f"Enviando busca ao gosom: {', '.join(display_keywords)}")
    response = http.post(f"{base_url}/api/v1/jobs", json=payload, timeout=20)
    response.raise_for_status()
    job_id = response.json()["id"]

    deadline = time.monotonic() + timeout_seconds
    status = "pending"
    while time.monotonic() < deadline:
        job_response = http.get(f"{base_url}/api/v1/jobs/{job_id}", timeout=20)
        job_response.raise_for_status()
        job_data = job_response.json()
        status = str(job_data.get("Status") or job_data.get("status") or "").lower()
        if status in GOSOM_TERMINAL_STATUSES:
            break
        time.sleep(2)
    if status != "ok":
        raise RuntimeError(f"Job gosom terminou com status '{status}'")

    download = http.get(f"{base_url}/api/v1/jobs/{job_id}/download", timeout=30)
    download.raise_for_status()
    rows = csv.DictReader(io.StringIO(download.content.decode('utf-8-sig', errors='replace')))
    candidates, seen = [], set()
    for row in rows:
        input_text = " ".join(str(row.get(k, "")) for k in ("input", "keyword", "query", "input_id")).lower()
        candidate = _gosom_candidate(row, brazilian_query="brazilian" in input_text)
        if not candidate:
            continue
        key = (candidate.get("maps_url") or candidate["url"]).lower().strip()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
        if len(candidates) >= limit * 3:
            break
    return candidates

def run_international_prospecting_job(segment, country_code, city_name, limit=10, source_mode="auto"):
    """Execute the expat search job in the background."""
    clear_logs()
    add_log(f"Iniciando Busca Internacional: Segmento='{segment}', País='{country_code}', Cidade='{city_name}'...")
    
    country_info = COUNTRIES.get(country_code)
    if not country_info:
        add_log(f"❌ País '{country_code}' não suportado.")
        return
        
    segment_info = SEGMENT_TEMPLATES.get(segment)
    if not segment_info:
        add_log(f"❌ Segmento '{segment}' não suportado.")
        return
        
    ddi = country_info["ddi"]
    country_name = country_info["name"]
    
    # 1. Build advanced expat search queries (limited to 3 queries to avoid DDG rate limiting)
    query_loc = f'"{city_name}"' if city_name else country_info["default_query_loc"]
    
    compact_terms = {
        "cleaning": '("cleaning service" OR "house cleaning" OR "maid service")',
        "handyman": '("handyman" OR "home renovation" OR "house painting")'
    }.get(segment, '("cleaning" OR "handyman")')
    
    expat_terms = '("brazilian" OR "brasileiro" OR "brasileira")'
    
    queries = [
        # Query 1: Google Maps profiles
        f'site:google.com/maps/place {compact_terms} {query_loc}',
        # Query 2: Expat Web Search
        f'{compact_terms} {expat_terms} {query_loc} -site:*.br',
        # Query 3: Facebook directory pages
        f'site:facebook.com {compact_terms} "brazilian" {query_loc}'
    ]
    
    candidates = []
    seen_urls = set()
    
    # Check already existing domains in database to avoid duplicates
    existing_prospects = database.get_prospects(is_international_filter=1)
    for ep in existing_prospects:
        web = ep.get('website', '')
        if web:
            seen_urls.add(web.lower().strip())
            
    # Prefer the self-hosted Maps engine when configured.
    serper_api_key = database.get_setting('serper_api_key', '')
    gosom_api_url = database.get_setting('gosom_api_url', '').strip()
    
    if source_mode in ("auto", "gosom") and gosom_api_url:
        add_log("Usando motor local gosom/google-maps-scraper...")
        try:
            candidates = search_companies_gosom(segment, city_name, country_code, gosom_api_url, limit)
        except Exception as e:
            add_log(f"Falha no gosom: {e}")
            if source_mode == "gosom":
                add_log("Busca encerrada: motor gosom selecionado explicitamente.")
                return
            add_log("Alternando para fonte reserva...")

    if not candidates and source_mode in ("auto", "serper") and serper_api_key and len(serper_api_key.strip()) > 3:
        add_log("Usando API do Serper.dev para buscar locais e contatos do Google Maps...")
        # 1. Search Google Maps places
        maps_candidates = search_companies_serper(segment, city_name, country_code, serper_api_key, limit)
        candidates.extend(maps_candidates)
        
        # 2. Search organic web listings as backup
        web_candidates = search_brazilian_leads_serper(segment, city_name, country_code, serper_api_key, limit)
        for wc in web_candidates:
            if not any(c["url"].lower().strip() == wc["url"].lower().strip() for c in candidates):
                candidates.append(wc)
    elif not candidates and source_mode in ("auto", "duckduckgo"):
        add_log("Usando DuckDuckGo para buscas locais (Sem API Key do Serper)...")
        # Run search engine
        with DDGS() as ddgs:
            for q in queries:
                add_log(f"Pesquisando: {q}")
                try:
                    results = list(ddgs.text(q, max_results=12))
                    for r in results:
                        url = r.get('href', '')
                        title = r.get('title', '')
                        snippet = r.get('body', '')
                        
                        if not url or url.lower().strip() in seen_urls:
                            continue
                            
                        # Skip common directory index domains unless they are profile specific
                        if any(kw in url.lower() for kw in ['yelp.', 'yellowpages.', 'tripadvisor.', 'wikipedia.', 'classifieds']):
                            continue
                            
                        # Filter candidates through the validation helper
                        if not is_valid_international_candidate(url, title, snippet):
                            continue
                            
                        seen_urls.add(url.lower().strip())
                        candidates.append({
                            "url": url,
                            "title": title,
                            "snippet": snippet
                        })
                        if len(candidates) >= limit * 2:
                            break
                except Exception as e:
                    add_log(f"Aviso na busca: {e}")
                
                # Throttle to prevent rate limit blocks
                time.sleep(3)
                if len(candidates) >= limit * 2:
                    break
                
    if not candidates:
        add_log("Aviso: Nenhum candidato encontrado. Se você realizou muitas buscas seguidas, o buscador pode ter bloqueado temporariamente as requisições. Aguarde 3-5 minutos e tente novamente.")
    else:
        add_log(f"Encontrados {len(candidates)} candidatos potenciais. Iniciando análise detalhada...")
    
    saved_count = 0
    for idx, cand in enumerate(candidates):
        if saved_count >= limit:
            break
            
        url = cand["url"]
        snippet_title = cand["title"]
        snippet_text = cand["snippet"]
        
        add_log(f"[{idx+1}/{len(candidates)}] Analisando {url}...")
        
        # 1. Clean company name from snippet title or url
        company_name = snippet_title.split('|')[0].split('-')[0].split('–')[0].split('—')[0].strip()
        if 'Instagram' in company_name or 'Facebook' in company_name or not company_name or re.match(r'^\d+$', re.sub(r'\s', '', company_name)) or len(company_name) < 3:
            # Try to get user handle from URL
            parsed_url = urllib.parse.urlparse(url)
            path_parts = [p for p in parsed_url.path.split('/') if p]
            if path_parts and not any(kw in path_parts[0].lower() for kw in ['page', 'profile', 'p']):
                company_name = path_parts[0].replace('-', ' ').replace('_', ' ').title()
            else:
                company_name = "Prestador Expat"
                
        # 2. Extract reputation from snippet/title (falling back to Serper's pre-extracted fields)
        rating = cand.get("rating", 0.0)
        reviews_count = cand.get("reviews_count", 0)
        if not rating and not reviews_count:
            rating, reviews_count = extract_reviews_and_rating(snippet_text, snippet_title)
        
        # 3. Scrape page (if website) or parse snippet text directly
        html, page_text = "", ""
        has_site = False
        is_amateur_site = False
        if not any(soc in url.lower() for soc in ['facebook.com', 'instagram.com', 'google.com/maps']):
            html, page_text = fetch_site_evidence(url)
            if html:
                has_site = True
                # Detect common amateur website tools
                if any(am in url.lower() or am in html.lower() for am in ['wixsite.com', 'site123.me', 'webnode.com', 'linktr.ee', 'wordpress.com']):
                    is_amateur_site = True
            
        # Combine page content with snippet context to maximize contact extraction and signal checks
        full_text_context = f"{snippet_title} {snippet_text} {page_text}"
        
        # 4. Expat signal verification
        signals = detect_brazilian_expat_signals(f"{full_text_context} {html}", url)
        if not has_brazilian_evidence(signals):
            # Fallback: check if the Maps listing title or snippet explicitly mentions Brazilian
            if "brazilian" in snippet_title.lower() or "brazilian" in snippet_text.lower() or "brasileir" in snippet_title.lower():
                signals = ["Identificado no Maps (Brazilian/Brasileiro)"]
                
        explicit_map_signal = any("Identificado no Maps" in signal for signal in signals)
        if not has_brazilian_evidence(signals) and not explicit_map_signal:
            add_log(f"⏩ Ignorando {url}: sem evidência verificável de conexão brasileira.")
            continue
            
        add_log(f"   -> Sinais expat encontrados: {', '.join(signals)}")
        
        email, phone, emails, phones = extract_contacts_from_html(html, full_text_context, url, ddi)
        if not email and cand.get("emails"):
            email = cand["emails"][0]
        
        # Fallback to Serper pre-extracted phone if not found in HTML
        if not phone and cand.get("phone"):
            phone = clean_phone_international(cand["phone"], ddi)
            
        # Ensure we have at least a phone or an email to make contact!
        if not email and not phone:
            add_log(f"⏩ Ignorando {url} pois não foi encontrado e-mail ou telefone de contato.")
            continue
            
        # 5. Opportunity Score calculation
        opportunity_score = calculate_opportunity_score(rating, reviews_count, has_site, is_amateur_site)
        
        # 6. Create prospect layout dict
        prospect_dict = {
            "company_name": company_name,
            "website": url,
            "segment": segment_info["title"],
            "region": f"{city_name} - {country_name}" if city_name else country_name,
            "status": "pending",
            "contact_email": email,
            "contact_phone": phone,
            "contact_whatsapp": phone,
            "notes": f"Sinais: {', '.join(signals)}. Rating: {rating} ({reviews_count} reviews).",
            "detected_issues": ["Site amador/improvisado" if is_amateur_site else "Sem site próprio" if not has_site else "Presença digital necessita profissionalização"],
            "is_surgical": 0,
            "is_international": 1,
            "international_country": country_code,
            "reviews_count": reviews_count,
            "rating": rating,
            "opportunity_score": opportunity_score
        }
        
        # 7. Generate copies using Gemini
        notes_critique, email_body, whatsapp_draft = query_gemini_international_copy(prospect_dict, country_name)
        prospect_dict["notes"] = f"Sinais: {', '.join(signals)}. Google: {rating} ({reviews_count} reviews). Critica: {notes_critique}"
        prospect_dict["email_subject"] = f"Sobre os serviços de {segment_info['title']} da {company_name} em {city_name}"
        prospect_dict["email_body"] = email_body
        prospect_dict["whatsapp_draft"] = whatsapp_draft
        
        # 8. Save to database
        lead_id = database.add_prospect(prospect_dict)
        add_log(f"✅ Lead Expat Salvo ID {lead_id}: {company_name} | Score: {opportunity_score} | Reviews: {reviews_count} | Rating: {rating}")
        saved_count += 1
        
        # Prevent API rate limits
        time.sleep(1)
        
    add_log(f"Busca internacional concluída! {saved_count} novos leads adicionados com sucesso.")
