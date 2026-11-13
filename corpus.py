"""CuneiLab corpus: import and retrieval of *documented* transliterations.

No photo-OCR nor synthetic translation. Depends only on Python stdlib.
"""
from __future__ import annotations
import csv
from contextlib import contextmanager
import re
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / 'data' / 'sumtablets.sqlite3'
SOURCE = 'SumTablets (Simmons, Diehl Martinez & Jurafsky), CC BY 4.0'
FIELDS = {'glyphs': 'glyph_norm', 'transliteration': 'translit_norm', 'id': 'id'}


def normalize(text: str, field: str) -> str:
    text = (text or '').strip()
    if field == 'glyphs':
        # Unicode cuneiform streams can be spaced for human readability.
        return re.sub(r'\s+', '', text)
    if field == 'transliteration':
        return re.sub(r'\s+', ' ', text).casefold()
    if field == 'id':
        return text.upper()
    raise ValueError('Campo no permitido')


@contextmanager
def _connect(db: Path):
    con = sqlite3.connect(str(db), timeout=20)
    con.row_factory = sqlite3.Row
    try:
        with con:
            yield con
    finally:
        con.close()


def _create_schema(con: sqlite3.Connection) -> None:
    con.executescript('''
        CREATE TABLE IF NOT EXISTS tablets (
            id TEXT PRIMARY KEY,
            period TEXT NOT NULL DEFAULT '',
            genre TEXT NOT NULL DEFAULT '',
            glyphs TEXT NOT NULL DEFAULT '',
            glyph_names TEXT NOT NULL DEFAULT '',
            transliteration TEXT NOT NULL DEFAULT '',
            glyph_norm TEXT NOT NULL DEFAULT '',
            translit_norm TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tablets_period ON tablets(period);
        CREATE INDEX IF NOT EXISTS idx_tablets_genre ON tablets(genre);
        CREATE INDEX IF NOT EXISTS idx_tablets_glyph_norm ON tablets(glyph_norm);
        CREATE INDEX IF NOT EXISTS idx_tablets_translit_norm ON tablets(translit_norm);
    ''')


def import_csv(csv_path: Path | str, db_path: Path | str = DEFAULT_DB, *, limit: int | None = None) -> dict:
    """Stream a SumTablets CSV into SQLite. Idempotent for matching IDs.

    'Train' is recommended for the retrieval index: reserve validation/test for evaluation.
    """
    csv_path, db_path = Path(csv_path), Path(db_path)
    if limit is not None and limit < 0:
        raise ValueError('limit no puede ser negativo')
    db_path.parent.mkdir(parents=True, exist_ok=True)
    inserted = scanned = 0
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f, _connect(db_path) as con:
        reader = csv.DictReader(f)
        required = {'id', 'glyphs', 'transliteration'}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('CSV inválido: faltan columnas ' + ', '.join(sorted(required - set(reader.fieldnames or []))))
        _create_schema(con)
        for row in reader:
            if limit is not None and scanned >= limit:
                break
            scanned += 1
            identifier = (row.get('id') or '').strip()
            glyphs = (row.get('glyphs') or '').strip()
            translit = (row.get('transliteration') or '').strip()
            if not identifier or not (glyphs or translit):
                continue
            result = con.execute('''
                INSERT OR IGNORE INTO tablets
                (id,period,genre,glyphs,glyph_names,transliteration,glyph_norm,translit_norm,source)
                VALUES (?,?,?,?,?,?,?,?,?)
            ''', (identifier, (row.get('period') or '').strip(), (row.get('genre') or '').strip(),
                  glyphs, (row.get('glyph_names') or '').strip(), translit,
                  normalize(glyphs,'glyphs'), normalize(translit,'transliteration'), SOURCE))
            inserted += result.rowcount
    return {'rows_scanned': scanned, 'rows_added': inserted, 'database': str(db_path)}


