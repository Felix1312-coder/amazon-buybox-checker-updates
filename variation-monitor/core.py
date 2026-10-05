import re, json, csv, io
from collections import defaultdict

MARKETS = {'DE':'de','FR':'fr','IT':'it','ES':'es','UK':'co.uk','NL':'nl','PL':'pl','SE':'se','BE':'com.be','AE':'ae'}
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
            attrs={dimension_key(k):str(d[k]).strip() for k in ('farbe','stil','style','größe','groesse','size','color','muster','material') if d.get(k) is not None and str(d[k]).strip()}
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
        for key,wanted in expected_attributes(expected_map.get(asin)).items():
            if key not in actual: unknown.append(DIMENSION_NAMES.get(key,key))
            elif normalize_value(wanted)!=normalize_value(actual[key]): changes.append({'dimension':DIMENSION_NAMES.get(key,key),'expected':wanted,'actual':actual[key]})
        if missing or extra or changes:
            deviations=True
            details.append({'asin':asin,'type':'abweichung','missing':sorted(missing),'extra':sorted(extra),'changes':changes,'text':'Sichtbare Verknüpfung weicht vom Soll ab.'})
        elif unknown:
            uncertain=True; details.append({'asin':asin,'type':'unklar','text':'Soll-Merkmale nicht auslesbar: '+', '.join(unknown)})
        else: details.append({'asin':asin,'type':'ok','text':'Alle erwarteten Varianten gefunden.'})
    status = 'Abweichung' if deviations else ('Unklar' if uncertain else 'OK')
    return {'status':status,'partial':uncertain,'details':details}

# Only variant-specific containers are read; recommendation ASINs are excluded.
EXTRACT = r'''() => {
 const scopes = [...document.querySelectorAll('#twister, #twister_feature_div, #twister-plus-inline-twister, [id^="variation_"]')];
 const ids = new Set(), attributes={}, dimensions=[];
 for(const root of document.querySelectorAll('[id^="variation_"]')) {
   const key=root.id.replace(/^variation_/, '');
   const selected=root.querySelector('.selection, select option:checked');
   const val=selected?.textContent.trim();
   dimensions.push(key);
   if(val)attributes[key]=val;
 }
 for (const root of scopes) for (const el of root.querySelectorAll('[data-asin], [data-defaultasin], [data-dp-url], a[href*="/dp/"], option[value]')) {
   for (const a of ['data-asin','data-defaultasin']) {const s=el.getAttribute(a)||''; if(/^[A-Z0-9]{10}$/.test(s))ids.add(s);}
   for (const a of ['data-dp-url','href','value']) {const m=(el.getAttribute(a)||'').match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/); if(m)ids.add(m[1]);}
 }
 return {title:document.querySelector('#productTitle')?.textContent.trim()||'', current:document.querySelector('input#ASIN')?.value||'',
   attributes, dimensions, asins:[...ids], scripts:[...document.scripts].map(s=>s.textContent).filter(s=>/asinVariationValues|dimensionToAsinMap|variationValues/.test(s)),
   blocked:!!document.querySelector('#captchacharacters, form[action*="validateCaptcha"], input[name="cvf_captcha_input"]'),
   labels:scopes.map(x=>x.innerText.trim()).filter(Boolean)};
}'''

def scan_page(page, market, asin):
    url = f'https://www.amazon.{MARKETS[market]}/dp/{asin}'
    page.goto(url, wait_until='domcontentloaded', timeout=35000)
    for selector in ['#sp-cc-accept', 'input[name="accept"]']:
        try:
            if page.locator(selector).count(): page.locator(selector).first.click(timeout=1500)
        except Exception: pass
    try: page.wait_for_selector('#productTitle',timeout=12000)
    except Exception: pass
    page.wait_for_timeout(1500)
    raw=page.evaluate(EXTRACT)
    result={'url':page.url,'title':raw['title'],'labels':raw['labels']}
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

DIMENSION_ALIASES = {
 'color':'color','colour':'color','farbe':'color','couleur':'color','colore':'color','kleur':'color','kolor':'color','färg':'color',
 'style':'style','stil':'style','stile':'style','estilo':'style','stijl':'style','styl':'style',
 'size':'size','größe':'size','groesse':'size','taille':'size','taglia':'size','talla':'size','maat':'size','rozmiar':'size','storlek':'size',
 'pattern':'pattern','muster':'pattern','material':'material','flavor':'flavor','scent':'scent','item_package_quantity':'quantity',
}
DIMENSION_NAMES={'color':'Farbe','style':'Stil','size':'Größe','pattern':'Muster','material':'Material','flavor':'Geschmack','scent':'Duft','quantity':'Menge'}

def dimension_key(value):
    value=str(value).strip().lower().removeprefix('variation_').removesuffix('_name')
    return DIMENSION_ALIASES.get(value,value)

def normalize_value(value):
    return ' '.join(str(value or '').split()).casefold()

def expected_attributes(value):
    return value.get('attributes',{}) if isinstance(value,dict) else {}

def variant_label(value):
    return value.get('label','') if isinstance(value,dict) else value

def embedded_variants(scripts):
    """Read only explicit twister maps, never arbitrary ASINs elsewhere in scripts."""
    ids,reliable=embedded_asins(scripts); variants={}; dimensions=set()
    for script in scripts:
        objects={}
        for key in ('asinVariationValues','variationValues','dimensionToAsinMap'):
            for match in re.finditer(r'["\']'+key+r'["\']\s*:\s*',script):
                try:
                    value,_=json.JSONDecoder().raw_decode(script[match.end():])
                    if isinstance(value,dict):objects[key]=value
                except (ValueError,TypeError):pass
        values=objects.get('variationValues',{})
        for rawkey in values: dimensions.add(dimension_key(rawkey))
        for asin,attrs in objects.get('asinVariationValues',{}).items():
            if not ASIN.fullmatch(asin) or not isinstance(attrs,dict):continue
            parsed={}
            for rawkey,index in attrs.items():
                key=dimension_key(rawkey);dimensions.add(key)
                options=values.get(rawkey)
                if isinstance(options,list) and str(index).isdigit() and int(index)<len(options):
                    parsed[key]=str(options[int(index)])
                elif isinstance(index,str) and not index.isdigit():parsed[key]=index
            if parsed:variants[asin]=parsed
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
