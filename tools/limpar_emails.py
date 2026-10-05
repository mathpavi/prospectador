"""Limpeza de e-mails invalidos ja gravados no banco (Q1 do PLANO_PROSPECTADOR).

Por padrao e SIMULACAO (nao altera nada). Use --apply para gravar.
  python tools/limpar_emails.py              lista o que seria limpo (so sintaxe, rapido)
  python tools/limpar_emails.py --mx         tambem consulta o DNS (mais lento)
  python tools/limpar_emails.py --apply      limpa: zera o e-mail invalido, volta o prospect para 'pending' e registra a nota
Nunca mexe em prospects ja enviados (status 'sent').
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database  # noqa: E402
import validators  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--mx", action="store_true")
    a = ap.parse_args()
    database.init_db()          # garante tabelas/colunas novas (idempotente)
    conn = database.get_db_connection()
    rows = conn.execute("select id, company_name, status, contact_email, notes from prospects "
                        "where contact_email is not null and contact_email != '' and status != 'sent' order by id").fetchall()
    conn.close()
    bad = []
    for r in rows:
        st, why, norm = validators.check_email(r["contact_email"], check_dns=a.mx)
        if st == "invalid":
            bad.append((r, why))
    print(f"Verificados: {len(rows)} | invalidos: {len(bad)} | modo: {'APLICANDO' if a.apply else 'simulacao (nada sera gravado)'}")
    for r, why in bad[:60]:
        print(f"  #{r['id']:5} {str(r['company_name'])[:30]:30} {r['status']:9} {r['contact_email']:38} -> {why}")
    if len(bad) > 60:
        print(f"  ... e mais {len(bad) - 60}")
    if a.apply:
        for r, why in bad:
            note = ((r["notes"] or "") + f"\n[sistema] e-mail invalido removido ({why}): {r['contact_email']}").strip()
            new_status = "pending" if r["status"] in ("approved", "pending", "failed", "rejected") else r["status"]
            database.update_prospect(r["id"], {"contact_email": "", "notes": note, "status": new_status})
            database.add_event(r["id"], "email_cleaned", why, {"email": r["contact_email"]})
        print(f"Limpos: {len(bad)}")
    elif bad:
        print("\nPara aplicar: python tools/limpar_emails.py --apply")


if __name__ == "__main__":
    main()
