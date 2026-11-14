"""Render an offline, read-only HTML report from CuneiLab OCR diagnostics.

Does not embed scripts, load external assets, contact services or perform OCR.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

EXPECTED_FORMAT = 'cuneilab-ocr-error-analysis'


def _safe(value) -> str:
    return html.escape(str(value), quote=True)


def _number(value) -> str:
    return f'{value:,}'.replace(',', '.') if type(value) is int else '—'


def _percentage(value) -> str:
    if value is None:
        return 'Sin datos'
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError('Métrica numérica inválida')
    return f'{value * 100:.2f}%'


def _rows(rows: list[dict], columns: list[tuple[str, str]]) -> str:
    head = ''.join(f'<th scope="col">{_safe(title)}</th>' for _, title in columns)
    body = ''.join(
        '<tr>' + ''.join(f'<td>{_safe(row.get(key, "—"))}</td>' for key, _ in columns) + '</tr>'
        for row in rows
    )
    if not body:
        body = f'<tr><td colspan="{len(columns)}">Sin registros</td></tr>'
    return '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>'


def render_report(report: dict) -> str:
    if not isinstance(report, dict) or report.get('format') != EXPECTED_FORMAT or report.get('version') != 1:
        raise ValueError('Se necesita un informe cuneilab-ocr-error-analysis v1')
    evaluation, totals = report.get('evaluation'), report.get('totals')
    if not isinstance(evaluation, dict) or not isinstance(totals, dict):
        raise ValueError('El informe no contiene métricas válidas')
    required_sections = ('most_common_substitutions', 'most_deleted_reference_signs',
                         'most_inserted_predicted_signs', 'worst_tablets')
    if any(not isinstance(report.get(k), list) or
           any(not isinstance(r, dict) for r in report[k]) for k in required_sections):
        raise ValueError('El informe tiene secciones de errores inválidas')

    tablets = []
    for row in report['worst_tablets']:
        item = dict(row)
        item['rate'] = _percentage(item.get('sign_error_rate'))
        item['status_label'] = ('Sin lectura' if item.get('status') == 'missing_prediction'
                                else 'Evaluada')
        tablets.append(item)

    confusions = report['most_common_substitutions']
    deleted = report['most_deleted_reference_signs']
    inserted = report['most_inserted_predicted_signs']
    cards = [
        ('Cobertura de fotos', _percentage(evaluation.get('coverage_images'))),
        ('Error por signo (OCR completado)', _percentage(evaluation.get('micro_sign_error_rate'))),
        ('Error incluyendo fotos faltantes', _percentage(evaluation.get('micro_sign_error_rate_including_missing'))),
        ('Fotografías evaluadas', _number(evaluation.get('images_scored'))),
    ]
    cards_html = ''.join(f'<div class="metric"><span>{_safe(label)}</span><strong>{_safe(value)}</strong></div>'
                         for label, value in cards)
    totals_html = ', '.join(f'{_safe(label)}: <b>{_number(totals.get(key))}</b>'
                           for key, label in [('correct','Correctos'),('substitution','Sustituciones'),
                                              ('deletion','Omisiones'),('insertion','Inserciones')])
    scope = 'Recortes de una cara (sin etiquetas de superficie)' if report.get('cropped_faces') else 'Inscripciones completas (con etiquetas de superficie)'
    sections = [
        ('Confusiones más comunes', _rows(confusions, [
            ('reference','Signo documentado'),('prediction','Signo reconocido'),('count','Veces')])),
        ('Signos omitidos', _rows(deleted, [('token','Signo'),('count','Veces')])),
        ('Signos agregados', _rows(inserted, [('token','Signo'),('count','Veces')])),
        ('Tablillas con más errores', _rows(tablets, [
            ('id','Documento'),('status_label','Estado'),('rate','Tasa de error'),
            ('reference_tokens','Signos de referencia'),('edit_errors','Errores'),
            ('substitutions','Sustituciones'),('deletions','Omisiones'),
            ('insertions','Inserciones')])),
    ]
    sections_html = '\n'.join(f'<section><h2>{_safe(title)}</h2>{table}</section>'
                              for title, table in sections)
    limitations = _safe(report.get('limitations', ''))
    return f'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>CuneiLab | Diagnóstico OCR</title>
<style>
:root{{color-scheme:light;font-family:system-ui,Segoe UI,sans-serif;background:#f4f5f7;color:#152237}}
body{{max-width:1120px;margin:auto;padding:24px}}
h1{{margin-bottom:4px}} h2{{margin-top:30px}}
small,.muted{{color:#4d6073}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px;margin:22px 0}}
.metric{{border-radius:12px;background:#fff;padding:18px;box-shadow:0 2px 10px #13253914}}
.metric span{{display:block;font-size:.85rem;color:#46576b}}
.metric strong{{display:block;font-size:1.5rem;margin-top:8px}}
section{{overflow:auto;background:#fff;border-radius:12px;padding:14px 18px;margin:20px 0}}
table{{border-collapse:collapse;width:100%;min-width:500px}}
th,td{{text-align:left;padding:10px;border-bottom:1px solid #dbe1e8}}
th{{background:#eaf0f7}}td{{font-size:.94rem}}
footer{{font-size:.9rem;line-height:1.6}}
@media print{{body{{max-width:none}}section,.metric{{box-shadow:none;border:1px solid #ccd5dc;break-inside:avoid}}}}
</style>
</head>
<body>
<header>
<h1>CuneiLab · Diagnóstico OCR</h1>
<p class="muted">Informe local de signos Unicode; no es traducción ni certificado de precisión.</p>
<p><b>Alcance:</b> {_safe(scope)}</p>
</header>
<div class="summary">{cards_html}</div>
<p>{totals_html}</p>
{sections_html}
<footer>
<h2>Interpretación y límites</h2>
<p>{limitations}</p>
<p>Las sustituciones dependen de una alineación óptima y pueden ser ambiguas con signos repetidos.
Los porcentajes pueden superar el 100% si existen muchas inserciones.
Se necesita un conjunto independiente de fotografías y referencias para interpretar estos valores científicamente.</p>
<p class="muted">Este HTML no incluye JavaScript, fuentes externas, imágenes privadas ni conexiones de red.</p>
</footer>
</body>
</html>
'''


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description='Generar reporte OCR HTML autónomo y offline')
    parser.add_argument('--input', type=Path, required=True, help='Reporte JSON de ocr_error_analysis.py')
    parser.add_argument('--output', type=Path, required=True, help='Archivo HTML de salida')
    args = parser.parse_args(argv)
    try:
        source = json.loads(args.input.read_text(encoding='utf-8'))
        rendered = render_report(source)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding='utf-8')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f'Informe offline creado: {args.output}')


if __name__ == '__main__':
    main()
