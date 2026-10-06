"""Higiene dos dados ja gravados (Q4 nomes de empresa e Q5 segmentos do PLANO_PROSPECTADOR).

  python tools/corrigir_dados.py            SIMULACAO: mostra o que mudaria (nao grava nada)
  python tools/corrigir_dados.py --apply    grava as correcoes
Nomes: 'Sobre', 'Pagina Inicial', 'e de arroz'... viram o nome tirado do dominio ('metalurgicabitello.com.br' -> 'Metalurgica Bitello').
Segmentos: 'metalurgica' e 'Metalurgica' passam a ser o mesmo (espacos limpos, 1a letra maiuscula).
Nunca altera o historico de envios, e-mails ou eventos; so os campos company_name e segment.
"""
import argparse
import collections
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database  # noqa: E402
import whatsapp_msg  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    database.init_db()
    conn = database.get_db_connection()
    rows = conn.execute("select id, company_name, website, segment from prospects").fetchall()

    names, segs = [], collections.Counter()
    for r in rows:
        if whatsapp_msg.is_junk_name(r["company_name"]):
            new = whatsapp_msg.brand_from_domain(r["website"])
            if new and new != r["company_name"]:
                names.append((r["id"], r["company_name"], new, r["website"]))
        ns = database.normalize_segment(r["segment"])
        if ns != (r["segment"] or ""):
            segs[(r["segment"], ns)] += 1

    print(f"Modo: {'APLICANDO' if a.apply else 'simulacao (nada sera gravado)'} | prospects: {len(rows)}")
    print(f"\nNomes de empresa a corrigir: {len(names)}")
    for pid, old, new, site in names[:40]:
        print(f"  #{pid:5} {str(old)[:30]:30} -> {new:34} ({site})")
    if len(names) > 40:
        print(f"  ... e mais {len(names) - 40}")
    print(f"\nSegmentos a unificar: {sum(segs.values())} prospects em {len(segs)} grafias")
    for (old, new), n in segs.most_common(25):
        print(f"  {n:4}  {old!r:34} -> {new!r}")

    if a.apply:
        for pid, old, new, _ in names:
            database.update_prospect(pid, {"company_name": new})
            database.add_event(pid, "name_fixed", f"{old} -> {new}")
        for r in rows:
            ns = database.normalize_segment(r["segment"])
            if ns != (r["segment"] or ""):
                database.update_prospect(r["id"], {"segment": ns})
        print("\nGravado.")
    elif names or segs:
        print("\nPara aplicar: python tools/corrigir_dados.py --apply")
    conn.close()


if __name__ == "__main__":
    main()
