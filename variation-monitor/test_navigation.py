import unittest
from unittest.mock import Mock
from core import navigate_product, scan_page, market_product_url

class NavigationTests(unittest.TestCase):
    def test_first_success_has_no_delay_or_extra_navigation(self):
        page=Mock()
        navigate_product(page,'https://www.amazon.fr/dp/B0B4HXDZWZ?language=fr_FR')
        self.assertEqual(page.goto.call_count,1)
        page.wait_for_timeout.assert_not_called()

    def test_transient_errors_retry_same_market_url_in_same_tab(self):
        for error in ('net::ERR_FAILED','Timeout 35000ms exceeded','net::ERR_CONNECTION_RESET'):
            page=Mock();page.goto.side_effect=[RuntimeError(error),None,None]
            url=market_product_url('FR','B0B4HXDZWZ')
            navigate_product(page,url)
            self.assertEqual([c.args[0] for c in page.goto.call_args_list],[url,'about:blank',url])
            page.wait_for_timeout.assert_called_once_with(2000)

    def test_persistent_error_does_not_extract_stale_product(self):
        page=Mock();page.goto.side_effect=RuntimeError('net::ERR_FAILED at example\nCall log: lengthy internal trace')
        with self.assertRaisesRegex(RuntimeError,'nach 2 Ladeversuchen') as caught:
            scan_page(page,'FR','B0B4HXDZWZ')
        self.assertEqual(page.goto.call_count,3)
        page.evaluate.assert_not_called()
        self.assertNotIn('Call log',str(caught.exception))

    def test_persistent_timeout_is_understandable(self):
        page=Mock();page.goto.side_effect=RuntimeError('Timeout 35000ms exceeded')
        with self.assertRaisesRegex(RuntimeError,'Zeitüberschreitung'):navigate_product(page,'url')

    def test_unrelated_error_is_not_retried(self):
        page=Mock();page.goto.side_effect=RuntimeError('Target page has been closed')
        with self.assertRaisesRegex(RuntimeError,'closed'):navigate_product(page,'url')
        self.assertEqual(page.goto.call_count,1)
