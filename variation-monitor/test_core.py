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

class EditorTests(unittest.TestCase):
 def test_localized_types(self):
  from core import dimension_key
  cases={'Farbe':'color','color_name':'color','Couleur':'color','Colore':'color','Kleur':'color','Kolor':'color','Färg':'color','اللون':'color','Nome stile':'style','Nombre de estilo':'style','Stijl':'style','Styl':'style','اسم النمط':'style','Größe':'size','size_name':'size','Taille':'size','Taglia':'size','Tamaño':'size','Maat':'size','Rozmiar':'size','Storlek':'size','المقاس':'size'}
  for raw,expected in cases.items():self.assertEqual(dimension_key(raw),expected,raw)
 def test_fields(self):
  from core import parse_family
  r=parse_family({'name':'A','market':'IT','variants':[{'asin':A,'attributes':[{'type':'Nome stile','value':'Classico'},{'type':'Größe','value':'50cm'}]}]})
  self.assertEqual(r['variants'][A]['attributes'],{'style':'Classico','size':'50cm'})
 def test_incomplete_field(self):
  from core import parse_family
  with self.assertRaises(ValueError):parse_family({'name':'A','market':'IT','variants':[{'asin':A,'attributes':[{'type':'color','value':''}]}]})
 def test_translated_headers(self):
  r=parse_import(f'Familie;Marktplatz;ASIN;Colore;Nome stile;Taglia\nA;IT;{A};Giallo;Classico;50 cm'.encode(),'x.csv')
  self.assertEqual(r[0]['variants'][A]['attributes'],{'color':'Giallo','style':'Classico','size':'50 cm'})
 def test_size_spacing(self):
  from core import normalize_value
  self.assertEqual(normalize_value('50 cm'),normalize_value('50cm'))
