"""Validacao de e-mail (Q1 do PLANO_PROSPECTADOR).

Barra lixo extraido de CSS/JS/arquivos (ex.: 'wght@100..900', 'intl-segmenter@11.7.10', 'logo@2x.png'),
enderecos de exemplo/sistema e dominios sem registro de e-mail (MX). Nunca levanta excecao.
"""
import re

_EMAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._%+\-]{0,63}@([a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?)+)$")
_TLD_RE = re.compile(r"^(?:[a-z]{2,24}|xn--[a-z0-9\-]{2,40})$")
_FILE_EXT = {"png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "css", "js", "json", "map", "woff", "woff2", "ttf", "eot", "pdf",
             "mp4", "webm", "avif", "bmp", "tiff", "zip", "html", "php", "xml", "txt"}
_JUNK_DOMAINS = {"example.com", "example.org", "example.net", "domain.com", "dominio.com", "dominio.com.br", "email.com", "seudominio.com.br",
                 "seudominio.com", "yourdomain.com", "mysite.com", "test.com", "teste.com", "sentry.io", "sentry.wixpress.com", "wixpress.com",
                 "godaddy.com", "sentry-next.wixpress.com", "localhost.com"}
_JUNK_LOCAL = re.compile(r"^(?:seu|seuemail|seunome|nome|name|email|usuario|user|username|teste|test|exemplo|example|fulano|"
                         r"no-?reply|noreply|do-?not-?reply|donotreply|mailer-daemon|postmaster|abuse|hostmaster|webmaster|root)$")
_ROLE_OK = {"contato", "comercial", "vendas", "atendimento", "sac", "financeiro", "orcamento", "orcamentos", "info", "adm", "administrativo", "contact"}
_mx_cache = {}


def normalize(email):
    e = (email or "").strip().lower()
    e = re.sub(r"^mailto:", "", e).strip(" <>\"'.,;:()[]")
    return e


def check_syntax(email):
    """(status, motivo): 'valid' ou 'invalid'. Sem rede."""
    e = normalize(email)
    if not e:
        return "invalid", "vazio"
    m = _EMAIL_RE.match(e)
    if not m:
        return "invalid", "sintaxe invalida"
    local, domain = e.rsplit("@", 1)
    if ".." in e or local.endswith(".") or "%" in domain:
        return "invalid", "sintaxe invalida"
    tld = domain.rsplit(".", 1)[1]
    if tld in _FILE_EXT:
        return "invalid", f"parece arquivo (.{tld})"
    if not _TLD_RE.match(tld):
        return "invalid", "dominio sem extensao valida (lixo de codigo?)"
    if re.search(r"@\d|\d+\.\d+\.\d+", e):
        return "invalid", "parece numero de versao"
    if domain in _JUNK_DOMAINS or any(domain.endswith("." + j) for j in _JUNK_DOMAINS):
        return "invalid", "dominio de exemplo/sistema"
    if _JUNK_LOCAL.match(local) and local not in _ROLE_OK:
        return "invalid", "endereco de sistema/exemplo"
    return "valid", ""


def check_mx(domain, timeout=3.0):
    """(status, motivo): 'valid' (tem MX ou A), 'invalid' (dominio inexistente/sem e-mail), 'risky' (nao deu para saber)."""
    domain = (domain or "").lower().strip(".")
    if domain in _mx_cache:
        return _mx_cache[domain]
    result = ("risky", "nao foi possivel consultar o DNS")
    try:
        import dns.resolver
        import dns.exception

        def resolver(public):
            r = dns.resolver.Resolver()
            if public:                       # DNS do sistema nao respondeu: tenta resolvedores publicos
                r.nameservers = ["1.1.1.1", "8.8.8.8"]
                r.timeout, r.lifetime = 2.0, timeout + 1
            else:
                r.timeout, r.lifetime = 1.2, 2.5
            return r

        for public in (False, True):
            res = resolver(public)
            try:
                ans = res.resolve(domain, "MX")
                result = ("valid", "") if len(ans) else ("invalid", "sem servidor de e-mail (MX)")
                break
            except dns.resolver.NoAnswer:
                try:
                    res.resolve(domain, "A")               # sem MX: o RFC permite cair no A
                    result = ("risky", "sem MX (usa o A)")
                except dns.resolver.NXDOMAIN:
                    result = ("invalid", "dominio inexistente")
                except dns.exception.DNSException:
                    result = ("invalid", "sem servidor de e-mail (MX)")
                break
            except dns.resolver.NXDOMAIN:
                result = ("invalid", "dominio inexistente")
                break
            except (dns.resolver.NoNameservers, dns.exception.Timeout):
                result = ("risky", "DNS nao respondeu")      # tenta o proximo resolvedor
                continue
    except Exception:  # noqa: BLE001
        pass
    if result[0] == "valid" or result[0] == "invalid" or "sem MX" in result[1]:
        _mx_cache[domain] = result                          # so guarda respostas conclusivas
    return result


def check_email(email, check_dns=True):
    """(status, motivo, email_normalizado). status: 'valid' | 'risky' | 'invalid'."""
    e = normalize(email)
    st, why = check_syntax(e)
    if st != "valid":
        return "invalid", why, e
    if check_dns:
        st2, why2 = check_mx(e.rsplit("@", 1)[1])
        if st2 != "valid":
            return st2, why2, e
    return "valid", "", e


def pick_valid_email(candidates, check_dns=False):
    """Primeiro e-mail valido de uma lista (ou ''). Usado na extracao dos sites."""
    for c in candidates or []:
        st, _, e = check_email(c, check_dns=check_dns)
        if st == "valid":
            return e
    return ""
