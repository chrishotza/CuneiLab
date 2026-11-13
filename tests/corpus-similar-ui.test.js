'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../corpus-ui.js'),'utf8');

function harness() {
  const nodes={}, listeners={};
  const element=id=>nodes[id]||(nodes[id]={value:'',textContent:'',innerHTML:'',classList:{toggle(){}},
    addEventListener(type,fn){this['on_'+type]=fn;},scrollIntoView(){},append(){}});
  const prompts=[];
  const document={getElementById:element, addEventListener(type,fn){listeners[type]=fn;},
    createElement(){return {value:'',textContent:''}}};
  element('unicodeInput').value='𒀭𒈗𒆠𒂍';
  element('corpusPeriod').value='';element('corpusGenre').value='';
  const requests=[];
  const fakeFetch=async url=>{
    requests.push(url);
    if(url==='/api/status')return {ok:true,json:async()=>({ready:false,message:'No corpus'})};
    if(String(url).startsWith('/api/similar?'))return {ok:true,json:async()=>({ready:true,results:[{
      id:'P000001',period:'Ur III',genre:'Literary',glyphs:'𒀭𒈗𒆠𒂍',
      transliteration:'an lugal ki e2',match_type:'fragmentos documentados',
      shared_ngrams:1,query_ngrams:1,ngram_width:4,
      evidence:{unicode:'𒀭𒈗𒆠𒂍',sign_count:4,query_segment:1,source_segment:1,query_sign_offset:0,source_sign_offset:0},
      cdli_url:'https://cdli.earth/artifacts/000001'}]})};
    throw Error('Unexpected URL '+url);
  };
  const sandboxWindow={confirm(msg){prompts.push(msg);return false;}};
  vm.runInNewContext(source,{document,window:sandboxWindow,fetch:fakeFetch,URLSearchParams,Event:class Event {constructor(type){this.type=type;}}});
  return {element,listeners,requests,prompts};
}

test('matching OCR glyphs uses documented corpus endpoint and cites overlap without confidence',async()=>{
  const h=harness();
  await h.element('matchSimilar').on_click();
  assert.ok(h.requests.some(url=>String(url).startsWith('/api/similar?')));
  const html=h.element('corpusResults').innerHTML;
  assert.match(html,/P000001/);
  assert.match(html,/1\/1 grupos de 4 signos compartidos/);
  assert.match(html,/No es probabilidad ni confianza del OCR/);
  assert.match(html,/an lugal ki e2/);
  assert.match(html,/Secuencia exacta documentada \(4 signos\)/);
  assert.match(html,/no se infiere una alineación fonética/);
});

test('accepting OCR dispatch triggers corpus comparison automatically',async()=>{
  const h=harness();
  await h.listeners['cuneilab:unicode-accepted']();
  assert.match(h.element('corpusResults').innerHTML,/P000001/);
});

test('fragment candidate cannot overwrite existing transcription without explicit review',async()=>{
  const h=harness();
  h.element('transliteration').value='my original reading';
  await h.element('matchSimilar').on_click();
  h.element('corpusResults').on_click({target:{closest:()=>({dataset:{useCorpus:'0'}})}});
  assert.equal(h.element('transliteration').value,'my original reading');
  assert.match(h.prompts[0],/reemplazará/);
});
