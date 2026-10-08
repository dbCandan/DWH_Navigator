# Görevler — dictionary-management

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 2, Decision 7 ve 10 / Acceptance 1-2 (backend kısmı): ortak güvenli
  Excel okuyucusu (bellekte açma, 100 MB açılmış boyut, adlı sayfa, satır ve sütun sınırı,
  `defusedxml`), yükleme biçimi (tür, 20 MB, boş gövde, dosya adı) ve formül değil metin yazan
  indirme. Kanıt: `tests/unit/test_excel_reader.py`, `tests/unit/test_excel_upload.py`.
- [x] Task 2 — Requirement 1, 3-7, 12 / Acceptance 1: şablon kontrolleri ve iletileri, yeni uyarı,
  sözlüğün sınırları, sürüm ve içerik özeti, dışa aktarma ve boş şablon. Kanıt:
  `tests/unit/test_dictionary_import.py`, `tests/parity/test_parity.py`.
- [x] Task 3 — Requirement 8-11, 14, 17, 18, Decision 3 / Acceptance 2: sürüm ve kayıt tabloları,
  tek işlemde yazma, içe aktarma kilidi (409), önce kur sonra yaz (500, 503), aynı içerik, iki
  sürümün saklanması ve budama, okuma işlevi ve elle değiştirilmiş kayıt, boş sözlük, tablo uçları,
  roller. Kanıt: `tests/integration/test_dictionary_api.py`,
  `tests/integration/test_data_dictionary_model.py`, `scripts/quality-gate.sh all`.
- [x] Task 4 — Requirement 16: `python -m app.scripts.dictionary import|export|template`. Kanıt:
  `tests/integration/test_dictionary_script.py`.
- [x] Task 5 — Gözlemlenebilirlik: olaylar, ölçümler, `dictionary import` aralığı ve işaret dizesi
  sızıntı testi. Kanıt: `tests/unit/test_dictionary_telemetry.py`,
  `tests/integration/test_dictionary_api.py`.
- [x] Task 6 — Dağıtım etkisi (yerel): yerel ters vekilde 20 MB gövde. Kanıt: yerel yığında
  `nginx -t` ve `curl` ile içe aktarma.
- [ ] Task 7 — Requirement 13 ve 15 / Acceptance 3: Sözlük sayfası, bırakma alanı, çekmece,
  bildirimler, Vitest testleri (ön yüz dalgası).
- [ ] Task 8 — Acceptance 4: yerel Compose'da tarayıcıyla senaryo (ön yüz dalgasından sonra).
- [ ] Task 9 — Acceptance 5: nonprod'da gerçek sözlükle içe aktarma (ayrı kullanıcı talimatı).
- [ ] Task 10 — Acceptance 6: görsel eşdeğerlik ekran görüntüleri.
