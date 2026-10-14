# Plan — anonymous-visitor

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 0.1.0). Uygulama, girişsiz ana ekran için
ziyaretçi kimliğini backend'e, veritabanına ve ön yüze birlikte ekler; yönetim ekranının girişi
değişmez.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Şema ve göç | `app/backend/app/domain/models/visitor.py` (yeni), `analysis_record.py`, `answer_vote.py`, `term_list.py`; yeni Alembic göçü (`scripts/db.sh generate`) | 4, 7, Decision 5 |
| Kimlik | `app/backend/app/api/visitor/dependencies.py` (yeni `CurrentVisitor`: `X-Device-Id` doğrulama, `visitor` kaydını açma/güncelleme, IP ve ters DNS), `core/client_address.py` (değişmez) | 2, 3, 4, Decision 1, 2 |
| Kiracı | `middleware/tenant_context.py` (oturumsuz ana ekran isteğinde kiracı başlığı istenmez; kiracıyı hizmet `platform` olarak çözer) | Decision 4 |
| Depolar | `analysis_record_repository.py`, `answer_vote_repository.py`, `term_list_repository.py` (hesap ve ziyaretçi için dış birleştirme, ziyaretçi sahipliği) | 5, 7 |
| Hizmetler | `services/analysis/jobs.py` (`Asker` hesap ya da ziyaretçi; sahiplik, akış ve hız sayaçları), `services/term_lists.py`, `services/answer_feedback.py`, `services/analysis_records.py` ("Soran") | 5, 6, 7 |
| API | `api/analyses/router.py`, `api/explorer/router.py`, `api/votes/router.py`, `api/term_lists/router.py` (rol koruması yerine `CurrentVisitor`); yönetim yönlendiricileri değişmez | 3, 5 |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | `lib/deviceId.ts` (yeni), `lib/apiClient.ts` (ana ekran isteğinde `X-Device-Id`, belirteç ve kiracı başlığı yok), `App.tsx` (`/` `AuthGuard` dışında), `ExplorerPage.tsx` (oturum alanı yok), yönetim analiz kayıtları sayfası ("Soran") | 1, 2, 7, 8 |

## Kararların uygulaması

- Decision 1 ve Requirement 2: Cihaz kimliği `crypto.randomUUID` ile üretilir, `localStorage`
  anahtarında durur; okunamazsa sayfa belleğinde tutulur.
- Decision 2: IP adresi `resolve_client_address` ile çözülür; ters DNS ayrı iş parçacığında, kısa
  zaman aşımıyla yapılır ve sonucu ziyaretçi kaydında saklanır; her istekte yeniden sorulmaz.
- Decision 5 ve Veri: Hesap ve ziyaretçi sütunlarından tam birinin dolu olduğu `CHECK` kısıtıyla
  sağlanır; göç ekleyicidir ve mevcut satırlara dokunmaz.
- Requirement 6: Hız sayaçları ziyaretçi `public_id`'si ve IP adresiyle anahtarlanır, süreç
  belleğinde ve sınırlı anahtar sayısıyla tutulur.

## Doğrulama

- `scripts/db.sh generate`, `scripts/db.sh apply`, `scripts/db.sh validate`, `scripts/db.sh status`.
- `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- `scripts/quality-gate.sh all`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1, 2, 8 | `app/frontend/src/App.test.tsx`, `app/frontend/src/lib/deviceId.test.ts`, `app/frontend/src/pages/ExplorerPage.test.tsx` |
| 3, 4, 5 | `app/backend/tests/integration/test_visitor_api.py` |
| 6 | `app/backend/tests/integration/test_visitor_rate_limits.py` |
| 7 | `app/backend/tests/integration/test_analysis_records_api.py`, göç testi |
| Acceptance 2 | `e2e/auth/02-anonymous-visitor.mjs` |
