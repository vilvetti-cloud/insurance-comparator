# Ссылки на официальные правила КАСКО

Исходные ссылки, по которым скачаны PDF в `data/sources/`.

| Компания | Файл в `data/sources/` | Ссылка |
|---|---|---|
| РЕСО-Гарантия | `reso/technical.pdf` | https://reso.ru/export/sites/reso/individual/auto/kasko/sredstv-avtotransporta-03022025.pdf |
| ВСК | `vsk/technical.pdf` | https://www.vsk.ru/cms/assets/1179953c-dc8f-45f9-9d46-8eaba56b9c10 |
| Ингосстрах | `ingos/technical.pdf` | https://www.ingos.ru/docs/prav_strakh_ts-13-05-2025.pdf |
| Ингосстрах | `ingos/supporting/ingos-gap-2025.pdf` | https://www.ingos.ru/docs/pravila_strahovania_dop_rashodov_gap-2025.pdf |
| Ренессанс Страхование | `renins/technical.pdf` | https://www.renins.ru/Media/Default/doc/rules_new/49.pdf |
| Ренессанс Страхование | `renins/supporting/ren-2.pdf` | https://www.renins.ru/Media/Default/doc/rules_new/50.pdf |
| Ренессанс Страхование | `renins/supporting/ren-3-accident.pdf` | https://www.renins.ru/Media/Default/doc/rules_new/133.pdf |
| Ренессанс Страхование | `renins/supporting/ren-4-gap.pdf` | https://www.renins.ru/Media/Default/doc/rules_new/107.pdf |
| АльфаСтрахование | `alfa/supporting/alfa-gap.pdf` | https://www.alfastrah.ru/upload/iblock/464/464485b507cb3ecec4aa8cb7c87f932f.pdf |
| АльфаСтрахование | `alfa/technical.pdf` | https://www.alfastrah.ru/upload/iblock/da8/6hxelk9vq4cnlhue3okjcluz1lowk2k0.pdf |
| Согласие | `soglasie/technical.pdf` | https://api.soglasie.ru/storage/managed/pravila_strahovania/4/%D0%9F%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0%20%D1%81%D1%82%D1%80%D0%B0%D1%85%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F.pdf |
| Росгосстрах | `rgs/technical.pdf` | https://www-data.rgs.ru/upload/iblock/c24/g1xtpnmp9yuzbacb6jrcwrxd1wf7ljyv/171_-Pravila_24022026.pdf |
| Т-Страхование | `t-insurance/technical.pdf` | https://cdn.tinsurance.ru/static/documents/kasko_15072024.pdf |
| СберСтрахование | `sber/technical.pdf` | https://sberbankins.ru/upload/iblock/257/Pravila-dobrovolnogo-strakhovaniya-transportnykh-sredstv-_-85.1.pdf |
| СберСтрахование | `sber/supporting/sber-349-2020.pdf` | https://sberbankins.ru/upload/iblock/750/-349-ot-25.11.2020.pdf |
| СберСтрахование | `sber/supporting/sber-gap-16-1.pdf` | https://sberbankins.ru/upload/iblock/c2c/zjn30vv4p5vsvvmr88nfnm5vne7amz1t/Pravila-strakhovaniya-finansovykh-riskov-vladeltsev-transportnykh-sredstv-GAP-_-16.1.pdf |
| Совкомбанк Страхование | `sovcom/technical.pdf` | https://sovcomins.ru/upload/pravila/kasko_11_23.pdf |
| Югория | `yugoria/technical.pdf` | https://ugsk.ru/pravila/%D0%9F%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0%D0%9A%D0%90%D0%A1%D0%9A%D0%9E_04_%D1%80%D0%B5%D0%B4.9.0.pdf |

Каждую ночь `scripts/check_sources.py` скачивает все файлы из этой таблицы и сравнивает их
с копиями в `data/sources/`. Если ссылка меняется, обновите её здесь.
