# Внешние фото гостиниц JAMAICA — без загрузки на Oracle

Да. HTML-страница может содержать <img src="https://...">, и браузер туриста загрузит изображение напрямую с внешнего HTTPS CDN. На Oracle хранится только URL и описание. Прямой URL не заменяет лицензию на коммерческую публикацию.

## Порядок источников

1. Прямые лицензированные фотографии конкретного отеля из Wikimedia Commons с авторством, ссылкой на оригинал и лицензией. Пример: ASIA INTERNATIONAL HOTEL GUANGDONG, ID 102667206879 — 3 фото здания и 3 отдельные панорамы Гуанчжоу из ресторана на 45-м этаже (декабрь 2021), автор 中少, CC BY-SA 4.0. Панорамы НЕ являются фотографиями номеров, интерьеров или текущего состояния гостиницы. Файлы физически не копируются на Jamaica.
2. Разрешённые правообладателем внешние ссылки на гостиничные CDN. Запись с точным hotel ID, названием, страной и документированным разрешением заносится в hotel-media-approved.json, только после проверки коммерческих прав, допустимости hotlinking и доступности URL. До этого записи отсутствуют.
3. Если фотографий здания нет, можно показать отдельные изображения города или курорта под недвусмысленной надписью НЕ ФОТОГРАФИЯ ГОСТИНИЦЫ.

## Формат записи прав на коммерческую фотогалерею

В hotel-media-approved.json внутри hotels[hotelId] необходимы:
- hotel_name и country: точные совпадения с destination-directory.json.
- rights_verified: true, commercial_publication_allowed: true, rights_verified_at: дата YYYY-MM-DD, permission_reference: ссылка на документ разрешения (не менее 12 символов).
- approved_image_hosts и approved_source_hosts: списки точных HTTPS-доменов, например cdn.example.org и www.example.org. Примерные адреса не являются реально разрешёнными фотографиями.
- photos: массив объектов src, source, alt, credit, kind и license='contract-authorized'. Вид фото kind — exterior, room, pool, restaurant, lobby, grounds или other.
- rights_expires_at: необязательная конечная дата действия прав YYYY-MM-DD.

Пример отдельной записи photos (НЕ ДОБАВЛЯТЬ В БОЕВОЙ СПИСОК БЕЗ РЕАЛЬНОГО РАЗРЕШЕНИЯ):

    {
      "src": "https://cdn.example.org/basaya/pool.jpg",
      "source": "https://www.example.org/basaya/gallery",
      "license": "contract-authorized",
      "kind": "pool",
      "alt": "Бассейн BASAYA BEACH HOTEL & RESORT",
      "credit": "Фотограф и правообладатель, указанные в договоре"
    }

Сайт проверяет точный ID, название, страну, HTTPS, совпадение доменов, отсутствие учётных данных/токенов и срок прав. Подгрузка img — lazy, referrerpolicy=no-referrer. При ошибке внешнего CDN страница возвращается к Wikimedia Commons и не показывает сломанное изображение как действительное фото гостиницы.

## Проверенные примеры городских панорам из конкретной гостиницы

Для Asia International Hotel дополнительно проверены следующие файлы Wikimedia Commons (автор 中少, CC BY-SA 4.0):

- `Views from Guangdong Asia International Hotel 45F Revolving Restaurant to Guangzhou Central City Area on 20211217-01.jpg`
- `Views from Guangdong Asia International Hotel 45F Revolving Restaurant to Guangzhou Central City Area on 20211217-05.jpg`
- `Views from Guangdong Asia International Hotel 45F Revolving Restaurant to Guangzhou Central City Area on 20211217-33.jpg`

Каждый из них содержит вид из ресторана гостиницы, поэтому в интерфейсе используется тип `view_from_hotel` и надпись «Вид из гостиницы», а не «Номер» или «Ресторан». Источники, авторы и лицензии присутствуют в карточке каждого файла. Снимки показываются напрямую с Wikimedia, без копирования на Oracle.

## Откуда брать остальные 11 тысяч изображений

Для массового наполнения нужен лицензионный отельный фотофид, предоставляющий соответствие hotelId -> URL и право на коммерческий показ или согласованные условия встраивания. У Библио-Глобуса существует поле hotelPic, но его наличие не подтверждает права и полный охват всех гостиниц. По последней проверке приватный серверный аудит обнаружил только 1 кандидата, а не 11 тысяч.

Пока такие права не получены, изображения с Booking, Tripadvisor и других сайтов нельзя автоматически показывать на Jamaica только на том основании, что найден прямой URL.

Документация: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia/technical
Права: https://www.gov.uk/government/publications/copyright-notice-digital-images-photographs-and-the-internet/copyright-notice-digital-images-photographs-and-the-internet
