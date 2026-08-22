/**
 * BUSCADOR DE PRECIOS PEWEN — Web App (Google Apps Script)
 * ------------------------------------------------------------
 * Tres cosas:
 *  1) Recibe fotos que el equipo sube o saca desde el buscador (celu o PC),
 *     las guarda en una carpeta de Drive y las anota en una planilla
 *     (CODIGO -> URL, puede haber varias por código). El buscador lee esa
 *     planilla al abrir (y cada tanto mientras sigue abierto) y arma la
 *     galería de cada producto — sin pasar por vos, aparecen al toque.
 *  2) Deja marcar una foto como "principal" (la que se ve primero en la
 *     card) y "ocultar" una foto que no sirve (subida por el equipo O la
 *     original del catálogo, ej. una con marca de agua ajena) — las dos
 *     cosas quedan anotadas acá, nunca se toca productos.json.
 *  3) Registra qué producto abre cada vendedor (con "Ver medidas y precios"),
 *     para poder ordenar por "más buscados".
 *
 * No hay moderación: lo que se sube/oculta/marca se ve enseguida. Para
 * deshacer algo, se borra la fila correspondiente en la planilla.
 * ------------------------------------------------------------
 */

var CONFIG = {
  // Opcional: ID de una carpeta de Drive ya existente para guardar las fotos.
  // Si lo dejás vacío, el script crea una carpeta la primera vez que alguien
  // sube una foto y de ahí en más siempre usa esa misma (queda guardada con
  // PropertiesService, no hace falta copiar nada a mano). Para ver cuál es,
  // correr Ejecutar > verEnlaces.
  FOLDER_ID: '',

  // Igual que arriba pero para la planilla (todas las pestañas viven en una sola).
  SHEET_ID: '',
  TAB_FOTOS: 'Fotos Subidas',
  TAB_VISTAS: 'Vistas',
  TAB_OCULTAS: 'Fotos Ocultas',
  TAB_PRINCIPAL: 'Foto Principal',

  // Bajo a propósito: el equipo va a estar subiendo/editando fotos en tanda
  // y no quiere ver algo desactualizado por llegar tarde el caché.
  CACHE_SECONDS_FOTOS: 20,
  CACHE_SECONDS_POPULARES: 300
};

