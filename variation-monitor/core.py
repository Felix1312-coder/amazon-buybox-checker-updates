import re, json, csv, io, unicodedata
from collections import defaultdict

MARKETS = {'DE':'de','FR':'fr','IT':'it','ES':'es','UK':'co.uk','IE':'ie','NL':'nl','PL':'pl','SE':'se','BE':'com.be','AE':'ae'}
MARKET_LOCALES={'DE':'de-DE','FR':'fr-FR','IT':'it-IT','ES':'es-ES','UK':'en-GB','IE':'en-IE','NL':'nl-NL','PL':'pl-PL','SE':'sv-SE','BE':'fr-BE','AE':'en-AE'}

def market_browser_options(market):
    locale=MARKET_LOCALES[market]
    return {'viewport':{'width':1360,'height':900},'locale':locale,
            'extra_http_headers':{'Accept-Language':locale+','+locale.split('-')[0]+';q=0.9'}}

def market_product_url(market,asin):
    return f'https://www.amazon.{MARKETS[market]}/dp/{asin}?language={MARKET_LOCALES[market].replace("-","_")}'

def page_language_error(raw,market):
    expected=MARKET_LOCALES[market].split('-')[0]
    signals=[raw.get('html_language',''),raw.get('nav_language','')]
    detected=[]
    for value in signals:
        value=str(value).strip().lower().replace('_','-')
        if re.fullmatch(r'[a-z]{2}(?:-[a-z]{2})?',value):detected.append(value.split('-')[0])
    if any(value!=expected for value in detected):
        return f'Amazon-Seitensprache stimmt nicht: erwartet {expected.upper()}, erkannt {", ".join(sorted(set(detected))).upper()}. Merkmalswerte werden nicht sprachübergreifend verglichen.'
    if not detected:return 'Amazon-Seitensprache nicht sicher erkannt. Merkmalsvergleich daher unklar.'
    return ''

ASIN = re.compile(r'^[A-Z0-9]{10}$')

def parse_import(data, filename):
    if filename.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        rows = list(wb.active.values); wb.close()
    elif filename.lower().endswith('.csv'):
        s = data.decode('utf-8-sig')
        if not s.strip(): raise ValueError('Die Datei ist leer.')
        rows = list(csv.reader(io.StringIO(s), delimiter=';' if s.splitlines()[0].count(';') > s.splitlines()[0].count(',') else ','))
    else: raise ValueError('Bitte XLSX oder CSV importieren.')
    if not rows: raise ValueError('Die Datei ist leer.')
    headers = [str(x or '').strip().lower() for x in rows[0]]
    meaningful=[x for x in headers if x]
    if len(meaningful)!=len(set(meaningful)):raise ValueError('Doppelte Spaltenüberschriften bitte entfernen.')
    required = ['familie','marktplatz','asin']
    if any(x not in headers for x in required): raise ValueError('Pflichtspalten: Familie, Marktplatz, ASIN. Optional: Variante.')
    groups = defaultdict(dict); owner = {}
    for n, row in enumerate(rows[1:],2):
        if not any(x is not None and str(x).strip() for x in row): continue
        d = dict(zip(headers,row)); family = str(d.get('familie') or '').strip(); asin = str(d.get('asin') or '').strip().upper()
        markets = re.split(r'[,; /]+', str(d.get('marktplatz') or '').strip().upper())
        for market in markets:
            if market == 'UAE': market = 'AE'
            if market == 'GB': market = 'UK'
            if not family or not ASIN.fullmatch(asin) or market not in MARKETS: raise ValueError(f'Zeile {n}: Familie, ASIN oder Marktplatz ungültig.')
            key = (market,asin)
            if key in owner and owner[key] != family: raise ValueError(f'Zeile {n}: {asin} ist in {market} mehreren Familien zugeordnet.')
            owner[key] = family
            label = str(d.get('variante') or '').strip()
            if asin in groups[(family,market)] and variant_label(groups[(family,market)][asin]) != label: raise ValueError(f'Zeile {n}: widersprüchliche Variantenbezeichnung.')
            attrs={}
            for header,raw in d.items():
                dim=dimension_key(header)
                if dim in DIMENSION_NAMES and raw is not None and str(raw).strip():
                    value=str(raw).strip()
                    if dim in attrs and attrs[dim]!=value:raise ValueError(f'Zeile {n}: widersprüchliche Spalten für {DIMENSION_NAMES[dim]}.')
                    attrs[dim]=value
            value={'label':label,'attributes':attrs} if attrs else label
            if asin in groups[(family,market)] and groups[(family,market)][asin] != value: raise ValueError(f'Zeile {n}: widersprüchliche Merkmale.')
            groups[(family,market)][asin] = value
    if not groups: raise ValueError('Keine Produkte gefunden.')
    return [{'name': f, 'market':m, 'variants':v} for (f,m),v in groups.items()]

def embedded_asins(scripts):
    found = set(); source = False
    for script in scripts:
        for match in re.finditer(r'["\'](?:asinVariationValues|dimensionToAsinMap)["\']\s*:\s*',script):
            try: obj, _ = json.JSONDecoder().raw_decode(script[match.end():])
            except (ValueError, TypeError): continue
            if not isinstance(obj,dict): continue
            vals = list(obj.keys()) + [x for x in obj.values() if isinstance(x,str)]
            ids = {x for x in vals if ASIN.fullmatch(x)}
            if ids: found |= ids; source = True
    return found, source

