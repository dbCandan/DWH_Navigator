# Plan — dictionary-management

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama üç parçadır: backend
(veri modeli, ortak güvenli Excel okuyucusu, içe/dışa aktarma ve sözlük gezgini uçları, okuma işlevi,
betik, gözlemlenebilirlik), içe aktarmanın [search-settings](../009-search-settings/PRD.md) değişiklik
sırasından geçmesi ve ön yüzdeki Sözlük sayfası.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/dictionary.py` (durumlar, kanallar, sınırlar, iletiler) | 2, 5, 6, 8, 11, 14 |
| Model ve göç | `domain/models/dictionary.py`, `schema/alembic/versions/202610080003_dictionary_versions.py` | 8, 14, Veri ve geçiş, Decision 8 |
| Ortak okuyucu | `infrastructure/excel/reader.py` (bellekte açma, açılmış boyut, adlı sayfa, satır ve sütun sınırı, `defusedxml`), `infrastructure/excel/writer.py` (formül değil metin, bellekte yazma) | 2, 12, Decision 7, 10 |
| Ayrıştırma | `services/analysis/dictionary_workbook.py` (`from_sheets`, `export`; kaynaktan taşınan kod), `services/dictionary_import.py` (sözlüğün sınırları, yeni uyarı) | 1, 3-7, 12, Decision 1, 5 |
| Depo | `infrastructure/repositories/dictionary_repository.py` (kayıtları şablon biçiminde okuma, yazma, budama, içe aktarma kilidi) | 8, 10, 14, 18 |
| Okuma işlevi | `services/dictionary_reading.py` | 10, 11, 17 |
| Servis | `services/dictionary_service.py` (durum, tablolar, içe/dışa aktarma, şablon) | 2-15, 18 |
| API | `api/excel_transfer.py` (yükleme biçimi ve indirme), `api/dictionary/router.py`, `schemas/dictionary/management.py` | 2, 15, 18, API sözleşmesi |
| Betik | `app/backend/app/scripts/dictionary.py` | 16 |
| Gözlemlenebilirlik | `core/telemetry.py` (sayaçlar, süre dağılımı, etkin sözlük göstergeleri, `dictionary import` aralığı) | Gözlemlenebilirlik |
| Kenar | `app/infra/nginx/nginx.local.conf` (`client_max_body_size 20m`) | Dağıtım etkisi |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Sözlük sayfası, bırakma alanı, tablo çekmecesi, bildirimler, `tr.json` | 13, 15 |

## Kararların uygulaması

- Decision 1: Kaynağın ayrıştırma kodu `services/analysis/` altında değişmeden durur; içe aktarma
  sayfaları yeni okuyucuyla okur ve aynı `from_sheets` kontrolünden geçirir. Yeni sınırlar ve yeni
  uyarı bu kodun dışında (`services/dictionary_import.py`) uygulanır; fark testi kaynak koduyla
  karşılaştırır.
- Requirement 6: Yeni uyarılar önce Objeler, sonra Kolonlar şablon sırasıyla eklenir; Objeler'de
  `ObjectKey` ile `DatabaseName`/`SchemaName`/`ObjectName` üçlüsünden biri bulunduğunda öteki için
  uyarı verilmez.
- Requirement 8: Yazma `pg_try_advisory_xact_lock` ile alınan tek kilidi bekletmeden dener; kilit
  yalnız yazma işleminde tutulur. Ekrandan gelen içe aktarmalar ayrıca süreç içindeki değişiklik
  sırasında tek tek işlenir; betik aynı kilidi kullanır.
- Requirement 9: İçe aktarma değişiklik sırasına girince yeni sözlükle motor kurulur, sonra sürüm
  yazılır. Aynı içerikte yazma yoktur; motor etkin sürümden kurulmamışsa yeniden kurulur.
- Requirement 10: Okuma işlevi kayıtları sayfa sırasıyla şablon alanları ve ek sütunlarla
  (`props.extra_cells`, sürümün başlık sırası) yeniden kurar; içerik özeti her okumada hesaplanır.
- Requirement 18: Tablo anahtarı yol parametresidir (`{table_key:path}`); `/` içeren anahtar
  yüzde kodlamalı ya da düz gelebilir.
- Hata iletisi PRD'de yazmayan iki kod için metin: `unsupported_media_type` "Dosya Excel (.xlsx)
  olarak gönderilmeli.", `dictionary_table_not_found` "Tablo sözlükte yok.".

## Doğrulama

- Backend: `scripts/quality-gate.sh all` (PostgreSQL'li tam kapı).
- Göç: `scripts/db.sh validate`; geri alıp yeniden uygulama
  `tests/integration/test_data_dictionary_model.py`.
- Fark testi: `tests/parity/test_parity.py` (sözlük ayrıştırması kaynak anlık görüntüsüyle).
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1, 3-7, 12 | `tests/unit/test_dictionary_import.py`, `tests/unit/analysis/test_dictionary_workbook.py`, `tests/parity/test_parity.py` |
| 2 | `tests/unit/test_excel_reader.py`, `tests/unit/test_excel_upload.py`, `tests/unit/test_dictionary_import.py`, `tests/integration/test_dictionary_api.py` |
| 8-11, 14, 17, 18, Decision 3 | `tests/integration/test_dictionary_api.py` |
| 16 | `tests/integration/test_dictionary_script.py` |
| Veri ve geçiş | `tests/integration/test_data_dictionary_model.py` |
| Gözlemlenebilirlik | `tests/unit/test_dictionary_telemetry.py`, `tests/integration/test_dictionary_api.py` |
| 13, 15 | Ön yüz testleri (açık görev) |
