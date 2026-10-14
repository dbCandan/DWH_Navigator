# Plan — analysis-records

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.1.0). Uygulama üç parçadır: kayıt
tablosu ve question-analysis'in iş hizmetinin kaydı açıp güncellemesi, yönetim ekranının uçları
(liste, özet, günlük sayılar, soranlar, ayrıntı, silme) ve ön yüzdeki Genel bakış ile Analizler
sayfaları.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Model ve göç | `app/backend/app/domain/models/analysis_record.py`, `schema/alembic/versions/202610090001_analysis_records_and_saved_answers.py` | 1, 2, 12, Veri ve geçiş, Decision 10, 13, 14 |
| Kaydın yazılması | `services/analysis/jobs.py` (kabulde açma, başlarken ve bitişte tek işlemde güncelleme, son durumdan sonra değişmeme), `services/analysis/steps.py` (adım biçimi, 500 sınırı, aşama süreleri, çağrı ve token toplamları) | 1-4, Decision 5, 9 |
| Depo | `infrastructure/repositories/analysis_record_repository.py` (yalnız son durumdaki kayıtlar, süzgeçler, kaçışlı metin araması) | 5, 6, 8-11 |
| Servis | `services/analysis_records.py` (dönemler İstanbul saatiyle, `until`, kaynaktaki `quantile`, `Analyses.kpi` ve `perf` hesabı, silme olayı ve ölçümü) | 6-12, Decision 6-8, 16 |
| API | `api/analysis_records/router.py`, `schemas/analysis_records/records.py` | API sözleşmesi, 5-11 |
| Gözlemlenebilirlik | `core/telemetry.py` (`dwhnavigator_analysis_records_deleted_total`) | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Genel bakış, Analizler, çekmeceler, `tr.json` | 13-23 |

## Kararların uygulaması

- Requirement 6 ve 11: `period` verilmezse liste ve özette `7d`'dir; silmede süzgeç sayılması için
  en az bir süzgeç (dönem dahil) ya da `all=true` açıkça verilmelidir. `until` zaman dilimli ISO
  8601'dir; zaman dilimsiz değer `422 invalid_filter` alır.
- Requirement 7: Yüzdelikler sunucuda kaynaktaki `quantile` ile (sıralı değerler arasında doğrusal
  aradeğerleme, aynı kayan nokta sonucu) hesaplanır; aşama ortalaması yalnız o aşaması sıfırdan
  büyük kayıtlar üzerindendir.
- Requirement 11: Silme, kayıtlı cevabın `analysis_public_id` bağını dış anahtarın `ON DELETE SET
  NULL` eylemiyle boşaltır.
- Requirement 3: Adım öğesi `seq`, `parent`, `name`, `kind`, `key`, `start_ms`, `ms`, `status`,
  `detail` alanlarını, model çağrısı adımı ayrıca `call` (llm-connection çağrı özeti), sunucu
  kontrolü `check` alanını taşır.
- Decision 2, Requirement 2, 6, 7, 9 ve 16: soran hesap ya da ziyaretçidir; ziyaretçi bağı, kabuldeki
  IP adresi ve makine adı sütunları, "tam biri dolu" kısıtı ve ziyaretçi sahiplik dizini
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md) göçüyle
  gelir; depo hesap ve ziyaretçi için dış birleştirmeyle `kind` ve "<makine adı> · <IP adresi>"
  etiketini kurar; `GET /analysis-records/askers` ziyaretçileri de döndürür; Analizler sayfası etiketi
  gösterir (Acceptance 1, 3, 4, 5).

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1-3, 12 | `tests/integration/test_analysis_jobs_api.py`, `tests/unit/analysis/test_steps.py`, `tests/integration/test_analysis_records_api.py` |
| 4 | `tests/integration/test_analysis_signals.py`, `tests/integration/test_analysis_jobs_api.py` |
| 5-11 | `tests/integration/test_analysis_records_api.py`, `tests/unit/test_analysis_records_summary.py` |
| Veri ve geçiş | `tests/integration/test_analysis_data_model.py` |
| Gözlemlenebilirlik | `tests/integration/test_analysis_records_api.py` |
| 13-23 | `app/frontend/src/pages/admin/OverviewPage.test.tsx`, `app/frontend/src/pages/admin/AnalysesPage.test.tsx`, `app/frontend/src/lib/analysisRecords.test.ts`, `app/frontend/src/services/analysisRecords.test.ts` |
