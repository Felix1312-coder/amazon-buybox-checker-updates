import unittest,tempfile,json,io,base64,zipfile
from pathlib import Path
import app
from core import parse_family

class StorageTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=app.DATA;app.DATA=Path(self.tmp.name)
  with app.db() as c:
   c.executescript('CREATE TABLE families(id TEXT PRIMARY KEY,name TEXT,market TEXT,variants TEXT, UNIQUE(name,market)); CREATE TABLE checks(id INTEGER PRIMARY KEY,family_id TEXT,name TEXT,market TEXT,at TEXT,result TEXT,observations TEXT,expected TEXT);')
 def tearDown(self):app.DATA=self.old;self.tmp.cleanup()
 def family(self,name='Test',market='IT',asin='B000000001'):
  return parse_family({'name':name,'market':market,'variants':[{'asin':asin,'attributes':[{'type':'style','value':'Classico'}]}]})
 def test_edit_keeps_id_history_and_checks_stale_edits(self):
  ident=app.save_groups([self.family()])[0];old=app.families()[0]
  with app.db() as c:c.execute('INSERT INTO checks(family_id,name,market,at,result,observations,expected) VALUES(?,?,?,?,?,?,?)',(ident,'Test','IT','2026-10-05','{}','{}',json.dumps(old['variants'])))
  new=self.family('Renamed','DE','B000000002')
  self.assertEqual(app.save_groups([new],edit_id=ident,revision=old['revision']),[ident])
  f=app.families()[0];self.assertEqual(f['id'],ident);self.assertEqual(f['name'],'Renamed');self.assertIn('B000000002',f['variants'])
  with app.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM checks').fetchone()[0],1)
  with self.assertRaises(ValueError):app.save_groups([new],edit_id=ident,revision=old['revision'])
 def test_edit_name_collision(self):
  a=app.save_groups([self.family('A')])[0];app.save_groups([self.family('B',asin='B000000002')]);f=next(x for x in app.families() if x['id']==a)
  with self.assertRaises(ValueError):app.save_groups([self.family('B')],edit_id=a,revision=f['revision'])
  self.assertEqual(len(app.families()),2)
 def test_templates_all_combinations(self):
  from openpyxl import load_workbook
  with zipfile.ZipFile(io.BytesIO(base64.b64decode((app.ROOT/'templates.bundle.b64').read_bytes()))) as z:
   for i in range(8):
    w=load_workbook(io.BytesIO(z.read(f'template-{i}.xlsx')),read_only=True)
    self.assertEqual(list(next(w['Varianten'].values)),['Familie','Marktplatz','ASIN']+[k for j,k in enumerate(['Farbe','Stil','Größe']) if i&(1<<j)])
    w.close()
