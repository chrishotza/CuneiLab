/* OCR Unicode output, not transliteration/translation. No external scripts. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CuneiTranscription = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const isSign = c => { const n=c.codePointAt(0); return n>=0x12000 && n<=0x1254F; };
  const count = text => Array.from(text).filter(isSign).length;
  function canonical(doc) {
    if (!doc || doc.format!=='cuneilab-transcription'||doc.version!==1||doc.kind!=='unicode-ocr') throw Error('Formato esperado: cuneilab-transcription v1 (unicode-ocr)');
    if (typeof doc.text!=='string'||!doc.text.length||doc.text.length>250000||doc.text.includes('\0')||!count(doc.text)) throw Error('OCR vacío o sin signos cuneiformes');
    if (typeof doc.source!=='string'||!doc.source.trim()||doc.source.length>180) throw Error('Fuente OCR inválida');
    if (typeof doc.model!=='string'||doc.model.length>180) throw Error('Modelo inválido');
    if (!doc.image||!Number.isInteger(doc.image.width)||!Number.isInteger(doc.image.height)||doc.image.width<1||doc.image.height<1||doc.image.width>30000||doc.image.height>30000) throw Error('Dimensiones inválidas');
    if (typeof doc.image_filename!=='string'||doc.image_filename.length>250||/[\\/]/.test(doc.image_filename)) throw Error('Nombre de imagen inválido');
    return {text:doc.text.replace(/\r\n/g,'\n'),source:doc.source,model:doc.model,image:doc.image,image_filename:doc.image_filename,signs:count(doc.text)};
  }
  function matchImage(d,w,h) { if (w && h && (w!==d.image.width||h!==d.image.height)) throw Error('Las dimensiones del OCR no corresponden a la fotografía cargada'); return d; }
  return Object.freeze({canonical, count, matchImage});
});
