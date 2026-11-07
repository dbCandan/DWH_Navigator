# PRD — dictionary-sync

Status: Draft

Version: 0.1.0

Domain: [data-dictionary](../../DOMAIN.md)

## Amaç

Yönetici veri sözlüğünü Excel yüklemek yerine **Sözlüğü güncelle** düğmesiyle veri ambarının sözlük
kaynağından günceller. Kaynaktan gelen sınırlı teknik bilgi, kurum içi sohbet modeli (LLM) desteğiyle
Navigator'ın beklediği sözlük alanlarına dönüştürülür ve etkin sözlükle **birleştirilir**; elle veya
daha önce üretilmiş değerli bilgi kaybolmaz. Her güncelleme yeni bir sürüm ve yöneticinin inceleyeceği
bir **sözlük güncelleme raporu** üretir. Sürümler bir ay saklanır; sorun olursa eski bir sürüme
dönülür. Sistem her zaman etkin olan en güncel sürümü kullanır. Dışa aktarma kalır, sözlüğün Excel'den
içe aktarılması kalkar.

Periyodik zamanlayıcı bu yeteneğin dışındadır (Decision 1).

## Aktörler ve sonuçlar

- **Yönetici** (`yonetici`): Kaynak bağlantısını girer ve dener, güncellemeyi başlatır, ilerlemesini
  izler, raporu inceler, onay bekleyen sürümü uygular veya reddeder, eski sürüme döner. Sonuç:
  ambardaki yeni tablo ve kolonlar elle dosya hazırlamadan sözlüğe girer; her değişikliğin kaydı
  raporda görünür.
- **Kullanıcı** (`kullanici`): Sözlük güncellemesini görmez. Sorusu, analizi başladığı anda etkin
  olan sürümle cevaplanır.
- **Veri ambarı sözlük kaynağı:** Datamartların sözlüğünü tutan, ambarın `EDWUTIL` veritabanındaki iki
  tablo. Kaynak SQL kullanıcısıyla kimlik doğrulaması ister ve Navigator'a HTTP sözleşmesiyle sunulur
  (Decision 2, Open Question 1).
- **Kurum içi model sunucusu:** [llm-connection](../003-llm-connection/PRD.md) ile tanımlı bağlantı
  üzerinden eksik alanları üretir.
- **İşletim ekibi:** Güncellemenin başarısını ve süresini olay kaydından izler; tablo, kolon veya
  açıklama içeriğini logda görmez.

Ölçülebilir sonuç: Yönetici tek düğmeyle güncelleme başlatır; işlem bitince yeni sürüm etkin olur veya
onay bekler ve aynı sürüme bağlı rapor açılır.

## Değişmezler ve sınırlar

- Uygulamanın tek sözlüğü PostgreSQL'dedir; kaynak veya model sözlüğün yerine geçmez.
- Yarım sözlük hiçbir zaman etkin olmaz: sürüm tek işlemde yazılır, indeks "önce kur, sonra yaz"
  düzeniyle değişir ([dictionary-management](../001-dictionary-management/PRD.md) Requirement 8, 9).
- Kaynaktan **yalnız tanım** okunur: `EDWUTIL` içindeki iki sözlük tablosunun içeriği. Ambarın öteki
  tabloları taranmaz; iş verisi, örnek değer ve profil istatistiği ne istenir ne saklanır ne modele
  gönderilir.
- Model yeni tablo veya kolon uyduramaz; yalnız kaynakta bulunan tablo ve kolonların alanlarını doldurur.
- Modelin çalışmaması etkin sözlüğü bozmaz.
- Aynı anda tek güncelleme yürür.
- Sözlük kurum içi veridir; bağlantı bilgisi yalnız sunucu sınırında ve şifreli durur.

## Kararlar

Decision 1: Güncelleme yalnız düğmeyle başlar. Zamanlayıcı proje sahibinin kararıyla bu yeteneğin
dışındadır ve yol haritasında ayrı iş olarak kayıtlıdır.

Decision 2: Kaynağa yalnız HTTP sözleşmesi üzerinden ulaşılır; backend ambar veritabanına doğrudan
bağlanmaz (`rules/01-mimari-ilkeleri.md`). Kaynak istemcisi, uygulama hizmetinin çağırdığı tipli bir
bağlantı noktasının arkasındaki altyapı uyarlayıcısıdır.

Decision 3: Her alanın sahibi bellidir (Requirement 6). Birleştirme tablo ve kolon anahtarıyla yapılır:
tablo için `DB.Şema.Obje`, kolon için tablo anahtarı ve kolon adı.

Decision 4: Model yalnız yeni veya tanımı değişmiş tablolar için çağrılır. Her tablonun kaynak tanımının
özeti saklanır; özeti değişmeyen tablo modele gitmez. Böylece 11.136 kolonun tamamı her seferinde
yeniden işlenmez.

