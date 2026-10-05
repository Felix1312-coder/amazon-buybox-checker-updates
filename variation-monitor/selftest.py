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
            page.screenshot(path=str(destination.with_suffix('.png')),full_page=True)
            page.set_content('''<span id="productTitle">Fixture</span><input id="ASIN" value="B000000001"><div id="variation_style_name"><span class="selection">Modern</span><li data-asin="B000000001"></li><li data-asin="B000000002"></li></div><div id="variation_size_name"><span class="selection">L</span><select><option value="/dp/B000000003">S</option></select></div><div id="recommendations"><li data-asin="B000000004"></li></div>''')
            raw=page.evaluate(EXTRACT)
            assert set(raw['asins'])=={'B000000001','B000000002','B000000003'},raw
            assert raw['attributes']['style_name']=='Modern',raw
            assert raw['attributes']['size_name']=='L',raw
            browser.close()
        result.update(ok=True,browser='Microsoft Edge',checks=['Frozen UI assets','Playwright driver + Edge','Manual entry rendered','Style and size extraction','Recommendation exclusion','openpyxl import','webview import'])
    except Exception as e:
        result['error']=repr(e)
        raise
    finally:
        destination.write_text(json.dumps(result,indent=2),encoding='utf8');server.shutdown()
