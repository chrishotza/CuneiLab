/* Intercambio de detecciones visuales: signos y coordenadas, NO lecturas lingüísticas. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.CuneiVision = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  function canonical(doc, filename) {
    if (doc && Array.isArray(doc.images) && Array.isArray(doc.annotations) && Array.isArray(doc.categories)) {
      const images = filename ? doc.images.filter(im => String(im.file_name || '').split(/[\\/]/).pop() === filename) : doc.images;
      if (images.length !== 1) throw new Error('El archivo COCO debe referirse a una sola imagen o coincidir con el nombre de la foto.');
      const im = images[0], names = new Map(doc.categories.map(c => [c.id, c.name]));
      doc = {format:'cuneilab-detections',version:1,image:{width:im.width,height:im.height},source:'COCO (clases sin lectura)',
        detections:doc.annotations.filter(a => a.image_id === im.id).map(a => ({bbox:a.bbox,label:names.get(a.category_id),confidence:a.score ?? 1,reading:''}))};
    }
    if (!doc || doc.format !== 'cuneilab-detections' || doc.version !== 1) throw new Error('Formato de detecciones desconocido.');
    const {width:w,height:h} = doc.image || {};
    if (!finite(w) || !finite(h) || w <= 0 || h <= 0 || w > 30000 || h > 30000) throw new Error('Dimensiones de imagen inválidas.');
    if (!Array.isArray(doc.detections) || doc.detections.length > 5000) throw new Error('Máximo 5000 detecciones por archivo.');
    const detections = doc.detections.map((d,i) => {
      if (!d || !Array.isArray(d.bbox) || d.bbox.length !== 4 || !d.bbox.every(finite)) throw new Error('bbox inválido en detección '+(i+1));
      const [x,y,bw,bh]=d.bbox;
      if (!(x>=0 && y>=0 && bw>0 && bh>0 && x+bw <= w+0.001 && y+bh<=h+0.001)) throw new Error('Caja fuera de imagen '+(i+1));
      if (typeof d.label !== 'string' || !d.label.trim() || d.label.length>120) throw new Error('Clase de signo inválida '+(i+1));
      const confidence = d.confidence ?? 1;
      if (!finite(confidence) || confidence < 0 || confidence>1) throw new Error('Confianza inválida '+(i+1));
      if (d.reading != null && (typeof d.reading !== 'string' || d.reading.length > 100)) throw new Error('Lectura inválida');
      return {bbox:[x,y,bw,bh],label:d.label.trim(),confidence,reading:d.reading||''};
    });
    return {format:'cuneilab-detections',version:1,image:{width:w,height:h},source:String(doc.source||'origen no indicado').slice(0,180),detections};
  }
  function matchSize(doc, imageWidth, imageHeight) {
    if (doc.image.width !== imageWidth || doc.image.height !== imageHeight) throw new Error('La imagen del modelo mide '+doc.image.width+'×'+doc.image.height+' px, pero la fotografía cargada mide '+imageWidth+'×'+imageHeight+' px.');
    return doc;
  }
  function readingOrder(detections) {
    // Agrupar por distancia vertical relativa a la altura mediana de la clase detectada.
    if (!detections.length) return [];
    const ranked = detections.map((d,index)=>({index, ...d, x:d.bbox[0]+d.bbox[2]/2, y:d.bbox[1]+d.bbox[3]/2, height:d.bbox[3]})).sort((a,b)=>a.y-b.y||a.x-b.x);
    const heights=ranked.map(d=>d.height).sort((a,b)=>a-b);
    const tolerance=Math.max(2,heights[Math.floor(heights.length/2)]*0.55);
    const lines=[];
    ranked.forEach(det=>{
      let line=lines.find(row=>Math.abs(row.center-det.y) <= tolerance);
      if(!line){line={center:det.y,items:[]};lines.push(line);}
      line.items.push(det);line.center=line.items.reduce((s,d)=>s+d.y,0)/line.items.length;
    });
    lines.sort((a,b)=>a.center-b.center);
    return lines.flatMap((line,lineIndex)=>line.items.sort((a,b)=>a.x-b.x).map(det=>({index:det.index,line:lineIndex+1})));
  }
  function toAnnotation(det, imageWidth, imageHeight) {
    const [x,y,w,h]=det.bbox;
    return {x:x/imageWidth,y:y/imageHeight,w:w/imageWidth,h:h/imageHeight,
      reading:det.reading.trim() || '?', note:`Detección IA sin lectura confirmada · clase ${det.label} · confianza ${(det.confidence*100).toFixed(1)}%`};
  }
  return Object.freeze({canonical,matchSize,readingOrder,toAnnotation});
});
