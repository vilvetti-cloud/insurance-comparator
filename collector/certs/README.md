# VSK TLS certificate chain

VSK serves certificates issued by Russian Trusted Sub CA. The public root was
retrieved over normally verified HTTPS from the Gosuslugi distribution CDN:
https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
Portal instructions: https://www.gosuslugi.ru/crt

DER SHA-256: `d26d2d0231b7c39f92cc738512ba54103519e4405d68b5bd703e9788ca8ecf31`
Subject/issuer: Russian Trusted Root CA, Ministry of Digital Development and Communications.
Valid until 2032-02-27 21:04:15 UTC. Retrieved 2026-09-28.

Only the CASCO client's `https://vsk.ru/` and `https://www.vsk.ru/` adapters use
this root. It is never installed system-wide and never applies to Gemini, the
database, other insurers, or redirected third-party hosts. Hostname, chain and
expiry validation remain enabled. A root-file change must update the reviewed
fingerprint. Do not use `verify=False` to recover a document.
