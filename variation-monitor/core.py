import re, json, csv, io, unicodedata
from collections import defaultdict

MARKETS = {'DE':'de','FR':'fr','IT':'it','ES':'es','UK':'co.uk','NL':'nl','PL':'pl','SE':'se','BE':'com.be','AE':'ae'}
MARKET_LOCALES={'DE':'de-DE','FR':'fr-FR','IT':'it-IT','ES':'es-ES','UK':'en-GB','NL':'nl-NL','PL':'pl-PL','SE':'sv-SE','BE':'fr-BE','AE':'en-AE'}

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
