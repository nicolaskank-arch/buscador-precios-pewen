# -*- coding: utf-8 -*-
"""
Suma fotos EXTRA a cada producto (galeria), ademas de su foto principal
(foto_url), matcheadas por codigo exacto (el id del producto y el codigo de
cada una de sus variantes). Fuentes, en este orden:
  - fotos_maxipiso.json (lo genera bajar_fotos_maxipiso.py) y
    fotos_chiusaroli.json (bajar_fotos_chiusaroli.py): hotlink, sus
    servidores dejan adjuntarlas al compartir.
  - fotos_extra_manual.json: fotos BAJADAS a fotos/ de sitios que no dejan
    adjuntarlas por CORS (ej. villagres.com.br), servidas desde el mismo
    buscador. {"<codigo>": {"fuente": "...", "pagina": "...", "fotos": [...]}}
    Van primero: son las del fabricante.

- Escribe p["fotos_extra"] = [urls...] sin repetir foto_url.
- Si el producto no tenia foto principal, la primera extra pasa a ser la
  principal (foto_fuente="web", foto_fuente_sitio="maxipiso.com.ar").
- Re-corrible: recalcula fotos_extra desde cero cada vez.

Va ULTIMO en actualizar_catalogo.py (despues de las fotos de PDF y web).

Uso:
    python agregar_fotos_extra.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
PRODUCTOS_JSON = HERE / "productos.json"
SIN_FOTO_CSV = HERE / "SIN-FOTO.csv"
FOTOS_MAXIPISO = HERE / "fotos_maxipiso.json"
FOTOS_CHIUSAROLI = HERE / "fotos_chiusaroli.json"
FOTOS_MANUAL = HERE / "fotos_extra_manual.json"


def main():
    if not FOTOS_MAXIPISO.exists():
        print("No hay fotos_maxipiso.json (correr bajar_fotos_maxipiso.py) -- nada que hacer.")
        return
    maxi = json.loads(FOTOS_MAXIPISO.read_text(encoding="utf-8"))
    if FOTOS_CHIUSAROLI.exists():
        for cod, urls in json.loads(FOTOS_CHIUSAROLI.read_text(encoding="utf-8")).items():
            maxi[cod] = maxi.get(cod, []) + [u for u in urls if u not in maxi.get(cod, [])]
    if FOTOS_MANUAL.exists():
        for cod, d in json.loads(FOTOS_MANUAL.read_text(encoding="utf-8")).items():
            maxi[cod] = d["fotos"] + [u for u in maxi.get(cod, []) if u not in d["fotos"]]
    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    productos = data["productos"]

    con_extra = nuevas_principales = total_extra = muertas = 0
    for p in productos:
        codigos = [p["id"]] + [str(v.get("codigo")) for v in p["variantes"]]
        urls = []
        for c in codigos:
            for u in maxi.get(c, []):
                if u not in urls:
                    urls.append(u)
        # Maxipiso tenia tienda Shopify (maxipiso.com.ar/cdn/shop/...) y se mudo:
        # esos links dan 404. Se reemplazan por la foto nueva, o se sacan si no hay.
        if "maxipiso.com.ar/cdn/shop/" in (p.get("foto_url") or ""):
            p["foto_url"] = None
            muertas += 1
        if not p.get("foto_url") and urls:
            p["foto_url"] = urls[0]
            p["foto_fuente"] = "web"
            p["foto_fuente_sitio"] = "maxipiso.com.ar"
            nuevas_principales += 1
        extra = [u for u in urls if u != p.get("foto_url")]
        if extra:
            p["fotos_extra"] = extra
            con_extra += 1
            total_extra += len(extra)
        else:
            p.pop("fotos_extra", None)

    PRODUCTOS_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    sin = [p for p in productos if not p.get("foto_url")]
    with open(SIN_FOTO_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rubro", "linea", "nombre_base", "nombre_ejemplo"])
        for p in sin:
            w.writerow([p["rubro"], p["linea"], p["nombre_base"], p["variantes"][0].get("nombre") or ""])

    print(f"Productos con fotos extra: {con_extra} ({total_extra} fotos) | "
          f"nuevas principales: {nuevas_principales} | links muertos de Maxipiso sacados: {muertas} | "
          f"quedan sin foto: {len(sin)}")


if __name__ == "__main__":
    main()
