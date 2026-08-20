# Buscador de Precios Pewen

Buscador interno (equipo de ventas) por tipo de piso, material y detalle, con foto y precio. Fuente: la lista minorista en xlsx que pasa Nico + las fotos ya indexadas en `buscador-fotos-pewen/fotos.db`.

## Archivos
- `index.html` — la app (una sola página, mobile-first, mismo estilo que Stock Pewen).
- `productos.json` — el catálogo ya armado, lo consume `index.html`. Se regenera, no se edita a mano.
- `build_catalogo.py` — arma `productos.json` a partir del xlsx.
- `SIN-FOTO.csv` — productos que quedaron sin foto (para ir completando con fotos nuevas de Drive o de internet).
- `AGRUPADOS.csv` — productos que el script fusionó en una sola card por venir en varias medidas (para revisar que no se haya fusionado mal algo).
- `fotos/` — thumbnails copiados de `buscador-fotos-pewen/thumbs` (no se suben a Drive, son una copia local liviana).

## Cómo actualizar cuando entran productos nuevos
```bash
python build_catalogo.py "ruta a la Lista Minorista nueva.xlsx"
```
Esto pisa `productos.json`, `SIN-FOTO.csv`, `AGRUPADOS.csv` y agrega fotos nuevas a `fotos/`. Después hay que volver a publicar (ver abajo).

Si cambian nombres de columnas en la planilla, hay que ajustar los índices `COL_*` al principio de `build_catalogo.py`.

## Qué precio se muestra
"Precio de Lista" de la planilla es el precio **sin descuento** (es el mismo que el de tarjeta en 12 pagos). Lo que se muestra en el buscador es la columna **"0-50 m² con descuento admisible, contado/transferencia"** — el precio real que se cobra en una venta chica. El resto de los rangos de m² y formas de pago están en "Ver medidas y precios" de cada card.

## Qué quedó afuera
Zócalos, terminaciones, adhesivos/pegamentos, accesorios de deck/pared, muebles de jardín, césped, servicios — no son pisos ni pared, no tiene sentido buscarlos acá. El detalle exacto de rubros excluidos está en `EXCLUDE_RUBROS` dentro de `build_catalogo.py`.

## Fotos
Se buscan primero en el índice ya armado de Drive (`buscador-fotos-pewen/fotos.db`), acotado a la carpeta de Drive que corresponde al rubro y exigiendo que coincidan varias palabras del nombre (no cualquier match — se prefiere dejar "sin foto" antes que mostrar la foto de otro producto). Cobertura actual: ~12% (220 de 1900). El resto queda en `SIN-FOTO.csv` para ir completando de a poco, buscando en internet o sacando fotos nuevas.

## Subir fotos desde la app (celu o PC)
Cada card tiene un botón "📷 Sacar/subir foto": en el celu abre la cámara directo, en la compu abre el explorador de archivos. La foto se achica en el navegador antes de mandarla (liviana, anda bien con datos móviles) y queda visible **al toque para todo el equipo** — no hay revisión previa. Si alguien sube una equivocada, alcanza con subir otra encima (la nueva pisa a la vieja) o borrar la fila en la planilla "Fotos Subidas" de Drive.

Esto necesita el backend de `apps-script/Codigo.gs` deployado (ver `GUIA-DEPLOY.html`, parte A) y la URL pegada en `var SCRIPT_URL = "";` dentro de `index.html`. Sin eso, el botón avisa que falta configurarlo pero el resto de la app funciona igual.

## Publicar
Ver `GUIA-DEPLOY.html`: subir a un repo de GitHub y activar GitHub Pages. Como es un catálogo interno con precios, conviene que el repo quede **privado** (GitHub Pages con repo privado funciona con plan pago, o dando acceso al repo a cada persona) — o si va público, que el link no se difunda.
