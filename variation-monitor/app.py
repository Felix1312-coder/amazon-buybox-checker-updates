import base64, io, json, os, sqlite3, threading, time, uuid, webbrowser, sys, multiprocessing, hashlib, zipfile
import updater, runtime
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from core import parse_import, parse_manual, evaluate, scan_page, ASIN, MARKETS, parse_family, dimension_key, market_browser_options, parse_snapshot_input, collect_snapshot, SnapshotCancelled, snapshot_workbook, snapshot_comparison, snapshot_structure, snapshot_baseline

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AmazonVariationMonitor'
DATA.mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock(); PROGRESS={'running':False,'text':'Bereit'}; TOKEN=uuid.uuid4().hex
DISCOVERY={}
CHECK_STOP=threading.Event()
SNAPSHOT_ACTIVE={"id":None}; SNAPSHOT_STOP=threading.Event()

@contextmanager
def db():
    c=sqlite3.connect(DATA/'monitor.sqlite', timeout=30); c.row_factory=sqlite3.Row
    try:
        with c: yield c
    finally: c.close()
with db() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS families(id TEXT PRIMARY KEY,name TEXT,market TEXT,variants TEXT, UNIQUE(name,market));
    CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY, family_id TEXT, name TEXT, market TEXT, at TEXT, result TEXT, observations TEXT, expected TEXT);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS snapshot_jobs(id TEXT PRIMARY KEY,name TEXT,created TEXT,finished TEXT,status TEXT,markets TEXT,error TEXT);
    CREATE TABLE IF NOT EXISTS snapshot_items(job_id TEXT,market TEXT,asin TEXT,name TEXT,position INTEGER,status TEXT,at TEXT,note TEXT,found INTEGER,result TEXT,PRIMARY KEY(job_id,market,asin));''')
    c.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',('config',json.dumps({'enabled':False,'time':'09:00','visible':True,'last_day':''})))

with db() as c:c.execute("UPDATE snapshot_jobs SET status='Unterbrochen',error='App wurde während der Aufnahme geschlossen. Offene Prüfungen können fortgesetzt werden.' WHERE status='Läuft'")

def config():
    with db() as c: return json.loads(c.execute('SELECT value FROM settings WHERE key="config"').fetchone()[0])

def with_revision(f):
    f['revision']=hashlib.sha256(json.dumps([f['name'],f['market'],f['variants']],sort_keys=True).encode()).hexdigest()
    return f

def families():
    with db() as c: return [with_revision({**dict(r),'variants':json.loads(r['variants'])}) for r in c.execute('SELECT * FROM families ORDER BY name,market')]

class SharedMarketPage:
    """One context and one tab per run, with market-specific language on navigation."""
    def __init__(self,browser):
        self.context=browser.new_context(viewport={'width':1360,'height':900})
        from core import MARKET_LOCALES
        mapping={'www.amazon.'+MARKETS[m]:locale for m,locale in MARKET_LOCALES.items()}
        self.context.add_init_script("const marketLocales="+json.dumps(mapping)+"; const marketLocale=marketLocales[location.hostname]; if(marketLocale){Object.defineProperty(navigator,'language',{get:()=>marketLocale});Object.defineProperty(navigator,'languages',{get:()=>[marketLocale,marketLocale.split('-')[0]]});}")
        self.page=self.context.new_page()
    def __call__(self,market):
        self.context.set_extra_http_headers(market_browser_options(market)['extra_http_headers'])
        return self.page

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
            page_for=SharedMarketPage(browser)
            try:
                for f in items:
                    if CHECK_STOP.is_set():break
                    page=page_for(f['market'])
                    observations={}
                    for asin in f['variants']:
                        if CHECK_STOP.is_set():break
                        PROGRESS['text']=f'{done+1}/{total} · {f["name"]} · {f["market"]} · {asin}'
                        try:
                            o=scan_page(page,f['market'],asin)
                            if CHECK_STOP.is_set():break
                            provisional=evaluate(f['variants'],{asin:o})
                            if not CHECK_STOP.is_set() and (o.get('error') or o.get('language_error') or any(d['type']=='abweichung' for d in provisional['details'])):
                                page.wait_for_timeout(2000)
                                if CHECK_STOP.is_set():break
                                second=scan_page(page,f['market'],asin)
                                if o.get('valid') and second.get('valid') and (o.get('asins'),o.get('attributes')) != (second.get('asins'),second.get('attributes')):
                                    second={**second,'valid':False,'error':'Widersprüchliche Ergebnisse bei Wiederholungsprüfung.'}
                                o=second
                            observations[asin]=o
                        except Exception as e: observations[asin]={'error':str(e)[:500]}
                        done+=1
                    if CHECK_STOP.is_set():break
                    result=evaluate(f['variants'],observations)
                    with db() as c:
                        c.execute('INSERT INTO checks(family_id,name,market,at,result,observations,expected) VALUES(?,?,?,?,?,?,?)',
                          (f['id'],f['name'],f['market'],datetime.now().astimezone().isoformat(timespec='seconds'),json.dumps(result),json.dumps(observations),json.dumps(f['variants'])))
            finally: browser.close()
        PROGRESS['text']=(f'Gestoppt · {done} ASINs bearbeitet. Fertige Gruppen bleiben gespeichert; die unterbrochene Gruppe wurde nicht neu bewertet.' if CHECK_STOP.is_set() else f'Abgeschlossen · {done} ASINs geprüft')
    except Exception as e: PROGRESS['text']='Prüfung fehlgeschlagen: '+str(e)
    finally:
        with LOCK: PROGRESS['running']=False

def start(ids=None, scheduled=False):
    with LOCK:
        if PROGRESS['running']: raise ValueError('Es läuft bereits eine Prüfung.')
        items=families()
        if ids is not None: items=[f for f in items if f['id'] in ids]
        if not items: raise ValueError('Bitte zuerst Variantenfamilien importieren.')
        CHECK_STOP.clear()
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
        if path.startswith('/api/snapshot'):
            try:
                q={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()}
                if path=='/api/snapshots':return self.send({'jobs':snapshot_jobs(),'active':SNAPSHOT_ACTIVE['id']})
                if path=='/api/snapshot/template':return self.send(('\ufeffASIN;Name\r\n').encode('utf8'),'text/csv; charset=utf-8')
                if path=='/api/snapshot/comparison':
                    job,items=snapshot_data(q.get('id'))
                    return self.send(snapshot_comparison(items,json.loads(job['markets'])))
                if path=='/api/snapshot/detail':
                    with db() as c:r=c.execute('SELECT * FROM snapshot_items WHERE job_id=? AND market=? AND asin=?',(q.get('id'),q.get('market'),q.get('asin'))).fetchone()
                    if not r:raise ValueError('Ergebnis nicht gefunden.')
                    item=dict(r);item['result']=json.loads(item['result']) if item['result'] else None
                    item['structure']=snapshot_structure(item['status'],len(set((item['result'] or {}).get('asins') or [])))
                    return self.send(item)
                if path=='/api/snapshot/export':
                    content,kind=snapshot_export(q.get('id'),q.get('market',''))
                    return self.send(content,kind)
                if path=='/api/snapshot':return self.send(snapshot_page(q))
                raise ValueError('Unbekannte Ist-Aufnahme-Aktion.')
            except Exception as e:return self.send({'error':str(e)},code=400)
        if path=='/api/state':
            with db() as c:
                history=[dict(r) for r in c.execute('SELECT id,family_id,name,market,at,result FROM checks ORDER BY id DESC LIMIT 500')]
                count=c.execute('SELECT COUNT(*) FROM checks').fetchone()[0]
                latest={r['family_id']:{**json.loads(r['result']),'at':r['at']} for r in c.execute('SELECT c.family_id,c.result,c.at FROM checks c JOIN families f ON f.id=c.family_id WHERE c.id IN (SELECT MAX(id) FROM checks GROUP BY family_id) AND c.expected=f.variants AND c.market=f.market')}
            return self.send({'families':families(),'history':history,'count':count,'latest':latest,'config':config(),'progress':PROGRESS,'discovery':DISCOVERY,'updates':dict(updater.STATE),'version':updater.current_version()})
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
            if size>22_000_000: raise ValueError('Upload zu groß (max. 5 MB je Datei).')
            d=json.loads(self.rfile.read(size)); path=urlparse(self.path).path
            if path=='/api/snapshot/preview':
                parsed=snapshot_input(d)
                return self.send({'count':len(parsed['seeds']),'duplicates':parsed['duplicates'],'preview':parsed['seeds'][:12]})
            if path=='/api/snapshot/baseline':
                return self.send(adopt_snapshot(d))
            if path=='/api/snapshot/extend':
                added=extend_snapshot(d)
                return self.send({'message':f'{added} neue Prüfungen ergänzt. Vorhandene Ergebnisse bleiben erhalten.','added':added})
            if path=='/api/snapshot/start':
                ident=start_snapshot(d)
                return self.send({'id':ident,'message':'Ist-Aufnahme gestartet.'})
            if path=='/api/snapshot/resume':
                ident=start_snapshot({},resume_id=d.get('id'))
                return self.send({'id':ident,'message':'Offene Prüfungen werden fortgesetzt.'})
            if path=='/api/snapshot/stop':
                with LOCK:
                    if not d.get('id') or SNAPSHOT_ACTIVE['id']!=d['id']:raise ValueError('Diese Aufnahme läuft nicht.')
                    SNAPSHOT_STOP.set()
                return self.send({'message':'Stop angefordert. Die aktuell geöffnete Seite wird noch beendet.'})
            if path=='/api/update':
                with LOCK:
                    if PROGRESS['running']:raise ValueError('Bitte die laufende Prüfung abwarten.')
                    updater.start(DATA/'updates',bool(d.get('install')))
                return self.send({'message':'Update wird installiert.' if d.get('install') else 'Update-Prüfung gestartet.'})
            if path=='/api/shortcut':
                if sys.platform!='win32' or not getattr(sys,'frozen',False):raise ValueError('Nur in der installierten Windows-App verfügbar.')
                runtime.create_shortcuts(Path(sys.executable))
                return self.send({'message':'Desktop- und Startmenü-Verknüpfung erstellt.'})
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
            if path=='/api/stop':
                with LOCK:
                    if not PROGRESS['running']:raise ValueError('Es läuft keine Prüfung.')
                    CHECK_STOP.set();SNAPSHOT_STOP.set()
                    PROGRESS['text']='Stop angefordert – aktuelle Seitenabfrage wird noch beendet.'
                return self.send({'message':'Stop angefordert. Fertige Ergebnisse bleiben gespeichert.'})
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
        CHECK_STOP.clear()
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
                page=browser.new_context(**market_browser_options(market)).new_page()
                o=scan_page(page,market,asin)
                if CHECK_STOP.is_set():
                    PROGRESS['text']='ASIN-Test gestoppt.';return
                if o.get('error') or o.get('language_error'):o=scan_page(page,market,asin)
                if CHECK_STOP.is_set():
                    PROGRESS['text']='ASIN-Test gestoppt.';return
                DISCOVERY.update(asin=asin,market=market,observation=o)
                PROGRESS['text']='ASIN-Test fertig. Ergebnis unter „Manuell testen“.'
            finally:browser.close()
    except Exception as e:
        DISCOVERY.update(asin=asin,market=market,observation={'error':str(e)})
        PROGRESS['text']='ASIN-Test fehlgeschlagen. Details unter „Manuell testen“.'
    finally:
        with LOCK:PROGRESS['running']=False

def snapshot_input(d):
    if d.get('text','').strip():
        return parse_snapshot_input(('ASIN\n'+d['text']).encode('utf8'),'input.csv')
    try:data=base64.b64decode(d.get('data',''),validate=True)
    except Exception:raise ValueError('Ungültige Upload-Datei.')
    if len(data)>5_000_000:raise ValueError('Maximal 5 MB pro Importdatei.')
    return parse_snapshot_input(data,str(d.get('filename','')))

def snapshot_jobs():
    with db() as c:
        rows=c.execute("""SELECT j.*,COUNT(i.asin) total,
          SUM(CASE WHEN i.status!='Ausstehend' THEN 1 ELSE 0 END) done,
          SUM(CASE WHEN i.status IN ('Teilweise','Unklar') THEN 1 ELSE 0 END) unclear
          FROM snapshot_jobs j LEFT JOIN snapshot_items i ON i.job_id=j.id GROUP BY j.id ORDER BY j.created DESC,j.rowid DESC""").fetchall()
    return [{**dict(r),'markets':json.loads(r['markets'])} for r in rows]

def snapshot_page(q):
    ident=q.get('id');page=max(1,int(q.get('page',1)));market=q.get('market','');search=q.get('q','').strip()[:200]
    with db() as c:
        job=c.execute('SELECT * FROM snapshot_jobs WHERE id=?',(ident,)).fetchone()
        if not job:raise ValueError('Ist-Aufnahme nicht gefunden.')
        where='job_id=?';args=[ident]
        if market:where+=' AND market=?';args.append(market)
        if search:where+=' AND (instr(lower(asin),lower(?))>0 OR instr(lower(name),lower(?))>0)';args.extend([search,search])
        count=c.execute('SELECT COUNT(*) FROM snapshot_items WHERE '+where,args).fetchone()[0]
        rows=c.execute('SELECT job_id,market,asin,name,status,at,note,found FROM snapshot_items WHERE '+where+' ORDER BY position LIMIT 50 OFFSET ?',[*args,(page-1)*50]).fetchall()
    return {'rows':[{**dict(r),'structure':snapshot_structure(r['status'],r['found'])} for r in rows],'count':count,'page':page,'pages':max(1,(count+49)//50)}

def adopt_snapshot(d):
    with LOCK:
        if PROGRESS['running']:raise ValueError('Bitte die laufende Prüfung zuerst beenden.')
        job,items=snapshot_data(d.get('id'));stored=families()
        plan=snapshot_baseline(items,stored,bool(d.get('attributes')))
        token=hashlib.sha256(json.dumps([job,items,stored,bool(d.get('attributes'))],sort_keys=True).encode()).hexdigest()
        if not d.get('apply'):return {**plan,'token':token,'job':job['name']}
        if d.get('token')!=token:raise ValueError('Die Aufnahme oder der Soll-Zustand wurde geändert. Bitte Vorschau erneut öffnen.')
        if not plan['groups']:raise ValueError('Keine neuen sicher übernehmbaren Gruppen vorhanden.')
        schedule=d.get('daily',False);clock=d.get('time','09:00')
        if schedule:datetime.strptime(clock,'%H:%M')
        with db() as c:
            for g in plan['groups']:
                c.execute('INSERT INTO families VALUES(?,?,?,?)',(uuid.uuid4().hex,g['name'],g['market'],json.dumps(g['variants'])))
            if schedule:
                cfg=json.loads(c.execute('SELECT value FROM settings WHERE key="config"').fetchone()[0])
                cfg.update(enabled=True,time=clock)
                c.execute('UPDATE settings SET value=? WHERE key="config"',(json.dumps(cfg),))
        return {'message':f"{len(plan['groups'])} Soll-Gruppen übernommen. "+('Tägliche Prüfung aktiviert.' if schedule else 'Manuelle Prüfung und Zeitplan unter Variantenfamilien / Einstellungen verfügbar.')}

def snapshot_extra_lists(d):
    extra=d.get('market_lists') or {}
    if not isinstance(extra,dict) or any(m not in ('UK','IE') for m in extra):raise ValueError('Eigene Länderlisten sind für UK und IE möglich.')
    return {m:snapshot_input(value) for m,value in extra.items()}

def extend_snapshot(d):
    extra=snapshot_extra_lists(d)
    if not extra:raise ValueError('Bitte zuerst eine UK- oder IE-Liste hochladen.')
    ident=d.get('id');added=0
    with LOCK:
        if PROGRESS['running']:raise ValueError('Bitte den laufenden Scan fertig laufen lassen oder stoppen. Danach Länderlisten ergänzen.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            job=c.execute('SELECT * FROM snapshot_jobs WHERE id=?',(ident,)).fetchone()
            if not job:raise ValueError('Aufnahme nicht gefunden.')
            markets=json.loads(job['markets'])
            position=c.execute('SELECT COALESCE(MAX(position),-1)+1 FROM snapshot_items WHERE job_id=?',(ident,)).fetchone()[0]
            for market,parsed in extra.items():
                if market not in markets:markets.append(market)
                for seed in parsed['seeds']:
                    cursor=c.execute('INSERT OR IGNORE INTO snapshot_items VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,market,seed['asin'],seed['name'],position,'Ausstehend','','',None,None))
                    if cursor.rowcount:added+=1;position+=1
            if added:c.execute("UPDATE snapshot_jobs SET markets=?,status='Ergänzt – offene Prüfungen',finished='',error='' WHERE id=?",(json.dumps(markets),ident))
    return added

def start_snapshot(d,resume_id=None):
    if resume_id is None:
        parsed=snapshot_input(d) if d.get('data') or d.get('text') else {'seeds':[]}
        extras=snapshot_extra_lists(d);markets=d.get('markets')
        if not isinstance(markets,list) or not markets or any(m not in MARKETS for m in markets):raise ValueError('Bitte mindestens einen gültigen Marktplatz auswählen.')
        markets=list(dict.fromkeys(markets));ident=uuid.uuid4().hex
        inputs={m:extras.get(m,parsed)['seeds'] for m in markets}
        if any(not seeds for seeds in inputs.values()):raise ValueError('Für jeden ausgewählten Markt eine Hauptliste oder eigene Länderliste hochladen.')
        name=str(d.get('name') or d.get('filename') or 'Ist-Aufnahme').strip()[:200]
    else:ident=str(resume_id)
    with LOCK:
        if PROGRESS['running']:raise ValueError('Bitte die laufende Prüfung abwarten.')
        with db() as c:
            if resume_id is None:
                now=datetime.now().astimezone().isoformat(timespec='seconds')
                c.execute('INSERT INTO snapshot_jobs VALUES(?,?,?,?,?,?,?)',(ident,name,now,'','Läuft',json.dumps(markets),''))
                position=0
                for market in markets:
                    for seed in inputs[market]:
                        c.execute('INSERT INTO snapshot_items VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,market,seed['asin'],seed['name'],position,'Ausstehend','','',None,None));position+=1
            else:
                if not c.execute('SELECT 1 FROM snapshot_jobs WHERE id=?',(ident,)).fetchone():raise ValueError('Aufnahme nicht gefunden.')
                if not c.execute("SELECT 1 FROM snapshot_items WHERE job_id=? AND status='Ausstehend'",(ident,)).fetchone():raise ValueError('Keine offenen Prüfungen. Für einen neuen Ist-Zustand eine neue Aufnahme starten.')
                c.execute("UPDATE snapshot_jobs SET status='Läuft',finished='',error='' WHERE id=?",(ident,))
        SNAPSHOT_STOP.clear();SNAPSHOT_ACTIVE['id']=ident
        PROGRESS.update(running=True,text='Ist-Aufnahme: Browser wird gestartet …')
        try:threading.Thread(target=run_snapshot,args=(ident,config()['visible']),daemon=True).start()
        except Exception:
            SNAPSHOT_ACTIVE['id']=None;PROGRESS['running']=False
            with db() as c:c.execute("UPDATE snapshot_jobs SET status='Fehlgeschlagen',error='Browserstart nicht möglich. Bitte fortsetzen.' WHERE id=?",(ident,))
            raise
    return ident

def snapshot_process(ident,page_for,scanner=scan_page):
    with db() as c:
        tasks=[dict(r) for r in c.execute("SELECT market,asin,name FROM snapshot_items WHERE job_id=? AND status='Ausstehend' ORDER BY position",(ident,))]
        total=c.execute('SELECT COUNT(*) FROM snapshot_items WHERE job_id=?',(ident,)).fetchone()[0]
    done=total-len(tasks);cache={}
    for task in tasks:
        if SNAPSHOT_STOP.is_set():break
        market=task['market'];page=page_for(market)
        def read(asin):
            key=(market,asin)
            if key not in cache:
                PROGRESS['text']=f"Ist-Aufnahme · {done}/{total} Eingabe-ASINs/Märkte fertig · {market} · {task['asin']} → {asin}"
                try:
                    o=scanner(page,market,asin)
                    if o.get('error') or o.get('language_error'):
                        if SNAPSHOT_STOP.is_set():raise SnapshotCancelled()
                        o=scanner(page,market,asin)
                except SnapshotCancelled:raise
                except Exception as e:o={'error':str(e)[:1000]}
                cache[key]={**o,'at':datetime.now().astimezone().isoformat(timespec='seconds')}
            return cache[key]
        try:r=collect_snapshot(task['asin'],market,read,cancelled=SNAPSHOT_STOP.is_set)
        except SnapshotCancelled:break
        now=datetime.now().astimezone().isoformat(timespec='seconds')
        with db() as c:
            c.execute('UPDATE snapshot_items SET status=?,at=?,note=?,found=?,result=? WHERE job_id=? AND market=? AND asin=?',(r['status'],now,r['note'],len(r['asins']) if r['status']!='Unklar' else None,json.dumps(r,ensure_ascii=False),ident,market,task['asin']))
        done+=1
    return done==total

def run_snapshot(ident,visible):
    final='Fehlgeschlagen';error=''
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=None
            for channel in ['msedge','chrome',None]:
                try:browser=p.chromium.launch(channel=channel,headless=not visible);break
                except Exception:pass
            if not browser:raise RuntimeError('Bitte Microsoft Edge oder Google Chrome installieren.')
            page_for=SharedMarketPage(browser)
            try:complete=snapshot_process(ident,page_for)
            finally:browser.close()
        final='Abgeschlossen' if complete else 'Gestoppt'
    except Exception as e:error=str(e)[:1000]
    finally:
        with db() as c:c.execute('UPDATE snapshot_jobs SET status=?,finished=?,error=? WHERE id=?',(final,datetime.now().astimezone().isoformat(timespec='seconds'),error,ident))
        with LOCK:
            SNAPSHOT_ACTIVE['id']=None;PROGRESS.update(running=False,text='Ist-Aufnahme '+final.lower()+('. '+error if error else '. Ergebnisse und Excel unter „Ist-Zustand“.'))

def snapshot_data(ident):
    with db() as c:
        c.execute('BEGIN')
        r=c.execute('SELECT * FROM snapshot_jobs WHERE id=?',(ident,)).fetchone()
        if not r:raise ValueError('Ist-Aufnahme nicht gefunden.')
        job=dict(r);markets=json.loads(job['markets'])
        items=[dict(r) for r in c.execute('SELECT * FROM snapshot_items WHERE job_id=? ORDER BY position',(ident,))]
    return job,items

def snapshot_export(ident,market=''):
    job,items=snapshot_data(ident);markets=json.loads(job['markets'])
    if market and market not in markets:raise ValueError('Marktplatz gehört nicht zu dieser Aufnahme.')
    if market:return snapshot_workbook(job,items,market),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for m in markets:z.writestr('Varianten-Ist-'+m+'.xlsx',snapshot_workbook(job,items,m))
    return output.getvalue(),'application/zip'

if __name__=='__main__':
    multiprocessing.freeze_support()
    if sys.stdout is None: sys.stdout=open(os.devnull,'w')
    if sys.stderr is None: sys.stderr=open(os.devnull,'w')
    if '--payload-probe' in sys.argv:
        Path(sys.argv[sys.argv.index('--payload-probe')+1]).write_text(json.dumps({'version':updater.current_version(),'source':str(ROOT),'families':len(families()),'snapshot_excel_bytes':len(snapshot_workbook({'name':'Compatibility check','status':'Abgeschlossen','created':''},[],'IT'))}),encoding='utf8')
        raise SystemExit(0)
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
    print('Amazon Variation Monitor 0.4.0\n'+url+'\nDieses Fenster für tägliche Prüfungen geöffnet lassen. Strg+C beendet die App.')
    updater.start(DATA/'updates')
    threading.Thread(target=scheduler,daemon=True).start()
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        import webview
        webview.settings['ALLOW_DOWNLOADS']=True
        window=webview.create_window('Amazon Variation Monitor '+updater.current_version(),url,width=1360,height=920,min_size=(950,650),confirm_close=True)
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

