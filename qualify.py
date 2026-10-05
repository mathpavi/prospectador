"""Q2 do PLANO_PROSPECTADOR: confirma, com IA barata, se o prospect e uma EMPRESA REAL do segmento procurado e de porte adequado.

Roda na hora do envio (so para quem ia receber e-mail), guarda o veredito em prospects.qualification e registra evento.
Falha ABERTA em erro de infraestrutura (sem chave, site fora do ar, IA indisponivel): nao trava o piloto, mas tambem nao
guarda veredito. Falha FECHADA quando a IA diz explicitamente que nao serve.
"""
import json
import re

import database
import gemini_util

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PROMPT = """Voce classifica prospects para uma empresa que vende criacao de sites para empresas pequenas e medias.
Segmento procurado: {segment}
Nome cadastrado: {name}
Endereco do site: {domain}

Conteudo do site (pode estar incompleto):
{text}

Responda SOMENTE um JSON com exatamente estas chaves:
{{"empresa_real": true|false,
 "segmento_confere": true|false,
 "porte": "micro"|"pequena"|"media"|"grande",
 "atividade": "o que a empresa faz, em uma frase curta",
 "motivo": "justificativa em uma frase"}}

Regras:
- empresa_real = false se for diretorio, agregador, portal de noticias, blog, marketplace, pagina de spam/SEO, rede social, curso, ou site sem atividade propria.
- segmento_confere = true se a atividade principal corresponde ao segmento procurado OU a um segmento proximo do mesmo setor (ex.: serralheria, usinagem e caldeiraria contam como metalurgia). Empresas de outras areas (RH, energia solar, software, contabilidade) NAO conferem com metalurgia.
- porte "grande" = multinacional, rede nacional, grande grupo ou capital aberto. Dono local de fabrica ou oficina e micro/pequena/media."""


def _fetch_text(url, limit=1800):
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, headers={"User-Agent": UA}, timeout=8, verify=False)
        if r.status_code >= 400:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        md = soup.find("meta", attrs={"name": "description"})
        meta = md.get("content", "") if md else ""
        for t in soup(["script", "style", "noscript", "svg", "iframe"]):
            t.decompose()
        body = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
        return f"Titulo: {title}\nDescricao: {meta}\nTexto: {body[:limit]}"
    except Exception:  # noqa: BLE001
        return ""


def _parse(txt):
    txt = re.sub(r"^```(?:json)?|```$", "", (txt or "").strip(), flags=re.M).strip()
    return json.loads(txt)


def verdict(data):
    """(ok, motivo) a partir da resposta da IA."""
    atividade = (data.get("atividade") or "").strip()[:90]
    if data.get("empresa_real") is False:
        return False, f"nao e uma empresa real ({(data.get('motivo') or atividade)[:100]})"
    if data.get("segmento_confere") is False:
        return False, f"segmento nao confere (atividade: {atividade})"
    if str(data.get("porte", "")).lower() == "grande":
        return False, "empresa de grande porte"
    return True, atividade


def qualify_prospect(prospect, force=False):
    """(ok, motivo). ok=True tambem quando nao foi possivel verificar (falha aberta)."""
    if database.get_setting("qualify_before_send", "1") == "0":
        return True, "verificacao desligada"
    cached = (prospect.get("qualification") or "").strip()
    if cached and not force:
        return (not cached.startswith("reject:")), cached.split(":", 1)[-1] if cached.startswith("reject:") else cached
    api_key = database.get_setting("gemini_api_key", "")
    if not api_key:
        return True, "sem chave de IA: nao verificado"
    site = prospect.get("website") or ""
    text = _fetch_text(site) if site.startswith("http") else ""
    if not text:
        text = "(site nao carregou) " + (prospect.get("notes") or "")[:600]
    from urllib.parse import urlparse
    prompt = PROMPT.format(segment=prospect.get("segment") or "?", name=prospect.get("company_name") or "?",
                           domain=urlparse(site).netloc or site, text=text)
    try:
        resp, _model = gemini_util.generate(api_key, prompt, {"response_mime_type": "application/json", "temperature": 0.1})
        data = _parse(resp.text)
    except Exception as e:  # noqa: BLE001
        return True, f"IA indisponivel: nao verificado ({type(e).__name__})"
    ok, why = verdict(data)
    pid = prospect.get("id")
    if pid:
        database.update_prospect(pid, {"qualification": ("ok: " + why) if ok else ("reject:" + why)})
        database.add_event(pid, "qualified" if ok else "qualification_rejected", why, {"porte": data.get("porte")})
    return ok, why
