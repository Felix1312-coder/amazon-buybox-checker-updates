import base64, io, json, os, sqlite3, threading, time, uuid, webbrowser, sys, multiprocessing, hashlib, zipfile
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core import parse_import, parse_manual, evaluate, scan_page, ASIN, MARKETS, parse_family, dimension_key

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AmazonVariationMonitor'
DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock(); PROGRESS={'running':False,'text':'Bereit'}; TOKEN=uuid.uuid4().hex
DISCOVERY={}

def db():
    c=sqlite3.connect(DATA/'monitor.sqlite', timeout=30); c.row_factory=sqlite3.Row; return c
with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS families(id TEXT PRIMARY KEY,name TEXT,market TEXT,variants TEXT, UNIQUE(name,market));
    CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, family_id TEXT, name TEXT, market TEXT, at TEXT, result TEXT, observations TEXT, expected TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''')
    c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('config',json.dumps({'enabled':False,'time':'09:00','visible':True,'last_day':''})))

def config():
    with db() as c: return json.loads(c.execute('SELECT value FROM settings WHERE key="config"').fetchone()[0])

def with_revision(f):
    f['revision']=hashlib.sha256(json.dumps([f['name'],f['market'],f['variants']],sort_keys=True).encode()).hexdigest()
    return f

def families():
    with db() as c: return [with_revision({**dict(r),'variants':json.loads(r['variants'])}) for r in c.execute('SELECT * FROM families ORDER BY name,market')]

def run(items, visible):
    try:
        from playwright.sync_api import sync_playwright
        total=sum(len(f['variants']) for f in items); done=0
        with sync_playwright() as p:
            browser=None
            for channel in ['msedge','chrome',None]:
                try:
                    browser=p.chromium.launch(channel=channel,headless=not visible); break
                except Exception: pass
            if not browser: raise RuntimeError('Kein Browser verfügbar. Bitte Microsoft Edge oder Google Chrome installieren.')
            context=browser.new_context(viewport={'width':1360,'height':900})
            page=context.new_page()
            try:
                for f in items:
                    observations={}
                    for asin in f['variants']:
                        PROGRESS['text']=f'{done+1}/{total} · {f["name"]} · {f["market"]} · {asin}'
                        try:
                            o=scan_page(page,f['market'],asin)
                            provisional=evaluate(f['variants'],{asin:o})
                            if o.get('error') or any(d['type']=='abweichung' for d in provisional['details']):
                                page.wait_for_timeout(2000)
                                second=scan_page(page,f['market'],asin)
                                if o.get('valid') and second.get('valid') and (o.get('asins'),o.get('attributes')) != (second.get('asins'),second.get('attributes')):
                                    second={**second,'valid':False,'error':'Widersprüchliche Ergebnisse bei Wiederholungsprüfung.'}
                                o=second
                            observations[asin]=o
                        except Exception as e: observations[asin]={'error':str(e)[:500]}
                        done+=1
                    result=evaluate(f['variants'],observations)
                    with db() as c:
                        c.execute('INSERT INTO checks(family_id,name,market,at,result,observations,expected) VALUES(?,?,?,?,?,?,?)',
                          (f['id'],f['name'],f['market'],datetime.now().astimezone().isoformat(timespec='seconds'),json.dumps(result),json.dumps(observations),json.dumps(f['variants'])))
            finally: browser.close()
        PROGRESS['text']=f'Abgeschlossen · {done} ASINs geprüft'
    except Exception as e: PROGRESS['text']='Prüfung fehlgeschlagen: '+str(e)
    finally:
        with LOCK: PROGRESS['running']=False

def start(ids=None, scheduled=False):
    with LOCK:
        if PROGRESS['running']: raise ValueError('Es läuft bereits eine Prüfung.')
        items=families()
        if ids is not None: items=[f for f in items if f['id'] in ids]
        if not items: raise ValueError('Bitte zuerst Variantenfamilien importieren.')
        cfg=config(); PROGRESS.update(running=True,text='Browser wird gestartet …')
        if scheduled:
            cfg['last_day']=datetime.now().date().isoformat()
            with db() as c: c.execute('UPDATE settings SET value=? WHERE key="config"',(json.dumps(cfg),))
        threading.Thread(target=run,args=(items,cfg['visible']),daemon=True).start()

def scheduler():
    while True:
        try:
            cfg=config(); now=datetime.now()
            if cfg['enabled'] and now.strftime('%H:%M')>=cfg['time'] and cfg['last_day']!=now.date().isoformat() and families(): start(scheduled=True)
        except Exception: pass
        time.sleep(15)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,data,kind='application/json',code=200):
        if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(code); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'): return self.send({'error':'Host ungültig'},code=403)
        path=urlparse(self.path).path
        if path=='/': return self.send((ROOT/'ui.html').read_text(encoding='utf8').replace('__TOKEN__',TOKEN).encode(),'text/html; charset=utf-8')
        if self.headers.get('X-Token')!=TOKEN: return self.send({'error':'Zugriff abgelehnt'},code=403)
        if path=='/api/state':
            with db() as c:
                history=[dict(r) for r in c.execute('SELECT id,family_id,name,market,at,result FROM checks ORDER BY id DESC LIMIT 500')]
                count=c.execute('SELECT COUNT(*) FROM checks').fetchone()[0]
                latest={r['family_id']:json.loads(r['result']) for r in c.execute('SELECT c.family_id,c.result FROM checks c JOIN families f ON f.id=c.family_id WHERE c.id IN (SELECT MAX(id) FROM checks GROUP BY family_id) AND c.expected=f.variants AND c.market=f.market')}
            return self.send({'families':families(),'history':history,'count':count,'latest':latest,'config':config(),'progress':PROGRESS,'discovery':DISCOVERY})
        if path=='/api/export':
            with db() as c:
                rows=[dict(r) for r in c.execute('SELECT * FROM checks ORDER BY id')]
            return self.send(rows)
        if path=='/api/template':
            query=parse_qs(urlparse(self.path).query,keep_blank_values=True)
            dims=[dimension_key(x) for x in query.get('dims',[''])[0].split(',') if x.strip()]
            if any(x not in ('color','style','size') for x in dims):return self.send({'error':'Ungültige Merkmalsauswahl.'},code=400)
            mask=sum(1<<i for i,k in enumerate(('color','style','size')) if k in dims)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode((ROOT/'templates.bundle.b64').read_bytes()))) as z:
                content=z.read(f'template-{mask}.xlsx')
            return self.send(content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        return self.send({'error':'Nicht gefunden'},code=404)
    def do_POST(self):
        if self.headers.get('X-Token')!=TOKEN: return self.send({'error':'Zugriff abgelehnt'},code=403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>8_000_000: raise ValueError('Datei zu groß (max. ca. 5 MB).')
            d=json.loads(self.rfile.read(size)); path=urlparse(self.path).path
            if path=='/api/import':
                groups=parse_import(base64.b64decode(d['data']),d['filename'])
                save_groups(groups)
                return self.send({'message':f'{len(groups)} Familien/Marktplätze importiert.'})
            if path=='/api/family':
                family=parse_family(d)
                ids=save_groups([family],edit_id=d.get('id'),revision=d.get('revision'))
                if d.get('run'):start(ids)
                return self.send({'message':'Änderungen gespeichert.' if d.get('id') else 'Familie gespeichert.','id':ids[0]})
            if path=='/api/manual':
                ids=save_groups(parse_manual(d))
                if d.get('run'): start(ids)
                return self.send({'message':'Familie gespeichert.'+(' Prüfung gestartet.' if d.get('run') else '')})
            if path=='/api/discover':
                start_discovery(d)
                return self.send({'message':'ASIN-Test gestartet.'})
            if path=='/api/run': start(d.get('ids')); return self.send({'message':'Prüfung gestartet.'})
            if path=='/api/config':
                datetime.strptime(d['time'],'%H:%M')
                with LOCK:
                    cfg=config(); cfg.update(time=d['time'],enabled=bool(d['enabled']),visible=bool(d['visible']))
                    with db() as c: c.execute('UPDATE settings SET value=? WHERE key="config"',(json.dumps(cfg),))
                return self.send({'message':'Zeitplan gespeichert.'})
            if path=='/api/delete':
                with LOCK:
                    if PROGRESS['running']: raise ValueError('Laufende Prüfung zuerst abwarten.')
                    with db() as c: c.execute('DELETE FROM families WHERE id=?',(d['id'],))
                return self.send({'message':'Familie entfernt. Historie bleibt erhalten.'})
            raise ValueError('Unbekannte Aktion.')
        except Exception as e: self.send({'error':str(e)},code=400)

def save_groups(groups,edit_id=None,revision=None):
    with LOCK:
        if PROGRESS['running']: raise ValueError('Bitte die laufende Prüfung abwarten.')
        stored=families();incoming={(g['name'],g['market']) for g in groups}
        if edit_id:
            old=next((f for f in stored if f['id']==edit_id),None)
            if not old:raise ValueError('Diese Familie wurde inzwischen entfernt. Bitte Ansicht aktualisieren.')
            if revision!=old['revision']:raise ValueError('Die Familie wurde inzwischen geändert. Bitte Bearbeiten erneut öffnen.')
            if len(groups)!=1:raise ValueError('Bitte genau eine Familie bearbeiten.')
            if any(f['id']!=edit_id and (f['name'],f['market']) in incoming for f in stored):
                raise ValueError('Eine andere Familie mit diesem Namen und Markt existiert bereits.')
        owners={(g['market'],a):g['name'] for g in stored if g['id']!=edit_id and (g['name'],g['market']) not in incoming for a in g['variants']}
        for g in groups:
            for asin in g['variants']:
                if (g['market'],asin) in owners: raise ValueError(f'{asin} ist in {g["market"]} bereits der Familie {owners[(g["market"],asin)]} zugeordnet.')
        ids=[]
        with db() as c:
            for g in groups:
                if edit_id:
                    c.execute('UPDATE families SET name=?,market=?,variants=? WHERE id=?',
                        (g['name'],g['market'],json.dumps(g['variants']),edit_id))
                    ids.append(edit_id)
                else:
                    c.execute('INSERT INTO families VALUES(?,?,?,?) ON CONFLICT(name,market) DO UPDATE SET variants=excluded.variants',
                        (uuid.uuid4().hex,g['name'],g['market'],json.dumps(g['variants'])))
                    ids.append(c.execute('SELECT id FROM families WHERE name=? AND market=?',(g['name'],g['market'])).fetchone()[0])
        return ids

def start_discovery(d):
    asin=str(d.get('asin') or '').strip().upper();market=str(d.get('market') or '').upper()
    if not ASIN.fullmatch(asin) or market not in MARKETS: raise ValueError('Bitte gültige ASIN und Marktplatz eingeben.')
    with LOCK:
        if PROGRESS['running']:raise ValueError('Es läuft bereits eine Prüfung.')
        PROGRESS.update(running=True,text=f'ASIN-Test · {market} · {asin}')
        DISCOVERY.clear()
        threading.Thread(target=discover,args=(asin,market,config()['visible']),daemon=True).start()

def discover(asin,market,visible):
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=None
            for channel in ['msedge','chrome',None]:
                try:browser=p.chromium.launch(channel=channel,headless=not visible);break
                except Exception:pass
            if not browser:raise RuntimeError('Bitte Microsoft Edge oder Google Chrome installieren.')
            try:
                page=browser.new_page(viewport={'width':1360,'height':900})
                o=scan_page(page,market,asin)
                if o.get('error'):o=scan_page(page,market,asin)
                DISCOVERY.update(asin=asin,market=market,observation=o)
                PROGRESS['text']='ASIN-Test fertig. Ergebnis unter „Manuell testen“.'
            finally:browser.close()
    except Exception as e:
        DISCOVERY.update(asin=asin,market=market,observation={'error':str(e)})
        PROGRESS['text']='ASIN-Test fehlgeschlagen. Details unter „Manuell testen“.'
    finally:
        with LOCK:PROGRESS['running']=False

if __name__=='__main__':
    multiprocessing.freeze_support()
    if sys.stdout is None: sys.stdout=open(os.devnull,'w')
    if sys.stderr is None: sys.stderr=open(os.devnull,'w')
    if '--self-test' in sys.argv:
        import selftest
        selftest.run(sys.modules[__name__],sys.argv[sys.argv.index('--self-test')+1])
        raise SystemExit(0)
    if sys.platform=='win32':
        import ctypes
        instance_mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\AmazonVariationMonitorStandalone')
        if ctypes.windll.kernel32.GetLastError()==183:
            ctypes.windll.user32.MessageBoxW(0,'Die App läuft bereits. Bitte das vorhandene Fenster öffnen.','Variation Monitor',0)
            raise SystemExit(0)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    print('Amazon Variation Monitor 0.3.0\n'+url+'\nDieses Fenster für tägliche Prüfungen geöffnet lassen. Strg+C beendet die App.')
    threading.Thread(target=scheduler,daemon=True).start()
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        import webview
        webview.settings['ALLOW_DOWNLOADS']=True
        window=webview.create_window('Amazon Variation Monitor 0.3.0',url,width=1360,height=920,min_size=(950,650),confirm_close=True)
        webview.start(gui='edgechromium' if sys.platform=='win32' else None)
    except Exception as e:
        # A browser fallback keeps the app usable if WebView2 is absent.
        webbrowser.open(url)
        import tkinter as tk
        root=tk.Tk();root.title('Variation Monitor läuft');root.geometry('490x180')
        tk.Label(root,text='Die App ist im Browser geöffnet.\nDieses Fenster für automatische Prüfungen geöffnet lassen.',padx=20,pady=25).pack()
        tk.Button(root,text='App erneut öffnen',command=lambda:webbrowser.open(url)).pack()
        root.mainloop()
    finally:server.shutdown()
