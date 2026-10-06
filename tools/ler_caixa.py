"""T3: le a caixa de entrada e mostra o que mudaria no funil (respostas, rejeicoes, pedidos de SAIR).

  python tools/ler_caixa.py              simulacao: nao altera nada
  python tools/ler_caixa.py --apply      aplica ao funil (estagios, bloqueios, eventos)
  python tools/ler_caixa.py --dias 30    olha mais para tras (padrao 14 dias)

Somente LEITURA da caixa: nao marca como lida e nao apaga nada. Usa o mesmo usuario/senha do SMTP.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import database  # noqa: E402
import inbox  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dias", type=int, default=14)
    a = ap.parse_args()
    database.init_db()
    try:
        st = inbox.check_inbox(dry=not a.apply, days=a.dias)
    except Exception as e:  # noqa: BLE001
        print("Nao consegui ler a caixa:", e)
        print("Confira em Configuracoes: usuario/senha de e-mail e o servidor IMAP (imap_host, padrao imap.hostinger.com).")
        return
    print(f"Mensagens lidas: {st['lidas']} | relevantes para o funil: {st['novas']}" + ("" if a.apply else "  (SIMULACAO: nada foi alterado)"))
    for line in st["acoes"]:
        print(" -", line)
    if not a.apply and st["acoes"]:
        print("\nPara aplicar: python tools/ler_caixa.py --apply")


if __name__ == "__main__":
    main()
