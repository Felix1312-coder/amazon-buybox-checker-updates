"""Windows UI smoke test with deterministic Amazon responses, no live product changes."""
import io,json,os,tempfile,threading,time,zipfile
from pathlib import Path
A='B000000001';B='B000000002'

def main():
 from playwright.sync_api import sync_playwright
 from openpyxl import load_workbook
 import app
 qa=Path('qa');qa.mkdir(exist_ok=True)
 original=app.snapshot_process
 def scanner(page,market,asin):
  page.set_content('<html lang="'+('it-IT' if market=='IT' else 'de-DE')+'"><body>Offline fixture</body></html>')
  return {'valid':True,'title':'Testprodukt '+asin,'asins':[A,B],'attributes':{asin:{'style':'Classico' if market=='IT' else 'Klassisch','color':'Giallo' if market=='IT' else 'Gelb','size':'50 cm'}},'url':f'https://www.amazon.{"it" if market=="IT" else "de"}/dp/{asin}'}
 app.snapshot_process=lambda ident,page_for:original(ident,page_for,scanner)
 with app.db() as c:c.execute('UPDATE settings SET value=? WHERE key="config"',(json.dumps({'visible':False,'enabled':False,'time':'09:00','last_day':''}),))
 server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
 threading.Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='msedge',headless=True)
   page=browser.new_page(viewport={'width':1500,'height':1100},accept_downloads=True)
   page.goto(f'http://127.0.0.1:{server.server_port}')
   page.locator('#nav-snapshots').click()
   page.locator('#snapFile').set_input_files({'name':'Liste.csv','mimeType':'text/csv','buffer':f'ASIN;Name\n{A};Test Eins\n{B};Test Zwei'.encode()})
   page.wait_for_function("document.querySelector('#snapPreview').innerText.includes('2 eindeutige ASINs')")
   page.get_by_role('button',name='Alle abwählen',exact=True).click()
   assert not page.locator('#snapStart').is_enabled()
   page.locator('#snapMarkets input[value=IT]').check();page.locator('#snapMarkets input[value=DE]').check()
   page.locator('#snapName').fill('Kollegenprüfung')
   page.locator('#snapStart').click()
   page.wait_for_function("document.querySelector('#snapJobStatus').innerText.includes('Abgeschlossen')",timeout=90000)
   assert '4 / 4' in page.locator('#snapJobStatus').inner_text()
   page.locator('#snapFilterMarket').select_option('IT')
   page.wait_for_function("document.querySelectorAll('#snapTable tbody tr').length===2")
   page.get_by_role('button',name='Varianten ansehen').first.click()
   page.locator('#detail').wait_for(state='visible')
   assert 'Classico' in page.locator('#detailbody').inner_text()
   assert B in page.locator('#detailbody').inner_text()
   page.screenshot(path=str(qa/'snapshot-detail.png'),full_page=True)
   page.locator('#detail button').first.click()
   page.locator('#snapExportMarket').select_option('IT')
   with page.expect_download() as info:page.get_by_role('button',name='Excel für diesen Markt ↓').click()
   target=qa/'snapshot-IT.xlsx';info.value.save_as(target)
   workbook=load_workbook(target)
   assert workbook['Varianten'].max_row==3
   assert workbook['Varianten']['C2'].value=='IT'
   assert workbook['Varianten']['G2'].value=='Classico'
   assert workbook['Übersicht'].max_row==7
   workbook.close()
   with page.expect_download() as info:page.get_by_role('button',name='Alle Märkte als Excel-Paket ↓').click()
   package=qa/'snapshot-all.zip';info.value.save_as(package)
   with zipfile.ZipFile(package) as z:assert set(z.namelist())=={'Varianten-Ist-IT.xlsx','Varianten-Ist-DE.xlsx'}
   page.locator('#snapViewComparison').click()
   page.wait_for_function("document.querySelector('#snapCompareTable').innerText.includes('Einheitliche Variation')")
   assert 'Gruppe A' in page.locator('#snapCompareTable').inner_text()
   page.screenshot(path=str(qa/'snapshot-overview.png'),full_page=True)
   page.locator('#snapUKFile').set_input_files({'name':'UK.csv','mimeType':'text/csv','buffer':f'ASIN;Name\n{A};UK Product'.encode()})
   page.wait_for_function("document.querySelector('#snapUKPreview').innerText.includes('1 ASINs')")
   page.locator('#snapIEFile').set_input_files({'name':'IE.csv','mimeType':'text/csv','buffer':f'ASIN;Name\n{B};IE Product'.encode()})
   page.wait_for_function("document.querySelector('#snapIEPreview').innerText.includes('1 ASINs')")
   assert '2 eindeutige ASINs' in page.locator('#snapPreview').inner_text()
   page.get_by_role('button',name='UK-/IE-Listen zu dieser Aufnahme hinzufügen',exact=True).click()
   page.wait_for_function("document.querySelector('#snapJobStatus').innerText.includes('4 / 6')")
   job=app.snapshot_jobs()[0];_,items=app.snapshot_data(job['id'])
   assert len(items)==6 and sum(i['status']=='Gelesen' for i in items)==4
   assert [(i['market'],i['asin']) for i in items[-2:]]==[('UK',A),('IE',B)]
   # Re-render a previously stored singleton with a style label; no Amazon rescan.
   with app.db() as c:
    row=c.execute('SELECT result FROM snapshot_items WHERE job_id=? AND market=? AND asin=?',(job['id'],'IT',A)).fetchone()
    result=json.loads(row['result']);result['asins']=[A];result['variants']=[v for v in result['variants'] if v['asin']==A]
    c.execute('UPDATE snapshot_items SET result=?,found=1 WHERE job_id=? AND market=? AND asin=?',(json.dumps(result),job['id'],'IT',A))
   page.locator('#snapViewResults').click()
   page.wait_for_function("document.querySelector('#snapTable').innerText.includes('Keine Variation – Einzelprodukt')")
   page.get_by_role('button',name='Varianten ansehen').first.click()
   page.wait_for_function("document.querySelector('#detailbody').innerText.includes('Keine Variation – Einzelprodukt')")
   assert 'Classico' in page.locator('#detailbody').inner_text()
   page.locator('#detail button').first.click()
   assert app.families()==[]
   browser.close()
  (qa/'snapshot-qa.json').write_text(json.dumps({'ok':True,'checks':['CSV upload and preview','Selected IT + DE Cartesian product','No selection disables start','Live progress and persisted results','Child ASIN style/color/size display','Filter does not limit export','One XLSX per market','ZIP contains both markets','Deduplicated family export','No Soll modifications']},indent=2))
 finally:server.shutdown()

if __name__=='__main__':
 with tempfile.TemporaryDirectory() as tmp:
  os.environ['LOCALAPPDATA']=tmp
  main()
