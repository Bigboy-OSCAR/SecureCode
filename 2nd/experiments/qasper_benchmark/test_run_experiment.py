import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import run_experiment as r

class Tokenizer:
    def tokens(self,text):return len(text)

class TestPipeline(unittest.TestCase):
    def test_document_boundary_and_hops(self):
        nodes=[{'id':'n000001','doc_id':'one','deps':['n000002','n000003']},
               {'id':'n000002','doc_id':'one','deps':['n000004']},
               {'id':'n000003','doc_id':'two','deps':['n000005']},
               {'id':'n000004','doc_id':'one','deps':[]},
               {'id':'n000005','doc_id':'two','deps':['n000001']}]
        self.assertEqual(r.expand(nodes,'n000001',1,True,8),['n000001','n000002'])
        self.assertEqual(r.expand(nodes,'n000001',2,False,8),['n000001','n000002','n000003','n000004','n000005'])
        self.assertEqual(len(r.expand(nodes,'n000001',30)),5)
    def test_selector_requires_one_whole_listed_id_and_finished_output(self):
        index={'ids':['n000001']}
        for text in ['n000001 n000002','I choose n000001','n000002','```n000001```','']:
            self.assertFalse(r.parse_selector({'answer':text,'status':'ok'},index)[1])
        self.assertTrue(r.parse_selector({'answer':' n000001\n','status':'ok'},index)[1])
        for flag in [{'stopped_limit':True},{'stop_type':'limit'}]:
            self.assertFalse(r.parse_selector({'answer':'n000001','status':'ok','response':flag},index)[1])
    def test_original_fragment_is_not_a_summary(self):
        original='  Kept spaces.\nExact amount = 2.50!\n'
        node={'id':'n000001','doc_id':'d1','start':0,'end':len(original)}
        self.assertTrue(r.source_text({'context':original},node).endswith(original))
    def test_greedy_whole_item_and_covered_duplicate(self):
        items=[(1,{'id':'too_long','source_ids':['x'],'text':'x'*1025}),
               (.9,{'id':'fits','source_ids':['a'],'text':'a'*600}),
               (.8,{'id':'duplicate','source_ids':['a'],'text':'a'*600}),
               (.7,{'id':'fits2','source_ids':['b'],'text':'b'*400})]
        text,chosen,rejected=r.pack(items,Tokenizer())
        self.assertEqual(len(text),1002)
        self.assertEqual([i['id'] for i in chosen],['fits','fits2'])
        self.assertEqual(rejected,['too_long'])
    def test_full_keeps_all_context(self):
        sentinel='FIRST\n'+'x'*40000+'\nLAST'
        p=r.answer_prompt('hotpotqa','Question?',sentinel)
        self.assertIn(sentinel,p)
    def test_overflow_never_calls_model_and_logs_requested_tokens(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'OUT',Path(d)):
            c=r.Client('http://unused',Tokenizer())
            c.post=lambda *a,**k:self.fail('Overflow must not send a truncated input')
            rec,_=c.complete('x'*33000,32,'fixture','FULL','answer')
            self.assertEqual(rec['status'],'context_overflow');self.assertEqual(rec['input_tokens'],0)
            self.assertGreater(rec['requested_input_tokens'],32768)
    def test_failed_request_preserved_and_not_silently_retried(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'OUT',Path(d)):
            c=r.Client('http://unused',Tokenizer()); attempts=[]
            def fail(*args,**kwargs):
                records=list(Path(d).rglob('*.json.gz'));self.assertEqual(len(records),1)
                self.assertEqual(r.read(records[0])['status'],'pending')
                attempts.append(1);raise TimeoutError('fixture')
            c.post=fail
            with self.assertRaises(TimeoutError):c.complete('text',32,'fixture','A','answer')
            stored=r.read(next(Path(d).rglob('*.json.gz')))
            self.assertEqual(stored['status'],'transport_error');self.assertTrue(stored['execution_cost_unknown'])
            with self.assertRaises(AssertionError):c.complete('text',32,'fixture','A','answer')
            self.assertEqual(len(attempts),1)
    def test_completed_call_is_reused_only_after_request_identity_check(self):
        with tempfile.TemporaryDirectory() as d,patch.object(r,'OUT',Path(d)):
            c=r.Client('http://unused',Tokenizer());count=[]
            def complete(path,payload):
                count.append(1)
                return {'content':'answer','tokens_predicted':2,'tokens_evaluated':len(payload['prompt']),'stop_type':'eos'}
            c.post=complete
            first,_=c.complete('text',32,'fixture','A','answer')
            second,reused=c.complete('text',32,'fixture','A','answer')
            self.assertTrue(reused);self.assertEqual(first,second);self.assertEqual(len(count),1)
            with self.assertRaises(AssertionError):c.complete('different',32,'fixture','A','answer')

if __name__=='__main__':unittest.main()
