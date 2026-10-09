# Görevler — analysis-records

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1-3, 12, Veri ve geçiş / Acceptance 1 (backend kısmı): kayıt tablosu ve
  göçü, zorunlu blok ve fiziksel silme sapması, kaydın kabulde açılması, başlarken ve bitişte tek
  işlemde güncellenmesi, adımlar, aşamalar ve model kullanımı. Kanıt:
  `tests/integration/test_analysis_data_model.py`, `tests/integration/test_analysis_jobs_api.py`,
  `tests/unit/analysis/test_steps.py`.
- [x] Task 2 — Requirement 5-11 / Acceptance 1: liste, özet, günlük sayılar, soranlar, ayrıntı ve
  silme uçları, roller. Kanıt: `tests/integration/test_analysis_records_api.py`,
  `tests/unit/test_analysis_records_summary.py`, `scripts/quality-gate.sh all`.
- [x] Task 3 — Requirement 4 ve Gözlemlenebilirlik / Acceptance 2: işaret dizesi sızıntı testi,
  silme olayı ve ölçümü. Kanıt: `tests/integration/test_analysis_signals.py`,
  `tests/integration/test_analysis_records_api.py`.
- [ ] Task 4 — Requirement 1'in toplu arama kısmı: list-search terimlerinin kaydı (`origin=list`,
  liste kimliği, dosya adı, sıra) list-search dalgasında `AnalysisJobs.start(origin=..., list_term=...)`
  ile.
- [ ] Task 5 — Requirement 13-23 / Acceptance 3: Genel bakış ve Analizler sayfaları, Vitest testleri
  (ön yüz dalgası).
- [ ] Task 6 — Acceptance 4 ve 5: yerel Compose'da tarayıcıyla senaryo.
- [ ] Task 7 — Acceptance 6: görsel eşdeğerlik ekran görüntüleri.
