"""Stable launcher protocol 1: per-user installation and verified source payloads."""
import base64, ctypes, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

APP_ID='amazon-variation-monitor'
PROTOCOL=1
REQUIRED={'app.py','core.py','updater.py','ui.html','templates.bundle.b64','version.json','selftest.py'}

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}',value):
        raise ValueError('Ungültige Update-Version.')
    return tuple(map(int,value.split('.')))

def validate_payload(folder):
    meta=json.loads((folder/'version.json').read_text(encoding='utf8'))
    version_tuple(meta['version'])
    if meta.get('app_id')!=APP_ID or meta.get('launcher_protocol')!=PROTOCOL:
        raise ValueError('Dieses Update benötigt eine andere Startprogramm-Version.')
    hashes=meta.get('files',{})
    if set(hashes)!=REQUIRED-{'version.json'}:raise ValueError('Unvollständiges Update.')
    for name,digest in hashes.items():
        p=folder/name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Beschädigte Update-Datei: '+name)
        if name.endswith('.py'):compile(p.read_bytes(),str(p),'exec')
    return meta

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value),encoding='utf8');os.replace(temp,path)

def install_bundle(data,manifest,root):
    version_tuple(manifest['version'])
    if manifest.get('app_id')!=APP_ID or manifest.get('launcher_protocol')!=PROTOCOL:
        raise ValueError('Update ist nicht mit dieser App kompatibel.')
    if hashlib.sha256(data).hexdigest()!=manifest.get('sha256'):
        raise ValueError('Prüfsumme des Updates stimmt nicht.')
    if len(data)>16*1024*1024:raise ValueError('Update zu groß.')
    root.mkdir(parents=True,exist_ok=True)
    import io
    with tempfile.TemporaryDirectory(dir=root,prefix='stage-') as temp:
        folder=Path(temp)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos=z.infolist()
            if len(infos)!=len(REQUIRED) or {i.filename for i in infos}!=REQUIRED:
                raise ValueError('Ungültige Dateien im Update.')
            if sum(i.file_size for i in infos)>32*1024*1024:raise ValueError('Entpacktes Update zu groß.')
            for i in infos:
                if (i.external_attr>>16)&0o170000==0o120000:raise ValueError('Verknüpfungen sind nicht erlaubt.')
                (folder/i.filename).write_bytes(z.read(i))
        meta=validate_payload(folder)
        if meta['version']!=manifest['version']:raise ValueError('Versionsangaben widersprechen sich.')
        destination=root/'versions'/(meta['version']+'-'+manifest['sha256'][:16])
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():shutil.move(str(folder),str(destination))
        validate_payload(destination)
        atomic_json(root/'active.json',{'folder':destination.name,'version':meta['version']})
    return meta['version']

def active_payload(root,fallback):
    try:
        pointer=json.loads((root/'active.json').read_text(encoding='utf8'))
        name=pointer['folder']
        if not re.fullmatch(r'\d{1,5}\.\d{1,5}\.\d{1,5}-[a-f0-9]{16}',name):raise ValueError('Ungültiger Update-Pfad.')
        chosen=root/'versions'/name
        meta=validate_payload(chosen)
        if version_tuple(meta['version'])<version_tuple(validate_payload(fallback)['version']):return fallback
        return chosen
    except Exception:
        return fallback

def create_shortcuts(executable,desktop_override=None):
    """WScript resolves the actual Desktop (including OneDrive redirection)."""
    def psquote(s):return "'"+str(s).replace("'","''")+"'"
    target=psquote(executable)
    desktop=psquote(desktop_override) if desktop_override else "$w.SpecialFolders.Item('Desktop')"
    script=f'''$ErrorActionPreference='Stop'
$w=New-Object -ComObject WScript.Shell
$desktop={desktop}
$folders=@($desktop)
'''
    if not desktop_override:script+="$folders+=Join-Path $w.SpecialFolders.Item('Programs') 'Amazon Variation Monitor'\n"
    script+=f'''foreach($folder in $folders) {{
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$s=$w.CreateShortcut((Join-Path $folder 'Amazon Variation Monitor.lnk'))
$s.TargetPath={target}
$s.WorkingDirectory=Split-Path {target}
$s.IconLocation={target}+',0'
$s.Description='Amazon Variantenfamilien überwachen'
$s.Save()
}}
'''
    encoded=base64.b64encode(script.encode('utf-16le')).decode('ascii')
    subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],check=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)

def install_launcher():
    if sys.platform!='win32' or not getattr(sys,'frozen',False):return
    target=Path(os.environ['LOCALAPPDATA'])/'Programs'/'AmazonVariationMonitor'/'Amazon-Variation-Monitor.exe'
    source=Path(sys.executable)
    if source.resolve()!=target.resolve():
        target.parent.mkdir(parents=True,exist_ok=True)
        try:
            shutil.copy2(source,target.with_suffix('.new'))
            os.replace(target.with_suffix('.new'),target)
        except PermissionError:
            ctypes.windll.user32.MessageBoxW(0,'Bitte die bereits laufende App schließen und diese Datei erneut starten.','Variation Monitor',0)
            raise SystemExit(0)
        try:create_shortcuts(target)
        except Exception:
            ctypes.windll.user32.MessageBoxW(0,'Die App wurde installiert. Die Desktop-Verknüpfung konnte nicht erstellt werden. In Einstellungen bitte erneut versuchen.','Variation Monitor',0)
        subprocess.Popen([str(target)],cwd=target.parent)
        raise SystemExit(0)
    # Repair a removed shortcut on every explicit start; failures do not block the app.
    try:create_shortcuts(target)
    except Exception:pass
