"""Extrai do site de um prospect os "slots" de conteudo usados pelos templates de esboco.

Somente leitura: faz GET nas paginas publicas e le a captura de tela local.
Uso:  python extract.py https://exemplo.com.br [screenshot.png]
"""
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
PHONE_RE = re.compile(r"\(?\b\d{2}\)?[\s.-]?9?\d{4}[\s.-]?\d{4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
YEAR_RE = re.compile(r"\b(?:desde|fundad[ao]\s+em|h[aá]\s+mais\s+de)\s*(?:de\s*)?(\d{4}|\d{1,2}\s+anos)", re.I)
ADDR_RE = re.compile(r"\b(?:Rua|R\.|Av\.?|Avenida|Rodovia|Estrada|Travessa|Alameda)\s[^|\n<]{6,90}", re.I)
SERVICE_HEAD_RE = re.compile(r"servi[cç]os|produtos|o que fazemos|solu[cç][oõ]es|especialidades|atua[cç][aã]o|processos", re.I)
SKIP_IMG_RE = re.compile(r"(favicon|sprite|pixel|tracking|facebook|instagram|whatsapp|icon|loader|spinner|\.svg(\?|$)|\.gif(\?|$)|1x1|avatar|selo)", re.I)


def fetch(url, timeout=15):
    for verify in (True, False):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, verify=verify)
            r.encoding = r.apparent_encoding or r.encoding
            return r.text, r.url
        except requests.exceptions.SSLError:
            continue
        except requests.RequestException:
            return "", url
    return "", url


def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()


def abs_url(base, src):
    """URL absoluta; data:image raster (nao svg) e mantida como esta, o resto de data: e descartado."""
    if not src:
        return None
    src = src.strip()
    if src.startswith("data:"):
        return src if re.match(r"data:image/(png|jpe?g|webp);base64,", src) and len(src) > 8000 else None
    return urljoin(base, src.split(" ")[0])


def img_candidates(soup, base):
    out, seen = [], set()
    for tag in soup.find_all("img"):
        src = tag.get("data-src") or tag.get("data-lazy-src") or tag.get("src")
        if not src and tag.get("srcset"):
            src = tag["srcset"].split(",")[-1].strip().split(" ")[0]
        u = abs_url(base, src)
        if not u or u in seen or (not u.startswith("data:") and SKIP_IMG_RE.search(u)):
            continue
        blob = " ".join([tag.get("alt", ""), " ".join(tag.get("class", [])), tag.get("id", "")]).lower()
        if "logo" in blob or ICON_ALT_RE.search(blob) or ICON_ALT_RE.search(u.split("?")[0].rsplit("/", 1)[-1]) or BANNER_RE.search(blob) or (not u.startswith("data:") and BANNER_RE.search(u.split("?")[0].rsplit("/", 1)[-1])):
            continue
        w, h = tag.get("width", ""), tag.get("height", "")
        if w.isdigit() and h.isdigit() and (int(w) < 120 or int(h) < 80):
            continue
        seen.add(u)
        out.append({"url": u, "alt": clean(tag.get("alt", ""))[:120]})
    return out


GENERIC = {"metalurgica", "metalurgicas", "serralheria", "industria", "industrias", "comercio", "ltda", "usinagem", "caldeiraria",
           "indústria", "metais", "metal", "aco", "acos", "estruturas", "ind", "com", "www", "net", "org", "empresa", "grupo"}
BANNER_RE = re.compile(r"promo|oferta|condi[cç]|parcel|desconto|cart[aã]o|cupom|black.?friday|sem.?juros", re.I)   # formato/tamanho tratam o resto


def brand_tokens(name, domain):
    import unicodedata
    raw = f"{name or ''} {domain or ''}"
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode().lower()
    toks = {t for t in re.split(r"[^a-z0-9]+", raw) if len(t) >= 4 and t not in GENERIC}
    return toks


