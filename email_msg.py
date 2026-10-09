"""E4 do PLANO_PROSPECTADOR: e-mail HONESTO e VARIADO.

- So afirma o que e verdade: o que foi visto (o site foi aberto), problemas REAIS (HTTPS, celular, rodape velho) e o que e oferta.
  Sem elogio inventado ("qualidade e seriedade do trabalho de vocês") e sem prometer estudo que nao existe.
- O espaco do esboco e um marcador ({{ESBOCO}}) resolvido NO ENVIO: vira o link se o esboco existir, ou uma oferta honesta se nao.
- Montado por pecas e formatos diferentes, estavel por prospect (mesmo lead = mesmo texto), para nao parecer e-mail em massa.
"""
import json
import random
import re
import zlib
from urllib.parse import urlparse

import whatsapp_msg as wm

ESBOCO_TOKEN = "{{ESBOCO}}"
PRECO_TOKEN = "{{PRECO}}"
LEGACY_CLAIMS = re.compile(r"fiz esse material especificamente|elaborei uma proposta visual|"
                           r"qualidade e a seriedade do trabalho|me chamou a atenção a qualidade|gostei muito do trabalho de vocês", re.I)


def real_issue(detected_issues, year_now=None):
    """Uma observacao REAL e compreensivel pelo dono (ou None). Problemas cosmeticos (favicon, previa do WhatsApp, H1...) sao ignorados."""
    try:
        issues = json.loads(detected_issues) if isinstance(detected_issues, str) else (detected_issues or [])
    except Exception:  # noqa: BLE001
        issues = []
    text = " | ".join(str(i) for i in issues).lower()
    if "inseguro" in text or "http)" in text:
        return "ele aparece como “não seguro” no navegador (sem HTTPS)"
    if "viewport" in text or "responsivo" in text:
        return "no celular ele não se adapta à tela"
    m = re.search(r"copyright desatualizado \((\d{4})\)", text)
    if m:
        return f"o rodapé ainda mostra © {m.group(1)}"
    return None


def is_legacy_body(body):
    """Corpo gerado pelo modelo antigo, que promete um 'estudo visual' que nao existia / elogios sem base."""
    return bool(LEGACY_CLAIMS.search(body or ""))


def _rng(prospect, salt=""):
    return random.Random(zlib.crc32(f"{prospect.get('id')}|{prospect.get('company_name')}|{salt}".encode("utf-8")))


