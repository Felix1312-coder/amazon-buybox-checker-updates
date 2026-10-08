import json,os,sqlite3,subprocess,tempfile
from pathlib import Path
import runtime
root=Path(__file__).resolve().parent
manifest=json.loads((root/'release/latest.json').read_text())
with tempfile.TemporaryDirectory() as tmp:
 data=Path(tmp)/'AmazonVariationMonitor';data.mkdir()
 with sqlite3.connect(data/'monitor.sqlite') as c:
  c.execute('CREATE TABLE families(id TEXT PRIMARY KEY,name TEXT,market TEXT,variants TEXT,UNIQUE(name,market))')
  c.execute('INSERT INTO families VALUES(?,?,?,?)',('existing','Existing Soll family','IT','{}'))
 runtime.install_bundle((root/'release'/('variation-monitor-'+manifest['version']+'.zip')).read_bytes(),manifest,data/'updates')
 output=root/'qa/frozen-compatibility.json'
 exe=root/'bootstrap/Amazon-Variation-Monitor.exe'
 subprocess.run([str(exe),'--payload-probe',str(output)],check=True,timeout=90,env={**os.environ,'LOCALAPPDATA':tmp})
 result=json.loads(output.read_text(encoding='utf8'))
 assert result['version']==manifest['version'],result
 assert result['families']==1,result
 assert result['snapshot_excel_bytes']>1000,result
 assert 'versions' in result['source'],result
 print(json.dumps(result,indent=2))
