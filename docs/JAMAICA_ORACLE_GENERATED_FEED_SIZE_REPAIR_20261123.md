# JAMAICA · Oracle GENERATED_FEED_INVALID_SIZE · 23 ноября 2026

## Наблюдение пользователя (не предположение)

Lenovo → Oracle SSH: `jamaica-oracle-catalog-5min.timer=active`.
При двух попытках сервис сообщил
`JAMAICA_ORACLE_5MIN_IMPORT_HOLD=GENERATED_FEED_INVALID_SIZE`.

Это означает, что периодический импорт не закончил публикацию свежего
каталога. **Активность таймера не равна успешной работе сервиса.**
Точный размер/наличие генерируемого файла из присланного вывода неизвестны.

## Устранённый программный разрыв

Раньше сканер мог сформировать до 60 000 описательных строк без ограничения
суммарного объёма в байтах. Publisher ожидал файл не более 45 MB и сообщал
одну и ту же общую ошибку как для отсутствующего файла, так и для
превышенного лимита.

Новый `scripts/catalog_size_budget.py` ограничивает действительный
UTF-8 JSON до 32 MB **дважды**: сразу после авторизованного чтения
прайс-листов и после объединения с 24-часовым архивом найденных вариантов.
При выборе сохраняется честное распределение *реальных* вариантов
по странам, а свежие данные имеют приоритет над архивными. Архивные
строки всегда остаются без цены, без подтверждения номеров/рейсов.
Обрезка отмечается `truncated_to_public_limit=true`.

Теперь `scripts/oracle_site_publisher.py` также печатает только
целочисленный `JAMAICA_GENERATED_FEED_BYTES`, чтобы отличить
`GENERATED_FEED_MISSING_OR_UNSAFE` от
`GENERATED_FEED_EMPTY_OR_OVERSIZED`.

## Проверка с Lenovo: без изменений Oracle

```bash
(
set -Eeuo pipefail
cd "$HOME/Загрузки/jamaica-ai-tour-hunter-site"
git pull --ff-only origin main
bash scripts/diagnose_oracle_catalog_from_lenovo.sh
)
```

Диагностика показывает только размер/наличие файла, ревизию Git,
SHA-256 серверного и GitHub publisher и разрешённые строки событий.

## Развёртывание исправления из официального репозитория

**Только после успешных GitHub CI и merge исправления**, с компьютера
Lenovo, где уже настроен ранее подтверждённый SSH-ключ:

```bash
(
set -Eeuo pipefail
cd "$HOME/Загрузки/jamaica-ai-tour-hunter-site"
git pull --ff-only origin main
python3 -B -m unittest -v \
  backend.test_catalog_size_budget \
  backend.test_oracle_site_publisher \
  backend.test_bg_preview_export
bash scripts/upgrade_oracle_catalog_on_server_once.sh
bash scripts/diagnose_oracle_catalog_from_lenovo.sh
)
```

Установщик переносит только публично проверенный код издателя,
не трогает ключи и логины, проверяет серверный Git-клон, ставит на
паузу таймер на время короткого обновления, делает резервную копию
издателя, запускает ровно одну проверку и восстанавливает таймер.
Старый опубликованный каталог не должен заменяться неподтверждёнными
данными при ошибке.

Критерий **действительного** восстановления: в журнале Oracle
встречается `JAMAICA_ORACLE_5MIN_IMPORT_PASS=YES`, статус сервиса
`success`, а `JAMAICA_ORACLE_TOUR_COUNT` /
`JAMAICA_ORACLE_COUNTRY_COUNT` согласованы с опубликованными данными.
Только успешные GitHub CI и GitHub Pages НЕ подтверждают этот результат.

**До подтверждения бронирования**: `quote_verified=false`,
`availability_verified=false`, `flight_verified=false`,
`bookable=false`; банковские платежи отключены. Увеличение каталога
не означает доступность туров во всех 251 справочных странах.
