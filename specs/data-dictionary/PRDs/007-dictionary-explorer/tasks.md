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
- [x] Task 3 — Requirement 1, 2, 4-9, 12-18 / Acceptance 2: ana ekran kabuğu, durum göstergesi,
  harita, yolculuk, tablo dosyası, ad eşleme, Vitest testleri (ön yüz dalgası). Kanıt:
  `app/frontend/src/components/explorer/Dossier.test.tsx`, `app/frontend/src/pages/ExplorerPage.map.test.tsx`,
  `app/frontend/src/pages/ExplorerPage.test.tsx`, `app/frontend/src/lib/cosmos/`,
  `scripts/quality-gate.sh frontend`.
- [x] Task 4 — Acceptance 3: yerel Compose'da klavyeyle ve tarayıcıyla senaryo. Kanıt:
  `e2e/data-dictionary/01-explorer.mjs`, haritanın başka oturumdaki içe aktarmadan sonra yeni
  tablolarla kurulması `e2e/data-dictionary/02-dictionary-versions.mjs` (yerel sahte model).
- [ ] Task 5 — Acceptance 4: nonprod'da gerçek sözlükle harita ve arama süresi (ayrı kullanıcı
  talimatı).
- [x] Task 6 — Acceptance 5: görsel eşdeğerlik ekran görüntüleri. Yerel Compose'da hedef ile kaynak
  `76e21a3` kopyası aynı sentetik sözlük ve aynı sahte modelle; açılış, yolculuk, cevap, tablo
  dosyası (kolon aramasıyla), liste (ret, süren, durdurulmuş, terim ayrıntısı, hap) ve oy alanı
  (rozetler, bölümler, gerekçe paneli) masaüstü ve telefon genişliğinde yan yana karşılaştırıldı.
  Farklar oturum alanından ve canlandırma anlarından (ilerleme çubuğu, dönen işaret) gelir.
