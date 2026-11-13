/* Corpus indexado por el servidor local. Los registros son referencias, NO traducciones. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const brief = (s, n) => (s && s.length > n ? s.slice(0, n) + '…' : (s || '—'));
  let items = [];
  let fragmentMode = false;
  function setStatus(message, ready = false) {
    $('corpusStatus').textContent = message;
    $('corpusStatus').classList.toggle('good', ready);
  }
  async function loadStatus() {
    try {
      const response = await fetch('/api/status', {cache:'no-store'});
      if (!response.ok) throw new Error('API');
      const data = await response.json();
      setStatus(data.ready ? `${data.count.toLocaleString('es-AR')} tablillas indexadas` : data.message, data.ready);
      if (data.ready) await loadFacets();
    } catch {
      setStatus('Modo sin servidor: ejecutá iniciar_cuneilab.bat para consultar el corpus.');
    }
  }
  async function loadFacets() {
    const res = await fetch('/api/facets', {cache: 'no-store'});
    if (!res.ok) throw new Error('No se pudieron cargar los filtros');
    const data = await res.json();
    for (const [name, target] of [['periods','corpusPeriod'], ['genres','corpusGenre']]) {
      const select = $(target);
      for (const row of data[name] || []) {
        const option = document.createElement('option');
        option.value = row.name;
        option.textContent = `${row.name} (${row.count})`;
        select.append(option);
      }
    }
  }
  function renderRows(similar = false) {
    $('corpusResults').innerHTML = items.map((item, i) => `
        <article class="corpus-card">
          <div class="corpus-card-header"><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(item.match_type)}</span></div>
          ${item.cdli_url ? `<a class="cdli-link" href="${escapeHtml(item.cdli_url)}" target="_blank" rel="noopener noreferrer">Abrir ficha de CDLI ↗</a>` : ''}
          <p class="corpus-meta">${escapeHtml(item.period || 'Período sin indicar')} · ${escapeHtml(item.genre || 'Género sin indicar')}</p>
          ${similar ? `<p class="corpus-meta"><b>Solapamiento textual:</b> ${item.shared_ngrams}/${item.query_ngrams} grupos de ${item.ngram_width} signos compartidos. No es probabilidad ni confianza del OCR.</p>` : ''}
          <div class="corpus-reading"><b>Signos:</b> <span class="cunei-small">${escapeHtml(brief(item.glyphs, 220))}</span></div>
          <div class="corpus-reading"><b>Transliteración documentada:</b> <code>${escapeHtml(brief(item.transliteration, 600))}</code></div>
          ${item.context?.match ? `<div class="corpus-kwic"><b>Contexto:</b> ${escapeHtml(item.context.before)}<mark>${escapeHtml(item.context.match)}</mark>${escapeHtml(item.context.after)}</div>` : ''}
          <button class="btn btn-secondary small" data-use-corpus="${i}" type="button">Usar transliteración como referencia</button>
        </article>`).join('');
  }

  async function runSearch() {
    const q = $('corpusQuery').value.trim();
    if (q.length < 2) { $('corpusResults').textContent = 'Ingresá al menos dos caracteres.'; return; }
    const mode = $('corpusField').value;
    $('corpusResults').textContent = 'Buscando en el corpus…';
    try {
      const params = new URLSearchParams({q, field:mode, period:$('corpusPeriod').value, genre:$('corpusGenre').value});
      const res = await fetch('/api/search?' + params, {cache:'no-store'});
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Error de búsqueda');
      if (!data.ready) throw new Error(data.message || 'Corpus no instalado');
      items = data.results;
      fragmentMode = false;
      if (!items.length) {
        $('corpusResults').innerHTML = '<p class="small-note">No aparecen coincidencias en las tablillas indexadas. Eso no significa que el signo no exista.</p>';
        return;
      }
      renderRows(false);
    } catch(e) {
      $('corpusResults').textContent = 'No se pudo consultar el corpus: ' + e.message;
    }
  }
  async function runSimilar() {
    const q = $('unicodeInput').value;
    const signs = [...q].filter(char => {
      const code = char.codePointAt(0);
      return code >= 0x12000 && code <= 0x1254F;
    });
    if (signs.length < 3) {
      $('corpusResults').textContent = 'Elegí al menos tres signos Unicode consecutivos para comparar.';
      return;
    }
    $('corpusResults').textContent = 'Comparando fragmentos de signos con SumTablets…';
    try {
      const params = new URLSearchParams({glyphs:q, period:$('corpusPeriod').value,
                                          genre:$('corpusGenre').value});
      const response = await fetch('/api/similar?' + params, {cache:'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo comparar');
      if (!data.ready) throw new Error(data.message || 'Importá el corpus primero');
      items = data.results;
      fragmentMode = true;
      if (!items.length) {
        $('corpusResults').textContent = 'No aparecen fragmentos compartidos en el corpus indexado. Eso no demuestra que la lectura sea errónea.';
        return;
      }
      renderRows(true);
      $('corpusStatus').textContent = `${items.length} candidatos documentados · no son traducciones automáticas`;
    } catch(error) {
      $('corpusResults').textContent = 'Comparación no disponible: ' + error.message;
    }
  }

  $('searchCorpus').addEventListener('click', runSearch);
  $('matchSimilar').addEventListener('click', runSimilar);
  document.addEventListener('cuneilab:unicode-accepted', runSimilar);
  $('corpusPeriod').addEventListener('change', () => { if ($('corpusQuery').value.trim()) runSearch(); });
  $('corpusGenre').addEventListener('change', () => { if ($('corpusQuery').value.trim()) runSearch(); });
  $('corpusQuery').addEventListener('keydown', ev => {if (ev.key === 'Enter') runSearch();});
  $('copyFromUnicode').addEventListener('click', () => {
    $('corpusField').value = 'glyphs';
    $('corpusQuery').value = $('unicodeInput').value.trim();
    runSearch();
  });
  $('copyFromATF').addEventListener('click', () => {
    $('corpusField').value = 'transliteration';
    // Remove numbered line prefixes, without erasing actual readings.
    $('corpusQuery').value = $('transliteration').value.replace(/^\s*\d+[.:]\s*/gm, '').trim();
    runSearch();
  });
  $('corpusResults').addEventListener('click', ev => {
    const btn = ev.target.closest('[data-use-corpus]');
    if (!btn) return;
    const i = Number(btn.dataset.useCorpus);
    const selected = items[i];
    if (!selected) return;
    const text = $('transliteration');
    if (text.value.trim() && text.value !== selected.transliteration &&
        !window.confirm('Esto reemplazará tu transliteración actual por el registro COMPLETO del corpus. ¿Continuar?')) return;
    if (fragmentMode && !window.confirm('Solo coinciden fragmentos de signos: el texto documentado puede pertenecer a otra tablilla. ¿Copiarlo igualmente como referencia?')) return;
    text.value = selected.transliteration;
    text.dispatchEvent(new Event('input', {bubbles:true}));
    $('projectTitle').value = `Comparación · ${selected.id}`;
    $('resultsPanel').scrollIntoView({behavior:'smooth', block:'start'});
    setStatus(`Referencia ${selected.id} insertada para revisión; sin traducción automática.`, true);
  });
  loadStatus();
})();
