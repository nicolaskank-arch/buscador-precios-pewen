# -*- coding: utf-8 -*-
"""
Actualiza TODO el catalogo de una: precios/cantidades/stock desde la lista
nueva + vuelve a aplicar las fotos ya conseguidas (PDF del proveedor, y web
si existe agregar_fotos_web.py). Un solo comando en vez de acordarse del
orden de 2-3 scripts.

Uso:
    python actualizar_catalogo.py "ruta a la Lista Minorista nueva.xlsx"

Que hace, en orden:
    1. build_catalogo.py <xlsx>   -> reconstruye productos.json desde cero
       (precios, stock, medidas, fotos de Drive). Esto pisa productos.json,
       asi que cualquier foto que NO venga de Drive se pierde en este paso...
    2. agregar_fotos_pdf.py       -> ...y se vuelve a aplicar aca (matchea de
       nuevo contra el productos.json fresco, no duplica nada).
    3. agregar_fotos_web.py       -> idem, si ya existe (se crea la primera
       vez que se completan fotos de internet).

Las fotos que sube el equipo desde la app (boton "Sacar/subir foto") NO
pasan por este script: viven en una planilla de Drive aparte y las lee
index.html en vivo -- no hay nada que perder ahi al actualizar precios.

Despues de correr esto falta: revisar SIN-FOTO.csv/AGRUPADOS.csv si querias,
y subir los cambios a GitHub (git add -A && git commit && git push).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def run(script, *args):
    print(f"\n=== {script} {' '.join(args)} ===")
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def main():
    if len(sys.argv) < 2:
        print('Uso: python actualizar_catalogo.py "ruta a la Lista Minorista nueva.xlsx"')
        sys.exit(1)
    xlsx_path = sys.argv[1]

    run("build_catalogo.py", xlsx_path)
    run("agregar_fotos_pdf.py")
    if (HERE / "agregar_fotos_web.py").exists():
        run("agregar_fotos_web.py")

    print("\nListo. Repasa SIN-FOTO.csv / AGRUPADOS.csv si queres, y despues:")
    print("  git add -A && git commit -m \"Actualizacion de precios\" && git push")


if __name__ == "__main__":
    main()
