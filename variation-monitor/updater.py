import json, threading, urllib.request
from pathlib import Path
from urllib.parse import urlparse
import runtime

CHANNEL='https://raw.githubusercontent.com/Felix1312-coder/amazon-buybox-checker-updates/variation-monitor-updates/'
LATEST=CHANNEL+'latest.json'
STATE={'busy':False,'message':'Updates werden beim Start geprüft.','available':False,'pending':False}
LOCK=threading.Lock()

def current_version():return json.loads((Path(__file__).parent/'version.json').read_text(encoding='utf8'))['version']

def fetch(url,limit):
    if not url.startswith(CHANNEL) or urlparse(url).scheme!='https':raise ValueError('Ungültige Update-Adresse.')
    req=urllib.request.Request(url,headers={'User-Agent':'AmazonVariationMonitor/1','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=25) as response:
        if not response.url.startswith(CHANNEL):raise ValueError('Update-Weiterleitung nicht erlaubt.')
        value=response.read(limit+1)
    if len(value)>limit:raise ValueError('Update überschreitet die zulässige Größe.')
    return value

def manifest():
    m=json.loads(fetch(LATEST,64000))
    runtime.version_tuple(m['version'])
    if m.get('app_id')!=runtime.APP_ID or m.get('launcher_protocol')!=runtime.PROTOCOL:
        raise ValueError('Dieses Update benötigt ein neueres Startprogramm.')
    if not isinstance(m.get('sha256'),str) or not runtime.re.fullmatch('[a-f0-9]{64}',m['sha256']):raise ValueError('Ungültige Update-Prüfsumme.')
    if not m.get('url','').startswith(CHANNEL):raise ValueError('Ungültige Update-Adresse.')
    return m

def task(root,install=False):
    try:
        m=manifest()
        available=runtime.version_tuple(m['version'])>runtime.version_tuple(current_version())
        STATE.update(available=available,version=m['version'])
        if not available:
            STATE['message']='Du verwendest die aktuelle Version '+current_version()+'.';return
        if not install:
            STATE['message']='Update '+m['version']+' verfügbar.';return
        version=runtime.install_bundle(fetch(m['url'],16*1024*1024),m,root)
        STATE.update(available=False,pending=True,message='Update '+version+' vorbereitet. App schließen und über dasselbe Desktop-Symbol neu öffnen.')
    except Exception as e:
        STATE['message']='Update nicht möglich: '+str(e)+'. Die bisherige App bleibt nutzbar.'
    finally:
        with LOCK:STATE['busy']=False

def start(root,install=False):
    with LOCK:
        if STATE['busy']:raise ValueError('Update-Prüfung läuft bereits.')
        if STATE['pending']:raise ValueError('Update ist bereit. App bitte schließen und erneut öffnen.')
        STATE.update(busy=True,message='Update wird geladen …' if install else 'Updates werden geprüft …')
    threading.Thread(target=task,args=(root,install),daemon=True).start()
