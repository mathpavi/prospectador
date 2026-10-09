"""Importador dos dados abertos de CNPJ da Receita Federal (fonte de leads gratuita e sem limite de creditos).

Fluxo (rodado de tools/importar_cnpj.py, em segundo plano, no Console da VPS):
  1) baixa os arquivos mensais (WebDAV publico da Receita), um por vez, e apaga depois de ler;
  2) Estabelecimentos: fica so com empresas ATIVAS dos estados pedidos (padrao: sul), CNAE dos segmentos-alvo, com e-mail ou telefone;
  3) Empresas: razao social, porte e natureza juridica das que sobraram;
  4) filtra e-mails de CONTADOR (ver `is_intermediary_email`) e grava os leads em `prospects` (status 'pending', sem site: o
     `site_finder` procura o site depois e so entao o lead pode ser aprovado).
Tudo fica em um banco de trabalho (`cnpj_stage.db`, em DATA_DIR); a importacao pode ser interrompida e retomada.
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import zipfile

csv.field_size_limit(10 ** 7)

WEBDAV = "https://arquivos.receitafederal.gov.br/public.php/webdav/"
SHARE_TOKEN = "YggdBLfdninEJX9"          # link publico oficial dos dados abertos de CNPJ (usuario = token, senha vazia)
SUL = ("RS", "SC", "PR")

# segmento do prospectador -> prefixos de CNAE (7 digitos). A ordem decide quando um CNAE cabe em mais de um segmento.
SEGMENT_CNAE = [
    ("Caldeiraria / Soldagem", ("2513", "2539001", "2539002")),
    ("Usinagem", ("2539",)),
    ("Esquadrias de Alumínio", ("2512",)),
    ("Serralheria", ("2542", "2511")),
    ("Metalúrgica", ("24", "251", "252", "2591", "2592", "2599", "2550")),
    ("Vidraçaria", ("2311", "2312", "2319", "4743")),
    ("Marmoraria", ("2391",)),
    ("Indústria de Plásticos", ("222",)),
    ("Fábrica de Móveis", ("31",)),
    ("Indústria Têxtil", ("13", "1412")),
    ("Panificadora", ("1091", "4721")),
    ("Serviços de Limpeza", ("8121", "8122", "8129")),
    ("Distribuidora / Logística", ("4930", "5211", "5212", "5229", "5250")),
    ("Advogado", ("6911",)),
    ("Segurança Eletrônica", ("8020",)),
    ("Clínica de Estética", ("9602502",)),
]

FREE_MAIL = {"gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.br", "bol.com.br", "uol.com.br", "terra.com.br", "icloud.com",
             "live.com", "msn.com", "globo.com", "ig.com.br", "oi.com.br", "zipmail.com.br", "r7.com", "protonmail.com"}
ACCOUNTING_WORDS = re.compile(r"contab|contador|contabil|escritorio|assessori|fiscal|bpo|tribut|despachante|folhapag|consultoria|"
                              r"cont[ae]\d|^cont@|^contabil|^fiscal@|^dp@|^rh@|^financeiro@|escrit", re.I)


def segment_for(cnae_principal, cnae_secundarios=""):
    """Segmento do prospectador para um CNAE (usa o principal; os secundarios so se o principal nao casar com nada)."""
    for code in [cnae_principal] + [c for c in (cnae_secundarios or "").split(",") if c]:
        code = re.sub(r"\D", "", code or "")
        if not code:
            continue
        for seg, prefixes in SEGMENT_CNAE:
            if any(code.startswith(p) for p in prefixes):
                return seg
        break          # principal sem segmento-alvo: nao procura nos secundarios (o negocio principal e outro)
    return None


def is_intermediary_email(email, count=1, domain_count=1):
    """True se o e-mail provavelmente NAO e da empresa: do contador/escritorio (palavras tipicas) ou o MESMO endereco em varios
    cadastros (contador/intermediario). A frequencia de dominio nao entra: dominios de provedores (brturbo, onda, via-rs...) sao
    compartilhados por milhares de pequenas empresas legitimas."""
    e = (email or "").strip().lower()
    if "@" not in e:
        return True
    local, domain = e.rsplit("@", 1)
    if ACCOUNTING_WORDS.search(local) or ACCOUNTING_WORDS.search(domain.split(".")[0]):
        return True
    return count >= 5


def clean_phone(ddd, tel):
    """DDD + telefone da Receita. O cadastro guarda 8 digitos; celular antigo (comeca com 6-9) ganha o 9 que faltava (vira 11 digitos)."""
    d, t = re.sub(r"\D", "", ddd or ""), re.sub(r"\D", "", tel or "")
    if len(d) != 2 or not t:
        return ""
    if len(t) == 8 and t[0] in "6789":
        t = "9" + t
    return d + t if len(t) in (8, 9) and len(d + t) in (10, 11) else ""


def titlecase_company(name):
    small = {"de", "da", "do", "das", "dos", "e", "em", "para", "com"}
    out = []
    for i, w in enumerate((name or "").strip().lower().split()):
        out.append(w if (w in small and i) else (w.upper() if w in ("ltda", "me", "epp", "eireli", "sa", "s/a") else w.capitalize()))
    return " ".join(out)


# ------------------------------------------------------------------ banco de trabalho ----
def stage_path():
    return os.path.join(os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__))), "cnpj_stage.db")


def open_stage():
    con = sqlite3.connect(stage_path())
    con.execute("""CREATE TABLE IF NOT EXISTS estab (
        cnpj TEXT PRIMARY KEY, basico TEXT, fantasia TEXT, uf TEXT, mun TEXT, cnae TEXT, cnae_sec TEXT, segmento TEXT, email TEXT,
        ddd1 TEXT, tel1 TEXT, ddd2 TEXT, tel2 TEXT, inicio TEXT, cep TEXT, logradouro TEXT, numero TEXT, bairro TEXT,
        razao TEXT, porte TEXT, natureza TEXT, importado INTEGER DEFAULT 0)""")
    con.execute("CREATE TABLE IF NOT EXISTS efreq (email TEXT PRIMARY KEY, n INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS dfreq (dom TEXT PRIMARY KEY, n INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS done (arquivo TEXT PRIMARY KEY, linhas INTEGER, mantidas INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS mun (cod TEXT PRIMARY KEY, nome TEXT)")
    con.commit()
    return con


def _clean_lines(f):
    """Linhas do arquivo sem caracteres NUL (existem no arquivo da Receita e fazem o modulo csv do Python parar)."""
    for line in f:
        yield line.replace("\x00", "") if "\x00" in line else line


def _rows(zf_path):
    """Linhas (listas de campos) do primeiro CSV do zip, em ISO-8859-1, separador ';'. Linha defeituosa e pulada, nao derruba a leitura."""
    with zipfile.ZipFile(zf_path) as z:
        name = z.namelist()[0]
        with z.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="latin-1", newline="")
            it = iter(csv.reader(_clean_lines(text), delimiter=";", quotechar='"'))
            while True:
                try:
                    row = next(it)
                except StopIteration:
                    break
                except csv.Error:
                    continue
                yield row


def load_municipios(zip_path, con):
    rows = [(r[0].strip(), r[1].strip()) for r in _rows(zip_path) if len(r) >= 2]
    con.executemany("INSERT OR REPLACE INTO mun VALUES (?,?)", rows)
    con.commit()
    return len(rows)


def scan_estabelecimentos(zip_path, con, ufs=SUL, name=None, progress=None):
    """Passo 1: le um arquivo de Estabelecimentos e guarda os que interessam. Conta tambem a frequencia dos e-mails (de TODOS os ativos
    dos estados pedidos) para reconhecer e-mail de contador. Devolve (linhas, mantidas)."""
    ufs = set(u.upper() for u in ufs)
    lin = kept = 0
    batch, fq, dq = [], {}, {}
    for r in _rows(zip_path):
        lin += 1
        if len(r) < 28:
            continue
        if r[5] != "02" or r[19] not in ufs:             # 02 = situacao cadastral ATIVA
            continue
        email = r[27].strip().lower()
        if email and "@" in email:
            fq[email] = fq.get(email, 0) + 1
            dom = email.rsplit("@", 1)[1]
            if dom not in FREE_MAIL:
                dq[dom] = dq.get(dom, 0) + 1
        if r[3] != "1":                                   # 1 = matriz; filiais repetem o contato da matriz
            continue
        seg = segment_for(r[11], r[12])
        if not seg:
            continue
        phone = clean_phone(r[21], r[22]) or clean_phone(r[23], r[24])
        if not email and not phone:
            continue
        kept += 1
        batch.append((r[0] + r[1] + r[2], r[0], r[4].strip(), r[19], r[20], r[11], r[12], seg, email, r[21], r[22], r[23], r[24], r[10], r[18], r[14], r[15], r[17]))
        if len(batch) >= 5000:
            _flush(con, batch, fq, dq)
            batch, fq, dq = [], {}, {}
            if progress:
                progress(lin, kept)
    _flush(con, batch, fq, dq)
    con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)", (name or os.path.basename(zip_path), lin, kept))
    con.commit()
    return lin, kept


def _flush(con, batch, fq, dq):
    con.executemany("""INSERT OR IGNORE INTO estab (cnpj, basico, fantasia, uf, mun, cnae, cnae_sec, segmento, email, ddd1, tel1, ddd2, tel2, inicio, cep, logradouro, numero, bairro)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", batch)
    con.executemany("INSERT INTO efreq VALUES (?,?) ON CONFLICT(email) DO UPDATE SET n=n+excluded.n", list(fq.items()))
    con.executemany("INSERT INTO dfreq VALUES (?,?) ON CONFLICT(dom) DO UPDATE SET n=n+excluded.n", list(dq.items()))
    con.commit()


