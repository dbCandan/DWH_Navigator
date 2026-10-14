# PRD — anonymous-visitor

Status: Accepted

Version: 0.1.0

Acceptance date: 2026-10-14

Domain: [application-foundation](../../DOMAIN.md)

Roadmap: [003 anonymous-visitor](../../roadmap.md)

Kabul kaydı: Proje sahibi 2026-10-14'te ana ekranın kaynak uygulamadaki gibi
giriş istemeden kullanılmasını, kişiye özgü işlemlerde kişinin IP adresi ve cihaz bilgisiyle
tanınmasını ve parolanın yalnız yönetim ekranında sorulmasını istedi.

## Amaç

Ana ekranı (soru, Evren haritası, toplu arama, oy, rapor) giriş istemeden açmak; parolayı yalnız
yönetim ekranında sormak. Kaynak uygulamada ana ekran kimlik sormuyordu, yönetim ekranı ise parolayla
korunuyordu; hedef bu ayrımı geri getirir. Yönetim ekranının girişi, rolleri ve hesap yönetimi
[user-accounts](../001-user-accounts/PRD.md) PRD'sinde kalır.

Girişsiz kişiye **ziyaretçi** denir. Ziyaretçinin analizi, listesi ve oyu ona bağlı kalmalıdır;
bunun için ziyaretçi parola yerine tarayıcısının taşıdığı rastgele bir **cihaz kimliği** ve isteğin
geldiği **IP adresi** ile tanınır (Decision 1, 2).

## Aktörler ve sonuçlar

- **Ziyaretçi:** Giriş yapmadan ana ekranı açar; soru sorar, analizini durdurur, raporunu indirir,
  haritada gezer, toplu arama listesi yükler, oy verir. Kendi analizini, listesini ve oyunu görür;
  başkasınınkini görmez.
- **Yönetici (`yonetici`) ve uygulama yöneticisi (süper yönetici):** Yönetim ekranına
  [user-accounts](../001-user-accounts/PRD.md) hesabıyla girer. Analiz kayıtlarında soruyu soran
  ziyaretçiyi IP adresi ve makine adıyla görür.
- **Kullanıcı (`kullanici`) hesabı:** Ana ekran için gerekmez (Decision 6).

Ölçülebilir sonuç: oturumu olmayan tarayıcı `/` adresinde giriş ekranına yönlenmeden ana ekranı
açar, soru sorar ve cevabı alır; aynı tarayıcıdan verilen oy ve yüklenen liste o tarayıcıda görünür,
başka cihaz kimliğiyle `404` alınır; `/admin` oturumsuz giriş ekranına yönlenir; yönetim API'si
oturumsuz `401` döner.

## Değişmezler ve sınırlar

- Decision 1: Ziyaretçinin kimliği tarayıcının ürettiği cihaz kimliğidir: tarayıcının tahmin
  edilemez rastgele üreteciyle (`crypto.randomUUID`) bir kez üretilen, tarayıcının kalıcı belleğinde
  (`localStorage`) duran UUID 4. Her ana ekran isteğinde `X-Device-Id` başlığıyla gider. Cihaz
  kimliği parola değildir; yalnız ziyaretçinin kendi işlerini başkalarınınkinden ayırır.
- Decision 2: İsteğin IP adresi backend'de user-accounts Requirement 9'daki güvenilen ağ geçidi
  kuralıyla (`X-Forwarded-For` yalnız güvenilen ağdan) çözülür. IP adresi kimliğin anahtarı değildir;
  hız sınırında ve analiz kaydının "Soran" bilgisinde kullanılır. Makine adı, IP adresinden backend'in
  yaptığı ters DNS sorgusuyla (kaynaktaki gibi) bulunur; bulunamazsa boş kalır. Tarayıcı makine adını
  bilemez ve göndermez.
- Decision 3: Ana ekran uçları (Requirement 3) oturum istemez; oturum belirteci gelse bile ana ekran
  uçlarında kimlik cihaz kimliğidir. Yönetim uçları ve hesap uçları user-accounts PRD'sindeki gibi
  oturum ve rol ister.
- Decision 4: Ziyaretçi tek `platform` kiracısındadır; oturumsuz istekte kiracıyı backend belirler.
  İstemcinin gönderdiği kiracı başlığı varsa `platform` olmak zorundadır.
