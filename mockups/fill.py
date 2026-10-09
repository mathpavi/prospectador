"""Preenche os slots de TEXTO de um template a partir do conteudo extraido do site.

Regra: o LLM escreve so copy. Fatos (telefone, endereco, logo, imagens, cor) vem do extrator, nunca do modelo.
O texto gerado e validado contra o que o site realmente diz (numeros, clichês, tamanho).

Chaves via variavel de ambiente (nunca em arquivo):  ANTHROPIC_API_KEY  |  GEMINI_API_KEY
Uso:  python fill.py <extracted.json> --provider anthropic|gemini [--out slots.json]
"""
import argparse
import json
import os
import re
import sys

import requests

MODELS = {
    "anthropic": {"id": "claude-haiku-4-5-20251001", "in": 1.00, "out": 5.00},     # US$/MTok (tabela oficial)
    "gemini": {"id": "gemini-2.5-flash-lite", "in": 0.10, "out": 0.40},
}
# US$/MTok (tabela oficial do Google). Se a chave nao tem acesso a um modelo (404), tenta o proximo da lista.
GEMINI_PRICES = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}
GEMINI_CHAIN = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]

BANNED = [r"transforme (o )?seu neg[oó]cio", r"revolucion", r"solu[cç][aã]o completa", r"l[ií]der de mercado",
          r"refer[eê]ncia (no|em) (mercado|setor)", r"de ponta", r"inova[cç][aã]o disruptiva",
          # vocabulario de folheto/IA: marca o texto como generico
          r"excel[eê]ncia", r"compromisso com a qualidade", r"qualidade e (seriedade|confian[cç]a)", r"solu[cç][oõ]es (completas|personalizadas|inovadoras|sob medida)",
          r"parceir[oa] (ideal|de confian[cç]a)", r"tradi[cç][aã]o e inova[cç][aã]o", r"alto padr[aã]o", r"mais do que", r"jornada", r"ecossistema",
          r"potencialize", r"eleve (o|a|seu|sua)", r"da melhor forma", r"cuidado em cada detalhe", r"pensado para voc[eê]", r"seu sucesso [eé] o nosso"]

SYSTEM = """Voce escreve o texto de um esboco de site institucional em portugues do Brasil para uma empresa REAL.
Regras inegociaveis:
1. Use APENAS informacoes presentes nos dados fornecidos. Se algo nao estiver nos dados, nao escreva. Nunca invente anos de mercado, numeros, certificacoes, clientes, premios ou capacidades.
2. Tom: claro, tecnico, direto, humano. Sem hype. Proibido: "transforme seu negocio", "revolucione", "solucao completa", "lider de mercado", "referencia no mercado", "de ponta".
3. A hero precisa ser ESPECIFICA desta empresa (o que faz, para quem, onde), nao poderia servir a qualquer concorrente. Titulo com no maximo 9 palavras. Pode destacar UMA palavra com <em>...</em>.
4. Servicos: use os nomes que a empresa ja usa. No maximo 6. Descricao so quando os dados trazem uma frase real sobre aquele servico; senao omita "desc".
5. Textos curtos. Sem emojis.
VOZ (evite texto de folheto, o tipo de frase que serviria a qualquer concorrente):
6. O titulo da hero precisa de UM detalhe concreto que so esta empresa tem nos dados: o produto especifico, o material, o publico, a cidade ou a regiao. Ruim: "Solucoes em aco para a industria". Bom: "Tanques de inox para vinho, feitos na Serra Gaucha".
7. Use o vocabulario do proprio site (termos tecnicos, nomes de produtos e de linhas). Nunca troque o nome que a empresa usa por um sinonimo mais "bonito".
8. Frases curtas, verbo concreto, sujeito claro. Proibido: listas de tres adjetivos ("rapido, seguro e eficiente"), "mais do que", "jornada", "excelencia", "compromisso com a qualidade", "solucoes sob medida", "parceiro de confianca", "alto padrao".
9. Se os dados forem poucos, escreva MENOS. Nao complete com generalidades para encher espaco.
10. O texto "sobre" deve soar como a empresa falando de si (primeira pessoa do plural, "fazemos", "atendemos") apenas se o site tambem fala assim; senao use terceira pessoa direta.
Responda SOMENTE um objeto JSON valido, sem markdown, com exatamente estas chaves:
{"eyebrow": str (segmento + cidade/UF), "hero_title_html": str, "hero_sub": str (max 30 palavras), "hero_alt": str,
 "services_title": str (max 6 palavras), "services_intro": str|null,
 "services": [{"name": str, "desc": str|null}],
 "process": [str]|[] (so se os dados descreverem etapas),
 "about_title": str (max 7 palavras), "about": [str] (1 a 2 paragrafos curtos, parafraseando o texto da propria empresa),
 "facts": [{"k": str, "v": str}] (max 3, somente fatos presentes nos dados),
 "contact_title": str (pergunta curta e direta),
 "how": [str, str, str] (3 passos curtos de como o cliente contrata, do primeiro contato ao servico; genericos, sem prazos),
 "faq": [{"q": str, "a": str}] (3 a 4 perguntas que clientes DESTE segmento costumam ter, com respostas educativas e prudentes;
        pode usar conhecimento geral do segmento, mas SEM numeros, prazos, precos, garantias, certificacoes ou promessas sobre a empresa)}"""


