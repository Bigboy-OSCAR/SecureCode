"""Focused invariants for question removal, losslessness, and literal-only graph edges."""
import unittest
from common import Tokenizer, digest
from prepare_data import build_document, extract_input, document_ranges, is_heading


class WordTokenizer:
    def tokens(self,text):return len(text.split())


class PreparationTests(unittest.TestCase):
    def setUp(self):self.tok=WordTokenizer()
    def test_scrolls_lossless_prefix(self):
        source='Who did it?\n\n\n  The exact document.\n\n'
        q,c,p,raw=extract_input('qasper',{'input':source,'id':'x'})
        self.assertEqual(q,'Who did it?');self.assertEqual(p+c,source)
        self.assertEqual(c,'\n  The exact document.\n\n')
    def test_quality_preserves_choices_in_question_only(self):
        source='Which answer?\n\n (A) Alpha\n (B) Beta\n (C) Gamma\n (D) Delta\n\n\nBODY\n'
        q,c,p,raw=extract_input('quality',{'input':source,'id':'x'})
        self.assertTrue(q.endswith('(D) Delta'));self.assertEqual(c,'\nBODY\n')
        self.assertEqual(p+c,source);self.assertNotIn('(A)',c)
        with self.assertRaises(AssertionError):extract_input('quality',{'input':source.replace('(C)','(B)'),'id':'x'})
    def test_longbench_separate_context(self):
        row={'input':'Question?','context':'  Original\n text  '}
        q,c,p,raw=extract_input('musique',row)
        self.assertEqual((q,c,p,raw),(row['input'],row['context'],'',row['input']))
    def test_quality_blank_line_inside_option_block(self):
        source='What role?\n\n (A) Career woman\n (B) Lead female\n\n (C) Director\n (D) Unknown\n\n\nARTICLE\n'
        q,c,p,raw=extract_input('quality',{'input':source,'id':'blank_b'})
        self.assertEqual(c,'\nARTICLE\n');self.assertIn('Lead female\n\n (C)',q)
        self.assertEqual(p+c,source)
    def test_three_official_quality_option_regressions(self):
        cases = {
            '32665_BFH6JK2Z_8': "Why did the squid always appear a little bit too late to save the anglers?\n\n (A) The anglers were not useful to the squid\n (B) The anglers were being punished\n\n (C) The anglers were not the squid's primary interest\n (D) The squid were a nearly defeated colony that didn’t have enough members to save every angler",
            '55815_ZJPKF6YE_5': 'What role does Greta audition for?\n\n (A) Career woman\n (B) Lead female\n\n (C) Director\n (D) Unknown',
            '51320_DIEFXLAR_5': 'What thesis does Charlie present to the Moranites?\n\n (A) The Moranites could extend their life span if they cooperated for the exploration\n (B) He is related to them by distant relative\n\n (C) They have the opportunity to advance into a technological age with some of the equipment he has\n (D) They are stranded Earthlings',
        }
        for source_id, option_block in cases.items():
            with self.subTest(source_id=source_id):
                source=option_block+'\n\n\nARTICLE TEXT\n'
                q,c,p,raw=extract_input('quality',{'input':source,'id':source_id})
                self.assertEqual(q,option_block);self.assertEqual(c,'\nARTICLE TEXT\n')
                self.assertEqual(q+'\n\n',p);self.assertEqual(p+c,source)
    def assert_lossless(self,d,source):
        self.assertEqual(d['document_id'],digest(source))
        self.assertEqual(''.join(source[n['start']:n['end']] for n in d['nodes']),source)
        self.assertEqual(d['nodes'][0]['start'],0)
        self.assertEqual(d['nodes'][-1]['end'],len(source))
        for a,b in zip(d['nodes'],d['nodes'][1:]):self.assertEqual(a['end'],b['start'])
        for n in d['nodes']:
            self.assertLessEqual(n['tokens'],256);self.assertGreater(n['tokens'],0)
            self.assertEqual(n['preview'],' '.join(source[n['start']:n['end']].split()[:12]))
    def test_continuation_only_for_split_paragraph(self):
        source='  '+('word '*600)+'\n\nIndependent paragraph.\n'
        d=build_document(source,self.tok);self.assert_lossless(d,source)
        byid={n['id']:n for n in d['nodes']}
        self.assertGreater(len(d['nodes']),3)
        for n in d['nodes']:
            for dep,types in n['edge_types'].items():
                self.assertEqual(types,['paragraph_continuation'])
                self.assertEqual(n['paragraph_id'],byid[dep]['paragraph_id'])
        self.assertEqual(d['nodes'][-1]['deps'],[])
    def test_exact_cross_document_title_mentions(self):
        source='Passage 1:\nFirst Article\nThis mentions Second Article exactly.\n\nPassage 2:\nSecond Article\nThis explains something.\n'
        d=build_document(source,self.tok);self.assert_lossless(d,source)
        self.assertEqual(len(d['roots']),2)
        n=d['nodes'][0];target=d['roots'][1]['first_node']
        self.assertIn(target,n['deps']);self.assertEqual(n['edge_types'][target],['document_title_mention'])
    def test_no_arbitrary_similarity_or_proximity_edges(self):
        source='Dogs like walks.\n\nDogs like walks and parks.\n\nA different paragraph.\n'
        d=build_document(source,self.tok);self.assert_lossless(d,source)
        self.assertTrue(all(not n['deps'] for n in d['nodes']))
    def test_heading_reference_within_document(self):
        source='Introduction\nThe details appear in Related Work.\n\nRelated Work\nThis is supporting text.\n'
        d=build_document(source,self.tok);self.assert_lossless(d,source)
        target=next(h['target_id'] for h in d['headings'] if h['text']=='Related Work')
        self.assertEqual(d['nodes'][0]['edge_types'][target],['section_heading_mention'])
    def test_no_single_word_or_duplicate_title_resolution(self):
        source='Passage 1:\nAlpha\nMentions Beta and Duplicate Title.\n\nPassage 2:\nBeta\nText.\n\nPassage 3:\nDuplicate Title\nText.\n\nPassage 4:\nDuplicate Title\nText.\n'
        d=build_document(source,self.tok)
        self.assertTrue(all(not n['deps'] for n in d['nodes']))
    def test_context_only_function_signature(self):
        import inspect
        self.assertEqual(list(inspect.signature(build_document).parameters),['context','tokenizer'])
        source='This context is stable.\n\nAnother paragraph.'
        self.assertEqual(build_document(source,self.tok),build_document(source,self.tok))
    def test_conservative_heading_lines(self):
        self.assertTrue(is_heading('Related Work'));self.assertTrue(is_heading('CHAPTER IV'))
        self.assertFalse(is_heading('Someone said this.'));self.assertFalse(is_heading('Speaker A: Hello'))
    def test_transcript_turns_and_exact_whitespace(self):
        source='\n'+''.join(f'Speaker {"ABC"[i%3]}: turn {i}.\n' for i in range(12))
        d=build_document(source,self.tok);self.assert_lossless(d,source)
        self.assertTrue(d['roots'][0]['transcript_turn_segmentation'])
        self.assertEqual(len(d['nodes']),12)
        self.assertTrue(all(not n['deps'] for n in d['nodes']))
    def test_actual_model_tokenizer_and_unicode(self):
        tok=Tokenizer();source='Résumé 한글 日本語🙂 '+('αβγ punctuation! repeated-body\n'*500)
        d=build_document(source,tok);self.assert_lossless(d,source)
        for n in d['nodes']:self.assertLessEqual(tok.tokens(source[n['start']:n['end']]),256)


if __name__=='__main__':unittest.main()
