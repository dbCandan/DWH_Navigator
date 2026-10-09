# Plan — user-accounts

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama iki parçadır: backend
(hesaplar, oturum, ortak web tabanı, telemetri) ve ön yüz (ekranlar, bellek içi belirteç, sessiz
yenileme). Ön yüz parçası kaynak tasarımla birlikte ayrı teslim edilir.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/accounts.py` (ad kuralları, roller ve sıra), `app/backend/app/domain/password_policy.py`, `app/backend/app/domain/common_passwords.txt` | 1, 2, 3, 10 |
| Modeller ve göç | `domain/models/{user,refresh_session,user_change,tenant}.py`, `schema/alembic/versions/202610080001_user_accounts.py` | 2, 4, 5, 7, Veri ve geçiş |
| Çekirdek | `core/security.py` (Argon2, tek kullanımlık parola, yenileme belirteci, JWT), `core/login_throttle.py`, `core/client_address.py`, `core/errors.py`, `core/telemetry.py`, `core/logging.py`, `core/secret_cipher.py`, `core/config.py` | 1, 2, 6, 7, 9, 15, 19 |
| Ara yazılım | `middleware/security_headers.py`, `middleware/cross_site.py`, `middleware/request_logging.py`, `middleware/tenant_context.py` | 12, 13, 14, 15, 19 |
| Servis | `services/auth_service.py`, `services/user_admin_service.py`, `services/super_admin_service.py`, `services/request_scope.py` | 1, 4-10, 17, 18 |
| API | `api/auth/{endpoints,dependencies}.py`, `api/admin/router.py`, `schemas/{auth,admin,errors}` | API sözleşmesi, 10, 15 |
| Komut | `app/scripts/create_super_admin.py` | 18 |
| Yapılandırma | `app/backend/.env.example`, `app/infra/docker-compose.local.yml`, `app/infra/docker-compose.observability.yml`, `app/infra/.env.example`, `app/backend/entrypoint.dev.sh`, `app/infra/Dockerfile.backend.release` (`--no-server-header`) | 14, 17, 19, Dağıtım etkisi |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | giriş, "Yeni parola belirleyin", "Parolamı değiştir", Kullanıcılar sayfası, bellek içi belirteç, Web Locks ile yenileme, SSE ve indirme için `Authorization`, `nginx.security-headers.conf` CSP | 6, 7, 12, 14, 16 |

## Kararların uygulaması

- Decision 19, yaygın parola listesi: iskeletin 11 maddelik taban listesi ile SecLists
  (`https://github.com/danielmiessler/SecLists`, MIT lisansı) `2026.1` sürümündeki
  (`190c6f7bd58c847ceadfe57d9853592737f059e8`, yayın 2026-03-23)
  `Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt` dosyasının (SHA-256
  `424a3e03a17df0a2bc2b3ca749d81b04e79d59cb7aeec8876a5a3f308d0caf51`) NFKC sonrası 15 ve daha uzun
  karakterli girdileri. Girdiler Türkçe katlanmış (`turkish_fold`), tekilleştirilmiş ve sıralanmış
  olarak `common_passwords.txt`'de durur (10.904 satır). Kabul kaydı `dependency-admission.json`'dadır.
- Decision 20: hesap yönetimi uçları rolü ve hesabı `services/request_scope.py`
  `acting_user_with_role` ile her istekte veritabanından okur; yönetim ekranının durum değiştiren uçları
  aynı işlevi `yonetici` ile kullanır.
- Değişiklik kaydı (`app_user_change`) yalnız eklenen akıştır: güncelleme ve yazılımsal silme sütunu
  yoktur (`AppendOnlyAuditMixin`); parola satırı değer taşımaz (veritabanı denetimi).
- Yenileme oturumu satırı bittikten 7 gün sonra giriş akışında kalıcı silinir.
- Telemetri yalnız PRD'nin iki ölçümünü ve istek başına sunucu iz aralığını üretir; veritabanı izi yoktur.

## Doğrulama

- Backend: `scripts/quality-gate.sh backend`; PostgreSQL'li tam koşum `scripts/quality-gate.sh all`.
- Göç: `scripts/db.sh validate`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.
- Ayar yüzeyi: `python3 scripts/check-config-sync.py`; bağımlılık: `scripts/check-dependency-admission.py`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1, 4, 6, 7, 8, 9 | `tests/integration/test_auth_flow.py`, `tests/unit/test_security.py`, `tests/unit/test_login_throttle.py` |
| 2, 5, 10 (hesap yönetimi) | `tests/integration/test_user_administration.py`, `tests/unit/test_rbac.py`, `tests/unit/test_accounts.py` |
| 3 | `tests/unit/test_password_policy.py`, `tests/integration/test_auth_flow.py` |
| 10 (Basic), 12 (backend), 13, 14 (backend), 15 | `tests/unit/test_web_baseline.py` |
| 17, 18 | `tests/integration/test_super_admin_bootstrap.py`, `tests/unit/test_super_admin_bootstrap.py` |
| 19 | `tests/integration/test_telemetry_signals.py`, `tests/unit/test_telemetry.py`, `tests/unit/test_config.py` |
| Sızıntı | `tests/integration/test_account_secrets.py` |
| Veri ve geçiş | `tests/integration/test_data_model.py` |
