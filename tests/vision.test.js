const {test}=require('node:test');
const assert=require('node:assert/strict');
const V=require('../vision.js');
const d={format:'cuneilab-detections',version:1,image:{width:100,height:80},source:'test',detections:[{bbox:[10,10,15,20],label:'AN',confidence:0.8}]};
test('valida esquema canónico',()=>assert.equal(V.canonical(d).detections[0].label,'AN'));
test('rechaza cajas fuera de imagen',()=>assert.throws(()=>V.canonical({...d,detections:[{bbox:[90,1,20,5],label:'X'}]}),/fuera/));
test('rechaza NaN y puntuaciones fuera de rango',()=>assert.throws(()=>V.canonical({...d,detections:[{bbox:[0,0,10,10],label:'x',confidence:1.4}]}),/Confianza/));
test('rechaza fotos de dimensiones diferentes',()=>assert.throws(()=>V.matchSize(V.canonical(d),90,80),/mide/));
test('COCO de una imagen usa clases, no inventa lecturas',()=>{
  const coco={images:[{id:7,file_name:'a.png',width:100,height:80}],categories:[{id:3,name:'LUGAL'}],annotations:[{image_id:7,category_id:3,bbox:[5,8,10,7]}]};
  const out=V.canonical(coco);assert.equal(out.detections[0].reading,'');assert.equal(out.detections[0].label,'LUGAL');
});
test('lectura no inferida queda ?',()=>assert.equal(V.toAnnotation(V.canonical(d).detections[0],100,80).reading,'?'));
test('orden de lectura visual por filas y columnas',()=>{
  const ds=[{bbox:[60,40,8,10]},{bbox:[50,10,8,10]},{bbox:[10,10,8,10]},{bbox:[10,40,8,10]}];
  assert.deepEqual(V.readingOrder(ds).map(d=>d.index),[2,1,3,0]);
});
