"""Optional local image -> Unicode OCR using boatbomber/NabuOCR (model weights ~2GB).

Requires separate install of PyTorch, Transformers and Pillow. The custom code
at the selected model revision is third-party code and must be explicitly trusted.
Uses the author's public evaluation notebook's OCR: prompt and transformers API.
No automatic model downloads unless this CLI is explicitly invoked.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transcription import make_document

DEFAULT_MODEL='boatbomber/NabuOCR'


def prepare_messages(image):
    return [{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':'OCR:'}]}]


def infer(image_file, model_name=DEFAULT_MODEL, device='auto', max_new_tokens=1024, revision=None, trust_remote_code=False):
    if not trust_remote_code:
        raise ValueError('Este modelo requiere código personalizado; agregá --trust-remote-code después de revisar su repositorio.')
    if not revision or not re.fullmatch(r'[a-fA-F0-9]{40}', revision):
        raise ValueError('Se exige --revision con el SHA completo de 40 caracteres del modelo revisado.')
    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForCausalLM, AutoProcessor
    except ImportError as exc:
        raise RuntimeError('Faltan PyTorch, Pillow o Transformers. Consultá la instalación opcional del README.') from exc
    if device=='auto':
        device='cuda' if torch.cuda.is_available() else 'cpu'
    if device.startswith('cuda') and not torch.cuda.is_available():
        raise RuntimeError('No hay CUDA disponible. Elegí --device cpu o instalá CUDA.')
    dtype=torch.bfloat16 if device.startswith('cuda') and torch.cuda.is_bf16_supported() else torch.float32
    load_args={'trust_remote_code': True, 'torch_dtype':dtype}
    if revision: load_args['revision']=revision
    model=AutoModelForCausalLM.from_pretrained(model_name,**load_args).to(device).eval()
    processor=AutoProcessor.from_pretrained(model_name,trust_remote_code=True, **({'revision':revision} if revision else {}))
    with Image.open(image_file) as input_image:
        width,height=input_image.size
        if width>30000 or height>30000 or min(width,height)<1:
            raise ValueError('Imagen fuera de los límites admitidos')
        image=input_image.convert('RGB')
        inputs=processor.apply_chat_template(prepare_messages(image),tokenize=True,
            add_generation_prompt=True,return_dict=True,return_tensors='pt').to(device)
    with torch.inference_mode():
        generated=model.generate(**inputs,max_new_tokens=max_new_tokens,
                                 repetition_penalty=1.03,do_sample=False,use_cache=True)
    completion=generated[0,inputs['input_ids'].shape[1]:]
    predicted=processor.decode(completion,skip_special_tokens=False).strip()
    # Strip the outer EOS only; preserve @obverse/@reverse tokens used by the model.
    for eos in ('</s>','<|endoftext|>','<|im_end|>'):
        if predicted.endswith(eos): predicted=predicted[:-len(eos)].strip()
    return make_document(predicted,width,height,Path(image_file).name,
                         model=f'{model_name}@{revision or "un-pinned"}',
                         source='NabuOCR local inference (machine-generated; unverified)')


def main(argv=None):
    ap=argparse.ArgumentParser(description='OCR fotográfico -> signos Unicode (NabuOCR)')
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--model', default=DEFAULT_MODEL)
    ap.add_argument('--revision',help='Commit SHA fijado para reproducibilidad y revisión de código')
    ap.add_argument('--device', choices=['auto','cpu','cuda','cuda:0'],default='auto')
    ap.add_argument('--max-new-tokens',type=int,default=1024)
    ap.add_argument('--trust-remote-code',action='store_true',help='Autorizo el código personalizado del modelo de terceros')
    a=ap.parse_args(argv)
    if not a.image.is_file(): ap.error('No existe la fotografía indicada')
    if a.max_new_tokens<1 or a.max_new_tokens>4096: ap.error('max-new-tokens debe estar entre 1 y 4096')
    if not a.trust_remote_code: ap.error('Falta --trust-remote-code (revisá primero el código del modelo)')
    if not a.revision or not re.fullmatch(r'[a-fA-F0-9]{40}',a.revision): ap.error('--revision requiere un SHA hexadecimal de 40 caracteres')
    result=infer(a.image, model_name=a.model,device=a.device,max_new_tokens=a.max_new_tokens,
                 revision=a.revision,trust_remote_code=True)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=a.output.with_suffix(a.output.suffix+'.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(a.output)
    print(f'OCR exportado: {a.output} — {result["sign_count"]} glifos Unicode; requiere revisión humana')


if __name__=='__main__':
    main()
