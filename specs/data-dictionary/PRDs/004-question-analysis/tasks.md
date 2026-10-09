# Görevler — question-analysis

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1, 2, 6, 24 / Acceptance 1-2: kaynak modüllerin taşınması, sabit fark
  testi, sentetik sözlükte kaynak anlık görüntüsüyle 0 fark. Kanıt: `tests/parity/test_parity.py`,
  `tests/unit/analysis/`.
- [x] Task 2 — Requirement 3, 5, 24, Decision 4, 15: motorun ayrı iş parçacığında işin model
  görünümüyle çalışması; `LlmGateway.snapshot`, `run_coroutine_threadsafe`, hata sınıfı eşlemesi,
  `Cancelled`, sunucu kontrolü. Kanıt: `tests/unit/analysis/test_model_view.py`,
  `tests/integration/test_analysis_jobs_api.py`.
- [x] Task 3 — Requirement 4, 7-12, 16, 17, 23 / Acceptance 4-5 (backend kısmı): iş uçları, kuyruk,
  eşzamanlılık, canlı akış ve `Last-Event-ID`, durdurma, kapanış ve açılışta yarıda kesme, rapor,
  `GET /status`, hız ve akış sınırı. Kanıt: `tests/integration/test_analysis_jobs_api.py`,
  `scripts/quality-gate.sh all`.
- [x] Task 4 — Requirement 13-15 / Acceptance 4: kayıtlı cevap tablosu, arama, yazma, 2000 sınırı,
  unutma, temizleme, özet. Kanıt: `tests/integration/test_saved_answers.py`.
- [x] Task 5 — Requirement 18 ve Gözlemlenebilirlik / Acceptance 5: analiz kaydına yazılanlar,
  olaylar, ölçümler, aralıklar ve işaret dizesi sızıntı testi. Kanıt:
  `tests/integration/test_analysis_signals.py`, `tests/unit/analysis/test_steps.py`.
- [x] Task 6 — Dağıtım etkisi (yerel): iki ayar, `.env.example` ve Compose ortam bloğu. Kanıt:
  `python3 scripts/check-config-sync.py`. Yerel yığında sahte OpenAI uyumlu sunucuyla `curl`
  denemesi (başlat, akış, sonuç, rapor, durdur, kayıtlı cevap).
- [ ] Task 7 — Requirement 7'nin oy tarafı: answer-feedback'in oy uygulamasının
  `AnalysisJobs.overlay` noktasına bağlanması (answer-feedback dalgası).
- [ ] Task 8 — Requirement 19-22 / Acceptance 6: soru çubuğu, ilerleme, cevap görünümü, Vitest
  testleri (ön yüz dalgası).
- [ ] Task 9 — Acceptance 7: yerel Compose'da onaylı gerçek model ucuyla tarayıcı senaryosu.
- [ ] Task 10 — Acceptance 3 ve 8: kaynak kopyasıyla `--verify-snapshot` ve gerçek sözlükle fark
  düzeneği (geliştirici makinesi, depo dışı veri).
- [ ] Task 11 — Acceptance 9: nonprod'da kurum içi model ucuyla koşum (ayrı kullanıcı talimatı).
- [ ] Task 12 — Acceptance 10: görsel eşdeğerlik ekran görüntüleri.