- Decision 5: Ziyaretçi backend'de ayrı bir `visitor` kaydıdır; hesap (`app_user`) değildir ve
  kullanıcı yönetimi sayfasında görünmez. Analiz kaydı, liste ve oy ya bir hesaba ya bir ziyaretçiye
  bağlanır; ikisine birden ya da hiçbirine bağlanamaz.
- Decision 6: `kullanici` rolü yerinde kalır; mevcut hesaplar silinmez ve yönetim ekranına giremez.
  Ana ekranda oturum alanı (ad, "Parolamı değiştir", "Çıkış") gösterilmez; kaynakta da yoktu.

## Mevcut davranış

- **Kaynak** (`src/vsa/web/server.py`, `security.py`, `static/index.html`): `/`, `/api/ask`,
  `/api/ask/cancel`, `/api/list…`, `/api/report/<id>`, `/api/objects`, `/api/object/<key>`,
  `/api/galaxy`, `/api/feedback`, `/api/status` kimliksizdir. Yönetim yolları (`/admin`,
  `/api/admin/…`, `/api/settings`, `/api/reindex`, `/api/llm…`) paylaşılan parolayla korunur. Analiz
  kaydı soranın IP adresini ve ters DNS ile bulunan makine adını taşır. Oy veren tarayıcının
  `localStorage`'daki `vsa-voter` rastgele kimliğidir; yoksa IP adresidir. Analizi, onu başlatan
  istemcinin ürettiği `ask_id`'yi bilen herkes durdurabilir; listelerin sahibi yoktur. Ana ekranda hız
  sınırı yoktur.
- **Hedefin bugünkü hâli:** [user-accounts](../001-user-accounts/PRD.md) Decision 3 ve Requirement 10
  gereği ana ekran dahil her uç oturum ve `kullanici` rolü ister; `/` oturumsuz giriş ekranına
  yönlenir. **Hedefte:** ana ekran oturumsuz açılır; sahiplik, oy ve hız sınırı ziyaretçiye göre
  işler; kaynaktan farklı olarak analiz ve liste yalnız sahibine açıktır (Requirement 5).

## İşlevsel gereksinimler

Requirement 1: `/` adresi oturum olmadan ana ekranı açar; giriş ekranına yönlenmez. `/admin` ve
altındaki sayfalar oturumsuz giriş ekranına yönlenir; girişten sonra kişi geldiği yönetim sayfasına
döner. Ana ekranda yönetim ekranına bağlantı yoktur (kaynakla aynı).

Requirement 2: Tarayıcıda cihaz kimliği yoksa ana ekran ilk açılışta Decision 1'deki gibi üretir ve
saklar. Kalıcı bellek kapalıysa kimlik yalnız o sayfa yaşamı boyunca bellekte durur. Ana ekranın
paylaşılan istemcisi her istekte `X-Device-Id` başlığını gönderir; ana ekran isteğine oturum
belirteci eklemez.

Requirement 3: Şu uçlar oturum istemez, geçerli bir `X-Device-Id` ister:
[question-analysis](../../../data-dictionary/PRDs/004-question-analysis/PRD.md) iş uçları (`POST
/analyses`, `GET /analyses/active`, `GET /analyses/{id}`, olay akışı, durdurma, rapor) ve `GET
/status`;
[list-search](../../../data-dictionary/PRDs/005-list-search/PRD.md) uçları;
[answer-feedback](../../../data-dictionary/PRDs/006-answer-feedback/PRD.md) oy ucu;
[dictionary-explorer](../../../data-dictionary/PRDs/007-dictionary-explorer/PRD.md) uçları.
`GET /analyses/active` ziyaretçinin en son başlattığı sıradaki ya da yürüyen işi döndürür. Başlık yoksa
ya da UUID 4 değilse yanıt `400 device_id_required` olur; yönetim ve hesap uçlarının yetkisi
değişmez.

Requirement 4: Backend ilk gördüğü cihaz kimliği için `visitor` kaydı açar; sonraki isteklerde son
görülme zamanını, son IP adresini ve son makine adını günceller. Aynı anda gelen iki ilk istek tek
kayıt üretir.

Requirement 5: Sahiplik ziyaretçiye göredir: analiz işi, olay akışı, durdurma ve rapor yalnız işi
başlatan cihaz kimliğine; liste ve terimleri yalnız listeyi yükleyen cihaz kimliğine açıktır.
Başkasının işi ve listesi `404` döner; var olduğu söylenmez. Oyun "kişi başına son oy" kuralı ve
"benim oyum" gösterimi ziyaretçiye göredir.

