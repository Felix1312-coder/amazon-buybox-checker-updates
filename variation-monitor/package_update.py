"""Build deterministic bundle and launcher payload from the same source."""
import hashlib, json, shutil, zipfile
from pathlib import Path
import runtime
VERSION='0.5.6'
ROOT=Path(__file__).parent
OUT=ROOT/'release';OUT.mkdir(exist_ok=True)
meta={'app_id':runtime.APP_ID,'version':VERSION,'launcher_protocol':runtime.PROTOCOL,'files':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(runtime.REQUIRED-{'version.json'})}}
(ROOT/'version.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
payload=ROOT/'payload';payload.mkdir(exist_ok=True)
for name in runtime.REQUIRED:shutil.copy2(ROOT/name,payload/name)
bundle=OUT/f'variation-monitor-{VERSION}.zip'
with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
    for name in sorted(runtime.REQUIRED):
        info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,(ROOT/name).read_bytes())
manifest={'app_id':runtime.APP_ID,'version':VERSION,'launcher_protocol':runtime.PROTOCOL,'url':f'https://raw.githubusercontent.com/Felix1312-coder/amazon-buybox-checker-updates/variation-monitor-updates/{bundle.name}','sha256':hashlib.sha256(bundle.read_bytes()).hexdigest()}
(OUT/'latest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
print(json.dumps({'bundle':str(bundle),'manifest':str(OUT/'latest.json'),'sha256':manifest['sha256']}))

