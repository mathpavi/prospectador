"""Rotas da Central WhatsApp (C9 do PLANO_PROSPECTADOR). Contato SEMPRE manual: nada aqui envia mensagem."""
import math
import re

from flask import Blueprint, jsonify, request

import database
import gemini_util
import mailer
import whatsapp_msg

bp = Blueprint("whatsapp_routes", __name__)

ACCOUNTS = ("business", "personal")
# resultado informado na tela -> (estagio do funil, nota)
OUTCOMES = {
    "respondeu": ("respondeu", None),
    "interessado": ("interessado", None),
    "reuniao": ("reuniao", None),
    "sem_interesse": ("perdido", "sem interesse (WhatsApp)"),
    "pediu_parar": ("descadastrou", "pediu para parar (WhatsApp)"),
    "numero_invalido": ("invalido", "numero invalido/sem WhatsApp"),
}


def _group_of(lead):
    return "email_sent" if lead.get("status") == "sent" else "no_email"


def _mockup_urls(rows):
    try:
        from mockups import store
        tokens = store.ready_tokens([r["id"] for r in rows])
    except Exception:  # noqa: BLE001
        tokens = {}
    base = mailer.public_base_url()
    return {pid: f"{base}/p/{tok}/" for pid, tok in tokens.items()}


def _counts():
    return {s: len(database.get_whatsapp_candidates(s)) for s in ("email_sent", "no_email", "contacted")}


@bp.route("/api/whatsapp/opportunities", methods=["GET"])
def opportunities():
    subtab = request.args.get("subtab", "email_sent")
    segment = request.args.get("segment")
    q = request.args.get("q") or request.args.get("search")
    min_score = request.args.get("min_score", 0, type=int) or 0
    page = max(1, request.args.get("page", 1, type=int) or 1)
    limit = request.args.get("limit", 24, type=int) or 24

    rows = database.get_whatsapp_candidates(subtab, segment, q)
    urls = _mockup_urls(rows)
    sender = database.get_setting("sender_name", "Matheus Paviani")
    leads = [whatsapp_msg.enrich(r, _group_of(r), urls.get(r["id"]), sender) for r in rows]
    if min_score:
        leads = [l for l in leads if l["wa_priority"] >= min_score]
    if subtab == "contacted":
        leads.sort(key=lambda l: l.get("whatsapp_contacted_at") or "", reverse=True)
    else:
        leads.sort(key=lambda l: (l["wa_priority"], l["id"]), reverse=True)

    total = len(leads)
    start = (page - 1) * limit
    stats = database.get_whatsapp_stats()
    counts = _counts()
    today = database.whatsapp_today_counts()
    stats.update({
        "email_sent_count": counts["email_sent"], "no_email_count": counts["no_email"], "contacted_count": counts["contacted"],
        "today_total": today["total"], "today_by_account": today["by_account"],
        "daily_goal": int(database.get_setting("whatsapp_daily_goal", "15") or 15),
        "last_contact_at": database.whatsapp_last_contact_at(),
    })
    return jsonify({"prospects": leads[start:start + limit], "total": total, "page": page, "limit": limit,
                    "total_pages": math.ceil(total / limit) if limit else 1, "stats": stats})


@bp.route("/api/whatsapp/mark-contacted/<int:prospect_id>", methods=["POST"])
def mark_contacted(prospect_id):
    body = request.get_json(silent=True) or {}
    prospect = database.get_prospect(prospect_id)
    if not prospect:
        return jsonify({"success": False, "error": "prospect nao encontrado"}), 404
    account = body.get("account") if body.get("account") in ACCOUNTS else None
    database.mark_whatsapp_contacted(prospect_id, True)
    database.add_event(prospect_id, "whatsapp_contacted", None,
                       {"account": account, "mockup": bool(body.get("mockup")), "group": body.get("group")})
    if not prospect.get("stage") or prospect.get("stage") == "novo":
        database.set_stage(prospect_id, "contatado", note="WhatsApp")
    return jsonify({"success": True, "message": "Lead marcado como contatado via WhatsApp!"})


def apply_generated_drafts(prospects):
    """Troca o rascunho de WhatsApp ANTIGO (frase fixa, igual para todos, com afirmacoes que nao eram verdade) pela mensagem gerada.
    Respeita o texto que voce mesmo editou e salvou (whatsapp_custom_draft). Usado nas listas de Leads, Acompanhamento etc."""
    sender = database.get_setting("sender_name", "Matheus Paviani")
    urls = _mockup_urls(prospects)
    for p in prospects:
        p["mockup_url"] = urls.get(p["id"], "")             # esboco no ar (selo nos cartoes de lead)
        if p.get("whatsapp_custom_draft"):
            p["wa_generated"] = False
            continue
        p["whatsapp_draft"] = whatsapp_msg.build_message(p, _group_of(p), urls.get(p["id"]), sender)
        p["wa_generated"] = True
    return prospects


