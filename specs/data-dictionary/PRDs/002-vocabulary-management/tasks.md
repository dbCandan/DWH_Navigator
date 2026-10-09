# Görevler — vocabulary-management

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 2-4, 6, 7 / Acceptance 1: denetimler ve iletileri, yeni sınırlar, katı
  alan türleri, Excel okuma ve yazma, motor için okuma işlevi (45 grup, 124 biçim). Kanıt:
  `tests/unit/test_vocabulary_rules.py`, `tests/parity/test_admin_parity.py`.
- [x] Task 2 — Requirement 1, 5, 8, 9, 14, 15 / Acceptance 2: tablolar ve başlangıç göçü (üç
  durum), önce kur sonra yaz, aynı içerikte `changed: false`, son yazanın kazanması, yazılımsal
  silme, Excel içe aktarma hata kodları, roller. Kanıt: `tests/integration/test_vocabulary_api.py`,
  `tests/integration/test_data_dictionary_model.py`, `scripts/quality-gate.sh all`.
- [x] Task 3 — Requirement 10-13 / Acceptance 3: Kelimeler sayfası (terim tablosu ve çekmecesi,
  gruplu durak kelimeler, kartta biriken değişiklikler, Excel içe ve dışa aktarma) ve Vitest
  testleri. Kanıt: `app/frontend/src/pages/admin/VocabularyPage.test.tsx`,
  `scripts/quality-gate.sh frontend`.
- [ ] Task 4 — Acceptance 4: yerel Compose'da tarayıcıyla senaryo; sözlük gezgini adımı
  dictionary-explorer ile.
- [x] Task 5 — Acceptance 5: görsel eşdeğerlik ekran görüntüleri. Yerel Compose'da hedef ile
  kaynak `76e21a3` aynı başlangıç listeleriyle çalıştırıldı; iki kart, kaydedilmemiş değişiklik
  çubuğu ve terim çekmecesi masaüstü ve telefon genişliğinde yan yana karşılaştırıldı. Farklar
  yalnız "Dosya: …", "Dosya ayarları" ve oturum alanıdır.
