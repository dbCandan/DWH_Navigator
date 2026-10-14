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
- [x] Task 7 — Requirement 7'nin oy tarafı: answer-feedback'in oy uygulamasının
  `AnalysisJobs.overlay` noktasına bağlanması. Kanıt: `tests/integration/test_votes_api.py`.
- [x] Task 8 — Requirement 19-22 / Acceptance 6: soru çubuğu, ilerleme, cevap görünümü, Vitest
  testleri (ön yüz dalgası). Kanıt: `app/frontend/src/hooks/useAsk.test.tsx`,
  `app/frontend/src/components/explorer/AnswerView.test.tsx`, `app/frontend/src/pages/ExplorerPage.test.tsx`,
  `scripts/quality-gate.sh frontend`.
- [ ] Task 9 — Acceptance 7: yerel Compose'da onaylı gerçek model ucuyla tarayıcı senaryosu.
- [ ] Task 10 — Acceptance 3 ve 8: kaynak kopyasıyla `--verify-snapshot` ve gerçek sözlükle fark
  düzeneği (geliştirici makinesi, depo dışı veri).
- [ ] Task 11 — Acceptance 9: nonprod'da kurum içi model ucuyla koşum (ayrı kullanıcı talimatı).
- [x] Task 12 — Acceptance 10: görsel eşdeğerlik ekran görüntüleri. Oylar geldikten sonra yeniden
  çekildi: yerel Compose'da hedef ile kaynak `76e21a3` kopyası aynı sentetik sözlük, aynı sahte model
  ve aynı tohum oylarıyla; açılış, süren analiz, durdurulmuş analiz, analist cevabı, kayıtlı cevap,
  "Analiz yapılamadı", açık öneri satırı ve yan kartlar masaüstü ve telefon genişliğinde yan yana
  karşılaştırıldı. Farklar oturum alanından (telefonda üst çubuğun daralması) ve görüntüleyenin kendi
  oylarının basılı görünmesinden gelir.
- [x] Task 13 — Requirement 19'un tam tablo adı kısmı ve Requirement 21'deki tablo dosyası
  bağlantıları ("Kolonlar", önerilmemiş tablo adları): dictionary-explorer'ın tablo dosyasıyla birlikte.
  Kanıt: `app/frontend/src/pages/ExplorerPage.map.test.tsx`, `e2e/data-dictionary/01-explorer.mjs`.
- [ ] Task 14 — Requirement 19 / Acceptance 6: soru çubuğunun üst çizgiye kayması hareket azaltma
  tercihi açıkken de canlandırılır ([dictionary-explorer](../007-dictionary-explorer/PRD.md)
  Decision 8, Task 7 ile birlikte). Kanıt: `app/frontend/src/pages/ExplorerPage.map.test.tsx`
  ("glides the question bar up into the top line"), `scripts/quality-gate.sh all`. Durum
  (2026-10-14): test ve kod yazıldı, Vitest geçti, tarayıcıda gözlendi; `scripts/quality-gate.sh all`
  çalıştırılmadı.
- [ ] Task 15 — Requirement 19, Decision 26 / Acceptance 6, Acceptance 7: her sekme kendi analizini
  yürütür. Önce başarısız testler: yeni sekme (boş sekme belleği) başka sekmenin süren analizini
  göstermez ve kendi sorusunu başlatır; aynı sekmede yenilemede sekme belleğindeki süren işe
  bağlanılır; son durumdaki ya da `404` dönen iş için değer silinir ve sayfa boş açılır; "Durdur"
  yalnız o sekmenin işini durdurur. Sonra `app/frontend/src/lib/tabAnalysis.ts`, `useAsk.ts` ve
  `ExplorerPage.tsx` değişikliği. Kanıt: `app/frontend/src/pages/ExplorerPage.test.tsx`,
  `app/frontend/src/hooks/useAsk.test.tsx`, iki sekmeli tarayıcı gözlemi, `scripts/quality-gate.sh all`.
  Durum (2026-10-14): testler önce kırmızı, sonra yeşil; ön yüz kapsayıcısında Vitest 37 dosya / 303
  test, ESLint ve tip denetimi geçti. Yerel yığında iki sekmeyle gözlendi: birinci sekmenin analizi
  sürerken açılan ikinci sekme boş açıldı, kendi sorusunu yürüttü; her sekme yalnız kendi
  `analysis_id` değerini tuttu ve iş bitince sildi. Açık: model bağlı olmadığından eşzamanlı süren
  iki analiz ve yenilemede yeniden bağlanma tarayıcıda gözlenmedi (Vitest ile sınandı);
  `scripts/quality-gate.sh all` çalıştırılmadı (`kt-iskelet` yok).
- [ ] Task 16 — Requirement 8, 10, 11, 16, 17, 18, 23, Decision 17, 25 / Acceptance 5, Acceptance 7:
  ana ekran girişsiz çalışır; uygulama anonymous-visitor ile birlikte
  ([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)
  Requirement 3, 5, 6, 7). Önce başarısız API testleri: oturumsuz istek `X-Device-Id` ile çalışır,
  başlıksız ya da UUID 4 olmayan başlık `400 device_id_required` alır; başka cihaz kimliğinin işi,
  akışı, durdurması ve raporu `404 analysis_not_found`; ziyaretçi başına 5 açık akış; soru başlatmada
  ziyaretçi (60 saniyede 30) ve IP adresi (60 saniyede 120) sınırı; analiz kaydı ve kayıtlı cevapta
  ziyaretçi bağı; kayıtlı cevap uçları `yonetici` kalır. Sonra uçlar, iş sahipliği, `OpenAPI` ve ön
  yüz tipleri, akış ve raporun `X-Device-Id` ile alınması. Kanıt: API testleri, ön yüz testleri,
  iki tarayıcı bağlamlı gözlem, `scripts/quality-gate.sh all`. Bu PRD yeniden kabul edilmeden
  uygulanmaz.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
