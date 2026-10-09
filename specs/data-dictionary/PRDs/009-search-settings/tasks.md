# Görevler — search-settings

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1-8 / Acceptance 1: ayar şeması, denetim ve iletileri, yalnız değişen
  değerin saklanması, açılışta saklı değerin denetimi, parmak izine giren alanlar. Kanıt:
  `tests/unit/test_search_settings_schema.py`, `tests/parity/test_admin_parity.py`,
  `tests/integration/test_search_settings_api.py`.
- [x] Task 2 — Requirement 9-15 / Acceptance 2: açılışta veritabanından kurma ve hazırlık
  denetimi, değişiklik sırası (önce kur sonra yaz, 500, 503, bağlantı kopsa da tamamlanma), analiz
  kilidi beklememe, kelime indeksinin yeniden kullanımı, elle yeniden kurma, durum ve `stale`.
  Kanıt: `tests/unit/test_search_index.py`, `tests/integration/test_search_settings_api.py`,
  `scripts/quality-gate.sh all`.
- [x] Task 3 — Gözlemlenebilirlik: olaylar, ölçümler ve aralıklar. Kanıt:
  `tests/integration/test_search_index_signals.py`.
- [x] Task 4 — Requirement 2 ve 10'un tüketicileri: question-analysis'in `GET /status`
  (`shortlist`) ve analiz başlatmada `503 search_index_not_ready`. Kanıt:
  `tests/integration/test_analysis_jobs_api.py`.
- [ ] Task 5 — Requirement 16: Bakım sayfasının kayıtlı cevap bloğu, question-analysis'in
  `GET /saved-answers/summary` ve `DELETE /saved-answers` uçlarıyla.
- [x] Task 6 — Requirement 17-25 / Acceptance 3: yönetim kabuğunun sözlük ve indeks durumu, rozetler,
  Ctrl K'daki ayarlar ve indeks işlemi, kaydedilmemiş değişiklik çubuğu ve çıkış onayı; Arama ve
  cevap ve Bakım sayfaları; ön yüz testleri. Kanıt:
  `app/frontend/src/pages/admin/SearchSettingsPage.test.tsx`,
  `app/frontend/src/pages/admin/MaintenancePage.test.tsx`, `app/frontend/src/lib/settingsDraft.test.ts`,
  `scripts/quality-gate.sh frontend`.
- [ ] Task 7 — Acceptance 4: yerel Compose'da tarayıcıyla senaryo.
- [ ] Task 8 — Acceptance 5: nonprod'da gerçek sözlükle kurulum süreleri ve bellek (ayrı kullanıcı
  talimatı).
- [x] Task 9 — Acceptance 6: görsel eşdeğerlik ekran görüntüleri. Yerel Compose'da hedef ile
  kaynak `76e21a3` aynı sözlük ve ayarlarla çalıştırıldı; kenar çubuğu ve rozetler, komut paleti,
  tablo çekmecesi, kaydedilmemiş değişiklik çubuğu, Arama ve cevap ve Bakım masaüstü ve telefon
  genişliğinde yan yana karşılaştırıldı. Farklar yalnız ¹ işaretli metinler, "Klasörler" kartı,
  oturum alanı ve Kullanıcılar menü öğesidir.