def build_user(prospect, ex):
    keep = {
        "empresa": prospect.get("company_name"), "segmento": prospect.get("segment"), "regiao": prospect.get("region"),
        "titulo_do_site": ex.get("title"), "descricao": ex.get("meta_description"), "h1": ex.get("h1"), "h2": ex.get("h2"),
        "itens_de_menu": ex.get("nav_items"), "servicos_detectados": ex.get("services"),
        "fundacao": ex.get("founded_hint"), "endereco": ex["contacts"].get("address"),
        "texto_do_site": ex.get("text_sample"),
    }
    return "DADOS DA EMPRESA:\n" + json.dumps(keep, ensure_ascii=False)


def call_anthropic(user):
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODELS["anthropic"]["id"], "max_tokens": 2200, "temperature": 0.4, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]})
    r.raise_for_status()
    j = r.json()
    return j["content"][0]["text"], j["usage"]["input_tokens"], j["usage"]["output_tokens"], MODELS["anthropic"]["id"]


def _db_setting(key):
    """Le uma configuracao do banco do app (somente leitura). Na VPS a chave do Gemini mora aqui."""
    import sqlite3
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = os.environ.get("DB_PATH") or os.path.join(os.environ.get("DATA_DIR", here), "prospector.db")
    try:
        con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
        row = con.execute("select value from settings where key=?", (key,)).fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception:  # noqa: BLE001
        return ""


def call_gemini(user):
    # chave: variavel de ambiente (teste local) ou configuracao do app (VPS). Nunca e impressa.
    api_key = os.environ.get("GEMINI_API_KEY") or _db_setting("gemini_api_key")
    if not api_key:
        sys.exit("Sem chave do Gemini: defina GEMINI_API_KEY ou salve a chave nas configuracoes do app.")
    # ordem de tentativa: modelo escolhido (env/config do app) e depois a lista padrao; pula os que a chave nao acessa (404)
    chosen = os.environ.get("FILL_GEMINI_MODEL") or _db_setting("gemini_model")
    chain = list(dict.fromkeys(([chosen] if chosen else []) + GEMINI_CHAIN))
    last = ""
    for model_id in chain:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
        r = requests.post(url, timeout=90, headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                          json={"systemInstruction": {"parts": [{"text": SYSTEM}]},
                                "contents": [{"role": "user", "parts": [{"text": user}]}],
                                "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json", "maxOutputTokens": 4000}})
        if r.status_code in (404, 403, 429, 500, 502, 503, 504):
            last = f"{model_id}: HTTP {r.status_code}"
            print(f"modelo {model_id} indisponivel para esta chave (HTTP {r.status_code}); tentando o proximo...")
            continue
        if r.status_code != 200:
            sys.exit(f"Gemini respondeu HTTP {r.status_code} no modelo {model_id}: {r.text[:300]}")
        j = r.json()
        u = j.get("usageMetadata", {})
        print(f"modelo usado: {model_id}")
        return (j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", 0),
                u.get("candidatesTokenCount", 0), model_id)
    sys.exit(f"Nenhum modelo Gemini acessivel com esta chave (ultimo erro: {last}). Confira a chave no AI Studio.")


