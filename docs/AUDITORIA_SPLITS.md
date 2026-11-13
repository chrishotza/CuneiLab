# Auditoría de contaminación entre conjuntos

Antes de medir OCR, comprobá que los CSV usados para entrenar y evaluar no contienen identificadores o textos idénticos entre particiones:

```powershell
py -3 scripts/audit_splits.py --train data/train.csv --validation data/validation.csv --test data/test.csv --output data/reports/splits.json
```

El programa imprime un JSON y termina con código **1** si detecta duplicados o **0** si no encuentra solapamientos exactos. El campo `passed_exact_overlap_audit` indica únicamente el resultado de esa comprobación, **no** que la evaluación neuronal sea independiente.

**Cobertura real:** identifica duplicados de `id` dentro de cada CSV y entre CSV, y textos `glyphs` idénticos (elimina espacios y saltos, pero conserva marcas de daño). No descubre fotos duplicadas, textos similares con variantes, duplicados entre transliteraciones diferentes ni muestras vistas por NabuOCR durante su preentrenamiento. Una prueba rigurosa requiere además cotejar imágenes, identificadores y splits de entrenamiento del modelo.

No descargamos, incorporamos ni distribuimos corpus de terceros al ejecutar este comando. Usá las mismas versiones congeladas de los archivos en cada comparación.