Decision 5: Eski sürüme dönmek geçmişi silmez. Seçilen sürümün içeriğiyle **yeni** bir etkin sürüm
oluşur; böylece etkin sürüm her zaman en güncel kayıttır.

Decision 6: Sürüm biçimi `<12 onaltılık hane>-<Kolonlar kayıt sayısı>` olarak kalır; dosya baytı artık
olmadığından ilk bölüm içerik özetinden gelir. Sürüm numarasını kullanan kayıtlı cevap, oy, analiz
kaydı ve rapor kuralları değişmez.

## İşlevsel gereksinimler

Requirement 1: Yönetici Sözlük sayfasında kaynak bağlantısını girer: API adresi ve isteğe bağlı API
anahtarı. **Bağlantıyı dene** kaynağa ulaşılabildiğini, tablo sayısını ve son değişiklik bilgisini
gösterir. Anahtar kaydedildikten sonra hiçbir yanıtta dönmez; şifreleme anahtarı tanımlı değilse anahtar
kaydedilmez ve yönetici açık bir iletiyle bilgilendirilir.

Requirement 2: **Sözlüğü güncelle** düğmesi arka planda bir güncelleme işi başlatır ve işin kimliğini
hemen döndürür. Yönetici sayfadan ayrılsa da iş sürer. İlerleme aşamayla görünür: kaynak okunuyor,
karşılaştırılıyor, model alanları dolduruyor, indeks kuruluyor, tamamlandı. İş sürerken ikinci istek 409
`dictionary_sync_in_progress` alır. Backend yeniden başlarsa yarım iş `kesildi` olarak kapanır ve
etkin sözlük değişmez.

Requirement 3: Kaynak sayfa sayfa okunur ve sınırlıdır: en çok tablo, kolon ve yanıt boyutu ayarla
belirlenir. Kaynak hatası, biçim hatası veya yarım okuma işi `başarısız` kapatır; eksik veriyle sürüm
oluşmaz. Bozuk tek kayıt bütün işi durdurmaz; atlanır ve raporda uyarı olur.

Requirement 4: Fark hesabı etkin sürüme karşı yapılır: yeni, silinen ve tanımı değişen tablo ve kolonlar
çıkarılır. Hiç fark yoksa ve alan doldurulacak kayıt kalmadıysa yeni sürüm oluşmaz; rapor "değişiklik
yok" sonucunu gösterir.

Requirement 5: Model, tablo başına bir çağrıyla yalnız tanım bilgisinden şu alanları üretir: tablo için
`ObjectDescription`, `Grain`, `KeyColumns`, `TimeColumns`, `BusinessDomain`, `DatasetGroup`; kolon için
`ColumnDescription`, `Synonyms`, `Role`, `Summary`. Çıktı şemayla denetlenir: `Role` sabit kümedendir
(Anahtar, Kod, Ad, Zaman, Ölçü, Bayrak, Metin), `Summary` en çok 70 karakterdir, `KeyColumns` ve
`TimeColumns` tabloda var olan kolonları adlandırır. Kurala uymayan çıktı reddedilir, alan boş kalır ve
raporda uyarı olur. Çağrılar [llm-connection](../003-llm-connection/PRD.md) eşzamanlılık sınırını
paylaşır; güncelleme soru analizlerini aç bırakmaz.

Requirement 6: Birleştirme alan sahipliğine göre yapılır:

| Alan | Sahip | Kural |
|---|---|---|
| Veritabanı, şema, tablo, kolon adı | Kaynak | Kaynaktaki hâli geçerlidir |
| Açıklamalar | Kaynak, boşsa model | Dolu değer korunur (Open Question 3) |
| Grain, KeyColumns, TimeColumns, BusinessDomain, DatasetGroup | Model | Dolu değer korunur |
| Synonyms, Role, Summary | Model | Dolu değer korunur |

Her alanın kaynağı (`kaynak`, `model`, `önceki sürüm`) kayıtlarda tutulur. Değeri olan alan boş değerle
ezilmez. Bugünkü etkin sözlük ilk güncellemenin temelidir; Excel'den gelmiş bilgiler bu yolla korunur.

Requirement 7: Kaynakta bulunmayan tablo ve kolon yeni sürüme girmez ve raporda "silinen" olarak görünür.
Güvenlik sınırı: kaynak boş dönerse iş `başarısız` kapanır; etkin sürümdeki tabloların veya kolonların
ayarlanabilir oranından fazlası (varsayılan %10) silinecekse sürüm etkinleşmez ve `onay bekliyor` olur.
Yönetici raporu görüp uygular veya reddeder.