def parse_json(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    return json.loads(txt)


def gemini_json(parts, temperature=0.2, max_tokens=1200):
    """Chamada generica ao Gemini (texto + IMAGENS) que devolve JSON. Usada pelo juiz do esboco.
    parts = [{"text": "..."}, {"inline_data": {"mime_type": "image/jpeg", "data": "<base64>"}}, ...]
    Devolve (dados, custo_usd, modelo). Levanta RuntimeError em qualquer falha (quem chama decide; o juiz falha FECHADO)."""
    api_key = os.environ.get("GEMINI_API_KEY") or _db_setting("gemini_api_key")
    if not api_key:
        raise RuntimeError("sem chave do Gemini")
    chosen = os.environ.get("FILL_GEMINI_MODEL") or _db_setting("gemini_model")
    chain = list(dict.fromkeys(([chosen] if chosen else []) + GEMINI_CHAIN))
    last = ""
    for model_id in chain:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
        r = requests.post(url, timeout=120, headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                          json={"contents": [{"role": "user", "parts": parts}],
                                "generationConfig": {"temperature": temperature, "responseMimeType": "application/json", "maxOutputTokens": max_tokens}})
        if r.status_code in (404, 403, 429, 500, 502, 503, 504):
            last = f"{model_id}: HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
        j = r.json()
        u = j.get("usageMetadata", {})
        p_in, p_out = GEMINI_PRICES.get(model_id, (0.3, 2.5))
        cost = u.get("promptTokenCount", 0) * p_in / 1e6 + u.get("candidatesTokenCount", 0) * p_out / 1e6
        try:
            return parse_json(j["candidates"][0]["content"]["parts"][0]["text"]), cost, model_id
        except (ValueError, KeyError, IndexError) as e:
            raise RuntimeError(f"resposta fora do formato ({type(e).__name__})") from e
    raise RuntimeError(f"nenhum modelo Gemini acessivel ({last})")


def source_blob(ex, prospect):
    parts = [ex.get("text_sample", ""), ex.get("title", ""), ex.get("meta_description", ""), " ".join(ex.get("h1", [])),
             " ".join(ex.get("h2", [])), " ".join(ex.get("nav_items", [])), ex["contacts"].get("address", ""),
             str(ex.get("founded_hint", "")), prospect.get("company_name", ""), prospect.get("region", ""), prospect.get("segment", "")]
    return " ".join(parts).lower()


def validate(copy, ex, prospect):
    """Devolve (copy_limpo, problemas). Problemas 'fatais' mandam o esboco para revisao manual."""
    problems, fatal = [], []
    src = source_blob(ex, prospect)
    # so campos de copy escritos pelo modelo (fatos como telefone/arquivos nao passam por aqui)
    copy_keys = ("eyebrow", "hero_title_html", "hero_sub", "hero_alt", "services_title", "services_intro", "services",
                 "process", "about_title", "about", "facts", "contact_title", "how", "faq")
    flat = json.dumps({k: copy.get(k) for k in copy_keys}, ensure_ascii=False).lower()

    for pat in BANNED:
        if re.search(pat, flat):
            problems.append(f"expressao proibida: /{pat}/")
    # numeros que nao existem na fonte (anos, quantidades) = possivel invencao
    for num in set(re.findall(r"\d[\d.,]*", re.sub(r"<[^>]+>", " ", flat))):
        if num.strip(".,") and num.strip(".,") not in src:
            fatal.append(f"numero '{num}' nao consta no site")
    words = len(re.sub(r"<[^>]+>", "", copy.get("hero_title_html", "")).split())
    if not 2 <= words <= 10:
        fatal.append(f"titulo da hero com {words} palavras")
    if len(copy.get("services", [])) < 3:
        fatal.append("menos de 3 servicos")
    if not copy.get("about"):
        problems.append("sem texto sobre a empresa")
    # remove desc de servico com palavras inventadas demais (heuristica: >60% das palavras fora da fonte)
    for sv in copy.get("services", []):
        d = sv.get("desc")
        if d:
            ws = [w for w in re.findall(r"[a-zà-ú]{5,}", d.lower())]
            if ws and sum(w not in src for w in ws) / len(ws) > 0.6:
                sv["desc"] = None
                problems.append(f"desc removida em '{sv.get('name')}'")
    return copy, problems, fatal


def pick_hero(prospect, slots, img_dir, call=None):
    """Foto principal escolhida por IA de visao (barata): olha ate 6 fotos e ordena da melhor para a pior como foto de abertura.
    Evita logos, banners com texto, mockups de notebook/celular, imagens de banco genericas e texturas. Devolve (ordem, custo)
    ou (None, 0) se nao conseguir (quem chama mantem a ordenacao por qualidade tecnica)."""
    import base64
    import io
    names = [n for n in slots.get("images", []) if n][:6]
    if not names:
        return None, 0.0
    call = call or gemini_json
    try:
        from PIL import Image
        parts = [{"text": "Estas sao " + str(len(names)) + " imagens numeradas (1 a " + str(len(names)) + ") do site de uma empresa do segmento '" + str(prospect.get("segment") or "") + "'. "
                  "Ordene da MELHOR para a PIOR como foto principal de abertura do novo site. Prefira fotos reais da empresa (fabrica, produto, equipe, fachada, trabalho feito). "
                  "Evite logos, banners com texto, ilustracoes, mockups de notebook/celular, imagens de banco genericas e texturas. "
                  'Informe tambem "relevante": true somente se a PRIMEIRA da ordem mostra claramente o produto, o servico, a obra, a fabrica ou a fachada desta empresa; '
                  'false se for generica (apertos de mao, equipe sorrindo, pessoas em escritorio, fundo abstrato) ou sem relacao com o que ela vende. '
                  'Responda apenas JSON: {"ordem": [numeros], "relevante": true|false}'}]
        for i, n in enumerate(names, 1):
            im = Image.open(os.path.join(img_dir, n)).convert("RGB")
            im.thumbnail((512, 512))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=70)
            parts.append({"text": "Imagem " + str(i) + ":"})
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
        data, cost, _ = call(parts, temperature=0.1, max_tokens=200)
        order = [int(x) - 1 for x in data.get("ordem", []) if str(x).isdigit() and 1 <= int(x) <= len(names)]
        order = list(dict.fromkeys(order))
        if not order:
            return None, cost
        if data.get("relevante") is False:
            slots["_hero_relevant"] = False
        ordered = [names[i] for i in order] + [n for i, n in enumerate(names) if i not in order]
        return ordered + [n for n in slots.get("images", []) if n not in ordered], cost
    except Exception:  # noqa: BLE001
        return None, 0.0


