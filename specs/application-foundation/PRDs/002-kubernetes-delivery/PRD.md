# PRD — kubernetes-delivery

Status: Accepted

Version: 1.0.0

Acceptance date: 2026-10-08

Domain: [application-foundation](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

DWH Navigator'ı PostgreSQL 17 dahil tek Helm chart'ı (Kubernetes'e kurulum paketi) ile nonprod KT
Rancher kümesine, Azure dağıtım işinin argümansız çağırdığı `helm/dwhnavigator/deploy.sh` üzerinden
güvenle kurmak; yerelde aynı yapıyı Windows ve macOS'ta Docker Compose ile çalıştırmak. Kaynağın tek
konteynerlik Docker kurulumu (`Dockerfile`, `compose.yaml`, `docs/KURULUM.md`) ve Windows başlatma
betikleri hedefte iskeletin chart'ı, release imajları, yerel Compose yığını ve fabrikanın yerel yığın
ajan komutlarıyla değişir; kaynağın her sertleştirme ölçüsünün karşılığı bu PRD'dedir. Nonprod
dağıtımı işletim ekibinin ayar veya gizli değişken vermesini beklemez: ortam adresleri ve sır olmayan
ayarlar `helm/dwhnavigator/values-project.yaml`'da; oturum imza anahtarı, ayar şifreleme anahtarı ve
isteğe bağlı süper yönetici başlangıç parolası `helm/dwhnavigator/deploy-hooks.sh`'ın hazırladığı
runtime Secret'ta (`dwhnavigator-runtime`; kümedeki sır deposu); veritabanı sırları `deploy.sh`'ın
ürettiği Secret'lardadır. Backend kümenin dışına yalnız model sunucusuna çıkar.

## Aktörler ve sonuçlar

- **İşletim ekibi:** Azure dağıtım işini çalıştırır. Sonuç: tek komutla kurulum veya güncelleme; ek
  ayar veya gizli değişken gerekmez; yayımlanmamış imajda kümeye dokunulmaz; hizmet veren sürüm
  silinmez.
- **Proje sahibi:** Nonprod `admin` süper yöneticisinin ilk parolasını seçer ve Azure gizli değişkeni
  `DWHNAVIGATOR_ADMIN_PASSWORD` olarak verir ([user-accounts](../001-user-accounts/PRD.md)
  Requirement 17).
- **Kullanıcı:** Uygulamaya `https://dwhnavigator.ailab-test.kuveytturk.com.tr` adresinden ulaşır
  (Decision 20); dakikalar süren bir analizin canlı ilerlemesi yolda kesilmez; Excel dosyalarını 20
  MB'a kadar yükler (Requirement 11).
- **Geliştirici:** Aynı yapıyı Windows ya da macOS'ta Docker Compose ile PostgreSQL 17 üzerinde
  çalıştırır; yığını ajan komutlarıyla başlatır, durdurur ve durumunu görür.

Ölçülebilir sonuç: argümansız Azure işi ek girdi olmadan kurar; podlar hazır, PostgreSQL diski 10Gi
`nfs-sc`, göç işi başarılı; backend listede olmayan adrese bağlanamaz; 60 saniyeden uzun süren bir
analizin canlı akışı kesilmez; release imajlarında düzeltmesi yayımlanmış zafiyet yoktur; yerel yığın
Windows ve macOS'ta aynı komutlarla açılır.

## Değişmezler ve sınırlar

- Decision 1: Tek chart `helm/dwhnavigator/` içinde dört iş yükü vardır: backend, frontend,
  PostgreSQL 17 StatefulSet (kalıcı diskli, tek kopya çalışan iş yükü) ve şema göç Job'u (bir kez
  çalışıp biten iş). Redis, işleyici, gözlemlenebilirlik iş yükü ve dosya diski yoktur.
- Decision 2: Chart Secret yazmaz; `values.yaml` ve `values-project.yaml` sır taşımaz. Runtime
  Secret'ı `deploy-hooks.sh`, veritabanı Secret'larını `deploy.sh` kümede hazırlar; boş veya tanımsız
  değişken kümedeki mevcut değeri korur.
- Decision 3: Fabrikanın yönettiği dosyalar projede elle düzenlenmez:
  `helm/dwhnavigator/Chart.yaml`, `values.yaml`, `templates/**`, `deploy.sh`,
  `scripts/render-charts.sh`, `scripts/render_charts.py`, `scripts/stack.sh`,
  `scripts/dev-secrets.sh`, `scripts/create-super-admin.sh`, `.github/workflows/image-build.yml`,
  `.dockerignore`, `.gitattributes`. Proje, rules/45'in projeye bıraktığı `values-project.yaml` ve
  `deploy-hooks.sh` ile iskeletin uygulamaya bıraktığı `app/**` dosyalarını değiştirir; fabrika
  dosyasında gereken değişiklik fabrika işi olarak istenir (Dağıtım etkisi, fabrika bağımlılıkları).
  Chart içi PostgreSQL ve göç Job'u rules/45'in açık seçimidir ve `values-project.yaml` ile açılır.
- Decision 4: `deploy.sh` iskeletin güvencelerini korur (rules/45): kümeye dokunmadan önce her imajın
  yayımlandığını doğrular, süren (`pending-*`) release'i bekler, yarım kalan güncellemeyi son sürüme
  geri alır ve hizmet vermiş release'i asla kaldırmaz.
- Decision 5: Backend tek kopya çalışır: arama indeksi süreç belleğindedir ve analizler kaynaktaki
  "tek motor, tek kilit" düzeniyle sırayla yürür (data-dictionary alanının
  [search-settings](../../../data-dictionary/PRDs/009-search-settings/PRD.md) ve
  [question-analysis](../../../data-dictionary/PRDs/004-question-analysis/PRD.md) PRD'leri).
  `backend.replicaCount` 1'den büyük yapılmaz. Güncellemede eski ve yeni backend süreci birlikte
  çalışmaz: backend Deployment'ı `Recreate` stratejisiyle (önce eski pod durur, sonra yeni pod
  başlar) güncellenir. question-analysis ve
  [list-search](../../../data-dictionary/PRDs/005-list-search/PRD.md) PRD'lerindeki "yarıda kesildi"
  tespiti bu kurala dayanır; iki sürecin çakışmasına karşı ek kilit gerekmez. Fabrika chart'ında
  bugün strateji seçeneği yoktur; seçenek fabrika bağımlılığıdır (Dağıtım etkisi) ve gelmeden
  nonprod'a dağıtım yapılmaz (Decision 22).
- Decision 6: Her iş yükü rules/45 sıkılaştırmasına uyar; kaynağın konteyner ölçüleriyle eşlemesi
  Requirement 2'dedir.
- Decision 7: Çalışma zamanı veritabanı rolü yalnız veri okuma ve yazma (DML) yetkilidir; tablo
  oluşturma ve değiştirme yalnız göç Job'unun kullandığı sahip rolündedir.
- Sınır: Hesap, oturum ve güvenlik başlıklarının anlamı user-accounts PRD'sinde; model bağlantılarının
  ve ayar şifreleme anahtarının anlamı
  [llm-connection](../../../data-dictionary/PRDs/003-llm-connection/PRD.md)'da; analiz işinin ve canlı
  olayların içeriği question-analysis'te; başlangıç verisinin girişi
  [vocabulary-management](../../../data-dictionary/PRDs/002-vocabulary-management/PRD.md)'da; arama
  indeksinin kurulması search-settings'tedir. Bu PRD onları kümeye ve yerel yığına taşır.

## Mevcut davranış

Kaynak `~/codes/kt-dwhnavigator` (`76e21a3`) ve hedef iskelet `~/codes/dwhnavigator-kt` bugün şöyle
çalışır; her maddenin sonunda hedefteki değişiklik yazılıdır.

- **Tek konteyner imajı** (`Dockerfile`, ADR-048): `python:3.12-alpine` taban imajı SHA-256 özetiyle
  (içeriğin parmak izi) sabittir; paketler `requirements.lock`'tan sürüm ve özetle, yalnız hazır paket
  (wheel) olarak kurulur (`--require-hashes --no-deps --only-binary=:all:`); çalışma imajında
  `apk upgrade` yapılır, pip, setuptools ve wheel kaldırılır; kullanıcı `vsa` uid/gid 10001,
  kabuğu `/sbin/nologin`; `HEALTHCHECK` `/healthz`'i 90 saniyelik başlangıç payıyla yoklar (açılışta
  indeks kurulur); port 8765; veri `/app/data` biriminde; `.dockerignore` beyaz listesiyle imaja yalnız
  kod ve iki kelime listesi girer. `docs/GUVENLIK.md`: Trivy imaj taramasında (zafiyet tarayıcısı)
  işletim sistemi ve Python paketlerinde 0 zafiyet, 0 gömülü sır; Debian tabanında 165 zafiyet vardı.
  **Hedefte:** iskeletin iki release imajı (backend `python:3.14-alpine3.23`, frontend
  `nginx:1.31.6-alpine-slim` ve kilitli Alpine yamaları) ile PostgreSQL imajı; ölçülerin karşılığı
  Requirement 2, 13 ve 14.
- **Compose** (`compose.yaml`): tek servis `vsa`; `VSA_ADMIN_PASSWORD` zorunlu; `./data:/app/data`
  birimi; `read_only: true`; `tmpfs /tmp` 64 MB; `cap_drop: [ALL]`; `no-new-privileges`;
  `mem_limit: 2g`; `pids_limit: 256`; json-file log 10 MB × 5; port 8765, TLS önündeki ters vekilde.
  **Hedefte:** nonprod'da chart (Requirement 1–2), yerelde iskeletin Compose yığını (Requirement 17).
- **Veri** (`docs/KURULUM.md` §2, ADR-052): sözlük, kelime listeleri, indeks, ayarlar, API anahtarı
  içeren `llm_integrations.yaml`, kayıtlı cevaplar, analiz kayıtları, oylar ve raporlar `data/`
  klasöründedir; "Yedeklenecek tek klasör `data/`'dır". **Hedefte:** her şey PostgreSQL'de;
  konteynerde dosya deposu yok; tek kalıcı disk PostgreSQL'indir (Requirement 3); yedek işi yoktur
  (Decision 21).
- **Kurulum ve güncelleme** (`docs/KURULUM.md` §1, §9): imaj internete çıkabilen bir makinede
  derlenip `docker save`/`docker load` ile taşınır ya da kurum kayıt defterine konur; güncelleme imaj
  etiketini değiştirip `docker compose up -d`; geri dönüş eski etiket. **Hedefte:** GitHub `main` →
  GHCR → kurum vekil önbelleği; Azure işi `deploy.sh`'ı çağırır; başarısız güncelleme kendiliğinden
  geri döner (Requirement 13, 15, 16).
- **Ters vekil ve sunucu sınırları** (`docs/KURULUM.md` §6; `src/vsa/web/server.py`): kaynak düz HTTP
  konuşur; vekilde TLS, `proxy_read_timeout 900s` (bir soru dakikalar sürer ve `/api/ask` cevabı tek
  istekte döner), `client_max_body_size 20m` ve `Strict-Transport-Security "max-age=31536000"`
  önerilir; konteyner portu yalnız vekile açılır. Sunucu istek okumaya 120 saniye tanır
  (`REQUEST_TIMEOUT`, yavaş istemci koruması) ve gövdeyi 20 MB ile sınırlar (`MAX_UPLOAD`, `_body`:
  411, 400, 413). **Hedefte:** TLS ve kenar sınırları giriş denetleyicisinde (ingress: kümeye gelen
  trafiği uygulamaya yönlendiren bileşen); uzun analiz iş olarak yürüdüğü ve ilerlemesi canlı akışla
  geldiği için uzun okuma süresi yerine 15 saniyelik canlı tutma; gövde 20 MB (Requirement 11, 12).
- **Ağ çıkışı** (`docs/GUVENLIK.md` "Kalan riskler" 3): konteynerin dışarıya tek ihtiyacı model
  sunucusudur; güvenlik duvarında yalnız ona izin önerilir, uygulama tarafında zorunlu değildir.
  **Hedefte:** varsayılanı kapalı ağ izin kuralı (NetworkPolicy); backend yalnız DNS'e, kendi
  veritabanına ve model sunucusuna çıkar (Requirement 10).
- **Model sunucusu** (`docs/KURULUM.md` §5): ölçümler ekibin DGX Spark sunucusundaki LM Studio
  üzerinde yapıldı (`gemma-4-31b`, sırayla çalışma, soru başına yaklaşık 45 saniye); kurulum belgesi
  örnek adres olarak `http://dgx-spark:8000/v1` verir. **Hedefte:** nonprod kurum içi RunAI ucunu
  kullanır ([llm-connection](../../../data-dictionary/PRDs/003-llm-connection/PRD.md) Decision 18);
  çıkış kuralı Requirement 10'dadır.
- **Windows geliştirme** (`baslat.bat`, `scripts/stop_servers.ps1`, `.claude/launch.json`; README
  "Geliştirme (Windows, yerel)"): `baslat.bat` bu klasörde çalışan bütün `vsa serve` süreçlerini
  PowerShell betiğiyle durdurur, sonra `.venv\Scripts\vsa.exe serve --open` ile arayüzü 8765'te açar;
  Docker kullanılmaz, model bu makinede çalışmaz. **Hedefte:** üçü de kaldırılır; yerel geliştirme
  Windows ve macOS'ta Docker Compose ile yapılır; yığını başlatma, durdurma ve durumunu gösterme
  fabrikanın sağlayacağı ajan komutlarıyla olur (Requirement 17).
- **Hedef iskelet** (`helm/dwhnavigator/`, `app/infra/`): chart DWH Code Review'daki fabrika chart'ıyla
  aynıdır; `values-project.yaml` ve `deploy-hooks.sh` yoktur; `postgres` ve `migration` kapalıdır;
  ingress adresi, sınıfı ve TLS adı boştur; backend bellek sınırı 512Mi'dır; ingress şablonu açıklama
  (annotation) taşımaz, yani giriş denetleyicisinin gövde ve süre ayarları değiştirilemez; backend
  Deployment'ının güncelleme stratejisi seçilemez (Kubernetes varsayılanı kesintisiz güncellemedir:
  yeni pod hazır olana kadar eski pod da çalışır); yerel vekil
  (`app/infra/nginx/nginx.local.conf`) gövdeyi 4 MB ile sınırlar, okuma süresi varsayılandır (60 sn) ve
  `Server` başlığı sürüm taşır; release backend imajında pip vardır; `image-build.yml` imajları tarama
  adımı olmadan yayımlar; yerel sırlar imza anahtarı ile veritabanı ve Redis parolalarıdır, ayar
  şifreleme anahtarı yoktur. **Hedefte:**
  Requirement 1–17.
- **Referans DWH Code Review** (`~/codes/dwhcodereview/helm/dwhcodereview/`, nonprod'da çalışıyor):
  aynı chart, `values-project.yaml` ve `deploy-hooks.sh`; güvenilen ingress pod ağı `10.42.0.0/16`;
  10Gi `nfs-sc` PostgreSQL diski; model çıkışı `10.14.3.99/32` TCP 443; süper yönetici parolası Azure
  gizli değişkeninden. **Hedefte:** aynı teslim modeli; dizin çıkışı ve dizin sertifikası yoktur
  (kimlik yerel hesaplardır, user-accounts Decision 7), SQL Server yoktur, model API anahtarı runtime
  Secret'ta değil PostgreSQL'de şifreli durur (Decision 8).

## İşlevsel gereksinimler

Requirement 1: Proje katmanıyla `helm template` çıktısı tam olarak backend ve frontend
Deployment'ını, PostgreSQL StatefulSet'ini, göç Job'unu, bunların Service'lerini (hepsi
`ClusterIP`), tek Ingress'i ve her iş yükü için bir ağ izin kuralını üretir; Secret, düğüm kapısı,
yük dengeleyici veya küme kapsamlı nesne üretmez. Backend Deployment'ı `replicas: 1` ve
`strategy.type: Recreate` taşır; bu, proje katmanıyla render edilen çıktıda proje testiyle
doğrulanır (Decision 5; strateji, fabrika chart'ına seçenek gelince yazılır ve ilk nonprod dağıtımı
ondan sonradır, Decision 22). Chart sürümü fabrikanın yönettiği `Chart.yaml`'dan gelir (Decision
18).

Requirement 2: Kaynağın sertleştirme ölçüleri hedefte şöyle karşılanır; her satır render denetimi
(`scripts/render-charts.sh`) ya da imaj testiyle doğrulanır:

| Kaynak ölçüsü | Hedefte | Doğrulama |
|---|---|---|
| Salt okunur kök dosya sistemi (`read_only: true`) | Her kapsayıcıda `readOnlyRootFilesystem: true` | Render |
| Yazılabilir yalnız `/app/data` ve 64 MB `/tmp` | Dosya deposu yok. Backend ve göç Job'unda yalnız 64 MiB `/tmp`; frontend'de 64 MiB `/var/cache/nginx` ve 8 MiB `/var/run`; PostgreSQL'de veri diski, `/var/run/postgresql` ve `/tmp` | Render |
| Kök olmayan kullanıcı, uid/gid 10001 | Backend ve göç Job'u 10001:10001; frontend 101:101 (nginx imajının kullanıcısı); PostgreSQL 999; hepsinde `runAsNonRoot` | Render ve imaj testi |
| Oturum kabuğu yok (`/sbin/nologin`) | Backend imajındaki uygulama kullanıcısının kabuğu `/sbin/nologin` | İmaj testi |
| `cap_drop: ALL` | `capabilities.drop: ["ALL"]` | Render |
| `no-new-privileges` | `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`, hizmet hesabı belirteci bağlanmaz | Render |
| Bellek sınırı 2 GB | Backend sınırı 2Gi, isteği 512Mi; CPU isteği 100m, sınırı 1 (Decision 10); frontend, PostgreSQL ve göç Job'u fabrika değerlerinde | Render |
| Süreç sınırı 256 (`pids_limit`) | Pod tanımında karşılığı yoktur (süreç sayısı sınırı düğüm ayarıdır); backend tek uvicorn süreciyle çalışır | Riskler |
| Log döndürme (10 MB × 5) | Loglar standart çıktıya gider; döndürme kümenin işidir | — |
| `HEALTHCHECK /healthz` | Başlatma, hazır olma ve canlılık yoklamaları (`/liveness`, `/readiness`; Requirement 6) | Render |
| Taban imaj özetle sabit | Backend `python:3.14-alpine3.23@sha256:2187…`, frontend `nginx:1.31.6-alpine-slim@sha256:f761…`, PostgreSQL `postgres:17.10@sha256:7958…`; Alpine yamaları kilit dosyasıyla | İmaj derleme argümanları; render (PostgreSQL özeti boşsa durur) |
| Paketler sürüm ve özetle, yalnız wheel | Backend `requirements.txt` özetli kilittir; kurulum `--require-hashes --only-binary=:all:` ile yapılır | İmaj derlemesi |
| pip ve setuptools çalışma imajında yok | Backend release imajında pip, setuptools, wheel ve taban imajın getirdiği kurulum aracı kopyaları bulunmaz | İmaj testi |
| İmaja yalnız kod ve iki liste girer | Release Dockerfile yalnız belirli yolları kopyalar (Requirement 13) | İmaj testi |
| 0 zafiyet | Requirement 14 | Trivy |
| Port yalnız vekile açık | Service `ClusterIP`; backend ve frontend girişi yalnız `kube-system`'deki giriş denetleyicisinden | Render |
| TLS ve HSTS vekilde | Giriş denetleyicisinde TLS (`ailab-tls`); HSTS user-accounts Requirement 14 | L2 nonprod |

Backend'in 64 MiB'lık `/tmp`'si fabrika şablonunda sabittir; Excel okuma (ortak güvenli Excel
okuyucu, [dictionary-management](../../../data-dictionary/PRDs/001-dictionary-management/PRD.md)
Requirement 2), Excel üretme ve dosya yükleme dosya sistemine yazmadan bellekte çalışır; sınır, yükleme
ve rapor uçlarının sahibi PRD'lerde uygulanır.

Requirement 3: PostgreSQL 17 imajı yerel Compose ile aynı sürüm ve özetle (`postgres:17.10@sha256:7958…`)
sabittir ve DWH Code Review ile KT Verim'in çektiği yoldan, düğümün Docker Hub aynası üzerinden
`postgres` deposundan çekilir (Decision 9). Tek kopya çalışır; veritabanı adı `dwhnavigator_db`'dir;
veri 10Gi boyutlu, depolama sınıfı `nfs-sc` açıkça yazılmış `ReadWriteOnce` kalıcı disk talebindedir
(PVC); kaynak isteği 100m CPU/256Mi, sınırı 1 CPU/1Gi'dir. Veri sağlama toplamı (`--data-checksums`)
açıktır, yoklamalar gerçek kullanıcıyla `SELECT 1` çalıştırır, kapanışa 60 saniye tanınır (rules/45).

Requirement 4: İlk kurulumda boş veri klasöründe sahip rolü oluşur. Göç Job'u Alembic'ten (şema
değişikliği aracı) önce sahip rolüyle, süper kullanıcı olmayan ve yalnız `SELECT`, `INSERT`,
`UPDATE`, `DELETE` ile dizi kullanımı yetkili uygulama rolünü oluşturur veya günceller; varsayılan
yetkiler Alembic'in sonradan oluşturduğu tablolara da uzanır. Backend yalnız uygulama rolüyle bağlanır;
sahip rolünün bağlantısı yalnız göç Job'undadır (rules/45, Decision 7).

Requirement 5: Şema göçü backend imajıyla çalışan `alembic upgrade head` komutudur; ilk kurulumda Job
veritabanıyla aynı adımda oluşur ve veritabanı bağlantı kabul edene kadar bekler, sonraki
güncellemelerde yeni backend podlarından önce çalışan kanca olarak koşar; süresi 600 saniyeyle
sınırlıdır ve yeniden denenmez; başarısız göç güncellemeyi durdurur ve önceki sürüm korunur (rules/45).
Göçler genişletici yazılır (eski sürüm yeni şemayla çalışabilir), çünkü geri almada şema geri
indirilmez. İlk kurulumdan sonra elle veri adımı yoktur: roller ve `platform` kiracısı göçle
(user-accounts, Veri ve geçiş), terim sözlüğü ile durak kelimelerin başlangıç listeleri
vocabulary-management PRD'sindeki yolla girer; sözlük yönetim ekranından Excel ile içe aktarılır
([dictionary-management](../../../data-dictionary/PRDs/001-dictionary-management/PRD.md)).

Requirement 6: Backend hazır olma yoklaması (`/readiness`), rules/45'teki koşullara (uygulama rolü
bağlanana ve şema imajın son göçüne gelene kadar hata metni içermeyen sabit gövdeli 503) ek olarak,
süreç açıldıktan sonra bellek içi arama indeksi ilk kez kurulana kadar da 503 döner; sözlük henüz
yoksa boş indeks hazır sayılır. İndeks kurulumu canlılık yanıtını bekletmez: süreç önce dinlemeye
başlar, indeks arka planda kurulur (fabrika yoklaması süreç başlangıcına yaklaşık 60 saniye tanır).
Sonraki yeniden kurmalar (sözlük, terim listesi veya ayar değişikliği) hazır olmayı 503'e çevirmez.
İlk kurulum başarısız olursa hazır olma 503 kalır ve neden sınıfı logda görünür; kurulumun kendisi ve
olayları search-settings PRD'sindedir (bu PRD'nin Decision 12'si).

Requirement 7: Runtime Secret `dwhnavigator-runtime`'ı `helm/dwhnavigator/deploy-hooks.sh` hazırlar.
Anahtarları ve kaynakları:

| Secret anahtarı | Kaynak | Hiç verilmezse |
|---|---|---|
| `DWHNAVIGATOR_JWT_PRIVATE_KEY` | Azure gizli değişkeni `JWT_PRIVATE_KEY` verilirse o; yoksa kümedeki değer; o da yoksa kanca P-256 imza anahtarını tahmin edilemez rastgele üreteçle bir kez üretir | Üretir |
| `DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY` | Azure gizli değişkeni `SETTINGS_ENCRYPTION_KEY` verilirse o; yoksa kümedeki değer; o da yoksa kanca rastgele 32 baytı bir kez üretir ve base64 olarak yazar | Üretir |
| `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD` | İsteğe bağlı Azure gizli değişkeni `DWHNAVIGATOR_ADMIN_PASSWORD`; yoksa kümedeki değer | Yazılmaz; backend süper yönetici açmaz (user-accounts Requirement 17) |

Boş veya tanımsız değişken ve çözülmemiş Azure `$(DEĞİŞKEN)` metni verilmemiş sayılır; kümedeki
mevcut değer korunur. Kümedeki Secret okunamazsa kanca hiçbir şeyi değiştirmeden durur; P-256 olmayan
`JWT_PRIVATE_KEY` ya da 32 baytın base64 yazımı olmayan `SETTINGS_ENCRYPTION_KEY` dağıtımı Helm
değişikliğinden önce durdurur. Kanca Secret'taki başka anahtarlara dokunmaz. Değerler komut
argümanına, Helm değerine ve loga girmez; `kubectl`'e yalnız sahibine özel geçici dosyalardan geçer;
logda yalnız anahtar adı görünür. Secret değiştiğinde kümede aynı imaj etiketiyle çalışan backend varsa
(Helm pod şablonunu değiştirmeyeceği için) kanca onu yeniden başlatır. Model bağlantılarının API
anahtarları bu Secret'ta değil, PostgreSQL'de şifreli durur (Decision 8); ayar şifreleme anahtarının
anlamı ve değişmesinin sonucu llm-connection PRD'sindedir.

Requirement 8: Sır olmayan ortam ayarları `values-project.yaml`'dadır:

- `backend.existingSecret: dwhnavigator-runtime`.
- `backend.config`: `DWHNAVIGATOR_ENVIRONMENT=staging` ([alan belgesindeki](../../DOMAIN.md)
  `nonprod` ortamı); `DWHNAVIGATOR_PUBLIC_ORIGIN` ve `DWHNAVIGATOR_CORS_ALLOW_ORIGINS` için
  uygulamanın HTTPS adresi `https://dwhnavigator.ailab-test.kuveytturk.com.tr` (Decision 20);
  güvenilen ingress pod ağı `DWHNAVIGATOR_TRUSTED_PROXY_CIDRS=10.42.0.0/16` (DWH Code Review'da
  çalışan değer); `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME=admin`; boş
  `DWHNAVIGATOR_OTEL_EXPORTER_OTLP_ENDPOINT` (kümede toplayıcı yoktur; user-accounts Requirement
  19); data-dictionary PRD'lerinin dağıtım girdisi olarak tanımladığı sır olmayan ayarlar
  (llm-connection ve question-analysis). Model sunucusunun adresi burada yoktur; model bağlantısı
  yönetim ekranından girilir ve PostgreSQL'de durur.
- `backend.resources` (Requirement 2) ve `backend.networkPolicy.egress` (Requirement 10).
- `frontend.ingress`: sınıf `nginx`, adres `dwhnavigator.ailab-test.kuveytturk.com.tr` (Decision
  20), TLS Secret'ı `ailab-tls`.
- `postgres.enabled: true` (10Gi, `nfs-sc`) ve `migration.enabled: true`.

Render denetimi bu dosyada sır görünümlü anahtarı, PEM özel anahtarını, boş eşi ve `/8`'den geniş
adres bloğunu reddeder (rules/45).

Requirement 9: Chart içi veritabanının sırları `deploy.sh`'ın ürettiği üç Secret'tadır:
`dwhnavigator-postgres` (sahip rolü), `dwhnavigator-migration` (sahip rolünün bağlantısı ve uygulama
rolünün adı ile parolası) ve `dwhnavigator-database` (uygulama rolünün `DWHNAVIGATOR_DATABASE_URL`
bağlantısı). Parolalar ilk kurulumda tahmin edilemez rastgele üreteçle üretilir ve Secret varken
yeniden üretilmez (veritabanı ilk parolayı diskte tuttuğu için). Backend yalnız
`dwhnavigator-database`'i görür (rules/45).

Requirement 10: Ağ izin kuralları (varsayılan: her şey kapalı):