def status(db_path: Path | str = DEFAULT_DB) -> dict:
    path = Path(db_path)
    if not path.exists():
        return {'ready': False, 'count': 0, 'message': 'Corpus no instalado: importá train.csv con scripts/import_corpus.py'}
    try:
        with _connect(path) as con:
            count = con.execute('SELECT COUNT(*) FROM tablets').fetchone()[0]
            return {'ready': count > 0, 'count': count, 'source': SOURCE,
                    'message': 'Corpus indexado' if count else 'Corpus vacío: importá train.csv'}
    except sqlite3.Error:
        return {'ready': False, 'count': 0, 'message': 'La base de datos no está inicializada'}


def _escape_like(s: str) -> str:
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def facets(db_path: Path | str = DEFAULT_DB) -> dict:
    """Return observed periods and genres, not inferred labels."""
    path = Path(db_path)
    if not status(path)['ready']:
        return {'ready': False, 'periods': [], 'genres': []}
    with _connect(path) as con:
        groups = {}
        for key in ('period', 'genre'):
            groups[key] = [{'name': row[0], 'count': row[1]} for row in con.execute(
                f"SELECT {key}, COUNT(*) FROM tablets WHERE {key} != '' GROUP BY {key} ORDER BY COUNT(*) DESC, {key}")]
    return {'ready': True, 'periods': groups['period'], 'genres': groups['genre']}


def cdli_url(identifier: str) -> str | None:
    """Only physical CDLI P numbers map to /artifacts/{digits}."""
    match = re.fullmatch(r'P([0-9]{6})', identifier or '')
    return f'https://cdli.earth/artifacts/{match.group(1)}' if match else None


def make_context(text: str, query: str, *, radius: int = 85) -> dict:
    """Short KWIC view; match spans are informational, not a linguistic alignment."""
    haystack = text.casefold()
    needle = query.casefold()
    index = haystack.find(needle) if needle else -1
    if index < 0:
        return {'before': text[: radius * 2], 'match': '', 'after': '', 'truncated': len(text) > radius * 2}
    left = max(0, index - radius)
    right = min(len(text), index + len(needle) + radius)
    return {
        'before': ('…' if left else '') + text[left:index],
        'match': text[index:index + len(needle)],
        'after': text[index + len(needle):right] + ('…' if right < len(text) else ''),
        'truncated': left > 0 or right < len(text),
    }


def search(query: str, field: str = 'transliteration', *, db_path: Path | str = DEFAULT_DB,
           limit: int = 15, period: str = '', genre: str = '') -> dict:
    """Return attested corpus rows; ranked exact, prefix and substring.

    A match is NOT equivalent to a palaeographic reading or translation.
    """
    if field not in FIELDS:
        raise ValueError('Campo no permitido')
    if not isinstance(query, str) or len(query) > 1500:
        raise ValueError('Consulta demasiado larga')
    clean = normalize(query, field)
    if len(clean) < 2:
        raise ValueError('Ingresá al menos dos caracteres')
    if not isinstance(limit, int) or limit < 1 or limit > 50:
        raise ValueError('Límite fuera del rango 1–50')
    if not isinstance(period, str) or len(period) > 100 or not isinstance(genre, str) or len(genre) > 100:
        raise ValueError('Filtro inválido')
    if field == 'id' and not re.fullmatch(r'[PQ][0-9]{6}', clean):
        raise ValueError('Identificador esperado: P123456 o Q123456')
    col = FIELDS[field]  # allowlist, not user input interpolated freely
    needle = _escape_like(clean)
    sql = f'''
        SELECT id, period, genre, glyphs, transliteration, source,
          CASE WHEN {col} = ? THEN 'exacta'
               WHEN {col} LIKE ? ESCAPE '\\' THEN 'prefijo'
               ELSE 'parcial' END AS match_type
        FROM tablets
        WHERE {col} LIKE ? ESCAPE '\\'
          AND (? = '' OR period = ?)
          AND (? = '' OR genre = ?)
        ORDER BY CASE WHEN {col} = ? THEN 0
                      WHEN {col} LIKE ? ESCAPE '\\' THEN 1
                      ELSE 2 END,
                 LENGTH({col}), id
        LIMIT ?
    '''
    params = (clean, needle + '%', '%' + needle + '%', period, period, genre, genre, clean, needle + '%', limit)
    path = Path(db_path)
    if not status(path)['ready']:
        return {'ready': False, 'query': query, 'results': [], 'message': 'Primero importá el corpus SumTablets.'}
    with _connect(path) as con:
        rows = [dict(r) for r in con.execute(sql, params)]
    for row in rows:
        row['cdli_url'] = cdli_url(row['id'])
        if field == 'transliteration':
            row['context'] = make_context(row['transliteration'], clean)
    return {'ready': True, 'query': query, 'field': field, 'period': period, 'genre': genre, 'results': rows,
            'message': 'Coincidencias documentadas, no traducciones automáticas.'}