def brand_name(prospect, ex):
    """Nome da marca para o esboco: cadastro limpo; se for lixo ('Pagina inicial', 'Sobre') usa o nome do site/dominio."""
    raw = prospect.get("company_name") or ""
    if "  " in raw.strip():                       # 'Plastibras  de Plasticos': pedaco cortado por limpeza antiga
        raw = raw.strip().split("  ")[0]
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import whatsapp_msg as wm
        if wm.is_junk_name(raw):
            site = re.split(r"\s*[|\-–—·]\s*", ex.get("site_name") or "")[0].strip()
            raw = site if site and not wm.is_junk_name(site) else (wm.brand_from_domain(prospect.get("website") or ex.get("url")) or raw)
    except Exception:  # noqa: BLE001
        pass
    return re.sub(r"\s+", " ", raw).strip() or ex.get("site_name") or ""


def assemble(copy, ex, prospect):
    """Junta copy do LLM + fatos do extrator (que nunca passam pelo modelo)."""
    c = ex["contacts"]
    uf = (prospect.get("region") or "").split()[-1] if prospect.get("region") else ""
    slots = dict(copy)
    # cidade/UF: ultima parte do 'eyebrow' (separado por · – — ou " - "); sem isso, a regiao do cadastro
    parts = [p for p in re.split(r"\s*[·–—]\s*|\s+-\s+", slots.get("eyebrow", "")) if p.strip()]
    city_uf = parts[-1].strip() if len(parts) > 1 else (prospect.get("region") or "")
    if len(parts) > 1 and re.fullmatch(r"[A-Z]{2}", city_uf):      # "Metalurgica em Caxias do Sul - RS" -> "Caxias do Sul / RS"
        city_uf = f"{parts[-2].split(' em ')[-1].strip()} / {city_uf}"
    # a IA nao enxerga as imagens: o texto alternativo vem do proprio site, ou e so o nome da empresa (sem inventar descricao)
    first_alt = next((i.get("alt") for i in ex.get("images", []) if i.get("file") and i.get("alt")), "")
    slots.update({
        "brand_name": brand_name(prospect, ex),
        "short_name": brand_name(prospect, ex),
        "accent": ex["colors"].get("accent"),
        "specbar": [x for x in [uf and slots.get("eyebrow", "").split("·")[-1].strip(), (c.get("phones") or [None])[0]] if x],
        "phones": c.get("phones", [])[:2],
        "address": c.get("address", ""),
        "city_uf": city_uf,
        "hero_alt": first_alt or (prospect.get("company_name") or ex.get("site_name") or ""),
        "images": [i["file"] for i in ex.get("images", []) if i.get("file")][:3],
        "logo_file": ex.get("logo"),
    })
    return slots