Requirement 8: Güvenlik sınırını aşmayan güncelleme kendiliğinden etkin olur. Etkin sürüm değişince eski
kayıtlı cevaplar mevcut kurallara göre geçersiz olur; süren analiz başladığı indeksle biter.

Requirement 9: Her iş için bir **sözlük güncelleme raporu** oluşur ve şunları gösterir: başlangıç ve bitiş
zamanı, başlatan kişi, kaynak, sonuç, önceki ve yeni sürüm, yeni/silinen/değişen tablo ve kolon listeleri,
hangi alanın nasıl değiştiği, modelin doldurduğu alan sayısı ve kullanılan model, boş kalan alanlar,
uyarılar, terim sözlüğü ve durak kelime önerileri. Rapor Sözlük sayfasındaki geçmiş listesinden açılır,
filtrelenir ve sayfalıdır. Başarısız işte rapor hata sınıfını gösterir.

Requirement 10: Sürüm geçmişi son bir ayın sürümlerini tarih, başlatan, sayılar ve rapor bağlantısıyla
listeler. Yönetici bir sürüm için **Bu sürüme dön** seçer, onay verir ve Decision 5'teki gibi yeni etkin
sürüm oluşur; rapor bunu `geri dönüş` olarak kaydeder. Güncelleme sürerken geri dönüş 409 alır. Sonraki
güncelleme yeni etkin sürümü temel alır; kaynakta düzelmeyen değişiklik yeniden gelir ve raporda görünür.

Requirement 11: Etkin sürümün yerini aldığı andan itibaren 30 gün geçen sürümün tablo ve kolon kayıtları
budanır; sürüm kaydı ve raporun özeti yumuşak silinmiş kalır. Etkin sürüm hiç budanmaz. Zamanlayıcı
olmadığından budama her güncellemede ve backend açılışında çalışır.

Requirement 12: Sözlük güncellemesi terim sözlüğü ve durak kelimeler için de **öneri** üretir: tablo ve
kolon adlarındaki yeni kısaltmalar ve eş anlamlı adaylar ile aramayı kirleten sık kelimeler. Öneriler
raporda görünür; yönetici seçtiklerini tek işlemle uygular ve mevcut
[vocabulary-management](../002-vocabulary-management/PRD.md) kuralları geçerlidir. Yönetici onayı
olmadan liste değişmez (Open Question 4).

Requirement 13: Sözlüğün Excel'den içe aktarılması kalkar: yükleme ucu, sürükle-bırak alanı, içe aktarma
düğmesi ve betiğin `import` komutu silinir. Dışa aktarma kalır. Boş şablon indirme kalkar. Etkin sürüm
yokken boş durum **Kaynağı bağla** yönlendirmesini gösterir. Kelimeler sayfasının Excel'i bu kararın
dışındadır.

## API sözleşmesi

Bütün uçlar yalnız `yonetici` rolüne açıktır. Kesin yollar `plan.md` içinde mevcut sözlük uçlarına göre
sabitlenir.

- Kaynak bağlantısını oku, kaydet, dene.
- Güncelleme başlat (202), iş durumunu oku.
- Sürüm geçmişini ve raporu sayfalı oku.
- Onay bekleyen sürümü uygula, reddet; önerileri uygula.
- Eski sürüme dön.

Yeni hata kodları: `dictionary_sync_in_progress` (409), `dictionary_source_not_configured` (409),
`dictionary_source_unavailable` (502), `dictionary_source_invalid` (502),
`dictionary_version_expired` (410). Kaynak sözleşmesinin biçimi Open Question 1 kapanınca bu bölüme
yazılır.

## Güvenlik ve yetkilendirme

- Uçlar backend'de `yonetici` yetkisi ister; menü gizlemek yetki değildir.
- API anahtarı `DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY` ile şifreli saklanır; arayüze, loga, rapora dönmez.
- Kaynak adresi model bağlantısındaki ağ denetiminden geçer; yönlendirme izlenmez, yanıt boyutu ve süre
  sınırlıdır.
- Kaynaktan ve modelden gelen metin güvenilmeyen veridir: talimat sayılmaz, modele veri olarak verilir,
  arayüzde metin olarak gösterilir, Excel'e formül olmayacak biçimde yazılır.
- Kişisel veri işareti (KVKK) mevcut açıklama kuralıyla yeniden türetilir; model bu işareti kaldıramaz.
- Modele yalnız tanım gider (Değişmezler). Tanımlarda kişisel veri olup olmadığı KVKK incelemesinde
  doğrulanır.

## Veri ve geçiş

- Yeni kayıtlar: kaynak bağlantısı, güncelleme işi, sürüm raporu ve raporun değişiklik satırları.
- Sürüm tablosunda "en çok bir önceki sürüm" kısıtı kalkar; birden çok saklanan sürüm ve `onay bekliyor`
  durumu eklenir. En çok bir etkin sürüm kısıtı kalır.
