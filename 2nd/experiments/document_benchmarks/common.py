from __future__ import annotations
import ctypes, functools, gzip, hashlib, json, os
from pathlib import Path
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
OUT=REPO/'2nd/Documents/test_results/evidence/document_benchmarks_20261027'
MODEL=REPO/'1st/symbol_test/work/models/qwen2.5-coder-7b-instruct-q5_k_m.gguf'
DATASETS=['qmsum','qasper','narrative_qa','quality','hotpotqa','musique','multifieldqa_en']
ARMS=['A','B','R0','FULL']

def now():return datetime.now(timezone.utc).isoformat()
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.part')
    if path.suffix=='.gz':
        with gzip.open(temp,'wt',encoding='utf8') as f:json.dump(obj,f,ensure_ascii=False,separators=(',',':'))
    else:temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    os.replace(temp,path)
def read(path):
    path=Path(path)
    if path.suffix=='.gz':
        with gzip.open(path,'rt',encoding='utf8') as f:return json.load(f)
    return json.loads(path.read_text())
def rows(path):
    if not Path(path).exists():return []
    with Path(path).open() as f:return [json.loads(l) for l in f if l.strip()]

class Tokenizer:
    def __init__(self):
        self.lib=ctypes.CDLL(str(HERE/'tokenizer_bridge.dylib'))
        self.lib.tokenizer_open.argtypes=[ctypes.c_char_p];self.lib.tokenizer_open.restype=ctypes.c_void_p
        self.lib.tokenizer_count.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int32];self.lib.tokenizer_count.restype=ctypes.c_int32
        self.lib.tokenizer_context.argtypes=[ctypes.c_void_p];self.lib.tokenizer_context.restype=ctypes.c_int32
        self.model=self.lib.tokenizer_open(str(MODEL).encode())
        assert self.model
        self.context_train=self.lib.tokenizer_context(self.model)
    @functools.lru_cache(maxsize=2048)
    def tokens(self,text):
        b=text.encode();return self.lib.tokenizer_count(self.model,b,len(b))

def wrap(prompt):
    return '<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n<|im_start|>user\n'+prompt+'<|im_end|>\n<|im_start|>assistant\n'