def fill(prospect, ex, provider="anthropic"):
    user = build_user(prospect, ex)
    txt, tin, tout, model_id = (call_anthropic if provider == "anthropic" else call_gemini)(user)
    p_in, p_out = GEMINI_PRICES.get(model_id, (MODELS[provider]["in"], MODELS[provider]["out"])) if provider == "gemini" \
        else (MODELS[provider]["in"], MODELS[provider]["out"])
    cost = tin * p_in / 1e6 + tout * p_out / 1e6
    usage = {"provider": provider, "model": model_id, "in": tin, "out": tout, "usd": round(cost, 6)}
    try:
        copy = parse_json(txt)
    except ValueError:   # resposta fora do formato JSON: nao quebra o fluxo, manda para revisao
        return {"slots": {}, "problems": [], "fatal": ["a IA devolveu uma resposta fora do formato esperado"], "usage": usage,
                "raw": txt[:300]}
    copy, problems, fatal = validate(copy, ex, prospect)
    # texto com cara de folheto/IA (2+ expressoes de BANNED): pede UMA reescrita especifica, apontando o que sair
    slop = [x for x in problems if x.startswith("expressao proibida")]
    if len(slop) >= 2:
        try:
            nl = chr(10) * 2
            feedback = (user + nl + "SEU TEXTO ANTERIOR tinha frases de folheto (" + "; ".join(slop[:6]) + "). Reescreva TUDO sem essas expressoes, "
                        "com um detalhe concreto desta empresa no titulo e vocabulario do proprio site.")
            txt2, tin2, tout2, model2 = (call_anthropic if provider == "anthropic" else call_gemini)(feedback)
            copy2 = parse_json(txt2)
            copy2, problems2, fatal2 = validate(copy2, ex, prospect)
            if len([x for x in problems2 if x.startswith("expressao proibida")]) < len(slop) and not fatal2:
                copy, problems, fatal = copy2, problems2, fatal2
                usage["retry"] = True
                usage["usd"] = round(usage.get("usd", 0) + tin2 * 0.3 / 1e6 + tout2 * 2.5 / 1e6, 6)
        except Exception:  # noqa: BLE001
            pass
    return {"slots": assemble(copy, ex, prospect), "problems": problems, "fatal": fatal, "usage": usage}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("extracted")
    ap.add_argument("--provider", choices=list(MODELS), required=True)
    ap.add_argument("--company", default="")
    ap.add_argument("--segment", default="metalúrgica")
    ap.add_argument("--region", default="")
    ap.add_argument("--out")
    a = ap.parse_args()
    ex = json.load(open(a.extracted, encoding="utf-8"))
    res = fill({"company_name": a.company or ex.get("site_name"), "segment": a.segment, "region": a.region}, ex, a.provider)
    print(json.dumps({k: v for k, v in res.items() if k != "slots"}, ensure_ascii=False, indent=1))
    if a.out:
        json.dump(res["slots"], open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
