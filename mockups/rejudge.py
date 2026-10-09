"""Reavalia os esbocos NO AR com o juiz atual (processo separado; grava o andamento em JSON).

Uso: python mockups/rejudge.py --out <arquivo.json>
So emite veredito quando o juiz realmente comparou; se a captura ou a IA falhou, o esboco fica como 'sem_veredito' (nada e tirado do ar por falha tecnica).
"""
import argparse
import json
import os
import sys
import tempfile
import time
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import judge as judge_mod  # noqa: E402
import make_mockup as mm  # noqa: E402
import store  # noqa: E402


def candidates():
    now = int(time.time())
    return [m for m in store.list_all() if m["status"] == "ready" and m["expires_at"] > now]


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def evaluate(m):
    item = {"token": m["token"], "prospect_id": m["prospect_id"], "empresa": m["company"], "veredito": "sem_veredito", "motivo": "", "nota_site": None, "nota_esboco": None}
    idx = os.path.join(store.data_dir(), m["token"], "index.html")
    try:
        prospect = mm.load_prospect(m["prospect_id"])
    except SystemExit:
        item["motivo"] = "lead nao encontrado"
        return item
    if not (prospect.get("website") or "").strip() or not os.path.exists(idx):
        item["motivo"] = "esboco sem site para comparar (ou arquivo ausente)"
        item["veredito"] = "nao_se_aplica"
        return item
    work = tempfile.mkdtemp(prefix="rj_")
    try:
        shot = os.path.join(mm.ROOT, "static", "screenshots", prospect.get("screenshot") or "")
        ok, why, ns, nm, _cost = judge_mod.judge_mockup(prospect, idx, work, saved_shot=shot)
        item["motivo"], item["nota_site"], item["nota_esboco"] = why, ns, nm
        if ns is None:                      # falha tecnica (captura/IA): nao decide
            item["veredito"] = "sem_veredito"
        else:
            item["veredito"] = "mantem" if ok else "reprova"
    except Exception as e:  # noqa: BLE001
        item["motivo"] = f"erro: {type(e).__name__}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cands = candidates()
    data = {"iniciado": time.strftime("%d/%m %H:%M"), "total": len(cands), "feitos": 0, "terminou": False, "itens": []}
    save(a.out, data)
    for m in cands:
        data["itens"].append(evaluate(m))
        data["feitos"] += 1
        save(a.out, data)
    data["terminou"] = True
    data["terminado_em"] = time.strftime("%d/%m %H:%M")
    save(a.out, data)


if __name__ == "__main__":
    main()
