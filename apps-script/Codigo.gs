/**
 * BUSCADOR DE PRECIOS PEWEN — Web App (Google Apps Script)
 * ------------------------------------------------------------
 * Recibe fotos que el equipo sube o saca desde el buscador (celu o PC),
 * las guarda en una carpeta de Drive y las anota en una planilla
 * (CODIGO -> URL). El buscador lee esa planilla al abrir y le pega la
 * foto a cada producto — sin pasar por vos, aparecen al toque.
 *
 * No hay moderación: lo que se sube se ve enseguida. Si alguna queda
 * mal, se borra la fila en la planilla o se pisa subiendo otra.
 * ------------------------------------------------------------
 */

var CONFIG = {
  // Opcional: ID de una carpeta de Drive ya existente para guardar las fotos.
  // Si lo dejás vacío, el script crea una carpeta la primera vez que alguien
  // sube una foto y de ahí en más siempre usa esa misma (queda guardada con
  // PropertiesService, no hace falta copiar nada a mano). Para ver cuál es,
  // correr Ejecutar > verEnlaces.
  FOLDER_ID: '',

  // Igual que arriba pero para la planilla índice CODIGO -> URL.
  SHEET_ID: '',
  TAB_NAME: 'Fotos Subidas',

  CACHE_SECONDS: 60
};

// ====== SUBIR UNA FOTO (desde el buscador) ======
function doPost(e) {
  var out;
  try {
    var body = JSON.parse(e.postData.contents);
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

    var url = 'https://drive.google.com/thumbnail?id=' + archivo.getId() + '&sz=w1000';
    anotarEnPlanilla(codigo, body.nombre || '', url, body.vendedor || '');

    out = { ok: true, url: url };
  } catch (err) {
    out = { ok: false, error: String(err && err.message || err) };
  }
  return ContentService
    .createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====== LEER LAS FOTOS SUBIDAS (el buscador las pide al abrir) ======
function doGet(e) {
  var out;
  try {
    if (e && e.parameter && e.parameter.fotos === '1') {
      out = { ok: true, fotos: getFotosSubidas() };
    } else {
      out = { ok: true, msg: 'Buscador de Precios Pewen — backend de fotos.' };
    }
  } catch (err) {
    out = { ok: false, error: String(err && err.message || err) };
  }
  return ContentService
    .createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

// ====== NÚCLEO ======
function anotarEnPlanilla(codigo, nombre, url, vendedor) {
  var sh = getSheet();
  sh.appendRow([codigo, nombre, url, vendedor, nowIso()]);
  CacheService.getScriptCache().remove('fotos_subidas_v1');
}

function getFotosSubidas() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get('fotos_subidas_v1');
  if (hit) { try { return JSON.parse(hit); } catch (e) {} }

  var sh = getSheet();
  var vals = sh.getDataRange().getValues();
  var map = {};
  // última fila de cada código gana: así una foto nueva pisa a la vieja.
  for (var r = 1; r < vals.length; r++) {
    var codigo = String(vals[r][0] || '').trim();
    var url = String(vals[r][2] || '').trim();
    if (codigo && url) map[codigo] = url;
  }
  cache.put('fotos_subidas_v1', JSON.stringify(map), CONFIG.CACHE_SECONDS);
  return map;
}

// Cada ejecución de Apps Script arranca "en blanco" (no hay variables globales
// que sobrevivan entre pedidos): si CONFIG.FOLDER_ID/SHEET_ID están vacíos y
// creáramos la carpeta/planilla al vuelo cada vez, cada subida generaría una
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

function getSheet() {
  var ss;
  var sheetId = CONFIG.SHEET_ID;
  if (!sheetId) sheetId = PropertiesService.getScriptProperties().getProperty('SHEET_ID');
  if (sheetId) {
    ss = SpreadsheetApp.openById(sheetId);
  } else {
    ss = SpreadsheetApp.create('Buscador Precios Pewen - Fotos subidas');
    PropertiesService.getScriptProperties().setProperty('SHEET_ID', ss.getId());
    Logger.log('Creé la planilla "%s" (%s).', ss.getName(), ss.getId());
  }
  var sh = ss.getSheetByName(CONFIG.TAB_NAME);
  if (!sh) {
    sh = ss.getSheets()[0];
    sh.setName(CONFIG.TAB_NAME);
    sh.appendRow(['Codigo', 'Nombre', 'Url', 'Vendedor', 'Fecha']);
  }
  return sh;
}

// Diagnóstico: Ejecutar > verEnlaces y mirar el Registro — te da los links
// directos a la carpeta y a la planilla que está usando el script ahora mismo.
function verEnlaces() {
  Logger.log('Carpeta: https://drive.google.com/drive/folders/' + getFolderId());
  Logger.log('Planilla: https://docs.google.com/spreadsheets/d/' + getSheet().getParent().getId());
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
