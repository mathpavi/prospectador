"""M4 do PLANO_PROSPECTADOR: o esboco so e liberado se for REALMENTE melhor que o site atual.

Juiz de visao (Gemini multimodal), as cegas: recebe duas versoes rotuladas A/B (sem saber qual e o esboco),
em desktop e celular, duas rodadas com a ordem trocada. Falha FECHADO: se nao deu para comparar, nao libera.

Regra: media das notas do esboco >= min_score, margem media >= min_margin e o esboco ganha em TODAS as rodadas.
Etapa 1 (barata, so o site atual): se o site ja e muito bom (>= skip_site_score), nem gera o esboco.
"""
import base64
import io
import os

import fill as fill_mod

DEFAULTS = {"mockup_judge": "1", "mockup_min_score": "7.0", "mockup_min_margin": "1.5", "mockup_skip_site_score": "8.0"}

CRITERIA = ("clareza da proposta e do que a empresa faz, hierarquia visual e tipografia, aparencia moderna e profissional, "
            "uso de espaco/contraste, destaque do contato/orcamento (WhatsApp) e usabilidade no celular")


def cfg(key):
    try:
        v = fill_mod._db_setting(key)
    except Exception:  # noqa: BLE001
        v = None
    return v if v not in (None, "") else DEFAULTS[key]


def _f(key):
    try:
        return float(cfg(key))
    except ValueError:
        return float(DEFAULTS[key])


def enabled():
    return str(cfg("mockup_judge")) not in ("0", "false", "False", "")


def jpeg_b64(png_path, max_w=900, quality=70):
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def capture(target, out_dir, tag, is_url):
    """Capturas desktop (1440x900) e celular (390x844). Devolve [png_desktop, png_mobile] ou levanta excecao."""
    from playwright.sync_api import sync_playwright
    url = target if is_url else "file:///" + target.replace("\\", "/")
    outs = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, w, h in (("d", 1440, 900), ("m", 390, 844)):
            pg = b.new_page(viewport={"width": w, "height": h})
            pg.goto(url, wait_until="load", timeout=30000)
            try:
                pg.wait_for_load_state("networkidle", timeout=8000)
            except Exception:  # noqa: BLE001
                pass
            pg.add_style_tag(content=".rv-off .rv,.rv-off .pv-ix,.rv-off .pv-hero-in{transition:none!important;animation:none!important;opacity:1!important;transform:none!important;filter:none!important;clip-path:none!important}")
            pg.evaluate("document.documentElement.classList.add('rv-off')")
            pg.wait_for_timeout(500)
            out = os.path.join(out_dir, f"{tag}_{name}.png")
            pg.screenshot(path=out, full_page=False)
            outs.append(out)
            pg.close()
        b.close()
    return outs


def _parts(prompt, labeled):
    parts = [{"text": prompt}]
    for label, imgs in labeled:
        parts.append({"text": f"Versao {label} - desktop (primeira imagem) e celular (segunda imagem):"})
        for im in imgs:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": jpeg_b64(im)}})
    return parts


def rate_site(site_imgs, call=None):
    """Etapa 1: nota (0-10) do site atual sozinho. Devolve (nota, custo)."""
    call = call or fill_mod.gemini_json
    prompt = (f"Avalie o design do site mostrado de 0 a 10 considerando: {CRITERIA}. Seja criterio(a) e honesto(a): "
              'sites comuns de pequenas empresas ficam entre 3 e 6. Responda apenas JSON: {"nota": numero}')
    data, cost, _ = call(_parts(prompt, [("unica", site_imgs)]), temperature=0.1, max_tokens=200)
    return float(data["nota"]), cost


def compare_once(site_imgs, mock_imgs, swap, call=None):
    """Uma rodada cega. Devolve (nota_site, nota_esboco, custo). swap=True coloca o esboco como 'A'."""
    call = call or fill_mod.gemini_json
    a, b = (mock_imgs, site_imgs) if swap else (site_imgs, mock_imgs)
    prompt = (f"Voce e um diretor de arte comparando dois designs de site da MESMA empresa (versoes A e B). "
              f"Nota de 0 a 10 para cada um considerando: {CRITERIA}. Nao presuma qual e o mais novo; julgue so o que ve. "
              'Responda apenas JSON: {"A": numero, "B": numero}')
    data, cost, _ = call(_parts(prompt, [("A", a), ("B", b)]), temperature=0.1, max_tokens=200)
    na, nb = float(data["A"]), float(data["B"])
    return (nb, na, cost) if swap else (na, nb, cost)


