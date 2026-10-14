# Görevler — user-accounts

[Plan](plan.md) belgesinden türetildi.

- [x] Task 1 — Requirement 1-11, 13, 15, 17-19 / Acceptance 1 (backend kısmı): yerel hesaplar,
  roller, tek kullanımlık parola, zorunlu ve isteğe bağlı parola değişikliği, sıfırlama,
  pasifleştirme, rol değişikliği ve değişiklik kaydı, parola politikası, hız sınırı, 15 dakikalık
  erişim belirteci, yenileme çerezi, sunucu tarafı çıkış, süper yönetici açılışı ve elle komut,
  siteler arası istek denetimi, tek hata zarfı, OpenTelemetry altyapısı ve göç. Kanıt:
  `scripts/quality-gate.sh backend` ve PostgreSQL'li backend test koşumu.
- [x] Task 2 — Requirement 12 ve 14 (backend kısmı): her yanıtta güvenlik başlıkları ve API CSP'si
  (hatalar, akışlar ve indirmeler dahil), belirtecin yalnız `Authorization` başlığında kabulü, sürümsüz
  `Server` (`--no-server-header`). Kanıt: `tests/unit/test_web_baseline.py`.
- [ ] Task 3 — Requirement 6, 7, 12, 14 ve 16 (ön yüz kısmı): ekranlar, bellek içi belirteç, Web
  Locks ile sessiz yenileme, SSE ve indirmede `Authorization`, ön yüz sunucusunun katı CSP'si ve
  `server_tokens off`, yerel vekilin başlıkları; Vitest ve yapılandırma testleri (Acceptance 1 ön yüz
  kısmı).
- [ ] Task 4 — Acceptance 2 ve 4: yerel Compose'da tarayıcıyla uçtan uca akış ve ekran görüntüleri.
- [ ] Task 5 — Acceptance 3: nonprod kümede süper yönetici açılışı, giriş, hız sınırı ve başlıklar.
- [ ] Task 6 — Requirement 10, 11, 12, 16 / Acceptance 1, 2, 4: ana ekran uçlarından oturum ve
  `kullanici` rolü şartının kaldırılması, kayıtların hesaba ya da ziyaretçiye bağlanması, ana ekran
  akış ve indirmelerinde `X-Device-Id`, oturum alanının ve giriş yönlendirmesinin yalnız `/admin`
  kabuğunda kalması, uygulama [anonymous-visitor](../003-anonymous-visitor/PRD.md) ile birlikte.
  Durum (2026-10-15): kod ve testler yazıldı (önce kırmızı, sonra yeşil). Arka uç: pytest 996 testten 992'si geçti; kalan 4'ten 3'ü bu değişiklikle güncellendi ve geçiyor, 1'i (`test_two_parallel_activations_let_one_win`) değişiklikten önceki kodda da ara sıra kırılan bir yarış durumu. Ruff, mypy, `alembic check` temiz; `OpenAPI` ve ön yüz tipleri yeniden üretildi. Ön yüz: Vitest 39 dosya / 320 test (iki işçiyle) geçti, ESLint ve tip denetimi temiz. Yerel yığında oturumsuz ana ekran, cihaz kimliği ve ziyaretçi adına yazılan analiz kaydı tarayıcıda gözlendi. Açık: `scripts/quality-gate.sh all` ve tarayıcı senaryoları çalıştırılmadı (`kt-iskelet` ve çevrimdışı E2E paketi yok); nonprod gözlemi yapılmadı.