- `channel` değerlerine `kaynak` ve `geri dönüş` eklenir; tablo kaynak özeti ve alan kaynakları kayıtlarda
  tutulur.
- Bir aylık saklama için depolama tahmini `plan.md` içinde gerçek sözlük boyutuyla yapılır.
- Mevcut etkin sürüm ve veriler göçte korunur.

## Doğrulama ve test stratejisi

- Birim: fark hesabı, alan sahipliği, güvenlik sınırı, model çıktısı denetimi, sürüm özeti, budama.
- Tümleştirme: gerçek PostgreSQL ve HTTP uygulamasıyla güncelleme, tek işlem, kilit, kesilme, geri dönüş,
  yetki ve kiracı yalıtımı; kaynak ve model için sözleşmeye bağlı sahte sunucular.
- Tarayıcı: gerçek girişle bağlantı, güncelleme, rapor, onay ve geri dönüş.
- Excel içe aktarmanın kaldırıldığı uçların ve arayüzün yok olduğu doğrulanır; dışa aktarma korunur.

## Gözlemlenebilirlik

İş başlangıcı, bitişi, sonucu, süresi, sayılar ve hata sınıfı yapılandırılmış olay olarak yazılır. Tablo,
kolon, açıklama, model çıktısı ve kaynak adresindeki kimlik bilgisi loga girmez. Ölçüm etiketleri sınırlı
kalır.

## Dağıtım etkisi

- Backend çıkış ağ politikasına kaynak için dar ve açık bir izin eklenir; yerel yığında kaynak için
  `local-egress` düzeni [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  kapsamında değerlendirilir.
- İşçi veya ayrı iş yükü eklenmez; iş backend içinde çalışır. Birden çok kopyada tek iş kuralı
  veritabanı kilidiyle korunur.
- Kaynak istemcisi HTTP kullanır; yeni sürücü bağımlılığı gerekmez.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Etkilenen kabul edilmiş belgeler

Bu PRD kabul edilmeden önce aşağıdakiler yerinde revize edilip yeniden kabule sunulur:

- [dictionary-management](../001-dictionary-management/PRD.md): içe aktarma gereksinimleri, Requirement 7,
  8, 14, 15, 16 ve Decision 13 ("önceki sürüme dönüş yok").
- [DOMAIN.md](../../DOMAIN.md): "Excel yalnız aktarım içindir" tanımı, Sözlük sürümü tanımı, harici sınırlar.
- [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md): kaynak için
  çıkış izni.

## Açık sorular

Open Question 1: `EDWUTIL` içindeki iki tabloyu HTTP ile hangi servis sunacak, yanıt biçimi ne olacak?
Tabloların adları ve kolonları da bu soruya bağlıdır. Doğrudan SQL bağlantısı ancak
`rules/01-mimari-ilkeleri.md` kuralı kendi yönetişim kaynağında değişip projeye kanonik güncellemeyle
gelirse seçilebilir. Bu kapanmadan kaynak sözleşmesi ve uyarlayıcı yazılamaz.

Open Question 2: Excel içe aktarma kalkınca yönetici hatalı bir model değerini nasıl düzeltecek? Öneri:
raporda veya tablo ayrıntısında alanı düzeltme; düzeltilen alan `yönetici` kaynaklı olur ve kilitlenir.

Open Question 3: Kaynaktaki açıklamanın kalitesi düşükse model mevcut dolu açıklamayı iyileştirebilir mi?
Öneri: üzerine yazmaz, raporda öneri olarak gösterir.

Open Question 4: Terim ve durak kelime önerileri onaysız uygulanabilir mi? Öneri: hayır; bir kelime bütün
aramaları etkilediğinden yönetici onayı gerekir.

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 3–8 ve 11'in birim ve gerçek PostgreSQL
  testleri geçer; yarım okuma, model hatası ve kesilme etkin sürümü değiştirmez.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 1, 2, 9, 10, 12 ve 13'ün API ve ön yüz
  testleri geçer; yetkisiz rol 403 alır; anahtar hiçbir yanıtta dönmez; sözleşme ve tip sapması yoktur.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Requirement 6'da dolu alanın boş değerle ezilmediği,
  model çıktısının kaynakta olmayan tablo veya kolon ekleyemediği kanıtlanır.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel PostgreSQL ve canlı HTTP üzerinde
  yönetici tarayıcıda kaynağı bağlar, güncelleme başlatır, raporu inceler, eski sürüme döner ve sözlüğü
  dışa aktarır; soru analizi yeni sürümü kullanır.
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: güvenlik sınırını aşan silme etkinleşmez,
  onay bekler; onay ve ret yolları tarayıcıda gözlenir.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama
