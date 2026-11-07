# Görevler — llm-connection

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1-5, 14-16, 20, 21 / Acceptance 1 (backend kısmı): üç tipli ayar,
  `llm_integration` tablosu ve göçü, şifreli ve adres kökenine bağlı anahtar, tek aktif sohbet
  modeli (kısmi benzersiz dizin, `replace`, eşzamanlı aktif etmede 409), yazılımsal silme, model
  listesi, envanter ve bağlantı testi uçları, etkin bağlantının her analizde okunması
  (`LlmGateway.snapshot`). Kanıt: `scripts/quality-gate.sh all`,
  `tests/integration/test_llm_integrations_api.py`, `tests/integration/test_llm_data_model.py`.
- [x] Task 2 — Requirement 6, 7, 8, 13 / Acceptance 2: `httpx` bağdaştırıcısının istek gövdeleri,
  uyarlama ve onarım tekrarları kaynak `76e21a3` ile yan yana bayt bayt aynı (23 senaryo). Kanıt:
  `tests/llm_parity/test_llm_parity.py` ve kaynak kopyasıyla `--check` koşumu.
- [x] Task 3 — Requirement 9-12, 17 / Acceptance 3: özel ağ, TLS, vekil yok, yönlendirme yok,
  4 MiB, süreler ve üst süreler, durdurma, sağlık denetimi ve önbelleği, süreç geneli sınır.
  Kanıt: `tests/unit/test_llm_adapter.py`, `tests/unit/test_llm_call_slots.py`.
- [x] Task 4 — Requirement 18, 22 ve Gözlemlenebilirlik / Acceptance 4 (backend kısmı): çağrı
  özeti, `llm.call`, `llm.probe`, `llm_integration.changed`, `llm_integration.key_unreadable`,
  ölçüm adları ve etiket kümeleri, aralık öznitelikleri, işaret dizesi sızıntı testleri.
- [x] Task 5 — Dağıtım etkisi (yerel): ayarların `.env.example` ve Compose ortam bloğu,
  `httpx` ve `cryptography` kabul kaydı, kubernetes-delivery Requirement 17'deki `local-egress`
  geçidi. Kanıt: `python3 scripts/check-config-sync.py`, `scripts/check-dependency-admission.py`,
  `tests/infra/local-egress.test.sh`.
- [x] Task 6 — Requirement 5, 11 ve 18'in motor tarafı: question-analysis motorunun model
  portunu (`app/backend/app/services/analysis/llm/port.py` `LLMClient`) `LlmGateway` ve
  `OpenAICompatibleAdapter`'a bağlayan işe özgü görünüm
  (`app/backend/app/services/analysis/model_view.py`). Kanıt:
  `tests/unit/analysis/test_model_view.py`, `tests/integration/test_analysis_jobs_api.py`.
- [x] Task 7 — Requirement 18: analiz kaydındaki çağrı özetleri ve model kullanımı toplamları
  (analysis-records tablosuyla birlikte). Kanıt: `tests/integration/test_analysis_jobs_api.py`,
  `tests/unit/analysis/test_steps.py`.
- [x] Task 8 — Requirement 19 / Acceptance 5: Yapay zekâ sayfası (etkin model kartı, entegrasyon
  kartları, düzenleyici ve envanter çekmeceleri, onaylar ve bildirimler), kabuktaki rozet, sistem
  durumu satırı ve Ctrl K'daki iki eylem; Vitest testleri, OpenAPI ve üretilmiş tiplerin güncelliği.
  Sohbet modeli öneri listesi tarayıcının çizdiği `datalist` yerine temaya uyan `SuggestCombobox`'tır.
  Kanıt: `app/frontend/src/pages/admin/AiPage.test.tsx`, `scripts/quality-gate.sh frontend`.
- [x] Task 9 — Dağıtım etkisi (nonprod): `deploy-hooks.sh`'ın şifreleme anahtarını bir kez
  üretmesi, kurum kök sertifikasının imaja eklenmesi, ağ çıkış kuralı (kubernetes-delivery).
  Kanıt: `tests/helm/deploy-hooks.test.sh`, `tests/helm/values-project.test.sh`,
  `app/backend/tests/unit/test_corporate_ca.py`; sertifika release imajında sistem güven deposunda
  ve `DWHNAVIGATOR_LLM_CA_BUNDLE` ile adlandırılmış, ayar imajın içinde doğrulandı. Çıkış kuralının
  adresini ağ ekibinin doğrulaması işletim ekibindedir (kubernetes-delivery, Riskler); kümede
  erişim Task 11'de görülür.
