"""C8 do PLANO_PROSPECTADOR: ordem da fila de envio do piloto por POTENCIAL (antes era so ordem de chegada).

Quem tem e-mail da propria empresa, site proprio, dono conhecido, segmento do nucleo e um problema real no site vai primeiro.
Um bonus de espera garante que ninguem fique parado para sempre (sem fome).
"""
import json
import re
from datetime import datetime
from urllib.parse import urlparse

import whatsapp_msg

FREE_MAIL = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "uol.com.br", "bol.com.br", "terra.com.br",
             "ig.com.br", "live.com", "icloud.com", "globo.com", "msn.com"}
REAL_ISSUES = ("inseguro", "responsivo", "viewport", "copyright desatualizado")      # problemas que o dono entende; o resto e cosmetico


def _site_host(website):
    return re.sub(r"^www\.", "", urlparse(website or "").netloc.lower())


def email_priority(lead, now=None):
    """Numero maior = vai primeiro."""
    score = 50.0
    email = (lead.get("contact_email") or "").lower()
    edom = email.rsplit("@", 1)[1] if "@" in email else ""
    site = _site_host(lead.get("website"))
    if whatsapp_msg.has_own_site(lead):
        score += 15
        if edom and edom not in FREE_MAIL and (edom == site or site.endswith("." + edom) or edom.endswith("." + site)):
            score += 15          # e-mail do proprio dominio da empresa (tomador de decisao, nao caixa generica)
    if edom in FREE_MAIL:
        score -= 5
    if whatsapp_msg.partner_first_name(lead.get("socios")):
        score += 5
    if any(k in (lead.get("segment") or "").lower() for k in whatsapp_msg.CORE_SEGMENTS):
        score += 10
    if lead.get("porte") or lead.get("faturamento"):
        score += 5
    try:
        issues = lead.get("detected_issues")
        issues = json.loads(issues) if isinstance(issues, str) else (issues or [])
    except Exception:  # noqa: BLE001
        issues = []
    if any(any(k in str(i).lower() for k in REAL_ISSUES) for i in issues):
        score += 10
    try:
        age_days = ((now or datetime.now()) - datetime.strptime(str(lead.get("created_at"))[:19], "%Y-%m-%d %H:%M:%S")).days
        score += min(10, max(0, age_days) * 0.5)      # bonus de espera: no maximo +10
    except Exception:  # noqa: BLE001
        pass
    return score