@bp.route("/api/whatsapp/message/<int:prospect_id>", methods=["GET"])
def message_variant(prospect_id):
    """'Outra versao': a mensagem do lead na versao N (0, 1, 2...). Estavel e gratuita (nao usa IA)."""
    prospect = database.get_prospect(prospect_id)
    if not prospect:
        return jsonify({"error": "prospect nao encontrado"}), 404
    variant = request.args.get("variant", 0, type=int) or 0
    sender = database.get_setting("sender_name", "Matheus Paviani")
    url = _mockup_urls([prospect]).get(prospect_id)
    return jsonify({"message": whatsapp_msg.build_message(prospect, _group_of(prospect), url, sender, variant), "variant": variant})


_URL_RE = re.compile(r"https?://[^\s]+")
_EXIT_RE = re.compile(r"avis|\bparo\b|parar|incomod|n[aã]o volto|sem problema|sem compromisso|me diga|me diz|falar que n[aã]o", re.I)
_CLAIM_RE = re.compile(r"garant|gr[aá]tis|gratuit|l[ií]der|refer[eê]ncia|premiad|certificad|desconto|promo[cç]|melhor do|n[uú]mero 1", re.I)


def check_rewrite(original, rewritten):
    """Travas da reescrita por IA: devolve (ok, motivo). A IA nao pode inventar nada."""
    if not rewritten or len(rewritten) < 40:
        return False, "texto vazio ou curto demais"
    if len(rewritten) > max(int(len(original) * 1.4), 220) or len(rewritten) > 520:
        return False, "texto longo demais"
    if set(_URL_RE.findall(rewritten)) != set(_URL_RE.findall(original)):
        return False, "alterou ou removeu um link"
    if not set(re.findall(r"\d+", rewritten)) <= set(re.findall(r"\d+", original)):
        return False, "acrescentou numeros"
    if _CLAIM_RE.search(rewritten) and not _CLAIM_RE.search(original):
        return False, "acrescentou promessa ou afirmacao"
    if re.search(r"[\U0001F300-\U0001FAFF☀-➿]", rewritten):
        return False, "usou emoji"
    if not _EXIT_RE.search(rewritten):
        return False, "perdeu a frase que deixa a pessoa livre para pedir que voce pare"
    return True, ""


@bp.route("/api/whatsapp/rewrite/<int:prospect_id>", methods=["POST"])
def rewrite(prospect_id):
    """'Reescrever com IA': mesmo sentido, palavras diferentes. Se a IA inventar algo, devolve o original."""
    body = request.get_json(silent=True) or {}
    original = (body.get("text") or "").strip()
    if not original:
        return jsonify({"error": "sem texto para reescrever"}), 400
    api_key = database.get_setting("gemini_api_key", "")
    if not api_key:
        return jsonify({"error": "cadastre a chave do Gemini em Configuracoes"}), 503
    prompt = ("Reescreva esta mensagem de WhatsApp (prospeccao comercial) com palavras e estrutura diferentes, mantendo exatamente o mesmo "
              "significado, o mesmo tom humano e informal do portugues do Brasil e tamanho parecido.\n"
              "Regras: mantenha os links EXATAMENTE como estao; nao acrescente fatos, numeros, elogios, promessas, precos nem emojis; "
              "mantenha a frase final que deixa a pessoa livre para pedir que voce pare; devolva SOMENTE o texto da mensagem.\n\n"
              f"MENSAGEM:\n{original}")
    try:
        resp, _ = gemini_util.generate(api_key, prompt, {"temperature": 0.9})
        text = (resp.text or "").strip().strip('"').strip()
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"IA indisponivel ({type(e).__name__})"}), 502
    ok, why = check_rewrite(original, text)
    if not ok:
        return jsonify({"error": f"a IA devolveu um texto que nao passou nas travas ({why}); mantive o original", "text": original}), 422
    return jsonify({"text": text})


@bp.route("/api/whatsapp/outcome/<int:prospect_id>", methods=["POST"])
def outcome(prospect_id):
    body = request.get_json(silent=True) or {}
    key = body.get("outcome")
    if key not in OUTCOMES:
        return jsonify({"success": False, "error": f"resultado invalido. Use: {', '.join(OUTCOMES)}"}), 400
    prospect = database.get_prospect(prospect_id)
    if not prospect:
        return jsonify({"success": False, "error": "prospect nao encontrado"}), 404
    account = body.get("account") if body.get("account") in ACCOUNTS else None
    stage, note = OUTCOMES[key]
    if not prospect.get("whatsapp_contacted"):
        database.mark_whatsapp_contacted(prospect_id, True)
        database.add_event(prospect_id, "whatsapp_contacted", None, {"account": account})
    database.set_stage(prospect_id, stage, note=note)
    database.add_event(prospect_id, "whatsapp_outcome", key, {"account": account})
    if key in ("pediu_parar", "numero_invalido"):
        digits, _, _ = whatsapp_msg.phone_info(prospect.get("contact_whatsapp") or prospect.get("contact_phone"))
        if digits:
            database.add_suppression(digits, note, prospect_id, kind="phone")
    return jsonify({"success": True, "stage": stage})
