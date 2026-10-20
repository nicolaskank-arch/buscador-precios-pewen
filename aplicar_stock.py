# -*- coding: utf-8 -*-
"""
Aplica el stock REAL de MAXIPISO (stock menos reservas) al catalogo. La
columna Stock de la lista de precios es el stock bruto: no descuenta lo
reservado (ej. decks con 800 m2 en la lista y todo vendido).

stock_maxipiso.json (NO va al repo, ver .gitignore) es una foto del sistema:
    {"fecha": "2026-10-20",
     "sin_stock": ["17628", ...],     # no aparecen con "Solo con stock"
     "reservado": {"22250": -959},    # disponible <= 0 (todo reservado)
     "poco": {"3421": 23, ...}}       # disponible entre 1 y 99
Todo codigo que no esta en ninguna de las tres tiene 100 o mas disponibles.
Se arma desde la web de MAXIPISO por Claude in Chrome (skill
stock-maxipiso-pewen): filtro "Solo con stock" prendido, cargar todo y
cruzar por codigo.

No se oculta nada (decision de Nico, 20/10): lo que no tiene stock se
publica igual con cartel.

Por medida (variante):
  - sin stock o todo reservado -> v["sin_stock"] = True.
  - no figura en MAXIPISO y la lista trae el stock VACIO -> producto a pedido
    o que no se maneja ahi (colchones, Armstrong/Forbo, adhesivos, pisos
    tecnicos): sin marca.
Por producto:
  - ninguna medida con stock -> p["sin_stock"] = True (cartel "Sin stock",
    va al final de la lista).
  - algunas sin stock -> el "desde" se calcula solo con las que tienen.
  - todas las que tienen stock con menos de 100 -> p["poco_stock"] = True
    (cartel "Queda poco stock").

Va justo despues de build_catalogo.py en actualizar_catalogo.py. Si no hay
stock_maxipiso.json, no toca nada.

Uso:
    python aplicar_stock.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
PRODUCTOS_JSON = HERE / "productos.json"
STOCK_JSON = HERE / "stock_maxipiso.json"
POCO_MAX = 100


def main():
    if not STOCK_JSON.exists():
        print("No hay stock_maxipiso.json -- se publica con el stock de la lista.")
        return
    st = json.loads(STOCK_JSON.read_text(encoding="utf-8"))
    sin = set(st["sin_stock"])
    reservado = st["reservado"]
    poco = st["poco"]

    def disponible(v):
        c = v["codigo"]
        if c in sin:
            return None if v["stock"] is None else 0  # None = a pedido / sin dato
        if c in reservado:
            return reservado[c]
        if c in poco:
            return poco[c]
        return POCO_MAX  # 100 o mas

    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    n_sin = n_poco = n_medidas = 0
    for p in data["productos"]:
        p.pop("sin_stock", None)
        p.pop("poco_stock", None)
        con_stock = []
        for v in p["variantes"]:
            v.pop("sin_stock", None)
            d = disponible(v)
            if d is not None and d <= 0:
                v["sin_stock"] = True
            else:
                con_stock.append((v, d))
        if not con_stock:
            p["sin_stock"] = True
            n_sin += 1
            continue
        if len(con_stock) < len(p["variantes"]):
            n_medidas += 1
            precios = [v["precio_venta"] for v, _ in con_stock if v["precio_venta"] is not None]
            if precios:
                p["precio_desde"] = min(precios)
        if all(d is not None and d < POCO_MAX for _, d in con_stock):
            p["poco_stock"] = True
            n_poco += 1

    data["stock_fecha"] = st.get("fecha")
    PRODUCTOS_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Stock MAXIPISO {st.get('fecha')}: sin stock {n_sin} | con algunas medidas sin stock {n_medidas} | "
          f"poco stock {n_poco} | total {len(data['productos'])}")


if __name__ == "__main__":
    main()