// ====== ACCIONES QUE ESCRIBEN (desde el buscador) ======
function doPost(e) {
  var out;
  try {
    var body = JSON.parse(e.postData.contents);

    if (body.accion === 'vista') {
      registrarVista(body.codigo, body.nombre || '', body.vendedor || '');
      out = { ok: true };
    } else if (body.accion === 'ocultar_foto') {
      ocultarFoto(body.codigo, body.url, body.vendedor || '');
      out = { ok: true };
    } else if (body.accion === 'set_principal') {
      setPrincipal(body.codigo, body.url, body.vendedor || '');
      out = { ok: true };
    } else {
      var codigo = String(body.codigo || '').trim();
      var imagenBase64 = body.imagenBase64 || '';
      var mimeType = body.mimeType || 'image/jpeg';
      if (!codigo || !imagenBase64) throw new Error('Falta código o imagen.');

      var carpeta = DriveApp.getFolderById(getFolderId());
      var bytes = Utilities.base64Decode(imagenBase64);
      var ext = mimeType.indexOf('png') >= 0 ? 'png' : 'jpg';
      var nombreArchivo = codigo + '_' + Date.now() + '.' + ext;
      var blob = Utilities.newBlob(bytes, mimeType, nombreArchivo);
      var archivo = carpeta.createFile(blob);
      archivo.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

      // OJO: usar lh3.googleusercontent.com y NO drive.google.com/thumbnail --
      // el navegador puede pedir esta con fetch() (CORS permisivo) y por eso
      // se puede adjuntar al compartir por WhatsApp; la de drive.google.com
      // se puede mostrar en una <img> pero un fetch() de JS la rechaza.
      var url = 'https://lh3.googleusercontent.com/d/' + archivo.getId() + '=w1600';
      anotarFoto(codigo, body.nombre || '', url, body.vendedor || '');

      out = { ok: true, url: url };
    }
  } catch (err) {
    out = { ok: false, error: String(err && err.message || err) };
  }
  return ContentService
    .createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====== LECTURA (el buscador la pide seguido) ======
function doGet(e) {
  var out;
  try {
    var p = (e && e.parameter) || {};
    if (p.estado === '1') {
      // un solo pedido con todo lo que necesita la app — menos idas y vueltas
      out = {
        ok: true,
        fotos: getFotosSubidas(),
        populares: getPopulares(),
        ocultas: getOcultas(),
        principales: getPrincipales(),
        ranking: getRanking()
      };
    } else if (p.fotos === '1') {
      out = { ok: true, fotos: getFotosSubidas() };
    } else if (p.populares === '1') {
      out = { ok: true, populares: getPopulares() };
    } else {
      out = { ok: true, msg: 'Buscador de Precios Pewen — backend.' };
    }
  } catch (err) {
    out = { ok: false, error: String(err && err.message || err) };
  }
  return ContentService
    .createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====== FOTOS SUBIDAS ======
function anotarFoto(codigo, nombre, url, vendedor) {
  var sh = getSheet(CONFIG.TAB_FOTOS, ['Codigo', 'Nombre', 'Url', 'Vendedor', 'Fecha']);
  sh.appendRow([codigo, nombre, url, vendedor, nowIso()]);
  CacheService.getScriptCache().remove('fotos_subidas_v3');
}

// Devuelve {codigo: [{url, vendedor, fecha}, ...]} — puede haber varias fotos
// por código (más recientes al final); el buscador arma la galería con eso.
function getFotosSubidas() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('fotos_subidas_v3');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var sh = getSheet(CONFIG.TAB_FOTOS, ['Codigo', 'Nombre', 'Url', 'Vendedor', 'Fecha']);
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var r = 1; r < vals.length; r++) {
    var codigo = String(vals[r][0] || '').trim();
    var url = normalizarUrlFoto(vals[r][2]);
    if (!codigo || !url) continue;
    if (!map[codigo]) map[codigo] = [];
    map[codigo].push({ url: url, vendedor: String(vals[r][3] || ''), fecha: String(vals[r][4] || '') });
  }
  cache.put('fotos_subidas_v3', JSON.stringify(map), CONFIG.CACHE_SECONDS_FOTOS);
  return map;
}

// Las fotos subidas por el equipo se guardaron en algun momento como
// drive.google.com/thumbnail?id=... (se ve bien en una <img> pero un
// fetch() de JS la rechaza por CORS, asi que no se puede adjuntar al
// compartir por WhatsApp). lh3.googleusercontent.com es el mismo archivo
// de Drive pero con CORS permisivo. Se normaliza aca -- en la LECTURA, no
// en la planilla -- para que las fotos viejas tambien queden arregladas
// sin tener que volver a subirlas, y para que ocultar/marcar principal
// (que comparan por URL exacta) sigan matcheando pase lo que pase con el
// formato historico de cada fila.
function normalizarUrlFoto(url) {
  url = String(url || '').trim();
  var m = url.match(/[?&]id=([^&]+)/) || url.match(/\/d\/([^/=?]+)/);
  if (!m) return url; // no es una url de Drive reconocida (ej. una foto original del catalogo) -- se deja igual
  return 'https://lh3.googleusercontent.com/d/' + m[1] + '=w1600';
}

// ====== OCULTAR FOTO (subida O la original del catalogo — misma mecanica) ======
function ocultarFoto(codigo, url, vendedor) {
  codigo = String(codigo || '').trim();
  url = String(url || '').trim();
  if (!codigo || !url) throw new Error('Falta código o url.');
  var sh = getSheet(CONFIG.TAB_OCULTAS, ['Codigo', 'Url', 'Vendedor', 'Fecha']);
  sh.appendRow([codigo, url, vendedor || '', nowIso()]);
  CacheService.getScriptCache().remove('fotos_ocultas_v1');
}

