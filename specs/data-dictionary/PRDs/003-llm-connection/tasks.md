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
- [ ] Task 6 — Requirement 5, 11 ve 18'in motor tarafı: question-analysis motorunun model
  portunu (`app/backend/app/services/analysis/llm/port.py` `LLMClient`) `LlmGateway` ve
  `OpenAICompatibleAdapter`'a bağlayan görünüm; motor ana koda alındığında yapılır.
- [ ] Task 7 — Requirement 18: analiz kaydındaki çağrı özetleri ve model kullanımı toplamları
  (analysis-records tablosuyla birlikte).
- [ ] Task 8 — Requirement 19 / Acceptance 5: Yapay zekâ sayfası, Vitest testleri, OpenAPI ve
  üretilmiş tiplerin güncelliği.
- [ ] Task 9 — Dağıtım etkisi (nonprod): `deploy-hooks.sh`'ın şifreleme anahtarını bir kez
  üretmesi, kurum kök sertifikasının imaja eklenmesi, ağ çıkış kuralı (kubernetes-delivery).
- [ ] Task 10 — Acceptance 6 ve 7: yerel Compose'da tarayıcıyla ekle → test et → aktif et → soru
  akışı ve `nonprod` ayarlarıyla yerel koşum. Yerel çıkış kapısı ve sahte model sunucusuyla API
  düzeyindeki canlı deneme yapıldı; tarayıcı ve soru adımları Task 6-8'e bağlıdır.
- [ ] Task 11 — Acceptance 8: `vibecode-test` kümesinde RunAI ucuyla koşum (ayrı kullanıcı talimatı).
- [ ] Task 12 — Acceptance 9: görsel eşdeğerlik ekran görüntüleri.
