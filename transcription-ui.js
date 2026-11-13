/* Editable Unicode OCR review UI. OCR is never automatically accepted. */
(function () {
  'use strict';
  const $=id=>document.getElementById(id), T=window.CuneiTranscription;
  let last=null;
  function showError(message){ $('nabuStatus').textContent=message; }
  $('nabuImport').addEventListener('change', ev=>{
    const file=ev.target.files?.[0];ev.target.value='';if(!file)return;
    if(file.size>1024*1024)return showError('Archivo OCR demasiado grande (máximo 1 MB).');
    const reader=new FileReader();
    reader.onload=()=>{
      try {
        const t=T.canonical(JSON.parse(reader.result));
        const photo=$('imageStage');
        T.matchImage(t,Number(photo.dataset.imageWidth||0),Number(photo.dataset.imageHeight||0));
        const fileName=photo.dataset.filename;
        if(fileName && t.image_filename && fileName!==t.image_filename) throw Error('El OCR corresponde a '+t.image_filename+'; fotografía actual: '+fileName);
        last=t;
        $('nabuPreview').textContent=t.text;
        $('nabuPreview').hidden=false;
        $('nabuApply').disabled=false;
        $('nabuStatus').textContent=t.signs+' signos Unicode propuestos por '+t.source+'. Sin porcentaje de confianza. Revisá antes de copiar.';
      } catch(e){last=null;$('nabuPreview').hidden=true;$('nabuApply').disabled=true;showError('Importación rechazada: '+e.message);}
    };
    reader.onerror=()=>showError('No se pudo leer el archivo');
    reader.readAsText(file);
  });
  $('nabuApply').addEventListener('click',()=>{
    if(!last)return;
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
