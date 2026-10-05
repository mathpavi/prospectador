"""Gera os esbocos de site dos melhores contatos de WhatsApp (C9 do PLANO_PROSPECTADOR), para a mensagem sair com o link.

  python tools/preparar_esbocos_whatsapp.py --n 10 --dry-run     so lista quem seria atendido (nada e gerado)
  python tools/preparar_esbocos_whatsapp.py --n 10               gera ate 10 esbocos (cada um leva ~30-60 s e custa centavos de IA)
Escolhe, por ordem de prioridade, prospects com CELULAR, site proprio e sem esboco pronto. Quem nao passa nas portas de
qualidade do esboco (sem foto real, poucos dados...) fica em 'review' e a mensagem sai sem link.
Roda no Console do EasyPanel (shell Sh). Exige a chave do Gemini salva nas configuracoes do app.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "mockups"))
import database  # noqa: E402
import whatsapp_msg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--subtab", default="no_email", choices=["no_email", "email_sent", "all_pending"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    database.init_db()

    from mockups import store
    rows = database.get_whatsapp_candidates(a.subtab)
    have = store.ready_tokens([r["id"] for r in rows])
    sender = database.get_setting("sender_name", "Matheus Paviani")
    cand = []
    for r in rows:
        if r["id"] in have or not whatsapp_msg.has_own_site(r):
            continue
        lead = whatsapp_msg.enrich(r, "email_sent" if r.get("status") == "sent" else "no_email", None, sender)
        if lead["wa_mobile"]:
            cand.append(lead)
    cand.sort(key=lambda l: (l["wa_priority"], l["id"]), reverse=True)
    cand = cand[: a.n]
    print(f"Fila '{a.subtab}': {len(rows)} prospects | com celular + site proprio + sem esboco: {len(cand)} (limite {a.n})")
    for l in cand:
        print(f"  #{l['id']:5} prioridade {l['wa_priority']:3} {l['display_name'][:34]:34} {l['website']}")
    if a.dry_run or not cand:
        return

    import make_mockup
    ok = review = 0
    for l in cand:
        prospect = database.get_prospect(l["id"])
        print(f"\n>> #{l['id']} {l['display_name']} ...")
        try:
            token, status, why = make_mockup.make(prospect, provider="gemini")
        except SystemExit as e:                  # falha de configuracao (ex.: sem chave): para tudo
            print("PARANDO:", e)
            break
        except Exception as e:  # noqa: BLE001
            print("   falhou:", type(e).__name__, str(e)[:120])
            continue
        if status == "ready":
            ok += 1
            print(f"   pronto: {make_mockup.BASE_URL}/p/{token}/")
        else:
            review += 1
            print("   em revisao (a mensagem sai sem link):", "; ".join(why)[:140])
    print(f"\nResumo: {ok} prontos, {review} em revisao.")


if __name__ == "__main__":
    main()
