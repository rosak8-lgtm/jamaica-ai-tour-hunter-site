# JAMAICA — подключение лицензированного фотофида гостиниц (HBX/Hotelbeds)

**Новый тестовый ключ «HOTELBEDS SPAIN — PRUEBAS» не является LIVE-доступом.** Для него используйте безопасную инструкцию [HBX_EVALUATION_TEST_RU.md](HBX_EVALUATION_TEST_RU.md) и `scripts/hbx_test_probe.py` (1 GET к api.test.hotelbeds.com, без публикации и покупки). Указанные ниже команды — только после получения настоящих LIVE credentials и разрешения на коммерческие изображения.

**Что подключено технически:** скрипт `scripts/hbx_licensed_hotel_photos.py` умеет получать официальные метаданные гостиниц по Hotelbeds Content API, сопоставлять их с каталогом JAMAICA по подтверждённой таблице ID и публиковать прямые HTTPS-ссылки из `photos.hotelbeds.com`, **не скачивая сами фотографии на Oracle**.

**Почему сейчас часть отелей без фотографий:** для коммерческого показа нужен отдельный договор с HBX Group (или с другим правообладателем), API Key/Secret и таблица точных соответствий `JAMAICA id -> Hotelbeds code`. Существующий доступ к выгрузке цен Библио-Глобуса не предоставил эти права. До получения прав публичный `hotel-media-feed/index.json` правильно содержит ноль гостиниц.

## Массовая подготовка сопоставлений гостиниц без подмены чужих фото

Для массового наполнения галерей требуется сопоставить гостиницы из двух независимых справочников: `JAMAICA/BG hotel_id` и `HBX hotel code`. Ручное сопоставление по 11 000 гостиницам без автоматизации неэффективно, а совпадение одного названия без проверки может привязать фотографию чужого отеля.

В репозитории есть новый **локальный генератор предварительных кандидатов**, который принимает законно полученную HBX Content API JSON-выгрузку (без отправки дополнительных запросов) и `destination-directory.json`. Он сопоставляет только **уникальные точные нормализованные названия при совпадающем ISO-коде страны**. Дубликаты и приблизительные совпадения не проходят. Результат имеет исключительно частную схему `jamaica.private.hbx-crosswalk-candidates.v1`, признак `publication_authorized=false` и обязательную отметку `REQUIRES_INDEPENDENT_PROPERTY_ID_REVIEW`.

Для запуска на Oracle после получения официального полномасштабного выгруженного каталога:

```bash
umask 077
install -d -m 700 "$HOME/.config/jamaica-hbx"
python3 -B scripts/hbx_crosswalk_candidates.py \
  --directory destination-directory.json \
  --hbx-json "$HOME/.config/jamaica-hbx/hbx-content-licensed.json" \
  --output-private "$HOME/.config/jamaica-hbx/property-crosswalk-candidates.json"
```

**Ни одна из найденных пар не становится разрешённым соответствием автоматически.** Для публикации нужна независимая проверка каждой пары (например, гостиница, местоположение, адрес, GIATA/межпоставщицкий ID, первоисточник) и реальный доказательный `identity_evidence_reference`. Только после этого отдельный закрытый `crosswalk.json` проходит `verified_map()` и становится пригодным для лицензированного импорта. Исходный Evaluation-ключ не позволяет за один день получить десятки тысяч объектов: официальная начальная квота — 50 запросов/сутки.

## Что требуется получить от поставщика

1. Коммерческий доступ к **HBX Group Hotel Content API** с правом использовать гостиничные снимки на указанном сайте JAMAICA, показывая внешние HTTPS URL.
2. Сохранённое письменное подтверждение права коммерческой публикации и срока действия. Не вставлять договор, личные данные и секреты в публичный репозиторий; в опубликованной карточке используется только обезличенный идентификатор разрешения.
3. Сопоставление отелей JAMAICA (ID Библио-Глобуса) с числовыми кодами HBX/Hotelbeds, подтверждённое документально. **Совпадение только по названию запрещено.**
4. API Key + Secret **только на Oracle** (переменные `HBX_API_KEY`, `HBX_API_SECRET`), никогда в GitHub Pages.

Файл private/grant.json (локально на Oracle, доступ только владельцу):

```json
{
  "schema":"jamaica.hbx-license-grant.v1",
  "provider":"HBX Group",
  "commercial_publication_allowed":true,
  "direct_external_image_display_allowed":true,
  "publication_site":"https://rosak8-lgtm.github.io/jamaica-ai-tour-hunter-site/",
  "public_permission_reference":"REPLACE_WITH_VERIFIED_PUBLIC_LICENSE_REFERENCE",
  "attribution_text":"REPLACE_WITH_CONTRACTUALLY_REQUIRED_HOTEL_IMAGE_CREDIT",
  "license_verified_at":"YYYY-MM-DD",
  "rights_expires_at":"YYYY-MM-DD"
}
```