def _sign_segments(text: str) -> list[str]:
    """Conservative exact-sign runs; never bridge faces, lines or damage.

    Only ordinary spaces/tabs are ignored between known Unicode signs. Line
    breaks and any non-sign non-space symbol (e.g. ?, <D>, […]) terminate the
    run. This prevents a physically nonexistent 4-sign match from being
    assembled by stripping a damaged or illegible passage.
    """
    from transcription import FACE_MARKER, is_sign
    runs = []
    for part in FACE_MARKER.split(text):
        for line in part.splitlines():
            current = []
            for ch in line:
                if is_sign(ch):
                    current.append(ch)
                elif ch in (' ', '\t', '\u00a0'):
                    continue
                else:
                    if current:
                        runs.append(''.join(current))
                        current = []
            if current:
                runs.append(''.join(current))
    return runs


def _build_sign_automaton(signs: str) -> list[dict]:
    """Suffix automaton for longest shared contiguous sequence, O(n) build."""
    states = [{'next': {}, 'link': -1, 'length': 0, 'end': -1}]
    last = 0
    for pos, char in enumerate(signs):
        cur = len(states)
        states.append({'next': {}, 'link': 0, 'length': states[last]['length'] + 1, 'end': pos})
        node = last
        while node != -1 and char not in states[node]['next']:
            states[node]['next'][char] = cur
            node = states[node]['link']
        if node != -1:
            other = states[node]['next'][char]
            if states[node]['length'] + 1 == states[other]['length']:
                states[cur]['link'] = other
            else:
                clone = len(states)
                states.append({'next': states[other]['next'].copy(),
                               'link': states[other]['link'],
                               'length': states[node]['length'] + 1,
                               'end': states[other]['end']})
                while node != -1 and states[node]['next'].get(char) == other:
                    states[node]['next'][char] = clone
                    node = states[node]['link']
                states[other]['link'] = clone
                states[cur]['link'] = clone
        last = cur
    return states


def _evidence(automata: list[tuple[str, list[dict]]], source_segments: list[str]) -> dict | None:
    """An exact glyph run, with locations in sign-only runs (not phonetic alignment).

    Scan is linear in the number of signs per source segment for each query
    segment. It does not guess how glyphs align to ATF words or syllables.
    """
    best = None
    for query_idx, (query_signs, states) in enumerate(automata):
        for source_idx, source_signs in enumerate(source_segments):
            node = match_len = 0
            for source_end, char in enumerate(source_signs):
                while node and char not in states[node]['next']:
                    node = states[node]['link']
                    match_len = min(match_len, states[node]['length'])
                if char in states[node]['next']:
                    node = states[node]['next'][char]
                    match_len += 1
                else:
                    node = match_len = 0
                if match_len and (best is None or match_len > best['sign_count']):
                    query_start = states[node]['end'] - match_len + 1
                    best = {
                        'unicode': source_signs[source_end - match_len + 1:source_end + 1],
                        'sign_count': match_len,
                        'query_segment': query_idx + 1,
                        'source_segment': source_idx + 1,
                        'query_sign_offset': query_start,
                        'source_sign_offset': source_end - match_len + 1,
                    }
    return best


