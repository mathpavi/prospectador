"""Rotacao automatica de alvos do piloto: o piloto NUNCA fica parado por saturacao.

Cada busca do piloto mede o que rendeu (leads novos, com e-mail, so com WhatsApp). Alvo que rende pouco entra em DESCANSO
(`autopilot_cooldown_days`, padrao 14 dias) e o piloto passa para outro: outro segmento, outra regiao ou outra forma de busca
(organica -> Google Maps -> diretorio). Os alvos que voce cadastrou tem prioridade; quando todos estao saturados, entram os
alvos AUTOMATICOS (catalogo abaixo), em ordem de expansao: RS primeiro, depois estados vizinhos e demais.

Estado guardado em configuracoes: `autopilot_target_stats` (historico por alvo). Os alvos automaticos NAO sao gravados na sua lista
(`autopilot_search_targets`), para a tela de edicao nunca sobrescrever nada.
Interruptor: `autopilot_auto_rotate` (1/0, padrao 1).
"""
import json
from datetime import datetime, timedelta

import database

# segmentos com template de esboco e perfil do servico (ordem = prioridade)
SEGMENTS = ["Metalúrgica", "Usinagem", "Caldeiraria / Soldagem", "Serralheria", "Vidraçaria", "Esquadrias de Alumínio", "Marmoraria",
            "Indústria de Plásticos", "Fábrica de Móveis", "Indústria Têxtil", "Panificadora", "Serviços de Limpeza",
            "Distribuidora / Logística", "Advogado", "Segurança Eletrônica", "Clínica de Estética"]
# ordem de expansao geografica (estado inteiro)
REGIONS = ["RS", "SC", "PR", "SP", "MG", "RJ", "ES", "GO", "DF", "BA", "PE", "CE"]
# formas de busca, da que mais rende e-mail para a que menos rende
TYPES = ["organic", "maps_only", "directory"]

KEEP_RUNS = 6
MIN_USEFUL_2RUNS = 3.0          # soma de "utilidade" nas 2 ultimas buscas abaixo disso = saturado
ERROR_COOLDOWN_H = 3            # erro de busca (API fora, cota): descansa pouco, nao e saturacao


def enabled():
    return database.get_setting("autopilot_auto_rotate", "1") == "1"


def key_of(t):
    return f"{(t.get('segment') or '').strip().lower()}|{(t.get('region') or '').strip().lower()}|{t.get('type') or 'organic'}"


def _now():
    return database.get_now().replace(tzinfo=None)


