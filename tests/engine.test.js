const assert=require('node:assert/strict');
const {test}=require('node:test');
const E=require('../engine.js');
test('reconoce palabras sumérias',()=>{
 let r=E.parseATF('1. lugal e2\n2. an ki');
 assert.equal(r.tokens.length,4);assert.equal(r.counts.known,4);assert.equal(r.coverage,100);
});
test('no inventa significados desconocidos',()=>{
 let r=E.parseATF('1. zavrajs lugal');
 assert.equal(r.counts.unknown,1);assert.match(r.draft,/sin resolver: zavrajs/);
});
test('separa líneas ATF y omite metadatos',()=>{
 let r=E.parseATF('&P123456\n#atf: lang sux\n@obverse\n1. lugal e2\n$ damaged\n2. ama');
 assert.equal(r.lines.length,2);assert.equal(r.tokens.length,3);
});
test('preserva duda y daño',()=>{
 let r=E.parseATF('1. [lugal] e2? x');assert.equal(r.counts.damage,3);
});
test('acepta acadio sin mezclar glosario sumerio',()=>{
 let r=E.parseATF('1. šarrum lugal','akk');assert.equal(r.counts.known,1);assert.equal(r.counts.unknown,1);
});
test('analiza sufijos con raíz conocida pero no los inventa',()=>{
 let r=E.parseATF('1. lugal-ak misterioso-ak');assert.equal(r.counts.morph,1);assert.equal(r.counts.unknown,1);
});
test('exporta un ATF mínimo',()=>{const str=E.exportATF({title:'Demo',language:'sux',transliteration:'lugal\ne2'});assert.match(str,/#atf: lang sux/);assert.match(str,/1\. lugal/);assert.match(str,/2\. e2/);});
test('identifica signos digitales y sus lecturas hipotéticas',()=>{const r=E.scanGlyphs('𒈗 𒂍',[{glyph:'𒈗',name:'LUGAL'},{glyph:'𒂍',name:'E2'}]);assert.equal(r.length,2);assert.equal(r[0].name,'LUGAL');assert.equal(r[0].reading,'lugal');});

test('propone lectura desde Unicode y marca signos desconocidos',()=>{
 const catalog=[{glyph:'𒈗',name:'LUGAL'},{glyph:'𒂍',name:'E2'},{glyph:'𒋯',name:'NO-CONOCIDO'}];
 const r=E.unicodeToATF('𒈗 𒂍 𒋯',catalog);
 assert.equal(r.signCount,3);assert.equal(r.warnings.length,1);assert.match(r.text,/lugal e2 \[x\]/);
});
