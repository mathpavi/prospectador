"""Renderiza um esboco: template + slots + imagens -> pasta estatica (index.html + img/) e miniaturas.

Uso:  python render.py <template_id> <slots.json> <pasta_de_assets_do_extrator> <pasta_de_saida>
"""
import json
import os
import re
import shutil
import sys

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(HERE, "templates")


def _lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def fit_accent(hex_, bg="#0d0f11", min_ratio=4.5):
    """Clareia a cor da marca ate ter contraste legivel sobre o fundo escuro; escolhe texto claro/escuro p/ botoes."""
    import colorsys
    if not hex_ or not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_):
        hex_ = "#b2923a"
    c = hex_
    h, l, s = colorsys.rgb_to_hls(*(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)))  # mantem o matiz da marca
    contrast = lambda x: (max(_lum(x), _lum(bg)) + 0.05) / (min(_lum(x), _lum(bg)) + 0.05)  # noqa: E731
    step = 0.03 if _lum(bg) < 0.5 else -0.03          # fundo escuro -> clareia; fundo claro -> escurece
    while contrast(c) < min_ratio and 0.05 < l < 0.95:
        l += step
        c = "#%02x%02x%02x" % tuple(round(v * 255) for v in colorsys.hls_to_rgb(h, l, s))
    ratio = lambda fg: (max(_lum(c), _lum(fg)) + 0.05) / (min(_lum(c), _lum(fg)) + 0.05)  # noqa: E731
    on = max(("#12171c", "#ffffff"), key=ratio)
    return c, on


