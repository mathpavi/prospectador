"""Central WhatsApp (C9 do PLANO_PROSPECTADOR): prioridade, telefone movel e mensagens para contato MANUAL.

Nada aqui envia mensagem: so calcula a prioridade, higieniza o telefone e sugere o texto que VOCE le, ajusta e envia.
"""
import json
import random
import re
import zlib
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
def _hour():
    try:
        import zoneinfo
        return datetime.now(zoneinfo.ZoneInfo("America/Sao_Paulo")).hour
    except Exception:  # noqa: BLE001
        return datetime.now().hour


def _domain(website):
    return re.sub(r"^(https?://)?(www\.)?", "", (website or "").lower()).split("/")[0]


def build_message(lead, group, mockup_url, sender_name, variant=0, hour=None):
    """Mensagem curta, humana e HONESTA (so afirma o que e verdade: o que foi feito, o que foi visto, o que e oferta).

    Montada a partir de pecas intercambiaveis (saudacao, identidade, apresentacao, motivo, link, chamada, saida) e de varios
    formatos, para que dois leads quase nunca recebam o mesmo texto. A escolha e ESTAVEL por lead (mesmo id + nome + variant =
    mesma mensagem), e `variant` troca de versao ("Outra versao"). Sem emoji, sem elogio inventado, sem artigo de genero no remetente.
    """
    rng = random.Random(zlib.crc32(f"{lead.get('id')}|{lead.get('company_name')}|{variant}".encode("utf-8")))
    pick = lambda opts: opts[rng.randrange(len(opts))]  # noqa: E731
    h = _hour() if hour is None else hour
    company = clean_company_name(lead.get("company_name"), lead.get("website"))
    sender = first_name(sender_name) or "Matheus"
    seg = (lead.get("segment") or "").strip().lower() or "seu segmento"
    region = re.sub(r"\s*\(\+?\d+\s*km\)", "", lead.get("region") or "").strip() or "sua região"
    pn = partner_first_name(lead.get("socios"))
    site = _domain(lead.get("website"))

    greetings = ["Oi, tudo bem?", "Olá, tudo bem?", "Oi!", "Olá!", "Tudo bem?"]
    if h < 12:
        greetings += ["Bom dia!", "Bom dia, tudo bem?"]
    elif h < 18:
        greetings += ["Boa tarde!", "Boa tarde, tudo bem?"]
    if pn:
        identity = pick([f"Falo com {pn}?", f"Estou falando com {pn}?", f"Esse número é de {pn}?", f"{pn}, é você que cuida da {company}?"])
    else:
        identity = pick([f"Falo com a pessoa responsável pela {company}?", f"Quem cuida da divulgação da {company} por aí?",
                         f"Estou falando com a {company}?", f"Consigo falar com quem decide sobre o site da {company}?"])
    # se a saudacao ja citou a empresa, o resto da mensagem fala "de vocês" (evita repetir o nome 3 vezes e soar mecanico)
    identity_used = True if group != "email_sent" else (rng.random() < 0.5)
    use_you = identity_used and (company in identity) and (rng.random() < 0.8)
    de = "de vocês" if use_you else f"da {company}"
    para = "para vocês" if use_you else f"para a {company}"
    em = "em vocês" if use_you else f"na {company}"
    obj = "vocês" if use_you else f"a {company}"
    intro = pick([f"Aqui é {sender}.", f"Meu nome é {sender}.", f"{sender} aqui.", f"Me chamo {sender}.",
                  f"Sou {sender}, trabalho com criação de sites.", f"Sou {sender}, faço sites para empresas.",
                  f"Meu nome é {sender}, faço sites para empresas do segmento de {seg}.", f"Sou {sender} e crio sites para empresas de {seg}."])
    exit_line = pick(["Se não for o momento, é só me avisar que não volto a escrever.", "Se não tiver interesse, sem problema: é só me dizer.",
                      "Se preferir que eu não escreva mais, me avise que eu paro por aqui.", "Sem compromisso: se não fizer sentido, é só falar que não incomodo mais.",
                      "Caso não seja o momento, me avisa que eu paro de mandar mensagem.", "Se não for útil agora, sem problema, é só avisar."])
    link = ""
    if mockup_url:
        link = pick(["Dá uma olhada: {u}", "Está aqui: {u}", "Pode ver por este link: {u}", "Link: {u}", "{u}"]).format(u=mockup_url)

    if group == "email_sent":
        d = _days_since(lead.get("sent_at"))
        when = "ontem" if d == 1 else (f"há {d} dias" if d and d > 1 else "recentemente")
        reason = pick([f"Te enviei um e-mail {when} com uma ideia de site {para}.",
                       f"Mandei um e-mail {when} sobre uma proposta de site {para}.",
                       f"Passando para saber se você viu o e-mail que enviei {when} sobre o site {de}.",
                       f"Enviei {when} um e-mail com uma ideia de site {para} e queria saber se chegou."])
        cta = pick(["Conseguiu dar uma olhada?", "Chegou a ver?", "O que achou?", "Posso te explicar por aqui?"])
        if link:
            reason += " Preparei também um esboço."
        opener = pick(greetings) + (" " + identity if identity_used else "")
    else:
        if mockup_url:
            reason = pick([f"Montei uma proposta visual de como o site {de} poderia ficar.",
                           f"Preparei um esboço de site pensando {em}.",
                           f"Fiz um esboço de como poderia ser o site {de}, com base no que vi publicado.",
                           f"Separei um esboço de site {para} e queria sua opinião.",
                           f"Criei uma ideia de site {para}."])
            cta = pick(["O que achou?", "Me diz o que você acha?", "Posso te explicar como funcionaria?",
                        "Se fizer sentido, a gente conversa rapidinho.", "Quer que eu te explique em 5 minutos?"])
        elif has_own_site(lead):
            look = pick([f"Dei uma olhada no site {de}.", f"Vi o site {de} ({site}).", f"Acessei o site {de}."])
            value = pick(["Tenho ideias para deixá-lo mais rápido no celular e com pedido de orçamento direto pelo WhatsApp.",
                          "Dá para deixar o site mais leve no celular e com um botão de orçamento pelo WhatsApp.",
                          "Vejo espaço para deixá-lo mais rápido no celular e facilitar o contato dos clientes."])
            reason = f"{look} {value}"
            cta = pick(["Posso te mostrar um exemplo?", "Faz sentido conversarmos rapidinho?", "Posso te mandar um exemplo por aqui?",
                        "Teria interesse em ver como ficaria?", "Posso te explicar em 5 minutos?"])
        else:
            look = pick([f"Encontrei {obj} em {region}, mas não achei um site próprio.",
                         f"Procurei {obj} na internet e não encontrei um site próprio.",
                         f"Vi {obj} em {region}, mas sem site próprio."])
            value = pick(["Faço páginas simples com serviços, mapa e botão de WhatsApp.",
                          f"Crio sites simples e rápidos, com WhatsApp e localização, para empresas de {seg}.",
                          f"Monto uma página com seus serviços, contato e WhatsApp para empresas do segmento de {seg}."])
            reason = f"{look} {value}"
            cta = pick(["Posso te mostrar um exemplo?", "Faz sentido conversarmos rapidinho?", "Posso te mandar um exemplo por aqui?",
                        "Teria interesse em ver como ficaria?", "Posso te explicar em 5 minutos?"])
        opener = pick(greetings) + " " + identity

    if "interesse" in cta.lower() and "interesse" in exit_line.lower():       # evita repetir a palavra na mesma mensagem
        exit_line = "Se não for o momento, é só me avisar que não volto a escrever."

    shape = rng.randrange(4)
    if shape == 0:      # um bloco + link + fechamento
        text = f"{opener} {intro} {reason}\n{link}\n\n{cta} {exit_line}"
    elif shape == 1:    # blocos separados por linha
        text = f"{opener}\n\n{intro} {reason}\n{link}\n\n{cta}\n{exit_line}"
    elif shape == 2:    # compacto
        text = f"{opener} {intro} {reason} {link} {cta}\n{exit_line}"
    else:               # motivo primeiro, apresentacao depois
        text = f"{opener} {reason}\n{link}\n{intro} {cta} {exit_line}"
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text).strip()
    return re.sub(r"\n{2,}$", "", text)


def enrich(lead, group, mockup_url, sender_name, variant=0):
    """Acrescenta ao registro do prospect os campos que a tela usa."""
    digits, mobile, why = phone_info(lead.get("contact_whatsapp") or lead.get("contact_phone"))
    score, flags = priority(lead, group, bool(mockup_url))
    out = dict(lead)
    out.update({
        "wa_digits": digits, "wa_mobile": mobile, "wa_phone_note": why,
        "wa_priority": score, "wa_flags": flags, "mockup_url": mockup_url or "",
        "suggested_message": build_message(lead, group, mockup_url, sender_name, variant),
        "display_name": clean_company_name(lead.get("company_name"), lead.get("website")),
    })
    return out
