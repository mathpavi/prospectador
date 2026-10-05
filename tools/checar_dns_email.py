"""Confere SPF, DKIM e DMARC do dominio que envia os e-mails (E2 do PLANO_PROSPECTADOR). SOMENTE CONSULTA DNS.

  python tools/checar_dns_email.py seudominio.com.br
  python tools/checar_dns_email.py seudominio.com.br --selectors meuseletor,outro      (seletores DKIM extras)
Sem argumento: usa o dominio do e-mail de envio (smtp_user) cadastrado no app.
Nao achar um seletor DKIM NAO prova que ele nao existe: o nome do seletor depende do provedor.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import dns.exception  # noqa: E402
import dns.resolver  # noqa: E402

COMMON_SELECTORS = ["default", "google", "selector1", "selector2", "k1", "k2", "mail", "dkim", "s1", "s2", "smtp",
                    "hostingermail1", "hostingermail2", "hostingermail-a", "hostingermail-b", "hostingermail-c"]


def txt(name):
    for public in (False, True):
        r = dns.resolver.Resolver()
        if public:
            r.nameservers = ["1.1.1.1", "8.8.8.8"]
        r.timeout, r.lifetime = 2.0, 4.0
        try:
            return ["".join(p.decode() if isinstance(p, bytes) else p for p in rr.strings) for rr in r.resolve(name, "TXT")]
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            continue
    return None


def mx(name):
    for public in (False, True):
        r = dns.resolver.Resolver()
        if public:
            r.nameservers = ["1.1.1.1", "8.8.8.8"]
        r.timeout, r.lifetime = 2.0, 4.0
        try:
            return sorted(str(x.exchange).rstrip(".") for x in r.resolve(name, "MX"))
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return []
        except (dns.exception.Timeout, dns.resolver.NoNameservers):
            continue
    return None


def domain_from_settings():
    try:
        import database
        user = database.get_setting("smtp_user", "")
        return user.rsplit("@", 1)[1] if "@" in user else ""
    except Exception:  # noqa: BLE001
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dominio", nargs="?")
    ap.add_argument("--selectors", default="")
    a = ap.parse_args()
    d = (a.dominio or domain_from_settings()).strip().lower()
    if not d:
        sys.exit("informe o dominio: python tools/checar_dns_email.py seudominio.com.br")
    print(f"Dominio: {d}\n")
    problems, advice = [], []

    m = mx(d)
    print("MX  :", m if m else ("(consulta falhou)" if m is None else "(nenhum)"))

    t = txt(d)
    spf = [x for x in (t or []) if x.lower().startswith("v=spf1")]
    print("SPF :", spf[0] if spf else ("(consulta falhou)" if t is None else "NAO ENCONTRADO"))
    if t is not None:
        if not spf:
            problems.append("SPF ausente: provedores desconfiam de e-mails sem SPF.")
            advice.append("Crie um registro TXT no DNS do dominio com o valor indicado pelo seu provedor de e-mail (ex.: 'v=spf1 include:_spf.mail.hostinger.com ~all'; confira no painel do provedor).")
        elif len(spf) > 1:
            problems.append("Mais de um registro SPF: o correto e UM so (junte as inclusoes).")
        else:
            s = spf[0].lower()
            if "+all" in s or re.search(r"\s\?all", s):
                problems.append("SPF permissivo demais (+all/?all).")
            if "-all" not in s and "~all" not in s:
                problems.append("SPF sem terminacao (~all ou -all).")
            if len(re.findall(r"include:|redirect=|\sa\s|\smx\s|exists:", s)) > 8:
                problems.append("SPF com muitas inclusoes (limite de 10 consultas DNS).")

    dm = txt("_dmarc." + d)
    dmarc = [x for x in (dm or []) if x.lower().startswith("v=dmarc1")]
    print("DMARC:", dmarc[0] if dmarc else ("(consulta falhou)" if dm is None else "NAO ENCONTRADO"))
    if dm is not None:
        if not dmarc:
            problems.append("DMARC ausente: Gmail e Yahoo passaram a exigir para quem envia em volume e favorece quem tem.")
            advice.append("Comece com monitoramento: TXT em _dmarc." + d + " = 'v=DMARC1; p=none; rua=mailto:dmarc@" + d + "'. Depois de semanas sem problemas, suba para p=quarantine.")
        else:
            pol = re.search(r"p=(\w+)", dmarc[0].lower())
            if pol and pol.group(1) == "none":
                advice.append("DMARC esta em p=none (so monitora). Ok para comecar; suba para quarantine quando estiver estavel.")

    sels = COMMON_SELECTORS + [s.strip() for s in a.selectors.split(",") if s.strip()]
    found = []
    for s in dict.fromkeys(sels):
        r = txt(f"{s}._domainkey.{d}")
        if r:
            found.append((s, (r[0][:60] + "...") if len(r[0]) > 60 else r[0]))
    print("DKIM:", found if found else "nenhum seletor comum encontrado")
    if not found:
        advice.append("DKIM: nao achei seletor entre os comuns. Veja no painel do provedor de e-mail qual e o seletor do dominio e rode de novo com --selectors NOME. Se nao houver DKIM, ative-o la.")

    print("\n--- Resultado ---")
    if problems:
        print("PROBLEMAS:")
        for p in problems:
            print("  !", p)
    else:
        print("Nenhum problema grave nos registros verificados.")
    if advice:
        print("PROXIMOS PASSOS:")
        for p in advice:
            print("  >", p)
    print("\nObs.: isto mostra a CONFIGURACAO publica. Para ver como o Gmail avalia seus envios, envie um e-mail de teste para uma conta Gmail e use 'Mostrar original' (procure SPF/DKIM/DMARC: PASS).")


if __name__ == "__main__":
    main()
