# PRD — user-accounts

Status: Draft

Version: 0.1.0

Domain: [application-foundation](../../DOMAIN.md)

## Amaç

DWH Navigator'ı kullanan herkesin, uygulama yöneticisinin (süper yönetici) açtığı yerel hesapla giriş
yapması ve `kullanici` ya da `yonetici` rolüyle yetkilendirilmesi. Kaynak uygulamada soru ekranı
kimlik sormuyordu; yönetim ekranı ise herkesin paylaştığı tek bir parolayla (`VSA_ADMIN_PASSWORD`;
tarayıcının açtığı kullanıcı adı/parola penceresi, HTTP Basic) korunuyordu. Hedefte ikisinin yerini
kişiye ait hesap, rol ve oturum alır; analiz kayıtlarında ve oylarda kişi, istemci adresi yerine
oturumdaki kullanıcıdır. Kimlik doğrulama fabrikanın taban modelidir (`rules/21`: uygulamada saklanan
parola özeti ve uygulamanın imzaladığı erişim belirteci); dış kimlik sağlayıcı yoktur. Bu PRD,
`rules/21`'in kabul edilmiş PRD şartına bağladığı yenileme belirtecini ve sunucu tarafı oturum
kaydını da tanımlar. Kaynağın web katmanındaki korumaların (siteler arası istek denetimi, güvenlik
başlıkları, hata yanıtları) hedefte nerede karşılandığı da buradadır; hiçbiri sessizce düşmez.

## Aktörler ve sonuçlar

- **Kullanıcı (`kullanici`):** Süper yöneticinin açtığı hesapla girer. İlk girişte kendisine verilen
  tek kullanımlık parolayı kendi seçtiği parolayla değiştirmek zorundadır; sonra parolasını istediği
  zaman değiştirir. Soru sorar, toplu arama yapar, oy verir, sözlükte gezer, rapor indirir.
- **Yönetici (`yonetici`):** Kullanıcının yapabildiği her şeye ek olarak yönetim ekranını kullanır.
- **Uygulama yöneticisi (süper yönetici):** Yerel hesaptır. Hesap açar (kullanıcı adı, görünen ad,
  rol), rol değiştirir, parolayı sıfırlar, hesabı pasifleştirir ya da yeniden etkinleştirir. Açtığı
  veya sıfırladığı her hesap için uygulamanın ürettiği tek kullanımlık parolayı bir kez görür ve
  kişiye kendisi iletir. `nonprod`'da `admin` hesabı dağıtımdan sonra kendiliğinden açılır
  (Requirement 17).
- **İşletim ekibi:** Uygulama içinde rol değildir; süper yönetici parolası kaybolursa küme erişimiyle
  elle komut çalıştırarak sıfırlar (Requirement 18).
- **Geliştirici:** Yerelde süper yönetici hesabını açar; iki rolü kendi açtığı test hesaplarıyla dener.

Ölçülebilir sonuç: süper yöneticinin açtığı hesap tek kullanımlık parolayla girer, yeni parola
belirlemeden hiçbir ekrana ulaşamaz, yeni parolayla oturum alır; yanlış parola 401, `kullanici`'nın
yönetim işlemi 403, oturumsuz istek 401, başka siteden gelen durum değiştiren istek 403 alır; her
yanıt kaynaktaki güvenlik başlıklarını taşır; her giriş, çıkış, parola değişikliği, hesap açma, rol,
durum ve parola sıfırlama bir denetim olayı üretir.

## Değişmezler ve sınırlar

- Decision 1: Kimlik yalnız uygulamanın yerel hesaplarıdır. Parola uygulamada yalnız iskeletin
  yavaş ve tuzlu parola özetiyle (Argon2) saklanır. Düz parola, tek kullanımlık parola ve parola
  özeti hiçbir loga, erişim belirtecine, değişiklik kaydına, telemetriye ve API yanıtına girmez;
  tek istisna, tek kullanımlık parolanın üretildiği hesap açma veya sıfırlama yanıtıdır.
- Decision 2: Roller yalnız `kullanici` ve `yonetici`dir; süper yönetici dışındaki her hesabın tam
  bir rolü vardır. `yonetici`, `kullanici`'nın yapabildiği her şeyi yapar. İskeletin `super_admin`
  rolü uygulama yöneticisine aittir; API ile verilemez, alınamaz ve her rol denetiminden merkezi
  olarak geçer (Decision 9).
- Decision 3: Yetki backend sınırında denetlenir; menü veya düğme gizlemek yetki değildir. Sağlık
  uçları (`/liveness`, `/readiness`), giriş, parola değiştirme, yenileme ve çıkış dışındaki her API
  ve canlı olay akışı (SSE: sunucudan tarayıcıya canlı olay akışı) isteği geçerli oturum ve uygun rol
  ister.
- Decision 4: Hesabı yalnız süper yönetici açar; kendi kendine kayıt yoktur. Parola belirleme kanıtı
  (tek kullanımlık parola) yalnız uygulamanın tahmin edilemez rastgele üreteciyle (CSPRNG) üretilir,
  tek kullanımlık ve süreli olur (rules/58).
- Decision 5: Bütün hesaplar iskeletin tek `platform` kiracısındadır. Hangi data-dictionary ucunun
  hangi rolü istediği o uçların PRD'lerindedir; bu PRD rolleri, eşleme kuralını (Requirement 10) ve
  denetimi tanımlar.
- Decision 6: Hesap silinmez, yalnız pasifleştirilir; analiz kayıtları ve oylar kişiye bağlı kalır.

## Mevcut davranış

Kaynak `~/codes/kt-dwhnavigator` (`76e21a3`) ve hedef iskelet `~/codes/dwhnavigator-kt` bugün şöyle
çalışır; her maddenin sonunda hedefteki değişiklik yazılıdır.

- **Yönetim ekranı parolası** (`src/vsa/web/security.py` `AdminGuard`, `is_admin_path`,
  `ADMIN_PREFIXES`; ADR-047): `/admin`, `/api/admin/…`, `/api/settings`, `/api/reindex` ve
  `/api/llm…` yolları, `VSA_ADMIN_PASSWORD` (ya da `VSA_ADMIN_PASSWORD_FILE` ile verilen dosya)
  tanımlıysa HTTP Basic ister. Kullanıcı adı ne yazılırsa kabul edilir; yalnız parola sabit zamanlı
  karşılaştırılır (`hmac.compare_digest`); başarısız yanıt
  `WWW-Authenticate: Basic realm="DWH Navigator yonetim"` taşır. Parola herkes için aynıdır; kimin
  girdiği bilinmez. **Hedefte:** kişiye ait hesap ve `yonetici` rolü; iki parola ayarı ve tarayıcı
  parola penceresi kalkar (Requirement 10).
- **Parolasız kip** (`AdminGuard.check`): parola tanımlı değilse yönetim ekranı yalnız sunucunun
  kendisinden açılır: istemci adresi aynı makine (loopback), `X-Forwarded-For` yok ve `Host` başlığı
  `localhost`, `127.0.0.1` ya da `::1` (DNS rebinding'e, yani kötü niyetli bir alan adının yerel
  adrese yönlendirilmesine karşı). **Hedefte:** makineye göre istisna yoktur; yerelde de giriş ve rol
  gerekir (Requirement 10).
- **Hatalı parola sınırı** (`MAX_FAILURES = 5`, `LOCKOUT_SECONDS = 300`): aynı istemci adresinden
  5 hatalı denemeden sonra 5 dakika 429; sayaç süreç içindedir. **Hedefte:** kullanıcı adı ve adres
  başına 15 dakikada 5, adres başına 15 dakikada 30 hatalı deneme; kalıcı kilit yok (Requirement 9).
- **Kimliksiz soru ekranı** (`src/vsa/web/server.py` `make_handler`): `/`, `/api/ask`,
  `/api/ask/cancel`, `/api/list…`, `/api/feedback`, `/api/objects`, `/api/object/…`, `/api/galaxy`,
  `/api/report/…` ve `/api/status` herkese açıktır (`docs/GUVENLIK.md` "Kalan riskler" 2: kapalı ağ,
  ekip aracı). **Hedefte:** hepsinin karşılığı oturum ve `kullanici` rolü ister; kaynağı bugün
  kullanan herkes ilk açılışta giriş ekranıyla karşılaşır ve süper yöneticiden hesap ister
  (Requirement 10).
- **Kayıtlarda kimlik** (`App._log_analysis`, `App._host`, `App.feedback`; `static/index.html`
  `VOTER`): analiz kaydına istemci adresi ve ters DNS sorgusuyla bulunan makine adı, oy kaydına
  tarayıcının `localStorage`'da tuttuğu rastgele `vsa-voter` kimliği (yoksa istemci adresi) yazılır;
  "kişi başına son oy" bu kimliğe göre sayılır. **Hedefte:** oturumdaki kullanıcının `public_id`'si
  ve görünen adı; adres, makine adı ve istemcinin gönderdiği kimlik metni yazılmaz (Requirement 11).
