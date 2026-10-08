import json,unittest
import app
from core import accepted_deviation_groups,evaluate
from test_snapshots import SnapshotStorageTests,A,B,C,observation

class AcceptDeviationTests(SnapshotStorageTests):
 def prepare(self,observations=None,expected=None):
  expected=expected or {A:'Product A',B:'Product B'}
  observations=observations or {A:observation(A,members=[A]),B:observation(B,members=[B])}
  with app.db() as c:
   c.execute('CREATE TABLE checks(id INTEGER PRIMARY KEY,family_id TEXT,name TEXT,market TEXT,at TEXT,result TEXT,observations TEXT,expected TEXT)')
   c.execute('UPDATE families SET variants=? WHERE id=?',(json.dumps(expected),'existing'))
   c.execute('INSERT INTO checks(family_id,name,market,at,result,observations,expected) VALUES(?,?,?,?,?,?,?)',('existing','Soll','IT','2026-10-08T16:00:00+02:00',json.dumps(evaluate(expected,observations)),json.dumps(observations),json.dumps(expected)))
 def test_accept_split_keeps_history_and_every_product(self):
  self.prepare();plan=app.accept_deviation({'id':'existing'})
  self.assertEqual(len(plan['groups']),2)
  app.accept_deviation({'id':'existing','apply':True,'token':plan['token']})
  groups=app.families();self.assertEqual(len(groups),2);self.assertEqual({a for g in groups for a in g['variants']},{A,B})
  self.assertEqual([len(g['variants']) for g in groups],[1,1])
  with app.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM checks').fetchone()[0],1)
  with self.assertRaises(ValueError):app.accept_deviation({'id':'existing','apply':True,'token':plan['token']})
 def test_extra_asin_is_shown_and_kept(self):
  self.prepare({A:observation(A,members=[A,B,C]),B:observation(B,members=[A,B,C])})
  plan=app.accept_deviation({'id':'existing'});self.assertEqual(len(plan['groups']),1)
  self.assertIn(C,plan['groups'][0]['variants']);self.assertTrue(plan['notes'])
 def test_unclear_and_overlap_rejected(self):
  self.prepare({A:observation(A,members=[A,B]),B:observation(B,members=[B])})
  with self.assertRaisesRegex(ValueError,'überlappende'):app.accept_deviation({'id':'existing'})
  with app.db() as c:c.execute('UPDATE checks SET result=?',(json.dumps({'status':'Abweichung','partial':True}),))
  with self.assertRaisesRegex(ValueError,'vollständig'):app.accept_deviation({'id':'existing'})
 def test_other_family_conflict_and_stale_preview(self):
  self.prepare();plan=app.accept_deviation({'id':'existing'})
  with app.db() as c:c.execute('UPDATE families SET name=? WHERE id=?',('Renamed','existing'))
  with self.assertRaisesRegex(ValueError,'geändert'):app.accept_deviation({'id':'existing','apply':True,'token':plan['token']})
  f=app.families()[0]
  with self.assertRaisesRegex(ValueError,'bereits'):accepted_deviation_groups(f,{A:observation(A,members=[A,C]),B:observation(B,members=[B])},[f,{'id':'other','name':'Other','market':'IT','variants':{C:''}}])
 def test_changed_attributes_follow_existing_rules(self):
  expected={A:{'label':'Product','attributes':{'style':'Old'}}}
  self.prepare({A:observation(A,members=[A])},expected)
  plan=app.accept_deviation({'id':'existing'});self.assertEqual(plan['groups'][0]['variants'][A]['attributes'],{'style':'Classico'})
