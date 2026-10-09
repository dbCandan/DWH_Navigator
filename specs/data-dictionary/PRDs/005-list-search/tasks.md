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
- [ ] Task 7 — Requirement 17 / Acceptance 5'in ön yüz kısmı: liste arayüzü, hap, yoklama, Vitest
  testleri (ön yüz dalgası).
- [ ] Task 8 — Acceptance 6-8: yerel Compose'da bağlı bir sohbet modeliyle tarayıcı senaryoları.
- [ ] Task 9 — Dağıtım etkisi: kapanış bekleme süresi ve `Recreate` (kubernetes-delivery dalgası).
- [ ] Task 10 — Acceptance 9: nonprod'da ingress üzerinden liste ve dağıtım sırasında yarıda
  kesilme (ayrı kullanıcı talimatı).