- **Siteler arası istek denetimi** (`security.cross_site`): her POST'ta `Sec-Fetch-Site` varsa yalnız
  `same-origin` ve `none` kabul edilir; yoksa ve `Origin` varsa `X-Forwarded-Host`/`Host` ile
  eşleşmelidir; `Origin: null` reddedilir; ret 403 "Başka bir siteden gelen istek reddedildi".
  **Hedefte:** aynı kural durum değiştiren her istekte backend'de; karşılaştırma yapılandırılmış
  uygulama adresiyle; çerez kullanan uçlarda `Origin` ayrıca zorunlu (Requirement 13).
- **Güvenlik başlıkları** (`security.BASE_HEADERS`, `API_CSP`, `page_csp`; `Handler._send`,
  `send_error`): her yanıtta `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `X-Permitted-Cross-Domain-Policies: none`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`,
  `Cross-Origin-Resource-Policy: same-origin`,
  `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()` ve
  `Cache-Control: no-store`; API yanıtlarında
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`; sayfalarda
  yalnız sayfanın kendi betik ve stil bloklarına SHA-256 özetiyle izin veren, `'unsafe-inline'`
  içermeyen içerik güvenlik politikası (CSP: tarayıcıya sayfanın hangi kaynakları yükleyebileceğini
  söyleyen başlık). Sunucunun kendi hata yanıtları da aynı başlıkları taşır. HSTS (tarayıcıya siteyi
  yalnız HTTPS ile açmasını söyleyen başlık) ters vekilde verilir (`docs/KURULUM.md` §6).
  **Hedefte:** API başlıkları backend'de, sayfa başlıkları ön yüz sunucusunda (nginx)
  (Requirement 14).
- **Hata yanıtları ve sunucu adı** (`Handler._error`, `send_error`, `version_string`): hata gövdesi
  `{"error": "..."}`; beklenmeyen hatada genel ileti "Sunucu hatası (ayrıntı sunucu kaydında)",
  ayrıntı yalnız logda; `Server` başlığı yalnız `VSA`. Ancak 400 ve 404'te `ValueError` ve
  `FileNotFoundError` metni olduğu gibi döner. **Hedefte:** tek hata zarfı, iç ayrıntı yok, `Server`
  başlığında sürüm yok (Requirement 14, 15).
- **İskeletin girişi** (`app/backend/app/api/auth/endpoints.py`,
  `app/backend/app/services/auth_service.py`,
  `app/backend/app/infrastructure/repositories/user_repository.py`): kullanıcı adı veya e-postayla
  yerel parola girişi (`POST /auth/login`) ve `GET /auth/me`; ES256 imzalı 60 dakikalık erişim
  belirteci; belirteç ve kullanıcı bilgisi ön yüzde `localStorage`'da
  (`app/frontend/src/lib/authStorage.ts`); yenileme ve sunucu tarafı çıkış yok, çıkış yalnız
  tarayıcıdaki kaydı siler; hesap açma, parola değiştirme ve sıfırlama ucu ve ekranı yok; pasif hesap
  yanlış parolayla aynı 401'i alır; hata gövdeleri düz metin `detail`. **Hedefte:** yalnız kullanıcı
  adıyla giriş, 15 dakikalık bellek içi belirteç, yenileme çerezi, sunucu tarafı çıkış, hesap
  yönetimi ve parola akışları (Requirement 1–8).
- **İskeletin parola politikası** (`app/backend/app/core/security.py` `validate_password_strength`):
  en az 15, en çok 128 karakter; kompozisyon kuralı yok; 11 maddelik çevrimdışı yaygın parola listesi
  ve tek kısa birimin tekrarı reddi; hesap adını içeren parola reddi; politika yalnız süper yönetici
  komutunda uygulanır. **Hedefte:** kişinin belirlediği her parolaya uygulanır; liste genişler,
  Unicode normalleştirme ve şimdiki parolayla aynı olma reddi eklenir (Requirement 3).
- **İskeletin hız sınırı** (`app/backend/app/core/login_throttle.py`): kullanıcı adı ve adres başına
  15 dakikada 5 hatalı deneme; adres `request.client.host`, yani kümede giriş denetleyicisinin
  (ingress: kümeye gelen trafiği uygulamaya yönlendiren bileşen) adresi. **Hedefte:** adres yalnız
  güvenilen vekilden gelen `X-Forwarded-For`'dan; adres başına ek sınır; parola değiştirme de aynı
  sayaçla sınırlanır (Requirement 9).
- **İskeletin süper yönetici komutu** (`app/backend/app/scripts/create_super_admin.py`,
  `scripts/create-super-admin.sh`): hesabı açar ya da var olanın parolasını sıfırlar; parolayı önce
  süreç ortamındaki `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD`'dan, yoksa istemden veya
  `--password-stdin`'den okur; `platform` kiracısını da bu komut açar. İlk göç
  (`schema/alembic/versions/202608060001_platform_baseline.py`) yalnız `super_admin` rolünü ve
  `platform:access` iznini tohumlar. **Hedefte:** elle komut başlangıç parolasını okumaz; backend
  açılışta süper yöneticiyi bir kez açar (Requirement 17, 18); göç iki rolü ve kiracıyı tohumlar
  (Veri ve geçiş).
- **İskeletin güvenlik başlıkları** (`app/frontend/nginx.security-headers.conf`,
  `app/backend/app/main.py`): ön yüz sunucusu `nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer` ve `style-src 'self' 'unsafe-inline'` içeren CSP gönderir; backend
  hiçbir güvenlik başlığı eklemez; ön yüz sunucusunun `Server` başlığı nginx sürümünü taşır.
  **Hedefte:** Requirement 14.

## İşlevsel gereksinimler

Requirement 1: `POST /auth/login` kullanıcı adı ve parola alır. Kullanıcı adı NFKC ile
normalleştirilir (Unicode'da aynı görünen yazımların tek biçime indirilmesi), baştaki ve sondaki
boşluk atılır ve küçük harfe çevrilir; parola NFKC ile normalleştirilir ama kırpılmaz. Kullanıcı adı
en çok 64, parola en çok 128 karakter olabilir; aşan istek 422 alır. Sonuçlar: doğru parola ve etkin
hesapta oturum açılır (Requirement 6, 7); yanlış parola veya bilinmeyen kullanıcı adı 401
`invalid_credentials` alır ve yanıtın iletisi ve süresi hesabın var olup olmadığını ele vermez
(bilinmeyen adda da bir parola özeti doğrulaması yapılır); parola doğru ama hesap pasifse 403
`user_inactive`; parola doğru ama hesap yeni parola bekliyorsa oturum açılmaz ve 403
`password_change_required` döner; doğru tek kullanımlık parolanın süresi dolmuşsa 401
`one_time_password_expired` döner. Son üç ayrım yalnız doğru parolayı bilen kişiye görünür.

Requirement 2: Süper yönetici `POST /admin/users` ile hesap açar: kullanıcı adı (Requirement 1'deki
gibi normalleştirilir; 3–64 karakter; yalnız `a-z`, `0-9`, `.`, `_`, `-`), görünen ad (1–128
karakter, Türkçe harfler dahil Unicode; denetim karakteri içeremez) ve rol (`kullanici` veya
`yonetici`). Aynı kullanıcı adı, pasif hesaplar dahil, varsa 409 `username_taken` döner. Uygulama
tahmin edilemez rastgele üreteçle 20 karakterlik tek kullanımlık parola üretir (karışabilen `0`, `o`,
`1`, `l`, `i` olmadan küçük harf ve rakam; yaklaşık 100 bit rastgelelik), yalnız özetini saklar ve
hesabı "yeni parola bekliyor" durumunda, `DWHNAVIGATOR_ONE_TIME_PASSWORD_TTL_HOURS` (varsayılan 72;
1–168) saat geçerli parolayla açar. Tek kullanımlık parola ve bitiş zamanı yalnız bu yanıtta bir kez
döner; sonradan hiçbir uçla okunamaz. Açılış aynı işlemde değişiklik kaydına yazılır (Requirement 5).

Requirement 3: Parola politikası (rules/58, NIST 800-63-4 yönü) kişinin belirlediği her parolaya
uygulanır: ilk değiştirme, kendi isteğiyle değiştirme, süper yönetici açılışı ve elle komut. Parola
NFKC ile normalleştirildikten sonra Unicode karakter olarak sayılır; en az 15, en çok 128
karakterdir; boşluklar ve Türkçe harfler korunur; büyük harf, rakam veya özel karakter zorunluluğu
yoktur. Şu parolalar 422 `password_policy` ile reddedilir ve ileti nedeni sade dille söyler: 15'ten
kısa (`too_short`) veya 128'den uzun (`too_long`); depoda sürümlenen çevrimdışı yaygın ve ihlal
edilmiş parola listesinde olan ya da tek bir kısa birimin tekrarından oluşan (`aaaa…`, `abcabc…`)
(`common`); kullanıcı adını, görünen addaki 4 ve daha uzun karakterli bir sözcüğü ya da ürün adını
(`dwhnavigator`, `navigator`) içeren (`contains_account_name`); hesabın şimdiki parolasıyla veya tek
kullanımlık parolasıyla aynı olan (`reused`). Liste ve ad karşılaştırması büyük/küçük harf
duyarsızdır ve uygulamanın Türkçe normalleştirme yardımcısıyla yapılır (İ/ı); şimdiki parolayla
aynılık özet doğrulamasıyla birebir denetlenir. Liste hiçbir dış servise sorulmaz (Decision 19).
Arayüz politikayı parola alanının yanında gösterir ("En az 15 karakter; uzun bir cümle
seçebilirsiniz.").

Requirement 4: `POST /auth/password` kullanıcı adı, şimdiki parola (tek kullanımlık parola da
olabilir) ve yeni parolayı alır; oturum gerektirmez, şimdiki parolanın doğruluğu kimliği kanıtlar.
Şimdiki parola Requirement 1'deki gibi denetlenir (aynı hata kodları; pasif hesap 403 `user_inactive`,
süresi dolmuş tek kullanımlık parola 401 `one_time_password_expired`) ve aynı hız sınırı sayaçlarına
girer (Requirement 9). Yeni parola Requirement 3'e uymalıdır. Başarıda tek işlemde yeni parolanın
özeti yazılır, "yeni parola bekliyor" durumu ve tek kullanımlık parolanın bitiş zamanı silinir,
parola değişim zamanı yazılır, kişinin bütün yenileme oturumları kapatılır ve değişiklik kaydına
değer içermeyen bir `password` satırı eklenir; ardından yeni oturum açılır (Requirement 6, 7) ve
yanıt girişle aynıdır. İlk girişteki zorunlu değişiklik ve kişinin kendi isteğiyle değişikliği bu tek
uçla yapılır; süper yönetici kendi parolasını da böyle değiştirir.

Requirement 5: Süper yönetici hesapları sayfalı listeler (`page`, en çok 100 olan `size`; kullanıcı
adına göre sıralı; `q` kullanıcı adında ve görünen adda arar; yanıtta `items`, `page`, `size`,
`total`), süper yönetici dışındaki bir hesabın rolünü `kullanici` ↔ `yonetici` arasında değiştirir,
hesabı pasifleştirir veya yeniden etkinleştirir ve parolasını sıfırlar. Sıfırlama yeni bir tek
kullanımlık parola üretir (Requirement 2'deki gibi; yalnız o yanıtta bir kez döner), eski parolayı
hemen geçersiz kılar ve hesabı "yeni parola bekliyor" durumuna alır. Rol, durum ve parola değişikliği
o hesabın bütün yenileme oturumlarını kapatır (rules/58: yetki değişiminde oturum yenilenir) ve aynı
işlemde PostgreSQL'deki değişiklik kaydı tablosuna yazılır: yapan, hedef hesap, değişen alan
(`account`, `role`, `active`, `password`), eski ve yeni değer (parola satırında değer yoktur, yalnız
`reset` ya da `changed` türü) ve zaman (Decision 10). Pasif hesap doğru parolayla da 403
`user_inactive`, yenileme isteğinde 401 alır. Süper yönetici hesaplarının rolü, durumu ve parolası
bu uçlarla değiştirilemez (409 `super_admin_protected`); hiçbir hesap kendini pasifleştiremez (409).

Requirement 6: Başarılı giriş ve parola değişikliği 15 dakikalık, ES256 ile imzalı erişim belirteci
(JWT: uygulamanın imzaladığı kısa ömürlü oturum belirteci) döndürür. Belirteç kullanıcının
`public_id`'sini, kiracıyı, rolü ve izinleri, süper yönetici bayrağını, `iss`, `aud`, `iat` ve `exp`
değerlerini taşır; parola ve parola durumu taşımaz. Doğrulama yalnız yapılandırılmış algoritmayı
kabul eder; imzasız `none` ve algoritma karışıklığı reddedilir. Tarayıcı erişim belirtecini ve
kullanıcı bilgisini yalnız bellekte tutar; `localStorage` ve `sessionStorage` kullanılmaz.

Requirement 7: Giriş ve parola değişikliği ayrıca yenileme belirteci üretir (tahmin edilemez
rastgele üreteçle, en az 256 bit); PostgreSQL'de yalnız özeti saklanır; belirteç `dwhnavigator_refresh`
adlı, `Secure`, `HttpOnly` ve `SameSite=Strict` çerezde yalnız `/api/dwhnavigator/v1/auth` yolunda
taşınır. `POST /auth/refresh` her kullanımda belirteci yeniler, eskisini geçersiz kılar, rolü ve
hesabın durumunu veritabanından güncel okur; pasif hesap ve yeni parola bekleyen hesap 401 alır.
Boşta kalma süresi 60 dakika, mutlak üst sınır 8 saattir. Kullanılmış belirteç tekrar gelirse o
oturum ailesi (aynı girişten doğan belirteç zinciri) kapatılır ve denetim olayı yazılır. Ön yüz aynı
tarayıcıdaki sekmelerin yenileme isteklerini sekmeler arası tarayıcı kilidiyle (Web Locks) sıraya
koyar; böylece her istek çerezdeki en son belirteçle gider ve birden çok açık sekme tekrar kullanım
sayılmaz. Sayfa yeniden yüklenince ön yüz oturumu bu çerezle sessizce geri getirir. Yenileme
belirteci ve sunucu tarafı oturum kaydı `rules/21`'in kabul edilmiş PRD istediği eklerdir; bu PRD o
kabuldür.

Requirement 8: `POST /auth/logout` yenileme oturumunu sunucuda kapatır, çerezi siler ve 204 döner;
süresi dolmuş erişim belirteciyle de çalışır, çerez yoksa da 204'tür. Çıkıştan sonra aynı yenileme
belirteci 401 alır; ön yüz bellekteki belirteci siler ve giriş ekranına döner.

Requirement 9: Hız sınırı (rules/58): giriş ve parola değiştirme uçlarındaki hatalı denemeler aynı
sayaçlarla sayılır: aynı normalleştirilmiş kullanıcı adı ve istemci adresi için 15 dakikada 5, aynı
istemci adresi için 15 dakikada 30. Sınır aşılınca parola denetlenmeden 429 `rate_limited` ve
`Retry-After` döner; başarılı giriş kullanıcı adı sayacını sıfırlar. Kalıcı hesap kilidi yoktur
(saldırgan başkasının hesabını kilitleyemesin diye); süren denemeler log olayı ve ölçümle izlenir.
İstemci adresi yalnız güvenilen giriş denetleyicisinin pod ağından (`DWHNAVIGATOR_TRUSTED_PROXY_CIDRS`)
gelen `X-Forwarded-For` ile belirlenir; başka kaynaktan gelen başlık yok sayılır. Sayaçlar süreç
içindedir; backend tek kopya çalışır ([kubernetes-delivery](../002-kubernetes-delivery/PRD.md)
Decision 5).

Requirement 10: Yetki eşlemesi. Sağlık, giriş, parola değiştirme, yenileme ve çıkış dışındaki her uç
oturum ister. Kaynakta `AdminGuard` arkasında olan her işlemin hedefteki karşılığı (yönetim
ekranının yedi sayfası: Genel bakış, Analizler, Sözlük, Kelimeler, Yapay zekâ, Arama ve cevap, Bakım
ve onların uçları) `yonetici` ister. Kaynakta kimliksiz olan her işlemin karşılığı ve ondan türeyen
yeni uçlar (soru, analiz işi ve canlı akışı, iptal, toplu arama, oy, sözlük gezgini, durum, rapor)
`kullanici` ister. Hesap yönetimi uçları yalnız süper yöneticiye açıktır; süper yönetici her rol
denetiminden merkezi olarak geçer (`rules/21`). Kişiye ait nesnelere (analiz işi, toplu arama işi ve
onların raporları) erişim backend'de sahiplik denetimiyle yapılır; ayrıntısı ve yöneticinin
başkasının kaydını gördüğü uçlar data-dictionary alanının
[question-analysis](../../../data-dictionary/PRDs/004-question-analysis/PRD.md),
[list-search](../../../data-dictionary/PRDs/005-list-search/PRD.md) ve
[analysis-records](../../../data-dictionary/PRDs/008-analysis-records/PRD.md) PRD'lerindedir. Yönetim
ekranının durum değiştiren uçları ve hesap yönetimi uçları rolü ve hesabın durumunu her istekte
veritabanından güncel okur (Decision 20); diğer uçlar belirteçteki rolü kullanır, rol değişikliği
onlara en geç 15 dakikada yansır. `Authorization: Basic` başlığı hiçbir uçta anlam taşımaz: yalnız
onunla gelen istek 401 alır ve hiçbir yanıt `WWW-Authenticate: Basic` taşımaz (tarayıcı parola
penceresi açılmaz). `VSA_ADMIN_PASSWORD` ve `VSA_ADMIN_PASSWORD_FILE` hiçbir yerde okunmaz.

Requirement 11: Kayıtlarda kimlik: oturum, kayıt tutan servislere kullanıcının `public_id`'sini ve
görünen adını verir; analiz kaydı, oy ve toplu arama işi kişiyi bunlarla tutar (kayıt biçimi
analysis-records, [answer-feedback](../../../data-dictionary/PRDs/006-answer-feedback/PRD.md) ve
list-search PRD'lerinde). İstemci adresi, ters DNS ile bulunan makine adı ve istemcinin gönderdiği
kimlik alanları (kaynaktaki `voter`) kayda kimlik olarak alınmaz; böyle bir alan gelirse yok sayılır.
"Kişi başına son oy" oturumdaki kullanıcıya göre sayılır. Pasifleştirilen hesabın kayıtları ve oyları
yerinde kalır.

Requirement 12: Canlı akışlar ve dosya indirmeleri de oturum ister. Erişim belirteci yalnız bellekte
olduğundan ön yüz SSE akışını `EventSource` yerine `fetch` ile `Authorization` başlığı göndererek
açar (`EventSource` başlık gönderemez). Excel indirmeleri dahil her API isteği de belirteci
`Authorization` başlığında taşır: ön yüz dosyayı ortak API istemcisiyle (istek + blob: tarayıcıda
dosya içeriğini tutan nesne) alıp tarayıcıda kaydeder; belirteç taşımayan düz bağlantı indirmede
kullanılmaz. Rapor ve dışa aktarma uçlarını tanımlayan PRD'ler bu kurala bağlantı verir.
Belirteç adres satırında, sorgu parametresinde veya bağlantıda taşınmaz (rules/58). Sunucu açık bir
SSE akışını, akışı açan belirtecin bitiş zamanında kapatır; ön yüz belirteci sessizce yeniler ve
akışı yeniden açar. Akışın kapanması sunucuda süren işi durdurmaz (iş modeli ve yeniden bağlanma
question-analysis PRD'sindedir). Böylece pasifleştirilen ya da rolü alınan kişinin açık akışı en geç
15 dakikada kapanır.

Requirement 13: Siteler arası istek denetimi (CSRF: başka bir sitenin, tarayıcıyı kullanıcı adına
istek göndermeye kandırması). Backend durum değiştiren her istekte (POST, PUT, PATCH, DELETE),
oturum denetiminden önce: `Sec-Fetch-Site` başlığı varsa yalnız `same-origin` ve `none` kabul edilir;
yoksa ve `Origin` varsa `Origin`, `DWHNAVIGATOR_PUBLIC_ORIGIN` ile birebir aynı olmalıdır (`null`
reddedilir). Aksi 403 `cross_site_request` ("Başka bir siteden gelen istek reddedildi.") döner. İki
başlık da yoksa (tarayıcı olmayan istemci) bu denetim geçilir; korumalı uç yine oturum ister. Kimliği
çerezle kanıtlanan `/auth/refresh` ve `/auth/logout` ayrıca `Origin`'in bulunmasını ve birebir
eşleşmesini ister. Erişim belirteci çerezde değil `Authorization` başlığında taşındığından tarayıcı
onu başka siteden gelen isteğe kendiliğinden eklemez; bu denetim kaynaktaki ek savunmanın
korunmasıdır (Decision 12).

Requirement 14: Güvenlik başlıkları. Backend her yanıta, hatalar, SSE akışları ve Excel indirmeleri
dahil, şu başlıkları ekler: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`X-Permitted-Cross-Domain-Policies: none`, `Referrer-Policy: no-referrer`,
`Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp`,
`Cross-Origin-Resource-Policy: same-origin`,
`Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()`,
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'`,
`Cache-Control: no-store` ve `Strict-Transport-Security: max-age=31536000`. Ön yüz sunucusu
(`app/frontend/nginx.security-headers.conf`) sayfalara ve statik dosyalara aynı başlıkları ekler;
yalnız içerik güvenlik politikası olarak şunu gönderir:
`default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'`.
`'unsafe-inline'`, `'unsafe-eval'` ve dış kaynak yoktur; iskeletin bugünkü `style-src 'unsafe-inline'`
izni kalkar (Decision 13). `index.html` `Cache-Control: no-store` taşır; yalnız adı içerik özetli
statik JS ve CSS dosyaları önbelleğe alınabilir (Decision 14). Tarayıcı HSTS'yi düz HTTP'de yok
sayar, yerel çalışma etkilenmez; kümede giriş denetleyicisi kendi HSTS değerini koyarsa o geçerli
olur. Hiçbir yanıtın `Server` başlığı yazılım sürümü taşımaz: backend `--no-server-header` ile başlar,
ön yüz sunucusu ve yerel vekil `server_tokens off` kullanır. Tarayıcıdaki ana akışlarda (giriş,
parola değiştirme, soru, toplu arama, yönetim ekranı sayfaları) konsolda CSP ihlali görülmez.

