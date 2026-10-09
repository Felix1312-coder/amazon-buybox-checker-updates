import unittest
from core import evaluate

A='B07YSWKQBT'; B='B0FSRQNVPL'; C='B00AAW1VKQ'; D='B08JVH98YP'

def seen(*members):
    return {'valid':True,'asins':list(members)}

class LinkConfirmationTests(unittest.TestCase):
    def test_reported_sweden_case_is_unclear_not_missing_or_ok(self):
        obs={x:seen(A,B,C,D) for x in (A,B,C,D)}
        obs[A]=seen(A,C,D)
        result=evaluate([A,B,C,D],obs)
        self.assertEqual(result['status'],'Unklar')
        self.assertTrue(result['partial'])
        self.assertEqual([d['suspected_missing'] for d in result['details'] if d.get('suspected_missing')],[[B]])
        self.assertFalse(any(d['type']=='abweichung' for d in result['details']))
        self.assertFalse(any(d['asin']==A and d['type']=='ok' for d in result['details']))

    def test_consistent_split_still_alerts(self):
        result=evaluate([A,B,C,D],{A:seen(A,C),C:seen(A,C),B:seen(B,D),D:seen(B,D)})
        self.assertEqual(result['status'],'Abweichung')
        self.assertFalse(result['partial'])
        by_asin={d['asin']:d for d in result['details']}
        self.assertEqual(by_asin[A]['missing'],sorted([B,D]))
        self.assertEqual(by_asin[B]['missing'],sorted([A,C]))

    def test_unreadable_counterpart_is_unclear(self):
        for other in ({'error':'captcha'}, {'valid':False,'asins':[B]}, seen(C)):
            result=evaluate([A,B],{A:seen(A),B:other})
            self.assertEqual(result['status'],'Unklar')

    def test_third_page_contradiction_is_unclear(self):
        result=evaluate([A,B,C],{A:seen(A,C),B:seen(B,C),C:seen(A,B,C)})
        self.assertEqual(result['status'],'Unklar')

    def test_independent_extra_still_alerts(self):
        result=evaluate([A,B],{A:seen(A,C),B:seen(A,B)})
        self.assertEqual(result['status'],'Abweichung')
        self.assertTrue(result['partial'])
        self.assertEqual([d['extra'] for d in result['details'] if d['type']=='abweichung'],[[C]])

    def test_independent_attribute_change_still_alerts(self):
        result=evaluate({A:{'attributes':{'color':'Gelb'}},B:''},
            {A:{**seen(A),'attributes':{A:{'color':'Rot'}}},B:seen(A,B)})
        self.assertEqual(result['status'],'Abweichung')
        self.assertTrue(result['partial'])
        self.assertTrue(any(d.get('changes') for d in result['details']))

    def test_all_members_still_ok(self):
        self.assertEqual(evaluate([A,B],{A:seen(A,B),B:seen(A,B)})['status'],'OK')
