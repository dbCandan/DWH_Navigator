# Görevler — list-search

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1-3 / Acceptance 1: okuma kurallarının taşınması, ortak güvenli
  okuyucuyla bellekte okuma, satır, sütun, terim, karakter ve açılmış boyut sınırları, ret kodları,
  `parse_term_sheet` ve dosya okuma fark testi. Kanıt: `tests/unit/analysis/test_term_lists.py`,
  `tests/parity/test_term_lists_parity.py`.
- [x] Task 2 — Requirement 13 / Acceptance 2: `write_list_report` taşınması, çalışan, durdurulmuş,
  tamamlanmış ve hatalı terimli listelerde kaynakla hücre hücre (bağlantılar dahil) aynılık, "="
  ile başlayan terimin metin kalması. Kanıt: `tests/parity/test_term_lists_parity.py`.
- [x] Task 3 — Requirement 4-10, 18, 19 / Acceptance 3: liste tabloları ve göçü, liste işi, tek tek
  sıraya verme, her terimden sonra yazma, durdurma, sürdürme, kapanış, açılış ve dakikalık
  denetimde yarıda kesilme, tek çalışan liste, güvenli hata iletisi; gerçek PostgreSQL ve sahte
  analizle. Kanıt: `tests/integration/test_term_list_runs.py`,
  `tests/integration/test_list_and_vote_data_model.py`.
- [x] Task 4 — Requirement 4, 12, 14-16 / Acceptance 4: uçlar, sahiplik ve 404, listeleme ve
  sayfalama, terim ayrıntısı (oylar uygulanmış), terim ve liste raporu, kişi başına en yeni 5 liste,
  kayıtlı cevap ve sözlük yeniden içe aktarıldıktan sonra açılma, API tanım dosyası ve ön yüz tipleri.
  Kanıt: `tests/integration/test_term_lists_api.py`, `scripts/quality-gate.sh all`.
- [x] Task 5 — Gözlemlenebilirlik / Acceptance 5'in backend kısmı: olaylar, ölçümler, etiket
  kümeleri, günlükte terim metni ve dosya adı bulunmaması. Kanıt:
  `tests/integration/test_telemetry_signals.py`, `tests/integration/test_term_lists_api.py`.
- [x] Task 6 — Yerel yığında sahte modelle uçtan uca deneme (sahte model kanıtı, kabul değil):
  yükleme, ilerleme, durdurma, ara rapor, sürdürme, liste sürerken backend'in yeniden başlatılması
  ve "yarıda kesildi", sürdürme sonrası analiz kayıtlarında cevaplanmış terimin yeniden
  sorulmaması, terim ayrıntısı ve oylar, son rapor, günlükte terim metni olmaması.
- [x] Task 7 — Requirement 17 / Acceptance 5'in ön yüz kısmı: liste arayüzü, hap, yoklama, Vitest
  testleri (ön yüz dalgası). Kanıt: `app/frontend/src/components/explorer/TermListView.test.tsx`,
  `app/frontend/src/pages/ExplorerPage.lists.test.tsx`, `scripts/quality-gate.sh frontend`.
- [x] Task 8 — Acceptance 6-8: yerel Compose'da bağlı bir sohbet modeliyle tarayıcı senaryoları.
  Kanıt: `e2e/data-dictionary/04-term-list.mjs` (Acceptance 6, 8 ve sayfanın kapatılıp açılması);
  liste sürerken backend kapsayıcısının yeniden başlatılması tarayıcıyla ayrıca denendi: liste
  "Yarıda kesildi · 2/5" göründü, "▶ Devam et" sonrası analiz kayıtlarında cevaplanmış 1. ve 2.
  terim yeniden sorulmadı, günlükte terim metni yoktu. Bağlı model yerel sahte model sunucusuydu.
- [ ] Task 9 — Dağıtım etkisi: kapanış bekleme süresi ve `Recreate` (kubernetes-delivery dalgası).
  Kapanış bekleme süresi tamam: release imajı uvicorn'u `--timeout-graceful-shutdown 3` ile
  başlatır; 3 + 20 + 5 saniye pod'un 30 saniyelik bekleme süresine sığar (kanıt:
  `tests/helm/values-project.test.sh`). `Recreate` fabrika chart seçeneğini bekliyor.
