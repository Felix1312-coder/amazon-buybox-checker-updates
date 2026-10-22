import io,json,unittest
from unittest.mock import Mock
from openpyxl import load_workbook
from core import scan_page,collect_snapshot,short_product,snapshot_workbook,UNREACHABLE
A='B000000001';B='B000000002'

def raw(**updates):
    return dict({'page_complete':True,'variant_controls':False,'title':'Beurer IL 11 Infrarotlampe langer Produkttitel','current':A,'blocked':False,'scripts':[],'asins':[], 'attributes':{},'dimensions':[],'labels':[],'html_language':'de-DE','nav_language':'DE'},**updates)

def page_for(*results):
    p=Mock();p.url='https://www.amazon.de/dp/'+A
    p.locator.return_value.count.return_value=0
    p.evaluate.side_effect=list(results)
    return p

class SingletonReportTests(unittest.TestCase):
    def test_complete_standalone_without_attributes(self):
        p=page_for(raw(),raw());o=scan_page(p,'DE',A)
        self.assertTrue(o['valid']);self.assertTrue(o['standalone_confirmed'])
        self.assertEqual(p.evaluate.call_count,2)
        r=collect_snapshot(A,'DE',lambda a:o)
        self.assertEqual(r['status'],'Gelesen');self.assertEqual(r['asins'],[A])

    def test_late_variants_are_not_singleton(self):
        p=page_for(raw(),raw(variant_controls=True,asins=[A,B]))
        o=scan_page(p,'DE',A)
        self.assertFalse(o['standalone_confirmed']);self.assertEqual(o['asins'],[A,B])

    def test_unreadable_controls_stay_unclear(self):
        o=scan_page(page_for(raw(variant_controls=True)),'DE',A)
        self.assertFalse(o['valid'])

    def test_incomplete_page_never_singleton(self):
        p=page_for(raw(page_complete=False),raw(page_complete=False))
        self.assertFalse(scan_page(p,'DE',A)['valid'])

    def test_block_and_wrong_asin_never_singleton(self):
        for value in (raw(blocked=True),raw(current=B),raw(title='')):
            self.assertIn('error',scan_page(page_for(value),'DE',A))

    def test_unparsed_variant_payload_never_singleton(self):
        value=raw(scripts=['"variationValues":{"style_name":["One","Two"]}'])
        self.assertFalse(scan_page(page_for(value),'DE',A)['valid'])

    def test_short_models(self):
        for title,expected in [('Beurer IL11 Infrarotlampe','IL 11'),('Beurer BM 25 Blutdruckmessgerät','BM 25'),('Beurer EM49 TENS','EM 49'),('Beurer IH 60 Yearpack','IH 60 · Zubehör')]:
            self.assertEqual(short_product(title),expected)

    def test_export_status_and_short_name_preserve_original(self):
        o=scan_page(page_for(raw(),raw()),'DE',A)
        r=collect_snapshot(A,'DE',lambda a:o)
        fail={'status':'Unklar','note':'Amazon-Seite nach 2 Ladeversuchen nicht erreichbar (ERR_FAILED).','asins':[], 'variants':[{'asin':B,'title':'','attributes':{},'status':'Unklar','note':'net::ERR_FAILED','url':'https://www.amazon.de/dp/'+B,'at':''}]}
        items=[{'asin':a,'name':'','market':'DE','status':v['status'],'note':v['note'],'result':v,'at':''} for a,v in [(A,r),(B,fail)]]
        wb=load_workbook(io.BytesIO(snapshot_workbook({'name':'Test','status':'Abgeschlossen','created':''},items,'DE')))
        self.assertEqual(wb['Varianten']['E2'].value,'IL 11')
        self.assertIn('Infrarotlampe',wb['Varianten']['E2'].comment.text)
        self.assertEqual(wb['Übersicht']['I6'].value,'Keine Variation – Einzelprodukt')
        self.assertEqual(wb['Übersicht']['D7'].value,UNREACHABLE)
        self.assertEqual(wb['Übersicht']['I7'].value,UNREACHABLE)
        self.assertEqual(wb['Variationsgruppen']['C5'].value,UNREACHABLE)
        self.assertEqual(wb['Ländervergleich']['F5'].value,UNREACHABLE)
        self.assertIn('/dp/'+A,wb['Varianten']['E2'].hyperlink.target)
        self.assertEqual(wb['Varianten']['M2'].value,'Amazon öffnen ↗')
        self.assertIn('www.amazon.de',wb['Ländervergleich']['F4'].hyperlink.target)
        self.assertIn('/dp/'+B,wb['Ländervergleich']['F5'].hyperlink.target)
        self.assertIn('/dp/'+A,wb['Variationsgruppen']['G4'].hyperlink.target)
        wb.close()