Шаблон выше — **НЕ действующая лицензия**. Без заполненного и реально выданного письменного разрешения публикация запрещена.

Файл private/crosswalk.json (локально, ID только после проверки, не по догадке):

```json
{"schema":"jamaica.hbx-crosswalk.v1","mappings":[{
  "jamaica_hotel_id":"EXACT_ID_FROM_DESTINATION_DIRECTORY",
  "hotel_name":"EXACT_JAMAICA_HOTEL_NAME",
  "country":"EXACT_JAMAICA_COUNTRY",
  "hbx_code":12345,
  "hbx_verified_name":"EXACT_OFFICIAL_HBX_NAME",
  "hbx_country_code":"TH",
  "identity_evidence_reference":"REPLACE_WITH_ACTUAL_PROPERTY_MAPPING_PROOF"
}]}
```

## Запуск (только после разрешения)

```bash
umask 077
read -r -s -p 'HBX LIVE API Key: ' HBX_API_KEY; printf '\n'
read -r -s -p 'HBX LIVE API Secret: ' HBX_API_SECRET; printf '\n'
export HBX_API_KEY HBX_API_SECRET
export HBX_API_ENV=PRODUCTION HBX_LIVE_CONTENT_RIGHTS_CONFIRMED=yes
python3 -B scripts/hbx_licensed_hotel_photos.py \
  --directory destination-directory.json \
  --crosswalk "$HOME/.config/jamaica-hbx/crosswalk.json" \
  --grant "$HOME/.config/jamaica-hbx/grant.json" \
  --output-dir . --live --max-pages 250
```

### Автоматический ежедневный импорт на Oracle

Когда поставщик предоставит реальную коммерческую лицензию, таблицу ID и ключи, на сервере `ubuntu` создать приватный каталог:

```bash
install -d -m 700 "$HOME/.config/jamaica-hbx"
# Ручная установка и проверка действующих grant.json и crosswalk.json
chmod 600 "$HOME/.config/jamaica-hbx/grant.json" \
          "$HOME/.config/jamaica-hbx/crosswalk.json"
```

Создать приватный `$HOME/.config/jamaica-hbx/credentials.env` со строками `HBX_API_KEY=<действующий LIVE ключ>`, `HBX_API_SECRET=<его LIVE секрет>`, `HBX_API_ENV=PRODUCTION` и `HBX_LIVE_CONTENT_RIGHTS_CONFIRMED=yes`. **Evaluation/PRUEBAS ключ здесь запрещён.** Файл должен иметь режим `600`, каталог — `700`. **Никогда не помещать содержимое в GitHub, логи, переписку или публичный HTML.**

После этого (на Oracle, от пользователя `ubuntu`), если актуальный Git checkout уже установлен:

```bash
bash "$HOME/.local/share/jamaica-oracle-catalog/site/scripts/install_oracle_hbx_hotel_media_daily.sh"
systemctl --user list-timers jamaica-hbx-hotel-media-daily.timer --all
```

Установка не активирует расписание до успешного первого авторизованного импорта. Сервис ежедневно получает метаданные фотографий из HBX и публикует только ссылки; общий `flock` защищает рабочую ветку от одновременного обновления с пятиминутным импортом прайс-листов. **Ни один из этих шагов ещё не выполнен на Oracle без лицензии и ключей.**

После успешного запуска и проверки Git diff публиковать **только** `hotel-media-feed/index.json` и `hotel-media-feed/part-*.json` (не приватные файлы), например через привязанный к JAMAICA репозиторию deploy key. Отсутствие коммерческих прав или соответствия прекращает импорт с `HOLD`, а не подставляет чужую гостиницу. Новая картинка появится на страницах отелей и карточках путешествий после обновления индекса.

Для тестирования без API предусмотрен `--feed-json` c настоящей, законно полученной выгрузкой HBX. Никакие тестовые или выдуманные изображения не публикуются в JAMAICA.

**Источники технических спецификаций:** 
- https://developer.hotelbeds.com/documentation/hotels/content-api/
- https://developer.hotelbeds.com/documentation/hotels/content-api/use-images/
- https://developer.hotelbeds.com/documentation/getting-started/

**Ограничения:** изображение самого отеля ≠ подтверждение наличия номера. Цены, оформление, платёж и бронь не изменяются данным адаптером.