def scan_empresas(zip_path, con, name=None):
    """Passo 2: razao social, porte e natureza das empresas que ficaram."""
    basicos = {r[0] for r in con.execute("SELECT DISTINCT basico FROM estab")}
    n = 0
    upd = []
    for r in _rows(zip_path):
        if len(r) >= 6 and r[0] in basicos:
            upd.append((r[1].strip(), r[5].strip(), r[2].strip(), r[0]))
            n += 1
            if len(upd) >= 5000:
                con.executemany("UPDATE estab SET razao=?, porte=?, natureza=? WHERE basico=?", upd)
                upd = []
    con.executemany("UPDATE estab SET razao=?, porte=?, natureza=? WHERE basico=?", upd)
    con.execute("INSERT OR REPLACE INTO done VALUES (?,?,?)", (name or os.path.basename(zip_path), n, n))
    con.commit()
    return n


# ------------------------------------------------------------------ do estagio para o prospectador ----
def candidates(con, only_with_email=False):
    """Leads prontos: nome, segmento, cidade, contatos. E-mail de contador/intermediario e IGNORADO (o lead segue so com telefone)."""
    out = []
    mun = dict(con.execute("SELECT cod, nome FROM mun"))
    for r in con.execute("SELECT cnpj, fantasia, razao, uf, mun, segmento, email, ddd1, tel1, ddd2, tel2, inicio, porte, natureza, logradouro, numero, bairro, cep FROM estab WHERE importado=0"):
        cnpj, fant, razao, uf, mcod, seg, email, d1, t1, d2, t2, inicio, porte, nat, logr, num, bairro, cep = r
        if (nat or "").strip() == "2135":                 # empresario individual (inclui MEI): fora do perfil
            continue
        name = titlecase_company(fant or razao or "")
        if not name or len(name) < 3:
            continue
        email = (email or "").strip().lower()
        if email:
            n = (con.execute("SELECT n FROM efreq WHERE email=?", (email,)).fetchone() or (1,))[0]
            dom = email.rsplit("@", 1)[1] if "@" in email else ""
            dn = (con.execute("SELECT n FROM dfreq WHERE dom=?", (dom,)).fetchone() or (1,))[0]
            if is_intermediary_email(email, n, dn):
                email = ""
        phone1, phone2 = clean_phone(d1, t1), clean_phone(d2, t2)
        mobile = next((p for p in (phone1, phone2) if len(p) == 11 and p[2] == "9"), "")
        if only_with_email and not email:
            continue
        if not email and not (phone1 or phone2):
            continue
        city = (mun.get(mcod) or "").title()
        out.append({"cnpj": cnpj, "company_name": name, "razao": razao, "segment": seg, "uf": uf, "city": city, "email": email,
                    "phone": phone1 or phone2, "whatsapp": mobile, "inicio": inicio, "porte": porte, "natureza": nat,
                    "address": " ".join(x for x in (logr, num, bairro) if x).strip(), "cep": cep})
    return out