def evaluate(expected, observations):
    expected_map=expected if isinstance(expected,dict) else {}
    expected = set(expected); details=[]; uncertain=False; deviations=False
    for asin in sorted(expected):
        o = observations.get(asin,{})
        if o.get('error') or not o.get('valid'):
            uncertain=True; details.append({'asin':asin,'type':'unklar','text':o.get('error') or 'Keine verwertbaren Variantendaten.'}); continue
        seen = set(o.get('asins',[])); missing = expected-seen; extra = seen-expected
        changes=[]; unknown=[]
        actual=o.get('attributes',{}).get(asin,{})
        language_issue=o.get('language_error') if expected_attributes(expected_map.get(asin)) else ''
        if language_issue:
            uncertain=True
            if missing or extra:
                deviations=True
                details.append({'asin':asin,'type':'abweichung','missing':sorted(missing),'extra':sorted(extra),'changes':[],'text':'ASIN-Verknüpfung weicht ab. '+language_issue})
            else:details.append({'asin':asin,'type':'unklar','text':language_issue})
            continue
        for key,wanted in expected_attributes(expected_map.get(asin)).items():
            if key not in actual: unknown.append(DIMENSION_NAMES.get(key,key))
            elif normalize_value(wanted)!=normalize_value(actual[key]): changes.append({'dimension':DIMENSION_NAMES.get(key,key),'expected':wanted,'actual':actual[key]})
        if missing or extra or changes:
            deviations=True
            details.append({'asin':asin,'type':'abweichung','missing':sorted(missing),'extra':sorted(extra),'changes':changes,'text':'Verknüpfung oder Merkmalswert weicht vom Soll ab.'})
        elif unknown:
            uncertain=True; details.append({'asin':asin,'type':'unklar','text':'Soll-Merkmale nicht auslesbar: '+', '.join(unknown)})
        else: details.append({'asin':asin,'type':'ok','text':'Alle erwarteten Varianten gefunden.'})
    status = 'Abweichung' if deviations else ('Unklar' if uncertain else 'OK')
    return {'status':status,'partial':uncertain,'details':details}

# Only variant-specific containers are read; recommendation ASINs are excluded.
EXTRACT = r'''() => {
 const scopes = [...document.querySelectorAll('#twister, #twister_feature_div, #twister-plus-inline-twister, [id^="variation_"], [id^="inline-twister-row-"]')];
 const ids = new Set(), attributes={}, dimensions=[];
 for(const root of document.querySelectorAll('[id^="variation_"]')) {
   const key=root.id.replace(/^variation_/, '');
   const selected=root.querySelector('.selection') || root.querySelector('select option:checked');
   const val=selected?.textContent.trim();
   dimensions.push(key);
   if(val)attributes[key]=val;
   const label=root.querySelector('.a-form-label, label')?.textContent.trim().replace(/[:：]\s*$/, '');
   if(label){dimensions.push(label);if(val)attributes[label]=val;}
 }
 // Modern inline twister uses dimension text spans instead of .selection.
 for(const el of document.querySelectorAll('[id^="inline-twister-expanded-dimension-text-"], [id^="inline-twister-dimension-text-"]')) {
   const key=el.id.replace(/^inline-twister-(?:expanded-)?dimension-text-/, '');
   const val=el.textContent.trim();
   if(key && val){dimensions.push(key);attributes[key]=val;}
 }
 for(const root of document.querySelectorAll('[id^="inline-twister-row-"], [id^="inline-twister-dim-title-"]')) {
   const key=root.id.replace(/^inline-twister-(?:row|dim-title)-/, '');
   const selected=root.querySelector('.selection, .a-text-bold, [aria-selected="true"] .a-button-text');
   const val=selected?.textContent.trim();
   if(val && val.length<250 && !attributes[key]){dimensions.push(key);attributes[key]=val;}
 }
 for (const root of scopes) for (const el of root.querySelectorAll('[data-asin], [data-defaultasin], [data-dp-url], a[href*="/dp/"], option[value]')) {
   for (const a of ['data-asin','data-defaultasin']) {const s=el.getAttribute(a)||''; if(/^[A-Z0-9]{10}$/.test(s))ids.add(s);}
   for (const a of ['data-dp-url','href','value']) {const m=(el.getAttribute(a)||'').match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/); if(m)ids.add(m[1]);}
 }
 return {html_language:document.documentElement.lang||'', nav_language:document.querySelector('#icp-nav-flyout .icp-nav-link-inner')?.innerText.trim()||'', title:document.querySelector('#productTitle')?.textContent.trim()||'', current:document.querySelector('input#ASIN')?.value||'',
   attributes, dimensions, asins:[...ids], scripts:[...document.scripts].map(s=>s.textContent).filter(s=>/asinVariationValues|dimensionToAsinMap|variationValues|dimensionValuesDisplayData/.test(s)),
   blocked:!!document.querySelector('#captchacharacters, form[action*="validateCaptcha"], input[name="cvf_captcha_input"]'),
   labels:scopes.map(x=>x.innerText.trim()).filter(Boolean)};
}'''

