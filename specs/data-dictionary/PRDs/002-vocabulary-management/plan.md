# Plan — vocabulary-management

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama iki parçadır: backend
(liste tabloları ve başlangıç göçü, denetimler, Excel, uçlar, motor için okuma işlevi) ve ön yüzdeki
Kelimeler sayfası. Kayıtlar [search-settings](../009-search-settings/PRD.md) değişiklik sırasından
geçer.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/vocabulary.py` (`check_terms`, `check_stopwords`, katı alan türleri, sınırlar, `list_digest`) | 1, 3, 4, Decision 6, 7 |
| Model ve göç | `domain/models/vocabulary.py`, `schema/alembic/versions/202610080004_vocabulary_lists.py` (tablolar ve parmak izi denetimli başlangıç yüklemesi), `schema/alembic/seed/vocabulary/*.jsonl` | 1, 9, Veri ve geçiş, Decision 3, 4, 8, 10 |
| Depo | `infrastructure/repositories/vocabulary_repository.py` (okuma, yazılımsal silip yazma, revizyon) | 1, 5 |
| Okuma işlevi | `services/vocabulary_reading.py` (`TermGroup` dizisi, durak kelime biçimleri, içerik özetleri) | 2, Decision 2 |
| Excel | `services/vocabulary_workbook.py` (ortak güvenli okuyucuyla okuma, yazma) | 6, 7 |
| Servis | `services/vocabulary_service.py` | 5, 7, 8, 14, 15, Decision 5 |
| API | `api/vocabulary/router.py`, `schemas/vocabulary/lists.py` | API sözleşmesi, 15 |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Kelimeler sayfası, terim çekmecesi, `tr.json` | 10-13 |

## Kararların uygulaması

- Requirement 3: İstek gövdesi düz JSON okunur; liste değilse kaynaktaki `Liste bekleniyordu`
  (`vocabulary_items_invalid`), yanlış türde ya da bilinmeyen alan `invalid_request` ve yalnız alanın
  yeri (`items.3.term`) ile döner. Ek uzunluk denetimleri terim boşluğu denetiminden sonra, tekrar
  denetiminden önce yapılır.
- Requirement 5: Aynı içerik kararı denetlenmiş listenin `list_digest` özetiyle başlık kaydındaki
  özetin karşılaştırılmasıdır; özet sırayı ve bütün alanları kapsar.
- Requirement 9: Göç, uygulamanın Türkçe katlama yardımcısını ve `list_digest`'i kullanır; böylece
  başlangıç listesinin özeti ekrandan aynı listeyle yapılan kaydın özetiyle aynıdır.
- Requirement 7: Adlı sayfa yoksa ya da boşsa ilk sayfa okunur (kaynakla aynı); başka sayfa okunmaz.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_admin_parity.py` (kaynağın `check_terms`, `check_stopwords`,
  `words_from_workbook`, `words_to_workbook`, `load_term_dictionary`, `load_stopword_file`
  çıktılarının anlık görüntüsüyle; `python -m tests.parity.harness --verify-snapshot` yeniden üretir).
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 2-4, 6, 7 | `tests/unit/test_vocabulary_rules.py`, `tests/parity/test_admin_parity.py` |
| 1, 5, 8, 9, 14, 15 | `tests/integration/test_vocabulary_api.py` |
| Veri ve geçiş | `tests/integration/test_data_dictionary_model.py`, `tests/integration/test_vocabulary_api.py` |
| Gözlemlenebilirlik | `tests/integration/test_vocabulary_api.py`, `tests/integration/test_search_index_signals.py` |
| 10-13 | `app/frontend/src/pages/admin/VocabularyPage.test.tsx` |