Requirement 15: Hata yanıtları. Uygulamanın ürettiği her hata tek zarfla döner:
`{"detail":{"code":"...","message":"..."}}`; ileti Türkçedir ve güvenlidir, yanıt `x-request-id`
başlığını taşır. Beklenmeyen hata 500 `internal_error` ve sabit iletidir ("Sunucu hatası. Ayrıntı
sunucu kaydında."); istisna metni, yığın izi, SQL, dosya yolu, adres ve kütüphane adı yanıta girmez,
yalnız sunucu loguna istek kimliğiyle düşer. Doğrulama hatası (422) alanın yerini ve sabit iletiyi
verir, girilen değeri yankılamaz (parola alanları dahil). Bilinmeyen yol 404 `not_found`, uygun
olmayan yöntem 405 `method_not_allowed`; kiracı başlığı eksik veya geçersizse de aynı zarf kullanılır.
Kaynakta 400 ve 404 yanıtlarında dönen istisna metninin karşılığı yoktur; uçların kullanıcıya anlamlı
iletileri kendi PRD'lerindeki sabit kodlardır.

Requirement 16: Ön yüz:

- Giriş ekranı kullanıcı adı ve parola ister; hata iletisi kullanıcı adının mı parolanın mı yanlış
  olduğunu ayırt etmez; 429'da ne kadar bekleneceğini, `user_inactive`'te "Hesabınız pasif; uygulama
  yöneticisine başvurun.", `one_time_password_expired`'da "Tek kullanımlık parolanızın süresi doldu;
  uygulama yöneticisinden yenisini isteyin." der. Giriş ekranının ana ekranla aynı renk
  belirteçlerini kullanıp kullanmayacağı
  [dictionary-explorer](../../../data-dictionary/PRDs/007-dictionary-explorer/PRD.md) Açık soru 4'e
  bağlıdır.
- `password_change_required` gelince aynı ekranda "Yeni parola belirleyin" adımı açılır: yeni
  parola, tekrarı ve politikanın sade açıklaması; gönderim `POST /auth/password` iledir ve başarıda
  kişi doğrudan uygulamaya girer.
- Ana ekranın ve yönetim ekranının kabuğunda oturumdaki kişinin görünen adı, "Parolamı değiştir"
  (şimdiki, yeni ve yeni tekrar) ve "Çıkış" bulunur; kabukların düzeni data-dictionary alanının
  [dictionary-explorer](../../../data-dictionary/PRDs/007-dictionary-explorer/PRD.md) ve
  [search-settings](../../../data-dictionary/PRDs/009-search-settings/PRD.md) PRD'lerindedir.
- Yönetim ekranı yolları yalnız `yonetici` ve süper yöneticiye görünür; `kullanici` adresi yazarsa
  "Bu sayfa için yetkiniz yok" görür (backend zaten 403 verir).
- Yönetim ekranında yalnız süper yöneticiye görünen **Kullanıcılar** sayfası: arama, sayfalı liste
  (kullanıcı adı, görünen ad, rol, durum, yeni parola bekliyor mu, son giriş), "Kullanıcı ekle"
  (kullanıcı adı, görünen ad, rol), rol değiştirme, pasifleştirme ve etkinleştirme ve "Parolayı
  sıfırla". Açılışta ve sıfırlamada tek kullanımlık parola, kopyalama düğmesi ve bitiş zamanıyla bir
  kez gösterilir; pencere kapanınca bir daha gösterilmez ve ekran bunu önceden söyler.
  Pasifleştirme, rol değiştirme ve sıfırlama onay ister.
- Oturum bittiğinde (yenileme 401) giriş ekranına dönülür. Bütün metinler
  `app/frontend/src/locales/tr.json`'dadır.

Requirement 17: Süper yönetici açılışı (DWH Code Review ile aynı model; Decision 18): Backend her
açılışta `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD` doluysa
`DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME` (`nonprod`'da `admin`) adındaki hesabı arar; bu adla
hiçbir hesap yoksa onu etkin ve `super_admin` rollü açar. Açılış elle komutla (Requirement 18) aynı
kod yolunu kullanır: aynı ad kuralı, aynı parola politikası (Requirement 3) ve aynı parola özeti.
Açılan hesabın başlangıç parolası tek kullanımlık sayılır ve süresizdir: hesap ilk girişte yeni
parola belirler (Açık soru 1). Bu adla bir hesap varsa (etkin, pasif ya da başka rollü olsa da)
hiçbir alanına dokunulmaz; süper yöneticinin sonradan belirlediği parola yeniden dağıtımda korunur.
Parola politikaya uymuyor
veya ad geçersizse hesap açılmaz; backend çalışmaya devam eder ve yalnız neden sınıfını loglar.
Veritabanı veya şema henüz hazır değilse (ilk kurulumda göç sürerken) açılışı bekletmeden arka
planda 2 saniyeden başlayıp en çok 60 saniyeye çıkan aralıkla yeniden dener. Aynı anda iki açılış
denemesi olsa da (ör. backend açılışı ile elle komut) tek hesap açılır (kullanıcı adının benzersizlik
kısıtı). Hesap açıldığında aynı işlemde
değişiklik kaydına `account` satırı yazılır (yapan, açılan hesabın kendisidir; işlemi bir kişi değil
dağıtım yapar). Başlangıç parolası boşsa hiçbir şey yapılmaz ve veritabanına gidilmez.

Requirement 18: Elle komut: `python -m app.scripts.create_super_admin` parolayı yalnız istemden veya
`--password-stdin` ile okur; süreç ortamındaki `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD`'u
kullanmaz (iskeletin bugünkü önceliği kalkar). Hesap adını `--username`'den, yoksa
`DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_USERNAME`'den alır. Hesap yoksa açar; varsa parolasını sıfırlar,
hesabı etkinleştirir ve `super_admin` atamasını geri getirir. Parola politikası (Requirement 3)
uygulanır; değişen her alan değişiklik kaydına yazılır ve hesabın açık yenileme oturumları kapanır.
Parolası bu komutla verilen hesap ilk girişte yeni parola belirler (Açık soru 1). Komut yerelde
`scripts/create-super-admin.sh` ile, kümede işletim ekibinin backend podunda çalıştırmasıyla
kullanılır; süper yönetici parolasını sıfırlamanın uygulamada başka yolu yoktur.

Requirement 19: Telemetri altyapısı: bu PRD'nin ölçümlerini ve izlerini taşıyan ortak OpenTelemetry
(ölçüm ve iz gönderme standardı) altyapısı bu teslimle kurulur; sonraki PRD'lerin sinyalleri aynı
yolu kullanır. Tipli `DWHNAVIGATOR_OTEL_EXPORTER_OTLP_ENDPOINT`, `DWHNAVIGATOR_OTEL_SERVICE_NAME`,
`DWHNAVIGATOR_OTEL_TRACES_SAMPLE_RATIO` ve `DWHNAVIGATOR_OTEL_METRIC_EXPORT_INTERVAL_SECONDS`
ayarları vardır. Adres boşsa hiçbir sinyal dışarı çıkmaz; `OTEL_` ile başlayan süreç değişkeni varsa
backend başlamaz (kütüphanenin kendi ayarıyla başka adrese gönderim olmasın diye); `nonprod`'da adres
yalnız `https` olabilir. Her istek; yöntem, rota şablonu ve yanıt kodu taşıyan bir sunucu iz aralığı
üretir ve istek logu aynı iz kimliğini (`trace_id`) taşır. Yerelde gözlemlenebilirlik Compose katmanı
(`app/infra/docker-compose.observability.yml`) adresi kendi toplayıcısına yöneltir; orada Prometheus
ölçümleri 15 gün, Tempo izleri 14 gün saklar (araçların varsayılanı). `nonprod`'da kümede toplayıcı
yoktur ve adres boştur ([kubernetes-delivery](../002-kubernetes-delivery/PRD.md) Requirement 8).

## API sözleşmesi

Taban yol `/api/dwhnavigator/v1`. Hatalar Requirement 15'teki tek zarfı kullanır; her yanıt
`x-request-id` taşır.

| Uç | Yetki | Başarı | Hatalar |
|---|---|---|---|
| `POST /auth/login` | Herkese açık; aynı köken | 200: `access_token`, `token_type`, `expires_in`, `user`; yenileme çerezi | 401 `invalid_credentials`, 401 `one_time_password_expired`, 403 `user_inactive`, 403 `password_change_required`, 403 `cross_site_request`, 422, 429 `rate_limited` |
| `POST /auth/password` | Şimdiki parola; aynı köken | 200: girişle aynı; yenileme çerezi | 401 `invalid_credentials`, 401 `one_time_password_expired`, 403 `user_inactive`, 403 `cross_site_request`, 422 `password_policy`, 429 `rate_limited` |
| `POST /auth/refresh` | Yenileme çerezi; aynı köken | 200: yeni erişim belirteci; yeni çerez | 401 `session_expired`, 401 `session_revoked`, 403 `cross_site_request` |
| `POST /auth/logout` | Yenileme çerezi; aynı köken | 204; çerez silinir | 403 `cross_site_request` (çerez yoksa da 204) |
| `GET /auth/me` | Oturum | 200: `public_id`, kullanıcı adı, görünen ad, rol, süper yönetici mi | 401 |
| `GET /admin/users?page=&size=&q=` | `super_admin` | 200: `items` (`public_id`, kullanıcı adı, görünen ad, rol, etkin mi, yeni parola bekliyor mu, son giriş, açılış zamanı), `page`, `size`, `total`; kullanıcı adına göre sıralı | 401, 403, 422 |
| `POST /admin/users` | `super_admin` | 201: hesap, `one_time_password`, `one_time_password_expires_at` | 401, 403, 409 `username_taken`, 422 |
| `PUT /admin/users/{public_id}/role` | `super_admin` | 200: `{"role":"kullanici"\|"yonetici"}` | 401, 403, 404, 409 `super_admin_protected`, 422 |
| `PUT /admin/users/{public_id}/active` | `super_admin` | 200: `{"active":true\|false}` | 401, 403, 404, 409 (`super_admin_protected` ya da kendi hesabı), 422 |
| `POST /admin/users/{public_id}/password-reset` | `super_admin` | 200: `one_time_password`, `one_time_password_expires_at` | 401, 403, 404, 409 `super_admin_protected` |

"Aynı köken": Requirement 13'teki `Sec-Fetch-Site` ve `Origin` denetimi. Tekrar ve eşzamanlılık
davranışı (`rules/21`):

- `PUT …/role` ve `PUT …/active` tekrarlandığında aynı sonucu verir; değer zaten istenen değerse
  değişiklik kaydı yazılmaz ve oturumlar kapanmaz. Aynı hesaba eşzamanlı yazmalar satır kilidiyle
  sıraya girer; son yazan kazanır ve her gerçek değişiklik ayrı kayıttır.
- `POST /admin/users` tekrarlanırsa ikinci istek 409 `username_taken` alır; aynı adla eşzamanlı iki
  istekten yalnız biri hesap açar (benzersizlik kısıtı).
- `POST …/password-reset` her çağrıda yeni tek kullanımlık parola üretir ve öncekini geçersiz kılar;
  eşzamanlı iki sıfırlamada son işlenenin parolası geçerlidir.
- `POST /auth/password` tekrarlanırsa ikinci istek, şimdiki parola artık değiştiği için 401 alır;
  aynı hesap için eşzamanlı istekler satır kilidiyle sıraya girer.
- `POST /auth/refresh` aynı belirteçle iki kez gelirse ikincisi tekrar kullanım sayılır
  (Requirement 7); ön yüz bunu sekmeler arası sırayla önler. `POST /auth/logout` her zaman 204'tür.

`specs/openapi/dwhnavigator-api.yaml` ve üretilmiş ön yüz tipleri bu tabloyla aynı değişiklikte
güncellenir.

## Güvenlik ve yetkilendirme

- Parola özeti iskeletin Argon2 özetleyicisidir; bilinmeyen kullanıcı adında da bir özet doğrulaması
  yapılır, böylece yanıt süresi hesabın var olup olmadığını ele vermez.
- Tek kullanımlık parola yalnız hesap açma veya sıfırlama yanıtında bir kez görünür; yanıt
  `Cache-Control: no-store` taşır; ön yüz onu kalıcı depoya yazmaz ve pencere kapanınca bellekten
  siler.
- İmza anahtarı ve yenileme belirteci özetleri yalnız sunucudadır; tarayıcıya, loga ve Git'e girmez.
  Anahtarın kaynağı [kubernetes-delivery](../002-kubernetes-delivery/PRD.md) Requirement 7'dedir.
- `nonprod`'da `admin` (Requirement 17): parolayı proje sahibi seçer ve yalnız Azure gizli değişkeni
  `DWHNAVIGATOR_ADMIN_PASSWORD` ile verir; değer Git'e, değer dosyalarına, komut argümanına, loga,
  telemetriye ve test verisine girmez, kümeye yalnız runtime Secret (kümedeki sır deposu) üzerinden
  ulaşır (kubernetes-delivery Requirement 7). Dağıtım var olan hesabın parolasını değiştirmez.
- Pasifleştirme açık yenileme oturumlarını hemen kapatır; erişim belirteci kullanıcı uçlarında en çok
  15 dakika daha geçerli kalır; yönetim ekranının durum değiştiren uçları durumu her istekte denetler
  (Requirement 10).

Kaynağın güvenlik ölçüleri (`docs/GUVENLIK.md`) ve hedefteki karşılıkları:

| Kaynak ölçüsü | Hedefte | Sahibi |
|---|---|---|
| Bulgu 1: yönetim ekranı parolası; parolasızken yalnız aynı makine; 5 hatalı denemede 5 dakika | Kişiye ait yerel hesap, `yonetici` rolü, hız sınırı; makine istisnası yok | Bu PRD, Requirement 9 ve 10 |
| Bulgu 2: POST'larda `Sec-Fetch-Site`/`Origin` denetimi | Durum değiştiren her istekte aynı denetim; çerez kullanan uçlarda `Origin` zorunlu | Bu PRD, Requirement 13 |
| Bulgu 3: model bağlantı testinin sunucu taraflı istek yüzeyi (SSRF: sunucunun saldırgan adına başka adrese istek atması) yalnız parolayla korunuyordu | Yalnız `yonetici`; yalnız özel ağ adresleri; kümede çıkış yalnız model sunucusuna | Bu PRD Requirement 10; [llm-connection](../../../data-dictionary/PRDs/003-llm-connection/PRD.md); kubernetes-delivery Requirement 10 |
| Bulgu 4: Excel formül enjeksiyonu | Rapora yazılan her metin hücreye metin olarak yazılır | [data-dictionary alanı](../../../data-dictionary/DOMAIN.md) "Excel güvenliği" değişmezi; rapor üreten PRD'ler |
| Bulgu 5: XML saldırıları, sıkıştırma bombası, 20 MB yükleme sınırı | Ortak güvenli Excel okuyucu: güvenli XML ayrıştırıcı, bellekte okuma, 20 MB yükleme ve 100 MB açılmış boyut sınırı; satır/sütun sınırını çağıran verir; kenarda 20 MB | [dictionary-management](../../../data-dictionary/PRDs/001-dictionary-management/PRD.md) (okuyucunun sahibi); [vocabulary-management](../../../data-dictionary/PRDs/002-vocabulary-management/PRD.md) ve list-search kullanır; kubernetes-delivery Requirement 11 |
| Bulgu 6: güvenlik başlıkları ve katı CSP | Backend ve ön yüz sunucusu | Bu PRD, Requirement 14 |
| Bulgu 7: hata yanıtında istisna metni | Tek zarf, genel 500, girilen değer yankılanmaz | Bu PRD, Requirement 15 |
| Bulgu 8: `Server` başlığında sürüm | Sürümsüz `Server` başlığı | Bu PRD, Requirement 14 |
| Bulgu 9: geçersiz `Content-Length`, parçalı gövde, JSON dizisi gövde | Geçersiz uzunluğu sunucu katmanı 400 ile reddeder; parçalı gövde kabul edilir ama boyutu kenarda sınırlanır; yanlış tipte gövde 422 | Bu PRD Requirement 15; kubernetes-delivery Requirement 11 |
| Bulgu 10: yavaş istemci (120 sn okuma sınırı) | Kenar sunucusunun istek okuma süreleri | kubernetes-delivery Requirement 11 |
| Bulgu 11: 4.000 karakterlik soru sınırı | Korunur | question-analysis |
| Bulgu 12: `git` alt süreci | Yok | [quality-evaluation](../../../data-dictionary/PRDs/010-quality-evaluation/PRD.md) |
| Bulgu 13: sayfa kaynağındaki yorumlar | Üretim derlemesi yorumları atar | Ek iş yok |
| Kalan risk 1: TLS ve HSTS ters vekilde | Giriş denetleyicisinde TLS (`ailab-tls`); HSTS backend ve ön yüz sunucusunda da | kubernetes-delivery Requirement 11; bu PRD Requirement 14 |
| Kalan risk 2: son kullanıcı kimliği yok | Herkes yerel hesapla girer | Bu PRD |
| Kalan risk 3: ağ çıkışı uygulamada sınırlı değil | Varsayılanı kapalı çıkış kuralı | kubernetes-delivery Requirement 10 |
| Kalan risk 4: model ucu HTTP ise API anahtarı açık gider | Model bağlantısının TLS kuralları | llm-connection |
| Kalan risk 5: veri biriminde API anahtarı, soru metni, istemci adresi | PostgreSQL; anahtar şifreli; adres yazılmaz | llm-connection, analysis-records; bu PRD Requirement 11 |
| Kalan risk 6: kişisel veri | Uygulama yalnız sözlük metniyle çalışır | data-dictionary alanı |
| Kalan risk 7: taban imaj takibi | İmaj taraması | kubernetes-delivery Requirement 14 |
| Konteyner sertleştirmesi | Chart ve release imajları | kubernetes-delivery Requirement 2 |

## Veri ve geçiş

- `app_user`: kullanıcı adı benzersiz ve normalleştirilmiş; görünen ad; e-posta boş olabilir (hesap
  açılışında istenmez; doluysa benzersizdir) ve girişte kullanılmaz; "yeni parola bekliyor" bayrağı;
  tek kullanımlık parolanın bitiş zamanı (boş olabilir: açılışta ve elle komutta süresizdir); parola
  değişim zamanı; son giriş zamanı. Parola özeti bütün hesaplarda zorunlu kalır.
- Yeni yenileme oturumu tablosu: kullanıcı, oturum ailesi, belirteç özeti, son kullanım, mutlak
  bitiş, kapanma zamanı ve nedeni. Zorunlu sütun bloğunu (rules/41) taşır; süresi dolan satır 7 gün
  sonra kalıcı silinir. Bu, belirteç özetinin gereğinden uzun saklanmaması için rules/41'in
  yazılımsal silme kuralından bilinçli sapmadır.
- Yeni değişiklik kaydı tablosu (Requirement 5): yalnız eklenen bir akıştır (rules/41); yazılımsal
  silme sütunu yoktur, uygulamada güncelleme ve silme yolu yoktur; parola satırları değer taşımaz.
- Alembic göçü (şema değişikliği aracı) `kullanici` ve `yonetici` rollerini, izinlerini ve `platform`
  kiracısını tohumlar; böylece süper yönetici açılışı ve hesap açma kiracı oluşturmadan çalışır.
- Çevrimdışı yaygın ve ihlal edilmiş parola listesi backend paketinde sürümlenen bir veri dosyasıdır
  (Decision 19).
- Kaynakta taşınacak kullanıcı yoktur (kaynağın kullanıcı kavramı yoktu); `VSA_ADMIN_PASSWORD`
  taşınmaz. Kaynak `data/` dosyalarından veri taşıma olmadığı için analiz kayıtlarındaki adres ve
  makine adları ile oylardaki `vsa-voter` kimlikleri de taşınmaz.

## Gözlemlenebilirlik

Her olay yapılandırılmış JSON log satırıdır ve istek kimliği (`x-request-id`) taşır. Parola, tek
kullanımlık parola, erişim belirteci, çerez, yenileme belirteci ve parola özeti asla yazılmaz.
Kullanıcı adı loga girmez; başarısız denemede onun yerine anahtarlı özeti (anahtarı sunucuda duran,
geri çevrilemez parmak izi) yazılır.

| Olay | Alanlar |
|---|---|
| `auth.login.succeeded` | kullanıcı `public_id` |
| `auth.login.failed` | neden sınıfı (`invalid_credentials`, `user_inactive`, `one_time_password_expired`), ad özeti |
| `auth.login.password_change_required` | kullanıcı `public_id` |
| `auth.login.rate_limited` | ad özeti, sınır türü (`user`, `address`) |
| `auth.password.changed` | kullanıcı `public_id`, tür (`initial`, `voluntary`) |
| `auth.password.change_failed` | neden sınıfı (`invalid_credentials`, `user_inactive`, `one_time_password_expired`, `password_policy`), politika nedeni, ad özeti |
| `auth.session.reuse_detected` | kullanıcı `public_id`, oturum ailesi |
| `auth.logout` | kullanıcı `public_id` |
| `admin.user.created` | yapan, hedef `public_id`, rol |
| `admin.user.role_changed` / `admin.user.active_changed` | yapan, hedef, eski ve yeni değer |
| `admin.user.password_reset` | yapan, hedef |
| `auth.super_admin.bootstrap` | sonuç (`created`, `exists`, `rejected`, `not_configured`); `created` ve `exists`'te hesap `public_id`'si ve hesabın `super_admin` olup olmadığı; `rejected`'te neden (`password_policy`, `invalid_username`) |
| `auth.super_admin.bootstrap_retry` | deneme sırası, hata türü (yalnız sınıf adı), sonraki denemeye kalan saniye |
| `security.cross_site_rejected` | yöntem, rota şablonu, kararı veren başlık (`sec_fetch_site`, `origin`) |

Ölçümler: `dwhnavigator_auth_login_attempts_total{outcome}`; `outcome` `succeeded`,
`invalid_credentials`, `user_inactive`, `one_time_password_expired`, `password_change_required` veya
`rate_limited`'dır. `dwhnavigator_auth_password_change_attempts_total{outcome}`; `outcome`
`succeeded`, `invalid_credentials`, `user_inactive`, `one_time_password_expired`, `password_policy`
veya `rate_limited`'dır. Kümede olmayan değer `other` yazılır; kullanıcı adı, ad özeti, hesap kimliği
ve adres ölçüme girmez. İz aralıkları ve saklama süreleri Requirement 19'dadır; ortak telemetri
kuralları [alan belgesindedir](../../DOMAIN.md). Tüketen test:
`app/backend/tests/integration/test_telemetry_signals.py`. Rol, durum, hesap açma ve parola
olaylarının geçmişi ayrıca değişiklik kaydı tablosunda kalıcı saklanır (Decision 10).

## Dağıtım etkisi

- Yeni `DWHNAVIGATOR_` önekli ayarlar: `PUBLIC_ORIGIN`, `TRUSTED_PROXY_CIDRS`,
  `ACCESS_TOKEN_EXPIRE_MINUTES` (15), `REFRESH_SESSION_IDLE_MINUTES` (60),
  `REFRESH_SESSION_ABSOLUTE_HOURS` (8), `ONE_TIME_PASSWORD_TTL_HOURS` (72), süper yönetici hesap adı
  ve e-postası ile Requirement 19'daki telemetri ayarları. Hiçbiri sır değildir; `nonprod` değerlerinin
  `values-project.yaml`'a yazılması kubernetes-delivery Requirement 8'dedir.
- Süper yönetici başlangıç parolası runtime Secret'ın `DWHNAVIGATOR_BOOTSTRAP_SUPER_ADMIN_PASSWORD`
  anahtarındadır; kaynağı kubernetes-delivery Requirement 7'dedir.
- Release backend imajı uvicorn'u `--no-server-header` ile başlatır; ön yüz sunucusunun ve yerel
  vekilin yapılandırması Requirement 14 başlıklarını ve `server_tokens off`'u taşır.
- `app/backend/.env.example` ve yerel Compose ortam bloğu yeni ayarlarla güncellenir;
  `python3 scripts/check-config-sync.py` geçer.
- OpenTelemetry paketleri ve parola listesinin kaynağı bağımlılık kabul kaydına
  (`dependency-admission.json`) alınır.
- Kaldırılanlar: `VSA_ADMIN_PASSWORD`, `VSA_ADMIN_PASSWORD_FILE` ve parolasız "yalnız aynı makine"
  kipi.

## Test stratejisi

- Birim: kullanıcı adı ve parola normalleştirme (NFKC; parola kırpılmaz), tek kullanımlık parola
  üretimi (alfabe, uzunluk, CSPRNG kaynağı), politika matrisi (her neden; 15 ve 128 sınırı; boşluk ve
  Türkçe harfin korunması; görünen adda `İ`/`ı` geçen sözcüklerin yakalanması; şimdiki parolayla
  aynılık), erişim belirteci algoritma listesi ve `none` reddi, yenileme dönüşümü ve tekrar kullanım
  tespiti, giriş ve parola değiştirmenin ortak sayaçları, `X-Forwarded-For` güven kuralı.
- API, gerçek PostgreSQL'de: hesap açma, sıfırlama, rol ve durum akışları; tek kullanımlık parolanın
  yalnız açılış yanıtında görünmesi; süresi dolmuş parola; zorunlu değişiklikten önce hiçbir korumalı
  uca erişilememesi; rol, durum, sıfırlama ve parola değişikliğinde oturumların kapanması ve
  değişiklik kaydı satırları (parola değeri olmadan); süper yönetici koruması ve kendini
  pasifleştirme reddi; pasif hesap 403; `Authorization: Basic` ile 401; gönderilen `voter` alanının yok
  sayılması; tekrar ve eşzamanlılık (aynı hesaba paralel rol yazmaları; aynı adla paralel iki hesap
  açmadan biri 201, diğeri 409); siteler arası istek matrisi (`Sec-Fetch-Site` değerleri; `Origin`
  yok, `null`, yabancı, eşit; çerezli uçlarda `Origin` yokken ret); 200, 401, 403, 404, 422, 429 ve
  500 yanıtlarında, SSE akışında ve Excel indirmesinde Requirement 14 başlıkları; hata zarfında
  istisna metni ve girilen değerin bulunmaması.
- Süper yönetici açılışı (Requirement 17) ve elle komut (Requirement 18), gerçek PostgreSQL'de: hesabın
  bir kez açılıp ilk girişte yeni parola istemesi ve tek değişiklik kaydı; var olan hesaba
  dokunulmaması; zayıf parolada hesap açılmaması ve parolanın loga düşmemesi; eşzamanlı açılışta tek
  hesap; veritabanına ulaşılamazken artan aralıkla yeniden deneme; ayar boşken veritabanına hiç
  gidilmemesi; elle komutun süreç ortamındaki başlangıç parolasını kullanmaması.
- Sızıntı: ayırt edici bir işaret parola ve üretilen tek kullanımlık parola; log çıktısında,
  veritabanında (özet dışında), API yanıtlarında (açılış ve sıfırlama yanıtı dışında) ve telemetride
  aranır ve bulunmaz.
- Telemetri: `app/backend/tests/integration/test_telemetry_signals.py` ölçüm adlarını, etiket
  değerlerini, kullanıcı adının ve parolanın hiçbir sinyalde bulunmamasını, `OTEL_` değişkeninde
  başlangıç reddini ve boş adreste dışa aktarım olmamasını sınar.
- Ön yüz (Vitest): belirtecin kalıcı depoya yazılmaması, sessiz yenileme, sekmeler arası sıra (Web
  Locks taklidiyle), zorunlu yeni parola adımı, Kullanıcılar sayfasında tek kullanımlık parolanın bir
  kez gösterilmesi, role göre yollar. Yapılandırma testi: ön yüz sunucusunun CSP metni birebir ve
  `server_tokens off`.
- Tarayıcı senaryosu: hesap aç → tek kullanımlık parolayla gir → yeni parola belirle → uygulamayı kullan
  → çık; ana akışlarda konsolda CSP ihlali olmaması.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: backend, ön yüz ve göç kapıları; gerçek
  PostgreSQL'de Requirement 1–13 ve 15 API ve birim testleri, Requirement 14 başlık ve ön yüz sunucusu
  yapılandırma testleri, Requirement 16 Vitest testleri, Requirement 17–18 süper yönetici testleri ve
  Requirement 19 telemetri testi geçer; işaret parola ve tek kullanımlık parola log, veritabanı (özet
  dışında), API yanıtı (açılış ve sıfırlama yanıtı dışında) ve telemetride bulunmaz.
- [ ] Acceptance 2: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da tarayıcıyla süper
  yönetici bir `kullanici` ve bir `yonetici` hesabı açar; iki hesap tek kullanımlık parolayla girer,
  yeni parola belirlemeden ilerleyemez, yeni parolayla girer; 15 dakikalık belirteç sessizce yenilenir
  ve iki sekme açıkken oturum düşmez; çıkış çalışır; `kullanici` yönetim ekranına giremez (sayfa ve API
  403); süper yönetici rolü değiştirir, parolayı sıfırlar ve hesabı pasifleştirir, değişiklik hemen
  yansır; sayfa ve API yanıtlarında Requirement 14 başlıkları görülür, konsolda CSP ihlali yoktur;
  başka kökenden gönderilen POST 403 alır (Requirement 2–5, 7, 8, 10, 13, 14, 16).
- [ ] Acceptance 3: L2 — Nonprod kümede doğrulandı (yerel kanıttan ayrı raporlanır):
  `DWHNAVIGATOR_ADMIN_PASSWORD` tanımlıyken ilk dağıtımdan sonra `admin` girer ve logda
  `auth.super_admin.bootstrap` olayı `created`, sonraki dağıtımda `exists` görünür ve parola değişmez;
  `admin` bir hesap açar ve o hesap tarayıcıdan girer; yanlış parolada 401, altıncı hatalı denemede 429
  ve denetim olayları logda görünür; yanıtlarda HSTS ve sürümsüz `Server` başlığı vardır
  (Requirement 1, 2, 9, 14, 17).

## Kararlar

- Decision 7: Yerel hesap modeli (proje sahibinin 2026-10-08 kararı). Kimlik doğrulama teknoloji
  profilinin kayıtlı modelidir (`technology-profile.yml` `security.authentication: jwt-access-token`,
  `authorization: rbac-with-application-super-admin`; `rules/21` taban yüzeyi); dış kimlik sağlayıcı
  ve dizin bağlantısı yoktur, yeni bir kimlik sistemi kurulmaz. Bu PRD taban modele yalnız yenileme
  belirtecini, sunucu tarafı oturum kaydını, hesap yönetimini ve parola akışlarını ekler.
- Decision 8: Tek kullanımlık parolayı uygulama üretir, süper yönetici yazmaz (rules/58: sıfırlama
  kanıtı CSPRNG ile üretilir, tek kullanımlık ve kısa ömürlüdür). Varsayılan geçerlilik 72 saattir:
  süper yönetici parolayı ayrı bir kanaldan iletir ve kişinin aynı gün girmemesi olağandır; süre
  `DWHNAVIGATOR_ONE_TIME_PASSWORD_TTL_HOURS` ile 1–168 saat arasında değişir. Süresi dolan parolayla
  giriş yapılamaz; süper yönetici yenisini üretir.
- Decision 9: Süper yönetici her rol denetiminden geçer; ilk kurulumda henüz `yonetici` yokken sözlüğü
  içe aktarır, model bağlantısını ekler ve hesapları açar.
- Decision 10: Rol, durum, hesap açma ve parola olaylarının geçmişi PostgreSQL'deki küçük bir
  değişiklik kaydı tablosunda tutulur (Requirement 5); `nonprod`'da log saklama süresi güvenceli
  değildir.
- Decision 11: Oturum süreleri: erişim belirteci 15 dakika, yenileme oturumunda boşta kalma 60 dakika,
  mutlak üst sınır 8 saat. Bir analiz veya toplu arama işi oturumdan uzun sürebilir; iş sunucuda
  sürer ve kişi yeniden girince sonucunu görür (question-analysis, list-search).
- Decision 12: Erişim belirteci yalnız bellekte ve `Authorization` başlığında taşınır; çerez yalnız
  `/auth` yolundaki yenileme içindir. Böylece siteler arası istek riski çerezi okuyan veya yazan dört
  uçla (giriş, parola değiştirme, yenileme, çıkış) sınırlıdır; kaynaktaki `Sec-Fetch-Site`/`Origin`
  denetimi yine bütün durum değiştiren isteklerde ek savunma olarak kalır (Requirement 13).
- Decision 13: Sayfa CSP'si kaynak kadar katıdır: `style-src`'de `'unsafe-inline'` yoktur. React'in
  eleman stilleri tarayıcının stil nesnesiyle (CSSOM) verildiği için engellenmez; çalışırken `<style>`
  öğesi ekleyen arayüz bileşenleri kullanılmaz.
- Decision 14: Kaynak her yanıtta `Cache-Control: no-store` gönderiyordu (cevaplar ve raporlar
  önbelleğe girmesin diye). Hedefte API yanıtları ve `index.html` aynı kalır; yalnız adı içerik özetli
  statik JS ve CSS dosyaları önbelleğe alınabilir, çünkü veri taşımazlar.
- Decision 15: Ortak telemetri altyapısı bu PRD'yle kurulur (Requirement 19): uygulama temelinin ilk
  teslimi budur ve kendi ölçümleri ona dayanır; DWH Code Review'da da aynı yerde kuruldu.
- Decision 16: Kendi kendine parola sıfırlama yoktur: kapalı ağda e-posta veya SMS kanalı kullanılmaz;
  parolasını unutan kişi süper yöneticiden sıfırlama ister.
- Decision 17: Kullanıcı adı `a-z`, `0-9`, `.`, `_` ve `-` ile 3–64 karakterdir (ör. `ad.soyad`);
  Türkçe harf içermez, böylece küçük harfe çevirme İ/ı sorununa girmez. Görünen ad Türkçe harfli
  serbest metindir.
- Decision 18: `nonprod`'da `admin` süper yöneticisi DWH Code Review'daki gibi dağıtımdan sonra
  kendiliğinden açılır (proje sahibinin 2026-10-08 kararı; Requirement 17). rules/58'in yönetici
  hesabı oluşturmanın otomatikleşmesi için istediği eylem bazlı insan onayı bu karar ve PRD'nin
  kabulüdür. Açılış her ortamda yalnız başlangıç parolası verilince çalışır.
- Decision 19: Yaygın ve ihlal edilmiş parola listesi çevrimdışıdır: iskeletin taban listesi ile
  kamuya açık, lisansı uygun bir yaygın parola derlemesinin 15 ve daha uzun karakterli girdilerinden
  oluşur ve backend paketinde sürümlenir; derlemenin kaynağı, lisansı ve sürümü planda seçilir ve
  bağımlılık kabul kaydına yazılır. Çevrimiçi ihlal sorgusu kapalı ağ nedeniyle kullanılmaz.
- Decision 20: Yönetim ekranının durum değiştiren uçları ve hesap yönetimi uçları rolü ve hesap
  durumunu her istekte veritabanından okur (`rules/21`: güncel yetki gereken uç iddiaları yeniden
  okur). Sözlük içe aktarma, model bağlantısı değiştirme ve kayıt silme gibi işlemler, rolü alınmış
  veya pasifleştirilmiş kişiye 15 dakika açık kalmaz.

## Açık sorular

1. Süper yönetici ilk girişte parolasını değiştirmek zorunda olsun mu? Açılışta Azure gizli
   değişkeninden ya da elle komutla verilen süper yönetici parolası Azure'da ve kümedeki runtime
   Secret'ta düz durur; DWH Code Review'da değişiklik zorunlu değildi, bu yüzden Secret'ı okuyabilen
   herkes `admin` olarak girebiliyordu. Öneri: Evet; hesap DWH'deki gibi bir kez açılır, yalnız ilk
   girişte (süre sınırı olmadan) yeni parola istenir; böylece Azure'daki ve kümedeki kopya ilk
   girişten sonra işe yaramaz (Requirement 17 ve 18 bu öneriyle yazıldı).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- Tek kullanımlık parola süper yöneticiden kişiye ayrı bir kanalla (ör. kurum içi mesaj) gider; kanal
  ele geçirilirse parola süresi dolana kadar kullanılabilir. Kişi ilk girişte parolayı değiştirince
  risk biter; parola başkası tarafından kullanılmışsa kişi giremez ve süper yöneticiye bildirir.
- Hız sınırı sayaçları süreç içindedir: süreç yeniden başlayınca (her güncellemede) sıfırlanır.
- Kalıcı kilit olmadığı için yavaş ve dağıtık parola denemesi yalnız hız sınırıyla yavaşlar; 15
  karakter alt sınırı ve liste reddi riski düşürür, süren denemeler log ve ölçümle izlenir.
- Süper yönetici parolası kaybolursa hesap yönetimi durur; sıfırlama işletim ekibinin küme erişimine
  bağlıdır.
- Açık soru 1 kabul edilmezse Azure'daki ve runtime Secret'taki başlangıç parolasını okuyabilen kişi
  `admin` olarak girebilir.
- Azure gizli değişkeni dağıtım adımının ortamına eşlenmezse `admin` açılmaz (DWH Code Review'da
  yaşandı); o durumda süper yönetici elle komutla açılır (Requirement 18).
- Katı CSP, çalışırken `<style>` ekleyen bir arayüz kütüphanesini bozar; ihlal tarayıcı konsolunda
  görünür ve Acceptance 2'de yakalanır.
- Sunucu katmanının bozuk HTTP isteğine verdiği kısa 400 yanıtı uygulamaya ulaşmadığı için güvenlik
  başlıklarını taşımaz; kümede böyle istekler giriş denetleyicisinde durur.
- Kaynağı bugün kimliksiz kullanan herkes için hesap açılması gerekir; geçişte süper yöneticinin iş
  yükü artar ve hesabı olmayan kişi uygulamayı kullanamaz.
