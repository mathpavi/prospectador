"""M5: esboco para empresas SEM site. Sem site nao ha fotos nem textos para extrair, entao o esboco usa SO o que e verdade (nome, cidade, segmento,
telefone, e-mail, endereco e ano de abertura, vindos do cadastro da Receita) + ilustracao (marcada como tal) + servicos TIPICOS do segmento,
escritos por nos (sem IA, sem custo, sem inventar numeros, clientes, certificados ou capacidades). A faixa da proposta avisa "conteudo de exemplo".
"""
import re
import zlib

# segmento (nome normalizado do prospectador) -> perfil. 'frases' sao titulos; {cidade} entra sempre (detalhe concreto, nunca generico).
PROFILES = {
    "Metalúrgica": {"art": "estrutura", "accent": ["#2f5d8a", "#b4651f", "#4a5a3c"], "ocupacao": "Metalurgia",
                    "frases": ["Metalurgia e estruturas em <em>aço</em>, em {cidade}", "Peças e estruturas metálicas feitas em <em>{cidade}</em>", "Trabalho em <em>metal</em> sob projeto, em {cidade}"],
                    "servicos": ["Corte e dobra de chapas", "Soldagem", "Estruturas metálicas", "Usinagem de peças", "Manutenção industrial", "Projetos sob medida"]},
    "Usinagem": {"art": "engrenagem", "accent": ["#2f5d8a", "#8a3d2f", "#3b6b5a"], "ocupacao": "Usinagem",
                 "frases": ["Usinagem de <em>precisão</em> em {cidade}", "Peças usinadas, de protótipo a série, em <em>{cidade}</em>", "Torno, fresa e <em>ferramentaria</em> em {cidade}"],
                 "servicos": ["Torneamento", "Fresamento", "Peças sob desenho", "Manutenção de máquinas", "Ferramentaria", "Peças de reposição"]},
    "Caldeiraria / Soldagem": {"art": "engrenagem", "accent": ["#a14a1c", "#2f5d8a", "#5a4a3c"], "ocupacao": "Caldeiraria e soldagem",
                               "frases": ["Caldeiraria e <em>soldagem</em> em {cidade}", "Tanques, tubulações e estruturas soldadas em <em>{cidade}</em>", "Solda de <em>qualidade</em> para a indústria de {cidade}"],
                               "servicos": ["Caldeiraria média e leve", "Soldagem MIG, TIG e eletrodo", "Tanques e reservatórios", "Tubulações industriais", "Montagem e manutenção", "Reparos em geral"]},
    "Serralheria": {"art": "estrutura", "accent": ["#3a3f47", "#b4651f", "#2f5d8a"], "ocupacao": "Serralheria",
                    "frases": ["Serralheria sob medida em <em>{cidade}</em>", "Portões, grades e estruturas em {cidade}", "Do <em>projeto</em> à instalação, em {cidade}"],
                    "servicos": ["Portões e grades", "Corrimãos e escadas", "Coberturas e pergolados", "Estruturas metálicas", "Esquadrias de ferro", "Manutenção e reparos"]},
    "Vidraçaria": {"art": "esquadria", "accent": ["#2a7a8c", "#3a4a6a", "#4a6a5a"], "ocupacao": "Vidraçaria",
                   "frases": ["Vidros e <em>espelhos</em> sob medida em {cidade}", "Vidraçaria em <em>{cidade}</em>: do corte à instalação", "Vidro temperado, box e <em>fechamentos</em> em {cidade}"],
                   "servicos": ["Box de banheiro", "Vidro temperado", "Espelhos", "Fechamento de sacadas", "Portas e janelas de vidro", "Reposição e conserto"]},
    "Esquadrias de Alumínio": {"art": "esquadria", "accent": ["#3a4a6a", "#2a7a8c", "#6a4a3a"], "ocupacao": "Esquadrias de alumínio",
                               "frases": ["Esquadrias de <em>alumínio</em> em {cidade}", "Janelas, portas e fechamentos feitos para <em>{cidade}</em>", "Alumínio e vidro com <em>acabamento</em> em {cidade}"],
                               "servicos": ["Janelas de alumínio", "Portas e portões", "Fechamento de sacadas", "Divisórias e vitrines", "Box e fachadas", "Manutenção e reposição"]},
    "Marmoraria": {"art": "esquadria", "accent": ["#5a5048", "#8a6a3c", "#3a4a4a"], "ocupacao": "Marmoraria",
                   "frases": ["Mármore e <em>granito</em> sob medida em {cidade}", "Pias, bancadas e soleiras feitas em <em>{cidade}</em>", "Pedra natural com <em>acabamento</em> fino em {cidade}"],
                   "servicos": ["Bancadas e pias", "Soleiras e peitoris", "Lavatórios", "Escadas e revestimentos", "Mesas e tampos", "Lareiras e churrasqueiras"]},
    "Indústria de Plásticos": {"art": "cubos", "accent": ["#2f5d8a", "#c2511f", "#3b6b5a"], "ocupacao": "Indústria de plásticos",
                               "frases": ["Peças e produtos em <em>plástico</em>, feitos em {cidade}", "Injeção e transformação de plásticos em <em>{cidade}</em>", "Plástico <em>industrial</em> em {cidade}"],
                               "servicos": ["Injeção de plásticos", "Sopro e extrusão", "Peças técnicas", "Embalagens", "Ferramentaria de moldes", "Desenvolvimento de produtos"]},
    "Fábrica de Móveis": {"art": "cubos", "accent": ["#8a5a2b", "#3b5a4a", "#6a3a3a"], "ocupacao": "Fábrica de móveis",
                          "frases": ["Móveis feitos em <em>{cidade}</em>", "Móveis sob medida, do projeto à <em>entrega</em>, em {cidade}", "Marcenaria e móveis planejados em <em>{cidade}</em>"],
                          "servicos": ["Móveis sob medida", "Cozinhas e dormitórios", "Móveis corporativos", "Painéis e estantes", "Reformas e ajustes", "Projeto e instalação"]},
    "Indústria Têxtil": {"art": "cubos", "accent": ["#7a3a5a", "#2f5d8a", "#8a6a2b"], "ocupacao": "Indústria têxtil",
                         "frases": ["Confecção e produtos <em>têxteis</em> de {cidade}", "Tecidos e peças feitos em <em>{cidade}</em>", "Do tecido à <em>peça pronta</em>, em {cidade}"],
                         "servicos": ["Confecção sob encomenda", "Uniformes", "Peças em série", "Bordado e estampa", "Modelagem", "Acabamento"]},
    "Panificadora": {"art": "trigo", "accent": ["#a8662b", "#7a4a2b", "#b0822b"], "ocupacao": "Padaria",
                     "frases": ["Pão fresco, <em>todos os dias</em>, em {cidade}", "Padaria e confeitaria em <em>{cidade}</em>", "Do forno para a <em>mesa</em>, em {cidade}"],
                     "servicos": ["Pães frescos", "Bolos e tortas", "Salgados", "Café da manhã", "Encomendas", "Frios e lanches"]},
    "Serviços de Limpeza": {"art": "folha", "accent": ["#2a7a8c", "#3b7a4a", "#3a5a8a"], "ocupacao": "Serviços de limpeza",
                            "frases": ["Limpeza profissional em <em>{cidade}</em>", "Limpeza para empresas e residências em {cidade}", "Ambientes <em>limpos</em>, rotina tranquila, em {cidade}"],
                            "servicos": ["Limpeza comercial", "Limpeza residencial", "Pós-obra", "Higienização", "Conservação diária", "Serviços avulsos"]},
    "Distribuidora / Logística": {"art": "rota", "accent": ["#2f5d8a", "#c2511f", "#3a4a6a"], "ocupacao": "Transporte e logística",
                                  "frases": ["Transporte e <em>logística</em> saindo de {cidade}", "Cargas do ponto A ao ponto B, com base em <em>{cidade}</em>", "Entregas com <em>rota</em> e responsabilidade, em {cidade}"],
                                  "servicos": ["Transporte de cargas", "Entregas regionais", "Carga fracionada", "Armazenagem", "Distribuição", "Cotação pelo WhatsApp"]},
    "Advogado": {"art": "balanca", "accent": ["#3a2f5a", "#2f4a3c", "#5a3a2f"], "ocupacao": "Advocacia",
                 "frases": ["Advocacia em <em>{cidade}</em>", "Orientação jurídica clara, em {cidade}", "Atendimento <em>jurídico</em> próximo, em {cidade}"],
                 "servicos": ["Direito civil", "Direito empresarial", "Direito do trabalho", "Contratos", "Consultoria preventiva", "Atendimento por agendamento"]},
    "Segurança Eletrônica": {"art": "estrutura", "accent": ["#2f5d8a", "#1f4a3c", "#5a2f3a"], "ocupacao": "Segurança eletrônica",
                             "frases": ["Segurança <em>eletrônica</em> em {cidade}", "Câmeras, alarmes e cercas, instalados em <em>{cidade}</em>", "Proteção para casa e empresa em {cidade}"],
                             "servicos": ["Câmeras de segurança", "Alarmes", "Cerca elétrica", "Controle de acesso", "Interfonia", "Manutenção e suporte"]},
    "Clínica de Estética": {"art": "folha", "accent": ["#8a4a5a", "#4a6a5a", "#7a5a8a"], "ocupacao": "Estética",
                            "frases": ["Cuidado e <em>bem-estar</em> em {cidade}", "Estética com atendimento <em>individual</em>, em {cidade}", "Sua pele e seu <em>bem-estar</em> em {cidade}"],
                            "servicos": ["Limpeza de pele", "Tratamentos faciais", "Tratamentos corporais", "Depilação", "Massagens", "Avaliação inicial"]},
}
DEFAULT = PROFILES["Metalúrgica"]


