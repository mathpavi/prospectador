"""Chamada ao Gemini que tolera modelos indisponiveis para a chave.

Se o modelo configurado ('gemini_model') responde 404/NotFound (aposentado ou sem acesso para esta chave),
tenta os da lista seguinte e MEMORIZA o que funcionou na configuracao 'gemini_model'. Outros erros
(cota, rede, chave invalida) nao sao mascarados: sobem para quem chamou.
"""
import database

GEMINI_MODEL_CHAIN = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash"]


def is_model_unavailable(exc):
    text = str(exc).lower()
    return type(exc).__name__ == "NotFound" or "404" in text or "is not found" in text or "not supported for generatecontent" in text


def generate(api_key, contents, generation_config=None, log=None):
    """Devolve (resposta, nome_do_modelo_usado)."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    chosen = (database.get_setting("gemini_model", "") or "").strip()
    chain = list(dict.fromkeys(([chosen] if chosen else []) + GEMINI_MODEL_CHAIN))
    last = None
    for name in chain:
        try:
            resp = genai.GenerativeModel(name).generate_content(contents, generation_config=generation_config)
        except Exception as e:  # noqa: BLE001
            if is_model_unavailable(e):
                last = e
                if log:
                    log(f"Gemini: modelo '{name}' indisponivel para esta chave; tentando o proximo.")
                continue
            raise
        if name != chosen:
            database.save_settings({"gemini_model": name})        # lembra o que funcionou
            if log:
                log(f"Gemini: usando o modelo '{name}' (configuracao 'gemini_model' atualizada).")
        return resp, name
    raise last if last else RuntimeError("nenhum modelo Gemini disponivel")
