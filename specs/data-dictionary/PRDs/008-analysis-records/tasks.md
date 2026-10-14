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
- [x] Task 4 — Requirement 1'in toplu arama kısmı: list-search terimlerinin kaydı (`origin=list`,
  liste kimliği, dosya adı, sıra) `AnalysisJobs.start(origin=..., list_term=...)` ile. Kanıt:
  `tests/integration/test_term_lists_api.py` (`test_term_list_end_to_end`).
- [x] Task 5 — Requirement 13-23 / Acceptance 3: Genel bakış ve Analizler sayfaları, Vitest testleri
  (ön yüz dalgası). Kanıt: `app/frontend/src/pages/admin/OverviewPage.test.tsx`,
  `app/frontend/src/pages/admin/AnalysesPage.test.tsx`, `scripts/quality-gate.sh frontend`.
- [x] Task 6 — Acceptance 4 ve 5: yerel Compose'da tarayıcıyla senaryo. Kanıt:
  `e2e/data-dictionary/05-analysis-records.mjs`; backend analiz sürerken yeniden başlatılınca kaydın
  "Yarıda kesildi" görünmesi tarayıcıyla, `analysis_record` tablosunda adres ya da makine adı sütunu
  olmaması veritabanı sorgusuyla ayrıca denendi (yerel sahte model).
- [x] Task 7 — Acceptance 6: görsel eşdeğerlik ekran görüntüleri. Yerel Compose'da hedef ile kaynak
  aynı sentetik sözlük, aynı sahte model ve aynı sorularla; Genel bakış, Analizler, ayrıntı ve
  Performans çekmeceleri masaüstü ve telefon genişliğinde. Farklar oturum alanı ile kayıt verisinden
  gelir (soranın görünen adı, adressiz sebep, süreler).
- [ ] Task 8 — Decision 2, Requirement 2, 6, 7, 9, 16 / Acceptance 1, 3, 4, 5: soranın hesap ya da
  ziyaretçi olması, kabuldeki IP adresi ve makine adının saklanması, satırda, ayrıntıda ve soran
  listesinde "<makine adı> · <IP adresi>" etiketi, ziyaretçili "Soran" süzgeci, oturumsuz isteğe 401;
  uygulama anonymous-visitor ile birlikte
  ([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)). Kanıt:
  `tests/integration/test_analysis_records_api.py`, `tests/integration/test_analysis_data_model.py`,
  `app/frontend/src/pages/admin/AnalysesPage.test.tsx`, `e2e/data-dictionary/05-analysis-records.mjs`.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
