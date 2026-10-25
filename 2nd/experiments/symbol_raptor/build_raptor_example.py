"""Generate a small, separately logged explanatory example with the actual methods."""
from __future__ import annotations
import shutil, sys
sys.dont_write_bytecode=True
import experiment_raptor_large as exp

def main():
    out=exp.OUT/'index_example';out.mkdir(exist_ok=True)
    root=out/'dataset/projects/example'
    source=exp.v1.DEFAULT_OUT/'full_file_20261024/index_example/project'
    if not root.exists():shutil.copytree(source,root,ignore=shutil.ignore_patterns('__pycache__'))
    client=exp.audit.AuditedClient(out,'http://127.0.0.1:8766')
    exp.v1.build_assets(out,client)
    asset=exp.read(out/'assets/example.json');retriever=exp.v1.Retriever(asset['raw'])
    question='What does remaining(9, 1) return?'
    generated={'purpose':'Explanation only; no evaluation question and no generated answer. Actual summaries and actual retrieval/packing.',
        'question':question,'asset':asset,'arms':{}}
    for arm in exp.ARMS:
        client.reset_query();items=asset['raw']+[s for s in asset['summaries'] if arm!='RF' or s['level']==1]
        context,tokens,chosen,rejected=exp.v1.pack(client,retriever.ranked(question,items),1024)
        before=context;details=None
        if arm=='C':context,details=exp.audit.compact_selected(asset,chosen)
        generated['arms'][arm]={'context':context,'context_before_compaction':before,'tokens':client.tokens(context),
            'selected_tokens':tokens,'chosen':chosen,'compaction':details}
    exp.v1.dump(out/'generated.json',generated)
    print({a:g['tokens'] for a,g in generated['arms'].items()},flush=True)

if __name__=='__main__':main()
