# -*- coding: utf-8 -*-
"""
Baja el listado de fotos de la tienda de Chiusaroli (chiusaroli.com.ar,
Shopify) y lo guarda en fotos_chiusaroli.json: {"<sku>": ["url1", ...]}.

El sku de Chiusaroli ES el mismo codigo que usa Pewen, asi que despues se
matchea por codigo exacto (agregar_fotos_extra.py). Las fotos estan en el CDN
de Shopify, que manda Access-Control-Allow-Origin: *, asi que se pueden
hotlinkear Y adjuntar al compartir por WhatsApp. No traen marca de agua.

Cuidado con las variantes: un mismo producto de Shopify trae varios colores
(ej. "Angulo 20-4" Champagne y Plata). A cada sku se le asigna SU foto de
variante primero y despues las fotos generales del producto, pero nunca la
foto de otra variante hermana. Si un producto tiene varios colores y la
variante no tiene foto propia, ese sku se saltea (mejor sin foto que con la
de otro color).

No baja imagenes, solo URLs. Se corre de vez en cuando (no en cada
actualizacion de precios): el JSON queda en el repo.

Uso:
    python bajar_fotos_chiusaroli.py
"""
import json
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
SALIDA = HERE / "fotos_chiusaroli.json"
API = "https://www.chiusaroli.com.ar/products.json?limit=250&page={}"
MAX_FOTOS = 4


def bajar_todo():
    productos, pagina = [], 1
    while True:
        req = urllib.request.Request(API.format(pagina), headers={"User-Agent": "Mozilla/5.0"})
        lote = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))["products"]
        if not lote:
            return productos
        productos += lote
        pagina += 1
        time.sleep(2)  # sin rafagas


def limpio(u):
    return u.split("?")[0]


def main():
    productos = bajar_todo()
    por_sku, salteadas = {}, 0
    for p in productos:
        imgs = [limpio(i["src"]) for i in p["images"]]
        propias = {limpio(v["featured_image"]["src"]) for v in p["variants"] if v.get("featured_image")}
        generales = [u for u in imgs if u not in propias]
        por_color = any(o["name"].lower() in ("color", "style", "moldura") for o in p["options"])
        for v in p["variants"]:
            sku = (v.get("sku") or "").strip()
            if not sku:
                continue
            if v.get("featured_image"):
                urls = [limpio(v["featured_image"]["src"])] + generales
            elif len(p["variants"]) == 1 or not por_color:
                urls = imgs
            else:
                salteadas += 1
                continue
            if urls:
                por_sku[sku] = urls[:MAX_FOTOS]
    SALIDA.write_text(json.dumps(por_sku, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Productos Chiusaroli: {len(productos)} | skus con foto: {len(por_sku)} | "
          f"variantes de color sin foto propia (salteadas): {salteadas}")


if __name__ == "__main__":
    main()