def decide(runs, min_score=None, min_margin=None):
    """runs = [(nota_site, nota_esboco), ...]. Devolve (ok, motivo)."""
    min_score = _f("mockup_min_score") if min_score is None else min_score
    min_margin = _f("mockup_min_margin") if min_margin is None else min_margin
    if not runs:
        return False, "comparacao nao realizada"
    s = sum(r[0] for r in runs) / len(runs)
    m = sum(r[1] for r in runs) / len(runs)
    tag = f"nota do esboco {m:.1f} vs site atual {s:.1f}"
    if any(r[1] <= r[0] for r in runs):
        return False, f"esboco nao e melhor que o site atual em todas as rodadas ({tag})"
    if m < min_score:
        return False, f"esboco abaixo da nota minima {min_score:.1f} ({tag})"
    if m - s < min_margin:
        return False, f"diferenca menor que {min_margin:.1f} ponto(s) ({tag})"
    return True, tag


def judge_site_only(prospect, work, saved_shot=None, call=None, capture_fn=None):
    """Etapa 1. Devolve (pular, nota, motivo, custo). Se nao der para avaliar, nao pula (deixa seguir)."""
    capture_fn = capture_fn or capture
    try:
        imgs = capture_fn(prospect["website"], work, "site", True)
    except Exception:  # noqa: BLE001
        imgs = [saved_shot] * 2 if saved_shot and os.path.exists(saved_shot) else None
    if not imgs:
        return False, None, "", 0.0
    try:
        nota, cost = rate_site(imgs, call)
    except Exception:  # noqa: BLE001
        return False, None, "", 0.0
    if nota >= _f("mockup_skip_site_score"):
        return True, nota, f"o site atual ja e muito bom (nota {nota:.1f}); esboco nao agregaria", cost
    return False, nota, "", cost


def judge_mockup(prospect, index_path, work, saved_shot=None, call=None, capture_fn=None, keep=None):
    """Etapa 2. Devolve (ok, motivo, nota_site, nota_esboco, custo). Falha FECHADO."""
    capture_fn = capture_fn or capture
    try:
        mock = capture_fn(index_path, work, "mock", False)
    except Exception as e:  # noqa: BLE001
        return False, f"nao foi possivel capturar o esboco ({type(e).__name__})", None, None, 0.0
    try:
        site = capture_fn(prospect["website"], work, "site2", True)
    except Exception:  # noqa: BLE001
        site = [saved_shot] * 2 if saved_shot and os.path.exists(saved_shot) else None
    if not site:
        return False, "nao foi possivel capturar o site atual para comparar", None, None, 0.0
    if keep is not None:
        keep["site"], keep["mock"] = site[0], mock[0]
    runs, total = [], 0.0
    try:
        for swap in (False, True):
            s, m, c = compare_once(site, mock, swap, call)
            runs.append((s, m))
            total += c
    except Exception as e:  # noqa: BLE001
        return False, f"juiz indisponivel ({str(e)[:80]})", None, None, total
    ok, why = decide(runs)
    return ok, why, sum(r[0] for r in runs) / 2, sum(r[1] for r in runs) / 2, total


def write_compare(prospect, index_path, work, out_dir, keep=None, saved_shot=None, capture_fn=None):
    """M2: grava antes.jpg (site atual) e depois.jpg (esboco) na pasta do esboco, para o antes/depois da pagina. Nunca levanta excecao."""
    capture_fn = capture_fn or capture
    try:
        from PIL import Image
        keep = dict(keep or {})
        if not keep.get("mock"):
            keep["mock"] = capture_fn(index_path, work, "cmp_mock", False)[0]
        if not keep.get("site"):
            try:
                keep["site"] = capture_fn(prospect["website"], work, "cmp_site", True)[0]
            except Exception:  # noqa: BLE001
                if not (saved_shot and os.path.exists(saved_shot)):
                    return False
                keep["site"] = saved_shot
        for name, src in (("antes.jpg", keep["site"]), ("depois.jpg", keep["mock"])):
            im = Image.open(src).convert("RGB")
            im = im.crop((0, 0, im.width, min(im.height, int(im.width * 900 / 1440))))
            if im.width > 1440:
                im = im.resize((1440, int(im.height * 1440 / im.width)))
            im.save(os.path.join(out_dir, name), "JPEG", quality=80)
        return True
    except Exception:  # noqa: BLE001
        return False
