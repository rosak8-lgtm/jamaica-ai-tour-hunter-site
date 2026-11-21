# JAMAICA — HBX API TEST / PRUEBAS: безопасная проверка

Скриншот: Hotel API Keys → HOTELBEDS SPAIN — PRUEBAS. Это Evaluation (тестовая среда), не LIVE и не разрешение на коммерческую публикацию фотографий. По официальным правилам HBX начальная квота Evaluation — до 50 запросов в сутки. Связанных сертификатов 0: стандартные запросы Api-key + X-Signature документированы отдельно от mTLS.

Официальные источники:
- https://developer.hotelbeds.com/documentation/getting-started/
- https://developer.hotelbeds.com/documentation/hotels/content-api/how-use-content-api/
- https://developer.hotelbeds.com/documentation/hotels/content-api/photos-images/
- https://developer.hotelbeds.com/documentation/hotels/knowledge-base/certification-process/

Новый scripts/hbx_test_probe.py выполняет **ровно один** GET на https://api.test.hotelbeds.com/hotel-content-api/1.0/hotels?fields=all&language=ENG&from=1&to=10 . Тест не делает бронирований, публикации изображений, изменений цен или скачивания фото. Печатает только число тестовых гостиниц и количество путей изображений.

## Как проверить на Lenovo

API-key виден на предоставленном скриншоте. Перед боевым применением рекомендована ротация. Не отправляйте API Secret или ключ в чат, не вставляйте их в историю команд и не сохраняйте в GitHub.

Откройте терминал в актуальном клоне JAMAICA и выполните:

```bash
(
set -Eeuo pipefail
umask 077
git pull --ff-only
read -r -s -p 'HBX TEST Api-key: ' HBX_TEST_API_KEY
printf '\n'
read -r -s -p 'HBX TEST API Secret: ' HBX_TEST_API_SECRET
printf '\n'
export HBX_TEST_API_KEY HBX_TEST_API_SECRET
python3 -B scripts/hbx_test_probe.py
)
```

Ввод скрыт и не попадает в историю команд. Используйте только именно тестовые Hotel key + Secret, выданные одним аккаунтом. Если Secret на странице сразу не виден, откройте карточку Hotel API Key и документацию HBX.

При успехе появятся строки:

```text
JAMAICA_HBX_TEST_CONTENT_API=PASS
JAMAICA_HBX_TEST_SAMPLE_HOTELS=<число>
JAMAICA_HBX_TEST_SAMPLE_PHOTO_PATHS=<число>
JAMAICA_HBX_TEST_REQUESTS_USED=1
JAMAICA_HBX_IMAGE_BYTES_DOWNLOADED=0
JAMAICA_HBX_COMMERCIAL_PUBLICATION=DISABLED
JAMAICA_HBX_BOOKINGS=DISABLED
```

HTTP_401 или HTTP_403 могут означать неверные доступы, недостаточные права или исчерпание Evaluation-квоты. Не запускайте десятки повторных запросов.

## Для реального наполнения отелей на сайте

Нужно получить LIVE-доступ HBX Content API, письменное подтверждение прав на коммерческий показ фотографий на JAMAICA, и точную проверенную таблицу соответствия BG/JAMAICA hotel ID ↔ HBX code. Только после этого Oracle-адаптер сможет публиковать внешние ссылки на реальные фото. Тестовый ключ **не должен** использоваться для боевого импорта.

На Oracle в приватном credentials.env должны быть отдельные LIVE значения HBX_API_KEY и HBX_API_SECRET, а также строки HBX_API_ENV=PRODUCTION и HBX_LIVE_CONTENT_RIGHTS_CONFIRMED=yes. Эти строки не заменяют действительный договор и подтверждённую таблицу ID. Не включать продажи, платежи или бронирования от наличия тестового ключа.
