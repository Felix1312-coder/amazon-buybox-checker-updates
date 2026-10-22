import unittest,io
from openpyxl import load_workbook
from core import parse_rating,collect_snapshot,snapshot_workbook
A='B000000001'

class RatingTests(unittest.TestCase):
 def test_localized_stars_and_counts(self):
  for stars,count in [('4,0 sur 5 étoiles','9 456 évaluations'),('4.0 out of 5 stars','9,456 ratings'),('4,0 von 5 Sternen','9.456 Bewertungen'),('4,0 su 5 stelle','9\u202f456 valutazioni')]:
   r=parse_rating({'rating_text':stars,'rating_count_text':count})
   self.assertEqual(r['stars'],4.0);self.assertEqual(r['count'],9456)
 def test_unknown_never_zero_and_abbreviated_not_guessed(self):
  self.assertIsNone(parse_rating({})['stars']);self.assertIsNone(parse_rating({})['count'])
  self.assertIsNone(parse_rating({'rating_count_text':'9.4K ratings'})['count'])
  self.assertEqual(parse_rating({'rating_count_text':'0 ratings'})['count'],0)
 def test_saved_rating_reaches_excel_numeric_columns(self):
  rating=parse_rating({'rating_text':'4,0 sur 5','rating_count_text':'9 456'})
  result=collect_snapshot(A,'FR',lambda a:{'valid':True,'asins':[A],'title':'Beurer IL 11','attributes':{},'rating':rating})
  self.assertEqual(result['variants'][0]['rating'],rating)
  item={'asin':A,'name':'','market':'FR','status':result['status'],'note':result['note'],'result':result,'at':''}
  wb=load_workbook(io.BytesIO(snapshot_workbook({'name':'Rating','status':'Abgeschlossen','created':''},[item],'FR')))
  self.assertEqual(wb['Varianten']['Q2'].value,4)
  self.assertEqual(wb['Varianten']['R2'].value,9456)
  self.assertEqual(wb['Übersicht']['J6'].value,4)
  self.assertEqual(wb['Übersicht']['K6'].value,9456)
  self.assertIn('9.456 Bewertungen',wb['Variationsgruppen']['G4'].value)
  self.assertIn('4,0 ★',wb['Ländervergleich']['F4'].value)
  wb.close()