def find_logo(soup, base, tokens):
    """Escolhe o logo DA EMPRESA: precisa ter relacao com o nome (alt/arquivo/classe) ou estar no cabecalho
    com sinal de logo. Logos de clientes/parceiros (carrosseis) e imagens sem relacao sao rejeitados."""
    best, best_score = None, 0
    for tag in soup.find_all("img"):
        src = tag.get("data-src") or tag.get("src") or ""
        u = abs_url(base, src)
        if not u:
            continue
        ident = " ".join([src[:160] if not src.startswith("data:") else "", tag.get("alt", ""), " ".join(tag.get("class", [])), tag.get("id", "")]).lower()
        import unicodedata
        ident_n = unicodedata.normalize("NFKD", ident).encode("ascii", "ignore").decode()
        in_header = tag.find_parent(["header", "nav"]) is not None
        sc = 0
        if tokens and any(t in ident_n for t in tokens):
            sc += 5
        if in_header:
            sc += 3
        if "logo" in ident_n:
            sc += 2
        # alt do tipo "logo <outra empresa>" sem relacao com a marca => cliente/parceiro
        if re.search(r"\blogo\b", ident_n) and tokens and not any(t in ident_n for t in tokens) and not in_header:
            sc -= 6
        if sc > best_score:
            best, best_score = u, sc
    return best if best_score >= 5 else None


UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()


def clean_address(raw):
    """Corta o endereco onde ele termina: depois do CEP ou da UF, e antes de rotulos de formulario/horario."""
    s = clean(raw)
    s = re.split(r"\s(?:E-?mail|Tel|Telefone|Fone|Seg|Segunda|WhatsApp|CNPJ|Nome|Mensagem|Assunto|Enviar|Hor[aá]rio)\b|\s\*|\s{2,}", s, maxsplit=1)[0]
    s = re.split(r",?\s*(?:\(\d{2}\)|\d{4,5}[ -]\d{4}|\S+@)", s, maxsplit=1)[0] or s      # telefone/e-mail colados no endereco
    m = re.search(r"CEP:?\s*\d{5}-?\d{3}", s)
    if m:
        return s[:m.end()].strip(" ,-–")
    for m in re.finditer(r"(?:/|\s[–-]\s)\s?(" + "|".join(UFS) + r")\b", s):
        if m.start() > 12:
            return s[:m.end()].strip(" ,-–")
    return s[:140].strip(" ,-–")


