# Первичное наполнение CASCO

## Что изменилось

Для первого запуска добавлен отдельный workflow:

- `.github/workflows/casco-bootstrap.yml`
- `scripts/casco_bootstrap.py`

Он обрабатывает все зарегистрированные страховые компании и до 20 документов за запуск. Ночной workflow остаётся ограниченным и предназначен для проверки изменений.

## Запуск через GitHub Actions

1. Откройте репозиторий на GitHub.
2. Перейдите в **Actions → CASCO initial bootstrap**.
3. Нажмите **Run workflow**.
4. Оставьте поле `insurer` пустым, чтобы обработать все страховые.
5. Для первого запуска оставьте `retry_failed=false`.
6. Оставьте `probe_missing=true`, чтобы получить отчёт по нерешённым полям из официальных страниц и интернет-поиска.

Workflow использует следующие Secrets/Variables:

- Secret `DATABASE_URL`;
- Secret `GEMINI_API_KEY` или `GROQ_API_KEY`;
- Variable `GEMINI_MODEL` — необязательно;
- Variable `GROQ_MODEL` — необязательно.

Полный результат будет доступен в artifact `casco-bootstrap-report`.

После bootstrap workflow `Daily CASCO collection` каждую ночь дополнительно
запускает `scripts/casco_site_refresh.py`. Он проверяет официальные HTML-страницы,
сохраняет checksum и пропускает неизменившиеся страницы. Отдельный artifact
`casco-site-refresh-report` показывает опубликованные, отложенные и отклонённые
поля.

## Локальный запуск

```bash
export DATABASE_URL='postgresql://...'
export GEMINI_API_KEY='...'
python scripts/casco_bootstrap.py --max-documents 20 --probe-missing
```

Чтобы после PDF-анализа обработать нерешённые поля на официальных HTML-страницах
и публиковать только прошедшие evidence-проверку значения:

```bash
python scripts/casco_bootstrap.py \
  --max-documents 20 \
  --publish-official-site \
  --probe-missing
```

Для одного страховщика:

```bash
python scripts/casco_bootstrap.py \
  --insurer t-insurance \
  --max-documents 20 \
  --probe-missing
```

Для повторной обработки документов, предыдущая попытка которых завершилась ошибкой:

```bash
python scripts/casco_bootstrap.py \
  --max-documents 20 \
  --retry-failed \
  --probe-missing
```

## Важное поведение

- Неизменившийся документ не анализируется повторно.
- При изменении SHA-256 создаётся новая ревизия.
- Старое активное значение архивируется только после успешной проверки нового.
- При отсутствии AI-ключа детерминированные факты из точных правил всё равно могут попасть в первоначальную базу.
- Официальные HTML-страницы хранятся как отдельные source/document ревизии с `source_level=2`; их значения не могут перезаписать подтверждённое правило уровня 1.
- Неразрешённые поля не заполняются догадками.
- `--probe-missing` создаёт только отчёт для review: находки сайта и интернет-поиска не становятся активными условиями автоматически.

## После bootstrap

Проверьте:

1. artifact `bootstrap-report.json`;
2. количество `passed_fields` и `review_fields`;
3. раздел `/data-report`;
4. сравнение двух компаний через `/compare`;
5. последний успешный запуск и ошибки источников.

Если источник устарел или вернул блокирующую страницу, его нужно проверить вручную и обновить registry, а не публиковать найденный поисковый snippet как доказательство.
