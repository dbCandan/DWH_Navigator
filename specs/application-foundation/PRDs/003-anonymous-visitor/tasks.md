# Görevler — anonymous-visitor

[Plan](plan.md) belgesinden türetildi.

- [ ] Task 1 — Requirement 4, 7, Decision 5 / Acceptance 1: `visitor` tablosu ve hesap-ya-da-ziyaretçi
  sütunları; önce göç ettirilmiş şema testi, sonra model ve üretilmiş göç. Kanıt: göç testi,
  `scripts/db.sh validate`.
- [ ] Task 2 — Requirement 2, 3, 4, Decision 1, 2, 4 / Acceptance 1: `X-Device-Id` doğrulama,
  ziyaretçi kaydı, IP ve ters DNS, oturumsuz kiracı çözümü. Kanıt:
  `app/backend/tests/integration/test_visitor_api.py`.
- [ ] Task 3 — Requirement 3, 5, 6, 7 / Acceptance 1: analiz, liste, oy ve gezgin uçlarının ziyaretçi
  sahipliği, hız sınırları ve "Soran" bilgisi; ilgili data-dictionary PRD'lerinin görevleriyle
  birlikte. Kanıt: backend tümleştirme testleri.
- [ ] Task 4 — API sözleşmesi / Acceptance 1: `OpenAPI` dışa aktarımı ve ön yüz tipleri. Kanıt:
  `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- [ ] Task 5 — Requirement 1, 2, 7, 8 / Acceptance 1: ön yüz (cihaz kimliği, oturumsuz ana ekran,
  oturum alanının kaldırılması, `/admin` girişi, "Soran"). Kanıt: Vitest testleri.
- [ ] Task 6 — Acceptance 2: yerel yığında iki tarayıcı bağlamıyla tarayıcı senaryosu. Kanıt:
  `e2e/auth/02-anonymous-visitor.mjs`, `e2e/QUALITY_MANIFEST.md` satırı.
- [ ] Task 7 — Acceptance 3: nonprod'da şirket cihazından gözlem (ayrı kullanıcı talimatı).
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