- [ ] Task 10 — Acceptance 9: nonprod'da ingress üzerinden liste ve dağıtım sırasında yarıda
  kesilme (ayrı kullanıcı talimatı).
- [ ] Task 11 — Requirement 4, 5, 7, 11, 12, 14, 15, 16, 17 / Acceptance 4, 5, 8: liste uçlarının
  oturum yerine `X-Device-Id` ile ziyaretçiyi tanıması (`400 device_id_required`), ziyaretçi
  sahipliği ve başkasına 404, 409 iletisinin ziyaretçi karşılaştırması, ziyaretçi başına 5 liste,
  analizlerin sahip ziyaretçi adına yürümesi, oyların isteği yapan ziyaretçiye göre uygulanması, ön
  yüzde başlıkla istek ve indirme; iki tarayıcı bağlamıyla tarayıcı senaryosu. Uygulama
  anonymous-visitor ile birlikte
  ([PRD](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)); bu PRD yeniden kabul
  edilmeden başlamaz.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
- [x] Task 13 — Requirement 4 / Decision 3 / Acceptance 8 (revize): kiracı geneli tek çalışan liste
  kuralı sahip (ziyaretçi/hesap) başına tek çalışan listeye çevrildi. Göç
  [202611040001_term_list_running_per_owner.py](../../../../schema/alembic/versions/202611040001_term_list_running_per_owner.py)
  kiracı geneli kısmi benzersiz dizini kaldırıp sahip başına iki yeni dizini ve
  güncellenmiş tablo yorumunu ekliyor;
  [term_list.py](../../../../app/backend/app/domain/models/term_list.py:46) modeli bu dizinleri
  taşıyor;
  [term_list_repository.py](../../../../app/backend/app/infrastructure/repositories/term_list_repository.py:73)
  `running_for_owner(tenant_id, user_id, visitor_id)` sunuyor;
  [term_lists.py](../../../../app/backend/app/services/term_lists.py:106) servisi tek 409
  mesajını kullanıyor ve `refuse_while_running` ile `resume` bu sahip başına kontrole bağlı.
  Kanıt — yerel kapsayıcıda backend paketi: `pytest -q` 1009 passed, 2 skipped (atlananlar
  ilgisiz); etkilenen testler (`test_only_one_list_runs_per_owner`,
  `test_two_owners_run_lists_at_the_same_time`, `test_two_uploads_from_one_owner_start_one_list`,
  `test_a_list_is_its_owners_alone`) geçiyor. Ön yüz: `TermListView.test.tsx` (13/13) ve
  `ExplorerPage.lists.test.tsx` (12/12) geçiyor; proje genelinde başka test dosyalarında bu
  revizyonla ilgisiz 36 başarısızlık mevcut (admin sayfalarında `role="table"` değişiklikleri),
  bu revizyonun kapsamı dışıdır. Kalan açık nokta: `scripts/quality-gate.sh all` koşumu bu
  kutuda ruff'un EXE002 kuralı yüzünden ön yüz-öncesi düşüyor; sorun Windows OneDrive →
  Docker bağlama ortamında bütün .py dosyalarına verilen `+x` bitinin etkisi, kodla ilgili
  değil. Kanıt seviyesi L1 (etkilenen alanda).
- [ ] Task 12 — Requirement 11, 15, 17 / Decision 15: ana ekran sayfa açılışında Listeler ucunu
  kendiliğinden çağırmaz; yüklenen listenin kimliği yalnız onu yükleyen sekmenin `sessionStorage`
  belleğinde tutulur; aynı sekmede sayfa yenilendiğinde hap bu kimlikle geri kurulur; sekme
  kapandığında kayıt kaybolur. Kanıt: `app/frontend/src/pages/ExplorerPage.lists.test.tsx`
  (yenilenen testler); `app/frontend/src/hooks/useTermList.ts` ve `tabAnalysis` örüntüsüne benzeyen
  tab-kapsamlı yardımcı.
- [ ] Task 13 — Requirement 5, Decision 3: farklı ziyaretçilerin listelerinin terimleri paralel analiz edilir; uygulama question-analysis Task 18'dir. Kanıt: question-analysis Task 18 testleri ve iki ziyaretçili canlı gözlem.
