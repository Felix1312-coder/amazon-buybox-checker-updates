import json,sys,types,unittest
from unittest.mock import Mock,patch
import app
from test_snapshots import SnapshotStorageTests,A,B,observation

class MonitorStopTests(SnapshotStorageTests):
 def test_stop_keeps_finished_groups_without_partial_result(self):
  with app.db() as c:c.execute('CREATE TABLE checks(id INTEGER PRIMARY KEY,family_id TEXT,name TEXT,market TEXT,at TEXT,result TEXT,observations TEXT,expected TEXT)')
  families=[{'id':'one','name':'One','market':'IT','variants':{A:''}},{'id':'two','name':'Two','market':'DE','variants':{B:''}}]
  browser=Mock();pw=Mock();pw.chromium.launch.return_value=browser
  cm=Mock();cm.__enter__=Mock(return_value=pw);cm.__exit__=Mock(return_value=False)
  fake=types.ModuleType('playwright.sync_api');fake.sync_playwright=lambda:cm
  def scan(page,market,asin):
   if asin==B:app.CHECK_STOP.set()
   return observation(asin,market,members=[asin])
  app.CHECK_STOP.clear()
  with patch.dict(sys.modules,{'playwright.sync_api':fake}),patch.object(app,'scan_page',scan):app.run(families,True)
  with app.db() as c:rows=c.execute('SELECT family_id FROM checks').fetchall()
  self.assertEqual([r[0] for r in rows],['one']);self.assertIn('Gestoppt',app.PROGRESS['text'])
  browser.new_context.assert_called_once();browser.new_context.return_value.new_page.assert_called_once()
  browser.close.assert_called_once();app.CHECK_STOP.clear()