| İş yükü | Giriş | Çıkış |
|---|---|---|
| backend | `kube-system` ingress denetleyicisi, TCP 8000 | DNS (`kube-system` `kube-dns`, UDP ve TCP 53); aynı release'in PostgreSQL podu, TCP 5432; model sunucusu (RunAI ucu): tek adres ve tek port, DWH Code Review'da çalışan `10.14.3.99/32` TCP 443 (dağıtımdan önce yeniden doğrulanır; Riskler'deki bekleyen bilgi) |
| frontend | `kube-system` ingress denetleyicisi, TCP 8080 | Yok |
| PostgreSQL | Yalnız aynı release'in backend ve göç podları, TCP 5432 | Yok |
| göç Job'u | Yok | DNS; PostgreSQL 5432 |

Dış adresler yalnız `values-project.yaml`'dadır. Listede olmayan hedefe backend'den bağlantı
kurulamaz; internete ve listede olmayan başka bir kurum adresine çıkış yoktur. Model sunucusunun
kuralı adres yeniden doğrulanmadan yazılmaz; o sürede model çağrıları bağlantı hatasıyla biter ve analiz
"Analiz yapılamadı" olur (question-analysis). Uygulamanın özel ağ adresi denetimi llm-connection
PRD'sindeki ek savunmadır; asıl sınır bu kuraldır.

Requirement 11: Giriş denetleyicisi ve kenar:

- Ingress `nginx` sınıfıyla uygulamanın adresini (`dwhnavigator.ailab-test.kuveytturk.com.tr`,
  Decision 20) `ailab-tls` sertifikasıyla sunar; `deploy.sh` eksikse `ailab-tls`'i `kt-verim`
  namespace'inden kopyalar (rules/45).
- Yalnız `/api/dwhnavigator/v1` öneki backend'e, `/` frontend'e gider; backend'in `/docs` ve
  `/openapi.json` uçları dışarıdan erişilemez.
- API yolunda 20 MB'a kadar istek gövdesi kabul edilir; büyüğü uygulamaya ulaşmadan 413 alır.
  Uçların daha küçük sınırları kendi PRD'lerindedir. Nonprod'da bu sınır giriş denetleyicisine
  ingress açıklamasıyla (annotation) verilir. Bu, fabrika chart'ına gelecek ingress açıklamaları
  seçeneğine bağlıdır (fabrika bağımlılığı, Dağıtım etkisi); seçenek gelmeden denetleyicinin
  varsayılanı (ingress-nginx'te 1 MB) geçerli olacağı için nonprod'a dağıtım yapılmaz (Decision 22).
- Yavaş istemci koruması kenardadır: istek başlığını ve gövdesini okuma süreleri en çok 60 saniyedir
  (ingress-nginx ve nginx varsayılanı); kaynağın 120 saniyelik okuma sınırının karşılığı budur. Backend
  Service'ine yalnız giriş denetleyicisi ulaşabildiği için istemci backend'e doğrudan bağlanamaz.
- HSTS ve sürümsüz `Server` başlığı user-accounts Requirement 14'tedir; giriş denetleyicisi arka
  sunucunun `Server` başlığını kendi başlığıyla değiştirir.

Requirement 12: Uzun işler ve canlı akış kenardan kesilmeden geçer:

- Yanıtı 60 saniyeyi aşabilecek hiçbir istek tek istek olarak tasarlanmaz; böyle işler sunucuda iş
  olarak yürür ve ilerlemesi SSE (sunucudan tarayıcıya canlı olay akışı) ile gelir. İş modeli
  question-analysis PRD'sindedir; list-search ve llm-connection uçları da bu kurala uyar.
- Her SSE yanıtı `X-Accel-Buffering: no` başlığını taşır (vekil akışı biriktirmesin diye) ve açık
  kaldığı sürece en geç 15 saniyede bir canlı tutma satırı (SSE yorum satırı; biçimi question-analysis
  Requirement 10'dadır) gönderir; böylece vekilin 60
  saniyelik okuma süresi açık bir akışı kesmez.
- Akış herhangi bir nedenle kapanırsa (vekil, ağ ya da belirtecin bitişi, user-accounts
  Requirement 12) sunucudaki iş sürer; ön yüz yeniden bağlanır.
- Yerel vekil ve nonprod giriş denetleyicisi aynı davranır; kaynağın önerdiği 900 saniyelik okuma
  süresi taşınmaz (Decision 11).

Requirement 13: İmajlar ve yayın:

- `.github/workflows/image-build.yml` `main` dalına her birleşmede backend ve frontend imajlarını
  `app/infra/Dockerfile.backend.release` ve `app/infra/Dockerfile.frontend.release` ile derler,
  `ghcr.io/kt-vibecoding/dwhnavigator-backend` ve `-frontend` adlarıyla `latest`, UTC tarih, kısa ve tam
  commit etiketleriyle yayımlar. Küme onları
  `cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/dwhnavigator-{backend,frontend}` yolundan çeker.
- Backend release imajına yalnız `app/backend/app`, `alembic.ini` ve `schema/` girer;
  llm-connection PRD'si model sunucusu için kurum kök sertifikası isterse o da imaja girer. İmajda
  `.xlsx` dosyası, `.env` dosyası, özel anahtar, test verisi ve Windows betiği bulunmaz; bu, imaj
  içerik testiyle doğrulanır (fabrikanın `.dockerignore`'u kara listedir, beyaz liste değildir).
- Backend imajı uvicorn'u `--no-server-header` ile başlatır (user-accounts Requirement 14) ve
  Requirement 2'deki kurulum ve kaldırma kurallarını uygular.

Requirement 14: Backend ve frontend release imajları, PRD kabulünden önce ve her taban imaj özeti
veya bağımlılık değişikliğinde Trivy ile imaj olarak taranır (işletim sistemi ve dil paketleri, gömülü
sır, yapılandırma). Düzeltmesi yayımlanmış zafiyet sayısı 0, gömülü sır bulgusu 0'dır. Düzeltmesi
henüz olmayan bulgu, teknoloji profilinin bakım kuralına göre gerekçe, kapsam ve süreyle
`dependency-admission.json`'a istisna olarak yazılır; kaynağın "her önem seviyesinde 0" ölçümü hedef
olarak korunur ama düzeltmesi olmayan bulgu bu kayıt yoluyla kabul edilir. Tarama araç sürümü ve
zafiyet veritabanı tarihiyle koşum raporuna yazılır (Decision 16).

Requirement 15: Argümansız `deploy.sh` rules/45'teki sırayı izler: girdileri doğrular; `values.yaml`'ın
üstüne `values-project.yaml`'ı katmanlar; Azure'un `latest` isteğini tam 40 karakterlik
`BUILD_SOURCEVERSION` etiketine çözer; her imajın yayımını en çok `IMAGE_WAIT_SECONDS` (20 dakika)
bekler, yoksa kümeye dokunmadan durur (düğüm aynasından çekilen PostgreSQL imajı için kayıt defteri
yanıt vermez; bu `[IMAGE] UNKNOWN` olarak yazılır ve dağıtım sürer); namespace'i ve eksikse
`ailab-tls`'i hazırlar; `deploy-hooks.sh` ile runtime Secret'ı, ardından veritabanı Secret'larını
hazırlar; süren release'i çözer; `helm upgrade --install --atomic --wait --wait-for-jobs --timeout 30m`
çalıştırır. Release ve namespace adı argümansız çağrıda `dwhnavigator`'dır (Decision 20). `--render`
kümeye erişmeden ve kancayı çalıştırmadan aynı değerlerle çıktı üretir.

Requirement 16: Başarısız güncelleme `--atomic` ile kendiliğinden önceki sürüme döner ve şemayı geri
indirmez. Elle geri alma provası bu teslimin kapsamında değildir (Decision 17).

Requirement 17: Yerel geliştirme Docker Compose ile yapılır ve Windows ile macOS'ta aynı dosyalarla
çalışır (proje sahibinin 2026-10-08 kararı, Decision 15):

- Docker Desktop kurum uygulama kataloğundan edinilir (rules/05). Yerel yığın iskeletin Compose
  dosyasıyla (`app/infra/docker-compose.local.yml`) PostgreSQL 17 (Requirement 3'teki özetle aynı
  imaj), backend, frontend ve yerel vekili (nginx) çalıştırır; göçler uygulanır; uygulama
  `http://localhost:<APP_HTTP_PORT>` adresinde açılır.
- Kaynaktaki `baslat.bat` ve `scripts/stop_servers.ps1`'in yerini, yerel yığını başlatan, durduran ve
  durumunu (servislerin ayakta olup olmadığı, hazır olma ve uygulama adresi) gösteren ajan komutları
  alır: Claude Code ve Codex için skill'ler (kodlama ajanının çağırabildiği hazır komutlar). Bu
  komutları fabrika sağlar (ayrı fabrika işi); komutlar iskeletin yerel yığın akışıyla aynı Compose
  proje adını, dosya seçimini ve yerel sırları kullanır. Proje Windows'a veya macOS'a özel başlatma
  betiği yazmaz.
- Projenin kendi yerel dosyaları (Compose dosyası, `app/infra/nginx/nginx.local.conf`,
  `app/infra/.env.example`) iki işletim sisteminde aynı davranır: göreli yollar ve iki sistemin Docker
  Desktop'ında bulunan özellikler kullanılır; satır sonları depoda LF'dir (fabrikanın
  `.gitattributes`'ı).
- Yerel sırlar Git dışında, geliştiricinin makinesinde üretilir: imza anahtarı ve veritabanı parolası
  `scripts/dev-secrets.sh` ile; kalıcı ayar şifreleme anahtarı (anlamı
  [llm-connection](../../../data-dictionary/PRDs/003-llm-connection/PRD.md) Requirement 1) fabrikanın
  yerel sır üretimiyle, imza anahtarı gibi bir kez üretilir (fabrika bağımlılığı, Dağıtım etkisi); o
  gelene kadar geliştirici kendi ürettiği değeri Git'in yok saydığı `app/infra/.env` dosyasına bir kez
  yazar.
- Yerel vekil Requirement 11 ve 12'deki kenar davranışını uygular: 20 MB gövde (fazlası 413),
  varsayılan 60 saniyelik vekil okuma süresi, `server_tokens off`, canlı akış biriktirilmez, güvenlik
  başlıkları (user-accounts Requirement 14).
- Varsayılan yerel ağ dışarı çıkmaz. Model sunucusuna yerel erişim yalnız DWH Code Review'daki gibi
  isteğe bağlı bir yerel çıkış kapısıyla açılır: Git'in yok saydığı `app/infra/.env` dosyasına
  `COMPOSE_PROFILES=local-egress` yazılınca kapı başlar ve yalnız aynı dosyada verilen tek model
  sunucusu adresine ve portuna iletir; backend iç ağda kalır, profil yoksa hiçbir şey dışarı çıkmaz ve
  model adı çözülmez (Decision 14).
- Yerel süper yönetici `scripts/create-super-admin.sh` ile ya da `app/infra/.env`'de verilen başlangıç
  parolasıyla açılır; iki rol, süper yöneticinin açtığı test hesaplarıyla denenir (user-accounts
  Requirement 16–18).

## API sözleşmesi

N/A — HTTP API yoktur. Dağıtım arayüzü: `helm/dwhnavigator/deploy.sh [--render|--apply]`; argümansız
çağrı `--apply`, kanonik `values.yaml` ile `values-project.yaml`, release ve namespace `dwhnavigator`
demektir. Girdiler ortam değişkenidir: `IMAGE_TAG`, `BUILD_SOURCEVERSION`, `TF_BUILD`, Requirement 7'deki
isteğe bağlı gizli değişkenler, `IMAGE_WAIT_SECONDS`, `PENDING_WAIT_SECONDS`, `HELM_TIMEOUT`. Çıkış kodu
0 başarı, 1 dağıtım hatası, 2 geçersiz girdidir; log işaretleri `[IMAGE]`, `[HOOK]`, `[RUNTIME]`,
`[DATABASE]` ve `[RELEASE]` önekini taşır. Yerel yığının arayüzü fabrikanın ajan komutlarıdır
(Requirement 17).

## Güvenlik ve yetkilendirme

- `deploy.sh` Azure işinin sağladığı `KUBECONFIG` bağlantısını kullanır; kubeconfig içeriği, Secret
  değeri ve kayıt defteri belirteci loga yazılmaz; geçici dosyalar yalnız sahibine açıktır.
- Nonprod `admin` süper yöneticisini backend ilk açılışında runtime Secret'taki başlangıç parolasıyla
  bir kez açar (user-accounts Requirement 17); kanca ve `deploy.sh` hesap açmaz, parolayı yalnız
  Secret'a taşır.
- Kanca imza anahtarını ve ayar şifreleme anahtarını ilk dağıtımda kendiliğinden üretir; rules/58'in
  kriptografik anahtar yaşam döngüsünün otomatikleşmesi için istediği eylem bazlı insan onayı bu PRD'nin
  kabulüyle kayda geçer (Decision 13).
- Backend kümenin dışına yalnız model sunucusuna çıkar; kural tek adres ve tek port olarak yazılır
  (Requirement 10). Backend Service'ine yalnız giriş denetleyicisi ulaşır; `/docs` ve `/openapi.json`
  dışarıya açılmaz (Requirement 11).
- Release imajlarının içeriği ve taraması Requirement 13 ve 14'tedir.

## Veri ve geçiş

- Kalıcı veri yalnız PostgreSQL diskindedir; StatefulSet'in disk talebi release kaldırılsa da silinmez.
- Kaynaktan veri taşıma yoktur: kurulu bir kaynak sürüm yoktur; sözlük ilk kurulumda yönetim
  ekranından Excel ile içe aktarılır. Kaynağın kurulum dosyaları (`Dockerfile`, `compose.yaml`,
  `requirements.lock`, `.env.example`, `.dockerignore`, `docs/KURULUM.md`, `baslat.bat`,
  `scripts/stop_servers.ps1`, `.claude/launch.json`) taşınmaz; yerlerini iskeletin dosyaları ve
  fabrikanın ajan komutları alır.
- İlk kurulum sırası: (1) Azure işi chart'ı kurar; (2) göç Job'u uygulama rolünü, şemayı, rolleri,
  kiracıyı ve başlangıç listelerini hazırlar; (3) backend açılır, başlangıç parolası verilmişse `admin`'i
  açar ve boş indeksle hazır olur; (4) süper yönetici girer, sözlüğü içe aktarır, model bağlantısını
  ekler ve hesapları açar; (5) kullanıcılar girer.
- Veritabanı yedeği ve yedekten geri dönüş yoktur (Decision 21); yönetici önemli değişikliklerden
  sonra sözlüğü ve terim listelerini yönetim ekranından Excel olarak dışa aktarır.

## Gözlemlenebilirlik

`deploy.sh` ve kanca her adımı sabit işaretle yazar (imaj yayımı, kanca, Secret anahtar adları,
veritabanı Secret'ları, release durumu); hata iletisi girilen değeri yankılamaz. PostgreSQL ve backend
logları standart çıktıya gider. Chart gözlemlenebilirlik iş yükü içermez (rules/25 ayrı PRD ister);
nonprod'da telemetri adresi boştur (user-accounts Requirement 19). Bu PRD yeni ölçüm tanımlamaz.

## Dağıtım etkisi

- Azure işi (açılıp açılmadığı Riskler'deki bekleyen bilgidir) aynı komutla çalışır ve yeni ayar
  veya gizli değişken istemez. `JWT_PRIVATE_KEY`, `SETTINGS_ENCRYPTION_KEY` ve
  `DWHNAVIGATOR_ADMIN_PASSWORD` isteğe bağlıdır; Azure gizli değişkenleri betiğe kendiliğinden
  geçmediği için verilen her biri dağıtım adımının ortamına (`env:`) aynı adla açıkça eşlenir.
- Namespace'te 10Gi `nfs-sc` PostgreSQL diski, üç veritabanı Secret'ı, runtime Secret'ı ve `ailab-tls`
  kopyası oluşur. Azure işinin kimliği namespace'te Secret okuyup yazabilmeli ve Deployment'ı yeniden
  başlatabilmelidir.
- GHCR'da `dwhnavigator-backend` ve `dwhnavigator-frontend` paketleri ilk kez yayımlanır.
- Fabrikaya bağımlılıklar (fabrika işi olarak istenir; Decision 3): yerel yığın ajan komutları
  (Requirement 17); fabrika chart'ına backend güncelleme stratejisi seçeneği (`backend.strategy`; bu
  proje `Recreate` verir, Decision 5) ve `values-project.yaml`'dan verilen, üst sınırı olan ingress
  açıklamaları seçeneği (bu proje giriş denetleyicisinin gövde sınırını 20 MB yapar, Requirement 11);
  fabrikanın yerel sır üretimine bir kez üretilen ayar şifreleme anahtarı (Requirement 17; DWH Code
  Review da aynı anahtarı kullanır).
- Geliştirici cihazlarında Docker Desktop kurum kataloğundan kurulur (rules/05).

## Test stratejisi

- Chart: `scripts/render-charts.sh` proje katmanını `deploy.sh`'ın release ve namespace adıyla
  fabrikanın yapı denetimlerinden geçirir (sıkılaştırma, yoklama, kaynak denetimi; Secret
  üretilmemesi; sır görünümlü anahtarın, boş eşin ve `/8`'den geniş bloğun reddi). Proje testi aynı
  çıktıda backend `replicas: 1`'i, backend çıkış eşlerinin tam olarak Requirement 10'daki liste
  olduğunu ve backend kaynak değerlerini doğrular. `deploy.sh --render` aynı katmanla render eder.
- Kanca: `tests/helm/deploy-hooks.test.sh` sahte `kubectl` ile iki anahtarın ilk kurulumda bir kez
  üretilip sonraki çalıştırmalarda korunmasını, isteğe bağlı değişkenlerin varken yazılıp yokken
  kümedeki değerin korunmasını, çözülmemiş `$(...)` metninin verilmemiş sayılmasını, okunamayan
  Secret'ta ve geçersiz anahtarda durmayı, değerin argümana ve loga düşmemesini ve gereksiz yeniden
  başlatma olmamasını sınar.
- Göç: boş veritabanında `alembic upgrade head`, uygulama rolünün tablo oluşturamaması, tohum
  verisinin varlığı.
- Hazır olma: birim ve gerçek PostgreSQL testleri rules/45 durumlarına ek olarak indeks kurulmadan
  503, kurulunca 200, sonraki yeniden kurmada 200 kalmayı ve indeks kurulurken canlılığın 200 olmasını
  sınar.
- İmaj: release imajları üzerinde içerik testi (pip, setuptools ve wheel'in bulunmaması; kullanıcı
  10001 ve kabuğu `/sbin/nologin`; `.xlsx`, `.env`, özel anahtar ve test verisinin bulunmaması;
  uvicorn'un `--no-server-header` ile başlaması) ve Trivy taraması (Requirement 14).
- Kenar: yerel vekil yapılandırmasının `nginx -t` ile geçerliliği; 20 MB'ı aşan istekte 413; sürümsüz
  `Server` başlığı; sahte bir işle açılan SSE akışında `X-Accel-Buffering: no` başlığı ve en geç 15
  saniyede bir canlı tutma satırı.
- Yerel işletim sistemleri: Acceptance 3 Windows ve macOS'ta ayrı ayrı koşulur.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: proje katmanıyla chart denetimi ve proje chart
  testi, kanca testi, göç, hazır olma, imaj içerik ve kenar testleri Requirement 1–13 ve 15 için
  geçer.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: backend ve frontend release imajlarının Trivy
  taramasında düzeltmesi yayımlanmış zafiyet ve gömülü sır bulgusu 0'dır; varsa düzeltmesi olmayan
  bulgular `dependency-admission.json`'da istisna olarak kayıtlıdır; sonuç araç sürümü ve veritabanı
  tarihiyle raporlanır (Requirement 14).
- [ ] Acceptance 3: L2 — Gerçek istemci/ortamda doğrulandı: Windows'ta ve macOS'ta (Docker Desktop)
  fabrikanın ajan komutuyla yerel yığın başlar, durum komutu servisleri, hazır olmayı ve adresi
  gösterir; göçler uygulanmıştır ve hazır olma 200 döner; tarayıcıda giriş ve yönetim ekranı açılır;
  19 MB'lık bir dosya vekilden geçer, 21 MB'lık dosya 413 alır; en az 3 dakika süren bir analizin
  (gerçek model sunucusuna yerel çıkış profiliyle ya da yavaş yanıt veren sahte model sunucusuyla)
  canlı akışı kesilmez ve en geç 15 saniyede bir canlı tutma satırı görülür; durdurma komutu yığını
  kapatır ve veritabanı birimi korunur. Kanıt iki işletim sistemi için ayrı raporlanır
  (Requirement 6, 11, 12, 17).
- [ ] Acceptance 4: L2 — Canlı nonprod küme koşumu (yerel kanıttan ayrı): argümansız Azure işi ek
  ayar veya gizli değişken olmadan kurar; podlar hazır, PostgreSQL diski 10Gi `nfs-sc` bağlı, göç
  Job'u başarılı; HTTPS adresi `ailab-tls` ile açılır, yanıtlarda HSTS ve sürümsüz `Server` başlığı
  vardır; `/docs` ve `/openapi.json` dışarıdan açılmaz; backend model sunucusuna ulaşır (Requirement
  10'daki kural yazıldıktan sonra) ve listede olmayan bir adrese ulaşamaz; 60 saniyeden uzun süren
  bir analizin canlı akışı giriş denetleyicisinde kesilmez; 19 MB'lık bir Excel yüklemesi uygulamaya
  ulaşır, 21 MB'lık yükleme 413 alır; backend Deployment'ı `Recreate` stratejisiyle güncellenir
  (Requirement 1–13, 15; Decision 22).

## Kararlar

- Decision 8: Runtime Secret yalnız üç anahtar taşır: imza anahtarı, ayar şifreleme anahtarı ve
  isteğe bağlı süper yönetici başlangıç parolası. Model bağlantıları her ortamda yönetim ekranından
  yönetildiği ve API anahtarları PostgreSQL'de şifreli durduğu için (llm-connection) Secret'ta model
  anahtarı yoktur; SQL Server bilgisi de yoktur.
- Decision 9: PostgreSQL imajı yerel Compose'daki `postgres:17.10` ile aynı özettedir ve DWH Code
  Review ile KT Verim'in nonprod'da çalışan yoluyla, düğümün Docker Hub aynasından çekilir. Disk 10Gi,
  depolama sınıfı `nfs-sc`'dir (kümenin varsayılanı, açıkça yazılır); kaynak değerleri fabrikanın
  varsayılanıdır.
- Decision 10: Backend bellek sınırı kaynağın `mem_limit: 2g` değerine göre 2Gi, isteği 512Mi'dır:
  arama indeksi süreç belleğindedir ve Excel dosyaları bellekte okunur ve üretilir; fabrikanın 512Mi
  sınırı buna yetmez. CPU isteği 100m, sınırı 1'dir; indeks kurulumu kısa süre tek çekirdeği kullanır.
- Decision 11: Uzun analizler için okuma süresi uzatılmaz; iş, canlı akış ve 15 saniyelik canlı tutma
  kullanılır (Requirement 12). Kaynağın 900 saniyelik vekil süresi, cevabın tek istekte döndüğü
  `/api/ask` içindi; hedefte analiz iş olarak yürüdüğünden uzun tek istek yoktur. Bu yol giriş
  denetleyicisinin bilinmeyen varsayılanlarından etkilenmez ve yerelde de aynı davranır.
- Decision 12: Hazır olma ilk indeks kurulumunu bekler (Requirement 6); kaynak da `vsa serve` ile
  indeksi kurmadan dinlemeye başlamıyordu (`HEALTHCHECK` 90 saniyelik başlangıç payı). Böylece güncellemede
  yeni pod indeksi hazır olmadan trafik almaz.
- Decision 13: İmza anahtarı ve ayar şifreleme anahtarı Azure değişkeninde taşınmaz; kanca ilk
  kurulumda bir kez üretir, sonraki çalıştırmalarda kümedekini kullanır, pipeline değişkeni verilirse o
  geçerlidir (DWH Code Review'da aynı). rules/58'in kriptografik anahtar yaşam döngüsü için istediği
  eylem bazlı insan onayı bu PRD'nin kabulüdür.
- Decision 14: Yerel Compose varsayılan olarak dışarı çıkmaz; model sunucusuna çıkış, açıkça seçilen
  `local-egress` profiliyle ve tek adres ile porta sınırlıdır (DWH Code Review'daki yerel çıkış kapısının
  benzeri; orada hedef geliştiricinin kendi makinesiydi, burada ağdaki model sunucusudur).
- Decision 15: Yerel geliştirme Docker Compose ile kalır ve Windows ile macOS'ta çalışır; kaynaktaki
  Windows betiklerinin yerini fabrikanın sağlayacağı yerel yığın ajan komutları (Claude Code ve Codex
  skill'leri) alır (proje sahibinin 2026-10-08 kararı). Proje işletim sistemine özel betik yazmaz;
  böylece yerel akış tek kalır ve fabrika güncellemeleriyle gelir.
- Decision 16: İmaj taraması geliştirici tarafından yerelde koşulur ve koşum raporuna yazılır;
  fabrikanın yönettiği imaj yayın akışında tarama adımı yoktur ve proje onu değiştirmez (Decision 3).
- Decision 17: Elle geri alma (`helm rollback`) provası yapılmaz; başarısız güncellemede `--atomic` ile
  kendiliğinden geri dönüş geçerlidir. DWH Code Review'da aynı fabrika betiğiyle bu yeterli bulundu.
- Decision 18: Chart sürümü fabrikadan gelir; Helm güncellemesi artan chart sürümü istemez ve sürümü
  projede yükseltmek fabrikanın yönettiği `Chart.yaml`'ı elle düzenlemek olur.
- Decision 19: Kimlik yerel hesaplar olduğu için (user-accounts Decision 7) dizin çıkış kuralı, dizin
  sertifika dosyası ve dizin ayarları yoktur (proje sahibinin 2026-10-08 kararı); backend'in kümenin
  dışındaki tek hedefi model sunucusudur.

- Decision 20: Nonprod adresi `https://dwhnavigator.ailab-test.kuveytturk.com.tr`, namespace ve
  release adı `dwhnavigator`'dır. Gerekçe: `deploy.sh` argümansız çağrıda bu adları kullanır; DWH
  Code Review aynı `ailab-tls` sertifikasıyla `dwhcodereview.ailab-test.kuveytturk.com.tr` adresini
  sunar.
- Decision 21: Veritabanı yedeği alınmaz; chart'ta yedek işi yoktur ve disk kaybı riski kabul edilir
  (DWH Code Review ile aynı; proje sahibinin bu teslim için kararı). Sözlük ve terim listeleri
  yönetim ekranından Excel olarak dışa aktarılabildiği için yönetici önemli değişikliklerden sonra
  dışa aktarım alır; analiz kayıtları, kayıtlı cevaplar, oylar, ayarlar ve model bağlantıları için
  kopya yoktur.
- Decision 22: Nonprod'a ilk dağıtım, fabrika chart'ına backend güncelleme stratejisi
  (`backend.strategy`) ve ingress açıklamaları seçenekleri eklenip bu projede kullanıldıktan sonra
  yapılır. Gerekçe: seçenekler gelmeden kümede gövde sınırı 1 MB'tır (sözlük Excel'i
  yüklenemeyebilir) ve güncellemede eski ve yeni backend podu kısa süre birlikte çalışır; "yarıda
  kesildi" tespiti ve tek kopya varsayımı bozulur (Decision 5).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- Tek kopya PostgreSQL'de disk arızası sözlüğü, terim düzenlemelerini, ayarları, model
  bağlantılarını, analiz kayıtlarını ve oyları kaybettirir; yedek olmadığı için (Decision 21) bu
  risk kabul edilmiştir. Analiz kayıtları ve oylar süresiz saklandığı için kaybın kapsamı zamanla
  büyür.
- Runtime Secret silinirse kanca yeni bir ayar şifreleme anahtarı üretir; PostgreSQL'deki model API
  anahtarları eski anahtarla şifreli kaldığı için açılamaz ve yöneticinin onları yeniden girmesi
  gerekir; imza anahtarı da yenilendiği için bütün oturumlar kapanır.
- `Recreate` güncellemesi kısa bir kesinti demektir: eski pod durduktan sonra yeni pod ilk arama
  indeksini kurup hazır olana kadar uygulama yanıt vermez; süren analiz ve toplu arama işleri "yarıda
  kesildi" olur (question-analysis, list-search).
- İlk nonprod dağıtımı fabrika chart'ına gelecek iki seçeneğe (güncelleme stratejisi ve ingress
  açıklamaları) bağlıdır (Decision 22); seçenekler gecikirse nonprod dağıtımı da gecikir.
- Giriş denetleyicisinin süre ve tamponlama varsayılanları kümede doğrulanmadı; Acceptance 4 bunları
  gerçek akışla ölçer.
- Model sunucusunun adresi doğrulanmadan çıkış kuralı yazılmaz ve nonprod'da analiz yapılamaz
  (aşağıdaki bekleyen bilgi); adres veya IP değişirse çıkış kuralı çağrıları keser ve kural yeniden
  yazılmalıdır.
- Pod tanımı süreç sayısı sınırı taşımaz; kaynaktaki 256 süreç sınırının karşılığı düğüm ayarına
  bağlıdır.
- Azure gizli değişkeni dağıtım adımının ortamına eşlenmezse kanca onu görmez ve `admin` açılmaz; kanca
  logu `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD not provided` der; süper yönetici elle komutla
  açılır (user-accounts Requirement 18).
- GHCR paketleri ilk kez yayımlanacak; kurum vekil önbelleğinin onları çekebildiği Acceptance 4'te
  görülür.
- Yerel yığının Windows ve macOS'ta ajan komutlarıyla çalışması fabrika işinin teslimine bağlıdır;
  o gelene kadar yerel yığın macOS'ta iskeletin `scripts/stack.sh` akışıyla açılır, Windows'ta
  desteklenen bir açılış yolu yoktur.
- Backend'in 64 MiB'lık `/tmp`'si fabrika şablonunda sabittir; büyük Excel'i diske yazan bir yükleme
  veya rapor yolu bu alanı doldurursa istek başarısız olur.
- Düzeltmesi yayımlanmamış zafiyetler (ör. Python çalışma ortamında) istisna kaydıyla taşınır; her taban
  imaj güncellemesinde yeniden değerlendirilir.
- Geri almada şema geri inmez; genişletici olmayan bir göç önceki sürümü bozar.
- **Bekleyen bilgi:** Bu depo için Azure dağıtım işinin (her birleşmede
  `helm/dwhnavigator/deploy.sh`'ı argümansız çağıran otomatik adım) açılıp açılmadığı bilinmiyor;
  bilgi ve gerekirse işin açılması işletim ekibinden beklenir. İş, DWH Code Review'daki gibi
  `kt-vibecoding/kt-dwhnavigator` deposunun `main` dalına her birleşmede çalışmalı, `KUBECONFIG`'i
  sağlamalı, namespace'te Secret okuyup yazabilmeli ve Deployment'ı yeniden başlatabilmelidir;
  `DWHNAVIGATOR_ADMIN_PASSWORD` gizli değişkeni bu işin dağıtım adımının ortamına aynı adla eşlenir.
  İş açılmadan nonprod dağıtımı ve Acceptance 4 yapılamaz.
- **Bekleyen bilgi:** Kümeden RunAI model ucuna çıkış kuralının adresi ve portu işletim ve ağ
  ekibinden doğrulanmayı bekliyor: DWH Code Review'da nonprod'da çalışan kural `10.14.3.99/32`, TCP
  443'tür ve dağıtımdan önce yeniden doğrulanır. Doğrulanmadan Requirement 10'daki model kuralı
  yazılmaz; o sürede nonprod'da her analiz "Analiz yapılamadı" ile biter ve Acceptance 4'ün model
  adımı ile [llm-connection](../../../data-dictionary/PRDs/003-llm-connection/PRD.md) Acceptance 8
  yapılamaz.