def profile_for(segment):
    return PROFILES.get(segment) or next((v for k, v in PROFILES.items() if k.lower() in (segment or "").lower()), DEFAULT)


def opening_year(notes):
    m = re.search(r"aberta em (\d{4})\d{4}", notes or "")
    return m.group(1) if m else ""


def _pick(options, key):
    return options[zlib.crc32(key.encode("utf-8")) % len(options)]


def build_slots(prospect):
    """Slots do template para uma empresa sem site. So fatos reais + servicos tipicos do segmento."""
    seg = prospect.get("segment") or ""
    pf = profile_for(seg)
    name = (prospect.get("company_name") or "").strip()
    region = prospect.get("region") or ""
    city, uf = (region.split(" - ") + [""])[:2] if " - " in region else (region, "")
    city = city.strip() or "sua cidade"
    key = f"{name}|{region}"
    year = opening_year(prospect.get("notes"))
    phones = [x for x in (prospect.get("contact_whatsapp"), prospect.get("contact_phone")) if x]
    phones = list(dict.fromkeys(phones))[:2]
    title = _pick(pf["frases"], key).format(cidade=city)
    facts = ([{"k": "Atividade desde", "v": year}] if year else []) + [{"k": "Cidade", "v": f"{city}/{uf}" if uf else city}]
    if phones:
        facts.append({"k": "Contato", "v": phones[0]})
    about = [f"A {name} é uma empresa de {city}{('/' + uf) if uf else ''}, no segmento de {pf['ocupacao'].lower()}" + (f", em atividade desde {year}." if year else ".")]
    about.append("Esta página é um exemplo de como a empresa pode se apresentar na internet: os serviços, textos e fotos reais entram com as informações e o material da própria empresa.")
    return {
        "brand_name": name, "short_name": name, "accent": _pick(pf["accent"], key + "|cor"), "art": pf["art"], "sample_content": True,
        "eyebrow": f"{pf['ocupacao']} · {city}" + (f"/{uf}" if uf else ""),
        "hero_title_html": title, "hero_sub": "Conheça a empresa e peça um orçamento direto pelo WhatsApp.", "hero_alt": "",
        "services_title": "O que a empresa pode oferecer", "services_intro": "Exemplos de serviços do segmento, para ajustar com a empresa.",
        "services": [{"name": x, "desc": None} for x in pf["servicos"]], "process": [],
        "about_title": f"Sobre a {name}", "about": about, "facts": facts, "contact_title": "Vamos conversar sobre o seu projeto?",
        "phones": phones, "address": (re.search(r"CEP", prospect.get("notes") or "") and "") or "", "city_uf": f"{city}/{uf}" if uf else city,
        "specbar": [x for x in [f"{city}/{uf}" if uf else city, phones[0] if phones else None] if x],
        "images": [], "logo_file": None,
    }