def scan_page(page, market, asin):
    url = market_product_url(market,asin)
    page.goto(url, wait_until='domcontentloaded', timeout=35000)
    for selector in ['#sp-cc-accept', 'input[name="accept"]']:
        try:
            if page.locator(selector).count(): page.locator(selector).first.click(timeout=1500)
        except Exception: pass
    try: page.wait_for_selector('#productTitle',timeout=12000)
    except Exception: pass
    page.wait_for_timeout(1500)
    raw=page.evaluate(EXTRACT)
    result={'url':page.url,'title':raw['title'],'labels':raw['labels'],'detected_attributes':raw.get('attributes',{}),'detected_dimensions':raw.get('dimensions',[]),'language_error':page_language_error(raw,market),'language':{'expected':MARKET_LOCALES[market],'html':raw.get('html_language',''),'navigation':raw.get('nav_language','')}}
    if raw['blocked'] or not raw['title']: return {**result,'error':'Amazon-Seite blockiert oder Produkt nicht geladen.'}
    current=raw['current']
    if current != asin: return {**result,'error':f'ASIN nicht eindeutig bestätigt / Weiterleitung: {current or page.url}'}
    parsed=embedded_variants(raw['scripts']); reliable=parsed['reliable']
    ids = parsed['asins'] | set(raw['asins']) | {asin}
    attributes=parsed['attributes']; selected={dimension_key(k):v for k,v in raw.get('attributes',{}).items()}
    attributes.setdefault(asin,{}).update(selected)
    dimensions=sorted(set(parsed['dimensions']) | {dimension_key(k) for k in raw.get('dimensions',[])})
    # No variants may mean a split OR an unsupported page: never assume a split.
    valid = reliable or len(raw['asins']) >= 2
    return {**result,'valid':valid,'asins':sorted(ids),'attributes':attributes,'dimensions':dimensions,'source':'Seitendaten + Variantenauswahl' if reliable else 'Variantenauswahl',
      **({} if valid else {'error':'Keine sichere Variantenstruktur auslesbar; mögliche Trennung bitte manuell prüfen.'})}

DIMENSION_NAMES={'color':'Farbe','style':'Stil','size':'Größe','pattern':'Muster','material':'Material','flavor':'Geschmack','scent':'Duft','quantity':'Menge'}

def normalized_words(value):
    value=unicodedata.normalize('NFKD',str(value or '').casefold())
    value=''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[_:\-]+',' ',value).split())

_DIMENSION_GROUPS={
 'color':['color','colour','farbe','couleur','colore','kleur','kolor','färg','color name','colour name','farbname','nom de couleur','nom de la couleur','nome colore','nombre del color','kleurnaam','nazwa koloru','färgnamn','اللون','لون','اسم اللون'],
 'style':['style','stil','stile','estilo','stijl','styl','style name','stilname','nom du style','nom de style','nome stile','nome dello stile','nombre de estilo','nombre del estilo','stijlnaam','nazwa stylu','stilnamn','النمط','نمط','اسم النمط','الطراز','طراز','اسم الطراز'],
 'size':['size','größe','groesse','grosse','taille','taglia','talla','tamaño','dimensione','dimensioni','maat','rozmiar','storlek','size name','größenname','grossenname','nom de taille','nom de la taille','nome taglia','nombre de talla','nombre del tamaño','maatnaam','nazwa rozmiaru','storleksnamn','الحجم','حجم','المقاس','مقاس','اسم المقاس','اسم الحجم'],
 'pattern':['pattern','muster','pattern name'],'material':['material','material type'],
 'flavor':['flavor','flavour','geschmack'],'scent':['scent','duft'],'quantity':['item package quantity','quantity','menge']}
DIMENSION_ALIASES={normalized_words(word):key for key,words in _DIMENSION_GROUPS.items() for word in words}

def dimension_key(value):
    value=normalized_words(value)
    if value.startswith('variation '):value=value[len('variation '):]
    return DIMENSION_ALIASES.get(value,value)

def normalize_value(value):
    value=unicodedata.normalize('NFKC',' '.join(str(value or '').split())).casefold()
    # Formatting variants only, no guessing or translating arbitrary product labels.
    return re.sub(r'(\d)\s+(mm|cm|m|ml|l|g|kg)\b',r'\1\2',value)

def expected_attributes(value):
    return value.get('attributes',{}) if isinstance(value,dict) else {}

def variant_label(value):
    return value.get('label','') if isinstance(value,dict) else value

def embedded_variants(scripts):
    """Read only explicit twister maps, never arbitrary ASINs elsewhere in scripts."""
    ids,reliable=embedded_asins(scripts); variants={}; dimensions=set()
    for script in scripts:
        objects={}
        for key in ('asinVariationValues','variationValues','dimensionToAsinMap','dimensionValuesDisplayData','variationDisplayLabels'):
            for match in re.finditer(r'["\']'+key+r'["\']\s*:\s*',script):
                try:
                    value,_=json.JSONDecoder().raw_decode(script[match.end():])
                    if isinstance(value,dict):objects[key]=value
                except (ValueError,TypeError):pass
        values=objects.get('variationValues',{})
        def canonical(rawkey):
            known=dimension_key(rawkey)
            if known in DIMENSION_NAMES:return known
            return dimension_key(objects.get('variationDisplayLabels',{}).get(rawkey,rawkey))
        for rawkey in values: dimensions.add(canonical(rawkey))
        for asin,attrs in objects.get('asinVariationValues',{}).items():
            if not ASIN.fullmatch(asin) or not isinstance(attrs,dict):continue
            parsed={}
            for rawkey,index in attrs.items():
                key=canonical(rawkey);dimensions.add(key)
                options=values.get(rawkey)
                if isinstance(options,list) and str(index).isdigit() and int(index)<len(options):
                    parsed[key]=str(options[int(index)])
                elif isinstance(index,str) and not index.isdigit():parsed[key]=index
            if parsed:variants.setdefault(asin,{}).update(parsed)
        # Explicit dimension->value dictionaries are unambiguous; arrays need a declared order.
        for asin,attrs in objects.get('dimensionValuesDisplayData',{}).items():
            if not ASIN.fullmatch(asin) or not isinstance(attrs,dict):continue
            parsed={canonical(k):str(v) for k,v in attrs.items() if isinstance(v,(str,int,float)) and str(v).strip()}
            if parsed:
                variants.setdefault(asin,{}).update(parsed);dimensions.update(parsed)
    return {'asins':ids,'reliable':reliable,'attributes':variants,'dimensions':sorted(dimensions)}


