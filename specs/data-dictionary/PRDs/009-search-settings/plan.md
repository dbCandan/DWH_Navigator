# Plan — search-settings

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama üç parçadır: backend
(ayar şeması ve deposu, arama indeksinin yaşam döngüsü ve değişiklik sırası, uçlar, hazırlık
denetimi, gözlemlenebilirlik), motoru ve ayarları okuyan yeteneklerin bağlanması
([question-analysis](../004-question-analysis/PRD.md), [dictionary-explorer](../007-dictionary-explorer/PRD.md))
ve ön yüzdeki yönetim ekranı kabuğu ile Arama ve cevap ve Bakım sayfaları.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Ayar şeması | `app/backend/app/services/search_settings_schema.py` (5 bölüm, 24 alan, denetim ve iletiler, etkin değer, motor ayarı, özet) | 1, 3, 4, 7, 8, Decision 1, 2, 16 |
| Model ve göç | `domain/models/search_setting.py`, `schema/alembic/versions/202610080005_search_settings.py` | 4, Veri ve geçiş |
| Depo | `infrastructure/repositories/search_setting_repository.py` | 4, 6 |
| Girdiler | `services/search_inputs.py` (tek tutarlı görüntüden okuma, girdi kimliği) | 9, 15 |
| İndeks | `services/search_index.py` (açılış, değişiklik sırası, önce kur sonra yaz, kelime indeksinin yeniden kullanımı, durum, `stale`) | 9-15, Decision 3, 4, 6-9, 13-15 |
| Servis | `services/search_settings_service.py`, `services/search_status.py` | 2, 3, 6, 14, 15, 26 |
| API | `api/search/router.py`, `api/search_index_dependency.py`, `schemas/search/settings.py` | API sözleşmesi, 26 |
| Uygulama | `app/main.py` (süreç başına tek indeks, arka planda ilk kurulum), `api/health.py` (hazırlık ilk motoru bekler) | 10, Decision 7 |
| Gözlemlenebilirlik | `core/telemetry.py` (kurulum ve değişiklik sayaçları, süre dağılımı, hazır göstergesi, `search_change.apply` ve `search_index.build` aralıkları) | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Yönetim kabuğu, komut paleti, çekmece, taslak çubuğu, Arama ve cevap, Bakım, `tr.json` | 17-25 |

## Kararların uygulaması

- Requirement 9: Girdi kimliği sözlük sürümü ve içerik özeti, iki listenin başlık kaydındaki
  içerik özeti ve etkin ayarların özetidir. Durum ucu kimliği kayıtları okumadan karşılaştırır;
  kayıtların elle değiştirilmesi kimliği değiştirmez, sözlüğün okuma işlevi onu
  `dictionary.integrity_mismatch` ile bildirir.
- Requirement 10: İlk kurulum, iskeletin hazırlık denetimi veritabanını hazır bulana kadar saniyede
  bir bekler; bu sırada değişiklikler sırada bekler. Geçersiz saklı ayar ya da başarısız ilk kurulum
  süreci 1 çıkış koduyla durdurur.
- Requirement 11: Sıra süreç içindeki tek kilittir; 20 saniyeden uzun bekleyen istek 503 alır.
  Başlamış değişiklik ayrı bir görevde yürür ve isteği yapan bağlantı koparsa da tamamlanır. Kasıtlı
  bir ret (ör. `dictionary_import_in_progress`) son başarısız deneme sayılmaz.
- Requirement 12 ve 13: Motor ayrı iş parçacığında kurulur; kelime indeksi (BM25) yalnız sözlük,
  durak kelimeler ve altı `indeks` alanı aynıysa önceki motordan alınır, açılışta ve elle kurmada
  her zaman baştan hesaplanır. Kolon özellikleri motorun içerik anahtarlı önbelleğinden gelir.
- Requirement 15: `running` (süren değişikliğin türü ve başlangıcı) ve `last_failure` (son başarısız
  denemenin türü ve zamanı) alanları `{trigger, at}` biçimindedir.
- Requirement 2: Hizmetteki motorun ayarlarını veren okuma işlevi `SearchIndex.settings_values`'tır;
  durum ucundaki `shortlist` question-analysis ile bağlanır.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_admin_parity.py` (şema ve varsayılanlar kaynakla); parmak izi ve
  motor çıktıları `tests/parity/test_parity.py`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1, 3, 4, 7, 8 | `tests/unit/test_search_settings_schema.py`, `tests/parity/test_admin_parity.py` |
| 2-6, 26 | `tests/integration/test_search_settings_api.py` |
| 9-15 | `tests/unit/test_search_index.py`, `tests/integration/test_search_settings_api.py`, `tests/integration/test_dictionary_api.py`, `tests/integration/test_vocabulary_api.py` |
| 10 (hazırlık) | `tests/unit/test_readiness.py`, `tests/integration/test_search_settings_api.py` |
| Gözlemlenebilirlik | `tests/integration/test_search_index_signals.py` |
| 16 | question-analysis kayıtlı cevap uçları `tests/integration/test_analysis_jobs_api.py`; Bakım sayfası `app/frontend/src/pages/admin/MaintenancePage.test.tsx` |
| 17-25 | `app/frontend/src/pages/admin/SearchSettingsPage.test.tsx`, `app/frontend/src/pages/admin/MaintenancePage.test.tsx`, `app/frontend/src/components/admin/AdminShell.test.tsx` |