def _load():
    try:
        d = json.loads(database.get_setting("autopilot_target_stats", "{}") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save(d):
    database.save_settings({"autopilot_target_stats": json.dumps(d, ensure_ascii=False)})


def in_cooldown(key, stats=None, now=None):
    st = (stats if stats is not None else _load()).get(key) or {}
    until = st.get("cooldown_until")
    if not until:
        return False
    try:
        return datetime.strptime(until, "%Y-%m-%d %H:%M:%S") > (now or _now())
    except Exception:  # noqa: BLE001
        return False


def usefulness(run):
    """Valor de uma busca: e-mail novo vale 1; lead novo so com WhatsApp vale 0,1 (da para a Central WhatsApp)."""
    return run.get("email", 0) + 0.1 * run.get("whatsapp_only", 0)


def record_run(target, new, email, whatsapp_only, error=None, now=None):
    """Registra o resultado de uma busca e decide se o alvo esta saturado. Devolve (saturado, motivo)."""
    now = now or _now()
    d = _load()
    k = key_of(target)
    st = d.setdefault(k, {"segment": target.get("segment"), "region": target.get("region"), "type": target.get("type") or "organic", "runs": []})
    st["runs"].append({"t": now.strftime("%Y-%m-%d %H:%M:%S"), "new": int(new), "email": int(email), "whatsapp_only": int(whatsapp_only), "error": (error or "")[:120]})
    st["runs"] = st["runs"][-KEEP_RUNS:]
    reason = ""
    if error:
        st["cooldown_until"] = (now + timedelta(hours=ERROR_COOLDOWN_H)).strftime("%Y-%m-%d %H:%M:%S")
        st["reason"] = f"erro na busca: {error[:80]}"
        _save(d)
        return False, st["reason"]
    last = [r for r in st["runs"] if not r.get("error")][-2:]
    if last and last[-1]["new"] == 0:
        reason = "so trouxe leads repetidos (nenhum novo)"
    elif len(last) == 2 and sum(usefulness(r) for r in last) < MIN_USEFUL_2RUNS:
        reason = f"rendeu pouco: {sum(r['email'] for r in last)} lead(s) com e-mail nas ultimas 2 buscas"
    elif len(last) == 1 and last[0]["new"] >= 15 and last[0]["email"] == 0 and usefulness(last[0]) < MIN_USEFUL_2RUNS:
        reason = f"{last[0]['new']} leads novos, nenhum com e-mail"
    if reason:
        try:
            days = int(database.get_setting("autopilot_cooldown_days", "14"))
        except Exception:  # noqa: BLE001
            days = 14
        st["cooldown_until"] = (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        st["reason"] = reason
        st["runs"] = []              # recomeca a contagem quando voltar do descanso
    else:
        st.pop("cooldown_until", None)
        st.pop("reason", None)
    _save(d)
    return bool(reason), reason


def candidates():
    """Catalogo de alvos automaticos na ordem de expansao: regiao > segmento > forma de busca."""
    out = []
    for region in REGIONS:
        for seg in SEGMENTS:
            for typ in TYPES:
                out.append({"segment": seg, "region": region, "type": typ, "radius_km": 0, "limit": 60, "auto": True})
    return out


def choose(configured, current_idx=0, now=None):
    """Escolhe o proximo alvo. Devolve (alvo, origem, novo_indice). origem: 'configurado' | 'automatico' | None."""
    now = now or _now()
    stats = _load()
    rotate = enabled()
    n = len(configured)
    if n:
        for step in range(n):
            i = (current_idx + step) % n
            if not rotate or not in_cooldown(key_of(configured[i]), stats, now):
                return configured[i], "configurado", (i + 1) % n
    if not rotate:
        return None, None, current_idx
    # todos os alvos cadastrados saturados (ou nenhum cadastrado): usa o catalogo automatico
    never, resting = [], []
    for c in candidates():
        k = key_of(c)
        if in_cooldown(k, stats, now):
            continue
        (never if not (stats.get(k) or {}).get("runs") and k not in stats else resting).append(c)
    pool = never or resting
    if pool:
        return pool[0], "automatico", current_idx
    # tudo em descanso (improvavel): reabre o que vence primeiro, para nunca parar
    soonest = sorted(stats.items(), key=lambda kv: kv[1].get("cooldown_until") or "")
    if soonest:
        s = soonest[0][1]
        return {"segment": s["segment"], "region": s["region"], "type": s["type"], "radius_km": 0, "limit": 60, "auto": True}, "automatico", current_idx
    return None, None, current_idx


def retry_soon():
    """True se a ultima busca rendeu pouco: a proxima nao precisa esperar o intervalo inteiro."""
    return database.get_setting("autopilot_search_retry_soon", "0") == "1"


def set_retry_soon(flag):
    database.save_settings({"autopilot_search_retry_soon": "1" if flag else "0"})


def summary(now=None):
    """Para o Painel: alvos em descanso (com motivo e quando voltam) e historico recente."""
    now = now or _now()
    d = _load()
    resting, active = [], []
    for k, st in d.items():
        row = {"segmento": st.get("segment"), "regiao": st.get("region"), "tipo": st.get("type"), "motivo": st.get("reason", ""), "volta_em": st.get("cooldown_until", "")}
        runs = st.get("runs", [])
        row["ultima"] = (f"{runs[-1]['new']} novos, {runs[-1]['email']} com e-mail" if runs else "")
        (resting if in_cooldown(k, d, now) else active).append(row)
    return {"ligado": enabled(), "em_descanso": resting, "ativos": active[-8:]}


# ---------------------------------------------------------------------------------------------
# Quando buscar: guiado pelo ESTOQUE de leads com e-mail na fila, nao por relogio.
# Buscar nao e spam (spam e o ENVIO): o unico motivo para segurar uma busca e custo/cota das APIs e bloqueio dos sites.
# Por isso: busca continuamente (pausa minima de poucos minutos) enquanto o estoque estiver baixo; para quando a fila ja
# esta cheia (nao ha o que ganhar) ou quando o teto diario de buscas (credito das APIs) e atingido.
# ---------------------------------------------------------------------------------------------
def _int(key, default):
    try:
        return int(database.get_setting(key, str(default)))
    except Exception:  # noqa: BLE001
        return default


def searches_today(now=None):
    now = now or _now()
    if database.get_setting("autopilot_search_count_date", "") != now.strftime("%Y-%m-%d"):
        return 0
    return _int("autopilot_search_count", 0)


def note_search_started(now=None):
    now = now or _now()
    n = searches_today(now) + 1
    database.save_settings({"autopilot_search_count_date": now.strftime("%Y-%m-%d"), "autopilot_search_count": str(n)})
    return n


def stock():
    """Leads aprovados com e-mail esperando envio."""
    conn = database.get_db_connection()
    n = conn.execute("SELECT COUNT(*) FROM prospects WHERE status='approved' AND contact_email IS NOT NULL AND contact_email != ''").fetchone()[0]
    conn.close()
    return n


def search_gate(now=None):
    """(pode_buscar, codigo, motivo). codigos: ok | daily_cap | queue_full | waiting_interval."""
    now = now or _now()
    last = database.get_setting("autopilot_last_search_run_at", "")
    elapsed_min = None
    if last:
        try:
            elapsed_min = (now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60.0
        except Exception:  # noqa: BLE001
            elapsed_min = None
    if not enabled():
        # modo antigo: so o intervalo em horas
        hours = _int("autopilot_search_interval_hours", 12)
        if elapsed_min is not None and elapsed_min < hours * 60:
            return False, "waiting_interval", f"intervalo de {hours} h nao atingido"
        return True, "ok", ""
    cap = _int("autopilot_search_daily_cap", 60)
    if cap and searches_today(now) >= cap:
        return False, "daily_cap", f"teto diario de {cap} buscas atingido (protege o credito das APIs); volta amanha"
    gap = _int("autopilot_search_min_gap_min", 2)
    if elapsed_min is not None and elapsed_min < gap:
        return False, "waiting_interval", f"pausa minima de {gap} min entre buscas"
    target = _int("autopilot_queue_target", 60)
    if target and stock() >= target:
        return False, "queue_full", f"fila cheia ({stock()} leads com e-mail aguardando envio; meta {target}): nao ha o que ganhar buscando agora"
    return True, "ok", ""
