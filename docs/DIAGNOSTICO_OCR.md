# Diagnóstico de errores del OCR por signo

El evaluador `scripts/evaluate_nabu.py` calcula tasas de error. El nuevo diagnóstico `scripts/ocr_error_analysis.py` explica **qué errores produce el OCR** y en qué documentos aparecen.

```powershell
py -3 scripts/ocr_error_analysis.py --gold data/cuneiml/benchmark01/gold.jsonl --predicted data/ocr/batch/predictions.jsonl --cropped-faces --top 25 --output data/ocr/batch/errores_detallados.json
```

Las dos entradas son JSONL con objetos `{"id":"P123456-reverse","text":"𒀭𒆠"}`. Usá las mismas referencias y predicciones que para `evaluate_nabu.py`. El informe contiene:

- `most_common_substitutions`: signos Unicode de referencia confundidos con otros.
- `most_deleted_reference_signs`: signos que faltan en el OCR.
- `most_inserted_predicted_signs`: signos extra.
- `worst_tablets`: imágenes de peor tasa de error, incluidas las que nunca recibieron predicción.
- `evaluation`: cobertura y métricas compatibles con el evaluador principal.

**Alcance:** las sustituciones se infieren mediante una alineación de Levenshtein determinista, pero una secuencia con signos repetidos puede admitir varias alineaciones igualmente óptimas. Estas categorías son **diagnósticas**, no un resultado filológico único. El análisis detallado limita cada secuencia a 1.500 tokens para evitar uso descontrolado de memoria. Para recortes de una sola cara, pasá `--cropped-faces`, que ignora las etiquetas `@obverse` y `@reverse`.

El programa **no** descarga modelos ni produce predicciones por sí mismo; hasta ejecutar NabuOCR sobre imágenes reales con referencias independientes no tenemos cifras científicas de precisión.