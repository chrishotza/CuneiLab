/* CuneiLab — funciones de análisis lingüístico. Sin servicios de IA ni resultados inventados. */
(function(root) {
  'use strict';
  // Glosario introductorio curado: sólo lecturas/acepciones comunes, NO diccionario exhaustivo.
  // El guion pertenece a la transliteración; no se divide automáticamente en vocablos.
  const LEXICON = {
    'a': ['agua', 'sustantivo'], 'a2': ['brazo; fuerza', 'sustantivo'],
    'ama': ['madre', 'sustantivo'], 'an': ['cielo; An (deidad)', 'sustantivo / nombre'],
    'an-na': ['del cielo; en el cielo (según el contexto)', 'forma dependiente'],
    'anše': ['asno', 'sustantivo'], 'anše-kur-ra': ['caballo', 'sustantivo'],
    'bar': ['exterior; lado; separar (según el contexto)', 'nombre / verbo'],
    'd': ['determinativo divino (no pronunciado)', 'determinativo'],
    'dingir': ['deidad; dios', 'sustantivo / determinativo'],
    'dub': ['tablilla', 'sustantivo'], 'dub-sar': ['escriba', 'sustantivo'],
    'dumu': ['hijo; descendiente', 'sustantivo'], 'dumu-munus': ['hija', 'sustantivo'],
    'e2': ['casa; templo', 'sustantivo'], 'e2-gal': ['palacio (lit. casa grande)', 'sustantivo'],
    'en': ['señor; alto sacerdote', 'sustantivo'], 'ensi2': ['gobernante; administrador de ciudad', 'título'],
    'en-ki': ['Enki (deidad)', 'nombre propio'], 'en-lil2': ['Enlil (deidad)', 'nombre propio'],
    'erin2': ['tropa; trabajadores', 'sustantivo'], 'gi': ['caña', 'sustantivo'],
    'giš': ['madera; árbol; determinativo de objetos de madera', 'sustantivo / determinativo'],
    'gu4': ['buey; toro', 'sustantivo'], 'gur': ['unidad de capacidad; volver (según el contexto)', 'nombre / verbo'],
    'igi': ['ojo; frente; presencia', 'sustantivo'], 'inanna': ['Inanna (deidad)', 'nombre propio'],
    'iti': ['mes', 'sustantivo'], 'ka': ['boca', 'sustantivo'],
    'ki': ['lugar; tierra', 'sustantivo'], 'ku3': ['puro; sagrado; plata (según lectura)', 'adjetivo / sustantivo'],
    'kug': ['plata; puro; sagrado', 'sustantivo / adjetivo'],
    'kur': ['montaña; tierra extranjera; inframundo', 'sustantivo'],
    'lugal': ['rey', 'sustantivo'], 'lugal-la': ['del rey (posible forma flexionada)', 'forma dependiente'],
    'lu2': ['persona; hombre', 'sustantivo'], 'ma2': ['barco', 'sustantivo'],
    'me': ['poderes/atributos divinos; ser (según el contexto)', 'nombre / verbo'],
    'mu': ['nombre; año', 'sustantivo'], 'munus': ['mujer', 'sustantivo'],
    'na4': ['piedra (también determinativo)', 'sustantivo / determinativo'],
    'nanna': ['Nanna (deidad lunar)', 'nombre propio'], 'nig2': ['cosa; propiedad', 'sustantivo'],
    'nin': ['señora; dama', 'sustantivo'], 'nin-gal': ['Ningal (deidad)', 'nombre propio'],
    'sag': ['cabeza; primero', 'sustantivo / adjetivo'],
    'sanga': ['administrador de templo', 'título'], 'še': ['cebada; grano', 'sustantivo'],
    'še3': ['hacia; para (morfema terminativo)', 'morfema'],
    'sila3': ['unidad de capacidad (sila)', 'medida'],
    'šagina': ['general; gobernador militar', 'título'],
    'šag4': ['corazón; interior', 'sustantivo'],
    'udu': ['oveja', 'sustantivo'], 'ugula': ['supervisor', 'título'],
    'ur': ['perro; ciudad de Ur (según el contexto)', 'sustantivo / nombre'],
    'urim2': ['Ur (topónimo)', 'nombre propio'],
    'uru': ['ciudad', 'sustantivo / determinativo'], 'utu': ['Utu (deidad solar); sol', 'nombre / sustantivo'],
    'zi': ['vida; aliento; correcto (según el contexto)', 'sustantivo / adjetivo'],
    'ĝeš': ['árbol; madera', 'sustantivo'], 'ĝeštin': ['vid; vino', 'sustantivo'],
    'ĝiri3': ['pie', 'sustantivo'], 'ĝuruš': ['trabajador masculino', 'sustantivo'],
    // algunas voces acadias solo como glosas iniciales, no análisis morfológico
    'šarrum': ['rey (acadio)', 'sustantivo acadio'],
    'šarru': ['rey (acadio)', 'sustantivo acadio'],
    'bītum': ['casa (acadio)', 'sustantivo acadio'],
    'bītu': ['casa (acadio)', 'sustantivo acadio'],
    'ilum': ['dios (acadio)', 'sustantivo acadio'],
    'ilu': ['dios (acadio)', 'sustantivo acadio'],
    'mārum': ['hijo (acadio)', 'sustantivo acadio'],
    'māru': ['hijo (acadio)', 'sustantivo acadio'],
    'ṭuppum': ['tablilla (acadio)', 'sustantivo acadio'],
    'ṭuppu': ['tablilla (acadio)', 'sustantivo acadio'],
    'mātum': ['país; tierra (acadio)', 'sustantivo acadio'],
    'mātu': ['país; tierra (acadio)', 'sustantivo acadio'],
    'awīlum': ['persona; hombre (acadio)', 'sustantivo acadio'],
    'awīlu': ['persona; hombre (acadio)', 'sustantivo acadio']
  };
  const MORPHEMES = {
    'ak': 'genitivo: de', 'ra': 'dativo: a / para', 'ta': 'ablativo: desde / de',
    'še3': 'terminativo: hacia / para', 'a': 'locativo: en / sobre (también otras funciones)',
    'e': 'ergativo / locativo, según el contexto', 'bi': 'su / ese (inanimado)',
    'ene': 'plural humano', 'gin7': 'comparativo: como', 'da': 'comitativo: con',
    'me': 'forma plural/copulativa (según contexto)'
  };
  // Algunos signos inequívocos para un primer ejemplo. Un signo puede tener MUCHOS valores.
  const SIGN_HINTS = {
    'AN': {reading: 'an / dingir', gloss: 'cielo; deidad'},
    'A': {reading: 'a', gloss: 'agua'},
    'E2': {reading: 'e2', gloss: 'casa; templo'},
    'LUGAL': {reading: 'lugal', gloss: 'rey'},
    'KI': {reading: 'ki', gloss: 'lugar; tierra'},
    'EN': {reading: 'en', gloss: 'señor'},
    'LU2': {reading: 'lu2', gloss: 'persona'},
    'URU': {reading: 'uru', gloss: 'ciudad'},
    'NIN': {reading: 'nin', gloss: 'señora'},
    'DUB': {reading: 'dub', gloss: 'tablilla'},
    'NAM': {reading: 'nam', gloss: 'condición; destino (según contexto)'},
    'MU': {reading: 'mu', gloss: 'nombre; año'},
    'U': {reading: 'u', gloss: 'signo U; múltiples valores'},
    'UD': {reading: 'ud / utu', gloss: 'día; sol (según lectura)'}
  };

  function canonical(s) {
    return String(s || '').trim().toLowerCase()
      .replace(/[₂]/g,'2').replace(/[₃]/g,'3').replace(/[₄]/g,'4')
      .replace(/[₅]/g,'5').replace(/[₆]/g,'6').replace(/[₇]/g,'7')
      .replace(/[₈]/g,'8').replace(/[₉]/g,'9').replace(/[₀]/g,'0')
      .replace(/š/g,'š').replace(/’/g,"'");
  }
  function stripMarkup(s) {
    return s.replace(/[\[\]⸢⸣!?*#<>]/g,'').replace(/[{}]/g,'').replace(/^\+/,'');
  }
  function getGloss(token, language) {
    const damaged = /[\[\]xX…?⸢⸣]/.test(token) || /\.{3}/.test(token);
    const key = canonical(stripMarkup(token)).replace(/^[^a-zĝšṣṭḫāēīū]+|[^a-z0-9ĝšṣṭḫāēīū]+$/g,'');
    if (!key) return {token, key, status:'damage', gloss:'Laguna, número o signo no legible', part:''};
    if (damaged) return {token, key, status:'damage', gloss:'Lectura dañada o incierta; no se propone traducción', part:''};
    let entry = LEXICON[key];
    if (entry && language === 'akk' && !entry[1].includes('acadio')) entry = null;
    if (entry && language === 'sux' && entry[1].includes('acadio')) entry = null;
    if (entry) return {token, key, status:'known', gloss:entry[0], part:entry[1]};
    // Reconocer sufijos solo cuando queda una raíz del glosario establecida.
    if (language !== 'akk') {
      for (const [suffix, meaning] of Object.entries(MORPHEMES).sort((a,b)=>b[0].length-a[0].length)) {
        if (key.endsWith('-'+suffix)) {
          const root = key.slice(0,-suffix.length-1);
          if (LEXICON[root] && !LEXICON[root][1].includes('acadio')) {
            return {token,key,status:'morph',gloss:LEXICON[root][0]+' + '+meaning,part:'análisis morfológico tentativo'};
          }
        }
      }
    }
    return {token,key,status:'unknown',gloss:'Sin coincidencia en el glosario inicial',part:''};
  }
  function isMetadata(line) {
    return /^\s*(?:&\S+|@[a-z]+|#(?:atf|project|atf:|note|lem)|\$\s)/i.test(line);
  }
  function parseATF(text, language='sux') {
    const lines = String(text||'').split(/\r?\n/);
    const result = [];
    for (let idx=0; idx<lines.length; idx++) {
      const raw=lines[idx];
      if (!raw.trim() || isMetadata(raw)) continue;
      const body=raw.replace(/^\s*\d+(?:['a-z]+)?(?:\.\d+)?[.:]\s*/, '').trim();
      if(!body) continue;
      const tokens=body.split(/\s+/).filter(Boolean).map(t=>getGloss(t,language));
      result.push({number: idx+1, raw, tokens});
    }
    const flat=result.flatMap(l=>l.tokens);
    const counts={known:0,morph:0,unknown:0,damage:0};
    flat.forEach(t=>counts[t.status]++);
    const draft=result.map(l=>l.tokens.map(t=>t.status==='known'||t.status==='morph' ? t.gloss.split(';')[0].split(' + ')[0] : '[sin resolver: '+t.token+']').join(' · ')).join('\n');
    return {lines:result, tokens:flat, counts, draft, coverage:flat.length ? Math.round(100*(counts.known+counts.morph)/flat.length) : 0};
  }
  function isCuneiform(s) { return /[\u{12000}-\u{1254F}]/u.test(String(s||'')); }
  function scanGlyphs(text,catalog) {
    const index = Object.fromEntries(catalog.map(x=>[x.glyph,x]));
    return Array.from(String(text||'')).filter(c=>isCuneiform(c)).map(c=> {
      const sign=index[c]; const hint=sign ? SIGN_HINTS[sign.name] : undefined;
      return {glyph:c, name:sign?.name||'DESCONOCIDO', reading:hint?.reading||'—', gloss:hint?.gloss||'Requiere consulta de lista de signos', status:hint?'hint':'unresolved'};
    });
  }
  function unicodeToATF(text,catalog) {
    const index=Object.fromEntries(catalog.map(s=>[s.glyph,s.name]));
    const warnings=[];
    const lines=String(text||'').split(/\r?\n/).map((line,lineNo)=>{
      const chunks=[];
      for(const char of Array.from(line)) {
        if(isCuneiform(char)) {
          const n=index[char];const h=n?SIGN_HINTS[n]:null;
          if(!h) {warnings.push({line:lineNo+1,glyph:char,name:n||'DESCONOCIDO'});chunks.push('[x]');}
          else chunks.push(h.reading.split(' / ')[0].split(' ')[0]);
        } else if(/\s/.test(char)) { if(chunks.length && chunks[chunks.length-1]!==' ') chunks.push(' '); }
      }
      const result=chunks.join(' ').replace(/\s+/g,' ').trim();
      return result?`${lineNo+1}. ${result}`:'';
    }).filter(Boolean);
    return {text:lines.join('\n'),warnings,signCount:Array.from(String(text||'')).filter(isCuneiform).length};
  }
  function exportATF({title,language,transliteration,id}) {
    const ident=(id||'X000001').trim().replace(/\s/g,'_');
    const safeTitle=(title||'Sin título').replace(/[\r\n]+/g,' ');
    const source=String(transliteration||'').trim();
    const lines=source.split(/\r?\n/).filter(x=>x.trim());
    const numbered=lines.map((l,i)=>/^\s*(\d+[.:]|&|@|#|\$)/.test(l)?l:(i+1)+'. '+l).join('\n');
    return `&${ident} = ${safeTitle}\n#atf: lang ${language}\n@tablet\n@obverse\n${numbered}\n`;
  }
  const api={LEXICON,MORPHEMES,SIGN_HINTS,canonical,stripMarkup,getGloss,parseATF,isCuneiform,scanGlyphs,unicodeToATF,exportATF};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  root.CuneiEngine=api;
})(typeof window !== 'undefined'?window:globalThis);
