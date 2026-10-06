"""C3: prorroga a validade de um esboco (quando o lead pede mais tempo).

  python tools/prorrogar_esboco.py                lista os esbocos prontos e quando vencem
  python tools/prorrogar_esboco.py TOKEN 7        prorroga o esboco TOKEN por mais 7 dias
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mockups import store  # noqa: E402


def main():
    if len(sys.argv) >= 2:
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        new = store.extend(sys.argv[1], days)
        print("esboco nao encontrado" if not new else f"ok: vence agora em {datetime.fromtimestamp(new):%d/%m/%Y %H:%M}")
        return
    for m in store.list_all():
        if m["status"] == "ready":
            left = (m["expires_at"] - time.time()) / 86400
            print(f"{m['token']}  {m['company'][:34]:34}  aberturas={m['views']:<3}  {'vence em %.1f dia(s)' % left if left > 0 else 'VENCIDO'}")


if __name__ == "__main__":
    main()
