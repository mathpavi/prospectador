"""Rotas da Central WhatsApp (C9 do PLANO_PROSPECTADOR). Contato SEMPRE manual: nada aqui envia mensagem."""
import math

from flask import Blueprint, jsonify, request

import database
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