def build_email(prospect, sender):
    """(assunto, corpo). `sender` = {'name','whatsapp','portfolio'}. O corpo contem {{ESBOCO}} (resolvido no envio)."""
    rng = _rng(prospect)
    pick = lambda opts: opts[rng.randrange(len(opts))]  # noqa: E731
    company = wm.clean_company_name(prospect.get("company_name"), prospect.get("website"))
    sname = wm.first_name(sender.get("name")) or "Matheus"
    full = (sender.get("name") or "Matheus Paviani").strip()
    wa = (sender.get("whatsapp") or "").strip()
    portfolio = (sender.get("portfolio") or "").strip()
    seg = (prospect.get("segment") or "").strip().lower() or "seu segmento"
    pn = wm.partner_first_name(prospect.get("socios"))
    own_site = wm.has_own_site(prospect)
    site = wm._domain(prospect.get("website"))
    short = company if len(company) <= 34 else company[:34].rsplit(" ", 1)[0]

    subject = pick([f"Uma ideia de site para a {short}", f"Sobre o site da {short}", f"{short}: ideia para o site",
                    f"Site da {short}", f"Pergunta rápida sobre o site da {short}"]) if own_site else \
        pick([f"Um site para a {short}?", f"A {short} na internet", f"Ideia de site para a {short}"])

    greeting = pick([f"Olá, {pn}," if pn else "Olá,", f"Olá, {pn}, tudo bem?" if pn else "Olá, tudo bem?", f"Oi, {pn}, tudo bem?" if pn else "Oi, tudo bem?"])
    intro = pick([f"Meu nome é {sname}, faço sites para empresas do segmento de {seg}.",
                  f"Sou {sname} e trabalho com criação de sites para empresas de {seg}.",
                  f"Me chamo {sname} e crio sites para empresas do setor de {seg}."])
    if own_site:
        obs = real_issue(prospect.get("detected_issues"))
        look = pick([f"Ao abrir o site {site}, reparei que {obs}.", f"Estive no site {site} e notei que {obs}.", f"Visitei o site {site}: {obs}."]) if obs \
            else pick([f"Dei uma olhada no site {site}.", f"Estive no site {site} da {company}.", f"Acessei o site {site}."])
    else:
        look = pick([f"Procurei a {company} na internet e não encontrei um site próprio.",
                     f"Não achei um site próprio da {company}, apenas listagens e perfis.",
                     f"Pesquisei a {company} e não encontrei um site próprio."])
    value = pick(["Trabalho com sites rápidos no celular e com pedido de orçamento direto pelo WhatsApp.",
                  "Faço sites leves, que abrem rápido no celular e facilitam o contato dos clientes pelo WhatsApp.",
                  "O foco é um site claro, rápido no celular e com orçamento a um toque."])
    contact = f" Meu WhatsApp é {wa}." if wa else ""
    cta = pick([f"Se fizer sentido, posso te explicar por aqui ou numa ligação rápida.{contact}",
                f"Se tiver interesse, é só responder este e-mail" + (f" ou me chamar no WhatsApp {wa}." if wa else "."),
                f"Posso te apresentar a ideia em 10 minutos? Responda aqui" + (f" ou chame no WhatsApp {wa}." if wa else ".")])
    exit_line = pick(["Se não for o momento, sem problema: é só me avisar.", "Se preferir não receber mais mensagens, é só responder SAIR.", ""])
    signoff = pick(["Abraço,", "Um abraço,", "Atenciosamente,", "Obrigado pela atenção,"])
    sig = full + (f"\nPortfólio: {portfolio}" if portfolio and rng.random() < 0.6 else "")

    shape = rng.randrange(3)
    if shape == 0:
        blocks = [greeting, f"{intro} {look}", ESBOCO_TOKEN, value, PRECO_TOKEN, f"{cta} {exit_line}".strip(), f"{signoff}\n{sig}"]
    elif shape == 1:
        blocks = [greeting, look, intro, ESBOCO_TOKEN, f"{value}", PRECO_TOKEN, cta, exit_line, f"{signoff}\n{sig}"]
    else:
        blocks = [greeting, f"{look} {intro}", f"{value}", ESBOCO_TOKEN, PRECO_TOKEN, cta, f"{exit_line}\n\n{signoff}\n{sig}" if exit_line else f"{signoff}\n{sig}"]
    body = "\n\n".join(b for b in blocks if b)
    return subject, body


def esboco_paragraph(prospect, url, days=21):
    """O que entra no lugar de {{ESBOCO}} NO ENVIO: o link (esboco existe) ou uma oferta honesta (nao existe)."""
    rng = _rng(prospect, "esboco")
    pick = lambda opts: opts[rng.randrange(len(opts))]  # noqa: E731
    company = wm.clean_company_name(prospect.get("company_name"), prospect.get("website"))
    if url and not wm.has_own_site(prospect):
        return pick([
            f"Para você visualizar, montei um esboço de como o site da {company} poderia ficar:\n{url}\n(São textos e ilustrações de exemplo: o site de verdade leva as informações e as fotos da empresa. Não está publicado e fica disponível por {days} dias.)",
            f"Preparei um esboço de como a {company} poderia aparecer na internet, sem compromisso:\n{url}\n(Conteúdo de exemplo, só para dar uma ideia; no site real entram as fotos e os dados da empresa. Fica no ar por {days} dias.)",
        ])
    if url:
        return pick([
            f"Para facilitar a conversa, montei um esboço de como o site da {company} poderia ficar:\n{url}\n(É apenas um estudo visual, não é um site publicado, e fica disponível por {days} dias.)",
            f"Preparei um esboço de como poderia ser o novo site da {company}. Pode ver aqui, sem compromisso:\n{url}\n(Estudo visual: não está publicado e sai do ar em {days} dias.)",
            f"Aproveitei para montar um esboço visual, só para você ter uma ideia do que dá para fazer:\n{url}",
        ])
    return pick([
        f"Desenvolvi um estudo visual de como o site da {company} poderia ficar. Se quiser, te envio, sem compromisso.",
        f"Desenvolvi um estudo visual do novo site da {company}, só para você ter uma ideia. Posso te mostrar, sem compromisso?",
        f"Desenvolvi um estudo visual para a {company}. Se fizer sentido, te envio por aqui mesmo.",
    ])


