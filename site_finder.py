"""Descoberta de site dos leads vindos do CNPJ da Receita (eles chegam so com nome, cidade, telefone e e-mail do cadastro).

Para cada lead: busca "<nome> <cidade> <UF>", escolhe o resultado que parece o site PROPRIO da empresa (nao diretorio, rede social,
marketplace nem pagina de consulta de CNPJ) e analisa o site (problemas, e-mail e WhatsApp do proprio site). Sem site encontrado, o lead
fica registrado como "sem site" DEPOIS de procurado: so entao o e-mail pode dizer, com verdade, que nao encontramos um site.
O lead so e aprovado para envio depois de verificado (e se tiver e-mail valido de verdade da empresa).
"""
import re
import unicodedata
from urllib.parse import urlparse

import database

BAD_DOMAINS = ("instagram.", "facebook.", "fb.com", "linkedin.", "youtube.", "tiktok.", "twitter.", "x.com", "wa.me", "whatsapp.", "linktr.ee", "google.",
               "olx.", "mercadolivre.", "shopee.", "amazon.", "aliexpress.", "telelistas", "guiamais", "solutudo", "apontador", "econodata", "cnpj", "casadosdados",
               "cnpja", "empresaqui", "consultasocio", "listamais", "infoseg", "serasa", "reclameaqui", "jusbrasil", "tripadvisor", "yelp", "foursquare", "mapquest",
               "brasilapi", "gov.br", "wikipedia", "pinterest", "tudo", "guia", "lista", "catalogo", "diretorio", "empresas.", "paginasamarelas", "yellowpages",
               "bing.com", "yahoo.", "duckduckgo", "blogspot", "wordpress.com", "wixsite", "business.site", "negocio.site", "sites.google")
GENERIC = {"metalurgica", "metalurgicas", "industria", "industrias", "comercio", "servicos", "ltda", "epp", "eireli", "empresa", "grupo", "brasil", "brasileira",
           "usinagem", "caldeiraria", "serralheria", "vidracaria", "esquadrias", "aluminio", "marmoraria", "plasticos", "plastico", "moveis", "textil", "padaria",
           "panificadora", "confeitaria", "limpeza", "transportes", "transportadora", "logistica", "distribuidora", "advocacia", "advogados", "advogado", "associados",
           "escritorio", "seguranca", "estetica", "clinica", "equipamentos", "materiais", "produtos", "sociedade", "individual", "metais", "metal", "aco", "acos",
           "construcoes", "construcao", "montagens", "manutencao", "ferramentas", "ferramentaria", "pecas", "artefatos", "fabrica", "fabricacao", "sul", "norte"}


def _norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", s)


def name_tokens(name):
    """Palavras distintivas do nome (>=4 letras, fora termos genericos do segmento)."""
    toks = [t for t in _norm(name).split() if len(t) >= 4 and t not in GENERIC]
    return list(dict.fromkeys(toks))


def pick_site(name, results, city=""):
    """Escolhe, entre os resultados da busca, o site proprio da empresa (ou None). Exige que uma palavra distintiva do nome apareca
    no dominio ou no titulo; sem palavra distintiva, exige o nome inteiro no titulo."""
    toks = name_tokens(name)
    full = " ".join(_norm(name).split())
    best = None
    for r in results or []:
        href = r.get("href") or ""
        try:
            host = urlparse(href).netloc.lower().replace("www.", "")
        except Exception:  # noqa: BLE001
            continue
        if not host or any(b in host for b in BAD_DOMAINS):
            continue
        dom = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
        title = _norm(r.get("title", ""))
        snippet = _norm(r.get("body", ""))
        score = 0
        if toks:
            score += sum(2 for t in toks if t in dom) + sum(1 for t in toks if t in title)
        elif full and full in title:
            score += 2
        if city and _norm(city) in (title + " " + snippet):
            score += 1
        if score >= 2 and (best is None or score > best[0]):
            best = (score, f"https://{host}/")
    return best[1] if best else None


def has_event(conn, pid, etype):
    return bool(conn.execute("SELECT 1 FROM events WHERE prospect_id=? AND type=? LIMIT 1", (pid, etype)).fetchone())


def backlog(conn=None):
    """Leads do CNPJ ainda sem busca de site."""
    close = conn is None
    conn = conn or database.get_db_connection()
    n = conn.execute("""SELECT COUNT(*) FROM prospects p WHERE p.directory_source='cnpj_receita' AND (p.website IS NULL OR p.website='')
                        AND p.status IN ('pending') AND NOT EXISTS (SELECT 1 FROM events e WHERE e.prospect_id=p.id AND e.type='site_checked')""").fetchone()[0]
    if close:
        conn.close()
    return n


def _default_search(query, max_results=10):
    import agent
    return agent.search_web_candidates(query, max_results=max_results)


def _default_analyze(url, segment, region):
    import agent
    return agent.analyze_website(url, segment, region)


def _default_compose(prospect):
    import agent
    return agent.generate_prospect_email(prospect)


def _write_email(pid, compose):
    """O envio exige assunto e corpo gravados: gera depois que o site foi procurado (o texto muda se ha site ou nao)."""
    try:
        p = database.get_prospect(pid)
        subject, body, wa = (compose or _default_compose)(p)
        database.update_prospect(pid, {"email_subject": subject, "email_body": body, "whatsapp_draft": wa})
    except Exception:  # noqa: BLE001
        pass


