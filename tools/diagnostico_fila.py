"""S7 do PLANO_PROSPECTADOR: por que a fila de envio esta vazia? SOMENTE LEITURA (a menos que use --aprovar).

  python tools/diagnostico_fila.py             mostra, por segmento, onde os leads estao parados e o que fazer
  python tools/diagnostico_fila.py --aprovar   aprova os leads 'pending' com e-mail que passam em todas as portas (nao envia nada)
  DB_PATH=caminho\\prospector.db python tools/diagnostico_fila.py     para olhar outro banco (local)
"""
import argparse
import os
import sqlite3
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def connect(write=False):
    db = os.environ.get("DB_PATH") or os.path.join(os.environ.get("DATA_DIR", ROOT), "prospector.db")
    uri = "file:" + db.replace("\\", "/") + ("?mode=rw" if write else "?mode=ro")
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con, db


import re  # noqa: E402
TRANSIENT = re.compile(r"timed out|timeout|connection|conex|forçado|forcado|reset|temporar|try again|(?<!\d)4[25]\d(?!\d)|4\.\d\.\d|greylist", re.I)
PERMANENT = re.compile(r"(?<!\d)5\d\d(?!\d)|5\.\d\.\d|does not exist|no such user|user unknown|n[aã]o existe|invalid", re.I)


def reason(p, suppressed, validators, database):
    """(grupo, motivo curto) de por que o lead NAO esta na fila de envio."""
    st = p["status"]
    email = (p["contact_email"] or "").strip()
    if st == "sent":
        return "enviado", "ja recebeu e-mail"
    if st == "approved":
        return "na_fila", "aprovado: sera enviado"
    if not email:
        has_wa = bool((p["contact_whatsapp"] or p["contact_phone"] or "").strip())
        return "sem_email", "sem e-mail" + (" (tem telefone/WhatsApp: use a Central WhatsApp)" if has_wa else " e sem telefone")
    s, why = validators.check_syntax(email)
    if s != "valid":
        return "email_ruim", f"e-mail invalido ({why})"
    if email.lower() in suppressed or email.lower().rsplit("@", 1)[-1] in suppressed:
        return "bloqueado", "e-mail na lista de bloqueio"
    if st == "rejected":
        return "rejeitado", (p["error_message"] or "rejeitado pelas portas de qualidade")[:70]
    if st == "failed":
        return "falhou", (p["error_message"] or "falha no envio")[:70]
    if st == "pending":
        ok, why = database.approval_gate(dict(p))
        return ("pendente_ok", "pendente com e-mail valido: pode ser aprovado") if ok else ("pendente_barrado", f"pendente barrado: {why}")
    return "outro", f"status {st}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aprovar", action="store_true")
    ap.add_argument("--reenviar-falhas", action="store_true", help="devolve para a fila os leads que falharam por erro TEMPORARIO (rede, timeout, 4xx)")
    a = ap.parse_args()
    import database
    import validators
    con, db = connect(write=a.aprovar or a.reenviar_falhas)
    rows = con.execute("select * from prospects where coalesce(is_international,0)=0").fetchall()
    supp = {r[0].lower() for r in con.execute("select value from suppressions")} if con.execute("select 1 from sqlite_master where name='suppressions'").fetchone() else set()
    grupos, por_seg, motivos = Counter(), defaultdict(Counter), Counter()
    aprovaveis, transit = [], []
    for p in rows:
        g, m = reason(p, supp, validators, database)
        grupos[g] += 1
        por_seg[(p["segment"] or "-").strip().title()][g] += 1
        if g in ("rejeitado", "falhou", "pendente_barrado", "sem_email", "email_ruim"):
            motivos[(g, m)] += 1
        if g == "pendente_ok":
            aprovaveis.append(p["id"])
        if g == "falhou" and TRANSIENT.search(p["error_message"] or "") and not PERMANENT.search(p["error_message"] or ""):
            transit.append(p["id"])
    print(f"Banco: {db}\nLeads nacionais: {len(rows)}\n")
    nomes = {"enviado": "ja enviados", "na_fila": "NA FILA (aprovados)", "pendente_ok": "pendentes que podem ser aprovados agora", "pendente_barrado": "pendentes barrados pelas portas",
             "sem_email": "sem e-mail", "email_ruim": "e-mail invalido", "bloqueado": "e-mail bloqueado", "rejeitado": "rejeitados", "falhou": "falha no envio", "outro": "outros"}
    for g, n in grupos.most_common():
        print(f"  {n:5}  {nomes.get(g, g)}")
    print("\nPor segmento (enviado / na fila / aprovavel agora / sem e-mail / rejeitado+falhou):")
    for seg, c in sorted(por_seg.items(), key=lambda kv: -sum(kv[1].values()))[:15]:
        print(f"  {seg[:28]:28} total {sum(c.values()):4} | {c['enviado']:4} / {c['na_fila']:3} / {c['pendente_ok']:3} / {c['sem_email']:4} / {c['rejeitado'] + c['falhou'] + c['pendente_barrado']:4}")
    print("\nPrincipais motivos que seguram leads:")
    for (g, m), n in motivos.most_common(10):
        print(f"  {n:5}  {m}")
    sat = [(seg, c) for seg, c in por_seg.items() if sum(c.values()) >= 15 and (c["enviado"] + c["na_fila"]) / sum(c.values()) >= 0.6]
    if sat:
        print("\nSegmentos ja bem trabalhados (60%+ ja enviados): " + ", ".join(f"{seg} ({sum(c.values())})" for seg, c in sat))
    print("\nO que fazer:")
    if aprovaveis:
        print(f"  1) {len(aprovaveis)} lead(s) pendente(s) com e-mail valido podem entrar na fila agora: rode com --aprovar.")
    if grupos["sem_email"]:
        print(f"  2) {grupos['sem_email']} lead(s) sem e-mail: os que tem celular seguem pela Central WhatsApp (nao precisam de e-mail).")
    if grupos["falhou"]:
        print(f"  3) {grupos['falhou']} lead(s) com falha de envio: veja o motivo acima; falhas de rede podem ser reenviadas, endereco inexistente nao.")
    if transit:
        print(f"  3b) {len(transit)} falha(s) parecem TEMPORARIAS (rede/timeout): rode com --reenviar-falhas para devolve-las a fila.")
    if sat:
        print("  3c) Para ter mais leads novos, diversifique a busca: segmentos/cidades ainda pouco explorados (veja a tabela) em vez de repetir os ja saturados.")
    if not (aprovaveis or grupos["na_fila"]):
        print("  4) Nao ha leads aprovaveis nem na fila: o gargalo e a BUSCA. Aumente o lote de busca, inclua novas cidades/segmentos nos alvos do piloto.")
    if a.aprovar:
        if aprovaveis:
            con.executemany("update prospects set status='approved', updated_at=datetime('now') where id=? and status='pending'", [(i,) for i in aprovaveis])
            con.commit()
        print(f"\n{len(aprovaveis)} lead(s) aprovado(s) (passaram nas portas: e-mail valido, nao bloqueado, site proprio). Nada foi enviado.")
    if a.reenviar_falhas:
        if transit:
            con.executemany("update prospects set status='approved', error_message=NULL, updated_at=datetime('now') where id=? and status='failed'", [(i,) for i in transit])
            con.commit()
        print(f"\n{len(transit)} lead(s) com falha temporaria voltaram para a fila.")
    if not (a.aprovar or a.reenviar_falhas) and (aprovaveis or transit):
        print("\n(simulacao: nada foi alterado)")


if __name__ == "__main__":
    main()
