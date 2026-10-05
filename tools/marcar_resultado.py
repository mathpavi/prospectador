"""Registra o resultado comercial de um prospect (T2 do PLANO_PROSPECTADOR).

Achar o prospect:   python tools/marcar_resultado.py --buscar "bitello"
Marcar ganho:       python tools/marcar_resultado.py --id 123 --estagio ganho --valor 1800 --origem email --nota "fechou apos ligacao"
Outros estagios:    novo, contatado, respondeu, interessado, reuniao, proposta, ganho, perdido, descadastrou, invalido
Ver historico:      python tools/marcar_resultado.py --id 123 --historico
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--buscar", help="texto do nome da empresa, e-mail ou site")
    ap.add_argument("--id", type=int)
    ap.add_argument("--estagio", choices=database.STAGES)
    ap.add_argument("--valor", type=float, help="valor do negocio em R$ (ganho)")
    ap.add_argument("--origem", help="como o cliente chegou: email, whatsapp, telefone, indicacao, ...")
    ap.add_argument("--nota")
    ap.add_argument("--historico", action="store_true")
    a = ap.parse_args()
    database.init_db()          # garante tabelas/colunas novas (idempotente)

    if a.buscar:
        like = f"%{a.buscar}%"
        conn = database.get_db_connection()
        rows = conn.execute("select id, company_name, status, stage, sent_at, contact_email, website from prospects "
                            "where company_name like ? or contact_email like ? or website like ? order by id desc limit 25", (like, like, like)).fetchall()
        conn.close()
        for r in rows:
            print(f"#{r['id']:5} {str(r['company_name'])[:32]:32} status={str(r['status']):9} estagio={str(r['stage']):10} enviado={r['sent_at'] or '-'} {r['contact_email'] or ''}")
        if not rows:
            print("nenhum prospect encontrado")
        return
    if not a.id:
        ap.print_help()
        return
    if a.historico:
        for e in database.get_events(a.id):
            print(f"{e['created_at']}  {e['type']:28} {e['detail'] or ''}")
        return
    if not a.estagio:
        sys.exit("informe --estagio (ou --historico)")
    database.set_stage(a.id, a.estagio, a.valor, a.nota, a.origem)
    p = database.get_prospect(a.id)
    print(f"ok: #{a.id} {p['company_name']} -> {a.estagio}" + (f" (R$ {a.valor:.2f})" if a.valor else ""))


if __name__ == "__main__":
    main()
