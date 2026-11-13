/* CuneiLab — aplicación local, sin dependencias, ni claves API. */
(function () {
  'use strict';
  const E = window.CuneiEngine;
  const C = window.SIGN_CATALOG;
  const V = window.CuneiVision;
  const $ = id => document.getElementById(id);
  const state = { imageUrl:'', image:new Image(), imageFilename:'', predictions:[], visionSource:'', annotations:[], draftRect:null, mouseStart:null, result:null, lastSearch:'', title:'', language:'sux', transliteration:'', glyphs:'', contrast:110, brightness:100, gray:false };
  let toastTimer=null;
  const esc = value=>String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function toast(msg) { const t=$('toast');t.textContent=msg;t.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('visible'),3000); }
  function download(name, body, mime='text/plain;charset=utf-8') {
    const blob = new Blob([body], {type:mime}), link=document.createElement('a'), url=URL.createObjectURL(blob);
    link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function fileStem() { return ($('projectTitle').value || 'cuneilab').trim().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9_-]+/gi,'-').replace(/^-+|-+$/g,'').slice(0,70)||'cuneilab'; }
  function collect() {
    return {format:'cuneilab-project',version:1,createdAt:new Date().toISOString(),title:$('projectTitle').value,language:$('languageSelect').value,transliteration:$('transliteration').value,glyphs:$('unicodeInput').value,annotations:state.annotations,vision:{source:state.visionSource,detections:state.predictions,image:{width:state.image.naturalWidth||0,height:state.image.naturalHeight||0}},ocrSource:{source:$('unicodeInput').dataset.ocrSource||'',model:$('unicodeInput').dataset.ocrModel||''},filters:{contrast:Number($('contrast').value),brightness:Number($('brightness').value),grayscale:$('grayscale').checked},image:state.imageUrl||null};
  }
  function persist() { try { const v=collect(); delete v.image;localStorage.setItem('cuneilab-v1',JSON.stringify(v)); }catch(e){ /* persistencia opcional */ } }
  function restore() { try { const d=JSON.parse(localStorage.getItem('cuneilab-v1')||'null'); if(d?.format==='cuneilab-project') applyProject(d,false); }catch(e){} }
  function applyProject(d, showMessage=true) {
    if(d?.format!=='cuneilab-project' || d.version!==1) throw new Error('Formato de proyecto no reconocido (se requiere CuneiLab v1).');
    if(d.image && (!/^data:image\/(?:png|jpeg|webp);base64,/.test(d.image) || d.image.length>17000000)) throw new Error('Imagen incrustada inválida o demasiado grande.');
    $('projectTitle').value=String(d.title||'Nueva tablilla').slice(0,160);
    $('languageSelect').value=d.language==='akk'?'akk':'sux';
    $('transliteration').value=String(d.transliteration||'').slice(0,250000);
    $('unicodeInput').value=String(d.glyphs||'').slice(0,250000);
    $('unicodeInput').dataset.ocrSource=String(d.ocrSource?.source||'').slice(0,180);
    $('unicodeInput').dataset.ocrModel=String(d.ocrSource?.model||'').slice(0,180);
    const validRect=r=>r && [r.x,r.y,r.w,r.h].every(n=>typeof n==='number' && Number.isFinite(n) && n>=0 && n<=1);
    state.predictions=[];state.visionSource='';
    state.annotations=Array.isArray(d.annotations)?d.annotations.filter(validRect).slice(0,1000).map(r=>({x:r.x,y:r.y,w:r.w,h:r.h,reading:String(r.reading||'').slice(0,100),note:String(r.note||'').slice(0,500)})):[];
    $('contrast').value=Math.max(50,Math.min(250,Number(d.filters?.contrast)||110));
    $('brightness').value=Math.max(50,Math.min(180,Number(d.filters?.brightness)||100));
    $('grayscale').checked=!!d.filters?.grayscale;
    updateFilterLabels();renderAnnotations();
    if(d.image) loadImageUrl(d.image, () => {
      try { if(d.vision?.detections?.length){const v=V.canonical({format:'cuneilab-detections',version:1,source:d.vision.source||'proyecto',image:d.vision.image,detections:d.vision.detections});V.matchSize(v,state.image.naturalWidth,state.image.naturalHeight);state.predictions=v.detections;state.visionSource=v.source;} } catch(err){toast('Las predicciones guardadas no coinciden con la fotografía.');}
      renderDetections();
    }); else clearPhoto(false);
    renderDetections();
    analyze();persist();if(showMessage) toast('Proyecto importado.');
  }
  function clearPhoto(save=true) {
    state.imageUrl='';state.image=new Image();delete $('imageStage').dataset.filename;delete $('imageStage').dataset.imageWidth;delete $('imageStage').dataset.imageHeight;state.draftRect=null;state.predictions=[];state.visionSource='';renderDetections();
    $('imageEmpty').hidden=false;$('tabletCanvas').hidden=true;$('annotationForm').hidden=true;
    if(save)persist();
  }
  function loadImageUrl(src, done) {
    const img=new Image();
    img.onload=()=>{
      if(img.naturalWidth<1 || img.naturalHeight<1){toast('Imagen vacía.');return;}
      state.image=img;state.imageUrl=src;$('imageStage').dataset.imageWidth=String(img.naturalWidth);$('imageStage').dataset.imageHeight=String(img.naturalHeight);const cvs=$('tabletCanvas');const scale=Math.min(1,1600/Math.max(img.naturalWidth,img.naturalHeight));
      cvs.width=Math.max(1,Math.round(img.naturalWidth*scale));cvs.height=Math.max(1,Math.round(img.naturalHeight*scale));
      $('imageEmpty').hidden=true;cvs.hidden=false;renderImage();if(done)done();persist();
    };
    img.onerror=()=>toast('No se pudo abrir la imagen.');img.src=src;
  }
  function updateFilterLabels(){ $('contrastValue').textContent=$('contrast').value+'%';$('brightnessValue').textContent=$('brightness').value+'%'; }
  function renderImage() {
    if(!state.imageUrl || !state.image.complete || !state.image.naturalWidth)return;
    const cvs=$('tabletCanvas'),ctx=cvs.getContext('2d');const w=cvs.width,h=cvs.height;
    ctx.clearRect(0,0,w,h);
    ctx.filter=`contrast(${$('contrast').value}%) brightness(${$('brightness').value}%) ${$('grayscale').checked?'grayscale(1)':''}`;
    ctx.drawImage(state.image,0,0,w,h);ctx.filter='none';
    const threshold=Number($('visionThreshold').value)/100;
    state.predictions.filter(p=>p.confidence>=threshold).forEach(p=>{
      const [px,py,pw,ph]=p.bbox, sx=w/state.image.naturalWidth, sy=h/state.image.naturalHeight;
      ctx.strokeStyle='#dfa962';ctx.lineWidth=2;ctx.fillStyle='rgba(239,167,92,0.12)';
      ctx.fillRect(px*sx,py*sy,pw*sx,ph*sy);ctx.strokeRect(px*sx,py*sy,pw*sx,ph*sy);
    });
    const boxes=state.annotations.concat(state.draftRect?[{...state.draftRect,reading:'Nueva'}]:[]);
    boxes.forEach((r,i)=>{
      ctx.lineWidth=Math.max(2,Math.floor(w/600)*2);ctx.strokeStyle=i===state.annotations.length?'#e4c18a':'#a4d0a1';
      ctx.fillStyle='rgba(213,166,107,0.11)';ctx.fillRect(r.x*w,r.y*h,r.w*w,r.h*h);ctx.strokeRect(r.x*w,r.y*h,r.w*w,r.h*h);
      const label=String(r.reading||'?').slice(0,26),pad=6,fontSize=Math.max(13,Math.min(23,w/70));
      ctx.font=`bold ${fontSize}px Arial`;const tx=r.x*w,ty=Math.max(fontSize+8,r.y*h);const lw=Math.min(w-tx,ctx.measureText(label).width+2*pad);
      ctx.fillStyle='rgba(20,27,21,.88)';ctx.fillRect(tx,ty-fontSize-6,lw,fontSize+8);
      ctx.fillStyle='#f2dfb9';ctx.fillText(label,tx+pad,ty-5);
    });
  }
  function rectPoint(ev) {const r=$('tabletCanvas').getBoundingClientRect();return {x:Math.min(1,Math.max(0,(ev.clientX-r.left)/r.width)),y:Math.min(1,Math.max(0,(ev.clientY-r.top)/r.height))};}
  function rectFrom(a,b) {const x=Math.min(a.x,b.x),y=Math.min(a.y,b.y);return {x,y,w:Math.abs(a.x-b.x),h:Math.abs(a.y-b.y)};}
  function renderAnnotations() {
    $('annotationCount').textContent=state.annotations.length;
    $('annotationList').innerHTML=state.annotations.length?state.annotations.map((r,i)=>`<div class="annotation"><div class="num">${i+1}</div><div class="details"><strong>${esc(r.reading||'Sin lectura')}</strong><span>${esc(r.note||'Sin notas')}</span></div><button type="button" data-edit="${i}" title="Corregir lectura">Editar</button><button type="button" data-remove="${i}" title="Quitar región">Eliminar</button></div>`).join(''):'<p class="muted short">Todavía no hay anotaciones.</p>';
    renderImage();
  }
  function renderDetections() {
    const threshold=Number($('visionThreshold').value)/100;
    $('visionThresholdValue').textContent=Math.round(threshold*100)+'%';
    const ordered=V.readingOrder(state.predictions);
    const visible=ordered.filter(item=>state.predictions[item.index].confidence>=threshold);
    $('visionStatus').textContent=state.predictions.length?`${visible.length} / ${state.predictions.length} signos`:'Sin detecciones';
    $('visionResults').innerHTML=visible.length?visible.slice(0,300).map(item=>{
      const d=state.predictions[item.index];
      return `<div class="vision-detection"><div class="meta"><strong>${esc(d.label)} · ${Math.round(d.confidence*100)}%</strong><small>Línea visual ${item.line} · ${d.reading?`lectura sugerida: ${esc(d.reading)}`:'sin lectura fonética'}</small></div><button class="btn btn-secondary small" type="button" data-accept-detection="${item.index}">Agregar región</button></div>`;
    }).join('')+(visible.length>300?'<p class="vision-hint">Se muestran las primeras 300; podés cambiar el umbral.</p>':''):'<p class="vision-hint">Sin signos detectados. Cargá un JSON de un modelo real para ver los recuadros.</p>';
    renderImage();
  }
  function acceptDetection(index) {
    if(!state.imageUrl||!state.predictions[index])return;
    const d=state.predictions[index];
    const a=V.toAnnotation(d,state.image.naturalWidth,state.image.naturalHeight);
    state.annotations.push(a);state.predictions.splice(index,1);
    renderAnnotations();renderDetections();persist();
    toast('Región incorporada como lectura ?. Revisala antes de analizar.');
  }
  function renderCatalog(query='') {
    const q=query.trim().toUpperCase();
    const filtered=(q ? C.filter(s=>s.name.includes(q) || s.code.includes(q) || s.glyph===query.trim() || (E.SIGN_HINTS[s.name] && E.SIGN_HINTS[s.name].reading.toUpperCase().includes(q))) : C.filter(s=>E.SIGN_HINTS[s.name])).slice(0,72);
    $('signResults').innerHTML=filtered.length?filtered.map(s=>{
      const hint=E.SIGN_HINTS[s.name];
      return `<button type="button" class="sign-card" data-glyph="${esc(s.glyph)}" title="Agregar ${esc(s.name)} al texto Unicode"><span class="glyph">${esc(s.glyph)}</span><strong>${esc(s.name)}</strong><small>${esc(s.code)}</small>${hint?`<span class="hint">${esc(hint.reading)}</span>`:''}</button>`;
    }).join(''):'<p class="small-note">No aparecen signos con esa búsqueda. Probá el nombre Unicode o su código.</p>';
  }
  function renderAnalysis() {
    const result=state.result;
    $('statTokens').textContent=result.tokens.length;
    $('statKnown').textContent=result.counts.known+result.counts.morph;
    $('statUnknown').textContent=result.counts.unknown+result.counts.damage;
    $('analysisStatus').textContent=result.tokens.length? 'Glosario · '+result.coverage+'%': 'Preparado';
    $('resultIntro').textContent=result.tokens.length ? `Coincidencias con un glosario introductorio: ${result.coverage}%. No es un porcentaje de exactitud de la traducción.` : 'Pegá una transliteración para consultar sus palabras. No se infieren lecturas desconocidas.';
    $('resultRows').innerHTML=result.lines.map(line=>`<div class="line-label">LÍNEA ${line.number}</div>${line.tokens.map(t=>`<div class="token-line"><div><div class="token-name">${esc(t.token)}</div><div class="token-gloss">${esc(t.gloss)}</div></div><span class="token-status ${t.status}">${({known:'Glosario',morph:'Morfología',unknown:'Sin resolver',damage:'Dañado'})[t.status]}</span></div>`).join('')}`).join('');
    $('draftSection').hidden=!result.tokens.length;$('draftOutput').textContent=result.draft;
    const glyphs=E.scanGlyphs($('unicodeInput').value,C);
    $('glyphSection').hidden=glyphs.length===0;
    $('glyphResults').innerHTML=glyphs.map(g=>`<div class="glyph-item"><span>${esc(g.glyph)}</span><div><b>${esc(g.name)}</b><small>${esc(g.reading)}</small></div></div>`).join('');
  }
  function analyze() {state.result=E.parseATF($('transliteration').value,$('languageSelect').value);renderAnalysis();persist();}
  function appendAnnotations() {
    if(!state.annotations.length){toast('Primero marcá al menos una región.');return;}
    // Orden aproximado para una sola columna: posiciones verticales, luego horizontales.
    const ordered=state.annotations.slice().sort((a,b)=>Math.abs(a.y-b.y)<0.035 ? a.x-b.x : a.y-b.y);
    const text=ordered.map(a=>a.reading.trim()||'[x]').join(' ');
    const prev=$('transliteration').value.trim();
    $('transliteration').value=(prev?prev+'\n':'')+(prev?''+(prev.split('\n').length+1)+'. ':'1. ')+text;
    analyze();toast('Se agregaron las lecturas anotadas como una línea editable.');
  }
  function exportReport() {
    const d=collect(),r=E.parseATF(d.transliteration,d.language),g=E.scanGlyphs(d.glyphs,C);
    const s=[`CUNEILAB · ${d.title}`,`Idioma declarado: ${d.language==='sux'?'sumerio':'acadio'}`,'','TRANSITERACIÓN',d.transliteration||'(vacía)','','GLOSAS POR UNIDAD'];
    r.lines.forEach(l=>{s.push(`\nLínea ${l.number}: ${l.raw}`);l.tokens.forEach(t=>s.push(`- ${t.token} [${t.status}]: ${t.gloss}`));});
    s.push('','GLOSA LITERAL (no es traducción completa)',r.draft||'(sin análisis)','',`Cobertura del glosario: ${r.coverage}% (no mide exactitud)`,'','SIGNOS UNICODE');
    g.forEach(t=>s.push(`${t.glyph} ${t.name}: ${t.reading}`));
    s.push('','REGIONES DE LA FOTO');d.annotations.forEach((a,i)=>s.push(`${i+1}. ${a.reading}: ${a.note} (${Math.round(a.x*100)}%, ${Math.round(a.y*100)}%)`));
    s.push('','Documento generado por CuneiLab v0.1. Las lecturas y glosas requieren comprobación filológica.');
    download(fileStem()+'-informe.txt',s.join('\n'));
  }
  $('signCount').textContent=C.length.toLocaleString('es-AR');
  $('imageInput').addEventListener('change',ev=>{
    const file=ev.target.files?.[0];ev.target.value='';if(!file)return;
    if(!['image/jpeg','image/png','image/webp'].includes(file.type))return toast('Usá JPG, PNG o WebP.');
    if(file.size>12*1024*1024)return toast('La fotografía debe ocupar como máximo 12 MB.');
    const reader=new FileReader();reader.onload=()=>{state.annotations=[];state.predictions=[];state.visionSource='';state.imageFilename=file.name;$('imageStage').dataset.filename=file.name;loadImageUrl(reader.result,renderDetections);renderAnnotations();};reader.onerror=()=>toast('No se pudo leer la fotografía.');reader.readAsDataURL(file);
  });
  $('clearImage').addEventListener('click',()=>{clearPhoto();state.annotations=[];renderAnnotations();toast('Imagen eliminada del proyecto actual.');});
  ['contrast','brightness','grayscale'].forEach(id=>$(id).addEventListener('input',()=>{updateFilterLabels();renderImage();persist();}));
  const cvs=$('tabletCanvas');
  cvs.addEventListener('pointerdown',ev=>{if(!state.imageUrl)return;ev.preventDefault();state.mouseStart=rectPoint(ev);cvs.setPointerCapture(ev.pointerId);});
  cvs.addEventListener('pointermove',ev=>{if(!state.mouseStart)return;state.draftRect=rectFrom(state.mouseStart,rectPoint(ev));renderImage();});
  cvs.addEventListener('pointerup',ev=>{if(!state.mouseStart)return;const rect=rectFrom(state.mouseStart,rectPoint(ev));state.mouseStart=null;if(rect.w<.009||rect.h<.009){state.draftRect=null;renderImage();return;}
    state.draftRect=rect;$('annotationReading').value='';$('annotationNote').value='';$('annotationForm').hidden=false;$('annotationReading').focus();renderImage();});
  cvs.addEventListener('pointercancel',()=>{state.mouseStart=null;state.draftRect=null;renderImage();});
  $('cancelAnnotation').addEventListener('click',()=>{state.draftRect=null;$('annotationForm').hidden=true;renderImage();});
  $('saveAnnotation').addEventListener('click',()=>{
    const read=$('annotationReading').value.trim();if(!read)return toast('Ingresá una lectura tentativa o ? si es ilegible.');
    if(!state.draftRect)return;
    state.annotations.push({...state.draftRect,reading:read.slice(0,100),note:$('annotationNote').value.trim().slice(0,500)});
    state.draftRect=null;$('annotationForm').hidden=true;renderAnnotations();persist();toast('Región guardada.');
  });
  $('annotationList').addEventListener('click',ev=>{
    const edit=ev.target.closest('[data-edit]');
    if(edit){const i=Number(edit.dataset.edit),a=state.annotations[i];if(!a)return;
      const answer=window.prompt('Corregí la lectura a partir de la fotografía. Usá ? si es incierta:',a.reading);
      if(answer===null)return;const reading=answer.trim().slice(0,100);
      if(!reading)return toast('La lectura no puede estar vacía; usá ? si es desconocida.');
      a.reading=reading;renderAnnotations();persist();toast('Lectura corregida manualmente.');return;}
    const remove=ev.target.closest('[data-remove]');if(!remove)return;
    state.annotations.splice(Number(remove.dataset.remove),1);renderAnnotations();persist();
  });
  $('visionThreshold').addEventListener('input',renderDetections);
  $('predictionInput').addEventListener('change',ev=>{
    const file=ev.target.files?.[0];ev.target.value='';if(!file)return;
    if(!state.imageUrl||!state.image.naturalWidth)return toast('Primero cargá la fotografía correspondiente.');
    if(file.size>2*1024*1024)return toast('Archivo de detecciones demasiado grande (máx. 2 MB).');
    const reader=new FileReader();reader.onload=()=>{
      try {const data=V.matchSize(V.canonical(JSON.parse(reader.result),state.imageFilename),state.image.naturalWidth,state.image.naturalHeight);
        state.predictions=data.detections;state.visionSource=data.source;renderDetections();persist();toast(`${data.detections.length} detecciones importadas para revisión.`);
      } catch(err){toast('No se pudo importar OCR: '+err.message);}
    };reader.onerror=()=>toast('Error al leer detecciones.');reader.readAsText(file);
  });
  $('visionResults').addEventListener('click',ev=>{
    const button=ev.target.closest('[data-accept-detection]');if(button)acceptDetection(Number(button.dataset.acceptDetection));
  });
  $('acceptVisibleDetections').addEventListener('click',()=>{
    if(!state.imageUrl)return toast('Primero cargá la fotografía.');
    const threshold=Number($('visionThreshold').value)/100;
    const indices=V.readingOrder(state.predictions).filter(i=>state.predictions[i.index].confidence>=threshold).map(i=>i.index);
    if(!indices.length)return toast('No hay detecciones visibles.');
    indices.forEach(i=>state.annotations.push(V.toAnnotation(state.predictions[i],state.image.naturalWidth,state.image.naturalHeight)));
    const accepted=new Set(indices);state.predictions=state.predictions.filter((_,i)=>!accepted.has(i));
    renderAnnotations();renderDetections();persist();toast(`${indices.length} regiones agregadas sin lectura confirmada.`);
  });
  $('clearDetections').addEventListener('click',()=>{state.predictions=[];state.visionSource='';renderDetections();persist();});
  $('signSearch').addEventListener('input',ev=>renderCatalog(ev.target.value));
  $('clearSearch').addEventListener('click',()=>{$('signSearch').value='';renderCatalog();});
  $('signResults').addEventListener('click',ev=>{const b=ev.target.closest('[data-glyph]');if(!b)return;const fld=$('unicodeInput');fld.value+=(fld.value&&!/\s$/.test(fld.value)?' ':'')+b.dataset.glyph;analyze();toast(`Signo ${C.find(s=>s.glyph===b.dataset.glyph)?.name||''} agregado.`);});
  $('sampleButton').addEventListener('click',()=>{$('projectTitle').value='Ejemplo didáctico — no es una tablilla real';$('languageSelect').value='sux';$('transliteration').value='1. lugal e2\n2. an ki';$('unicodeInput').value='𒈗 𒂍\n𒀭 𒆠';analyze();toast('Ejemplo didáctico cargado.');});
  $('appendAnnotations').addEventListener('click',appendAnnotations);
  $('suggestReadings').addEventListener('click',()=>{
    const r=E.unicodeToATF($('unicodeInput').value,C);
    if(!r.signCount)return toast('Primero pegá o seleccioná signos cuneiformes.');
    const existing=$('transliteration').value.trim();
    $('transliteration').value=existing?existing+'\n'+r.text:r.text;
    analyze();
    toast(`Propuesta agregada · ${r.warnings.length} signo(s) sin lectura. Revisá todas las lecturas.`);
  });
  $('analyzeButton').addEventListener('click',()=>{analyze();$('resultsPanel').scrollIntoView({behavior:'smooth',block:'start'});toast('Análisis del glosario actualizado.');});
  ['projectTitle','languageSelect','transliteration','unicodeInput'].forEach(id=>$(id).addEventListener('input',()=>{analyze();}));
  $('btnExport').addEventListener('click',()=>{const d=collect();const serial=JSON.stringify(d,null,2);if(serial.length>18000000)return toast('El proyecto supera el tamaño permitido; usá una imagen más pequeña.');download(fileStem()+'.cuneilab.json',serial,'application/json;charset=utf-8');toast('Proyecto exportado.');});
  $('btnImport').addEventListener('click',()=>$('projectFile').click());
  $('projectFile').addEventListener('change',ev=>{const file=ev.target.files?.[0];ev.target.value='';if(!file)return;if(file.size>18*1024*1024)return toast('Proyecto demasiado grande.');const reader=new FileReader();reader.onload=()=>{try{applyProject(JSON.parse(reader.result));}catch(e){toast('No se pudo importar: '+e.message);}};reader.readAsText(file);});
  $('exportTxt').addEventListener('click',exportReport);
  $('exportAtf').addEventListener('click',()=>{download(fileStem()+'.atf',E.exportATF({title:$('projectTitle').value,language:$('languageSelect').value,transliteration:$('transliteration').value}));toast('ATF simplificado exportado.');});
  renderCatalog();restore();renderDetections();analyze();
})();
