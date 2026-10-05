import unittest
from core import parse_import,evaluate,embedded_asins
A='B000000001'; B='B000000002'; C='B000000003'
class Tests(unittest.TestCase):
 def test_markets(self):
  r=parse_import(f'Familie;Marktplatz;ASIN;Variante\nHuggy;DE,FR;{A};Taupe\nHuggy;DE,FR;{B};Creme'.encode(),'a.csv')
  self.assertEqual(len(r),2);self.assertEqual(len(r[0]['variants']),2)
 def test_conflict(self):
  with self.assertRaises(ValueError):parse_import(f'Familie;Marktplatz;ASIN\nA;DE;{A}\nB;DE;{A}'.encode(),'a.csv')
 def test_block(self):
  r=evaluate([A,B],{A:{'error':'captcha'},B:{'valid':True,'asins':[A,B]}});self.assertEqual(r['status'],'Unklar')
 def test_missing(self):
  r=evaluate([A,B],{A:{'valid':True,'asins':[A,C]},B:{'valid':True,'asins':[B]}})
  self.assertEqual(r['status'],'Abweichung');self.assertEqual(r['details'][0]['missing'],[B]);self.assertEqual(r['details'][0]['extra'],[C])
 def test_ok_order(self):
  self.assertEqual(evaluate([A,B],{x:{'valid':True,'asins':[B,A]} for x in [A,B]})['status'],'OK')
 def test_excludes_recommendations(self):
  s='"recommendations":{"'+C+'":{}}, "asinVariationValues":{"'+A+'":{},"'+B+'":{}}'
  self.assertEqual(embedded_asins([s])[0],{A,B})
 def test_no_evidence(self):self.assertEqual(evaluate([A],{A:{'valid':False,'asins':[A]}})['status'],'Unklar')
if __name__=='__main__':unittest.main()

class DimensionsTests(unittest.TestCase):
 def test_manual_attributes(self):
  from core import parse_manual
  r=parse_manual({'name':'Huggy','market':'DE','lines':A+'; Taupe; Klassisch; M\n'+B+'; Creme; Modern; L'})
  self.assertEqual(r[0]['variants'][A]['attributes'],{'color':'Taupe','style':'Klassisch','size':'M'})
 def test_style_size_maps(self):
  from core import embedded_variants
  import json
  raw=json.dumps({'variationValues':{'style_name':['Modern','Classic'],'size_name':['S','L']},'asinVariationValues':{A:{'style_name':0,'size_name':1},B:{'style_name':1,'size_name':0}},'recommendation':C})
  r=embedded_variants([raw]);self.assertEqual(r['asins'],{A,B});self.assertEqual(r['attributes'][A],{'style':'Modern','size':'L'})
 def test_attribute_change(self):
  r=evaluate({A:{'attributes':{'style':'Modern','size':'S'}}},{A:{'valid':True,'asins':[A],'attributes':{A:{'style':'Classic','size':'S'}}}})
  self.assertEqual(r['status'],'Abweichung');self.assertEqual(r['details'][0]['changes'][0]['dimension'],'Stil')
 def test_attribute_missing_is_unclear(self):
  self.assertEqual(evaluate({A:{'attributes':{'size':'S'}}},{A:{'valid':True,'asins':[A]}})['status'],'Unklar')
 def test_empty_csv(self):
  with self.assertRaises(ValueError):parse_import(b'','x.csv')
 def test_conflicting_attributes(self):
  with self.assertRaises(ValueError):parse_import(f'Familie;Marktplatz;ASIN;Stil\nA;DE;{A};X\nA;DE;{A};Y'.encode(),'a.csv')
