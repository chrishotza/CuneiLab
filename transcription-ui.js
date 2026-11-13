/* Editable Unicode OCR review UI. OCR is never automatically accepted. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id), T=window.CuneiTranscription;
  let last=null, lastImageUrl=null;
  function showError(message){ $('nabuStatus').textContent=message; }
  function showDocument(raw) {
    const t=T.canonical(raw);
    const photo=$('imageStage');
    T.matchImage(t,Number(photo.dataset.imageWidth||0),Number(photo.dataset.imageHeight||0));
    const fileName=photo.dataset.filename;
    if(fileName && t.image_filename && fileName!==t.image_filename) throw Error('El OCR corresponde a '+t.image_filename+'; fotografía actual: '+fileName);
    last=t;lastImageUrl=window.CuneiLabPhotoForOCR?.().url||null;
    $('nabuPreview').textContent=t.text;
    $('nabuPreview').hidden=false;
    $('nabuApply').disabled=false;
    $('nabuStatus').textContent=t.signs+' signos propuestos por '+t.source+'. Sin confianza calibrada: revisá antes de copiar.';
  }
  async function refreshLocal() {
    const btn=$('nabuRunLocal');
    if (location.protocol==='file:') {showError('Editor offline: el OCR directo necesita el servidor local. Podés importar JSON.');return;}
    try {
      const response=await fetch('/api/ocr-status',{cache:'no-store'});
      if(!response.ok)throw Error('Servidor no compatible');
      const state=await response.json();
      btn.disabled=!state.enabled;
      if(!state.enabled)showError('OCR local deshabilitado; podés seguir anotando e importar JSON. Consultá el README para activarlo.');
      else showError('NabuOCR local habilitado. Cargá una foto y pulsá «Ejecutar OCR local». La primera carga del modelo puede tardar.');
    }catch(_){btn.disabled=true;showError('OCR local no disponible; el editor y la importación de JSON siguen funcionando.');}
  }
  $('nabuRunLocal').addEventListener('click',async ()=>{
    const btn=$('nabuRunLocal'), snapshot=window.CuneiLabPhotoForOCR?.();
    if(!snapshot?.url?.startsWith('data:image/') || !snapshot.width || !snapshot.height) return showError('Primero cargá una fotografía JPG, PNG o WebP.');
    if(snapshot.url.length>17_000_000)return showError('La imagen excede el máximo de 12 MB.');
    btn.disabled=true;
    last=null;lastImageUrl=null;$('nabuApply').disabled=true;$('nabuPreview').hidden=true;
    showError('Ejecutando OCR local; no cierres esta pestaña. La lectura aún no está confirmada.');
    try {
      const blob=await (await fetch(snapshot.url)).blob();
      if(blob.size>12*1024*1024)throw Error('Fotografía demasiado grande');
      const extension={'image/jpeg':'.jpg','image/png':'.png','image/webp':'.webp'}[blob.type];
      if(!extension)throw Error('Formato de fotografía incompatible');
      const filename=snapshot.filename||('tablilla'+extension);
      const response=await fetch('/api/ocr',{
        method:'POST',headers:{'Content-Type':blob.type,'X-CuneiLab-Request':'ocr-v1','X-CuneiLab-Filename':encodeURIComponent(filename)},
        body:blob,cache:'no-store'
      });
      const result=await response.json();
      if(!response.ok)throw Error(result.error||'Error de OCR local ('+response.status+')');
      const now=window.CuneiLabPhotoForOCR?.();
      if(!now || now.url!==snapshot.url)throw Error('La imagen cambió durante el OCR. Cargá nuevamente la fotografía original.');
      showDocument(result);
    }catch(error){showError('OCR no completado: '+error.message);}
    finally{btn.disabled=false;}
  });
  refreshLocal();
  $('nabuImport').addEventListener('change', ev=>{
    const file=ev.target.files?.[0];ev.target.value='';if(!file)return;
    if(file.size>1024*1024)return showError('Archivo OCR demasiado grande (máximo 1 MB).');
    const reader=new FileReader();
    reader.onload=()=>{
      try {
        showDocument(JSON.parse(reader.result));
      } catch(e){last=null;lastImageUrl=null;$('nabuPreview').hidden=true;$('nabuApply').disabled=true;showError('Importación rechazada: '+e.message);}
    };
    reader.onerror=()=>showError('No se pudo leer el archivo');
    reader.readAsText(file);
  });
  $('nabuApply').addEventListener('click',()=>{
    if(!last)return;
    const current=window.CuneiLabPhotoForOCR?.();
    if(!current?.url || current.url!==lastImageUrl){last=null;$('nabuApply').disabled=true;return showError('La fotografía cambió: descarté la predicción anterior.');}
    const field=$('unicodeInput');
    if(field.value.trim()&&!window.confirm('Ya hay signos en el editor. ¿Reemplazar con la predicción OCR?'))return;
    field.value=last.text;
    field.dataset.ocrSource=last.source;
    field.dataset.ocrModel=last.model;
    field.dispatchEvent(new Event('input',{bubbles:true}));
    $('nabuStatus').textContent='Signos copiados al editor para corrección. No constituyen una transliteración validada.';
    field.scrollIntoView({behavior:'smooth',block:'center'});
  });
})();
