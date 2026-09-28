import unittest
from unittest.mock import Mock, patch
from collector.casco_transport import CascoFetcher, VskTLSAdapter, ROOT


class TransportTests(unittest.TestCase):
    def test_extra_root_is_scoped_to_exact_vsk_hosts(self):
        f = CascoFetcher()
        for url in ['https://vsk.ru/a', 'https://www.vsk.ru/cms/assets/a']:
            self.assertIsInstance(f.session.get_adapter(url), VskTLSAdapter)
        for url in ['https://vsk.ru.evil.test/a', 'https://generativelanguage.googleapis.com/a', 'https://soglasie.ru/a']:
            self.assertNotIsInstance(f.session.get_adapter(url), VskTLSAdapter)

    def test_certificate_verification_remains_required(self):
        conn = Mock()
        VskTLSAdapter().cert_verify(conn, 'https://www.vsk.ru/a', True, None)
        self.assertEqual(conn.cert_reqs, 'CERT_REQUIRED')
        self.assertEqual(conn.ca_certs, str(ROOT))

    def test_changed_root_fails_closed(self):
        with patch('collector.casco_transport.ROOT_SHA256', 'wrong'):
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                VskTLSAdapter().cert_verify(Mock(), 'https://vsk.ru/a', True, None)
