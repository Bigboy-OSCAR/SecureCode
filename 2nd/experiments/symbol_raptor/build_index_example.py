"""Generate a small explanatory fixture with the actual experiment implementations."""
from __future__ import annotations
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import experiment_full as exp


def build():
    out=exp.DEFAULT_OUT/'index_example'
    root=out/'project';root.mkdir(parents=True,exist_ok=True)
    sources={
        'service.py':"from rules import sellable\n\ndef remaining(on_hand, held):\n    return sellable(on_hand, held)\n\ndef label(on_hand):\n    return 'empty' if on_hand <= 0 else 'stocked'\n",
        'rules.py':"from policy import SAFETY_STOCK\n\ndef sellable(on_hand, held):\n    return max(0, on_hand - held - SAFETY_STOCK)\n",
        'policy.py':"SAFETY_STOCK = 3\n",
    }
    for path,source in sources.items():(root/path).write_text(source)
    index=exp.original.build_index(root)
    nodes=exp.original.source_nodes(root)
    raw=exp.original.raw_items(nodes)
    retriever=exp.original.Retriever(raw)
    question="What does remaining(9,1) return?"
    ordered=retriever.ranked(question,raw)
    start='memory://symbol/service.py::remaining'
    seed={'ok':True,'answer':start}
    a,_,valid=exp.audited.baseline_ordered({'index':index,'nodes':nodes},root,{'question':question},seed)
    assert valid
    b,_,valid=exp.ab.b_ordered({'index':index,'nodes':nodes},{'question':question},seed)
    assert valid
    executed=exp.ab.gold_audit.execution(root,[{'module':'service','function':'remaining','args':[9,1]}])[0]
    assert type(executed) is int and executed==5
    exp.original.dump(out/'generated.json',{'scope':'Illustration only; not part of the 96 evaluation questions. A/B seed explicitly fixed for showing retrieval, no LLM answer or selector is simulated.',
        'sources':sources,'question':question,'expected':executed,'expected_verified_by_execution':True,'symbol_index':index,'nodes':nodes,'raw':raw,
        'idf':retriever.idf,'document_vectors':retriever.vectors,
        'ranking':[{'id':item['id'],'score':score} for score,item in ordered],
        'A_ordered_items':[item for _,item in a],'B_ordered_items':[item for _,item in b]})
    assert [u for _,item in a for u in item['source_uris']]==[start]
    assert set(u for _,item in b for u in item['source_uris'])=={
        start,'memory://symbol/rules.py::sellable','memory://symbol/policy.py::SAFETY_STOCK'}
    assert index['symbols'][0].keys()=={'path','kind','name','qualname','start_line','end_line','uri'}
    assert next(n for n in raw if n['id']==start)['source_uris']==[
        start,'memory://symbol/rules.py::sellable','memory://symbol/policy.py::SAFETY_STOCK']
    print(json.dumps({'status':'PASS','illustration':str(out),'R0_ranked_ids':[x['id'] for _,x in ordered]},ensure_ascii=False))


if __name__=='__main__':build()