def _photo_like(raw):
    """True se a imagem parece foto/conteudo (nao banner largo, tira estreita ou miniatura)."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        w, h = im.size
        if not (min(w, h) >= 240 and 0.45 <= w / h <= 2.3):
            return False
        # emblema/logo/arte: PNG ou WebP com areas transparentes (foto de verdade quase nunca tem transparencia)
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            alpha = list(im.convert("RGBA").resize((64, 64)).getchannel("A").getdata())
            if sum(1 for v in alpha if v < 128) / len(alpha) > 0.08:
                return False
        # logo de parceiro / arte grafica: fundo branco dominante + regioes chapadas.
        # (calibrado em amostras reais; pode recusar foto de produto em fundo branco: prefere-se ter menos imagens)
        s = im.convert("RGB").resize((96, 96))
        px = list(s.getdata())
        white = sum(1 for r, g, b in px if r > 235 and g > 235 and b > 235) / len(px)
        flat = sum(1 for i in range(97, len(px)) if i % 96 and sum(abs(a - b) for a, b in zip(px[i], px[i - 1])) < 6) / len(px)
        return not (white >= 0.5 and flat >= 0.5)
    except Exception:  # noqa: BLE001
        return True


ICON_ALT_RE = re.compile(r"diferencial|[ií]cone|(?<![a-z])icon|(?<![a-z])selo(?![a-z])|badge|(?<![a-z])seta(?![a-z])|arrow|avatar|depoimento", re.I)


def _prep_logo(path):
    """Apara as margens vazias (transparentes ou brancas) do logo para ele nao ficar minusculo no cabecalho.
    Devolve False se o arquivo for uma FOTO (nao e logo) ou ilegivel: quem chama descarta."""
    try:
        from PIL import Image, ImageChops
        if path.lower().endswith(".svg"):
            return True
        raw = open(path, "rb").read()
        im = Image.open(path)
        if path.lower().endswith((".jpg", ".jpeg")) and min(im.size) >= 200 and _photo_like(raw):
            return False                     # JPG com cara de foto: provavelmente nao e o logo
        im.load()
        if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            bbox = rgba.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()
            out = rgba
        else:
            rgb = im.convert("RGB")
            bbox = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255))).point(lambda v: 255 if v > 24 else 0).getbbox()
            out = rgb
        if not bbox:
            return False
        pad = max(2, int(0.02 * max(im.size)))
        box = (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))
        if (box[2] - box[0]) * (box[3] - box[1]) < 0.9 * im.width * im.height:
            ext = "PNG" if out.mode == "RGBA" else ("JPEG" if path.lower().endswith((".jpg", ".jpeg")) else "PNG")
            out.crop(box).save(path, ext)
        return True
    except Exception:  # noqa: BLE001
        return True


def materialize(items, save_dir, limit=8, photos_only=False):
    """Baixa/decodifica imagens para arquivos locais. Devolve lista com 'file' preenchido."""
    import base64
    import hashlib
    os.makedirs(save_dir, exist_ok=True)
    saved = []
    for it in items[:limit]:
        u = it["url"] if isinstance(it, dict) else it
        try:
            if u.startswith("data:"):
                head, b64 = u.split(",", 1)
                raw, ext = base64.b64decode(b64), ("jpg" if "jpeg" in head or "jpg" in head else head.split("/")[1].split(";")[0])
            else:
                r = requests.get(u, headers={"User-Agent": UA}, timeout=15, verify=False)
                ctype = r.headers.get("content-type", "")
                if r.status_code != 200 or not ctype.startswith("image/") or len(r.content) > 6_000_000:
                    continue
                raw, ext = r.content, ("jpg" if "jpeg" in ctype else ctype.split("/")[1].split(";")[0].replace("svg+xml", "svg"))
            if len(raw) < (25_000 if photos_only else 1_500) or (photos_only and not _photo_like(raw)):
                continue
            name = hashlib.sha1(raw).hexdigest()[:12] + "." + ext
            with open(os.path.join(save_dir, name), "wb") as f:
                f.write(raw)
            d = dict(it) if isinstance(it, dict) else {}
            d.update({"url": u if not u.startswith("data:") else "(inline)", "file": name, "bytes": len(raw)})
            saved.append(d)
        except Exception:  # noqa: BLE001
            continue
    return saved


def norm_phones(raw):
    """Normaliza e remove duplicatas (mesmo numero com/sem 55)."""
    out, seen = [], set()
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("55") and len(digits) in (12, 13):
            digits = digits[2:]
        if len(digits) not in (10, 11) or digits in seen:
            continue
        seen.add(digits)
        ddd, rest = digits[:2], digits[2:]
        out.append(f"({ddd}) {rest[:-4]}-{rest[-4:]}")
    return out


def find_services(soup):
    """Itens de lista / subtitulos logo abaixo de um cabecalho de servicos ou produtos."""
    items = []
    for head in soup.find_all(["h1", "h2", "h3"]):
        if not SERVICE_HEAD_RE.search(head.get_text()):
            continue
        scope = head.find_parent(["section", "div"]) or head.parent
        for el in scope.find_all(["li", "h3", "h4"]):
            t = clean(el.get_text(" "))
            if 3 <= len(t) <= 70 and t.lower() != clean(head.get_text()).lower():
                items.append(t)
        if len(items) >= 4:
            break
    seen, out = set(), []
    for t in items:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out[:12]


def nav_items(soup):
    """Itens do menu principal (sem Home/Contato etc.): sinal fraco de servicos/produtos."""
    skip = re.compile(r"^(in[ií]cio|home|contato|fale|quem somos|sobre|a empresa|blog|not[ií]cias|whats|or[cç]amento|trabalhe|login|prop[oó]sito|parceiros?)", re.I)
    nav = soup.find("nav") or soup.find("header")
    if not nav:
        return []
    items = [clean(a.get_text(" ")) for a in nav.find_all("a")]
    return [t for t in dict.fromkeys(items) if 3 <= len(t) <= 40 and not skip.match(t)][:8]


def dominant_colors(path, n=5):
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.thumbnail((200, 200))
        q = im.quantize(colors=12, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()
        counts = Counter(q.getdata())
        cols = []
        for idx, cnt in counts.most_common():
            r, g, b = pal[idx * 3: idx * 3 + 3]
            mx, mn = max(r, g, b), min(r, g, b)
            sat = 0 if mx == 0 else (mx - mn) / mx
            cols.append({"hex": "#%02x%02x%02x" % (r, g, b), "share": round(cnt / sum(counts.values()), 3),
                         "saturation": round(sat, 2), "luma": round((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255, 2)})
        accents = [c for c in cols if c["saturation"] > 0.45 and 0.2 < c["luma"] < 0.9]
        return {"palette": cols[:n], "accent": accents[0]["hex"] if accents else None}
    except Exception as e:  # noqa: BLE001
        return {"palette": [], "accent": None, "error": str(e)}


def extract(url, screenshot_path=None, save_dir=None, brand=None):
    html, final = fetch(url)
    if not html:
        return {"url": url, "ok": False, "error": "nao foi possivel baixar o site"}
    soup = BeautifulSoup(html, "html.parser")
    base = final

    # texto sem ruido
    nav = nav_items(soup)
    og_site = soup.find("meta", property="og:site_name")
    tokens = brand_tokens(" ".join(x for x in [brand, og_site["content"] if og_site and og_site.get("content") else ""] if x), urlparse(base).netloc)
    images = img_candidates(soup, base)
    logo = find_logo(soup, base, tokens)
    services = find_services(soup)
    for t in soup(["script", "style", "noscript", "svg", "iframe"]):
        t.decompose()
    text = clean(soup.get_text(" "))

    title = clean(soup.title.get_text()) if soup.title else ""
    md = soup.find("meta", attrs={"name": "description"})
    og = soup.find("meta", property="og:site_name")
    theme = soup.find("meta", attrs={"name": "theme-color"})
    h1 = [clean(h.get_text(" ")) for h in soup.find_all("h1")][:2]
    h2 = [clean(h.get_text(" ")) for h in soup.find_all("h2") if 4 <= len(clean(h.get_text())) <= 90][:10]

    wa = [a["href"] for a in soup.find_all("a", href=True) if re.search(r"wa\.me|api\.whatsapp|web\.whatsapp", a["href"])]
    tel = [re.sub(r"\D", "", a["href"][4:]) for a in soup.find_all("a", href=True) if a["href"].startswith("tel:")]
    wa_num = [re.search(r"(?:wa\.me/|phone=)(\d+)", w).group(1) for w in wa if re.search(r"(?:wa\.me/|phone=)(\d+)", w)]
    phones = norm_phones(tel + PHONE_RE.findall(text) + wa_num)[:4]
    emails = [e for e in dict.fromkeys(EMAIL_RE.findall(text)) if not e.lower().endswith(("png", "jpg", "webp"))][:3]
    addr = ADDR_RE.search(text)
    address = clean_address(addr.group(0)) if addr else ""
    year = YEAR_RE.search(text)

    if save_dir:
        images = materialize(images, os.path.join(save_dir, "img"), photos_only=True)
        if logo:
            lg = materialize([{"url": logo}], os.path.join(save_dir, "img"), limit=1)
            logo = lg[0]["file"] if lg else None
            if logo and not _prep_logo(os.path.join(save_dir, "img", logo)):
                logo = None
    colors =dominant_colors(screenshot_path) if screenshot_path and os.path.exists(screenshot_path) else {"palette": [], "accent": None}

    data = {
        "url": base,
        "ok": True,
        "domain": urlparse(base).netloc,
        "site_name": clean(og["content"]) if og and og.get("content") else "",
        "title": title,
        "meta_description": clean(md["content"]) if md and md.get("content") else "",
        "h1": h1,
        "h2": h2,
        "services": services,
        "nav_items": nav,
        "contacts": {
            "whatsapp": wa_num[:1], "phones": phones, "emails": emails, "address": address,
        },
        "founded_hint": year.group(1) if year else "",
        "logo": logo,
        "images": images[:12] if not save_dir else images,
        "theme_color": theme["content"] if theme and theme.get("content") else "",
        "colors": colors,
        "text_sample": text[:1800],
        "text_len": len(text),
    }
    data["data_score"] = score(data)
    return data


def score(d):
    """Sinal deterministico de 'ha conteudo real suficiente para uma hero especifica'."""
    pts, why = 0, []
    checks = [
        (len(d["images"]) >= 2, 3, "2+ fotos reais"),
        # servicos: lista/menu detectados, ou texto longo o bastante para o LLM derivar os servicos
        (len(d["services"]) >= 3 or len(d["nav_items"]) >= 3 or (d["text_len"] > 1500 and len(d["h2"]) >= 3), 3, "servicos/produtos identificaveis"),
        (bool(d["contacts"]["phones"] or d["contacts"]["whatsapp"]), 2, "telefone ou WhatsApp"),
        (bool(d["logo"]), 1, "logo"),
        (bool(d["meta_description"] or d["h1"]), 1, "titulo/descricao"),
        (d["text_len"] > 600, 1, "texto suficiente"),
    ]
    for ok, w, label in checks:
        if ok:
            pts += w
        else:
            why.append("falta: " + label)
    return {"points": pts, "max": 11, "missing": why}


if __name__ == "__main__":
    out = extract(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