def _fmt_phone(d):
    return f"({d[:2]}) {d[2:7]}-{d[7:]}" if len(d) == 11 else (f"({d[:2]}) {d[2:6]}-{d[6:]}" if len(d) == 10 else d)


def to_prospects(cands, limit=None, db_con=None):
    """Grava candidatos em `prospects` (status pending, sem site, directory_source='cnpj_receita'). Evita duplicados por CNPJ e por telefone/nome.
    Devolve (novos, duplicados)."""
    import database
    conn = database.get_db_connection()
    existing_cnpj = {r[0] for r in conn.execute("SELECT cnpj FROM prospects WHERE cnpj IS NOT NULL AND cnpj != ''")}
    existing_names = {(r[0] or "").lower() for r in conn.execute("SELECT company_name FROM prospects")}
    new = dup = 0
    now = database.get_now_str()
    for c in cands:
        if limit and new >= limit:
            break
        if c["cnpj"] in existing_cnpj or c["company_name"].lower() in existing_names:
            dup += 1
            continue
        notes = f"[cnpj] {c['cnpj']} · aberta em {c['inicio']} · porte {c['porte']} · {c['address']}, CEP {c['cep']}"
        conn.execute("""INSERT INTO prospects (company_name, website, segment, region, status, contact_email, contact_phone, contact_whatsapp, notes,
                        created_at, updated_at, cnpj, is_autopilot, directory_source, is_directory)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (c["company_name"], "", database.normalize_segment(c["segment"]), f"{c['city']} - {c['uf']}", "pending", c["email"],
                      _fmt_phone(c["phone"]), _fmt_phone(c["whatsapp"]) if c["whatsapp"] else "", notes, now, now, c["cnpj"], 1, "cnpj_receita", 0))
        existing_cnpj.add(c["cnpj"])
        existing_names.add(c["company_name"].lower())
        new += 1
    conn.commit()
    conn.close()
    return new, dup


def mark_imported(con, cnpjs):
    con.executemany("UPDATE estab SET importado=1 WHERE cnpj=?", [(c,) for c in cnpjs])
    con.commit()


# ------------------------------------------------------------------ download ----
def webdav(path, method="GET", depth=None, timeout=60, stream=False):
    import requests
    h = {"Depth": str(depth)} if depth is not None else {}
    return requests.request(method, WEBDAV + path, auth=(SHARE_TOKEN, ""), headers=h, timeout=timeout, stream=stream)


def latest_month():
    r = webdav("", "PROPFIND", depth=1)
    months = sorted(set(re.findall(r"/public\.php/webdav/(\d{4}-\d{2})/", r.text)))
    return months[-1] if months else None


def list_files(month):
    r = webdav(month + "/", "PROPFIND", depth=1)
    return re.findall(r"<d:href>[^<]*/(\w+\.zip)</d:href>", r.text)


def download(month, filename, dest_dir, progress=None):
    """Baixa um arquivo. Se um arquivo completo (mesmo tamanho) ja estiver na pasta, reaproveita: nao baixa de novo."""
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    try:
        expected = int(webdav(f"{month}/{filename}", "HEAD", timeout=60).headers.get("content-length", 0))
    except Exception:  # noqa: BLE001
        expected = 0
    if expected and os.path.exists(dest) and os.path.getsize(dest) == expected:
        return dest
    with webdav(f"{month}/{filename}", stream=True, timeout=120) as r:
        r.raise_for_status()
        total, got, t0 = int(r.headers.get("content-length", 0)), 0, time.time()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                got += len(chunk)
                if progress and (time.time() - t0) > 5:
                    progress(got, total)
                    t0 = time.time()
    return dest
