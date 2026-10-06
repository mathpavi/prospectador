"""Comando unico: prospect -> extrai -> portas de qualidade -> textos -> pagina -> miniatura -> registro.

Exemplos (na pasta raiz do prospectador):
  python mockups/make_mockup.py --prospect-id 719 --slots-file mockups/_work/kleiner/slots_industrial_escuro.json
  python mockups/make_mockup.py --prospect-id 719 --provider gemini        (exige GEMINI_API_KEY no ambiente)
  python mockups/make_mockup.py --list
  python mockups/make_mockup.py --approve <token>      # libera um esboco que ficou em 'review'
  python mockups/make_mockup.py --revoke <token>
"""
import argparse
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import extract as ex_mod  # noqa: E402
import fill as fill_mod  # noqa: E402
import judge as judge_mod  # noqa: E402
import render as render_mod  # noqa: E402
import store  # noqa: E402

MIN_SCORE = 7          # de 11: abaixo disso nao ha conteudo real para uma hero especifica
BASE_URL = os.environ.get("MOCKUP_BASE_URL", "http://localhost:5055")

# "sites" que na verdade sao diretorios, redes sociais ou agregadores: nao ha site proprio para extrair
DIRECTORY_RE = re.compile(r"telelistas|guiamais|solutudo|apontador|econodata|cnpj\.biz|casadosdados|cnpja|facebook|instagram|"
                          r"linkedin|google\.|youtube|linktr\.ee|wa\.me|olx\.|mercadolivre|tiktok|twitter|(^|\.)x\.com", re.I)


def is_directory_url(url):
    from urllib.parse import urlparse
    return bool(DIRECTORY_RE.search(urlparse(url or "").netloc))


def pick_template(segment, prospect_id=0):
    """Mapa segmento -> template. None = ainda sem template adequado (vai para revisao).
    Industriais alternam entre escuro e claro (por id), para vizinhas nao receberem esbocos iguais."""
    s = (segment or "").lower()
    if re.search(r"metal|usina|caldeir|repux|serralh|a[cç]o|soldag|alum[ií]n|esquadri|vidra|marcen", s):
        return "industrial_escuro" if prospect_id % 2 == 0 else "industrial_claro"
    if re.search(r"pl[aá]stic|t[eê]xtil|m[oó]vei|aliment|pap[eé]l|pap[eé]is|embalag|confec|cal[cç]ad", s):
        return "vitrine_produto"
    if re.search(r"limpez|clean|marmor|panific|padaria|seguran|distribuidor|log[ií]stic|transport|chaveir|dedetiz|jardin|lavander|mudan[cç]", s):
        return "servico_local"
    if re.search(r"advog|m[eé]dic|cl[ií]nic|est[eé]tic|odont|psic|contab|arquitet|fisio|nutri|dentist", s):
        return "servicos_profissionais"
    return None


def load_prospect(pid):
    # na VPS o banco fica em DATA_DIR (/app/data); localmente, na raiz do projeto
    db = os.environ.get("DB_PATH") or os.path.join(os.environ.get("DATA_DIR", ROOT), "prospector.db")
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)   # somente leitura
    con.row_factory = sqlite3.Row
    r = con.execute("select id, company_name, website, segment, region, screenshot from prospects where id=?", (pid,)).fetchone()
    if not r:
        sys.exit(f"prospect {pid} nao encontrado")
    return dict(r)


