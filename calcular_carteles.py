# -*- coding: utf-8 -*-
"""
Carteles de la ficha, comparando la lista actual contra la ANTERIOR:

  - "Bajo X%"           alguna variante bajo 3% o mas (misma moneda).
  - "Gran oportunidad"  bajo mas de 15% (reemplaza al de "Bajo").
  - "Nuevo"             ninguna de sus variantes estaba en la lista anterior,
                        y es piso, deck o revestimiento (no grupo "Otros" --
                        colchones, sommiers -- ni "Accesorios" -- zocalos,
                        adhesivos, limpiadores).

Duran hasta la proxima lista: cada lista nueva se compara contra la que
reemplaza.

La lista anterior vive en lista_anterior.json (codigo -> precio y moneda).
actualizar_catalogo.py la guarda ANTES de reconstruir el catalogo con
--guardar-anterior, y solo si el xlsx que entra es otro (si se re-corre la
misma lista, se sigue comparando contra la de antes, no contra si misma).

Escribe en productos.json:
  producto: cartel ("baja" | "oportunidad" | "nuevo"), baja_pct,
            precio_desde_anterior
  variante: precio_anterior (solo si esa variante bajo)

Uso:
    python calcular_carteles.py                          # aplica carteles
    python calcular_carteles.py --guardar-anterior X.xlsx
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
PRODUCTOS_JSON = HERE / "productos.json"
LISTA_ANTERIOR = HERE / "lista_anterior.json"

BAJA_MIN = 0.03
OPORTUNIDAD_MIN = 0.15
SIN_CARTEL_NUEVO = {"Otros", "Accesorios"}


def guardar_anterior(xlsx_path):
    if not PRODUCTOS_JSON.exists():
        return
    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    if data.get("generado_de") == Path(xlsx_path).name:
        print("Es la misma lista que ya estaba cargada: se mantiene lista_anterior.json.")
        return
    variantes = {
        v["codigo"]: {"precio_venta": v["precio_venta"], "moneda": v["moneda"]}
        for p in data["productos"] for v in p["variantes"]
    }
    LISTA_ANTERIOR.write_text(json.dumps(
        {"generado_de": data.get("generado_de"), "variantes": variantes},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Lista anterior guardada ({data.get('generado_de')}, {len(variantes)} variantes).")


def es_piso_o_revestimiento(p):
    return p["grupo"] not in SIN_CARTEL_NUEVO


def aplicar():
    if not LISTA_ANTERIOR.exists():
        print("No hay lista_anterior.json -- sin carteles (pasa la primera vez).")
        return
    anterior = json.loads(LISTA_ANTERIOR.read_text(encoding="utf-8"))
    prev = anterior["variantes"]
    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    data["carteles_vs"] = anterior.get("generado_de")

    conteo = {"baja": 0, "oportunidad": 0, "nuevo": 0}
    for p in data["productos"]:
        for k in ("cartel", "baja_pct", "precio_desde_anterior"):
            p.pop(k, None)
        mayor_baja = 0.0
        viejos = []
        for v in p["variantes"]:
            v.pop("precio_anterior", None)
            ant = prev.get(v["codigo"])
            if not ant or ant["moneda"] != v["moneda"] or not ant["precio_venta"] or v["precio_venta"] is None:
                continue
            viejos.append(ant["precio_venta"])
            baja = 1 - v["precio_venta"] / ant["precio_venta"]
            if baja >= BAJA_MIN:
                v["precio_anterior"] = ant["precio_venta"]
                mayor_baja = max(mayor_baja, baja)

        if mayor_baja >= BAJA_MIN:
            p["cartel"] = "oportunidad" if mayor_baja > OPORTUNIDAD_MIN else "baja"
            p["baja_pct"] = round(mayor_baja * 100)
            # El "desde" viejo tachado, solo si el "desde" de hoy es mas bajo.
            if viejos and p["precio_desde"] is not None and p["precio_desde"] < min(viejos) * (1 - BAJA_MIN):
                p["precio_desde_anterior"] = min(viejos)
        elif not any(v["codigo"] in prev for v in p["variantes"]) and es_piso_o_revestimiento(p):
            p["cartel"] = "nuevo"
        if p.get("cartel"):
            conteo[p["cartel"]] += 1

    PRODUCTOS_JSON.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Carteles vs {anterior.get('generado_de')}: bajaron {conteo['baja']} | "
          f"gran oportunidad {conteo['oportunidad']} | nuevos {conteo['nuevo']}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--guardar-anterior":
        guardar_anterior(sys.argv[2])
    else:
        aplicar()
