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

BANNED = [r"transforme (o )?seu neg[oó]cio", r"revolucion", r"solu[cç][aã]o completa", r"l[ií]der de mercado",
          r"refer[eê]ncia (no|em) (mercado|setor)", r"de ponta", r"inova[cç][aã]o disruptiva"]

SYSTEM = """Voce escreve o texto de um esboco de site institucional em portugues do Brasil para uma empresa REAL.
Regras inegociaveis:
1. Use APENAS informacoes presentes nos dados fornecidos. Se algo nao estiver nos dados, nao escreva. Nunca invente anos de mercado, numeros, certificacoes, clientes, premios ou capacidades.
2. Tom: claro, tecnico, direto, humano. Sem hype. Proibido: "transforme seu negocio", "revolucione", "solucao completa", "lider de mercado", "referencia no mercado", "de ponta".
3. A hero precisa ser ESPECIFICA desta empresa (o que faz, para quem, onde), nao poderia servir a qualquer concorrente. Titulo com no maximo 9 palavras. Pode destacar UMA palavra com <em>...</em>.
4. Servicos: use os nomes que a empresa ja usa. No maximo 6. Descricao so quando os dados trazem uma frase real sobre aquele servico; senao omita "desc".
5. Textos curtos. Sem emojis.
Responda SOMENTE um objeto JSON valido, sem markdown, com exatamente estas chaves:
{"eyebrow": str (segmento + cidade/UF), "hero_title_html": str, "hero_sub": str (max 30 palavras), "hero_alt": str,
 "services_title": str (max 6 palavras), "services_intro": str|null,
 "services": [{"name": str, "desc": str|null}],
 "process": [str]|[] (so se os dados descreverem etapas),
 "about_title": str (max 7 palavras), "about": [str] (1 a 2 paragrafos curtos, parafraseando o texto da propria empresa),
 "facts": [{"k": str, "v": str}] (max 3, somente fatos presentes nos dados),
 "contact_title": str (pergunta curta e direta)}"""


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
        json={"model": MODELS["anthropic"]["id"], "max_tokens": 1500, "temperature": 0.4, "system": SYSTEM,
              "messages": [{"role": "user", "content": user}]})
    r.raise_for_status()
    j = r.json()
    return j["content"][0]["text"], j["usage"]["input_tokens"], j["usage"]["output_tokens"]


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
    # modelo trocavel sem mexer no codigo (ex.: se a chave for recusada no 2.5, usar gemini-3.5-flash-lite)
    model_id = os.environ.get("FILL_GEMINI_MODEL") or _db_setting("gemini_model") or MODELS["gemini"]["id"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent"
    r = requests.post(url, timeout=60, headers={"x-goog-api-key": api_key, "content-type": "application/json"},
                      json={"systemInstruction": {"parts": [{"text": SYSTEM}]},
                            "contents": [{"role": "user", "parts": [{"text": user}]}],
                            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json", "maxOutputTokens": 1500}})
    r.raise_for_status()
    j = r.json()
    u = j.get("usageMetadata", {})
    return j["candidates"][0]["content"]["parts"][0]["text"], u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def parse_json(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    return json.loads(txt)


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
                 "process", "about_title", "about", "facts", "contact_title")
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


def assemble(copy, ex, prospect):
    """Junta copy do LLM + fatos do extrator (que nunca passam pelo modelo)."""
    c = ex["contacts"]
    uf = (prospect.get("region") or "").split()[-1] if prospect.get("region") else ""
    slots = dict(copy)
    slots.update({
        "brand_name": prospect.get("company_name") or ex.get("site_name"),
        "short_name": prospect.get("company_name") or ex.get("site_name"),
        "accent": ex["colors"].get("accent"),
        "specbar": [x for x in [uf and slots.get("eyebrow", "").split("·")[-1].strip(), (c.get("phones") or [None])[0]] if x],
        "phones": c.get("phones", [])[:2],
        "address": c.get("address", ""),
        "city_uf": slots.get("eyebrow", "").split("·")[-1].strip(),
        "images": [i["file"] for i in ex.get("images", []) if i.get("file")][:3],
        "logo_file": ex.get("logo"),
    })
    return slots


def fill(prospect, ex, provider="anthropic"):
    user = build_user(prospect, ex)
    txt, tin, tout = (call_anthropic if provider == "anthropic" else call_gemini)(user)
    m = MODELS[provider]
    cost = tin * m["in"] / 1e6 + tout * m["out"] / 1e6
    copy = parse_json(txt)
    copy, problems, fatal = validate(copy, ex, prospect)
    return {"slots": assemble(copy, ex, prospect), "problems": problems, "fatal": fatal,
            "usage": {"provider": provider, "model": m["id"], "in": tin, "out": tout, "usd": round(cost, 6)}}


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
