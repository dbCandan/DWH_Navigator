# Plan — dictionary-explorer

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama iki parçadır: backend'de
hizmetteki arama indeksinden okuyan üç uç (Evren verisi, tablo arama, tablo ayrıntısı) ve fark
testi; ön yüzde ana ekran kabuğu, harita, yolculuk ve tablo dosyası.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Okuma | `app/backend/app/services/explorer.py` (`table_index`, `galaxy`, `search`, `table_detail`: kaynağın `App._object_index`, `App.galaxy`, `App.objects`, `App.object_detail`; motor başına bir kez kurulan tablo dizini `ExplorerIndex`) | 3, 10, 11, Decision 1 |
| API | `api/explorer/router.py`, `schemas/explorer/tables.py` | 3, 10, 11, 19, Decision 2, 9, API sözleşmesi |
| Uygulama | `app/main.py` (süreçteki tablo dizini), `services/search_index.py` (`search_index_not_ready`, analiz işleriyle ortak) | 19 |
| Gözlemlenebilirlik | `core/telemetry.py` (istek sayacı, arama süresi, `explorer search` aralığı), `explorer.search` olayı | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Kabuk, durum göstergesi, harita, yolculuk, tablo dosyası, ad eşleme, `globals.css`, `tr.json` | 1, 2, 4-9, 12-18 |

## Kararların uygulaması

- Decision 1: Uçların içeriği kaynak kodun saf işlev olarak taşınmış hâlidir; `rank_objects`
  çekirdek motordandır. Fark düzeneğinin `explorer` toplayıcısı aynı sözlük, kelime listeleri ve
  varsayılan ayarlarla 722 aramayı (altın set soruları, tablo adları ve yazım çeşitleri, `Şema.ad`,
  tam anahtar, ad ve kolon adı parçaları, boş ve kısa metin), Evren verisini ve her tablonun
  ayrıntısını kaynakla karşılaştırır (`elapsed_ms` dışında).
- Requirement 10: Arama metni gövdededir; içerik katmanı dahil bütün arama `asyncio.to_thread` ile
  ayrı iş parçacığında çalışır; hiçbir kilit alınmaz.
- Requirement 11 ve Decision 14: Tablo anahtarı yol parametresidir; yüzde kodlamalı `/` içeren
  anahtar da çözülür; hizmetteki indekste olmayan tablo 404 `table_not_found` ("Kayıt bulunamadı",
  kaynaktaki ileti) alır.
- Requirement 19: İndeks hizmette değilken üç uç da 503 `search_index_not_ready` döner.
- Gözlemlenebilirlik: Etiketler sabit kümelerdir; arama metni, tablo ve kolon adı hiçbir olaya,
  ölçüme ve aralığa girmez; `explorer.search` olayı kip, karakter sayısı, katman başına sonuç sayısı
  ve süreyi taşır.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_explorer_parity.py` (kaynak anlık görüntüsü `explorer.json`),
  yeniden kurma `python -m tests.parity.harness --verify-snapshot`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 3, 10, 11, Decision 1 | `tests/parity/test_explorer_parity.py`, `tests/integration/test_explorer_api.py` |
| 10 (kilit ve iş parçacığı) | `tests/integration/test_explorer_api.py` (`test_a_running_analysis_never_makes_a_search_wait`, `test_the_content_layer_does_not_hold_the_event_loop`) |
| 19, Decision 2 | `tests/integration/test_explorer_api.py` (`test_before_the_first_index_every_endpoint_is_not_ready`, `test_roles`) |
| Gözlemlenebilirlik | `tests/unit/test_explorer_telemetry.py` |
| 1, 2, 4-9, 12-18 | Ön yüz testleri (açık görev) |