def parse_manual(data):
    name=str(data.get('name') or '').strip()
    if not name: raise ValueError('Bitte einen Familiennamen eingeben.')
    market=str(data.get('market') or '').upper()
    lines=str(data.get('lines') or '').strip().splitlines()
    out=io.StringIO();w=csv.writer(out,delimiter=';');w.writerow(['Familie','Marktplatz','ASIN','Farbe','Stil','Größe'])
    for line in lines:
        if not line.strip():continue
        fields=[x.strip() for x in line.split(';')]
        if len(fields)>4:raise ValueError('Pro Zeile: ASIN; Farbe; Stil; Größe (Merkmale optional).')
        fields += ['']*(4-len(fields));w.writerow([name,market,*fields])
    return parse_import(out.getvalue().encode(),'manual.csv')


def parse_family(data):
    name=str(data.get('name') or '').strip();market=str(data.get('market') or '').upper().strip()
    if not name:raise ValueError('Bitte einen Familiennamen eingeben.')
    if market not in MARKETS:raise ValueError('Bitte einen gültigen Marktplatz auswählen.')
    rows=data.get('variants')
    if not isinstance(rows,list):raise ValueError('Bitte Varianten eingeben.')
    variants={}
    for i,row in enumerate(rows,1):
        if not isinstance(row,dict):raise ValueError(f'Variante {i}: ungültige Eingabe.')
        asin=str(row.get('asin') or '').strip().upper();attrs={}
        entries=row.get('attributes',[])
        if not isinstance(entries,list):raise ValueError(f'Variante {i}: ungültige Merkmale.')
        for entry in entries:
            if not isinstance(entry,dict):raise ValueError(f'Variante {i}: ungültiges Merkmal.')
            raw_type=str(entry.get('type') or '').strip();value=str(entry.get('value') or '').strip()
            if not raw_type and not value:continue
            key=dimension_key(raw_type)
            if key not in ('color','style','size'):raise ValueError(f'Variante {i}: bitte Farbe, Stil oder Größe auswählen.')
            if not value:raise ValueError(f'Variante {i}: bitte einen Soll-Wert für {DIMENSION_NAMES[key]} eingeben oder das Merkmal entfernen.')
            if key in attrs:raise ValueError(f'Variante {i}: {DIMENSION_NAMES[key]} ist doppelt vorhanden.')
            attrs[key]=value
        label=str(row.get('label') or '').strip()
        if not asin and not attrs and not label:continue
        if not ASIN.fullmatch(asin):raise ValueError(f'Variante {i}: ASIN muss aus 10 Buchstaben/Ziffern bestehen.')
        if asin in variants:raise ValueError(f'ASIN {asin} ist doppelt vorhanden.')
        variants[asin]={'label':label,'attributes':attrs} if attrs or label else ''
    if not variants:raise ValueError('Bitte mindestens eine ASIN eingeben.')
    return {'name':name,'market':market,'variants':variants}


# Standalone, read-only bulk snapshots. These never change monitored Soll families.
def parse_snapshot_input(data, filename):
    if filename.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
        try:
            sheet=wb.active
            if sheet.max_row>10001 or sheet.max_column>200:raise ValueError('Bitte eine Liste mit höchstens 10.000 Zeilen und 200 Spalten verwenden.')
            rows=list(sheet.values)
        finally:wb.close()
    elif filename.lower().endswith('.csv'):
        text=data.decode('utf-8-sig')
        try: dialect=csv.Sniffer().sniff(text[:4096],delimiters=';,\t')
        except csv.Error: dialect=csv.excel
        rows=list(csv.reader(io.StringIO(text),dialect))
    else:raise ValueError('Bitte eine XLSX- oder CSV-Datei hochladen.')
    rows=[r for r in rows if any(str(v or '').strip() for v in r)]
    if not rows:raise ValueError('Die Liste ist leer.')
    headers=[normalized_words(v) for v in rows[0]]
    asin_cols=[i for i,v in enumerate(headers) if v in ('asin','child asin','childasin')]
    if len(asin_cols)>1:raise ValueError('Mehrere ASIN-Spalten gefunden. Bitte nur eine verwenden.')
    if asin_cols:
        idx=asin_cols[0];body=rows[1:];offset=2
        names=[i for i,v in enumerate(headers) if v in ('name','produktname','produkt','title','titel','bezeichnung')]
        nameidx=names[0] if names else None
    elif len(rows[0])==1 and ASIN.fullmatch(str(rows[0][0]).strip().upper()):
        idx=0;nameidx=None;body=rows;offset=1
    else:raise ValueError('Eine Spalte mit der Überschrift ASIN ist erforderlich. Name ist optional.')
    found={};duplicates=0;errors=[]
    for n,row in enumerate(body,offset):
        value=str(row[idx] or '').strip().upper() if idx<len(row) else ''
        if not ASIN.fullmatch(value):errors.append(str(n));continue
        name=str(row[nameidx] or '').strip()[:500] if nameidx is not None and nameidx<len(row) else ''
        if value in found:
            duplicates+=1
            if not found[value]['name']:found[value]['name']=name
        else:found[value]={'asin':value,'name':name}
    if errors:raise ValueError('Ungültige oder leere ASIN in Zeile '+', '.join(errors[:15])+(' …' if len(errors)>15 else '')+'. Es wurde nichts gestartet.')
    if not found:raise ValueError('Keine ASINs gefunden.')
    if len(found)>2000:raise ValueError('Bitte maximal 2.000 unterschiedliche ASINs pro Aufnahme verwenden.')
    return {'seeds':list(found.values()),'duplicates':duplicates}