def make(prospect, provider=None, slots_file=None, days=21, forced_template=None, judge=None):
    token = secrets.token_urlsafe(12)
    out_dir = os.path.join(store.data_dir(), token)
    work = tempfile.mkdtemp(prefix="mk_")
    reasons, status = [], "ready"
    judge = judge_mod.enabled() if judge is None else judge
    try:
        if is_directory_url(prospect.get("website")):
            why = "o 'site' cadastrado e um diretorio/rede social, nao o site da empresa"
            store.create(token, prospect["id"], prospect["company_name"], "-", "review", why, 0, days)
            return token, "review", [why]
        shot = os.path.join(ROOT, "static", "screenshots", prospect.get("screenshot") or "")
        ex = ex_mod.extract(prospect["website"], shot, save_dir=work, brand=prospect["company_name"])
        if not ex.get("ok"):
            store.create(token, prospect["id"], prospect["company_name"], "-", "review", "site nao baixou", 0, days)
            return token, "review", ["site nao baixou"]

        score = ex["data_score"]["points"]
        if not ex.get("images"):
            reasons.append("sem foto real da empresa (a hero ficaria generica)")
        if score < MIN_SCORE:
            reasons.append(f"dados insuficientes ({score}/{ex['data_score']['max']}: {', '.join(ex['data_score']['missing'])})")
        template = forced_template or pick_template(prospect.get("segment"), prospect["id"])
        if not template:
            reasons.append(f"sem template para o segmento '{prospect.get('segment')}'")
            template = "industrial_escuro"      # so para ter uma previa local; nao sera servido

        if judge and not reasons:        # etapa 1 (barata): se o site atual ja e muito bom, nem gera
            skip, nota, why, cost = judge_mod.judge_site_only(prospect, work, saved_shot=shot)
            if skip:
                store.create(token, prospect["id"], prospect["company_name"], "-", "review", why, score, days)
                print(f"custo do juiz: US$ {cost:.4f}")
                return token, "review", [why]

        if slots_file:
            slots = json.load(open(slots_file, encoding="utf-8"))
            usage = {"provider": "arquivo", "usd": 0}
        else:
            res = fill_mod.fill(prospect, ex, provider)
            slots, usage = res["slots"], res["usage"]
            reasons += res["fatal"]
            if not slots:        # resposta da IA inutilizavel: nao ha o que renderizar
                store.create(token, prospect["id"], prospect["company_name"], "-", "review", "; ".join(reasons), score, days)
                print(f"custo da IA: US$ {usage.get('usd', 0)} ({usage.get('model')})")
                return token, "review", reasons
            if res["problems"]:
                print("avisos:", res["problems"])

        og = {"title": f"Proposta visual · {slots.get('brand_name', '')}", "image": f"{BASE_URL}/p/{token}/thumb.png",
              "url": f"{BASE_URL}/p/{token}/"}
        idx = render_mod.render(template, slots, work, out_dir, og=og)
        render_mod.screenshot(idx, os.path.join(out_dir, "thumb.png"), 1200, 630, full=False)
        if judge and not reasons:        # etapa 2: o esboco precisa ser REALMENTE melhor que o site atual
            keep = {}
            ok, why, ns, nm, cost = judge_mod.judge_mockup(prospect, idx, work, saved_shot=shot, keep=keep)
            print(f"juiz: {why} (US$ {cost:.4f})")
            if not ok:
                reasons.append(why)
        status = "review" if reasons else "ready"
        if status == "ready":        # M2: antes/depois (so para esbocos que serao servidos)
            judge_mod.write_compare(prospect, idx, work, out_dir, keep=locals().get("keep"), saved_shot=shot)
        store.create(token, prospect["id"], prospect["company_name"], template, status, "; ".join(reasons), score, days)
        print(f"custo da IA: US$ {usage.get('usd', 0)} ({usage.get('model') or usage.get('provider')})")
        return token, status, reasons
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prospect-id", type=int)
    ap.add_argument("--provider", choices=list(fill_mod.MODELS))
    ap.add_argument("--slots-file")
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--template", help="forca um template (ex.: industrial_claro); padrao: escolhido pelo segmento")
    ap.add_argument("--no-judge", action="store_true", help="nao compara com o site atual (M4); so para testes")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--find", nargs="?", const="", metavar="TEXTO",
                    help="lista prospects (id, segmento, nome, site); TEXTO filtra por segmento ou nome. Ex.: --find metal")
    ap.add_argument("--approve")
    ap.add_argument("--revoke")
    a = ap.parse_args()

    if a.find is not None:
        db = os.environ.get("DB_PATH") or os.path.join(os.environ.get("DATA_DIR", ROOT), "prospector.db")
        con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)    # somente leitura
        like = f"%{a.find}%"
        rows = con.execute("select id, segment, company_name, website from prospects "
                           "where website like 'http%' and (segment like ? or company_name like ?) "
                           "order by id desc limit 400", (like, like)).fetchall()
        rows = [r for r in rows if not is_directory_url(r[3])][:15]      # so prospects com site proprio
        for r in rows:
            print(f"{r[0]:5} | {str(r[1])[:22]:22} | {str(r[2])[:34]:34} | {r[3]}")
        print("\nUse: python mockups/make_mockup.py --prospect-id NUMERO --provider gemini")
    elif a.list:
        for m in store.list_all():
            print(f"{m['token']}  {m['status']:7} aberturas={m['views']:<3} {m['company']}  {m['reason'] or ''}")
    elif a.approve:
        store.set_status(a.approve, "ready", "aprovado manualmente"); print("liberado:", f"{BASE_URL}/p/{a.approve}/")
    elif a.revoke:
        store.set_status(a.revoke, "revoked", "revogado"); print("revogado")
    elif a.prospect_id:
        if not (a.provider or a.slots_file):
            sys.exit("informe --provider (gemini|anthropic) ou --slots-file")
        t, st, why = make(load_prospect(a.prospect_id), a.provider, a.slots_file, a.days, a.template, judge=False if a.no_judge else None)
        print("token:", t, "| status:", st)
        for w in why:
            print(" - revisar:", w)
        if st == "ready":
            print("link:", f"{BASE_URL}/p/{t}/")
    else:
        ap.print_help()
