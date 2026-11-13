# CuneiLab v0.4 — editor de tablillas y puente de detección cuneiforme

**Estado:** estación de trabajo experimental que funciona offline para anotación, glosario y lectura documentada de corpus. **NO traduce automáticamente fotografías ni incluye un modelo neuronal preinstalado.**

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
4. Cargá una fotografía en **La tablilla**. Para superponer detecciones, usá **Importar resultado OCR (.json)** y elegí el JSON de la *misma fotografía* (mismas dimensiones originales). Revisá cada caja y su `label` antes de aceptar. Toda lectura importada se conserva solo como sugerencia en las notas y queda marcada `?` hasta que la corrijas con **Editar** en el listado de regiones.

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