class SnapshotCancelled(Exception):pass

def collect_snapshot(seed,market,read,cancelled=lambda:False,max_members=500):
    """Expand only explicit variant links; retain page-local evidence and failures."""
    queue=[seed];seen=set();variants=[];known=set();notes=[];seed_valid=False
    while queue:
        if cancelled():raise SnapshotCancelled()
        asin=queue.pop(0)
        if asin in seen:continue
        if len(seen)>=max_members:
            notes.append(f'Grenze von {max_members} geöffneten Varianten erreicht. Aufnahme ist unvollständig.');break
        seen.add(asin)
        o=read(asin)
        if cancelled():raise SnapshotCancelled()
        if asin==seed:seed_valid=bool(o.get('valid') and not o.get('error'))
        issue=o.get('error') or ('' if o.get('valid') else 'Keine sichere Variantenstruktur auslesbar.')
        language=o.get('language_error','')
        attributes=dict(o.get('attributes',{}).get(asin,{})) if not issue and not language else {}
        status='Unklar' if issue or language else ('Gelesen' if attributes else 'Teilweise')
        note=issue or language or ('' if attributes else 'Merkmalswerte nicht auslesbar.')
        variants.append({'asin':asin,'title':o.get('title',''),'attributes':attributes,'status':status,'note':note,'at':o.get('at',''),'url':o.get('url') or market_product_url(market,asin)})
        if not issue:
            linked={a for a in o.get('asins',[]) if isinstance(a,str) and ASIN.fullmatch(a)}
            known.update(linked)
            if seed not in linked:notes.append(f'{asin}: Ausgangs-ASIN nicht in der dortigen Variantenauswahl gefunden.')
            for child in sorted(linked):
                if child not in seen and child not in queue:queue.append(child)
    if not seed_valid:
        return {'status':'Unklar','note':variants[0]['note'] if variants else 'Keine Daten.','asins':[],'variants':variants}
    known.add(seed)
    pending=known-seen
    for asin in sorted(pending):
        variants.append({'asin':asin,'title':'','attributes':{},'status':'Unklar','note':'Gefunden, wegen der Begrenzung noch nicht geöffnet.','at':'','url':market_product_url(market,asin)})
    incomplete=any(v['status']!='Gelesen' for v in variants)
    if incomplete:notes.append('Mindestens eine Variante oder ihr Merkmalswert konnte nicht vollständig gelesen werden.')
    return {'status':'Teilweise' if notes or incomplete else 'Gelesen','note':' '.join(dict.fromkeys(notes)),'asins':sorted(known),'variants':variants}


def snapshot_baseline(items,existing,include_attributes=False):
    groups={};skipped=[];evidence={}
    for item in items:
        r=snapshot_result(item);members=tuple(sorted(set(r.get('asins') or [item['asin']])))
        for a in members:evidence.setdefault((item['market'],a),set()).add((members,item['status']))
    for item in items:
        r=snapshot_result(item);members=tuple(sorted(set(r.get('asins') or [])))
        if item['status']!='Gelesen' or not members or item['asin'] not in members:
            skipped.append({'market':item['market'],'asin':item['asin'],'reason':'Nicht vollständig und sicher gelesen.'});continue
        key=(item['market'],members)
        variants={v['asin']:v for v in r.get('variants',[])}
        if any(a not in variants or variants[a].get('status')!='Gelesen' for a in members):
            skipped.append({'market':item['market'],'asin':item['asin'],'reason':'Produktdetails unvollständig.'});continue
        attrs={a:{'label':variants[a].get('title',''),'attributes':{k:v for k,v in variants[a].get('attributes',{}).items() if k in ('color','style','size')} if include_attributes else {}} for a in members}
        group={'market':item['market'],'name':'Ist · '+(item.get('name') or variants[item['asin']].get('title') or item['asin'])[:130]+' · '+members[0],'variants':attrs,'members':members}
        if key in groups and include_attributes and groups[key]['variants']!=attrs:groups[key]['conflict']=True
        else:groups.setdefault(key,group)
    accepted=[];unchanged=0
    for (market,members),g in groups.items():
        reasons=[]
        if g.get('conflict'):reasons.append('Widersprüchliche Merkmalswerte.')
        if any(status!='Gelesen' or other!=members for a in members for other,status in evidence.get((market,a),set())):
            reasons.append('Überlappende oder widersprüchliche Ergebnisse in der Aufnahme.')
        owners=[f for f in existing if f['market']==market and set(f['variants'])&set(members)]
        if owners:
            if len(owners)==1 and set(owners[0]['variants'])==set(members):
                unchanged+=1;continue
            reasons.append('ASINs sind bereits einem anderen Soll zugeordnet. Bitte bestehende Familie bearbeiten.')
        if reasons:skipped.append({'market':market,'asin':', '.join(members),'reason':' '.join(reasons)});continue
        # Never overwrite a user-defined family with an identical name.
        used={f['name'] for f in existing if f['market']==market}|{f['name'] for f in accepted if f['market']==market}
        base=g['name'];number=2
        while g['name'] in used:g['name']=base+f' ({number})';number+=1
        accepted.append({k:g[k] for k in ('name','market','variants')})
    return {'groups':accepted,'skipped':skipped,'unchanged':unchanged}


