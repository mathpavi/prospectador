"""Central WhatsApp (C9 do PLANO_PROSPECTADOR): prioridade, telefone movel e mensagens para contato MANUAL.

Nada aqui envia mensagem: so calcula a prioridade, higieniza o telefone e sugere o texto que VOCE le, ajusta e envia.
"""
import json
import re
from datetime import datetime

CORE_SEGMENTS = ("metal", "usina", "caldeir", "serralh", "alumin", "vidra", "esquadri", "marcen", "funilar", "solda")
JUNK_NAMES = {"sobre", "pagina inicial", "página inicial", "inicio", "início", "home", "contato", "contatos", "quem somos",
              "empresa", "institucional", "servicos", "serviços", "produtos", "portfolio", "portfólio", "blog", "menu"}
LEGAL_SUFFIX = re.compile(r"[\s,\-–]*\b(ltda\.?|eireli|epp|me|s\.?a\.?|s/a|mei|ltd)\b\.?$", re.I)


# ------------------------------------------------------------------------------- telefone ----
def phone_info(raw):
    """(digitos_com_55, e_movel, motivo). e_movel True so para celular brasileiro com 9 digitos."""
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) not in (10, 11):
        return "", False, "numero incompleto"
    ddd, num = d[:2], d[2:]
    if not ("11" <= ddd <= "99") or ddd[1] == "0":
        return "", False, "DDD invalido"
    if len(num) == 9:
        return "55" + d, num[0] == "9", ("" if num[0] == "9" else "9 digitos que nao comeca com 9")
    # 8 digitos: fixo (comeca com 2-5) ou celular antigo sem o 9 (6-9): o WhatsApp costuma nao achar
    return "55" + d, False, ("fixo" if num[0] in "2345" else "celular sem o 9 (pode falhar no WhatsApp)")


# --------------------------------------------------------------------------------- nomes ----
def clean_company_name(name, website=""):
    n = re.sub(r"\s+", " ", (name or "")).strip(" -–|,.")
    if n.lower() in JUNK_NAMES or len(n) < 3:
        host = re.sub(r"^(https?://)?(www\.)?", "", (website or "").lower()).split("/")[0].split(".")[0]
        n = host.replace("-", " ").title() if host else "sua empresa"
    n = LEGAL_SUFFIX.sub("", n).strip(" -–|,.") or n
    return n


def first_name(full):
    p = re.sub(r"[^A-Za-zÀ-ÿ ]", " ", full or "").split()
    if not p or len(p[0]) < 2:
        return ""
    return p[0].capitalize()


def partner_first_name(socios_json):
    try:
        items = json.loads(socios_json) if isinstance(socios_json, str) else (socios_json or [])
        for it in items:
            fn = first_name((it or {}).get("nome", ""))
            if fn:
                return fn
    except Exception:  # noqa: BLE001
        pass
    return ""


def _days_since(s):
    try:
        return (datetime.now() - datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")).days
    except Exception:  # noqa: BLE001
        return None


def has_own_site(lead):
    w = (lead.get("website") or "").lower()
    return bool(w.startswith("http")) and not any(x in w for x in (
        "maps", "google.", "telelistas", "guiamais", "solutudo", "apontador", "facebook", "instagram", "linkedin", "wa.me", "cnpj"))


# ---------------------------------------------------------------------------- prioridade ----
def priority(lead, group, has_mockup):
    """(0-100, flags). Quem tem celular, esboco pronto e encaixe no que voce vende vem primeiro."""
    _, mobile, why = phone_info(lead.get("contact_whatsapp") or lead.get("contact_phone"))
    flags, score = [], 40
    if mobile:
        score += 20
    else:
        score -= 25
        flags.append("sem_celular")
    if has_mockup:
        score += 15
        flags.append("esboco_pronto")
    if has_own_site(lead):
        score += 10
    if partner_first_name(lead.get("socios")):
        score += 5
        flags.append("nome_do_socio")
    seg = (lead.get("segment") or "").lower()
    if any(k in seg for k in CORE_SEGMENTS):
        score += 10
    if group == "email_sent":
        d = _days_since(lead.get("sent_at"))
        if d is not None:
            if 2 <= d <= 10:
                score += 10
                flags.append("momento_do_followup")
            elif d > 30:
                score -= 10
    return max(0, min(100, score)), flags


# ---------------------------------------------------------------------------- mensagens ----
def _greeting(lead, company):
    pn = partner_first_name(lead.get("socios"))
    return f"Oi, tudo bem? Falo com {pn}?" if pn else f"Oi, tudo bem? Falo com o responsável pela {company}?"


def build_message(lead, group, mockup_url, sender_name):
    """Texto curto, humano e honesto (sem elogio inventado). Termina com saida facil. Varia por lead para nao repetir."""
    company = clean_company_name(lead.get("company_name"), lead.get("website"))
    sender = first_name(sender_name) or "Matheus"
    greet = _greeting(lead, company)
    seg = (lead.get("segment") or "").strip().lower() or "seu segmento"
    region = re.sub(r"\s*\(\+?\d+\s*km\)", "", lead.get("region") or "").strip() or "sua região"
    exit_line = "Se não for o momento, é só me avisar que eu não volto a escrever."
    v = (lead.get("id") or 0) % 3

    if group == "email_sent":
        d = _days_since(lead.get("sent_at"))
        when = "ontem" if d == 1 else (f"há {d} dias" if d and d > 1 else "recentemente")
        base = f"{greet} Aqui é o {sender}. Te mandei um e-mail {when} com uma ideia de site para a {company}."
        if mockup_url:
            base += f" Se quiser ver o esboço que preparei: {mockup_url}"
        return f"{base}\nConseguiu dar uma olhada? {exit_line}"

    if mockup_url:
        options = [
            f"{greet} Aqui é o {sender}. Montei uma proposta visual de como o site da {company} poderia ficar. É só olhar, sem compromisso: {mockup_url}\nSe fizer sentido, a gente conversa. {exit_line}",
            f"{greet} Sou o {sender}, faço sites para empresas do setor de {seg}. Preparei um esboço pensando na {company}: {mockup_url}\nO que você acha? {exit_line}",
            f"{greet} {sender} aqui. Fiz um esboço de site para a {company}, com o que vi publicamente de vocês: {mockup_url}\nPosso te explicar em 5 minutos? {exit_line}",
        ]
        return options[v]
    if has_own_site(lead):
        return (f"{greet} Aqui é o {sender}. Dei uma olhada no site da {company} e vi um caminho para deixá-lo mais rápido no celular, "
                f"com pedido de orçamento direto pelo WhatsApp. Posso te mostrar um exemplo? {exit_line}")
    return (f"{greet} Aqui é o {sender}. Encontrei a {company} em {region}, mas não achei um site próprio. "
            f"Faço páginas simples (serviços, mapa e WhatsApp) para empresas do setor de {seg}. Posso te mostrar um exemplo? {exit_line}")


def enrich(lead, group, mockup_url, sender_name):
    """Acrescenta ao registro do prospect os campos que a tela usa."""
    digits, mobile, why = phone_info(lead.get("contact_whatsapp") or lead.get("contact_phone"))
    score, flags = priority(lead, group, bool(mockup_url))
    out = dict(lead)
    out.update({
        "wa_digits": digits, "wa_mobile": mobile, "wa_phone_note": why,
        "wa_priority": score, "wa_flags": flags, "mockup_url": mockup_url or "",
        "suggested_message": build_message(lead, group, mockup_url, sender_name),
        "display_name": clean_company_name(lead.get("company_name"), lead.get("website")),
    })
    return out
