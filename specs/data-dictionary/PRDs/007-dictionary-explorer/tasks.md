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
- [ ] Task 7 — Requirement 8, Decision 8, Decision 16 / Acceptance 2, Acceptance 3: hareket azaltma
  tercihi açıkken de haritanın çizim döngüsü, radar beklemesi, yolculuk ve bilgi satırı adımları,
  pusulanın dönüşü ve bulutsu kayması sürer; soru çubuğu kayar. Önce tercihi açık öykünen başarısız
  testler, sonra motor, `CosmosMap.tsx`, `ExplorerPage.tsx` ve `explorer.css` değişikliği. Kanıt:
  `app/frontend/src/lib/cosmos/engine.test.ts`, `app/frontend/src/pages/ExplorerPage.map.test.tsx`,
  `e2e/data-dictionary/01-explorer.mjs`, `scripts/quality-gate.sh all`. Durum (2026-10-14): kod ve
  testler yazıldı; ön yüz kapsayıcısında Vitest 37 dosya / 297 test, ESLint ve tip denetimi geçti;
  yerel yığında "hareketi azalt" yanıtı açık verilirken harita, pusula, radar beklemesi ve soru
  çubuğunun kayması tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve
  `e2e/data-dictionary/01-explorer.mjs` çalıştırılmadı (çevrimdışı E2E paketi ve `kt-iskelet` yok).
- [ ] Task 8 — Requirement 1, 18, Decision 2, API sözleşmesi / Acceptance 1, Acceptance 2,
  Acceptance 3, Acceptance 5: ana ekran ve explorer uçları oturumsuz çalışır, uçlar geçerli
  `X-Device-Id` ister (yoksa `400 device_id_required`), ana ekran üst çubuğunda oturum alanı yoktur,
  `/admin` giriş ister; uygulama anonymous-visitor ile birlikte
  ([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)). Önce
  başarısız testler (`tests/integration/test_explorer_api.py`, ön yüz testleri,
  `e2e/data-dictionary/01-explorer.mjs`), sonra router, rota ve üst çubuk değişikliği; OpenAPI ve
  ön yüz tipleri yeniden üretilir. Kanıt: `scripts/quality-gate.sh all`, yerel yığında oturumsuz
  tarayıcı senaryosu. PRD yeniden kabul edilmeden başlamaz.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
