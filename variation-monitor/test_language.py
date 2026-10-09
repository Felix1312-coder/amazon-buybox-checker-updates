import unittest
from unittest.mock import Mock
from core import MARKET_LOCALES,MARKETS,market_browser_options,market_product_url,page_language_error,evaluate,scan_page
A='B01KWTC5YW';B='B0CP983KKH'
class LanguageTests(unittest.TestCase):
    def test_all_markets_have_matching_locale_and_url(self):
        self.assertEqual(set(MARKETS),set(MARKET_LOCALES))
        for market,locale in MARKET_LOCALES.items():
            self.assertEqual(market_browser_options(market)['locale'],locale)
            self.assertTrue(market_browser_options(market)['extra_http_headers']['Accept-Language'].startswith(locale))
            self.assertIn('language='+locale.replace('-','_'),market_product_url(market,A))
    def test_italian_scan_requests_italian_and_reads_language(self):
        page=Mock();page.url=market_product_url('IT',A)
        page.locator.return_value.count.return_value=0
        page.evaluate.return_value={'title':'Prodotto','labels':[],'blocked':False,'current':A,'scripts':[],'asins':[A,B],'attributes':{'style_name':'Con doccia nasale'},'dimensions':['style_name'],'html_language':'it-IT','nav_language':'IT'}
        observation=scan_page(page,'IT',A)
        self.assertIn('language=it_IT',page.goto.call_args.args[0])
        self.assertFalse(observation['language_error'])
        self.assertEqual(observation['attributes'][A]['style'],'Con doccia nasale')
    def test_wrong_language_does_not_become_false_style_change(self):
        err=page_language_error({'html_language':'en-GB','nav_language':'EN'},'IT')
        observation={'valid':True,'asins':[A],'attributes':{A:{'style':'With nasal shower'}},'language_error':err}
        result=evaluate({A:{'attributes':{'style':'Con doccia nasale'}}},{A:observation})
        self.assertEqual(result['status'],'Unklar');self.assertNotIn('changes',result['details'][0])
    def test_wrong_language_still_detects_extra_asin(self):
        result=evaluate({A:{'attributes':{'style':'Italiano'}}},{A:{'valid':True,'asins':[A,B],'language_error':'English'}})
        self.assertEqual(result['status'],'Abweichung');self.assertEqual(result['details'][0]['extra'],[B]);self.assertTrue(result['partial'])
    def test_wrong_language_does_not_block_asin_only_checks(self):
        self.assertEqual(evaluate({A:''},{A:{'valid':True,'asins':[A],'language_error':'English'}})['status'],'OK')
    def test_correct_language_still_compares_values(self):
        result=evaluate({A:{'attributes':{'style':'Uno'}}},{A:{'valid':True,'asins':[A],'attributes':{A:{'style':'Due'}},'language_error':''}})
        self.assertEqual(result['status'],'Abweichung')
    def test_missing_and_conflicting_language_are_unclear(self):
        self.assertTrue(page_language_error({},'IT'))
        self.assertTrue(page_language_error({'html_language':'it-IT','nav_language':'EN'},'IT'))
        self.assertFalse(page_language_error({'html_language':'it-IT'},'IT'))
