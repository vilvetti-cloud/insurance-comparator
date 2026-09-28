"""Insurer-specific TLS trust; normal verification stays enabled everywhere."""
import hashlib
from pathlib import Path
import ssl
from urllib.parse import urlsplit
from requests.adapters import HTTPAdapter
from collector.http_client import HttpFetcher

ROOT = Path(__file__).parent / 'certs' / 'russian_trusted_root_ca.pem'
ROOT_SHA256 = 'd26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31'


class VskTLSAdapter(HTTPAdapter):
    def cert_verify(self, conn, url, verify, cert):
        if urlsplit(url).hostname in {'vsk.ru', 'www.vsk.ru'}:
            der = ssl.PEM_cert_to_DER_cert(ROOT.read_text(encoding='ascii'))
            if hashlib.sha256(der).hexdigest() != ROOT_SHA256:
                raise ValueError('VSK CA fingerprint mismatch')
            verify = str(ROOT)
        return super().cert_verify(conn, url, verify, cert)


class CascoFetcher(HttpFetcher):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for host in ('vsk.ru', 'www.vsk.ru'):
            self.session.mount(f'https://{host}/', VskTLSAdapter())