def _ngrams(segments: list[str], width: int) -> set[str]:
    return {segment[pos:pos + width]
            for segment in segments if len(segment) >= width
            for pos in range(len(segment) - width + 1)}


def _anchors(grams: set[str], limit: int = 12) -> list[str]:
    """Deterministic spread over all anchors, not just the first line."""
    ordered = sorted(grams)
    if len(ordered) <= limit:
        return ordered
    return [ordered[(idx * (len(ordered) - 1)) // (limit - 1)] for idx in range(limit)]


def similar_signs(text: str, *, db_path: Path | str = DEFAULT_DB,
                  limit: int = 8, period: str = '', genre: str = '') -> dict:
    """Retrieve attested *candidate* records sharing consecutive Unicode signs.

    The coverage fraction is NOT a confidence, probability, transliteration,
    translation or scientific accuracy metric. Only rows in the imported
    SQLite retrieval index are considered (normally SumTablets train).
    """
    if not isinstance(text, str) or len(text) > 4000:
        raise ValueError('Consulta de signos demasiado larga (máximo 4000 caracteres)')
    if type(limit) is not int or not 1 <= limit <= 15:
        raise ValueError('Límite fuera del rango 1–15')
    if not isinstance(period, str) or len(period) > 100 or not isinstance(genre, str) or len(genre) > 100:
        raise ValueError('Filtro inválido')
    segments = _sign_segments(text)
    n_signs = sum(len(s) for s in segments)
    if n_signs < 3:
        raise ValueError('Se necesitan al menos 3 signos cuneiformes consecutivos')
    if n_signs > 700:
        raise ValueError('Elegí un fragmento de hasta 700 signos para comparar')
    path = Path(db_path)
    if not status(path)['ready']:
        return {'ready': False, 'results': [], 'message': 'Primero importá SumTablets train.csv.'}

    # Four-sign anchors reduce incidental matches; for 3-sign fragments we
    # must use trigrams. Fall back to trigrams if no 4-sign anchor is attested.
    automata = [(segment, _build_sign_automaton(segment)) for segment in segments]
    with _connect(path) as connection:
        for width in (4, 3):
            grams = _ngrams(segments, width)
            if not grams:
                continue
            candidates: dict[str, dict] = {}
            for anchor in _anchors(grams):
                sql = '''SELECT id, period, genre, glyphs, transliteration, source
                         FROM tablets WHERE glyph_norm LIKE ? ESCAPE '\\'
                         AND (? = '' OR period = ?) AND (? = '' OR genre = ?)
                         ORDER BY LENGTH(glyph_norm), id LIMIT 90'''
                for row in connection.execute(sql, ('%' + _escape_like(anchor) + '%',
                                                     period, period, genre, genre)):
                    candidates[row['id']] = dict(row)
            results = []
            for row in candidates.values():
                source_segments = _sign_segments(row['glyphs'])
                row_grams = _ngrams(source_segments, width)
                common = grams & row_grams
                if not common:
                    continue
                matches = len(common)
                evidence = _evidence(automata, source_segments)
                if not evidence or evidence['sign_count'] < width:
                    continue
                # Evidence is an exact contiguous Unicode span only: no ATF alignment.
                results.append({**row, 'cdli_url': cdli_url(row['id']),
                                'evidence': evidence,
                                'shared_ngrams': matches, 'query_ngrams': len(grams),
                                'ngram_width': width, 'overlap_fraction': round(matches/len(grams), 4),
                                'match_type': 'fragmentos documentados'})
            if results:
                results.sort(key=lambda row: (-row['evidence']['sign_count'],
                                              -row['overlap_fraction'], -row['shared_ngrams'],
                                              len(row['glyphs']), row['id']))
                return {'ready': True, 'results': results[:limit], 'query_signs': n_signs,
                        'ngram_width': width,
                        'message': 'Coincidencias de secuencias; NO son lecturas automáticas ni probabilidades.'}
    return {'ready': True, 'results': [], 'query_signs': n_signs,
            'message': 'No se encontraron fragmentos compartidos en el corpus indexado.'}
