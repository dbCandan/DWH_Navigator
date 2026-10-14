# Plan — answer-feedback

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.1.0). Uygulama üç parçadır: kaynaktan
taşınan saf ağırlıklandırma (`assess`, `apply`) ve fark testi, oy tablosu, oy ucu ve cevaplara oy
uygulaması (question-analysis'in uygulama noktası ve list-search terim ayrıntısı), ön yüzdeki oy
öğeleri.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Ağırlıklandırma | `app/backend/app/services/analysis/feedback.py` (kaynağın `assess`, `apply` ve sabitleri; saf) | 3-7, 17, Decision 1 |
| Kalıcılık | `domain/models/answer_vote.py`, `infrastructure/repositories/answer_vote_repository.py` (`question_votes`: iki anahtar dizini üzerinden okuma) | 1, 3, 16, 18, Decision 3, 13 |
| Göç | `schema/alembic/versions/202610090002_answer_votes.py` | Veri ve geçiş |
| Hizmet | `services/answer_feedback.py` (`AnswerVotes`: oy kaydı, anahtarların sunucuda hesaplanması, cevap reddinde kayıtlı cevabın silinmesi, okunan cevaba oy uygulaması) | 1, 2, 6-10, 14 |
| Uygulama noktası | `services/analysis/jobs.py` (`AnalysisJobs.overlay` zorunlu; `present` hem tek soru sonucuna hem liste terimine) | 8, 14 |
| API | `api/votes/router.py`, `schemas/votes/votes.py`, `schemas/analysis/jobs.py` (cevaba eklenen oy alanları) | 1, 7, 15, API sözleşmesi |
| Uygulama | `app/main.py` (oy hizmeti işlerin uygulama noktasıdır) | 8 |
| Gözlemlenebilirlik | `core/telemetry.py` (üç ölçüm), `app.feedback` olayları | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Oy düğmeleri, gerekçe paneli, rozetler, bölümler, cevap oyu, `tr.json` | 11-13 |

## Kararların uygulaması

- Decision 2 ve 11: Oy veren, `X-Device-Id` başlığından çözülen ziyaretçidir; sorunun metin ve anlam
  anahtarı tam metinden, hizmetteki motorun `cache_keys`'i ile hesaplanır.
- Ziyaretçi ile oy (Decision 2, Requirement 1, 8, 15, 19; Acceptance 2, 7):
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md) ile birlikte
  uygulanır. `POST /votes` ve cevap uçlarındaki oy uygulaması oturum yerine ziyaretçi bağımlılığını
  kullanır; `answer_vote` hesap ya da ziyaretçiye bağlanır ve oy anındaki IP adresi ile makine adını
  taşır (003 Veri ve geçiş göçü); oy ucu 003 Requirement 6'daki hız sınırını kullanır; ön yüz oy
  isteğini paylaşılan istemciyle `X-Device-Id` başlığıyla gönderir.
- Decision 3: Satırlar yalnız eklenir; okurken bir sorunun satırları oy zamanı (eşitlikte kayıt
  sırası) sırasıyla alınır ve kişinin son oyunu kaynaktaki `assess` seçer. Oy zamanı UTC'dir;
  ağırlıklandırmaya kaynaktaki gibi saniyeye kesilmiş ISO metni olarak verilir.
- Requirement 6: Cevabın yazıldığı an, cevabın İstanbul saatli `generated_at`'idir (kayıtlı cevapta
  ilk analizin anı); cevap oylarına dakika duyarlılığıyla uygulanır ve yanıtta `feedback.answer_at`
  saat dilimli ISO metni olarak döner. Oy ucuna gelen `answer_at` saat dilimli olmalıdır.
- Requirement 7 ve 8: Oylar okunan her cevaba (tek soru sonucu, kayıtlı cevap, liste terimi)
  question-analysis'in uygulama noktasında o kullanıcı için uygulanır; sözlük sürümü ve tablo adları
  hizmetteki motordandır. Uygulama hata verirse hata sınıfı yazılır, ölçülür ve cevap oysuz döner.
- Requirement 9: Oylar analiz kaydına, kayıtlı cevaba, raporlara ve liste satırına dokunmaz.
- Requirement 10: Cevap oyundan sonra cevap reddedilmiş sayılırsa question-analysis'in
  `SavedAnswers.forget(kiracı, text_key, meaning_key)` hizmeti, parmak izinden bağımsız siler.
- Requirement 18: Okuma iki dizinden geçer: kiracı ve metin anahtarı, kiracı ve (yalnız boş
  olmayan) anlam anahtarı; sorgu planı test edilir.
- Decision 6 ve 7: Tablo anahtarı oy anındaki sözlükte olmalıdır (422 `vote_table_unknown`);
  uzun değerler kesilmez, reddedilir; bilinmeyen alan 422'dir. İndeks henüz kurulmamışsa uç
  anahtarları hesaplayamadığı için 503 `search_index_not_ready` döner.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_votes_parity.py` (400 üretilmiş oy satırı kümesi ve cevap; kaynak
  anlık görüntüsü `votes.json`).
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 3-7, 17 | `tests/unit/analysis/test_feedback.py` (kaynak testleri), `tests/unit/analysis/test_feedback_limits.py`, `tests/parity/test_votes_parity.py` |
| 1, 2, 10, 15, 18 | `tests/integration/test_votes_api.py` |
| 8, 9 | `tests/integration/test_votes_api.py` (`test_an_overlay_failure_returns_the_answer_without_votes`, `test_votes_change_neither_the_report_nor_the_record`), `tests/integration/test_term_lists_api.py` |
| 14 | `tests/integration/test_term_lists_api.py` (`test_votes_shape_the_term_but_not_the_row_or_the_report`) |
| 16 | `tests/integration/test_votes_api.py` (`test_old_votes_stay_and_weigh_by_their_age`) |
| Veri ve geçiş | `tests/integration/test_list_and_vote_data_model.py` |
| Gözlemlenebilirlik | `tests/integration/test_telemetry_signals.py`, `tests/integration/test_votes_api.py` |
| 11-13 | Ön yüz testleri (açık görev) |
