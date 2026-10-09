"""Importa leads dos dados abertos de CNPJ da Receita Federal (gratuito, sem limite de creditos).

No Console (Sh) do EasyPanel. Como leva um tempo (baixa uns 7 GB, um arquivo por vez, e apaga depois de ler), rode em segundo plano:

  nohup python tools/importar_cnpj.py --importar --limite 3000 > /app/data/importar_cnpj.log 2>&1 &
  tail -f /app/data/importar_cnpj.log          (Ctrl+C sai do acompanhamento; a importacao continua)

Opcoes:
  (sem opcoes)         so conta quantos leads existiriam, por segmento e cidade; NAO grava nada
  --importar           grava os leads no prospectador (status pendente, sem site; o piloto procura o site e aprova depois)
  --limite N           grava no maximo N leads novos nesta rodada (padrao 3000)
  --ufs RS,SC,PR       estados (padrao: sul)
  --segmentos A,B      so estes segmentos (padrao: todos)
  --mes AAAA-MM        mes dos dados (padrao: o mais recente)
  --so-com-email       ignora quem nao tem e-mail da empresa (e-mail de contador ja e ignorado sempre)
Pode ser interrompido e retomado: os arquivos ja lidos ficam registrados.
"""
import argparse
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cnpj_import as C  # noqa: E402


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--importar", action="store_true")
    ap.add_argument("--limite", type=int, default=3000)
    ap.add_argument("--ufs", default=",".join(C.SUL))
    ap.add_argument("--segmentos", default="")
    ap.add_argument("--mes", default="")
    ap.add_argument("--so-com-email", action="store_true")
    a = ap.parse_args()
    ufs = [u.strip().upper() for u in a.ufs.split(",") if u.strip()]
    wanted = {s.strip().lower() for s in a.segmentos.split(",") if s.strip()}

    con = C.open_stage()
    month = a.mes or C.latest_month()
    if not month:
        say("Nao consegui falar com o servidor da Receita (verifique a internet da VPS).")
        return
    files = set(C.list_files(month))
    say(f"Dados abertos de {month}: {len(files)} arquivos. Estados: {', '.join(ufs)}")
    tmp = os.path.join(os.path.dirname(C.stage_path()), "cnpj_tmp")
    done = {r[0] for r in con.execute("SELECT arquivo FROM done")}

    if "Municipios.zip" in files:
        z = C.download(month, "Municipios.zip", tmp)
        say("municipios:", C.load_municipios(z, con))
        os.remove(z)

    for i in range(10):
        name = f"Estabelecimentos{i}.zip"
        key = f"{month}/{name}/{','.join(sorted(ufs))}"
        if name not in files or key in done:
            continue
        say(f"baixando {name} ...")
        z = C.download(month, name, tmp, progress=lambda g, t: say(f"   {g // (1 << 20)} de {t // (1 << 20)} MB"))
        say(f"lendo {name} ...")
        lin, kept = C.scan_estabelecimentos(z, con, ufs, name=key, progress=lambda l, k: say(f"   {l:,} linhas lidas, {k:,} leads") if l % 1000000 < 5000 else None)
        os.remove(z)
        say(f"{name}: {lin:,} linhas, {kept:,} empresas dos segmentos-alvo")

    for i in range(10):
        name = f"Empresas{i}.zip"
        key = f"{month}/{name}/{','.join(sorted(ufs))}"
        if name not in files or key in done:
            continue
        say(f"baixando {name} ...")
        z = C.download(month, name, tmp)
        n = C.scan_empresas(z, con, name=key)
        os.remove(z)
        say(f"{name}: {n:,} razoes sociais associadas")
    shutil.rmtree(tmp, ignore_errors=True)

    cands = C.candidates(con, only_with_email=a.so_com_email)
    if wanted:
        cands = [c for c in cands if c["segment"].lower() in wanted]
    with_email = [c for c in cands if c["email"]]
    with_wa = [c for c in cands if c["whatsapp"]]
    say(f"\nLeads possiveis: {len(cands):,}  (com e-mail da empresa: {len(with_email):,} | com celular/WhatsApp: {len(with_wa):,}; e-mails de contador ja descartados)")
    by_seg, by_city = {}, {}
    for c in cands:
        by_seg[c["segment"]] = by_seg.get(c["segment"], 0) + 1
        k = f"{c['city']} - {c['uf']}"
        by_city[k] = by_city.get(k, 0) + 1
    say("Por segmento:")
    for k, v in sorted(by_seg.items(), key=lambda kv: -kv[1]):
        print(f"   {v:6,}  {k}")
    say("Principais cidades:")
    for k, v in sorted(by_city.items(), key=lambda kv: -kv[1])[:15]:
        print(f"   {v:6,}  {k}")

    if not a.importar:
        say("\n(so contagem: nada foi gravado. Para gravar, rode de novo com --importar)")
        return
    cands.sort(key=lambda c: (not c["email"], not c["whatsapp"], c["city"]))          # primeiro quem tem e-mail da empresa e celular
    import database
    database.init_db()
    new, dup = C.to_prospects(cands, limit=a.limite)
    C.mark_imported(con, [c["cnpj"] for c in cands[:new + dup]])
    say(f"\nGravados {new:,} leads novos ({dup:,} ja existiam). O piloto vai procurar o site de cada um e aprovar os que tiverem e-mail.")


if __name__ == "__main__":
    main()
