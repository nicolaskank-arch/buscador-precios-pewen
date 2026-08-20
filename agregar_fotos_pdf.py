# -*- coding: utf-8 -*-
"""
Agrega fotos a productos.json usando como fuente extra el catalogo PDF de un
PROVEEDOR ("Maxi Piso"). Del PDF solo se usan las FOTOS -- el precio de ese PDF
no se toca ni se guarda en ningun lado (nuestra lista de precios propia sigue
siendo la unica fuente de precio, ver build_catalogo.py).

Metodo:
  1. Por cada pagina del PDF: se toman los bloques de texto con posicion
     (page.get_text("blocks")) y se identifican los que tienen forma de
     "codigo - nombre" / "codigo" / "nombre" seguido de specs (mm/Caja/m2/AC).
  2. Para cada bloque asi, se busca la imagen (o grupo de imagenes) cuyo bbox
     esta inmediatamente ARRIBA y alineado en X -- se toma la de mayor area de
     esa zona como "la foto". Si hay ambiguedad (dos bloques reclaman la misma
     imagen, o no hay imagen clara), se descarta esa fila antes que asignar mal.
  3. Se recorta la pagina renderizada en ese bbox (page.get_pixmap(clip=...))
     a _pdf_extraidas/ -- esto aplana badges/banda de precio/textura en un solo
     PNG limpio, sin lidiar con capas de XObjects superpuestas.
  4. Matching contra nuestro catalogo (productos.json):
     - "codigo": el codigo de proveedor (ej. P1202, 43127, K325) aparece como
       palabra significativa DENTRO del nombre_base/nombre de un producto
       nuestro (ya probamos matchear contra variantes[].codigo directo -- da
       0% de acierto, porque nuestro codigo es un ID interno correlativo, no
       el codigo de fabrica; en cambio muchos productos "Flotante"/"SPC"
       tienen el codigo de fabrica pegado en el nombre, ej. "Kronotex P1202
       Adak" -- eso es lo que se aprovecha aca).
     - "nombre": si no hay codigo, se prueba con la misma logica conservadora
       de build_catalogo.buscar_foto (overlap de palabras significativas,
       con umbral segun si el overlap incluye o no una palabra con digitos).
     Solo se asignan fotos a productos que TODAVIA no tienen foto_url (no se
     pisa nada existente).
  5. Se guardan las fotos elegidas en fotos/pdf_<id>.jpg (JPEG calidad 85), se
     actualiza productos.json (foto_url + foto_fuente="pdf_proveedor") y se
     reescribe SIN-FOTO.csv sin los productos ya completados.

Re-corrible: si se vuelve a correr, los productos que ya tienen foto_url (de
esta fuente o de otra) se saltean -- no se duplica ni se pisa nada.

Uso:
    python agregar_fotos_pdf.py ["ruta al pdf, opcional"]
"""
import sys
import re
import io
import json
import csv
import importlib.util
from pathlib import Path
from collections import defaultdict

import fitz  # PyMuPDF
from PIL import Image

HERE = Path(__file__).parent
DEFAULT_PDF = Path(r"C:\Users\Win10.DESKTOP-2PLJ2EA\Downloads\0.Lista_GENERAL_05-2026#6 (1).pdf")
CROPS_DIR = HERE / "_pdf_extraidas"
FOTOS_DIR = HERE / "fotos"
PRODUCTOS_JSON = HERE / "productos.json"
SIN_FOTO_CSV = HERE / "SIN-FOTO.csv"

# --- Reusamos significant_words()/STOPWORDS de build_catalogo.py (mismo criterio
# conservador que ya usa el pipeline principal para matchear foto <-> producto). ---
_spec = importlib.util.spec_from_file_location("build_catalogo", HERE / "build_catalogo.py")
_bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bc)
significant_words = _bc.significant_words

DPI = 200
PT_TO_PX = DPI / 72.0

# Palabras que aparecen mucho en el PDF del proveedor y no aportan nada al
# matching (categorias, badges, etiquetas de layout). significant_words() ya
# filtra palabras de <4 letras (saca SPC/LVT/AC4/AC5/8mm solas), esto suma
# algunas mas largas que igual son ruido de catalogo-de-proveedor.
PDF_STOPWORDS_EXTRA = {
    "MAXIPISO", "WATERPROOF", "GRATIS", "MANTO", "VENTA", "LOTE", "NUEVO",
    "INGRESO", "ECONOMY", "CLICK", "ONEFLOOR", "AQUABLUE", "MAXCORE",
    "CHALLET", "OFERTA", "OFERTAS", "CATALOGO", "ORIGEN", "ALEMAN", "CHINA",
}

CODE_RE = re.compile(r"^[A-Z]{0,3}\d{2,6}(-\d{1,3})?$")