def snapshot_structure(status,count):
    if status=='Ausstehend':return 'Noch nicht geprüft'
    if status!='Gelesen' or not count:return 'Unklar – keine sichere Aussage zur Variation'
    if count==1:return 'Keine Variation – Einzelprodukt'
    return f'Variation vorhanden – {count} ASINs'


def snapshot_result(item):
    value=item.get('result')
    return json.loads(value) if isinstance(value,str) and value else value or {}


def snapshot_comparison(items,markets):
    """Compare exact observed member sets per input seed; never infer transitive families."""
    seeds={}
    for item in items:
        row=seeds.setdefault(item['asin'],{'asin':item['asin'],'name':item.get('name',''),'markets':{}})
        r=snapshot_result(item);members=sorted(set(r.get('asins') or []))
        variants=r.get('variants') or []
        title=next((v.get('title') for v in variants if v['asin']==item['asin'] and v.get('title')),'')
        if not row['name']:row['name']=title
        complete=item['status']=='Gelesen' and bool(members) and item['asin'] in members
        row['markets'][item['market']]={'asins':members,'complete':complete,'title':title,'status':item['status'],'at':item.get('at',''),'note':item.get('note',''),'variants':variants}
    rows=[]
    for row in seeds.values():
        signatures={};unknown=[]
        for market in markets:
            cell=row['markets'].setdefault(market,{'asins':[],'complete':False,'status':'Nicht in Länderliste','variants':[]})
            if cell['complete']:
                key=tuple(cell['asins']);code=signatures.setdefault(key,chr(65+len(signatures)))
                cell['label']=('Variation' if len(key)>1 else 'Keine Variation – Einzelprodukt')+f' · {len(key)} ASIN'+('s' if len(key)>1 else '')+f' · Gruppe {code}'
            else:
                unknown.append(market);cell['label']=cell['status']+' · nicht sicher vergleichbar'
        if len(signatures)>1:verdict='Abweichend'
        elif unknown:verdict='Noch nicht sicher vergleichbar'
        elif len(markets)<2:verdict='Nur ein Markt'
        elif signatures and len(next(iter(signatures)))==1:verdict='Einheitlich ohne Variation'
        else:verdict='Einheitliche Variation'
        row['verdict']=verdict
        row['same']='; '.join(' / '.join(m for m in markets if row['markets'][m]['complete'] and tuple(row['markets'][m]['asins'])==key)+f' (Gruppe {code})' for key,code in signatures.items())
        row['unknown']=', '.join(unknown);rows.append(row)
    return {'markets':markets,'rows':rows}


def add_report_sheet(wb,title,headers,rows,widths,note):
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    ws=wb.create_sheet(title)
    ws.append([title]);ws.append([note]);ws.append(headers)
    for row in rows:ws.append(row)
    for row in ws:
        for c in row:
            if isinstance(c.value,str):c.data_type='s'
            c.alignment=Alignment(vertical='top',wrap_text=True)
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=len(headers))
    ws.merge_cells(start_row=2,start_column=1,end_row=2,end_column=len(headers))
    ws['A1'].font=Font(size=20,bold=True,color='163C33');ws.row_dimensions[1].height=32;ws.row_dimensions[2].height=48
    for c in ws[3]:c.fill=PatternFill('solid',fgColor='163C33');c.font=Font(color='FFFFFF',bold=True)
    ws.row_dimensions[3].height=32
    for i,width in enumerate(widths,1):ws.column_dimensions[get_column_letter(i)].width=width
    import math
    for row in ws.iter_rows(min_row=4):
        lines=max(sum(max(1,math.ceil(len(line)/max(8,widths[c.column-1]-2))) for line in str(c.value or '').split('\n')) for c in row)
        ws.row_dimensions[row[0].row].height=min(409,max(70,lines*15+10))
        for c in row:
            c.fill=PatternFill('solid',fgColor='F0F5F1' if c.row%2==0 else 'FFFFFF')
            if c.column==1:c.font=Font(bold=True,color='163C33',size=12)
            if c.value in ('Abweichend','Noch nicht sicher vergleichbar'):c.fill=PatternFill('solid',fgColor='FFF2CC')
    ws.freeze_panes='C4';ws.auto_filter.ref=f'A3:{get_column_letter(len(headers))}{max(3,ws.max_row)}'
    ws.sheet_view.zoomScale=85;ws.print_title_rows='1:3'
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    return ws