// Devuelve {codigo: [url, url, ...]} — las que hay que sacar de la galeria.
function getOcultas() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('fotos_ocultas_v1');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var sh = getSheet(CONFIG.TAB_OCULTAS, ['Codigo', 'Url', 'Vendedor', 'Fecha']);
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var r = 1; r < vals.length; r++) {
    var codigo = String(vals[r][0] || '').trim();
    var url = normalizarUrlFoto(vals[r][1]);
    if (!codigo || !url) continue;
    if (!map[codigo]) map[codigo] = [];
    map[codigo].push(url);
  }
  cache.put('fotos_ocultas_v1', JSON.stringify(map), CONFIG.CACHE_SECONDS_FOTOS);
  return map;
}

// ====== FOTO PRINCIPAL (cual se ve primero en la card) ======
function setPrincipal(codigo, url, vendedor) {
  codigo = String(codigo || '').trim();
  url = String(url || '').trim();
  if (!codigo || !url) throw new Error('Falta código o url.');
  var sh = getSheet(CONFIG.TAB_PRINCIPAL, ['Codigo', 'Url', 'Vendedor', 'Fecha']);
  sh.appendRow([codigo, url, vendedor || '', nowIso()]);
  CacheService.getScriptCache().remove('fotos_principal_v1');
}

// Devuelve {codigo: url} — la ultima marcada gana.
function getPrincipales() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('fotos_principal_v1');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var sh = getSheet(CONFIG.TAB_PRINCIPAL, ['Codigo', 'Url', 'Vendedor', 'Fecha']);
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var r = 1; r < vals.length; r++) {
    var codigo = String(vals[r][0] || '').trim();
    var url = normalizarUrlFoto(vals[r][1]);
    if (!codigo || !url) continue;
    map[codigo] = url; // la ultima fila de cada codigo pisa a la anterior
  }
  cache.put('fotos_principal_v1', JSON.stringify(map), CONFIG.CACHE_SECONDS_FOTOS);
  return map;
}

// ====== VISTAS (para "más buscados" y para saber quién trabajó qué) ======
function registrarVista(codigo, nombre, vendedor) {
  codigo = String(codigo || '').trim();
  if (!codigo) return;
  var sh = getSheet(CONFIG.TAB_VISTAS, ['Codigo', 'Nombre', 'Vendedor', 'Fecha']);
  sh.appendRow([codigo, nombre, vendedor || '', nowIso()]);
}

// Devuelve {codigo: cantidad_de_vistas}. Cache más largo: no hace falta que
// sea al segundo, solo sirve para ordenar "más buscados".
function getPopulares() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('populares_v1');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var sh = getSheet(CONFIG.TAB_VISTAS, ['Codigo', 'Nombre', 'Vendedor', 'Fecha']);
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var r = 1; r < vals.length; r++) {
    var codigo = String(vals[r][0] || '').trim();
    if (!codigo) continue;
    map[codigo] = (map[codigo] || 0) + 1;
  }
  cache.put('populares_v1', JSON.stringify(map), CONFIG.CACHE_SECONDS_POPULARES);
  return map;
}

// ====== RANKING (chiste interno: quién sube más fotos, quién más consulta) ======
// Devuelve {fotos: {vendedor: cantidad}, vistas: {vendedor: cantidad}}.
function getRanking() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('ranking_v2');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  // "Fotos Subidas" tiene una columna Url de mas antes de Vendedor (indice 3);
  // "Vistas" no la tiene (Vendedor va en el indice 2) — ojo si se agrega otra columna.
  var out = {
    fotos: contarPorVendedor(CONFIG.TAB_FOTOS, ['Codigo', 'Nombre', 'Url', 'Vendedor', 'Fecha'], 3),
    vistas: contarPorVendedor(CONFIG.TAB_VISTAS, ['Codigo', 'Nombre', 'Vendedor', 'Fecha'], 2)
  };
  cache.put('ranking_v2', JSON.stringify(out), CONFIG.CACHE_SECONDS_POPULARES);
  return out;
}

