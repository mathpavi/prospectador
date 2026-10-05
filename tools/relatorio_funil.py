"""Relatorio do funil (F4 do PLANO_PROSPECTADOR). SOMENTE LEITURA.

Na VPS (Console do EasyPanel, shell Sh):   python tools/relatorio_funil.py
Local, apontando para um banco:           DB_PATH=caminho\\prospector.db python tools/relatorio_funil.py
Opcoes:  --dias 30   janela dos eventos recentes      --json   saida em JSON
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import validators  # noqa: E402

NOT_A_SITE = ("telelistas", "guiamais", "solutudo", "apontador", "econodata", "cnpj.biz", "casadosdados", "facebook", "instagram", "linkedin")


def connect():
    db = os.environ.get("DB_PATH") or os.path.join(os.environ.get("DATA_DIR", ROOT), "prospector.db")
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con, db


def table_exists(con, name):
    return bool(con.execute("select 1 from sqlite_master where type='table' and name=?", (name,)).fetchone())


def has_col(con, table, col):
    return col in [r[1] for r in con.execute(f"pragma table_info({table})")]


def build(days):
    con, db = connect()
    q = lambda s, *a: con.execute(s, a).fetchall()  # noqa: E731
    out = {"banco": db}
    total = q("select count(*) c from prospects")[0]["c"]
    out["total_prospects"] = total
    out["por_status"] = {r["status"]: r["c"] for r in q("select status, count(*) c from prospects group by 1 order by 2 desc")}

    # contatos
    out["contatos"] = {
        "com_email": q("select count(*) c from prospects where contact_email is not null and contact_email!=''")[0]["c"],
        "com_whatsapp": q("select count(*) c from prospects where contact_whatsapp is not null and contact_whatsapp!=''")[0]["c"],
        "sem_nenhum_contato": q("select count(*) c from prospects where (contact_email is null or contact_email='') and "
                                "(contact_whatsapp is null or contact_whatsapp='') and (contact_phone is null or contact_phone='')")[0]["c"],
    }
    bad = Counter()
    for r in q("select contact_email from prospects where contact_email is not null and contact_email!=''"):
        st, why = validators.check_syntax(r["contact_email"])
        if st != "valid":
            bad[why] += 1
    out["emails_invalidos_por_motivo"] = dict(bad)

    # envios por dia
    use_events = table_exists(con, "events") and q("select count(*) c from events where type='email_sent'")[0]["c"] > 0
    if use_events:
        rows = q("select substr(created_at,1,10) d, count(*) c from events where type='email_sent' group by 1 order by 1 desc limit ?", days)
    else:
        rows = q("select substr(sent_at,1,10) d, count(*) c from prospects where sent_at is not null and sent_at!='' group by 1 order by 1 desc limit ?", days)
    out["envios_por_dia"] = [(r["d"], r["c"]) for r in rows]
    out["total_enviados"] = out["por_status"].get("sent", 0)

    # falhas
    out["falhas_por_motivo"] = [(r["e"], r["c"]) for r in q(
        "select substr(error_message,1,80) e, count(*) c from prospects where error_message is not null and error_message!='' group by 1 order by 2 desc limit 8")]

    # segmentos
    seg = []
    for r in q("select segment, count(*) total, sum(status='sent') enviados, sum(status='failed') falhas, sum(status='rejected') rejeitados "
               "from prospects group by segment order by total desc limit 14"):
        seg.append(dict(r))
    out["segmentos"] = seg

    # fila
    fila = q("select contact_email, website from prospects where status in ('approved','pending') and contact_email is not null and contact_email!=''")
    inval = sum(1 for r in fila if validators.check_syntax(r["contact_email"])[0] != "valid")
    dirs = sum(1 for r in fila if any(d in (r["website"] or "").lower() for d in NOT_A_SITE))
    out["fila"] = {"com_email_aprovados_ou_pendentes": len(fila), "emails_invalidos": inval, "site_e_diretorio": dirs}

    # follow-up
    out["followup"] = {r["followup_status"]: r["c"] for r in q("select followup_status, count(*) c from prospects group by 1")}
    if has_col(con, "prospects", "whatsapp_contacted"):
        out["whatsapp_contatados"] = q("select count(*) c from prospects where whatsapp_contacted=1")[0]["c"]

    # resultados
    if has_col(con, "prospects", "stage"):
        out["estagios"] = {str(r["stage"]): r["c"] for r in q("select stage, count(*) c from prospects where stage is not null group by 1")}
        wins = q("select id, company_name, deal_value, win_source, closed_at from prospects where stage='ganho'")
        out["ganhos"] = [dict(w) for w in wins]
        out["taxa_ganho_sobre_enviados"] = round(100 * len(wins) / out["total_enviados"], 2) if out["total_enviados"] else None

    # eventos recentes
    if table_exists(con, "events"):
        out["eventos_recentes"] = {r["type"]: r["c"] for r in q(
            "select type, count(*) c from events where created_at >= date('now', ?) group by 1 order by 2 desc", f"-{days} day")}
        out["descadastros"] = q("select count(*) c from events where type='stage:descadastrou'")[0]["c"]
        # auditoria: o que as portas automaticas barraram (para achar falso positivo)
        out["rejeicoes_automaticas"] = [dict(r) for r in q(
            "select e.created_at, e.type, e.detail, p.id pid, p.company_name from events e left join prospects p on p.id = e.prospect_id "
            "where e.type in ('qualification_rejected','email_not_qualified','email_invalid','email_blocked') order by e.id desc limit 12")]
    if table_exists(con, "suppressions"):
        out["lista_de_bloqueio"] = q("select count(*) c from suppressions")[0]["c"]

    # esbocos
    try:
        from mockups import store
        mdb = os.path.join(store.data_dir(), "mockups.db")
        if os.path.exists(mdb):
            m = sqlite3.connect("file:" + mdb.replace("\\", "/") + "?mode=ro", uri=True)
            m.row_factory = sqlite3.Row
            out["esbocos"] = {"por_status": {r["status"]: r["c"] for r in m.execute("select status, count(*) c from mockups group by 1")},
                              "visitas_total": m.execute("select coalesce(sum(views),0) v from mockups").fetchone()["v"],
                              "mais_vistos": [dict(r) for r in m.execute("select company, views, last_view_at from mockups where views>0 order by views desc limit 5")]}
    except Exception:  # noqa: BLE001
        pass

    # alertas
    alertas = []
    ev = out.get("eventos_recentes", {})
    sent_recent, bounced = ev.get("email_sent", 0), ev.get("email_bounced", 0)
    if sent_recent >= 20 and bounced / sent_recent > 0.03:
        alertas.append(f"Rejeicoes definitivas em {100 * bounced / sent_recent:.1f}% dos envios recentes (limite saudavel: ate ~3%). Pare e limpe a lista.")
    if ev.get("email_blocked_by_provider", 0):
        alertas.append(f"{ev['email_blocked_by_provider']} envio(s) bloqueado(s) pelo provedor por spam/reputacao. Verifique SPF/DKIM/DMARC e reduza o volume.")
    if out["fila"]["emails_invalidos"]:
        alertas.append(f"{out['fila']['emails_invalidos']} e-mail(s) invalido(s) na fila. Rode: python tools/limpar_emails.py")
    if not table_exists(con, "events"):
        alertas.append("Tabela de eventos ainda nao existe: faca o deploy da versao nova (o app a cria ao iniciar).")
    out["alertas"] = alertas
    return out


def show(o, days):
    L = lambda t: print(f"\n=== {t} ===")  # noqa: E731
    print(f"Banco: {o['banco']}")
    L("Prospects")
    print(f"Total: {o['total_prospects']}")
    for k, v in o["por_status"].items():
        print(f"  {str(k):12} {v}")
    L("Contatos")
    c = o["contatos"]
    print(f"  com e-mail {c['com_email']} | com WhatsApp {c['com_whatsapp']} | sem nenhum contato {c['sem_nenhum_contato']}")
    if o["emails_invalidos_por_motivo"]:
        print("  e-mails com problema de sintaxe:", o["emails_invalidos_por_motivo"])
    L(f"Envios por dia (ultimos {days} dias com envio) | total enviados: {o['total_enviados']}")
    for d, n in o["envios_por_dia"]:
        print(f"  {d}  {n}")
    L("Falhas mais comuns")
    for e, n in o["falhas_por_motivo"]:
        print(f"  {n:4} {e}")
    L("Segmentos (total / enviados / falhas / rejeitados)")
    for s in o["segmentos"]:
        print(f"  {str(s['segment'])[:34]:34} {s['total']:4} {s['enviados'] or 0:4} {s['falhas'] or 0:4} {s['rejeitados'] or 0:4}")
    L("Fila de envio (aprovados/pendentes com e-mail)")
    print("  ", o["fila"])
    L("Follow-up")
    print("  ", o["followup"], "| WhatsApp contatados:", o.get("whatsapp_contatados", "-"))
    if "estagios" in o:
        L("Resultados")
        print("  estagios:", o["estagios"] or "(nenhum registrado ainda: use tools/marcar_resultado.py)")
        for w in o["ganhos"]:
            print(f"  GANHO #{w['id']} {w['company_name']} | valor {w['deal_value']} | origem {w['win_source']} | {w['closed_at']}")
        if o["taxa_ganho_sobre_enviados"] is not None:
            print(f"  taxa de ganho sobre enviados: {o['taxa_ganho_sobre_enviados']}%")
    if "eventos_recentes" in o:
        L(f"Eventos dos ultimos {days} dias")
        print("  ", o["eventos_recentes"] or "(nenhum ainda)", "| descadastros (total):", o.get("descadastros", 0))
    if o.get("rejeicoes_automaticas"):
        L("Ultimas rejeicoes automaticas (confira se alguma e falso positivo)")
        for r in o["rejeicoes_automaticas"]:
            print(f"  {r['created_at']}  #{r['pid']} {str(r['company_name'])[:28]:28} {r['type']:24} {(r['detail'] or '')[:70]}")
    if "lista_de_bloqueio" in o:
        print(f"  lista de bloqueio: {o['lista_de_bloqueio']} endereco(s)")
    if "esbocos" in o:
        L("Esbocos de site")
        print("  ", o["esbocos"])
    L("ALERTAS")
    print("\n".join("  ! " + a for a in o["alertas"]) if o["alertas"] else "  nenhum")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    data = build(a.dias)
    print(json.dumps(data, ensure_ascii=False, indent=1, default=str)) if a.json else show(data, a.dias)