Requirement 6: Hız sınırları: soru başlatma ziyaretçi başına 60 saniyede 30 (question-analysis
Requirement 23) ve IP adresi başına 60 saniyede 120; oy ziyaretçi başına 60 saniyede 30 ve IP adresi
başına 60 saniyede 120; yeni ziyaretçi kaydı IP adresi başına 60 saniyede 20. Aşımda `429
rate_limited` ve `Retry-After` döner. Açık olay akışı ziyaretçi başına en çok 5'tir. Sayaçlar süreç
belleğindedir ve sınırlı sayıda anahtar tutar.

Requirement 7: Analiz kaydı, liste ve oy kaydı ziyaretçiye bağlandığında kayıt anındaki IP adresini
ve makine adını da taşır. Yönetim ekranının analiz kayıtları sayfasında "Soran" ziyaretçi için
"<makine adı> · <IP adresi>" (makine adı yoksa yalnız IP adresi), hesap için görünen addır; "Soran"
süzgeci ziyaretçileri de listeler.

Requirement 8: Ana ekranda oturum alanı gösterilmez. Yönetim ekranındaki oturum alanı ve yönetim
ekranından çıkış değişmez.

## API sözleşmesi

| Uç | Yetki | Değişiklik |
|---|---|---|
| Requirement 3'teki ana ekran uçları | `X-Device-Id` (oturum yok) | Bearer ve kiracı başlığı istenmez; yanıtlar değişmez |
| Yönetim ve hesap uçları | user-accounts'taki gibi | Değişmez |

Yeni hata kodu: `400 device_id_required` ("Tarayıcı kimliği eksik; sayfayı yenileyin."). `OpenAPI`
belgesi ana ekran uçlarında `X-Device-Id` başlık parametresini taşır; ön yüz tipleri yeniden üretilir.

## Güvenlik ve yetkilendirme

- Ana ekran uçları herkese açıktır; yetki sınırı yönetim ekranıdır. Uygulamanın ağ erişimi
  (iç ağ, giriş kapısı) bu sınırın parçasıdır.
- Cihaz kimliği bir kimlik bilgisi değildir: bilen biri o ziyaretçinin analizini, listesini ve oyunu
  görebilir. Kimlik URL'de taşınmaz, loglara ve telemetriye yazılmaz; yanıtlarda dönmez.
- Durum değiştiren istekler user-accounts Requirement 13'teki siteler arası istek denetiminden geçer.
  Cihaz kimliği çerezde değil başlıkta gittiği için başka sitenin sayfası onu ekleyemez.
- Oy, saklı cevabı silebildiği için (answer-feedback) ziyaretçi ve IP hız sınırı (Requirement 6)
  kötüye kullanımı sınırlar; tam önlemez (Riskler).
- Ziyaretçiye `super_admin`, rol ya da izin verilmez; yönetim uçları cihaz kimliğini dikkate almaz.

## Veri ve geçiş

- Yeni `visitor` tablosu: iç kimlik, `public_id` (cihaz kimliği değil, ayrı rastgele kimlik),
  cihaz kimliğinin SHA-256 özeti (benzersiz; cihaz kimliği düz saklanmaz), `tenant_id`, ilk ve son
  görülme zamanı, son IP adresi, son makine adı ve zorunlu yaşam döngüsü/denetim sütunları.
- `analysis_record.asked_by`, `answer_vote.voter_id`, `term_list.owner_id` boş olabilir olur; her
  tabloya `visitor` tablosuna dış anahtarlı, boş olabilir ziyaretçi sütunu ile kayıt anındaki IP
  adresi ve makine adı sütunları eklenir. Kısıt: hesap ve ziyaretçi sütunundan tam biri doludur.
  Sahiplik dizinleri ziyaretçi sütununu da kapsar.
- Göç ekleyicidir; mevcut satırlar hesaba bağlı kalır. Okuma yolları hesap ve ziyaretçi için dış
  birleştirme kullanır.
- IP adresi ve makine adı kişisel veridir; analiz kaydı, liste ve oyla aynı süre saklanır ve
  onlarla birlikte silinir.

## Gözlemlenebilirlik

