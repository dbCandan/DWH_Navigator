# Görevler — answer-feedback

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 3-7, 17 / Acceptance 1: kaynağın `test_feedback.py` testleri, eklenen
  eşik, son oy, gerekçe, sıralama, seviye, sınır ve dakika testleri, `assess`/`apply` fark testi.
  Kanıt: `tests/unit/analysis/test_feedback.py`, `tests/unit/analysis/test_feedback_limits.py`,
  `tests/parity/test_votes_parity.py`.
- [x] Task 2 — Requirement 1, 2, 10, 15, 18 / Acceptance 2: oy tablosu ve göçü, `POST /votes`,
  doğrulama, oturumdan alınan kimlik, tam metinden anahtar, cevap reddinde kayıtlı cevabın
  silinmesi, ham oyun dönmemesi, dizinle okuma, API tanım dosyası ve ön yüz tipleri. Kanıt:
  `tests/integration/test_votes_api.py`, `tests/integration/test_list_and_vote_data_model.py`.
- [x] Task 3 — Requirement 8, 9, 14 / Acceptance 3: oyların question-analysis uygulama noktasına
  bağlanması, hata dayanıklılığı, rapor, kayıt ve liste satırının etkilenmemesi, liste terimi
  oylarıyla tek sorunun karşılıklı etkilenmesi. Kanıt: `tests/integration/test_votes_api.py`,
  `tests/integration/test_term_lists_api.py`.
- [x] Task 4 — Requirement 16 ve Gözlemlenebilirlik / Acceptance 4: süresiz saklama ve yaş
  çarpanı, olaylar ve ölçümler, günlükte soru, tablo ve gerekçe bulunmaması. Kanıt:
  `tests/integration/test_votes_api.py`, `tests/integration/test_telemetry_signals.py`.
- [x] Task 5 — Yerel yığında sahte modelle deneme (sahte model kanıtı, kabul değil): iki kullanıcının
  liste terimindeki tabloya 👎 vermesiyle tablonun `rejected`'a geçmesi, liste satırının
  değişmemesi, iki cevap 👎'siyle kayıtlı cevabın silinmesi.
- [x] Task 6 — Requirement 11-13 / Acceptance 5: oy öğeleri, rozetler, bölümler ve cevap oyu, Vitest
  testleri (ön yüz dalgası). Kanıt: `app/frontend/src/components/explorer/Votes.test.tsx`,
  `scripts/quality-gate.sh frontend`.
- [x] Task 7 — Acceptance 6 ve 7: yerel Compose'da bağlı bir sohbet modeliyle üç kullanıcılı
  tarayıcı senaryoları. Kanıt: `e2e/data-dictionary/03-votes.mjs` (bağlı model yerel sahte model
  sunucusuydu; senaryo art arda iki kez geçti).
- [ ] Task 8 — Decision 2, Requirement 1, 8, 15, 19 / Acceptance 2, 6, 7: oy verenin `X-Device-Id`
  başlığından çözülen ziyaretçi olması, `answer_vote`'un hesap ya da ziyaretçiye bağlanması ve oyla
  IP adresi ile makine adının saklanıp dönmemesi, ziyaretçiye göre son oy ve `mine`, oy hız sınırı,
  testler ve tarayıcı senaryosunun girişsiz ziyaretçilerle güncellenmesi; uygulama anonymous-visitor
  ile birlikte. Kanıt: `tests/integration/test_votes_api.py`, `e2e/data-dictionary/03-votes.mjs`.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