def looks_like_code(word):
    return bool(CODE_RE.match(word)) and any(c.isdigit() for c in word)


def pdf_significant_words(text):
    words = significant_words(text)
    return [w for w in words if w not in PDF_STOPWORDS_EXTRA]


TAG_ONLY = {
    "ROLLO", "DRYBACK", "SIERRA", "OASIS", "GRATIS", "MANTO", "VENTA",
    "NUEVO", "OFERTA", "ORIGEN", "ALEMAN", "CHINA", "SPC", "LVT", "MDF",
}


def is_candidate_block(block_text):
    lines = [l.strip() for l in block_text.strip("\n").split("\n") if l.strip()]
    if not lines:
        return False
    first = lines[0]
    if len(first) < 2 or len(first) > 60:
        return False
    if first.upper().startswith(("U$S", "USD", "U$s".upper())):
        return False
    if re.match(r"^\+?\s*iva", first, re.I):
        return False
    if re.fullmatch(r"(AC\d|\d+[.,]?\d*\s*mm)", first, re.I):
        return False
    # Lineas de medidas tipo "4/0.3 x 610 x 305mm" o "12mm x 191mm x 1380mm"
    # a veces quedan en su PROPIO bloque de texto (separado del nombre, cuando
    # el layout no los combina). Sin este filtro se cuelan como si fueran el
    # nombre del producto y le "roban" la imagen de arriba al bloque real.
    if len(re.findall(r"\d\s*x\s*\d", first, re.I)) >= 2:
        return False
    if "Lista #" in block_text or "MAYO 2026" in block_text or "Índice" in block_text or "Indice" in block_text:
        return False
    if first.upper() in TAG_ONLY:
        return False
    has_spec_line = len(lines) >= 2 and re.search(r"(mm|caja|m2|m\u00b2|ac\d|x\s*\d)", lines[1], re.I)
    has_digit_first = re.search(r"\d", first) is not None
    if not (has_spec_line or (has_digit_first and len(first) <= 40)):
        return False
    return True


def extract_page(page, page_idx):
    """Devuelve lista de dicts {bbox, nombre_pdf} para los bloques de producto
    de esta pagina que se pudieron asociar sin ambiguedad a una imagen."""
    blocks = page.get_text("blocks")
    candidates = []
    for b in blocks:
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        if (x1 - x0) > 320 or (y1 - y0) > 90:
            continue  # bloque demasiado ancho/alto: fila fusionada o parrafo, ambiguo
        if (x1 - x0) < 30:
            continue
        if not is_candidate_block(text):
            continue
        first_line = text.strip("\n").split("\n")[0].strip()
        candidates.append({"bbox": (x0, y0, x1, y1), "nombre_pdf": first_line})

    if not candidates:
        return []

    imgs = page.get_image_info(xrefs=True)
    imgs = [im["bbox"] for im in imgs]

    assoc = {}  # id(candidate) -> chosen image bbox
    img_claims = defaultdict(list)  # image bbox (rounded) -> list of candidate idx

    for ci, cand in enumerate(candidates):
        bx0, by0, bx1, by1 = cand["bbox"]
        best = None
        best_area = 0
        for ix0, iy0, ix1, iy1 in imgs:
            iw, ih = ix1 - ix0, iy1 - iy0
            if iw <= 0 or ih <= 0:
                continue
            area = iw * ih
            if area < 1500 or iw > 350 or ih > 300:
                continue
            if iy1 > by0 + 6:
                continue  # la imagen tiene que terminar arriba (o casi) del texto
            if by0 - iy1 > 25:
                continue  # pero no muy lejos (si no, es de otra fila)
            overlap = min(bx1, ix1) - max(bx0, ix0)
            min_w = min(bx1 - bx0, ix1 - ix0)
            if overlap < 0.5 * min_w and overlap < 40:
                continue
            if area > best_area:
                best_area = area
                best = (round(ix0, 1), round(iy0, 1), round(ix1, 1), round(iy1, 1))
        if best:
            assoc[ci] = best
            img_claims[best].append(ci)

    out = []
    for ci, cand in enumerate(candidates):
        if ci not in assoc:
            continue
        img_bbox = assoc[ci]
        if len(img_claims[img_bbox]) > 1:
            continue  # dos bloques reclaman la misma foto -> ambiguo, se descarta
        out.append({"bbox": img_bbox, "nombre_pdf": cand["nombre_pdf"], "page": page_idx})
    return out


