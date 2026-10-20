# -*- coding: utf-8 -*-
"""
Baja el listado de fotos del catalogo de Maxipiso (maxipiso.com.ar/catalogo)
y lo guarda en fotos_maxipiso.json: {"<sku>": ["url1", "url2", ...]}.

El sku de Maxipiso ES el mismo codigo que usa Pewen (el "id" de
productos.json y el "codigo" de cada variante), asi que despues se matchea
por codigo exacto, sin adivinar por nombre.

Las fotos de Maxipiso (Cloudinary y su propio dominio) mandan
Access-Control-Allow-Origin: *, asi que se pueden hotlinkear Y adjuntar al
compartir por WhatsApp -- no hace falta pasarlas a Drive.

No baja imagenes, solo URLs. Se corre de vez en cuando (no en cada
actualizacion de precios): el JSON queda en el repo y agregar_fotos_extra.py
lo aplica.

Uso:
    python bajar_fotos_maxipiso.py
"""
import json
import time
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
SALIDA = HERE / "fotos_maxipiso.json"
API = "https://www.maxipiso.com.ar/api/catalogo/todos?take=100&skip={}&sortBy=relevancia"
BASE = "https://www.maxipiso.com.ar"


def bajar_todo():
    productos, skip = [], 0
    while True:
        req = urllib.request.Request(API.format(skip), headers={"User-Agent": "Mozilla/5.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode("utf-8"))
        pagina = d["data"]["productos"]
        productos += pagina
        if len(pagina) < 100:
            return productos
        skip += 100
        time.sleep(2)  # sin rafagas


def urls_de(campo):
    """El campo 'imagenes' viene en 3 formatos: 'a | b', '["a","b"]' o rutas
    relativas '/123-1.jpg' (servidas desde su dominio)."""
    s = (campo or "").strip()
    if not s:
        return []
    partes = json.loads(s) if s.startswith("[") else s.split("|")
    urls = []
    for u in partes:
        u = u.strip()
        if u.startswith("/"):
            u = BASE + u
        if u and u not in urls:
            urls.append(u)
    return urls


def main():
    productos = bajar_todo()
    por_sku = {str(p["sku"]): urls_de(p.get("imagenes")) for p in productos if p.get("sku")}

    # Una misma imagen colgada de varios skus es un placeholder generico
    # (ej. /19453-1.jpg en 14 productos) -- no sirve como foto del producto.
    usos = Counter(u for urls in por_sku.values() for u in set(urls))
    repetidas = {u for u, c in usos.items() if c > 1}
    por_sku = {k: [u for u in v if u not in repetidas] for k, v in por_sku.items()}
    por_sku = {k: v for k, v in por_sku.items() if v}

    SALIDA.write_text(json.dumps(por_sku, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Productos Maxipiso: {len(productos)} | con foto: {len(por_sku)} | "
          f"fotos: {sum(len(v) for v in por_sku.values())} | placeholders descartados: {len(repetidas)}")


if __name__ == "__main__":
    main()