def logo_class(path, bg_is_dark):
    """Classe CSS para o logo ficar legivel: 'plate' (logo com fundo proprio), 'inv' (escuro em fundo escuro),
    'ink' (claro em fundo claro) ou '' (ok como esta)."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
        im.thumbnail((200, 200))
        px = [p for p in im.getdata()]
        opaque_share = sum(p[3] > 200 for p in px) / len(px)
        if opaque_share > 0.97:                       # sem transparencia: logo traz o proprio fundo
            return "plate"
        vis = [p for p in px if p[3] > 128]
        if not vis:
            return ""
        tone = sum(0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in vis) / len(vis) / 255
        if bg_is_dark and tone < 0.35:
            return "inv"
        if not bg_is_dark and tone > 0.65:
            return "ink"
    except Exception:  # noqa: BLE001
        pass
    return ""


def _prep_photo(path, accent=None):
    """Tratamento de foto para as imagens nao parecerem 'colagem do site antigo': tom uniforme (contraste automatico, cor um pouco
    contida, leve toque da cor da marca), ampliacao suave de fotos pequenas e granulado fino para esconder serrilhado.
    Devolve (nota_de_qualidade, largura). A nota ordena as fotos: a melhor vira a foto principal. Nunca levanta excecao."""
    try:
        from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat
        im = Image.open(path)
        if im.mode in ("RGBA", "LA", "P") and (im.mode != "P" or "transparency" in im.info):
            alpha = im.convert("RGBA").getchannel("A")
            if alpha.getextrema()[0] < 250:
                return 0.0, im.width            # arte com transparencia (emblema): nao mexer
        fmt = (im.format or "JPEG").upper()
        w0, h0 = im.size
        rgb = im.convert("RGB")
        gray = rgb.convert("L").resize((min(w0, 640), max(1, int(h0 * min(w0, 640) / w0))))
        edges = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]       # nitidez (variancia das bordas)
        if w0 < 1400:
            k = 1400 / w0
            rgb = rgb.resize((1400, int(h0 * k)), Image.LANCZOS)
            rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.6, percent=60, threshold=3))
        rgb = ImageOps.autocontrast(rgb, cutoff=0.6)
        rgb = ImageEnhance.Color(rgb).enhance(0.93)
        if accent and re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
            tint = Image.new("RGB", rgb.size, accent)
            rgb = Image.blend(rgb, tint, 0.05)
        noise = Image.effect_noise(rgb.size, 6).convert("RGB")
        rgb = Image.blend(rgb, ImageChops.add(rgb, noise, 1.0, -128), 0.12)
        out_fmt = "PNG" if fmt == "PNG" else "JPEG"
        rgb.save(path, out_fmt, **({"quality": 86, "optimize": True} if out_fmt == "JPEG" else {}))
        import math
        ratio = w0 / max(h0, 1)
        pen = 0.35 if (ratio > 2.2 or ratio < 0.55) else 1.0           # faixas muito largas/estreitas servem mal de foto principal
        return (min(w0, 1800) / 1800.0) * (0.5 + math.log10(1.0 + edges) / 4.0) * pen, w0
    except Exception:  # noqa: BLE001
        return 1.0, 0


def _digits(x):
    return re.sub(r"\D", "", x or "")


def company_contact(phones):
    """(whatsapp_url_base, tel_url) da empresa: WhatsApp so se houver celular (9 apos o DDD); tel: com o primeiro numero."""
    wa = tel = ""
    for p in phones or []:
        d = _digits(p)
        d = d[2:] if d.startswith("55") and len(d) > 11 else d
        if not tel and len(d) >= 10:
            tel = "tel:+55" + d
        if not wa and len(d) == 11 and d[2] == "9":
            wa = "https://wa.me/55" + d
    return wa, tel


def default_proposal(brand):
    """Faixa 'Proposta visual': o botao abre o WhatsApp do Paviani (configuracao sender_whatsapp) com mensagem pronta."""
    from urllib.parse import quote
    num = ""
    try:
        import fill
        num = _digits(fill._db_setting("sender_whatsapp"))
    except Exception:  # noqa: BLE001
        pass
    num = num or "5551997661506"
    if not num.startswith("55"):
        num = "55" + num
    msg = f"Olá! Vi o esboço de site que você preparou para a {brand}. Gostei e quero conversar sobre ajustes ou algo diferente."
    return {"author": "Paviani", "cta_label": "Falar com a Paviani", "cta_url": f"https://wa.me/{num}?text={quote(msg)}"}


def render(template_id, slots, assets_dir, out_dir, proposal=None, og=None):
    env = Environment(loader=FileSystemLoader([os.path.join(TEMPLATES, template_id), os.path.join(TEMPLATES, "_shared")]),
                      autoescape=select_autoescape(["html"]))
    tpl = env.get_template("template.html")

    os.makedirs(os.path.join(out_dir, "img"), exist_ok=True)
    used = []
    for name in slots.get("images", []) + ([slots["logo_file"]] if slots.get("logo_file") else []):
        src = os.path.join(assets_dir, "img", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, "img", name))
            used.append(name)

    # tratamento e ordenacao das fotos: a de melhor qualidade vira a principal (hero)
    scored = []
    for name in [i for i in slots.get("images", []) if i in used]:
        q, w = _prep_photo(os.path.join(out_dir, "img", name), slots.get("accent"))
        scored.append((q, name))
    ordered = [n for q, n in sorted(scored, key=lambda x: -x[0])]
    if slots.get("images_locked"):                       # a IA de visao ja escolheu a ordem: respeita
        ordered = [i for i in slots.get("images", []) if i in used]
    slots = dict(slots)
    slots["images"] = ordered + [i for i in slots.get("images", []) if i not in ordered]

    meta_path = os.path.join(TEMPLATES, template_id, "meta.json")
    meta = json.load(open(meta_path, encoding="utf-8")) if os.path.exists(meta_path) else {"bg": "#0d0f11", "dark": True, "alt_bg": "#f3f1ec"}
    slots = dict(slots)
    if slots.get("variant") not in (0, 1, 2):
        # variacao de estrutura: estavel por empresa, para duas empresas do mesmo segmento nao receberem a mesma pagina
        import zlib
        slots["variant"] = zlib.crc32((slots.get("brand_name") or "").encode("utf-8")) % 3
    slots["wa_url"], slots["tel_url"] = company_contact(slots.get("phones"))
    slots["accent"], on_accent = fit_accent(slots.get("accent"), meta["bg"])
    accent_alt, on_accent_alt = fit_accent(slots.get("accent"), meta["alt_bg"])   # versao para blocos de fundo oposto
    logo_file = slots.get("logo_file") if slots.get("logo_file") in used else None
    lcls = logo_class(os.path.join(out_dir, "img", logo_file), meta["dark"]) if logo_file else ""
    html = tpl.render(
        s=slots, on_accent=on_accent, accent_alt=accent_alt, on_accent_alt=on_accent_alt, og=og, logo_cls=lcls,
        images=[i for i in slots.get("images", []) if i in used],
        logo_file=logo_file,
        proposal=proposal or default_proposal(slots.get("short_name") or slots.get("brand_name") or "minha empresa"),
    )
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def screenshot(index_path, out_png, width=1440, height=900, full=True):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": height})
        pg.goto("file:///" + index_path.replace("\\", "/"), wait_until="networkidle")
        pg.add_style_tag(content=".rv-off .rv,.rv-off .pv-ix,.rv-off .pv-hero-in{transition:none!important;animation:none!important;opacity:1!important;transform:none!important;filter:none!important;clip-path:none!important}")
        pg.evaluate("document.documentElement.classList.add('rv-off')")
        pg.wait_for_timeout(400)
        pg.screenshot(path=out_png, full_page=full)
        b.close()


if __name__ == "__main__":
    tid, slots_path, assets, out = sys.argv[1:5]
    slots = json.load(open(slots_path, encoding="utf-8"))
    idx = render(tid, slots, assets, out)
    print("ok:", idx)
