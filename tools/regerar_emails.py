"""Atualiza os e-mails AINDA NAO ENVIADOS que foram escritos pelo modelo antigo (E4 do PLANO_PROSPECTADOR).

O modelo antigo prometia "desenvolvi um estudo visual... fiz especificamente para vocês" (nao existia) e elogiava sem base.
Mesmo sem rodar esta ferramenta, o envio ja regenera esses corpos automaticamente; ela serve para voce ver o texto novo na tela antes.

  python tools/regerar_emails.py             SIMULACAO: conta e mostra 3 exemplos (nao grava)
  python tools/regerar_emails.py --apply     regrava assunto e corpo dos nao enviados com texto antigo
  python tools/regerar_emails.py --todos --apply   regrava TODOS os nao enviados (inclusive os que voce editou: cuidado)
Nunca mexe em prospects ja enviados (status 'sent').
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database  # noqa: E402
import email_msg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--todos", action="store_true")
    a = ap.parse_args()
    database.init_db()
    sender = {"name": database.get_setting("sender_name", "Matheus Paviani"), "whatsapp": database.get_setting("sender_whatsapp", ""),
              "portfolio": database.get_setting("sender_portfolio", "")}
    conn = database.get_db_connection()
    rows = [dict(r) for r in conn.execute("select * from prospects where status in ('pending','approved','failed')").fetchall()]
    conn.close()
    targets = [r for r in rows if a.todos or email_msg.is_legacy_body(r.get("email_body")) or not (r.get("email_body") or "").strip()]
    print(f"Nao enviados: {len(rows)} | a atualizar: {len(targets)} | modo: {'APLICANDO' if a.apply else 'simulacao (nada sera gravado)'}")
    for r in targets[:3]:
        subj, body = email_msg.build_email(r, sender)
        print(f"\n#{r['id']} {r['company_name']}\nASSUNTO: {subj}\n{body}\n" + "-" * 50)
    if a.apply:
        for r in targets:
            subj, body = email_msg.build_email(r, sender)
            database.update_prospect(r["id"], {"email_subject": subj, "email_body": body})
            database.add_event(r["id"], "email_regenerated", "modelo honesto")
        print(f"\nAtualizados: {len(targets)}")
    elif targets:
        print("\nPara aplicar: python tools/regerar_emails.py --apply")


if __name__ == "__main__":
    main()
