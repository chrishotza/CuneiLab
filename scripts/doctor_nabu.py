"""Read-only NabuOCR environment diagnostics. No network, weights or remote code.

This is a *preflight*, not proof that a checkpoint loads or recognizes a tablet.
Use --python to inspect the exact virtualenv that CuneiLab will execute.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MODULES = ('torch', 'transformers', 'Pillow', 'accelerate', 'safetensors')
PROBE = r'''
import importlib.metadata as metadata
import json
import platform
import sys
versions={}
for name in ('torch','transformers','Pillow','accelerate','safetensors'):
    try: versions[name]=metadata.version(name)
    except metadata.PackageNotFoundError: versions[name]=None
print(json.dumps({'python':sys.version.split()[0], 'platform':platform.system(),
                  'packages':versions}))
'''


def inspect_python(python: Path, *, executor=subprocess.run):
    executable = Path(python).expanduser().resolve()
    if not executable.is_file():
        raise ValueError('No existe el Python indicado: ' + str(executable))
    try:
        response = executor([str(executable), '-I', '-c', PROBE],
                            text=True, capture_output=True, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('No pude inspeccionar el entorno: ' + type(exc).__name__) from exc
    if response.returncode != 0:
        raise ValueError('Fallo al inspeccionar el Python seleccionado')
    try:
        data = json.loads(response.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError('Respuesta de diagnóstico inválida') from exc
    if not isinstance(data, dict) or not isinstance(data.get('packages'), dict):
        raise ValueError('Respuesta de diagnóstico incompleta')
    packages = data['packages']
    missing = [module for module in MODULES if not packages.get(module)]
    return {'executable': str(executable), 'python': data.get('python'),
            'platform': data.get('platform'), 'packages': packages, 'missing': missing,
            'dependencies_present': not missing,
            'model_weights_checked': False, 'model_inference_checked': False,
            'note': 'Comprueba instalación de paquetes, NO compatibilidad de versiones ni lectura de fotografías.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Diagnóstico NabuOCR sin descargar pesos ni ejecutar terceros')
    parser.add_argument('--python', type=Path, default=Path(sys.executable), help='Python del entorno NabuOCR')
    parser.add_argument('--revision', help='SHA completo del modelo revisado por el operador (opcional)')
    args = parser.parse_args(argv)
    if args.revision and not re.fullmatch(r'[0-9a-fA-F]{40}', args.revision):
        parser.error('--revision debe contener exactamente 40 caracteres hexadecimales')
    try:
        result = inspect_python(args.python)
    except ValueError as e:
        parser.exit(2, f'Error: {e}\n')
    result['revision_format_valid'] = bool(args.revision)
    result['revision_verified_remotely'] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['dependencies_present'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