def finalize(body, paragraph):
    """Troca o marcador pelo paragrafo e arruma as linhas em branco."""
    out = (body or "").replace(ESBOCO_TOKEN, paragraph or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _brl(v):
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        return str(v)
    return "R$ " + f"{n:,.0f}".replace(",", ".")


def price_line(get_setting, rng=None):
    """Oferta direta com PRECO na primeira mensagem (planos Essencial e Assinatura). Valores vem das configuracoes (price_*)."""
    setup, monthly, sub = get_setting("price_setup", "960"), get_setting("price_monthly", "55"), get_setting("price_subscription", "149")
    opts = [f"Se preferir algo direto: site pronto a partir de {_brl(setup)} + {_brl(monthly)}/mês (hospedagem, domínio e suporte), ou {_brl(sub)}/mês sem entrada.",
            f"Valores: a partir de {_brl(setup)} + {_brl(monthly)}/mês com hospedagem e suporte inclusos, ou {_brl(sub)}/mês sem pagar nada na entrada.",
            f"Para ficar claro desde já: o site sai a partir de {_brl(setup)} + {_brl(monthly)}/mês, ou {_brl(sub)}/mês sem entrada."]
    return opts[rng.randrange(len(opts))] if rng else opts[0]


def build_consultive(prospect, sender, custom_from="2500"):
    """Faixa PERSONALIZADA: e-mail curto e consultivo, sem esboco, apontando um problema REAL do site e convidando para uma conversa."""
    rng = _rng(prospect, "consultivo")
    pick = lambda opts: opts[rng.randrange(len(opts))]  # noqa: E731
    company = wm.clean_company_name(prospect.get("company_name"), prospect.get("website"))
    sname = wm.first_name(sender.get("name")) or "Matheus"
    full = (sender.get("name") or "Matheus Paviani").strip()
    wa = (sender.get("whatsapp") or "").strip()
    portfolio = (sender.get("portfolio") or "").strip()
    pn = wm.partner_first_name(prospect.get("socios"))
    seg = (prospect.get("segment") or "").strip().lower() or "seu segmento"
    site = wm._domain(prospect.get("website"))
    obs = real_issue(prospect.get("detected_issues"))
    subject = pick([f"Sobre o site da {company}", f"{company}: uma ideia para o site", f"Pergunta sobre o site da {company}"])
    greeting = pick([f"Olá, {pn}," if pn else "Olá,", f"Olá, {pn}, tudo bem?" if pn else "Olá, tudo bem?"])
    look = pick([f"Estive no site {site} e notei que {obs}.", f"Ao abrir o site {site}, reparei que {obs}."]) if obs else f"Dei uma olhada no site {site}."
    intro = pick([f"Sou {sname} e desenvolvo sites sob medida para empresas do segmento de {seg}.", f"Meu nome é {sname}: projeto e desenvolvo sites sob medida para empresas de {seg}."])
    offer = pick([f"Faço projetos personalizados, pensados para o jeito de vender da {company}, a partir de {_brl(custom_from)}.",
                  f"Trabalho com projetos sob medida (identidade da {company}, foco em gerar contatos), a partir de {_brl(custom_from)}."])
    cta = pick([f"Posso te mostrar em 15 minutos o que eu faria no site da {company}?" + (f" Responda aqui ou me chame no WhatsApp {wa}." if wa else " Responda aqui."),
                f"Se fizer sentido, marcamos uma conversa rápida para eu apresentar a ideia." + (f" Meu WhatsApp é {wa}." if wa else "")])
    exit_line = "Se não for o momento, sem problema: é só me avisar."
    sig = full + (f"\nPortfólio: {portfolio}" if portfolio else "")
    body = "\n\n".join([greeting, f"{look} {intro}", offer, cta, exit_line, f"{pick(['Abraço,', 'Atenciosamente,'])}\n{sig}"])
    return subject, body


def finalize_all(body, esboco_paragraph, price):
    """Resolve os marcadores {{ESBOCO}} e {{PRECO}} e arruma as linhas em branco."""
    out = (body or "").replace(ESBOCO_TOKEN, esboco_paragraph or "").replace(PRECO_TOKEN, price or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()
