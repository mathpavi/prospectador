"""Chamada ao Gemini (API REST direta, sem o pacote `google-generativeai`, que foi descontinuado pelo Google).

Tolera modelos indisponiveis para a chave: se o modelo configurado ('gemini_model') responde 404 (aposentado ou sem acesso), ou o servico esta
sobrecarregado (500/502/503/504), tenta os da lista seguinte e MEMORIZA o que funcionou na configuracao 'gemini_model'.
Outros erros (cota 429, chave invalida 400/401/403, rede) nao sao mascarados: sobem para quem chamou.
Interface igual a anterior: generate(api_key, contents, generation_config, log) -> (resposta com .text, nome_do_modelo).
"""
import base64
import io

import requests

import database

GEMINI_MODEL_CHAIN = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OVERLOADED = (500, 502, 503, 504)


class GeminiHTTPError(Exception):
    def __init__(self, status, text):
        super().__init__(f"{status} {text}")
        self.status = status


class Resp:
    def __init__(self, text):
        self.text = text


def is_model_unavailable(exc):
    text = str(exc).lower()
    return (type(exc).__name__ == "NotFound" or getattr(exc, "status", None) in (404,) + OVERLOADED
            or "404" in text or "is not found" in text or "not supported for generatecontent" in text)


def _parts(contents):
    items = contents if isinstance(contents, (list, tuple)) else [contents]
    parts = []
    for it in items:
        if isinstance(it, str):
            parts.append({"text": it})
        elif hasattr(it, "save"):                                  # imagem PIL
            buf = io.BytesIO()
            img = it.convert("RGB") if getattr(it, "mode", "RGB") not in ("RGB", "L") else it
            img.save(buf, "JPEG", quality=85)
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}})
        else:
            parts.append({"text": str(it)})
    return parts


def _config(gc):
    out = {}
    for k, v in (gc or {}).items():
        key = {"response_mime_type": "responseMimeType", "max_output_tokens": "maxOutputTokens", "top_p": "topP", "top_k": "topK"}.get(k, k)
        out[key] = v
    return out


def _call(api_key, model, contents, generation_config):
    body = {"contents": [{"role": "user", "parts": _parts(contents)}]}
    cfg = _config(generation_config)
    if cfg:
        body["generationConfig"] = cfg
    r = requests.post(ENDPOINT.format(model=model), headers={"x-goog-api-key": api_key, "content-type": "application/json"}, json=body, timeout=90)
    if r.status_code != 200:
        raise GeminiHTTPError(r.status_code, f"models/{model}: {r.text[:300]}")
    data = r.json()
    try:
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"resposta vazia do Gemini (bloqueio de seguranca?): {str(data)[:200]}")
    return Resp(text)


def generate(api_key, contents, generation_config=None, log=None):
    """Devolve (resposta, nome_do_modelo_usado)."""
    chosen = (database.get_setting("gemini_model", "") or "").strip()
    chain = list(dict.fromkeys(([chosen] if chosen else []) + GEMINI_MODEL_CHAIN))
    last = None
    for name in chain:
        try:
            resp = _call(api_key, name, contents, generation_config)
        except Exception as e:  # noqa: BLE001
            if is_model_unavailable(e):
                last = e
                if log:
                    log(f"Gemini: modelo '{name}' indisponivel agora ({str(e)[:60]}); tentando o proximo.")
                continue
            raise
        if name != chosen:
            database.save_settings({"gemini_model": name})        # lembra o que funcionou
            if log:
                log(f"Gemini: usando o modelo '{name}' (configuracao 'gemini_model' atualizada).")
        return resp, name
    raise last if last else RuntimeError("nenhum modelo Gemini disponivel")
