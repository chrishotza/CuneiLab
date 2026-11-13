'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');

const script=fs.readFileSync(path.join(__dirname,'../transcription-ui.js'),'utf8');
const library=require('../transcription.js');
const glyphs='𒀭𒆠';

function instance({switchImage=false,enabled=true}={}) {
  const nodes={};
  const element=id=>nodes[id]||(nodes[id]={dataset:{},disabled:false,hidden:false,value:'',textContent:'',
    listeners:{},addEventListener(event,handler){this.listeners[event]=handler;},
    scrollIntoView(){},dispatchEvent(){}});
  const photo={url:'data:image/png;base64,AAAA',filename:'photo.png',width:20,height:30};
  element('imageStage').dataset={filename:'photo.png',imageWidth:'20',imageHeight:'30'};
  let uploads=0;
  async function fakeFetch(url,options){
    if(url==='/api/ocr-status')return {ok:true,json:async()=>({enabled})};
    if(url===photo.url)return {blob:async()=>new Blob(['png'],{type:'image/png'})};
    if(url==='/api/ocr'){
      assert.equal(options.headers['X-CuneiLab-Request'],'ocr-v1');
      assert.equal(options.headers['X-CuneiLab-Filename'],'photo.png');
      uploads++;
      if(switchImage)photo.url='data:image/png;base64,BBBB';
      return {ok:true,json:async()=>({format:'cuneilab-transcription',version:1,kind:'unicode-ocr',
        image:{width:20,height:30},image_filename:'photo.png',source:'test-local',model:'test',text:glyphs})};
    }
    throw Error(`Unexpected URL: ${url}`);
  }
  const dispatched=[];
  const sandbox={document:{getElementById:element,dispatchEvent(event){dispatched.push(event.type);}},window:{CuneiTranscription:library,CuneiLabPhotoForOCR:()=>({...photo})},
    location:{protocol:'http:'},fetch:fakeFetch,Blob,Event:class Event{constructor(type){this.type=type;}},console};
  vm.runInNewContext(script,sandbox);
  return {element,photo,uploads:()=>uploads,dispatched};
}
async function flush(){await new Promise(resolve=>setImmediate(resolve));}

test('OCR disabled until operator enables local model',async()=>{
  const c=instance({enabled:false});await flush();
  assert.equal(c.element('nabuRunLocal').disabled,true);
  assert.match(c.element('nabuStatus').textContent,/deshabilitado/);
});

test('user click requests local OCR and requires explicit approval to copy',async()=>{
  const c=instance();await flush();
  assert.equal(c.element('nabuRunLocal').disabled,false);
  await c.element('nabuRunLocal').listeners.click();
  assert.equal(c.uploads(),1);
  assert.equal(c.element('nabuPreview').textContent,glyphs);
  assert.equal(c.element('unicodeInput').value,'');
  assert.equal(c.element('nabuApply').disabled,false);
  c.element('nabuApply').listeners.click();
  assert.equal(c.element('unicodeInput').value,glyphs);
  assert.deepEqual(c.dispatched,['cuneilab:unicode-accepted']);
});

test('cannot copy result after changing photo',async()=>{
  const c=instance();await flush();
  await c.element('nabuRunLocal').listeners.click();
  c.photo.url='data:image/png;base64,SECOND';
  c.element('nabuApply').listeners.click();
  assert.equal(c.element('unicodeInput').value,'');
  assert.match(c.element('nabuStatus').textContent,/fotografía cambió/);
});

test('changed photo invalidates in-flight prediction',async()=>{
  const c=instance({switchImage:true});await flush();
  await c.element('nabuRunLocal').listeners.click();
  assert.equal(c.element('nabuApply').disabled,true);
  assert.equal(c.element('nabuPreview').hidden,true);
  assert.match(c.element('nabuStatus').textContent,/imagen cambió/);
});
