# Görevler — dictionary-explorer

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 3, 10, 11, 19, Decision 1, 2, 9 / Acceptance 1: Evren verisi, tablo
  arama ve tablo ayrıntısı uçları, roller, indeks hazır değilken 503, analiz sürerken beklememe,
  içerik katmanının ayrı iş parçacığında çalışması, kaynakla fark testi, telemetri ve içerik
  sızmaması, API tanım dosyası ve ön yüz tipleri. Kanıt: `tests/integration/test_explorer_api.py`,
  `tests/parity/test_explorer_parity.py`, `tests/unit/test_explorer_telemetry.py`,
  `scripts/quality-gate.sh all`.
- [x] Task 2 — Yerel yığında deneme (sahte model kanıtı, kabul değil): Evren verisi, arama, tablo
  ayrıntısı, 404, 422 ve oturumsuz 401.
- [ ] Task 3 — Requirement 1, 2, 4-9, 12-18 / Acceptance 2: ana ekran kabuğu, durum göstergesi,
  harita, yolculuk, tablo dosyası, ad eşleme, Vitest testleri (ön yüz dalgası).
- [ ] Task 4 — Acceptance 3: yerel Compose'da klavyeyle ve tarayıcıyla senaryo.
- [ ] Task 5 — Acceptance 4: nonprod'da gerçek sözlükle harita ve arama süresi (ayrı kullanıcı
  talimatı).
- [ ] Task 6 — Acceptance 5: görsel eşdeğerlik ekran görüntüleri.