def add_comparison_sheet(wb,items,markets):
    comparison=snapshot_comparison(items,markets);rows=[]
    for r in comparison['rows']:
        cells=[]
        for m in markets:
            c=r['markets'][m]
            cells.append(c['label']+'\n'+('\n'.join((v.get('title') or 'Produktname nicht erfasst')+' · '+v['asin'] for v in c['variants']) or 'Keine gesicherten Produktdaten')+'\n'+c.get('note','')+'\n'+str(c.get('at') or ''))
        rows.append([r['name'] or 'Produktname nicht erfasst',r['asin'],r['verdict'],r['same'],r['unknown'],*cells])
    return add_report_sheet(wb,'Ländervergleich',['Produkt / Name aus Liste','Eingabe-ASIN','Ergebnis','Gleiche Zusammensetzung','Unklare / offene Länder',*markets],rows,[42,18,28,32,24]+[48]*len(markets),'Pro Eingabeprodukt: gleiche Gruppe A/B/... bedeutet dieselben enthaltenen ASINs innerhalb dieser Zeile. Namen, Farbe, Stil und Größe beeinflussen den Vergleich nicht. Unvollständige Ergebnisse gelten nie als einheitlich. Keine Variation – Einzelprodukt = nur die Eingabe-ASIN gefunden. Vergleich der gespeicherten Zeitpunkte.')