- [ ] Task 10 — Acceptance 6 ve 7: yerel Compose'da tarayıcıyla ekle → test et → aktif et → soru
  akışı ve `nonprod` ayarlarıyla yerel koşum. Yerel çıkış kapısı ve sahte model sunucusuyla API
  düzeyinde ve tarayıcıda ekle → test et → aktif et denendi; soru adımı Task 6-7'ye bağlıdır.
- [ ] Task 11 — Acceptance 8: `vibecode-test` kümesinde RunAI ucuyla koşum (ayrı kullanıcı talimatı).
- [x] Task 12 — Acceptance 9: görsel eşdeğerlik ekran görüntüleri. Yerel Compose'da hedef ile
  kaynak `76e21a3` aynı sentetik entegrasyonlarla ve sahte model sunucusuyla (yerel çıkış kapısı)
  çalıştırıldı; sayfa, model listesi, düzenleyicinin üç adımı ve envanter masaüstü ve telefon
  genişliğinde yan yana karşılaştırıldı. Farklar yalnız model sunucusunun adresi (hedefte kapı adı,
  kaynakta makinenin kendisi), hata metninde adresin olmaması (Requirement 13) ve oturum alanıdır.
- [ ] Task 13 — Requirement 6, 8, 13, 18, Decision 20 / Acceptance 2, Acceptance 4: uzunluk
  sınırında kesilen yanıt. Önce başarısız testler: `finish_reason: "length"` taşıyan JSON olmayan
  ilk yanıtta sunucu tek istek alır, sonuç `output_truncated`, `repaired` yanlış, token'lar
  toplanır; onarım yanıtı kesilirse de `output_truncated`; kesilmiş ama geçerli JSON kabul edilir;
  `finish_reason`'sız JSON olmayan yanıt kaynaktaki gibi onarılır ve `invalid_json` olur; ölçüm
  etiket kümesi 16 sınıf; analiz sebebi "Model hatası: model cevabı uzunluk sınırında kesildi"
  (question-analysis Requirement 5). Sonra bağdaştırıcı, sınıf ve metin tabloları, OpenAPI ve ön yüz
  tipleri, analiz kayıtları etiketi. Kanıt: `tests/unit/test_llm_adapter.py`,
  `tests/llm_parity/test_llm_parity.py`, `tests/unit/test_llm_domain.py`, analiz sebebi testi,
  `scripts/quality-gate.sh all`.
  Durum (2026-11-04): testler önce kırmızı (6), sonra yeşil. Odaklı pytest 193 geçti, 1 atlandı
  (kaynak kopyası yok); ruff (EXE002 dışında), black, isort ve mypy temiz; `export-openapi.sh
  --check`, `generate-types.sh --check` ve `render-clients.sh --check` geçti; Vitest
  `analysisRecords` ve yerelleştirme anahtar denetimi geçti. Gerçek model sunucusunda (LM Studio,
  `gemma-4-26b-a4b-qat`) 20 token sınırıyla çağrı tek istekle `output_truncated` verdi, onarım
  gitmedi. Açık: `scripts/quality-gate.sh all` geçmedi: Windows bağlamasında her dosya 777
  göründüğü için ruff EXE002 verir; PostgreSQL'li 273 test, aynı çalışma ağacındaki kayıtsız
  `term_list` değişikliğinin şema sapmasıyla (`202611040001_term_list_running_per_owner.py`)
  hazırlıkta durdu; `render-charts.sh` için `kt-iskelet` yok; Vitest'te iki yönetim sayfası
  dosyasının ilk testi soğuk yüklemede 1 saniye sınırını aşıyor (sıra karıştırılınca ilk sıradaki
  başka test düşüyor).
- [ ] Task 14 — Requirement 1, 17, Decision 11 / Acceptance 3: sohbet çağrısı sınırının varsayılanı 5 (question-analysis Task 18 ile birlikte). Kanıt: ayar testi, `tests/unit/test_llm_call_slots.py`, `scripts/check-config-sync.py`.
