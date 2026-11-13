# CuneiLab 0.3 — estación local para estudiar tablillas cuneiformes

**Estado:** prototipo funcional, no un traductor automático integral. Incluye la interfaz de v0.1 y un módulo nuevo de consulta de corpus real (SumTablets).

## Qué funciona

- Editor y anotación manual de fotos con regiones, filtros, importación/exportación de proyectos.
- Catálogo de 1.118 caracteres cuneiformes Unicode, con lecturas orientativas para una selección limitada.
- Glosario introductorio para analizar transliteraciones sumerias y algunas acadias (no traduce la sintaxis).
- **Nuevo:** importación en SQLite de CSV oficiales del corpus [SumTablets](https://huggingface.co/datasets/colesimmons/SumTablets), búsqueda por **secuencias Unicode** o **transliteración**, lista de coincidencias exactas / de prefijo / parciales con identificador, época y género.
- **v0.3:** filtros por período y género, contexto KWIC de coincidencias, búsqueda por ID P/Q y enlaces de P-numbers a fichas CDLI.
- **v0.3:** descarga opcional del CSV de entrenamiento verificada por SHA-256, sin descargar datos de evaluación.
- **Nuevo:** sugerir usar como referencia la transliteración ya documentada de una coincidencia de corpus y someterla al análisis léxico (requiere revisión humana).
- Servidor HTTP de uso local, con biblioteca estándar de Python 3 (sin librerías externas, cuenta en nube ni claves de IA).

> **Crítico:** SumTablets no contiene traducciones al español de los 91.606 textos ni fotos listas para OCR. Sus pares son `glyphs` ↔ `transliteration`. Las coincidencias son *retrieval* (búsqueda de ejemplos documentados), **no reconocimiento visual, inferencia neuronal ni traducción automática**. Tampoco la cobertura del glosario es una métrica de precisión filológica.

## 1. Primera ejecución en Windows

1. Instalá [Python 3](https://www.python.org/downloads/) (marcá **Add Python to PATH** al instalar), si todavía no está disponible.
2. Extraé el ZIP en una carpeta.
3. Abrí `iniciar_cuneilab.bat`, que inicia la página en `http://127.0.0.1:8765`.
4. Aunque no hayas importado el corpus, la aplicación conserva el editor y las anotaciones manuales.

> También podés hacer doble clic en `index.html` **sin instalar Python**: la versión offline sigue funcionando, excepto las búsquedas de corpus.

## 2. Agregar las tablillas reales de SumTablets

El corpus se descarga desde la publicación original, para conservar procedencia y evitar incluir archivos enormes en el repositorio GitHub:

1. Ejecutá `py -3 scripts/download_corpus.py --import` para descargar, verificar SHA-256 e importar automáticamente `train.csv` (aprox. 106 MB). También podés ejecutar `preparar_corpus.bat` en Windows. Alternativamente, descargá `train.csv` desde [SumTablets → Files](https://huggingface.co/datasets/colesimmons/SumTablets/tree/main).
2. Solo si descargaste el archivo manualmente: guardá `train.csv` en el directorio `data/`.
3. Solo si descargaste manualmente el CSV, desde una terminal en la carpeta del proyecto ejecutá:

   ```powershell
   py -3 scripts/import_corpus.py data/train.csv
   py -3 server.py
   ```
4. Abrí `http://127.0.0.1:8765` en Chrome o Edge; abajo vas a encontrar **Concordancia con tablillas existentes**.

La importación crea `data/sumtablets.sqlite3`, que se conserva para las siguientes sesiones. Para una primera prueba rápida podés limitar la importación:

```powershell
py -3 scripts/import_corpus.py data/train.csv --limit 1000
```

Podés repetir el importador sin duplicar IDs. Para cargar el conjunto completo después de la muestra, ejecutalo sin `--limit`.

**Aviso metodológico:** importá `train.csv` para búsqueda exploratoria. Los CSV `validation.csv` y `test.csv` deben permanecer separados si entrenamos y medimos futuros modelos, para evitar fuga de datos.

## 3. Ejecutar pruebas

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
node --test tests/engine.test.js
```

Las pruebas de JavaScript requieren Node.js; Python y el navegador no lo necesitan.

## 4. Estructura del repositorio

```text
CuneiLab/
├── index.html, styles.css, app.js, catalog.js, engine.js
├── corpus-ui.js       # búsqueda y referencias documentadas en el navegador
├── corpus.py          # importador SQLite, normalizador y buscador
├── server.py          # backend HTTP local restringido a 127.0.0.1
├── iniciar_cuneilab.bat
├── scripts/
│   └── import_corpus.py
├── tests/
│   ├── engine.test.js
│   └── test_corpus.py
├── data/               # CSV y SQLite se ignoran en Git
├── .gitignore
└── README.md
```

## 5. Hoja de ruta con criterios verificables

- **v0.3 — Corpus:** búsqueda por ID P/Q, filtros de período y género, enlaces CDLI para artefactos P, resaltado del contexto y descargador con verificación SHA-256. **Implementado.**
- **v0.4 — Modelos:** primer detector visual eBL ejecutable en un servicio opcional. Benchmark por imagen y por signo (datasets separados por época); sin llamadas externas opacas.
- **v0.5 — Transliteración:** modelo que vaya de imágenes a signos y, separadamente, de glifos digitales a lecturas. Registrar top-k, confianza y fuente.
- **v0.6 — Traducción:** traducción lingüística sumerio/acadio → español basada en corpus bilingüe y revisión profesional, con alineación de palabras e incertidumbre.

## 6. Fuentes y atribución

- **SumTablets:** Cole Simmons, Richard Diehl Martinez, Dan Jurafsky, *SumTablets: A Transliteration Dataset of Sumerian Tablets*, ACL ML4AL 2024, [dataset](https://huggingface.co/datasets/colesimmons/SumTablets), **CC BY 4.0**. Los datos no se incluyen automáticamente con este proyecto: cada instalación los importa desde el original.
- **CDLI REST API:** [documentación](https://cdli.earth/docs/api).
- **ePSD2:** [Sumerian Dictionary](https://oracc.museum.upenn.edu/epsd2/).
- **eBL:** [cuneiform-ocr](https://github.com/ElectronicBabylonianLiterature/cuneiform-ocr).

Este repositorio no tiene licencia de software seleccionada: elegí la apropiada antes de publicarlo. Respeta las licencias, condiciones y atribuciones de los corpus y modelos que se incorporen.

## Alcance y seguridad de la versión 0.3

- Los vínculos CDLI usan `https://cdli.earth/artifacts/123456` para un ID `P123456`. Los identificadores compuestos `Q` no se presentan como artefactos individuales.
- La vista de contexto KWIC resalta una coincidencia textual, no una traducción ni una alineación lingüística.
- El descargador verifica un hash SHA-256 publicado por SumTablets para su `train.csv` de referencia. Si el archivo cambia, se detiene en vez de aceptar material no verificado. No se descargan ni indexan los conjuntos de evaluación.
- La base SQLite no se sube a GitHub: cada usuario la construye en su PC.
- Faltan el OCR de fotos y la traducción automática a español. Las herramientas de análisis léxico existente son ayudas de revisión, no resultados de modelos de IA evaluados.
