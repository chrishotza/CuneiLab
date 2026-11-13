# CuneiLab v0.8 — lectura cuneiforme con evaluación por cara revisada

**Estado:** editor + motor de consulta de corpus + adaptadores OCR opcionales. No hay un modelo OCR preinstalado ni una traducción automática al español validada. Las pruebas automáticas usan imágenes sintéticas; no son una medición de precisión neuronal.

## v0.8: corregimos el error de evaluación de fotografías compuestas

**Importante:** en CuneiML `bboxes` define el rectángulo de una **cara principal** dentro de una fotografía compuesta, pero **no la identifica como anverso o reverso**. La v0.7 podía crear un `gold.jsonl` con TODAS las caras para una sola fotografía. Esa comparación era metodológicamente inválida. El viejo `scripts/prepare_cuneiml.py` ahora redirige al preparador seguro y su antigua función programática `prepare()` queda deshabilitada. Los resultados previos que usaran ese método **no deben citarse como tasas de error válidas**.

El nuevo `scripts/prepare_cuneiml_faces.py` usa solo **fotografías locales que tengas derecho a utilizar**, recorta según el `bboxes` oficial mediante Pillow, guarda huellas SHA-256 del original y del recorte, y **exige revisión de la cara antes de crear referencias**.

### Paso 1 — ver recortes y asignar la cara

Instalá la dependencia liviana (no instala modelos):

```powershell
py -3 -m pip install "Pillow>=10,<13"
```

