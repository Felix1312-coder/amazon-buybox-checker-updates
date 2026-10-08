import base64,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import app
from core import parse_snapshot_input,collect_snapshot,snapshot_workbook,SnapshotCancelled
A='B000000001';B='B000000002';C='B000000003'

def observation(asin,market='IT',members=None):
 return {'valid':True,'title':'Prodotto '+asin,'asins':members or [A,B], 'attributes':{asin:{'style':'Classico' if asin==A else 'Moderno','color':'Giallo','size':'50 cm'}},'url':f'https://www.amazon.it/dp/{asin}','at':'2026-10-08T12:00:00+02:00'}

class SnapshotInputTests(unittest.TestCase):
 def test_csv_duplicates_and_selected_name(self):
  r=parse_snapshot_input(f'ASIN;Name\n{A.lower()};Uno\n{A};Due\n{B};Tre\n'.encode(),'list.csv')
  self.assertEqual(r['duplicates'],1);self.assertEqual(r['seeds'],[{'asin':A,'name':'Uno'},{'asin':B,'name':'Tre'}])
 def test_invalid_row_stops_whole_import(self):
  with self.assertRaisesRegex(ValueError,'3'):parse_snapshot_input(f'ASIN\n{A}\nBAD'.encode(),'a.csv')
 def test_single_column_without_header(self):self.assertEqual(len(parse_snapshot_input(f'{A}\n{B}'.encode(),'a.csv')['seeds']),2)
 def test_xlsx_input_and_formula_value(self):
  from openpyxl import Workbook
  w=Workbook();w.active.append(['Name','ASIN']);w.active.append(['Uno',A]);b=io.BytesIO();w.save(b);w.close()
  self.assertEqual(parse_snapshot_input(b.getvalue(),'a.xlsx')['seeds'],[{'asin':A,'name':'Uno'}])
 def test_requires_asin_header(self):
  with self.assertRaisesRegex(ValueError,'ASIN'):parse_snapshot_input(b'Product;ID\nTest;B000000001','a.csv')
 def test_duplicate_asin_headers_rejected(self):
  with self.assertRaises(ValueError):parse_snapshot_input(f'ASIN;Child ASIN\n{A};{B}'.encode(),'a.csv')

class CollectionTests(unittest.TestCase):
 def test_expands_children_and_reads_own_attributes(self):
  seen=[]
  def read(a):seen.append(a);return observation(a,members=[A,B] if a==A else [A,B,C])
  r=collect_snapshot(A,'IT',read)
  self.assertEqual(seen,[A,B,C]);self.assertEqual(r['asins'],[A,B,C]);self.assertEqual(r['status'],'Gelesen')
  self.assertEqual(r['variants'][1]['attributes']['style'],'Moderno')
 def test_failure_retained_and_not_called_no_variants(self):
  r=collect_snapshot(A,'IT',lambda a:{'error':'Produkt nicht geladen'})
  self.assertEqual(r['status'],'Unklar');self.assertEqual(r['asins'],[]);self.assertEqual(r['variants'][0]['note'],'Produkt nicht geladen')
 def test_child_failure_and_wrong_language(self):
  r=collect_snapshot(A,'IT',lambda a:observation(a) if a==A else {**observation(a),'language_error':'English'})
  self.assertEqual(r['status'],'Teilweise');self.assertEqual(r['variants'][1]['attributes'],{});self.assertEqual(r['variants'][1]['status'],'Unklar')
 def test_limit_and_cancel(self):
  r=collect_snapshot(A,'IT',lambda a:observation(a,members=[A,B,C]),max_members=1)
  self.assertEqual(r['status'],'Teilweise');self.assertEqual(len(r['variants']),3);self.assertIn('Grenze',r['note'])
  with self.assertRaises(SnapshotCancelled):collect_snapshot(A,'IT',lambda a:observation(a),lambda:True)

class SnapshotStorageTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=app.DATA;app.DATA=Path(self.temp.name)
  with app.db() as c:
   c.executescript('CREATE TABLE snapshot_jobs(id TEXT PRIMARY KEY,name TEXT,created TEXT,finished TEXT,status TEXT,markets TEXT,error TEXT); CREATE TABLE snapshot_items(job_id TEXT,market TEXT,asin TEXT,name TEXT,position INTEGER,status TEXT,at TEXT,note TEXT,found INTEGER,result TEXT,PRIMARY KEY(job_id,market,asin));CREATE TABLE families(id TEXT PRIMARY KEY,name TEXT,market TEXT,variants TEXT);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);')
   c.execute('INSERT INTO families VALUES(?,?,?,?)',('existing','Soll','IT','{}'))
   c.execute('INSERT INTO settings VALUES(?,?)',('config',json.dumps({'visible':False})))
  app.PROGRESS['running']=False;app.SNAPSHOT_ACTIVE['id']=None;app.SNAPSHOT_STOP.clear()
 def tearDown(self):
  app.DATA=self.old;app.PROGRESS['running']=False;app.SNAPSHOT_ACTIVE['id']=None;app.SNAPSHOT_STOP.clear();self.temp.cleanup()
 def create(self,markets=None):
  with patch.object(app.threading,'Thread'):
   return app.start_snapshot({'filename':'list.csv','data':base64.b64encode(f'ASIN;Name\n{A};=SUM(A1:A2)\n{B};Second'.encode()).decode(),'markets':markets or ['IT','DE'],'name':'Review'})
 def test_full_matrix_cache_market_isolation_and_excel(self):
  ident=self.create();calls=[]
  def scanner(page,market,asin):calls.append((market,asin));return observation(asin,market)
  self.assertTrue(app.snapshot_process(ident,lambda m:m,scanner))
  self.assertEqual(calls,[('IT',A),('IT',B),('DE',A),('DE',B)])
  self.assertEqual(app.families()[0]['name'],'Soll');self.assertEqual(app.snapshot_jobs()[0]['done'],4)
  data,kind=app.snapshot_export(ident)
  self.assertEqual(kind,'application/zip')
  from openpyxl import load_workbook
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   self.assertEqual(set(z.namelist()),{'Varianten-Ist-IT.xlsx','Varianten-Ist-DE.xlsx'})
   for market in ('IT','DE'):
    w=load_workbook(io.BytesIO(z.read('Varianten-Ist-'+market+'.xlsx')))
    self.assertEqual(w.sheetnames,['Übersicht','Varianten'])
    self.assertEqual(w['Varianten'].max_row,3) # same family from two input ASINs deduplicates
    self.assertEqual(w['Varianten']['C2'].value,market)
    self.assertEqual(w['Varianten']['B2'].value,A+', '+B)
    self.assertEqual(w['Übersicht']['B6'].value,'=SUM(A1:A2)');self.assertEqual(w['Übersicht']['B6'].data_type,'s')
    self.assertEqual(w['Varianten']['N2'].value,'Offen');self.assertEqual(len(w['Varianten'].data_validations.dataValidation),1)
    self.assertEqual(w['Varianten'].freeze_panes,'A2');self.assertIsNotNone(w['Varianten']['M2'].hyperlink)
    w.close()
 def test_stop_retains_finished_tasks_and_resume_only_open(self):
  ident=self.create(['IT']);calls=[]
  def scanner(page,market,asin):
   calls.append(asin)
   if asin==B:app.SNAPSHOT_STOP.set()
   return observation(asin,members=[asin])
  self.assertFalse(app.snapshot_process(ident,lambda m:m,scanner));self.assertEqual(app.snapshot_jobs()[0]['done'],1)
  app.PROGRESS['running']=False
  with patch.object(app.threading,'Thread'):self.assertEqual(app.start_snapshot({},resume_id=ident),ident)
  calls=[]
  self.assertTrue(app.snapshot_process(ident,lambda m:m,lambda p,m,a:(calls.append(a) or observation(a,members=[a]))))
  self.assertEqual(calls,[B]);self.assertEqual(app.snapshot_jobs()[0]['done'],2)
 def test_pending_items_exported_without_fake_zero(self):
  ident=self.create(['IT']);data,_=app.snapshot_export(ident,'IT')
  from openpyxl import load_workbook
  w=load_workbook(io.BytesIO(data));self.assertEqual(w['Übersicht']['D6'].value,'Ausstehend');self.assertIsNone(w['Übersicht']['E6'].value);w.close()
 def test_shared_lock_and_market_validation(self):
  ident=self.create()
  with self.assertRaisesRegex(ValueError,'laufende'):self.create()
  with self.assertRaises(ValueError):app.snapshot_export(ident,'UK')
  page=app.snapshot_page({'id':ident,'market':'DE','q':B});self.assertEqual(page['count'],1)