Yeni olaylar: `visitor.created` (yalnız ziyaretçinin `public_id`'si), `rate_limited` olaylarında
sınırın türü (`visitor`, `address`). Cihaz kimliği, IP adresi ve makine adı hiçbir loga, ölçüme ve
ize girmez.

## Dağıtım etkisi

Yeni ayar yoktur; IP adresi user-accounts'taki güvenilen ağ ayarıyla çözülür. Ters DNS küme içi ad
çözümünü kullanır; kümede çözüm yoksa makine adı boş kalır (N/A — yeni çıkış kuralı gerekmez). Göç
mevcut `Job` ile uygulanır.

## Test stratejisi

- Backend tümleştirme: oturumsuz ana ekran uçları `X-Device-Id` ile çalışır, başlıksız `400`;
  başka cihaz kimliğiyle iş, akış, durdurma, rapor ve liste `404`; oyda kişi başına son oy ve "benim
  oyum" ziyaretçiye göre; hız sınırları (ziyaretçi ve IP); eşzamanlı ilk istekte tek `visitor`
  kaydı; yönetim uçları oturumsuz `401`, `kullanici` ile `403`; analiz kaydında IP ve makine adı;
  göç sonrası mevcut satırların korunması ve "tam biri dolu" kısıtı.
- Ön yüz (Vitest): ana ekran oturumsuz açılır; cihaz kimliği üretilir, saklanır ve başlıkta gider,
  kalıcı bellek kapalıyken bellekte kalır; ana ekranda oturum alanı yok; `/admin` oturumsuz giriş
  ekranına yönlenir.
- Tarayıcı senaryosu: oturumsuz soru, iki ayrı tarayıcı bağlamıyla sahiplik ayrımı, yönetimde
  "Soran" bilgisi.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

N/A — bu yetenek vektör araması veya gömme kullanmaz.

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Test stratejisindeki backend ve ön yüz testleri,
  `OpenAPI` ve tip sapma denetimi, göç doğrulaması (Requirement 1–8).
- [ ] Acceptance 2: L2 — Gerçek istemci/ortamda doğrulandı: yerel yığında oturumsuz tarayıcı ana
  ekranı açar, soru sorar ve cevap alır; ikinci tarayıcı bağlamı birincinin analizini ve listesini
  göremez; oy verilir ve yalnız veren tarayıcıda "benim oyum" görünür; `/admin` giriş ister ve
  `yonetici` girişiyle analiz kaydında ziyaretçinin IP adresi görünür (Requirement 1–8).
- [ ] Acceptance 3: L2 — nonprod'da şirket cihazından oturumsuz soru ve yönetimde "Soran" bilgisinde
  ziyaretçinin şirket ağındaki IP adresi (ağ geçidinin değil) görünür (Decision 2).

## Kararlar

Decision 1–6 yukarıdadır.

- Decision 7: Kimliğin anahtarı yalnız IP adresi değildir. Şirket ağında, sanal masaüstünde ve ağ
  geçidi arkasında birçok kişi aynı IP adresiyle görünür; yalnız IP adresine bağlanan sahiplik
  kişilerin birbirinin analizini görmesine yol açar. Cihaz kimliği kaynaktaki `vsa-voter` yaklaşımının
  devamıdır.
- Decision 8: Analiz ve liste kaynaktan farklı olarak sahibine özeldir (Requirement 5); kaynakta
  `ask_id`'yi bilen herkes analizi durdurabiliyordu, listelerin sahibi yoktu.

## Açık sorular

- Open Question 1: Yalnız ana ekranı kullanan eski `kullanici` hesapları pasifleştirilsin mi?
  Varsayılan: dokunulmaz (Decision 6).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Kimliğin taşınması:** Cihaz kimliği tarayıcı verisi silinince, başka tarayıcıda ya da gizli
  pencerede değişir; ziyaretçi önceki analizini ve listesini göremez (iş sürer, analiz kaydına
  yazılır).
- **Oyla kötüye kullanım:** Yeni cihaz kimliği üretmek kolaydır; bir kişi birden çok "ziyaretçi" gibi
  oy verip saklı cevabı sildirebilir. IP hız sınırı yavaşlatır; aynı IP'deki çok sayıda kişiyi
  engellememek için sınır yüksektir.
- **Kişisel veri:** IP adresi ve makine adı kişisel veridir ve yönetim ekranında görünür; kaynakta da
  böyleydi. KVKK aydınlatması kurumun sorumluluğundadır.
- **Açık erişim:** Ana ekrana uygulamaya ağdan ulaşabilen herkes erişir; sözlükteki tablo ve kolon
  adları görünür (kaynakla aynı).
- **Yanlış IP:** Ağ geçidinin güvenilen ağ ayarı yanlışsa her ziyaretçi ağ geçidinin IP adresiyle
  görünür ve IP hız sınırı herkesi birlikte sayar (Acceptance 3).
