# -*- coding: utf-8 -*-
"""
Agrega fotos a productos.json usando como fuente resultados YA CONFIRMADOS de
busqueda web en sitios de distribuidores/fabricantes (pisosalemanes.com,
pewenpisos.com.ar, maxipiso.com.ar, ergopisos.com.ar). NO baja ni guarda
imagenes: se hotlinkea directo a la URL de la fuente (mismo criterio que ya
usa el proyecto hermano stock-pewen con pewenpisos.com.ar).

Los resultados fueron investigados y confirmados a mano (uno por uno, con el
mismo criterio conservador de build_catalogo.buscar_foto: 2+ palabras
significativas en comun con bonus a las que traen codigo de diseno, mas
verificacion cruzada del nombre) y quedaron embebidos en el JSON intermedio
fotos_web_encontradas.json -- este script NO vuelve a scrapear nada en vivo,
solo lee ese JSON y lo aplica contra productos.json. Esto lo hace mas robusto
que repetir el scraping+matching en cada corrida (los sitios de terceros
cambian de HTML todo el tiempo) y mas facil de auditar (el JSON intermedio es
la lista completa y final de lo que se va a escribir).

fotos_web_encontradas.json: {"<id_producto>": {"url": "...", "fuente": "sitio.com"}}

Reglas (mismas que agregar_fotos_pdf.py):
  - Solo se asignan fotos a productos que TODAVIA no tienen foto_url (no se
    pisa nada existente, sea de Drive o del PDF de Maxi Piso).
  - Se guarda foto_url (la URL externa, SIN bajarla) + foto_fuente="web" +
    foto_fuente_sitio=<nombre del sitio de origen>, para trazabilidad.
  - Reescribe productos.json y SIN-FOTO.csv sin los productos completados.
  - Re-corrible: si se vuelve a correr, los productos que ya tienen foto_url
    (de esta fuente o de cualquier otra) se saltean.

  EXCEPCION -- REEMPLAZOS_FORZADOS (20/08/2026): estos 29 ids SI pueden
  pisar una foto_url existente. Son productos cuya foto venia de
  pisosalemanes.com con la marca de agua "PISOS ALEMANES" bien visible y
  centrada (no se puede tapar con un logo chico); se busco el mismo
  diseno/tono sin marca de agua en pewenpisos.com.ar / maxipiso.com.ar
  (coincidencia de codigo de diseno o SKU exacto, mas 4 verificados a mano
  por titulo/specs cuando el codigo no alcanzaba) y fotos_web_encontradas.json
  ya tiene la URL nueva para estos ids. Cualquier otro id que ya tenga
  foto_url (las otras ~631 fotos de Drive/PDF/otros sitios web) se sigue
  salteando como siempre -- esto NO es un flag general para pisar fotos.

Uso:
    python agregar_fotos_web.py
"""
import json
import csv
from pathlib import Path

HERE = Path(__file__).parent
PRODUCTOS_JSON = HERE / "productos.json"
SIN_FOTO_CSV = HERE / "SIN-FOTO.csv"
FOTOS_WEB_JSON = HERE / "fotos_web_encontradas.json"

REEMPLAZOS_FORZADOS = {
    "18247", "20377", "24648", "24650", "24653", "18941", "17271", "19021",
    "19029", "24644", "5263", "18188", "19376", "23771", "23772", "24781",
    "24783", "25316", "25318", "25319", "25472", "25372", "25373", "23063",
    "22899", "18422", "25341", "23516", "23233",
}

# pisosalemanes.com es un competidor y sus fotos traen su marca de agua
# encima -- no se usa mas como fuente, ni para productos nuevos ni para
# completar SIN-FOTO. Si fotos_web_encontradas.json trae una entrada de ahi
# (de una tanda de busqueda vieja) se ignora aca en vez de confiar en que a
# nadie se le escape sacarla del JSON a mano.
SITIOS_EXCLUIDOS = {"pisosalemanes.com"}


def main():
    encontradas = json.loads(FOTOS_WEB_JSON.read_text(encoding="utf-8"))
    print(f"Resultados web confirmados (fotos_web_encontradas.json): {len(encontradas)}")

    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    productos = data["productos"]
    by_id = {p["id"]: p for p in productos}

    aplicadas = 0
    reemplazadas = 0
    saltadas_ya_tenian = 0
    saltadas_id_inexistente = 0
    por_sitio = {}

    saltadas_sitio_excluido = 0
    for pid, info in encontradas.items():
        if info.get("fuente") in SITIOS_EXCLUIDOS:
            saltadas_sitio_excluido += 1
            continue
        p = by_id.get(pid)
        if p is None:
            saltadas_id_inexistente += 1
            continue
        es_reemplazo_forzado = pid in REEMPLAZOS_FORZADOS
        if p.get("foto_url") and not es_reemplazo_forzado:
            saltadas_ya_tenian += 1
            continue
        if es_reemplazo_forzado and p.get("foto_url"):
            fuente_anterior = p.get("foto_fuente_sitio")
            print(f"  reemplazo forzado: {pid} ({p['nombre_base'][:45]}) {fuente_anterior} -> {info['fuente']}")
            reemplazadas += 1
        p["foto_url"] = info["url"]
        p["foto_fuente"] = "web"
        p["foto_fuente_sitio"] = info["fuente"]
        aplicadas += 1
        por_sitio[info["fuente"]] = por_sitio.get(info["fuente"], 0) + 1

    print(f"Fotos aplicadas ahora: {aplicadas}")
    if reemplazadas:
        print(f"  de las cuales son reemplazos forzados (pisaron una foto existente): {reemplazadas}")
    if saltadas_ya_tenian:
        print(f"  saltadas (ya tenian foto de otra fuente): {saltadas_ya_tenian}")
    if saltadas_id_inexistente:
        print(f"  saltadas (id ya no existe en productos.json): {saltadas_id_inexistente}")
    if saltadas_sitio_excluido:
        print(f"  saltadas (sitio excluido, ej. competidor con marca de agua): {saltadas_sitio_excluido}")
    print("Desglose por sitio de origen:")
    for sitio, n in sorted(por_sitio.items(), key=lambda kv: -kv[1]):
        print(f"  {sitio}: {n}")

    PRODUCTOS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    with open(SIN_FOTO_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rubro", "linea", "nombre_base", "nombre_ejemplo"])
        restantes = 0
        for p in productos:
            if p.get("foto_url"):
                continue
            restantes += 1
            primero = p["variantes"][0]
            w.writerow([p["rubro"], p["linea"], p["nombre_base"], primero.get("nombre") or ""])

    print(f"productos.json y SIN-FOTO.csv actualizados. Quedan sin foto: {restantes}")


if __name__ == "__main__":
    main()
