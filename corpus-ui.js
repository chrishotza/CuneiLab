/* Corpus indexado por el servidor local. Los registros son referencias, NO traducciones. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const brief = (s, n) => (s && s.length > n ? s.slice(0, n) + '…' : (s || '—'));
  let items = [];
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
      if (!items.length) {
        $('corpusResults').innerHTML = '<p class="small-note">No aparecen coincidencias en las tablillas indexadas. Eso no significa que el signo no exista.</p>';
        return;
      }
      $('corpusResults').innerHTML = items.map((item, i) => `
        <article class="corpus-card">
          <div class="corpus-card-header"><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(item.match_type)}</span></div>
          ${item.cdli_url ? `<a class="cdli-link" href="${escapeHtml(item.cdli_url)}" target="_blank" rel="noopener noreferrer">Abrir ficha de CDLI ↗</a>` : ''}
          <p class="corpus-meta">${escapeHtml(item.period || 'Período sin indicar')} · ${escapeHtml(item.genre || 'Género sin indicar')}</p>
          <div class="corpus-reading"><b>Signos:</b> <span class="cunei-small">${escapeHtml(brief(item.glyphs, 220))}</span></div>
          <div class="corpus-reading"><b>Transliteración documentada:</b> <code>${escapeHtml(brief(item.transliteration, 600))}</code></div>
          ${item.context?.match ? `<div class="corpus-kwic"><b>Contexto:</b> ${escapeHtml(item.context.before)}<mark>${escapeHtml(item.context.match)}</mark>${escapeHtml(item.context.after)}</div>` : ''}
          <button class="btn btn-secondary small" data-use-corpus="${i}" type="button">Usar transliteración como referencia</button>
        </article>`).join('');
    } catch(e) {
      $('corpusResults').textContent = 'No se pudo consultar el corpus: ' + e.message;
    }
  }
  $('searchCorpus').addEventListener('click', runSearch);
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
    text.value = selected.transliteration;
    text.dispatchEvent(new Event('input', {bubbles:true}));
    $('projectTitle').value = `Comparación · ${selected.id}`;
    $('resultsPanel').scrollIntoView({behavior:'smooth', block:'start'});
    setStatus(`Referencia ${selected.id} insertada para revisión; sin traducción automática.`, true);
  });
  loadStatus();
})();