def check_one(p, search=None, analyze=None, compose=None):
    """Procura e analisa o site de um lead. Devolve 'site' | 'sem_site' | 'duplicado' | 'adiado' (busca vazia: tenta de novo depois)."""
    search = search or _default_search
    analyze = analyze or _default_analyze
    city = (p.get("region") or "").split(" - ")[0]
    uf = (p.get("region") or "").split(" - ")[-1]
    query = f'"{p["company_name"]}" {city} {uf}'
    try:
        results = search(query, 10) or []
    except Exception:  # noqa: BLE001
        results = []
    if not results:
        # busca vazia = provavel falha do buscador (cota, bloqueio), NAO prova de que a empresa nao tem site: tenta de novo mais tarde
        # e so conclui "sem site" depois de 3 buscas vazias seguidas
        conn = database.get_db_connection()
        n = conn.execute("SELECT COUNT(*) FROM events WHERE prospect_id=? AND type='site_search_empty'", (p["id"],)).fetchone()[0]
        conn.close()
        if n < 2:
            database.add_event(p["id"], "site_search_empty", query, {})
            return "adiado"
    url = pick_site(p["company_name"], results, city)
    if not url:
        database.add_event(p["id"], "site_checked", "nenhum site proprio encontrado", {"found": False, "q": query})
        _write_email(p["id"], compose)
        return "sem_site"
    dom = urlparse(url).netloc.replace("www.", "")
    existing = database.check_domain_exists(dom, full_url=url)
    if existing and existing != p["id"]:
        database.update_prospect(p["id"], {"status": "rejected", "error_message": f"site ja cadastrado em outro lead ({existing})"})
        database.add_event(p["id"], "site_checked", f"duplicado de {existing}", {"found": True, "url": url, "dup": existing})
        return "duplicado"
    upd = {"website": url}
    try:
        a = analyze(url, p.get("segment") or "", p.get("region") or "")
    except Exception:  # noqa: BLE001
        a = None
    if a:
        upd.update({"website": a.get("website") or url, "detected_issues": a.get("detected_issues") or [],
                    "screenshot": a.get("screenshot") or ""})
        site_email = (a.get("contact_email") or "").strip().lower()
        # e-mail do PROPRIO dominio da empresa vale mais que o do cadastro da Receita
        if site_email and site_email.rsplit("@", 1)[-1].replace("www.", "") == dom:
            upd["contact_email"] = site_email
        if a.get("contact_whatsapp") and not p.get("contact_whatsapp"):
            upd["contact_whatsapp"] = a["contact_whatsapp"]
    database.update_prospect(p["id"], upd)
    database.add_event(p["id"], "site_checked", url, {"found": True, "url": url, "analyzed": bool(a)})
    _write_email(p["id"], compose)
    return "site"


def approve_waiting(limit):
    """Aprova leads do CNPJ ja verificados (site procurado) com e-mail valido da empresa, ate `limit`. Respeita a porta de aprovacao."""
    if limit <= 0 or database.get_setting("autopilot_auto_approve", "0") != "1":
        return 0
    conn = database.get_db_connection()
    rows = conn.execute("""SELECT p.id FROM prospects p WHERE p.directory_source='cnpj_receita' AND p.status='pending'
                           AND p.contact_email IS NOT NULL AND p.contact_email != ''
                           AND EXISTS (SELECT 1 FROM events e WHERE e.prospect_id=p.id AND e.type='site_checked')
                           AND NOT EXISTS (SELECT 1 FROM events e WHERE e.prospect_id=p.id AND e.type='cnpj_approve_blocked')
                           ORDER BY (p.website IS NOT NULL AND p.website != '') DESC, p.id LIMIT ?""", (limit * 3,)).fetchall()
    conn.close()
    n = 0
    for r in rows:
        if n >= limit:
            break
        p = database.get_prospect(r["id"])
        ok, why = database.approval_gate(dict(p, website=p.get("website") or "https://sem-site.invalid"))
        if not ok:
            database.add_event(p["id"], "cnpj_approve_blocked", why, {})
            continue
        database.update_prospect(p["id"], {"status": "approved"})
        database.add_event(p["id"], "cnpj_approved", None, {})
        n += 1
    return n


def process_batch(limit=8, search=None, analyze=None, compose=None):
    """Verifica ate `limit` leads (os com e-mail primeiro) e aprova os prontos conforme o estoque da fila. Devolve estatisticas."""
    import rotation
    conn = database.get_db_connection()
    rows = conn.execute("""SELECT p.id FROM prospects p WHERE p.directory_source='cnpj_receita' AND (p.website IS NULL OR p.website='')
                           AND p.status='pending' AND NOT EXISTS (SELECT 1 FROM events e WHERE e.prospect_id=p.id AND e.type='site_checked')
                           ORDER BY (p.contact_email IS NOT NULL AND p.contact_email != '') DESC, p.id LIMIT ?""", (limit,)).fetchall()
    conn.close()
    stats = {"site": 0, "sem_site": 0, "duplicado": 0, "adiado": 0}
    for r in rows:
        p = database.get_prospect(r["id"])
        if p:
            stats[check_one(p, search, analyze, compose)] += 1
    try:
        target = int(database.get_setting("autopilot_queue_target", "60") or 60)
    except Exception:  # noqa: BLE001
        target = 60
    stats["aprovados"] = approve_waiting(max(0, target - rotation.stock()))
    stats["restantes"] = backlog()
    return stats
