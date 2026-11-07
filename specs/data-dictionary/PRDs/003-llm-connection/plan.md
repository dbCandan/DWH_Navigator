# Plan — llm-connection

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.2.0). Uygulama dört parçadır: backend
(veri modeli, model portu ve bağdaştırıcısı, yönetim uçları, gözlemlenebilirlik), motorun portu
kullanması ([question-analysis](../004-question-analysis/PRD.md)), çağrı özetinin analiz kaydına
yazılması ([analysis-records](../008-analysis-records/PRD.md)) ve ön yüzdeki Yapay zekâ sayfası.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/llm.py` (sabitler, hata sınıfları ve metinleri, alan kuralları, adres kökeni, `parse_json_reply`, uyarlama kuralı, bağlantı anlık görüntüsü, çağrı özeti, `LlmChatPort`), `app/backend/app/domain/turkish_text.py` (`fold`) | 1, 2, 5, 7, 8, 12, 13, 18, Decision 1 |
| Model ve göç | `domain/models/llm_integration.py`, `schema/alembic/versions/202610080002_llm_integration.py` | 2, 3, 4, 20, Veri ve geçiş |
| Bağdaştırıcı | `infrastructure/llm/network.py` (özel ağ, bağlanma süresi, TLS), `infrastructure/llm/call_slots.py` (süreç geneli sınır), `infrastructure/llm/openai_adapter.py` (gövde, uyarlama, onarım, sınıflar, sağlık önbelleği, model listesi, envanter, durdurma) | 6-14, 17, 18, Decision 5-7, 11-14 |
| Depo | `infrastructure/repositories/llm_integration_repository.py` | 2-4, 15, 21 |
| Servis | `services/llm_connections.py` (anahtar şifreleme, etkin bağlantı okuması, model durumu, `LlmGateway`, süreçteki tek bağdaştırıcı), `services/llm_integration_service.py` (Yapay zekâ sayfasının işleri) | 2-5, 12, 14-16, 20, 21 |
| API | `api/llm_integrations/router.py`, `schemas/llm/integrations.py`, `api/router.py` | API sözleşmesi, 21 |
| Çekirdek | `core/config.py` (`llm_ca_bundle`, `llm_max_concurrent_calls`), `core/telemetry.py` (ölçümler ve aralıklar) | 1, Gözlemlenebilirlik |
| Yapılandırma | `app/backend/.env.example`, `app/infra/docker-compose.local.yml` (ortam bloğu, `local-egress` geçidi, `host-gate` ve `egress` ağları), `app/infra/nginx/nginx.local-egress.conf`, `app/infra/.env.example`, `app/infra/README.md`, `tests/infra/local-egress.test.sh` | 1, Dağıtım etkisi |
| Bağımlılık | `app/backend/requirements.in` (`httpx`, `cryptography`), `requirements-dev.in`, üç kilit, `dependency-admission.json` | Dağıtım etkisi, Decision 5 |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Yapay zekâ sayfası, düzenleyici ve envanter çekmeceleri, `tr.json` metinleri | 19 |

## Kararların uygulaması

- Decision 1: Port `app/backend/app/domain/llm.py` `LlmChatPort`'tur (sohbet, sağlık denetimi, model
  listesi); `OpenAICompatibleAdapter` onu `httpx` ile uygular. Analizin bağlantı anlık görüntüsünü
  `services/llm_connections.py` `LlmGateway.snapshot` PostgreSQL'den bir kez okur (Requirement 5);
  model durumu nesnesini `LlmGateway.model_state` verir (question-analysis `GET /status`).
- Requirement 11: Durdurma, kaynak `cancel.Token` biçimindeki bir işaretle (`cancelled`,
  `on_cancel`) verilir; işaret başka iş parçacığından gelse de açık istek görevi iptal edilir,
  bağlantı kapanır ve sonuç `cancelled` olur. Yer bekleyen çağrı istek göndermez.
- Requirement 17: Sınır, olay döngüsünden ve iş parçacığından bağımsız tek süreç sınırıdır
  (`CallSlots`); motorun ayrı iş parçacığındaki çağrılar da aynı yerleri paylaşır.
- Requirement 2'nin ileti listesinde adın ve sohbet modelinin denetim karakteri için ileti yoktur;
  API anahtarı iletisinin biçimiyle "Ad geçersiz karakter içeriyor" ve "Sohbet modeli geçersiz
  karakter içeriyor" kullanılır.
- Analiz yapılamadığında gösterilen sebep metni bu PRD'de değil, question-analysis Requirement
  5'tedir (PRD 1.0.1); bu PRD sınıfı, HTTP kodunu ve test/yoklama kısa nedenini üretir.
- Kayıtta ad çözme ve özel ağ denetimi, adres ilk kez kaydedilirken ve değiştiğinde yapılır.
- Kayıtlı test sonucu (`record`) `updated_at`'i değiştirmez; bağlantı değişikliği sayılmaz.
- Requirement 8, 13, Decision 20: `domain/llm.py`'ye `LlmOutcome.OUTPUT_TRUNCATED` ve metni,
  `openai_adapter.py` `_exchange`'e `choices[0].finish_reason` okuması (geçersiz yanıt ve `"length"`
  ise onarımsız `output_truncated`), `core/telemetry.py` sonuç kümesi, `schemas/llm/integrations.py`
  sınıf listesi, analiz motorunun port sınıfı (`services/analysis/llm/port.py`) ve sebep metni
  (`services/analysis/pipeline.py`, question-analysis Requirement 5), analiz kayıtlarındaki sonuç
  etiketi (`app/frontend/src/lib/analysisRecords.ts`, `tr.json`); OpenAPI ve ön yüz tipleri yeniden
  üretilir. Fark testine kesilen yanıt senaryoları eklenir; kaynağın kaydı değişmez.
- Yerel çıkış kapısı (kubernetes-delivery Requirement 17): `app/infra/.env`'de
  `COMPOSE_PROFILES=local-egress`, `LOCAL_EGRESS_MODEL_PORT`, isteğe bağlı
  `LOCAL_EGRESS_MODEL_ADDRESS` (IPv4; boşsa bu bilgisayar) ve `LOCAL_EGRESS_MODEL_HOST` (API
  adresindeki ad; varsayılan `host.docker.internal`). Geçit tek porta ve tek adrese TCP aktarır.

## Doğrulama

- Backend: `scripts/quality-gate.sh backend`; PostgreSQL'li tam koşum `scripts/quality-gate.sh all`.
- Göç: `scripts/db.sh validate`; göçün geri alınıp yeniden uygulanması
  `tests/integration/test_llm_data_model.py`.
- Fark testi: `tests/llm_parity/test_llm_parity.py` kaydedilmiş kaynak çıktısıyla her koşumda;
  kaynak kopyası verilince (`DWHNAVIGATOR_PARITY_SOURCE_DIR`, `git archive 76e21a3`) kaynak yeniden
  çalıştırılır. Kayıt `python -m tests.llm_parity.run_source --source <kopya> --write|--check
  tests/llm_parity/snapshots/source-76e21a3.json` ile üretilir ve doğrulanır.
- Yerel çıkış kapısı: `tests/infra/local-egress.test.sh`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- Ayar yüzeyi: `python3 scripts/check-config-sync.py`; bağımlılık: `scripts/check-dependency-admission.py`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1 | `tests/unit/test_llm_settings.py`, `tests/unit/test_llm_domain.py` |
| 2, 3, 4, 16, 20, 21 | `tests/integration/test_llm_integrations_api.py`, `tests/unit/test_llm_domain.py`, `tests/unit/test_llm_connection_keys.py` |
| 5 | `tests/integration/test_llm_integrations_api.py` (`test_the_next_analysis_uses_a_newly_activated_connection`) |
| 6, 7, 8, 13 | `tests/llm_parity/test_llm_parity.py`, `tests/unit/test_llm_adapter.py`, `tests/unit/test_llm_domain.py` |
| 9, 10, 11, 12, 17 | `tests/unit/test_llm_adapter.py`, `tests/unit/test_llm_call_slots.py` |
| 14, 15 | `tests/unit/test_llm_adapter.py`, `tests/integration/test_llm_integrations_api.py` |
| 18, 22, Gözlemlenebilirlik | `tests/unit/test_llm_adapter.py`, `tests/integration/test_llm_integrations_api.py` |
| Veri ve geçiş | `tests/integration/test_llm_data_model.py` |
| 19 | `app/frontend/src/pages/admin/AiPage.test.tsx`, `app/frontend/src/components/admin/AdminShell.test.tsx` |