def main():
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf_path.exists():
        print(f"No encuentro el PDF: {pdf_path}")
        sys.exit(1)

    print(f"Abriendo {pdf_path.name} ...")
    doc = fitz.open(str(pdf_path))
    print(f"Paginas: {len(doc)}")

    CROPS_DIR.mkdir(exist_ok=True)
    FOTOS_DIR.mkdir(exist_ok=True)

    extraidas = []
    paginas_con_candidatos = 0
    paginas_sin_candidatos = 0
    for i in range(len(doc)):
        page = doc[i]
        items = extract_page(page, i)
        if items:
            paginas_con_candidatos += 1
        else:
            paginas_sin_candidatos += 1
        for k, item in enumerate(items):
            clip = fitz.Rect(*item["bbox"])
            pix = page.get_pixmap(clip=clip, dpi=DPI)
            crop_path = CROPS_DIR / f"p{i:02d}_{k:02d}.png"
            pix.save(str(crop_path))
            item["crop_path"] = crop_path
            extraidas.append(item)

    print(f"Paginas con al menos un producto detectado: {paginas_con_candidatos}")
    print(f"Paginas sin patron claro (salteadas): {paginas_sin_candidatos}")
    print(f"Fotos extraidas del PDF (recortes candidatos): {len(extraidas)}")

    # --- Cargar catalogo propio ---
    data = json.loads(PRODUCTOS_JSON.read_text(encoding="utf-8"))
    productos = data["productos"]
    by_id = {p["id"]: p for p in productos}

    def single_pass(exclude_ids):
        """Una pasada completa sobre TODOS los items extraidos, contra el pool de
        productos sin foto que quedan afuera de exclude_ids. Devuelve dict
        producto_id -> (item, tipo).

        Un mismo codigo "pelado" (ej. un numero de 4 digitos como 3003) puede
        aparecer por casualidad en dos productos de proveedor totalmente
        distintos dentro del PDF (un piso vinilico y, sin relacion, un SPC).
        Si dos items del PDF compiten por el mismo producto nuestro via
        codigo, no nos quedamos con "el primero que aparece en la pagina":
        elegimos el que tiene MAS palabras en comun (no solo el codigo) con
        el nombre del producto -- esa corroboracion extra es lo que separa un
        match real de una coincidencia numerica.
        """
        usados = set(exclude_ids)
        sin_foto_productos = [p for p in productos if p["id"] not in usados]
        word_index = defaultdict(set)
        prod_words = {}
        for p in sin_foto_productos:
            texto = p["nombre_base"] + " " + " ".join(v.get("nombre") or "" for v in p["variantes"])
            pw = set(pdf_significant_words(texto))
            prod_words[p["id"]] = pw
            for w in pw:
                word_index[w].add(p["id"])

        def overlap_score(words_a, words_b):
            overlap = words_a & words_b
            return sum(2 if looks_like_code(w) else 1 for w in overlap), overlap

        # 1) candidatos por codigo: para cada item, palabras con digitos que
        #    mapean (sin ambiguedad) a un solo producto. Se agrupan por
        #    producto para poder arbitrar competencia entre items.
        #
        #    Un codigo alfanumerico (P1202, D4739, K668...) es practicamente
        #    un SKU de fabrica -- confiamos en el solo. Un codigo puramente
        #    numerico corto (7001, 3003...) es mucho mas propenso a repetirse
        #    por casualidad entre productos de rubros distintos (nos paso con
        #    "3003": un vinilico y un SPC sin ninguna relacion compartian ese
        #    numero). Para esos exigimos ademas UNA palabra mas en comun con
        #    el nombre del producto -- si el unico punto de contacto es el
        #    numero pelado, mejor dejarlo sin foto que arriesgar un match
        #    cruzado.
        item_words = {}
        candidatos_por_producto = defaultdict(list)  # pid -> [(item, score)]
        for item in extraidas:
            words = pdf_significant_words(item["nombre_pdf"])
            item_words[id(item)] = words
            if not words:
                continue
            wset = set(words)
            vistos = set()
            for w in words:
                if not looks_like_code(w):
                    continue
                ids = word_index.get(w)
                if not ids or len(ids) != 1:
                    continue
                pid = next(iter(ids))
                if pid in usados or pid in vistos:
                    continue
                vistos.add(pid)
                score, overlap = overlap_score(wset, prod_words[pid])
                codigo_alfanumerico = bool(re.match(r"^[A-Z]", w))
                if not codigo_alfanumerico and len(overlap) < 2:
                    continue  # codigo numerico "pelado", sin corroboracion -> se descarta
                candidatos_por_producto[pid].append((item, score))

        asignados = {}
        resueltos_por_codigo = set()  # id(item)
        for pid, cands in candidatos_por_producto.items():
            if pid in usados:
                continue
            mejor_item, mejor_score = max(cands, key=lambda t: t[1])
            asignados[pid] = (mejor_item, "codigo")
            usados.add(pid)
            resueltos_por_codigo.add(id(mejor_item))

        # 2) fallback por nombre: overlap de palabras significativas contra
        #    nombre_base+variantes de productos sin foto (mismo criterio
        #    conservador que build_catalogo.buscar_foto). Solo para los items
        #    que no ganaron ningun producto por codigo.
        for item in extraidas:
            if id(item) in resueltos_por_codigo:
                continue
            words = item_words.get(id(item), [])
            if not words:
                continue
            wset = set(words)
            best = None
            best_score = 0
            best_con_codigo = False
            for p in sin_foto_productos:
                if p["id"] in usados:
                    continue
                score, overlap = overlap_score(wset, prod_words[p["id"]])
                if not overlap:
                    continue
                con_codigo = any(looks_like_code(w) for w in overlap)
                if score > best_score:
                    best_score = score
                    best = p
                    best_con_codigo = con_codigo
            umbral = 3 if best_con_codigo else 4
            if best is not None and best_score >= umbral:
                usados.add(best["id"])
                asignados[best["id"]] = (item, "nombre")
        return asignados

    # Corremos el matching a punto fijo: cada vez que un producto se resuelve,
    # queda afuera del pool de candidatos y eso puede desambiguar a un "hermano"
    # (mismo codigo de fabrica, otra variante de largo/coleccion) que antes
    # empataba en el ranking y perdia contra el que ya se uso. Repetimos pasadas
    # completas -- recalculando todo desde cero contra el set ya comprometido --
    # hasta que una pasada no sume ningun producto nuevo, asi una sola corrida
    # ya converge solita (no hace falta ejecutar el script varias veces a mano).
    comprometidos = {p["id"] for p in productos if p.get("foto_url")}
    resultados_por_id = {}
    for _ in range(25):
        asignados = single_pass(comprometidos)
        nuevos_ids = set(asignados) - set(resultados_por_id)
        if not nuevos_ids:
            break
        for pid in nuevos_ids:
            resultados_por_id[pid] = asignados[pid]
        comprometidos |= nuevos_ids

    resultados = [(item, by_id[pid], tipo) for pid, (item, tipo) in resultados_por_id.items()]

    print(f"Matcheadas contra el catalogo: {len(resultados)}")
    n_codigo = sum(1 for _, _, t in resultados if t == "codigo")
    n_nombre = sum(1 for _, _, t in resultados if t == "nombre")
    print(f"  por codigo embebido en nombre: {n_codigo}")
    print(f"  por nombre (overlap de palabras): {n_nombre}")

    # --- Copiar fotos + actualizar productos.json ---
    completados_sin_foto = 0
    muestras_nombre = []
    muestras_codigo = []
    for item, producto, tipo in resultados:
        destino = FOTOS_DIR / f"pdf_{producto['id']}.jpg"
        if not destino.exists():
            img = Image.open(item["crop_path"]).convert("RGB")
            img.save(destino, "JPEG", quality=85)
        producto["foto_url"] = f"fotos/{destino.name}"
        producto["foto_fuente"] = "pdf_proveedor"
        completados_sin_foto += 1
        muestra = (item["nombre_pdf"], producto["nombre_base"], producto["id"])
        if tipo == "nombre":
            muestras_nombre.append(muestra)
        else:
            muestras_codigo.append(muestra)

    print(f"Productos de SIN-FOTO.csv completados: {completados_sin_foto}")

    PRODUCTOS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )

    # --- Reescribir SIN-FOTO.csv sin los que ya se completaron ---
    with open(SIN_FOTO_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rubro", "linea", "nombre_base", "nombre_ejemplo"])
        for p in productos:
            if p.get("foto_url"):
                continue
            primero = p["variantes"][0]
            w.writerow([p["rubro"], p["linea"], p["nombre_base"], primero.get("nombre") or ""])

    print("productos.json y SIN-FOTO.csv actualizados.")

    print("\n--- Muestra de matches por NOMBRE (revisar) ---")
    for pdf_nombre, prod_nombre, pid in muestras_nombre[:20]:
        print(f"  [{pid}] '{pdf_nombre}' -> '{prod_nombre}'")
    print("\n--- Muestra de matches por CODIGO ---")
    for pdf_nombre, prod_nombre, pid in muestras_codigo[:10]:
        print(f"  [{pid}] '{pdf_nombre}' -> '{prod_nombre}'")

    return {
        "paginas_con_candidatos": paginas_con_candidatos,
        "paginas_sin_candidatos": paginas_sin_candidatos,
        "extraidas": len(extraidas),
        "matched": len(resultados),
        "n_codigo": n_codigo,
        "n_nombre": n_nombre,
        "completados": completados_sin_foto,
    }


if __name__ == "__main__":
    main()
