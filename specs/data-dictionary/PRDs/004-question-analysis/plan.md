# Plan — question-analysis

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.1). Uygulama dört parçadır: kaynaktan
taşınan çekirdek ve fark testi, analiz işi (kabul, kuyruk, canlı ilerleme, durdurma, yeniden
başlama) ile motorun model portuna bağlanması, kayıtlı cevaplar, rapor ve durum ucu ve ön yüzdeki
soru çubuğu ile cevap görünümü.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/analysis.py` (veri sınıfları), `domain/analysis_records.py` (iş durumları, akışlar, köken, sınırlar, hata kodları ve iletileri), `domain/turkish_text.py` | 1, 8, 18, 24 |
| Çekirdek | `services/analysis/` (taşınan saf modüller), `pipeline.py` `Engine.with_llm` (işin model görünümüyle motor), `trace.py` (adım anahtarı ve dinleyici) | 1, 2, 3, 5, 6, 18, 24 |
| Model görünümü | `services/analysis/model_view.py` (`JobModel`: olay döngüsünde `run_coroutine_threadsafe(port.chat)`, çağrı özeti, sınıf eşlemesi, `Cancelled`, sunucu kontrolü) | 5, 11, 24, Decision 4, 15 |
| İş ve kuyruk | `services/analysis/jobs.py` (`AnalysisJobs`: kabul, ilk gelen ilk çıkar, eşzamanlılık, aynı soru için bekleme, olay günlüğü ve akış, durdurma, kapanış ve açılış, hız ve akış sınırı, oy uygulama noktası) | 8-12, 14, 18, 23, Decision 2, 5-8, 21, 23 |
| Kayıtlı cevap | `domain/models/saved_answer.py`, `infrastructure/repositories/saved_answer_repository.py`, `services/analysis/saved_answers.py` | 13-15, Decision 3, 8, 9, 24 |
| Cevap biçimleri | `services/analysis/serialize.py` (Requirement 7 zarfı), `services/analysis/answer_record.py` (kaydın sözlükten bağımsız biçimi), `services/analysis/steps.py` (adımlar, aşamalar) | 7, 16, 18 |
| Göç | `schema/alembic/versions/202610090001_analysis_records_and_saved_answers.py` | Veri ve geçiş |
| API | `api/analyses/router.py`, `schemas/analysis/jobs.py` | 4, 7, 10, 11, 15-17, 23, API sözleşmesi |
| Uygulama | `app/main.py` (süreçteki tek iş yöneticisi, açılışta yarıda kalanlar, kapanışta yarıda kesme), `middleware/security_headers.py` (akış `no-cache`) | 10, 12 |
| Ayar | `core/config.py` (`analysis_concurrency`, `analysis_queue_limit`), `.env.example`, Compose ortam bloğu | 9, Dağıtım etkisi |
| Gözlemlenebilirlik | `core/telemetry.py` (ölçümler, `analysis.run` ve adım aralıkları) | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Soru çubuğu, ilerleme, cevap görünümü, `tr.json` | 19-22 |

## Kararların uygulaması

- Decision 2 ve 15: İşler süreç belleğindeki tek kuyruktadır; yürüyen iş motoru `asyncio.to_thread`
  ile ayrı iş parçacığında çalıştırır. Motorun model çağrıları `JobModel` üzerinden olay döngüsündeki
  llm-connection bağdaştırıcısına gider; durdurma işareti açık isteği kapatır.
- Requirement 3: İş, yürümeye başladığı anda hizmetteki motoru ve `LlmGateway.snapshot` ile etkin
  bağlantıyı sabitler; motorun kopyası (`Engine.with_llm`) yalnız o işin model görünümünü taşır.
- Requirement 9 ve 14: Kuyruk ilk gelen ilk çıkar sırasıyla yürür; `fresh` olmayan iş, aynı
  `text_key`, aynı `top` ve hizmetteki motorla yürüyen iş bitene kadar başlatılmaz, sonra kayıtlı
  cevabı arar. Kabulde kayıtlı cevapla biten iş kuyruk sınırına sayılmaz.
- Requirement 10: Her işin olayları sırayla numaralanır ve iş süresince bellekte durur. Akış
  `snapshot` ile başlar, `Last-Event-ID`'den sonraki adım olaylarını yeniden gönderir, sonra canlı
  olayları ve 15 saniyede bir `: canlı` satırını yollar; erişim belirtecinin bitişinde kapanır.
  Adım olayları ve OpenTelemetry adım aralıkları, izdeki anahtarlı adımların dinleyicisinden gelir.
- Requirement 12: Kapanışta sıradakiler ve yürüyenler `interrupted` olur (yürüyenlerin model
  bağlantısı kapatılır); açılışta bu süreçten önce kabul edilmiş `queued` ya da `running` kayıtlar
  `interrupted` yapılır.
- Requirement 7: Sonuç okunurken cevap `AnswerOverlay` uygulama noktasından geçer; answer-feedback
  oy uygulamasını buraya bağlar, hata verirse cevap oysuz döner ve `analysis.feedback_overlay_failed`
  yazılır. Oy deposu olmadığı sürece uygulama noktası cevabı değiştirmez.
- Requirement 18 ve Decision 10: Kayıtlı cevap kaynağın biçimini (`answer_cache.encode`, kolonlar
  anahtarla) taşır ve güncel sözlükle kurulur. Analiz kaydının tam cevabı aynı biçimdir ama her
  kolonun sözlük satırını içinde taşır; böylece sonraki içe aktarmalardan sonra da sonuç zarfı
  (Requirement 7) ve rapor ondan üretilir.
- "Yanıt JSON değil — onarım isteniyor" ve "Model bir özelliği reddetti — onsuz yeniden" olayları,
  bağdaştırıcı çağrının içinde yazmadığı için çağrı bitince çağrı özetinden (deneme sırası, bırakılan
  özelliğin adı) model çağrısı adımının altına yazılır.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_parity.py`; HTTP, PostgreSQL ve sahte model sunucusu üzerinden
  kaynak anlık görüntüsüyle karşılaştırma `tests/integration/test_analysis_jobs_api.py`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- Ayar yüzeyi: `python3 scripts/check-config-sync.py`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1, 2, 6 | `tests/parity/test_parity.py`, `tests/unit/analysis/` |
