"""Continue the authorized experiment after summary preparation completes."""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode=True
import experiment_raptor_large as exp

out=exp.OUT
while not (out/'build_manifest.json').exists():
    time.sleep(5)

def phase(name,script,*args):
    print('START',name,exp.audit.now(),flush=True)
    with (out/(name+'.log')).open('w') as log:
        subprocess.run([sys.executable,'-B',str(Path(__file__).with_name(script)),*args],stdout=log,stderr=subprocess.STDOUT,check=True)
    print('DONE',name,exp.audit.now(),flush=True)

phase('example','build_raptor_example.py')
phase('development','experiment_raptor_large.py','dev')
dev=exp.audit.rows(out/'results_dev.jsonl')
assert len(dev)==24 and all('error' not in r['answer_call'] and not r['answer_call']['truncated'] for r in dev)
assert all(r['selected_context_tokens']<=1024 for r in dev)
exp.v1.dump(out/'development_gate.json',{'passed_at_utc':exp.audit.now(),'rows':24,'quality_was_not_used_to_tune':True,'checks':['no transport errors','no input truncation','selected evidence <=1024']})
phase('evaluation','experiment_raptor_large.py','run')
phase('analysis','analyze_raptor_large.py')
phase('verification','verify_raptor_large.py')
print('READY FOR REPORT REVIEW',exp.audit.now(),flush=True)