Descargá **manualmente** `CuneiMLv1.2.json` desde [Zenodo](https://zenodo.org/records/10806319) y guardá en `data/cuneiml/`; las fotos `P123456.jpg` deben proceder de una fuente donde tengas derechos de uso y estar en `data/cuneiml/photos/`.

```powershell
py -3 scripts/prepare_cuneiml_faces.py --mode review --metadata data/cuneiml/CuneiMLv1.2.json --photos data/cuneiml/photos --output-dir data/cuneiml/review01 --split all --max-tablets 50 --verify-md5
```

Se generan `review01/images/P......_crop.png`, `faces_template.jsonl` y un informe `dataset.json` **sin `gold.jsonl`**. Abrí cada recorte y editá solo el valor `face` de `null` a `"obverse"`, `"reverse"`, `"left"`, etc., cuando la orientación esté confirmada. **No inventes la cara**: si no sabés cuál es, conservá `null`. No alteres los hashes.

Ejemplo de una línea *antes* de revisar (los SHA reales los crea el programa):

```json
{"id":"P131837","face":null,"source_sha256":"...","crop_sha256":"...","crop_box":[204,200,523,522],"image":"images/P131837_crop.png"}
```

### Paso 2 — producir solo pares imagen/cara verificados

```powershell
py -3 scripts/prepare_cuneiml_faces.py --mode prepare --metadata data/cuneiml/CuneiMLv1.2.json --photos data/cuneiml/photos --face-map data/cuneiml/review01/faces_template.jsonl --output-dir data/cuneiml/benchmark01 --split all --max-tablets 50 --verify-md5
py -3 scripts/batch_nabu.py --manifest data/cuneiml/benchmark01/manifest.jsonl --check
```

La herramienta crea `images/P131837_reverse.png`, `manifest.jsonl` con ID `P131837-reverse`, `gold.jsonl` **solo con los signos de esa cara**, `audit.jsonl` con la cara, el recorte y los hashes, y un `dataset.json`. Rechaza caras con Unicode incompleto o dañado; nunca elimina silenciosamente los signos ilegibles. Aborta si la fotografía o su recorte cambiaron después de la revisión. El resultado solo es **exploratorio**: nuestro split por ID no demuestra separación del conjunto de entrenamiento de NabuOCR.

Una vez que realmente ejecutes los pesos de NabuOCR con `scripts/batch_nabu.py`, evaluá un lote de recortes con:

```powershell
py -3 scripts/evaluate_nabu.py --gold data/cuneiml/benchmark01/gold.jsonl --predicted data/ocr/batch/predictions.jsonl --cropped-faces --output data/ocr/batch/metrics.json
```

`--cropped-faces` compara **solamente caracteres cuneiformes** e ignora marcadores `@obverse/@reverse` que puede emitir el modelo; en una foto de una sola cara esos marcadores no deben penalizar ni favorecer la precisión de los signos. La tasa de error incluye una versión que cuenta los documentos sin OCR como fallos totales. Este resultado **no** es una traducción lingüística ni equivale al TER tokenizado del artículo.

### Lo que la v0.8 todavía no prueba

- No se descargaron ni ejecutaron pesos de NabuOCR en GitHub Actions (son ~2 GB, con dependencias independientes).
- No se descargaron automáticamente fotografías ni el JSON de Zenodo. No hay un benchmark visual real publicado por CuneiLab.
- Las pruebas locales y CI validan el recorte, la concordancia foto–cara, la procedencia y las métricas usando *fixtures sintéticos*.

---

# Historial: CuneiLab v0.6 — estación de OCR por lotes y evaluación reproducible

**Estado:** estación de trabajo experimental que funciona offline para anotación, glosario y lectura documentada de corpus. **NO traduce automáticamente fotografías ni incluye un modelo neuronal preinstalado.**



## v0.6 — Procesar muchas fotografías sin reiniciar NabuOCR

Se agregó `scripts/batch_nabu.py` para generar un lote reproducible de **fotografías → signos Unicode**. Carga el modelo una sola vez durante la corrida, produce un JSON CuneiLab por imagen válida y un `predictions.jsonl` compatible con el evaluador. No calcula exactitud sin referencias independientes.

### Preparar el manifiesto

Creá un archivo `data/heldout/manifest.jsonl` (una línea JSON por imagen) y colocá las fotos **dentro de esa carpeta**, por ejemplo en `data/heldout/images/`:

```jsonl
{"id":"P000001","image":"images/P000001.jpg"}
{"id":"P000002","image":"images/P000002.png"}
```

Los ID deben ser únicos y las rutas relativas no pueden escapar de la carpeta del manifiesto. `--check` calcula SHA-256 y detecta imágenes ausentes, duplicados y rutas inseguras; **no abre el modelo, no baja pesos y no modifica archivos**:

```powershell
py -3 scripts/batch_nabu.py --manifest data/heldout/manifest.jsonl --check
```

### Ejecutar lote con un checkpoint fijo

Desde el entorno virtual con PyTorch, Transformers y NabuOCR previamente revisados:

```powershell
.venv-nabu\Scripts\python scripts/batch_nabu.py --manifest data/heldout/manifest.jsonl --output-dir data/ocr/lote01 --revision SHA_COMPLETO_DE_40_CARACTERES --device auto --trust-remote-code
```

- Revisá el código de terceros antes de pasar `--trust-remote-code`. La revisión SHA debe ser **exacta y previamente verificada**, nunca una etiqueta móvil como `main`.
- Salidas: `run.json` (modelo, revisión, huellas de imágenes y configuración), `predictions.jsonl` (solo lecturas conseguidas), `errors.jsonl` (errores), `summary.json` (cobertura) y `documents/<ID>.json` (importables en CuneiLab).
- Si la ejecución se interrumpe, repetí el mismo comando con `--resume`. No permite reanudar cuando cambia el modelo, el manifiesto o los bytes de una fotografía. No sobrescribe resultados anteriores sin confirmación explícita mediante un directorio nuevo.
- Un error de OCR **no** se convierte en una lectura falsa: se registra como fallo y se excluye de las predicciones.

### Medir contra una referencia independiente

Prepará `data/heldout/gold.jsonl` con `{"id":"P000001","text":"𒀭𒆠"}` por línea. Cada referencia debe estar revisada y corresponder a la misma fotografía. Ejecutá:

```powershell
py -3 scripts/evaluate_nabu.py --gold data/heldout/gold.jsonl --predicted data/ocr/lote01/predictions.jsonl --output data/ocr/lote01/metrics.json
```

El evaluador muestra IDs faltantes y la tasa de errores **solo sobre las imágenes que tienen predicción**, por lo que **siempre debés citar junto con ella la cobertura del lote** (`succeeded/total`). No confundas esa tasa con la calidad de traducción ni con el TER del autor. Conservá separados entrenamiento, validación y evaluación; no importes el conjunto de prueba al buscador de entrenamiento.

**Estado verificable:** tests sin pesos para la ejecución, hashes, rutas, reanudación, aislamiento de modelos y fallos. No se afirma haber calculado un benchmark neuronal real. El conjunto de evaluación y las fotografías deben aportarse/descargarse respetando sus licencias.

## v0.5 — OCR de fotografía a Unicode con NabuOCR (opcional)

La versión 0.5 integra **[NabuOCR](https://huggingface.co/boatbomber/NabuOCR)**, un modelo ya entrenado basado en PaddleOCR-VL, que produce **signos Unicode** desde una foto de tablilla. A diferencia del motor eBL, genera **texto sin coordenadas por signo**. No traduce a español ni garantiza lecturas filológicamente correctas.

**Dependencias opcionales y descarga grande:** el modelo ocupa aproximadamente **2,05 GB** y puede requerir bastante memoria; se recomienda una GPU compatible. No está incluido en el ZIP ni se descarga cuando se abre el programa. El código del modelo es de terceros; requiere `--trust-remote-code`, que solo debe usarse tras inspeccionarlo y fijar una revisión (`--revision`).

1. Instalá las dependencias en un entorno virtual separado del servidor CuneiLab (consulta las versiones compatibles en el repositorio del modelo):

   ```powershell
   py -3 -m venv .venv-nabu
   .venv-nabu\Scripts\python -m pip install --upgrade pip
   .venv-nabu\Scripts\python -m pip install torch torchvision pillow "transformers>=4.57,<5" accelerate safetensors
   ```

2. Revisá el código remoto de NabuOCR y obtené una revisión Git concreta de Hugging Face (sin utilizar una referencia móvil en usos científicos). Ejecutá:

   ```powershell
   .venv-nabu\Scripts\python scripts/run_nabu_ocr.py --image data/tablet.jpg --output data/ocr/tablet.json --device auto --revision TU_SHA_VERIFICADO --trust-remote-code
   ```

   El programa usa el mismo prompt `OCR:` y la clase `AutoModelForCausalLM` que el [cuaderno de evaluación publicado por NabuOCR](https://huggingface.co/boatbomber/NabuOCR/blob/main/training/cuneiform_ocr_eval.ipynb). El script aborta si el resultado no contiene signos cuneiformes; no inventa una transcripción.

3. Iniciá CuneiLab (`iniciar_cuneilab.bat`), cargá **la misma fotografía** y pulsá **«Importar transcripción neuronal (.json)»**. Verificá el texto en la vista previa y elegí **«Usar signos en el editor»** para revisarlo. Se conserva la procedencia del OCR en el proyecto exportado.

### Evaluación con referencias independientes

Usá dos archivos JSONL **separados**, uno de referencia y otro de predicciones, con `{"id":"P123456","text":"𒀭𒆠"}` por fila. No entrenes ni elijas hiperparámetros sobre el conjunto de evaluación.

```powershell
py -3 scripts/evaluate_nabu.py --gold data/gold.jsonl --predicted data/predicted.jsonl --output data/ocr/evaluation.json
```

El reporte incluye tasa de errores por signo basada en **Levenshtein de glifos Unicode y marcadores de cara** y detalla IDs faltantes. **No es el TER basado en IDs del tokenizer del autor ni un puntaje de traducción.**

**Estado de las pruebas:** interfaces, formatos, métricas y CLI probados sin pesos. No se ha ejecutado una inferencia real de NabuOCR ni un benchmark sobre fotografías con este lanzamiento: requiere instalar el modelo, sus pesos y ejecutar un conjunto de evaluación con ground truth.

## Capacidades actuales

- Subir una foto local, ajustar brillo y contraste, dibujar regiones y transcribirlas manualmente.
- Consultar 1.118 caracteres Unicode y un glosario introductorio de sumerio/acadio; los análisis léxicos no son traducciones filológicas.
- Buscar identificadores, transliteraciones y glifos documentados en [SumTablets](https://huggingface.co/datasets/colesimmons/SumTablets) con un índice SQLite local opcional, e ir a CDLI cuando hay `P-number`.
- **v0.4: importar predicciones visuales** en JSON CuneiLab o COCO con una sola imagen; dibujar cajas de signos detectados sobre la foto, filtrar por confianza, mostrar orden aproximado por renglones y aceptar las hipótesis como regiones **sin lectura fonética confirmada**.
- **v0.4: adaptador de inferencia eBL/MMDetection opcional** para quien tenga un checkpoint/config compatible en un entorno de Python correctamente configurado. No descarga ni incluye modelos.
- **v0.4: evaluación reproducible** de predicciones frente a cajas de referencia anotadas (greedy IoU por clase, precision/recall/F1). **No** es COCO mAP ni mide calidad de traducción.

## Abrirlo en Windows

1. Instalá [Python 3](https://www.python.org/downloads/) si no lo tenés. El servidor no requiere `pip install`.
2. Descomprimí el proyecto y ejecutá `iniciar_cuneilab.bat`.
3. En el navegador abrí `http://127.0.0.1:8765`. Sin Python, `index.html` sirve para el editor y la importación de detecciones; la búsqueda de corpus necesita servidor.
4. Cargá una fotografía en **La tablilla**. Para superponer detecciones, usá **Importar resultado OCR (.json)** y elegí el JSON de la *misma fotografía* (mismas dimensiones originales). Revisá cada caja y su `label` antes de aceptar. La lectura importada, si no se proporciona explícitamente, queda en `?`.

El botón **Aceptar detecciones visibles como regiones** no asigna lecturas automáticamente. Las clases del modelo, como `AN` o `CLASS_2`, no equivalen siempre a una pronunciación o interpretación inequívoca. Cambiar el umbral de confianza únicamente filtra predicciones, no mejora el modelo.

## Formato de detecciones

```json
{
  "format": "cuneilab-detections", "version": 1,
  "image": {"width": 1024, "height": 768},
  "source": "nombre del modelo / versión",
  "detections": [
    {"bbox": [110, 245, 35, 42], "label": "AN", "confidence": 0.81, "reading": ""}
  ]
}
```

- `bbox`: `[x, y, ancho, alto]` en **píxeles de la imagen original**, no del canvas escalado.
- `label`: clase visual devuelta por un modelo, no traducción. `reading` opcional solo cuando existe una lectura verificada externamente.
- `confidence`: de 0 a 1. En COCO se acepta un `score` por anotación, si existe.
- Se valida que ninguna caja sobresalga de la imagen y que la fotografía cargada tenga exactamente las mismas dimensiones.
- También se admite COCO con `images/categories/annotations`, **solo** para una imagen coincidente. Si el JSON tiene varias imágenes, se selecciona por el nombre del archivo cargado; en caso de duda, se rechaza.

El editor guarda las predicciones pendientes en su JSON de proyecto junto con las anotaciones aceptadas. No guarda la configuración/los pesos del modelo neuronal.

## Ejecutar OCR real con un checkpoint eBL (opcional, avanzado)

El proyecto [eBL `cuneiform-ocr`](https://github.com/ElectronicBabylonianLiterature/cuneiform-ocr) publicó modelos DETR de 173 y 106 clases; los pesos, las configuraciones y las dependencias vienen de su distribución, **no** están incluidos en CuneiLab. Seguí las instrucciones específicas de su repositorio (especialmente las restricciones de MMDetection, MMCV, PyTorch y CUDA), en un **entorno separado**. En algunas máquinas Windows el entorno nativo requerirá WSL2/Linux y GPU compatible. No hay compatibilidad CPU garantizada para los checkpoints de origen.

Desde ese entorno, con el **mismo** MMDetection que corresponde a tu checkpoint:

```powershell
python scripts/run_ebl_ocr.py --image data/tablilla.jpg --config path/al/detr.py --checkpoint path/al/epoch_1000.pth --classes data/classes.json --device cpu --threshold 0.35 --output data/detecciones.json
```

`classes.json` es una lista JSON de los nombres de clase **en el mismo orden exacto** que se usó en el entrenamiento, no una lista inventada. Si el checkpoint ya expone `model.dataset_meta['classes']`, el argumento `--classes` es opcional. Un orden erróneo de clases invalida las etiquetas aunque los cuadros sean plausibles. El programa se detiene si no hay clases identificables. `--device cuda:0` es posible solo si tu instalación lo soporta.

El adaptador usa `mmdet.apis.init_detector` y `inference_detector`. **No se ha medido aún su rendimiento con checkpoints eBL reales en esta instalación**, porque no se descargaron los pesos ni se preparó el entorno GPU. Esto es una integración ejecutable y verificable, no un servicio de IA inventado.

Una vez obtenido `data/detecciones.json`, abrilo desde el botón de importación de CuneiLab después de cargar la misma imagen.

## Evaluar predicciones (sin fuga de datos)

Creá un segundo JSON CuneiLab con cajas de referencia **revisadas** de la misma fotografía y clases consistentes. Después ejecutá:

```powershell
python scripts/evaluate_ocr.py --reference data/referencia.json --predictions data/detecciones.json --iou 0.5 --score 0.35
```

El script mide precisión, exhaustividad, F1, TP, FP y FN mediante emparejamiento greedy por clase e IoU. No calculamos AP/mAP, CER ni calidad filológica aquí. Para un benchmark serio se necesita un conjunto externo de imágenes de evaluación, separado de entrenamiento, con clases compatibles y licencias verificadas.

## Importar textos documentados de SumTablets

Usá **solo** el conjunto `train` para construir el buscador; reservá validación y test para evaluaciones honestas:

```powershell
py -3 scripts/download_corpus.py --import
```

En Windows también podés ejecutar `preparar_corpus.bat`. Descarga y comprueba SHA-256 antes de importar. Alternativamente, descargá manualmente el `train.csv` del repositorio de datos:

```powershell
py -3 scripts/import_corpus.py data/train.csv
```

La base se crea en `data/sumtablets.sqlite3`, excluida del repositorio.

## Pruebas

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
node --test tests/*.test.js
```

Las pruebas del adaptador simulan resultados de MMDetection sin afirmar que los pesos externos estén instalados. Las pruebas visuales de navegador podrían requerir un entorno sin bloqueos de `file://` y `localhost`.

## Estructura

| Archivo | Responsabilidad |
|---|---|
| `index.html`, `styles.css`, `app.js` | Interfaz, anotación de fotos y edición |
| `vision.js`, `vision.py` | Formato, validación, lectura espacial, IoU, adaptadores |
| `scripts/run_ebl_ocr.py` | Inferencia opcional externa con MMDetection |
| `scripts/evaluate_ocr.py` | Medición por imagen, por caja y por clase |
| `corpus.py`, `corpus-ui.js`, `server.py` | Corpus local e interfaz HTTP |
| `scripts/download_corpus.py`, `scripts/import_corpus.py` | Importación de corpus y verificación de hash |
| `engine.js`, `catalog.js` | Análisis lingüístico introductorio y signos Unicode |
| `tests/` | Pruebas de backend y motor del navegador |

## Fuentes, licencias y límites

- [eBL cuneiform-ocr](https://github.com/ElectronicBabylonianLiterature/cuneiform-ocr), trabajos de Cobanoglu et al. (2024), modelos actualizados en octubre de 2025. Revisar la licencia exacta de cada checkpoint y corpus antes de redistribuir.
- [SumTablets](https://huggingface.co/datasets/colesimmons/SumTablets) — Simmons, Diehl Martinez y Jurafsky, *SumTablets*, 2024, **CC BY 4.0**. La base no se copia al repo.
- [CDLI API](https://cdli.earth/docs/api), [ePSD2](https://oracc.museum.upenn.edu/epsd2/).

Este repositorio no fija todavía una licencia de software. **El OCR detecta clases visuales; la transliteración exige resolver ambigüedad; la traducción al español exige modelos o filología adicionales.** Ninguna de esas fases debe hacerse pasar por las otras.

### Atribución NabuOCR

NabuOCR, Zack Williams (2025), licencia Apache-2.0; véase https://huggingface.co/boatbomber/NabuOCR. CuneiLab no redistribuye sus pesos.

## v0.7 — Histórico (no usar para evaluar OCR)

La preparación inicial de CuneiML de v0.7 mezclaba en una sola referencia glifos de múltiples caras. Su función `prepare()` fue desactivada; su CLI redirige a v0.8. Cualquier métrica generada con ese protocolo debe considerarse inválida y volver a calcularse con recortes cuya cara haya sido revisada.