| 2, 3, 13 (uçtan uca) | `tests/integration/test_analysis_jobs_api.py` (`test_over_http_the_answer_and_keys_are_the_source_snapshots`, `test_a_question_runs_as_a_job_and_answers_as_the_engine_does`) |
| 4, 23 | `tests/integration/test_analysis_jobs_api.py` |
| 5 | `tests/unit/analysis/test_reasons.py`, `tests/unit/analysis/test_model_view.py`, `tests/integration/test_analysis_jobs_api.py` |
| 7, 16, 17 | `tests/integration/test_analysis_jobs_api.py`, `tests/unit/analysis/test_answer_record.py` |
| 8-12 | `tests/integration/test_analysis_jobs_api.py` |
| 13-15 | `tests/integration/test_saved_answers.py`, `tests/integration/test_analysis_jobs_api.py` |
| 18 | `tests/unit/analysis/test_steps.py`, `tests/integration/test_analysis_jobs_api.py` |
| 24 | `tests/unit/analysis/test_model_view.py` |
| Gözlemlenebilirlik, sızıntı | `tests/integration/test_analysis_signals.py` |
| Veri ve geçiş | `tests/integration/test_analysis_data_model.py` |
| 19-22 | `app/frontend/src/hooks/useAsk.test.tsx`, `app/frontend/src/components/explorer/AnswerView.test.tsx`, `app/frontend/src/pages/ExplorerPage.test.tsx`, `app/frontend/src/lib/cosmos/engine.test.ts`; tarayıcı senaryosu `e2e/question/01-ask-and-answer.mjs` |
