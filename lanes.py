"""Faixas de abordagem (decisao do usuario, 09/10/2026): cada lead recebe UMA abordagem conforme o que vale a pena.

  direta         volume: e-mail automatico com esboco (quando existe) e preco na primeira mensagem (planos prontos).
                 Entram: empresa SEM site, ou com site que o nosso esboco supera.
  personalizada  projeto sob medida (a partir de R$ 2.500, faixa que o proprio dono ja atende): empresa COM site onde o esboco de template NAO
                 supera o site atual (ou nao ha como gerar), com porte/capacidade de pagar e um problema REAL no site para comentar.
                 Recebe e-mail consultivo (sem esboco) e entra na lista "Quem chamar hoje" para contato humano.
  descartar      sem nenhum contato util, ou site atual ja muito bom (nao ha o que melhorar).
Roda NO MOMENTO DO ENVIO (depois do esboco/juiz), para usar o resultado do juiz de visao.
"""
import re

import database
import email_msg
import whatsapp_msg as wm

CAPITAL_MIN = 100_000          # R$ de capital social que, junto com o porte, indica capacidade de pagar (quando o dado existe)
PORTE_OK = ("03", "05")        # 03 = empresa de pequeno porte; 05 = demais (medio/grande). 01 = micro, 00 = nao informado


def enabled():
    return database.get_setting("lanes_enabled", "1") == "1"


def _num(txt):
    try:
        return float(str(txt).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def capacity(prospect):
    """(tem_capacidade, motivo). Usa porte/capital do cadastro da Receita (notas) e os campos antigos (porte, faturamento, funcionarios)."""
    notes = prospect.get("notes") or ""
    m = re.search(r"porte (\d{2})", notes)
    cap = re.search(r"capital R\$ ([\d.,]+)", notes)
    capital = _num(cap.group(1)) if cap else None
    if m and m.group(1) in PORTE_OK:
        if capital is None or capital >= CAPITAL_MIN:
            return True, f"porte {m.group(1)}" + (f", capital R$ {capital:,.0f}".replace(",", ".") if capital else "")
        return False, f"porte {m.group(1)} mas capital baixo (R$ {capital:,.0f})".replace(",", ".")
    if capital and capital >= CAPITAL_MIN * 3:
        return True, f"capital R$ {capital:,.0f}".replace(",", ".")
    porte = str(prospect.get("porte") or "").lower()
    if any(w in porte for w in ("demais", "médio", "medio", "grande", "epp", "pequeno porte")):
        return True, f"porte '{porte}'"
    fat = _num(re.sub(r"[^\d,.]", "", str(prospect.get("faturamento") or "")))
    if fat and fat >= 1_000_000:
        return True, "faturamento declarado alto"
    try:
        if int(re.sub(r"\D", "", str(prospect.get("funcionarios") or "0")) or 0) >= 20:
            return True, "20+ funcionarios"
    except ValueError:
        pass
    return False, "sem sinal de porte"


def classify(prospect, mockup=None, mockup_state=None):
    """Devolve (faixa, motivo). `mockup` = ultima linha da loja de esbocos do lead (ou None)."""
    has_contact = bool((prospect.get("contact_email") or "").strip() or (prospect.get("contact_phone") or "").strip()
                       or (prospect.get("contact_whatsapp") or "").strip())
    if not has_contact:
        return "descartar", "sem nenhum contato util"
    if not wm.has_own_site(prospect):
        return "direta", "sem site proprio"
    status = (mockup or {}).get("status")
    reason = ((mockup or {}).get("reason") or "").lower()
    if status == "ready":
        return "direta", "esboco melhor que o site atual"
    if "muito bom" in reason:
        return "descartar", "o site atual ja e muito bom"
    if mockup is None and mockup_state == "pending":
        return "direta", "esboco ainda nao avaliado (limite do dia ou outro esboco em andamento): oferta direta"
    has_cap, cap_why = capacity(prospect)
    real = email_msg.real_issue(prospect.get("detected_issues"))
    if has_cap and real:
        return "personalizada", f"esboco de template nao supera o site ({cap_why}); problema real: {real}"
    if has_cap and not real:
        return "direta", f"{cap_why}, mas sem problema real do site para citar"
    return "direta", "sem esboco melhor e sem sinal de porte: oferta direta"