// Cuenta cuantas filas tiene cada vendedor. Salta filas viejas, de antes de
// que existiera la columna Vendedor, que en ese indice tienen otra cosa
// (una fecha con pinta de ISO 2026-01-01T...) en vez de un nombre.
var FECHA_ISO_RE = /^\d{4}-\d{2}-\d{2}T/;
function contarPorVendedor(tabName, encabezado, colVendedor) {
  var sh = getSheet(tabName, encabezado);
  var vals = sh.getDataRange().getValues();
  var map = {};
  for (var r = 1; r < vals.length; r++) {
    var vendedor = String(vals[r][colVendedor] || '').trim();
    if (!vendedor || FECHA_ISO_RE.test(vendedor)) continue;
    map[vendedor] = (map[vendedor] || 0) + 1;
  }
  return map;
}

// ====== NÚCLEO (persistencia entre pedidos) ======
// Cada ejecución de Apps Script arranca "en blanco" (no hay variables globales
// que sobrevivan entre pedidos): si CONFIG.FOLDER_ID/SHEET_ID están vacíos y
// creáramos la carpeta/planilla al vuelo cada vez, cada pedido generaría una
// carpeta y una planilla NUEVAS. PropertiesService sí persiste entre pedidos,
// así que el ID se crea una sola vez la primera vez y de ahí en más se reusa.
function getFolderId() {
  if (CONFIG.FOLDER_ID) return CONFIG.FOLDER_ID;
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('FOLDER_ID');
  if (id) return id;
  var carpeta = DriveApp.createFolder('Buscador Precios Pewen - Fotos subidas');
  props.setProperty('FOLDER_ID', carpeta.getId());
  Logger.log('Creé la carpeta "%s" (%s).', carpeta.getName(), carpeta.getId());
  return carpeta.getId();
}

function getSpreadsheet() {
  var sheetId = CONFIG.SHEET_ID || PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (sheetId) return SpreadsheetApp.openById(sheetId);
  var ss = SpreadsheetApp.create('Buscador Precios Pewen - Fotos subidas');
  PropertiesService.getScriptProperties().setProperty('SHEET_ID', ss.getId());
  Logger.log('Creé la planilla "%s" (%s).', ss.getName(), ss.getId());
  return ss;
}

function getSheet(tabName, encabezado) {
  var ss = getSpreadsheet();
  var sh = ss.getSheetByName(tabName);
  if (!sh) {
    // primera pestaña: reusar la que trae la planilla nueva en vez de crear otra al pedo
    var vacia = ss.getSheets().length === 1 && ss.getSheets()[0].getLastRow() === 0;
    sh = vacia ? ss.getSheets()[0] : ss.insertSheet();
    sh.setName(tabName);
    sh.appendRow(encabezado);
  }
  return sh;
}

// Diagnóstico: Ejecutar > verEnlaces y mirar el Registro — te da los links
// directos a la carpeta y a la planilla que está usando el script ahora mismo.
function verEnlaces() {
  Logger.log('Carpeta: https://drive.google.com/drive/folders/' + getFolderId());
  Logger.log('Planilla: https://docs.google.com/spreadsheets/d/' + getSpreadsheet().getId());
}

function nowIso() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone() || 'America/Argentina/Cordoba', "yyyy-MM-dd'T'HH:mm:ssXXX");
}

// Diagnóstico: Ejecutar > subirFotoDePrueba y mirar el Registro.
function subirFotoDePrueba() {
  var pixelPngBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=';
  var res = doPost({ postData: { contents: JSON.stringify({
    codigo: 'TEST', nombre: 'Prueba', imagenBase64: pixelPngBase64, mimeType: 'image/png', vendedor: 'test'
  }) } });
  Logger.log(res.getContent());
}
