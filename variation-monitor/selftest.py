"""Offline packaged-runtime smoke test, invoked explicitly by Windows CI."""
import json,threading,sys
from pathlib import Path

def run(app,output):
    from openpyxl import Workbook
    from playwright.sync_api import sync_playwright
    import webview
    from core import EXTRACT
    destination=Path(output);destination.parent.mkdir(parents=True,exist_ok=True)
    server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    result={'ok':False,'frozen':bool(getattr(sys,'frozen',False))}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1050})
            page.goto(url)
            page.wait_for_selector('#familytable .empty')
            page.locator('#nav-manual').click()
            page.wait_for_selector('#testasin',state='visible')
            page.get_by_role('button',name='＋ Familie anlegen').last.click()
            page.locator('#editname').fill('Testfamilie')
            page.locator('#editmarket').select_option('IT')
            page.locator('.variant-asin').fill('B000000001')
            page.get_by_role('button',name='＋ Merkmal hinzufügen').click()
            page.locator('.attribute-type').select_option('style')
            page.locator('.attribute-value').fill('Classico')
            page.get_by_role('button',name='Änderungen speichern').click()
            page.wait_for_selector('#editor',state='hidden')
            page.get_by_role('button',name='Bearbeiten',exact=True).click()
            assert page.locator('.attribute-value').input_value()=='Classico'
            page.locator('#editname').fill('Bearbeitete Familie')
            page.get_by_role('button',name='＋ Merkmal hinzufügen').click()
            page.locator('.attribute-type').last.select_option('size')
            page.locator('.attribute-value').last.fill('50 cm')
            page.screenshot(path=str(destination.with_suffix('.png')),full_page=True)
            page.get_by_role('button',name='Änderungen speichern').click()
            page.wait_for_selector('#editor',state='hidden')
            assert len(app.families())==1
            assert app.families()[0]['name']=='Bearbeitete Familie'
            assert app.families()[0]['variants']['B000000001']['attributes']['size']=='50 cm'
            page.get_by_role('button',name='Adaptive Excel-Vorlage ↓').click()
            page.locator('#templateDialog input[value=style]').check()
            with page.expect_download() as download_info:
                page.get_by_role('button',name='Vorlage herunterladen ↓').click()
            download=download_info.value
            target=destination.parent/'template-downloaded.xlsx';download.save_as(target)
            from openpyxl import load_workbook
            w=load_workbook(target,read_only=True)
            assert list(next(w['Varianten'].values))==['Familie','Marktplatz','ASIN','Stil'];w.close()
            page.locator('#templateDialog button').first.click()

            page.set_content('''<span id="productTitle">Fixture</span><input id="ASIN" value="B000000001"><div id="variation_style_name"><span class="selection">Modern</span><li data-asin="B000000001"></li><li data-asin="B000000002"></li></div><div id="variation_size_name"><span class="selection">L</span><select><option value="/dp/B000000003">S</option></select></div><div id="recommendations"><li data-asin="B000000004"></li></div>''')
            raw=page.evaluate(EXTRACT)
            assert set(raw['asins'])=={'B000000001','B000000002','B000000003'},raw
            assert raw['attributes']['style_name']=='Modern',raw
            assert raw['attributes']['size_name']=='L',raw
            page.set_content('''<span id="productTitle">Fixture IT</span><input id="ASIN" value="B0CP983KKH"><div id="twister-plus-inline-twister"><div id="inline-twister-row-style_name"><span>Nome stile:</span><span id="inline-twister-expanded-dimension-text-style_name">Aerosol per bambini</span><li data-asin="B0CP983KKH"></li><li data-asin="B01KWTC5YW"></li></div><div id="inline-twister-row-size_name"><span id="inline-twister-dim-title-size_name">Taglia: <b class="a-text-bold">50 cm</b></span></div></div>''')
            modern=page.evaluate(EXTRACT)
            assert modern['attributes']['style_name']=='Aerosol per bambini',modern
            assert modern['attributes']['size_name']=='50 cm',modern
            assert set(modern['asins'])=={'B0CP983KKH','B01KWTC5YW'},modern
            browser.close()
        # Exercise real frozen launcher loading a new payload through the SAME executable.
        import runtime,hashlib,io,subprocess,zipfile
        shortcut_dir=destination.parent/'shortcuts'
        runtime.create_shortcuts(Path(sys.executable),shortcut_dir)
        assert (shortcut_dir/'Amazon Variation Monitor.lnk').exists()
        files={name:(app.ROOT/name).read_bytes() for name in runtime.REQUIRED}
        meta=json.loads(files['version.json']);meta['version']='0.4.1'
        files['version.json']=json.dumps(meta).encode()
        blob=io.BytesIO()
        with zipfile.ZipFile(blob,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in files.items():z.writestr(name,value)
        before=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        runtime.install_bundle(blob.getvalue(),{'app_id':runtime.APP_ID,'version':'0.4.1','launcher_protocol':1,'sha256':hashlib.sha256(blob.getvalue()).hexdigest()},app.DATA/'updates')
        probe=destination.parent/'payload-probe.json'
        subprocess.run([sys.executable,'--payload-probe',str(probe)],check=True,timeout=60)
        loaded=json.loads(probe.read_text(encoding='utf8'))
        assert loaded['version']=='0.4.1',loaded
        assert 'versions' in loaded['source'],loaded
        assert loaded['families']==1,loaded
        assert before==hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
        (app.DATA/'updates'/'active.json').unlink()
        result.update(ok=True,browser='Microsoft Edge',checks=['Desktop shortcut creation','Frozen launcher loads updated payload without EXE replacement','Existing family preserved across payload update','Frozen UI assets','Playwright driver + Edge','Family creation and editing with stable identity','Adaptive XLSX download and columns','Legacy and modern inline twister style/size extraction','Recommendation exclusion','openpyxl import','webview import'])
    except Exception as e:
        result['error']=repr(e)
        raise
    finally:
        destination.write_text(json.dumps(result,indent=2),encoding='utf8');server.shutdown()
