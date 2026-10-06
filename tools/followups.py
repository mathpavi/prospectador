"""C1: mostra (e, se pedido, envia) os follow-ups devidos agora.

  python tools/followups.py                  lista o que esta devido, com a mensagem de cada um (nao envia nada)
  python tools/followups.py --send 3         envia agora ate 3 follow-ups devidos (respeita bloqueios e o limite do dia)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database  # noqa: E402
import followup  # noqa: E402
import mailer  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", type=int, default=0)
    a = ap.parse_args()
    database.init_db()
    lst = followup.due_list()
    print(f"Follow-ups devidos agora: {len(lst)} | ligado: {followup.enabled()} | enviados hoje: {followup.sent_today()}")
    for it in lst[:15]:
        p = it["prospect"]
        subj, body = followup.build_followup(p, it["step"], mailer._sender_info(), followup._mockup_url(p["id"]))
        print(f"\n[{p['id']}] {p['company_name']} <{p['contact_email']}> | passo {it['step']}/3 | atraso {it['overdue_days']:.1f} dia(s)\n  Assunto: {subj}\n" + "\n".join("  " + l for l in body.splitlines()))
    sent = 0
    for it in lst[:max(a.send, 0)]:
        if not followup.can_send_today():
            print("\nLimite do dia atingido.")
            break
        try:
            followup.send_followup(it["prospect"]["id"], it["step"])
            sent += 1
            print(f"enviado: {it['prospect']['company_name']} (passo {it['step']})")
        except Exception as e:  # noqa: BLE001
            print(f"nao enviado: {it['prospect']['company_name']}: {e}")
    if a.send:
        print(f"\n{sent} follow-up(s) enviado(s).")


if __name__ == "__main__":
    main()