def snapshot_workbook(job,items,market):
    """Runtime Excel export using the app's already bundled Excel dependency."""
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.worksheet.datavalidation import DataValidation
    from datetime import datetime
    wb=Workbook();summary=wb.active;summary.title='Übersicht';sheet=wb.create_sheet('Varianten')
    def safe_append(ws,values):
        ws.append(values)
        for c in ws[ws.max_row]:
            if isinstance(c.value,str):c.data_type='s'  # Never interpret Amazon/user text as Excel formulas.
    def date(value):
        try:return datetime.fromisoformat(value).replace(tzinfo=None)
        except (ValueError,TypeError):return None
    safe_append(summary,['Ist-Aufnahme',job['name'],'Marktplatz',market])
    safe_append(summary,['Stand des Laufs',job['status'],'Erstellt',job['created']])
    safe_append(summary,['Momentaufnahme der auslesbaren Amazon-Varianten. „Gelesen“ bedeutet nicht fachlich korrekt. Unvollständige Seiten und offene Prüfungen sind gekennzeichnet.'])
    safe_append(summary,['Zeiten entsprechen der lokalen Rechnerzeit. Kolleg:innen bewerten in den beiden letzten Spalten des Blatts Varianten.'])
    summary_headers=['Eingabe-ASIN','Name aus Liste','Marktplatz','Lesestatus','Gefundene ASINs','Hinweis','Ausgelesen am','Amazon-Link','Variation?']
    safe_append(summary,summary_headers)
    headers=['Gruppe','Eingabe-ASINs','Marktplatz','ASIN','Produkttitel','Farbe','Stil','Größe','Weitere Merkmale','Lesestatus','Hinweis','Ausgelesen am','Amazon-Link','Bewertung','Kommentar','Variation?']
    safe_append(sheet,headers)
    groups={}
    for item in items:
        if item['market']!=market:continue
        r=json.loads(item['result']) if isinstance(item.get('result'),str) and item['result'] else item.get('result') or {}
        safe_append(summary,[item['asin'],item['name'],market,item['status'],len(r['asins']) if 'asins' in r and r.get('status')!='Unklar' else None,item.get('note',''),date(item.get('at')),market_product_url(market,item['asin']),snapshot_structure(item['status'],len(set(r.get('asins') or [])))])
        if not r:continue
        # Deduplicate identical discoveries, never merge different or overlapping sets.
        key=tuple(sorted(set(r.get('asins') or [item['asin']])))
        group=groups.setdefault(key,{'seeds':[],'variants':{},'notes':[],'names':[],'statuses':[]})
        group['seeds'].append(item['asin'])
        group['names'].append(item.get('name',''));group['statuses'].append(item['status'])
        if r.get('note'):group['notes'].append(r['note'])
        for v in r.get('variants',[]):
            old=group['variants'].get(v['asin'])
            if old and old['attributes']!=v['attributes']:
                group['notes'].append('Unterschiedliche Merkmalswerte während dieses Laufs beobachtet; letzter Stand dargestellt.')
            group['variants'][v['asin']]=v
    for number,group in enumerate(groups.values(),1):
        for asin,v in sorted(group['variants'].items()):
            attrs=v['attributes'];note=' '.join(dict.fromkeys([v.get('note',''),*group['notes']])).strip()
            safe_append(sheet,[f'{market}-{number:03}',', '.join(group['seeds']),market,asin,v['title'],attrs.get('color',''),attrs.get('style',''),attrs.get('size',''),'; '.join(DIMENSION_NAMES.get(k,k)+': '+str(value) for k,value in attrs.items() if k not in ('color','style','size')),v['status'],note,date(v.get('at')),v['url'],'Offen','',snapshot_structure('Gelesen' if all(st=='Gelesen' for st in group['statuses']) else 'Unklar',len(group['variants']))])
    validation=DataValidation(type='list',formula1='"Offen,Passt,Bitte ändern,Unklar"');sheet.add_data_validation(validation)
    if sheet.max_row>=2:validation.add(f'N2:N{sheet.max_row}')
    for ws,head,widths in [(summary,5,[18,35,14,18,20,70,23,58,40]),(sheet,1,[14,32,13,18,48,22,32,22,40,18,65,23,58,20,45,40])]:
        ws.freeze_panes=f'A{head+1}';ws.auto_filter.ref=f'A{head}:{ws.cell(ws.max_row,len(widths)).coordinate}'
        ws.sheet_view.zoomScale=90
        for col,width in enumerate(widths,1):ws.column_dimensions[ws.cell(1,col).column_letter].width=width
        for c in ws[head]:c.fill=PatternFill('solid',fgColor='163C33');c.font=Font(color='FFFFFF',bold=True);c.alignment=Alignment(wrap_text=True,vertical='center')
        ws.row_dimensions[head].height=30
        for row in ws.iter_rows(min_row=head+1):
            for c in row:
                c.alignment=Alignment(vertical='top',wrap_text=True)
                if isinstance(c.value,datetime):c.number_format='yyyy-mm-dd hh:mm:ss'
                if c.row%2==0:c.fill=PatternFill('solid',fgColor='F0F5F1')
            import math
            lines=max(sum(max(1,math.ceil(len(line)/max(8,widths[c.column-1]-2))) for line in str(c.value or '').split('\n')) for c in row)
            ws.row_dimensions[row[0].row].height=min(409,max(32,lines*15+8))
        urlcol=8 if ws==summary else 13
        for row in range(head+1,ws.max_row+1):
            cell=ws.cell(row,urlcol)
            if isinstance(cell.value,str) and cell.value.startswith('https://www.amazon.'):
                cell.hyperlink=cell.value;cell.font=Font(color='28694B',underline='single')
        ws.sheet_properties.pageSetUpPr.fitToPage=True
        ws.page_setup.orientation='landscape';ws.page_setup.paperSize=ws.PAPERSIZE_A3;ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
        ws.print_title_rows=f'1:{head}'
    summary.merge_cells('A3:H3');summary.merge_cells('A4:H4')
    summary['A3'].alignment=summary['A4'].alignment=Alignment(wrap_text=True,vertical='center')
    summary.row_dimensions[3].height=32;summary.row_dimensions[4].height=30
    summary['A1'].font=Font(size=16,bold=True,color='163C33')
    if sheet.max_row>=2:
        for row in sheet.iter_rows(min_row=2,min_col=14,max_col=15):
            for c in row:c.fill=PatternFill('solid',fgColor='FFF2CC')
    rows=[]
    max_members=max([len(g['variants']) for g in groups.values()]+[1])
    for number,g in enumerate(groups.values(),1):
        variants=sorted(g['variants'].values(),key=lambda v:v['asin'])
        name=next((n for n in g['names'] if n),None) or next((v.get('title') for v in variants if v.get('title')),'Produktname nicht erfasst')
        complete=all(st=='Gelesen' for st in g['statuses'])
        state=snapshot_structure('Gelesen' if complete else 'Unklar',len(variants))
        cards=[(v.get('title') or 'Produktname nicht erfasst')+'\nASIN: '+v['asin']+'\n'+' · '.join(DIMENSION_NAMES.get(k,k)+': '+str(val) for k,val in v.get('attributes',{}).items())+'\n'+v.get('status','') for v in variants]
        rows.append([name,f'{market}-{number:03}',state,len(variants),', '.join(g['seeds']),' '.join(dict.fromkeys(g['notes'])),*cards,*(['']*(max_members-len(cards)))])
    for item in items:
        if item['market']==market and not snapshot_result(item):
            rows.append([item.get('name') or 'Produktname noch nicht erfasst','',item['status'],None,item['asin'],item.get('note',''),*(['']*max_members)])
    grouped=add_report_sheet(wb,'Variationsgruppen',['Produkt / Name aus Liste','Gruppe','Variation?','Produkte','Eingabe-ASINs','Hinweis']+[f'Produkt {i+1}' for i in range(max_members)],rows,[42,14,26,12,25,42]+[42]*max_members,'Eine Zeile = eine beobachtete Variationsgruppe. Zusammengehörige Produkte stehen nebeneinander, Produktname zuerst. Unterschiedliche oder überlappende Gruppen bleiben getrennt. Details und Bewertungsfelder stehen im Blatt Varianten. Eine sicher gelesene einzelne ASIN ist keine Variation, auch bei angezeigtem Stil, Farbe oder Größe. Offene / unklare Prüfungen sind keine bestätigten Einzelprodukte.')
    for rownum,g in enumerate(groups.values(),4):
        for col,v in enumerate(sorted(g['variants'].values(),key=lambda v:v['asin']),7):
            grouped.cell(rownum,col).hyperlink=market_product_url(market,v['asin'])
    markets=job.get('markets') or sorted({i['market'] for i in items}) or [market]
    if isinstance(markets,str):markets=json.loads(markets)
    add_comparison_sheet(wb,items,markets)
    wb._sheets=[grouped,wb['Ländervergleich'],summary,sheet]
    wb.active=0
    result=io.BytesIO();wb.save(result);wb.close();return result.getvalue()
