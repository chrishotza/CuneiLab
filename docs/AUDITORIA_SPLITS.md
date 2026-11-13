# Auditoría de contaminación entre conjuntos (v2)

Usá esta herramienta antes de informar precisión de OCR. Necesita los CSV de los splits locales y **no descarga nada**.

```powershell
py -3 scripts/audit_splits.py --train data/train.csv --validation data/validation.csv --test data/test.csv --output data/reports/splits.json
```

Opcionalmente, si contás con archivos `audit.jsonl` del preparador CuneiML u otro proceso confiable, podés agregar `--train-audit data/train_audit.jsonl --test-audit data/test_audit.jsonl`. Cada línea debe tener `id` y `image_sha256` (o `crop_sha256`), con digest hexadecimal SHA-256 de 64 caracteres. Estos archivos deben corresponder a los IDs de sus respectivos CSV.

El reporte distingue tres clases de señales:

- **Conflictos exactos (código de salida 1):** IDs repetidos, signos iguales conservando líneas y caras, o imágenes con el mismo hash en diferentes particiones.
- **Coincidencias a revisar (código 3):** secuencias que se vuelven iguales únicamente si se eliminan los saltos de línea. No se tratan automáticamente como textos idénticos.
- **Sin señales detectadas (código 0):** no se encontraron los casos cubiertos; no implica ausencia de toda contaminación.

El archivo JSON incluye `passed_exact_overlap_audit` y `needs_manual_review`. No confundas estos campos con confianza neuronal ni calidad filológica. En particular, NabuOCR pudo haber usado imágenes CDLI aunque tus conjuntos locales sean diferentes; verificar esa independencia exige conocer sus fuentes de entrenamiento. La misma fotografía reescalada o recortada puede tener otro SHA-256; dos fotos de una misma tablilla también pueden ser distintas.

La auditoría se limita a evidencia aportada localmente. Conserva los marcadores de daño, no adivina caras ni modifica los CSV.

## Control de originales y recortes

Si el manifiesto contiene `source_sha256` (o `image_sha256`) junto con `crop_sha256`, la auditoría revisa **ambas** huellas por separado. Esto detecta una fotografía original reutilizada con dos recortes distintos y también un mismo recorte repetido. No se compara erróneamente el hash de un recorte contra el de una fotografía completa. Los registros solo con `crop_sha256` siguen siendo admitidos, pero **no permiten descartar** que los recortes procedan de una misma imagen original. Para comprobar esa procedencia, conservá siempre el SHA-256 original durante la preparación de datos.
