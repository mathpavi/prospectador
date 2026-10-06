"""M1 do PLANO_PROSPECTADOR: o esboco de site entra no fluxo de envio, sozinho.

ensure_mockup(prospect) -> URL do esboco pronto (gerando um novo se preciso) ou None. NUNCA levanta excecao: se qualquer coisa falhar
(sem foto real, sem chave, Chromium, limite do dia...), o e-mail simplesmente sai sem link, com a oferta honesta de preparar um esboco.

A geracao roda em PROCESSO SEPARADO (python mockups/make_mockup.py): o Chromium nao disputa memoria com o painel e, se travar, morre sozinho.
Controles: configuracao 'mockup_in_email' (1/0), 'mockup_daily_limit' (padrao 40 por 24 h), uma geracao por vez, nao insiste no mesmo prospect por 7 dias.
"""
import os
import subprocess
import sys
import threading

import database
import whatsapp_msg

ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(ROOT, "mockups", "make_mockup.py")
_lock = threading.Lock()


def _url_for(prospect_id):
    from mockups import store
    import mailer
    token = store.ready_tokens([prospect_id]).get(prospect_id)
    return f"{mailer.public_base_url()}/p/{token}/" if token else None


def ensure_mockup(prospect, timeout=300):
    try:
        if database.get_setting("mockup_in_email", "1") == "0":
            return None
        pid = prospect.get("id")
        if not pid or not whatsapp_msg.has_own_site(prospect):
            return None
        url = _url_for(pid)
        if url:
            return url
        from mockups import store
        sys.path.insert(0, os.path.join(ROOT, "mockups"))
        import make_mockup
        if not make_mockup.pick_template(prospect.get("segment"), pid):
            return None                                           # sem template para este segmento: nao adianta gerar
        if store.recent_attempt(pid, 7):
            return None                                           # ja tentou (pronto expirado ou em revisao): nao insistir
        try:
            limit = int(database.get_setting("mockup_daily_limit", "40") or 40)
        except ValueError:
            limit = 40
        if store.created_last_24h() >= limit:
            return None
        if not _lock.acquire(blocking=False):
            return None                                           # outro esboco em andamento: este e-mail sai sem link
        try:
            proc = subprocess.run([sys.executable, SCRIPT, "--prospect-id", str(pid), "--provider", "gemini"],
                                  capture_output=True, text=True, timeout=timeout, cwd=ROOT, env=os.environ.copy())
            out = (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            out = "timeout"
        finally:
            _lock.release()
        url = _url_for(pid)
        reason = next((ln.strip(" -") for ln in out.splitlines() if "revisar" in ln), "")[:160]
        database.add_event(pid, "mockup_generated" if url else "mockup_review", reason or ("pronto" if url else out.strip()[-160:]))
        return url
    except Exception:  # noqa: BLE001
        return None
