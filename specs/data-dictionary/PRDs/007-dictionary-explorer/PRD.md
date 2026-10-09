# PRD — dictionary-explorer

Status: Accepted

Version: 1.0.0

Acceptance date: 2026-10-08

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

Kullanıcı ana ekranda veri ambarındaki bütün tabloları "Evren" yıldız haritasında görür: her yıldız
bir tablodur, yıldızlar veri seti gruplarına göre kümelenir ve her küme kendi rengini taşır
(ADR-024/027). Bir yıldıza tıklayarak ya da soru çubuğuna tablonun adını yazarak tablonun dosyasını
açar: bütün kolonlar, açıklamaları, eş anlamlıları, KVKK ve birleştirme anahtarı işaretleri,
kolonlarda arama, süzgeçler ve aynı kümedeki öteki tablolar. Soru analiz edilirken harita aday
tabloları dolaşan bir "yolculuk" gösterir; cevap gelince önerilen tabloları işaretler. Bu PRD ayrıca
ana ekranın genel kabuğunu tanımlar: üst çubuk, durum göstergesi ve oturum alanı.

Kaynak arayüz (`src/vsa/web/static/index.html`) React'te görsel olarak birebir aynı kurulur
(Decision 3). Frontend kurallarının (rules/30-34) istekleri görünümü değiştirmeden karşılanır; nasıl
karşılandıkları Decision 4–8'de yazılıdır.

## Aktörler ve sonuçlar

- **Kullanıcı (`kullanici`) ve yönetici (`yonetici`):** Ana ekranı aynı biçimde kullanır: haritada
  gezinir, tablo dosyası açar, tablo arar, durum göstergesinden sözlüğün ve sohbet modelinin hazır
  olup olmadığını görür. Ana ekranda yönetim ekranına bağlantı yoktur; yönetici yönetim ekranını
  adresini (`/admin`) yazarak açar (kaynakla aynı).
- **Ana ekrana bağlanan yetenekler:** [question-analysis](../004-question-analysis/PRD.md) soru
  çubuğunu üst çubuğun ortasına yerleştirir, yolculuğu başlatıp bitirir ve cevaptaki tabloların dosyasını
  açar; [list-search](../005-list-search/PRD.md) üst çubuğa toplu arama hapını koyar;
  [answer-feedback](../006-answer-feedback/PRD.md) kullanıcıların doğruladığı tabloların dosyasını açar.

Ölçülebilir sonuç: Giriş yapmış her kullanıcı herhangi bir tablonun bütün kolonlarını en çok iki
adımda (yıldız ya da tablo adı → tablo dosyası) ve fare kullanmadan da (soru çubuğuna tablo adını
yazarak) açar; ana ekran aynı sözlük ve ekran boyutunda kaynaktakiyle aynı görünür, tek fark oturum
alanıdır; tablo arama, Evren verisi ve tablo ayrıntısı uçları aynı sözlük, kelime listeleri ve
ayarlarla kaynakla aynı sonucu (aynı tablolar, aynı sıra, aynı alanlar) döner; durum göstergesi
sözlüğün ya da modelin hazır olmadığını en geç 60 saniyede gösterir; süren bir analiz bu uçların
hiçbirini bekletmez.

## Değişmezler ve sınırlar

- Bu yetenek salt okunurdur; hiçbir ucu veri yazmaz. Veriyi hizmetteki arama indeksinden okur. İndeksin
  kurulması ve yaşam döngüsü [search-settings](../009-search-settings/PRD.md), sözlük kayıtları ve sürümü
  [dictionary-management](../001-dictionary-management/PRD.md) PRD'sinindir.
- Uçlar analiz kilidini (analizleri sıraya koyan kilidi) almaz; süren bir analiz bu uçları bekletmez
  (kaynakta `tests/test_web.py` `test_explorer_not_blocked_by_a_running_question`).
- Soru metni, arama metni, tablo ve kolon adı uygulama loguna, ölçümlere ve izlere girmez; soru ve arama
  metni adres satırında taşınmaz (Decision 9).
- Soru çubuğu, cevap görünümü, analiz akışı ve durum ucu (`GET /status`)
  [question-analysis](../004-question-analysis/PRD.md); toplu
  arama hapı ve listesi [list-search](../005-list-search/PRD.md); oy arayüzü
  [answer-feedback](../006-answer-feedback/PRD.md); giriş, oturum, roller ve görünen ad
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md); model sunucusunun
  sağlık denetimi ve hata sınıfları [llm-connection](../003-llm-connection/PRD.md); analistin okuduğu
  aday sayısı ayarı [search-settings](../009-search-settings/PRD.md) PRD'sindedir. Bu PRD onların kabukta
  duracağı yerleri, tablo dosyasını açma işlevini ve yolculuk işlevlerini sağlar.

Decision 1: Tablo arama, Evren verisi ve tablo ayrıntısı kaynaktaki kodla bayt bayt aynı sonucu verir:
`src/vsa/web/server.py` `App.objects`, `App._object_index`, `App.galaxy`, `App.object_detail`,
`src/vsa/web/serialize.py` `column` ve `src/vsa/scoring/explain.py` `key_columns`. İçerik katmanı motorun
`rank_objects` işlevini kullanır (çekirdek motor [question-analysis](../004-question-analysis/PRD.md)
sahipliğindedir). Aynı sözlük, kelime listeleri ve ayarlarla yanıtlar `elapsed_ms` dışında kaynakla
aynıdır; bu, kaynak paketle yan yana çalışan fark testleriyle (aynı girdiyle kaynağı ve hedefi
çalıştırıp çıktıları karşılaştıran testlerle) kanıtlanır.

Decision 2: Bu PRD'nin bütün uçları `kullanici` ve `yonetici` rollerine açıktır (süper yönetici her
rotayı görür); oturumsuz istek 401, iki rolden birine sahip olmayan kullanıcı 403 alır. Kaynakta ana
ekran ve bu uçlar kimliksizdi.

Decision 3: Ana ekranın görsel tasarımı kaynakla birebir aynıdır: koyu "Evren" gökyüzü, kümeler,
yolculuk, tablo dosyası paneli, soru çubuğu, cevap görünümü, liste ve oylar kaynaktaki CSS
değerleriyle (renkler, yazı tipleri, aralıklar, gölgeler, canlandırmalar, kırılma noktaları), mümkün
olduğunca aynı DOM düzeni ve sınıf adlarıyla, aynı Türkçe metinler ve aynı etkileşimlerle kurulur.
Görünür yeni öğe eklenmez; tek yeni öğe fabrikanın zorunlu kıldığı oturum alanıdır (Requirement 1).
İskeletin kendi varsayılan görünümü (ör. `HomePage`) kullanılmaz. Frontend kurallarının istekleri
görünümü değiştirmeden karşılanır (Decision 4–8).

## Mevcut davranış

Kaynak: bu deponun geçmişindeki `76e21a3`; ana ekran `src/vsa/web/static/index.html` (tek dosya, dış
kaynak yok). Her maddenin sonunda hedefteki karşılığı yazılıdır.

- **Kabuk ve üst çubuk** (`index.html` `header.top`): Solda pusula simgesi, "DWH Navigator" ve
  altında "Veri ambarı rehberi"; marka `/` adresine giden "Yeni başlangıç" bağlantısıdır (sayfayı
  yeniden yükler). Ortada boş bir yuva vardır; ilk sorudan sonra soru çubuğu kayarak buraya
  yerleşir. Sağda durum göstergesi ve toplu arama sürerken "Liste N/M" ya da "Liste sonucu" hapı
  bulunur. Pusula bir analiz sürerken arar gibi döner, cevap gelince yerine oturur. Sayfa
  kaydırılınca üst çubuğun arkasında yumuşak bir perde belirir. 760 pikselden dar ekranda durum
  göstergesi gizlenir. Kullanıcı kimliği ve çıkış yoktur. Ana ekrandan yönetim ekranına bilerek
  bağlantı verilmez; yönetim ekranı adres elle yazılarak açılır (ADR-047, `tests/test_web.py`
  `test_admin_page_served_and_not_linked`). Alt satır boş bir boşluktur. **Hedefte:** Aynı görünüm;
  giriş zorunludur ve üst çubuğa yalnız oturum alanı eklenir; ana ekrandan yönetim ekranına yine
  bağlantı verilmez (Requirement 1).
- **Durum göstergesi** (`loadStatus`; `server.py` `App.status`, `App._llm_state`): Açılışta ve 60
  saniyede bir `GET /api/status` çağrılır; ayrıca analistin yazmadığı bir cevaptan sonra yenilenir.
  Yanıt `columns`, `objects`, `llm` (bağlı model adı ya da boş), `llm_state` (`ok`, `none`, `down`;
  `model`, `reason`) ve `shortlist` (analistin okuduğu aday sayısı) taşır. Hap "Hazır" (yeşil nokta),
  "Modele ulaşılamıyor" ya da "Model bağlı değil" der; ipucu kutusu "Sözlük: N kolon · M tablo" ve
  "Analist: <model>" ya da "Model: <sebep>" satırlarını gösterir. Model sorunu varsa açılış görünümünde
  soru çubuğunun altında "<sebep>. Model çalışmadan soru analiz edilemez." ya da "Sohbet modeli bağlı
  değil: soru analiz edilemez. Yönetim → Yapay zekâ sayfasından bir model bağlayın." yazar. İstek
  başarısızsa hap "Sunucuya ulaşılamadı" der. Sebep metni model sunucusunun adresini içerir
  (`llm/client.py`: "Model sunucusuna ulaşılamadı (<adres>): …") ve herkese görünür. Sözlük boşken hap
  yine "Hazır" der. **Hedefte:** Aynı alanlar ve metinler; durum ucu
  [question-analysis](../004-question-analysis/PRD.md) PRD'sinindir (Requirement 17) ve
  `dictionary_version` taşır; oturum gerekir; sebepte adres yoktur; boş sözlük gösterilir
  (Requirement 2, Decision 10, Decision 13).
- **Evren verisi** (`server.py` `App.galaxy`, `App._object_index`): `GET /api/galaxy` her tablo için
  `key`, `name`, `schema` (`DB.Şema`), `group` (tablonun kolonlarındaki veri seti gruplarının sıralı
  listesinin ilki; grup Objeler sayfasından geldiği için pratikte tablonun grubu; yoksa "Diğer") ve
  `columns` (kolon sayısı) döner; sıra tablo adının kod noktası sırasıdır (Python'un düz metin
  karşılaştırması), eşitlikte sözlükteki sıra. Harita veriyi sayfa açılışında bir kez yükler.
  **Hedefte:** `GET /explorer/galaxy`, aynı içerik (Requirement 3); sözlük değişince yeniden yükleme
  (Requirement 16).
- **Yerleşim ve renk** (`index.html` `Cosmos.build`, `screen`): Kümeler üye sayısına göre büyükten
  küçüğe dizilir; küme merkezleri ayçiçeği diziliminde (altın açıyla, `r = 0,1 + 0,82 × √((i + 0,5) / G)`)
  merkezden dışa yerleşir, en büyük küme merkeze en yakındır. Kümenin tonu küme adından FNV-1a ile (adı
  tek bir sayıya indiren sabit hesapla) bulunur (`mod 360`). Üyeler küme merkezinin çevresine ad
  sırasıyla sarmal dizilir; küçük sapmalar, derinlik ve ışıldama evresi küme adından türetilen sabit
  tohumla hesaplanır; yerleşim her açılışta aynıdır. Yıldızın büyüklüğü `0,9 + √kolon × 0,32`'dir.
  Konumlar ekranın genişliğinin %47'si ve yüksekliğinin %46'sıyla ölçeklenir. **Hedefte:** Aynı hesap,
  saf ve test edilen bir işlev olarak (Requirement 4).
- **Çizim ve hareket** (`Cosmos.frame`, `draw`): Çizim alanı (canvas) sayfanın arkasındadır ve ekran
  okuyucudan gizlidir (`aria-hidden`). Sabit tohumlu 480 sönük toz noktası, her yıldızdan küme merkezine
  çok ince çizgi, ışıldama; boşta gökyüzü çok yavaş döner (derinliğe göre farklı hızla), fareyle hafifçe
  kayar (yakın yıldızlar daha çok); arka planda bulutsu 38 saniyelik bir döngüyle kayar. Sol altta "Veri
  evreni · N tablo · K küme" ve yolculuk günlüğü (HUD: haritanın üstündeki bilgi satırı); dar ekranda,
  120 pikselden fazla kaydırınca ve cevap varken gizlenir. Çizim saniyede en çok yaklaşık 30 kare,
  yolculuğun okuma ve bekleme evrelerinde 20 kare yapılır; sekme görünmezken durur. Sayfada cevap varken
  harita %30 parlaklıkta arka plandır ve yıldızlar etkileşime kapanır. Evren verisi alınamazsa sayfa
  haritasız çalışır. **Hedefte:** Aynı (Requirement 5).
- **Üzerine gelme, tıklama ve seçim** (`Cosmos` `pointermove`, `click`, `steer`, `drawSelected`):
  İmlece 14 pikselden yakın yıldız seçilebilir olur: el imleci, beyaz halka ve ipucu kutusunda ad,
  "<şema> · <N> kolon" ve grup. Üst çubuk, cevap, soru çubuğu, düğme, bağlantı, form alanı, tablo,
  açılır bölüm, alt satır ve tablo dosyası üzerindeyken yıldız seçilmez. Yıldıza tıklama tablo
  dosyasını açar, boş gökyüzüne tıklama açık dosyayı kapatır. Dosya açıkken seçili yıldız ekranın
  panel dışındaki alanının ortasına kayar (en az 320 piksel kalıyorsa), kümesinin üyelerine çizgiler
  çıkar, dönen bir nişangâh ve adı görünür, öteki kümeler %40 parlaklığa iner. Yıldızlara klavyeyle
  erişilemez. **Hedefte:** Aynı fare davranışı; harita süsleyici kalır ve tablolara klavyeyle var
  olan yollardan ulaşılır (Requirement 6, 15, Decision 4).
- **Yolculuk** (`ask`, `Cosmos.begin`, `candidates`, `focus`, `end`, `radarDone`, `patrol`,
  `startReading`, `showCandidates`, `showFocus`): Soru gönderilince radar soru çubuğunun altından bir tur
  döner (1,2 rad/sn hızla, yaklaşık 5,2 saniye); bilgi satırı "N kolon taranıyor" ya da "rota
  planlanıyor" der. Aynı anda soru metniyle `GET /api/objects?q=` çağrılır ve içerik katmanından skorlu
  tablolar aday olur. Radar bitince en yüksek skorlu en çok 12 aday en yakın komşu sırasıyla rota olur ("N aday",
  "rota çizildi") ve bir sonda (küçük gemi) rotayı izler; aday yoksa en büyük 9 kümeyi dolaşır ("veri
  kümeleri taranıyor"). Model bağlıysa sonda adayların ilk `shortlist` tanesi (yoksa 8) arasında halka
  çizer ("K finalist", "model okuyor", "okunuyor: <ad>"). Cevap gelince sonda önerilen tablolara uçup
  birinci tabloya iner (yeşil halkalar); bilgi satırı "N sonuç · varış: <ad>" der; sonuçlar takımyıldız
  olarak kalır (skorla büyüyen ışıma, birinci tabloda yeşil nokta, ilk 6 tabloda "<sıra>. <ad>" ve
  "%<skor>" etiketleri, tabloları sırayla bağlayan kesikli çizgi). Cevap radar turundan önce gelirse (ör. kayıtlı cevap)
  ekran turun bitmesini bekler; "Durdur" bu beklemeyi de bitirir. Hareket azaltma tercihi açıkken de
  yolculuk çizilir ve bekleme sürer. **Hedefte:** Aynı; hareket azaltmada durağan ve beklemesiz
  (Requirement 7, 8).
- **Tablo adıyla açma** (`ask`, `Cosmos.find`): Soru çubuğuna yazılan metin boşluk içermiyorsa ve
  Türkçe büyük/küçük harf duyarsız (ı ile i eşit) tam olarak bir tablonun adına, `Şema.ad`'ına ya da
  tam anahtarına eşitse soru sorulmaz, o tablonun dosyası açılır. İki şemadaki `vCampaign` gibi
  birden çok eşleşmede metin soru olarak sorulur. **Hedefte:** Aynı; tablolara klavyeyle ulaşmanın
  ana yoludur (Requirement 9, 15).
- **Tablo arama ucu** (`server.py` `App.objects`; ADR-023): Üç katman: ad (anahtar ve grup adı
  içinde geçen metin), içerik (metin en az 3 karakterse motorun model kullanmayan kural sıralaması,
  en çok 25 tablo) ve kolon adı. Boş metinde ad sırasındaki ilk 60 tablo; en çok 60 sonuç; sıra
  katman, skor, ad. Motor kilidi alınmaz. Arayüzde yalnız yolculuk adaylarını bulmak için
  kullanılır; "Keşfet" sekmesi ADR-027 ile kalkmıştır. Soru metni adres satırında (`?q=`) gider.
  **Hedefte:** Aynı sonuç ve aynı kullanım; metin istek gövdesinde (`POST /explorer/table-searches`)
  (Requirement 10, Decision 9).
- **Tablo dosyası** (`Dossier`, `GET /api/object/<anahtar>`, `App.object_detail`): Yanıt `key`,
  `name`, `schema`, `groups`, kolonlar (`key`, `column`, `object`, `description`, `synonyms`, `pii`,
  `group`) ve `join_keys` (birleştirme anahtarları). Panel sağdan açılır (en çok 540 piksel; dar
  ekranda tam genişlik): küme tonunda gezegen simgesi, grup başlığı, tablo adı, tam anahtar ve
  "Kopyala", "Kapat (Esc)"; kolon, anahtar ve KVKK sayıları; kolon araması; "Tümü · N", "Anahtar ·
  n", "KVKK · n" süzgeçleri; kolon satırları (`div` + `role=button`, Enter ve Space ile açılır);
  "Aynı kümede · N tablo" ve en büyük 14 komşu. Açılınca odak "Kapat"a gider, kapanınca dosyayı açan
  öğeye döner; Esc kapatır, "/" kolon aramasına gider; Tab odağı panelden çıkıp soluklaşmış sayfaya
  geçebilir. `Role` ve `Summary` gösterilmez. **Hedefte:** Aynı içerik ve görünüm; odak panelde
  kalır, satırlar yerel düğme (Requirement 11–13, Decision 6–7).
- **Dosyayı açan öteki yerler** (`colsButton`, `richOf`, `crowdSections`): Cevap kartındaki "Kolonlar"
  düğmesi, cevap metninde geçen ama önerilerde olmayan tablo adları ve kullanıcıların doğruladığı
  tablolar aynı paneli açar. **Hedefte:** Paylaşılan açma işlevi (Requirement 14).
- **Görsel değerler** (`index.html` `:root` ve bileşen CSS'i): Koyu "Evren" paleti sabit renklerle
  yazılmıştır (yönetim ekranı `admin.html` aynı paleti kullanır); sistem yazı tipleri; dış kaynak
  yoktur. Hareket azaltma tercihi CSS canlandırmalarını kapatır ama çizim alanındaki hareketi
  durdurmaz. **Hedefte:** Kaynak CSS'in değerleri `globals.css`'te merkezi belirteçler (CSS
  değişkenleri) olur ve görünüm değişmez; hareket azaltma tercihi çizim alanına da uygulanır
  (Requirement 8, 17, Decision 5, 8).

## İşlevsel gereksinimler

Requirement 1: Ana ekran (`/`) yalnız oturumla açılır; oturum yoksa giriş ekranına yönlenir
([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)). Üst çubuk soldan
sağa şunları taşır:
- Marka: pusula simgesi, "DWH Navigator", altında "Veri ambarı rehberi"; "Yeni başlangıç" bağlantısıdır
  ve ana ekranı ilk hâline döndürür (cevap temizlenir, soru çubuğu ortaya iner). Sürmekte olan toplu
  aramanın ne olacağı [list-search](../005-list-search/PRD.md) PRD'sindedir.
- Orta yuva: ilk sorudan sonra soru çubuğu buraya yerleşir ([question-analysis](../004-question-analysis/PRD.md)).
- Araçlar: toplu arama hapının yeri ([list-search](../005-list-search/PRD.md)), durum göstergesi
  (Requirement 2) ve oturum alanı (görünen ad, "Parolamı değiştir" ve "Çıkış"; davranışı
  user-accounts Requirement 16'dadır). Oturum alanı fabrikanın zorunlu kıldığı tek yeni öğedir;
  kaynağın üst çubuk biçimine en az müdahaleyle, durum hapıyla aynı görünüm ve belirteçlerle
  yerleşir. Ana ekranda yönetim ekranına bağlantı yoktur (kaynakla aynı); yönetici `/admin` adresini
  yazarak açar.

Pusula simgesi bir analiz sürerken arar gibi döner ve cevap gelince yerine oturur; hareket azaltmada
dönmez. Sayfa kaydırılınca üst çubuğun arkasında içeriğin okunaklı geçmesini sağlayan yumuşak bir
perde belirir. 760 pikselden dar ekranda durum göstergesi gizlenir (kaynakla aynı); oturum alanı
yalnız simgeyle, erişilebilir adıyla görünür. Sekme başlığı "DWH Navigator", sekme simgesi
pusuladır.

Requirement 2: Durum göstergesi [question-analysis](../004-question-analysis/PRD.md) PRD'sinin
`GET /status` ucunu (Requirement 17) açılışta, 60 saniyede bir ve question-analysis analistin yazmadığı
bir cevap gösterdiğinde çağırır. Soru çubuğunun altındaki uyarı satırının metinleri ve önceliği bu
gereksinimdedir (question-analysis Requirement 22 buraya bağlantı verir). Hap durumları şu önceliktedir:
1. Sözlük boş (`objects` 0): uyarı rengi, "Sözlük yok"; uyarı satırı "Sözlük henüz içe aktarılmadı: soru
   analiz edilemez. Yönetim → Sözlük sayfasından şablondaki Excel'i içe aktarın." (yeni, Decision 10).
2. Model bağlı değil (`llm_state.state` `none`): uyarı rengi, "Model bağlı değil"; uyarı satırı "Sohbet
   modeli bağlı değil: soru analiz edilemez. Yönetim → Yapay zekâ sayfasından bir model bağlayın."
3. Modele ulaşılamıyor (`down`): hata rengi, "Modele ulaşılamıyor"; uyarı satırı "<sebep>. Model
   çalışmadan soru analiz edilemez."
4. Hazır (`ok`): yeşil nokta, "Hazır"; uyarı satırı yok.

İpucu kutusu iki satırdır: "Sözlük: <kolon> kolon · <tablo> tablo" (sayılar Türkçe biçimde, ör. 11.136)
ve "Analist:
<model>" ya da "Model: <sebep ya da 'bağlı değil'>". Uyarı satırı yalnız açılış görünümünde, soru
çubuğunun altında durur. İstek başarısız olursa hap "Sunucuya ulaşılamadı" der. Sebep metni
[llm-connection](../003-llm-connection/PRD.md) PRD'sindeki sabit hata sınıfının kısa Türkçe iletisidir;
model sunucusunun adresi ve hata gövdesi gösterilmez.

Requirement 3: `GET /explorer/galaxy` hizmetteki indeksteki her tablo için `key` (`DB.Şema.Obje`),
`name`, `schema` (`DB.Şema`), `group` (Mevcut davranıştaki kural; grubu olmayan tablo "Diğer") ve
`columns` (kolon sayısı) döner. Sıra, tablo adının kod noktası sırası (Python'un düz metin
karşılaştırması), eşitlikte sözlükteki sıradır.
Bütün tablolar tek yanıtta, `total` ile döner (Decision 11). Sözlük boşken `items` boş, `total` 0'dır.

Requirement 4: Yerleşim ve renk saf (yan etkisiz) ve test edilen bir işlevdir; aynı Evren verisi her
zaman aynı konumları, büyüklükleri, derinlikleri ve tonları verir. Kural kaynaktaki `Cosmos.build`
hesabıdır: her tablo bir yıldız, aynı gruptaki tablolar bir küme; kümeler üye sayısına göre büyükten
küçüğe ve ayçiçeği diziliminde merkezden dışa; kümenin tonu küme adının FNV-1a sayısının 360'a
bölümünden kalan; üyeler küme merkezinin çevresinde ad sırasıyla sarmal; sapmalar, derinlik ve ışıldama
evresi küme adından türetilen sabit tohumla; yıldız büyüklüğü `0,9 + √kolon × 0,32`. Konumlar ekranın
boyutuna oranlıdır (genişliğin %47'si, yüksekliğin %46'sı); sabit piksel konumu yoktur.

Requirement 5: Haritanın çizimi:
- Arka planda sabit tohumlu 480 sönük toz noktası, her yıldızdan küme merkezine çok ince bir çizgi;
  yıldızlar hafifçe ışıldar; boşta gökyüzü çok yavaş döner (derinliğe göre farklı hızla) ve fareyle
  hafifçe kayar.
- Sol altta "Veri evreni · <tablo> tablo · <küme> küme" yazısı ve yolculuk günlüğü durur; 760 pikselden
  dar ekranda, sayfa 120 pikselden fazla kaydırılınca, cevap varken ve tablo dosyası açıkken gizlenir.
- Çizim saniyede en çok yaklaşık 30 kare, yolculuğun okuma ve bekleme evrelerinde en çok 20 kare yapılır;
  sekme görünmezken çizim durur.
- Sayfada cevap varken harita %30 parlaklıkta yalnız arka plandır; yıldızlar üzerine gelme, etiket ve
  tıklamaya kapanır.
- Harita bileşeni gecikmeli yüklenir; kabuk ve soru çubuğu onu beklemeden çalışır. Evren verisi
  alınamazsa sayfa haritasız çalışır.

Requirement 6: Fareyle etkileşim:
- İmleç bir yıldıza 14 pikselden yakınsa yıldız seçilebilir olur: el imleci, yıldızın çevresinde halka ve
  ipucu kutusunda tablo adı, "<şema> · <kolon> kolon" ve grup görünür. Üst çubuk, soru çubuğu, cevap,
  düğme, bağlantı, form alanı, tablo, açılır bölüm ve tablo dosyası üzerindeyken yıldız seçilmez.
- Yıldıza tıklama tablo dosyasını açar; dosya açıkken boş gökyüzüne tıklama dosyayı kapatır.
- Dosya açıkken seçili yıldız ekranın panel dışındaki alanının ortasına kayar (panel dışında en az 320
  piksel kalıyorsa); yıldızdan kendi kümesinin üyelerine çizgiler çıkar, çevresinde dönen bir nişangâh
  ve adı görünür; öteki kümeler %40 parlaklığa iner.

Requirement 7: Yolculuk, [question-analysis](../004-question-analysis/PRD.md) tarafından başlatılır ve
bitirilir (bu PRD'nin Requirement 14'teki işlevleriyle) ve kaynaktaki evreleri izler:
1. Başlangıç: yolculuk soru çubuğunun altından başlar; radar halkaları ve dönen tarama ışını bir tur
   (yaklaşık 5,2 saniye) döner; sol alttaki bilgi satırı "<kolon sayısı> kolon taranıyor" ya da sayı
   yoksa "rota planlanıyor" der.
2. Adaylar: soru metniyle tablo arama ucu (Requirement 10) çağrılır; skoru olan tablolar aday olur.
   Radar bitince en yüksek skorlu en çok 12 aday en yakın komşu sırasıyla rota olur; bilgi satırı "<N>
   aday" ve "rota çizildi" der; sonda rotayı izler ve uğradığı yıldızda halka, ad ve skor gösterir. Radar
   bittiğinde aday gelmemişse sonda en büyük 9 kümeyi dolaşır ("veri kümeleri taranıyor").
3. Okuma: durumdaki `llm` doluysa sonda adayların ilk `shortlist` tanesi (en az 2) arasında kapalı bir
   halka çizer; bilgi satırı "<K> finalist", "model okuyor" ve geçtiği yıldızda "okunuyor: <tablo adı>"
   der. Model bağlı değilse sonda bekler.
4. Varış: cevap gelince sonda önerilen tablolara uçar ve birinci tabloya iner (yeşil iniş halkaları);
   bilgi satırı "<N> sonuç · varış: <tablo adı>" der. Sonuçlar takımyıldız olarak kalır: skorla büyüyen
   ışıma ve halka, birinci tabloda yeşil nokta, ilk 6 tabloda "<sıra>. <ad>" ve "%<skor>" etiketleri,
   boştayken tabloları sırayla bağlayan kesikli çizgi.
5. Bitiş: cevapsız biten, durdurulan ya da hata veren analizde yolculuk durur.

Bilgi satırındaki yolculuk günlüğü son dört adımı " → " ile gösterir; daha eskisi varsa başa "…"
konur. Analiz işi sıradayken (`queued`) günlüğe "sırada" adımı yazılır; sayı ve süre yazılmaz
([question-analysis](../004-question-analysis/PRD.md) Requirement 20). Cevap radar turundan önce
gelirse (ör. kayıtlı cevap) cevap görünümü turun bitmesini bekler; "Durdur" bu beklemeyi de bitirir
(Decision 12). Hareket azaltmada (Requirement 8) bekleme yoktur.

Requirement 8: İşletim sisteminin "hareketi azalt" tercihi açıksa harita durağandır: dönüş,
ışıldama, bulutsu kayması, fare kayması, radar, sonda, iniş halkaları ve panel geçiş canlandırmaları
çizilmez; seçili yıldız ve sonuç takımyıldızı durağan işaretlerle gösterilir; kamera kayması anında
olur; soru akışı radar turunu beklemez; pusula dönmez (Decision 8).

Requirement 9: [question-analysis](../004-question-analysis/PRD.md) soruyu göndermeden önce metni bu
yeteneğin ad eşleme işlevine verir. Metin boşluk içermiyorsa ve Türkçe büyük/küçük harf duyarsız (ı ile
i eşit sayılarak) tam olarak bir tablonun adına (`vCustomerInfo`), `Şema.ad`'ına ya da tam anahtarına
(`DB.Şema.Obje`) eşitse soru sorulmaz, analiz kaydı oluşmaz, o tablonun dosyası açılır ve metin çubukta
kalır. Birden çok tablo eşleşirse (iki şemadaki `vCampaign`) ya da hiçbiri eşleşmezse metin soru olarak
sorulur. Eşleme Evren verisi üzerinde tarayıcıda yapılır; harita yüklenemediyse eşleme yapılmaz.

Requirement 10: `POST /explorer/table-searches` gövdesi `{"query": "…"}`'dır; baştaki ve sondaki boşluk
atıldıktan sonra metin en çok 4.000 karakterdir (soru sınırıyla aynı), fazlası 422 `query_too_long`
"Arama metni çok uzun (en fazla 4000 karakter)." alır. Yanıt kaynaktaki `App.objects` kuralıdır:
- Boş metin: göz atma; ad sırasındaki ilk 60 tablo, `match` `""`, `counts` ve `concepts` boş.
- Ad katmanı: Türkçe katlanmış (`fold`; Türkçe küçük harf ve aksansız) metin, tablonun anahtarı ve grup
  adlarının katlanmış hâlinde geçiyorsa `match` `ad`.
- İçerik katmanı: katlanmış metin en az 3 karakterse motorun model kullanmayan kural sıralaması
  (`rank_objects`: Türkçe normalleştirme, terim sözlüğü, sözlükteki eş anlamlılar, BM25 kelime araması
  — kelime sıklığına dayalı arama — ve tabloya toplama) en çok 25 tablo verir; ad katmanında olmayanlar `match` `içerik` olur; bu tabloların
  hepsine `score`, `level` (Yüksek, Orta, Düşük), `matched` (en çok 5 kolon adı), `covered`, `missing` ve
  `signal` (ilk sinyal) eklenir; yanıtın `concepts` alanı metinde okunan kavramlardır.
- Kolon adı katmanı: öteki katmanlarda olmayan ve bir kolon adının katlanmış hâlinde metin geçen tablo
  `match` `kolon adı` ve `matched` (en çok 5 kolon adı) alır.
- Sıra önce `ad`, sonra `içerik`, sonra `kolon adı`; katman içinde skor büyükten küçüğe, sonra ad; en çok
  60 tablo. `counts` katman başına sonuç sayısı, `elapsed_ms` süredir. Her öğe `key`, `name`, `schema`,
  `columns`, `groups` taşır.

Arama analiz kilidini almaz. İşlemciyi yoran içerik katmanı, isteklere cevap veren ana döngüyü ve canlı
olay akışlarını (SSE: sunucudan tarayıcıya sürekli olay gönderen bağlantı) bekletmemek için ayrı bir iş
parçacığında (arka planda paralel çalışan kod yolunda) çalışır.

Requirement 11: `GET /explorer/tables/{table_key}` `key`, `name`, `schema` (`DB.Şema`), `groups`
(kolonların veri seti gruplarının sıralı listesi), `columns` ve `join_keys` döner. `columns` sözlükteki
sırayla her kolon için `key`, `column`, `object`, `description`, `synonyms` (ayrıştırılmış liste), `pii`
(KVKK işareti) ve `group` taşır; görünüm ayrıştırılmıştır (yinelenen ve eksik alanlı satırlar yoktur).
`join_keys` kaynaktaki `key_columns` kuralıdır: adı Türkçe katlanmış hâliyle `accountnumber`,
`customerid`, `customernumber`, `customerpartyid`, `partyid` olan kolonlar bu sırayla, ardından varsa
`Period`, yoksa `DataDate` kolonu. Tablo hizmetteki indekste yoksa 404 `table_not_found`.

Requirement 12: Tablo dosyasının içeriği:
- Üst kısım: küme tonunda gezegen simgesi; küçük başlıkta grup adı (yıldızı yoksa "Tablo"; ayrıntı
  gelince tablonun grupları " · " ile); tablo adı (uzun adlar yalnız büyük harf geçişlerinde ve alt
  çizgiden sonra satır kırar); tam anahtar ve "Kopyala" düğmesi ("Tam adı kopyala"; anahtarı panoya
  yazar, 1,4 saniye boyunca "Kopyalandı ✓" ya da "Kopyalanamadı" der); "Kapat (Esc)" düğmesi.
- Sayılar: "kolon", "anahtar" (birleştirme anahtarı) ve "KVKK" (Türkçe sayı biçiminde; sıfır olan
  soluk).
- Kolon araması: "Kolon, açıklama, eş anlamlı ara…" (erişilebilir adı "Kolonlarda ara"); kolon adı,
  açıklama ve eş anlamlılarda Türkçe harf duyarsız arar ("İŞLEM", "işlem" ve "islem" eşleşir); eşleşen
  yerler vurgulanır; sağdaki sayı "N" ya da "M / N".
- Süzgeçler: "Tümü · N", "Anahtar · n", "KVKK · n"; sayısı sıfır olan süzgeç devre dışıdır; seçili
  süzgeç basılı görünür ve erişilebilir durumu "basılı"dır.
- Kolon satırları sözlükteki sırayla: kolon adı, birleştirme anahtarıysa "ANAHTAR" rozeti (ipucu "Diğer
  tablolarla birleştirme anahtarı"), KVKK işaretliyse "KVKK" rozeti (ipucu "Kişisel veri (KVKK)") ve iki
  satıra kısaltılmış açıklama ya da "Açıklama yok". Rozetler yazılıdır; bilgi yalnız renkle verilmez.
  Satır açılınca açıklamanın tamamı ve "Eş anlamlılar" listesi görünür; eş anlamlı yoksa ve açıklama
  140 karakterden kısaysa "Ek not yok" yazar. Metin seçilirken tıklama satırı açıp kapatmaz.
- Durumlar: yüklenirken beş yer tutucu (iskelet) satır; uyan kolon yoksa "Bu filtreye uyan kolon
  yok."; hata olursa "Tablo yüklenemedi: <ileti>" (`table_not_found` için ileti "Kayıt bulunamadı").
- Alt kısım: "Aynı kümede · <N> tablo" ve kolon sayısına göre en büyük 14 komşu tablo düğmesi (ad ve
  kolon sayısı; ipucu "<şema> · <N> kolon"); tıklanınca o tablonun dosyası açılır. Komşu yoksa alt kısım
  gizlenir.
- Yeni bir tablo açılınca önceki tablonun geç gelen cevabı gösterilmez; arama kutusu boşalır ve süzgeç
  "Tümü"ye döner.

Requirement 13: Tablo dosyasının etkileşimi:
- Dosya sağdan açılan ve arkadaki sayfayı kilitleyen bir çekmecedir (paylaşılan bileşen; ekran
  okuyucuya iletişim kutusu olduğunu bildiren `dialog` rolü ve tablo adından oluşan erişilebilir ad
  taşır; Decision 6). Açılınca klavye odağı "Kapat" düğmesine gider; Tab ile odak panelin içinde kalır;
  Esc kapatır; "/" kolon aramasına gider; kapanınca odak dosyayı açan öğeye döner.
- Dosya açıkken ana içerik soluklaşır ve bulanıklaşır, harita tam parlaklığa döner, sol alttaki bilgi
  satırı gizlenir. Açık dosyada başka bir yıldıza ya da komşu tablo düğmesine tıklama dosyayı o tabloya
  geçirir.
- Geniş ekranda panel en çok 540 piksel genişliğindedir; 760 pikselden dar ekranda ekranın tamamını
  kaplar.
- Kolon satırının açma eylemi yerel bir düğmedir (Decision 7); açık ya da kapalı olduğu erişilebilir
  durum olarak bildirilir.

Requirement 14: Ana ekrandaki her yetenek tablo dosyasını tek bir paylaşılan işlevle açar ve kapatır
(`open(key)`, `close()`, açık mı bilgisi). Kullananlar: yıldız tıklaması, tablo adıyla açma
(Requirement 9), komşu tablo düğmeleri, cevap kartındaki "Kolonlar"
düğmesi ve cevap metnindeki önerilmemiş tablo adları ([question-analysis](../004-question-analysis/PRD.md)),
kullanıcıların doğruladığı tablolar ([answer-feedback](../006-answer-feedback/PRD.md)). Yıldızı olmayan
bir tablo da açılabilir (küçük başlık "Tablo", varsayılan ton, komşu yok). Yolculuk işlevleri (başlat,
adayları ver, sonuçları göster, bitir ve radar süresi) aynı paylaşılan bağlamdan verilir.

Requirement 15: Klavye erişimi görünümü değiştirmeden sağlanır (Decision 4); görünür yeni öğe eklenmez:
- Ana ekrandaki bütün etkileşimli öğeler (marka, soru çubuğu, düğmeler, cevaptaki tablo düğmeleri,
  tablo dosyasının denetimleri, kolon satırları, komşu tablo düğmeleri) klavyeyle odaklanır ve Enter
  ya da Boşluk ile çalışır.
- Klavye odağı yalnız klavyeyle gezinirken görünen bir odak halkasıyla gösterilir (`:focus-visible`;
  kaynağın yönetim ekranındaki `2px` vurgu rengi halka); fareyle kullanımda görünüm değişmez.
- Haritadaki tablolara klavyeyle var olan yollardan ulaşılır: soru çubuğuna tablo adını yazmak
  (Requirement 9), cevap kartındaki "Kolonlar" ve tablo düğmeleri, kullanıcıların doğruladığı
  tablolar ve tablo dosyasındaki komşu tablo düğmeleri. Tablo dosyası kapanınca odak dosyayı açan
  öğeye döner.

Requirement 16: Durum yanıtındaki `dictionary_version`, yüklenmiş Evren verisininkinden farklıysa
(sözlük içe aktarıldı ya da indeks yeniden kuruldu) Evren verisi yeniden yüklenir
ve harita yeni tablolarla kurulur; açık tablo dosyası açık kalır (yeni; kaynakta harita sayfa
yenilenene kadar eski kalıyordu).

Requirement 17: Ana ekranın görünümü kaynaktaki `index.html` CSS'iyle birebir aynıdır. Kaynak CSS'in
bütün değerleri (renkler, yazı tipleri, yazı boyutları, aralıklar, gölgeler, yarıçaplar,
canlandırmalar, kırılma noktaları) `app/frontend/src/globals.css` içinde merkezi belirteçler (CSS
değişkenleri; gökyüzü yüzeyi, yüzey, çizgi, yazı, soluk yazı, vurgu, Yüksek/Orta/Düşük, KVKK gibi
adlarla) olarak tanımlanır; bileşenler sabit renk yazmaz, belirteçleri kullanır. DOM düzeni ve sınıf
adları mümkün olduğunca kaynaktaki gibidir; iskeletin kendi varsayılan görünümü (ör. `HomePage`)
kullanılmaz. Küme tonu Requirement 4'teki hesapla bulunur ve belirteçteki doygunluk ve açıklık
değerleriyle uygulanır. Yazı tipleri sistem yazı tipleridir; dışarıdan yazı tipi ya da başka kaynak
yüklenmez. Yönetim ekranı aynı belirteçleri kullanır
([search-settings](../009-search-settings/PRD.md)); gerekçe bu PRD'nin Decision 5'idir. Dinamik
görsel değerler (küme tonu, konum, parlaklık) çizim alanında (canvas) ya da tarayıcının stil nesnesi
(CSSOM) ve SVG öznitelikleriyle verilir; çalışırken `<style>` öğesi ekleyen bileşen kullanılmaz
(sayfa CSP'si `style-src 'self'`:
[user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 14,
Decision 13).

Requirement 18: Kullanıcıya görünen bütün metinler `app/frontend/src/locales/tr.json` kataloğundadır
ve kaynaktaki Türkçe metinlerle aynıdır (Mevcut davranışta ve Requirement 1–15'te tırnak içinde
verilenler). Yeni metinler yalnız Requirement 2'deki sözlük uyarısı ve oturum alanının metinleridir
([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)). "Diğer" küme adı
backend'den veri olarak gelir ve katalogda değildir.

Requirement 19: Hizmette indeks yokken (açılış sırasında) Evren, tablo arama ve tablo ayrıntısı
uçları 503 `search_index_not_ready` döner (hazırlığın tanımı
[search-settings](../009-search-settings/PRD.md) PRD'sindedir); durum ucu 200 ile 0 kolon ve 0 tablo
döner (question-analysis Requirement 17). Ön yüz 503'te haritasız çalışır ve bir sonraki durum
yoklamasında Evren verisini yeniden dener.

## API sözleşmesi

Bütün uçlar `/api/dwhnavigator/v1` altındadır, geçerli oturum ve `kullanici` ya da `yonetici` rolü
ister. Hata gövdesi tek hata zarfıdır: `{"detail":{"code":"...","message":"..."}}`; istek kimliği
`x-request-id` başlığıyla döner. OpenAPI dosyası (API tanım dosyası) `specs/openapi/dwhnavigator-api.yaml`
ve üretilmiş ön yüz tipleri aynı değişiklikte güncellenir.

| Yöntem ve yol | Rol | İstek özü | Başarı | Hatalar |
|---|---|---|---|---|
| `GET /explorer/galaxy` | `kullanici`, `yonetici` | — | 200: `items[]` (`key`, `name`, `schema`, `group`, `columns`), `total` | 401, 403, 503 `search_index_not_ready` |
| `POST /explorer/table-searches` | `kullanici`, `yonetici` | `{"query": "…"}` (0–4.000 karakter) | 200: `query`, `items[]` (`key`, `name`, `schema`, `columns`, `groups`, `match`; katmana göre `score`, `level`, `matched`, `covered`, `missing`, `signal`), `counts`, `concepts[]`, `elapsed_ms`; hiçbir şey saklanmaz | 401, 403, 422 `query_too_long`, 503 `search_index_not_ready` |
| `GET /explorer/tables/{table_key}` | `kullanici`, `yonetici` | anahtar yüzde kodlamalı (adreste güvenle taşınacak biçimde kodlanmış); `/` içeren anahtar da desteklenir | 200: `key`, `name`, `schema`, `groups[]`, `columns[]` (`key`, `column`, `object`, `description`, `synonyms[]`, `pii`, `group`), `join_keys[]` | 401, 403, 404 `table_not_found`, 503 `search_index_not_ready` |

Ortak hatalar 401 `not_authenticated` ve 403 `forbidden`'dır. `match` değerleri (`""`, `ad`, `içerik`,
`kolon adı`) ve `level` değerleri (`Yüksek`, `Orta`, `Düşük`) kaynaktaki makine değerleridir ve
değişmez. Kaynaktaki karşılıklar: `GET /api/galaxy`, `GET /api/objects?q=`, `GET /api/object/<anahtar>`.
Durum göstergesinin okuduğu `GET /status` (kaynak `GET /api/status`) bu PRD'nin ucu değildir; alanları
[question-analysis](../004-question-analysis/PRD.md) Requirement 17'dedir.

## Güvenlik ve yetkilendirme

- Kimlik ve rol [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) ile
  gelir; rol denetimi backend'de, her uçta yapılır. Ön yüzde bir öğeyi gizlemek yetki denetimi değildir.
- Ana ekran sözlüğün ayrıştırılmış hâlini (tablo ve kolon adları, açıklamalar, eş anlamlılar, KVKK
  işaretleri) giriş yapmış her kullanıcıya gösterir; bu, alanın amacıdır (kullanıcı sözlükte tablo ve
  kolon gezer). KVKK işareti kolonun kişisel veri içerebileceğini söyler; kişisel verinin kendisi
  sözlükte yoktur.
- Soru ve arama metni istek gövdesinde taşınır; adres satırına, uygulama loguna ve giriş katmanının
  erişim loguna girmez (Decision 9). Tablo anahtarı tablo ayrıntısı adresinde taşınır; uygulamanın HTTP
  logu yalnız yol şablonunu (`/explorer/tables/{table_key}`) yazar, giriş katmanının erişim logu tam
  adresi yazabilir. Tablo adları kişisel veri değildir; bu durum kabul edilmiştir.
- Açıklamalar ve adlar her zaman düz metin olarak gösterilir; vurgulama metin parçalarından kurulur, ham
  HTML hiçbir yerde eklenmez.
- Durum bilgisindeki model sebebi model sunucusunun adresini, anahtarını ve hata gövdesini taşımaz
  ([llm-connection](../003-llm-connection/PRD.md)).
- "Kopyala" yalnız tablonun anahtarını panoya yazar. Bu yetenek tarayıcı deposuna bir şey yazmaz.

## Veri ve geçiş

- Bu yeteneğin veritabanı tablosu ve göçü yoktur. Uçlar hizmetteki arama indeksinden okur; indeks
  [dictionary-management](../001-dictionary-management/PRD.md) PRD'sinin okuma işleviyle, etkin sözlük
  sürümünden [search-settings](../009-search-settings/PRD.md) PRD'sine göre kurulur.
- Kaynaktan taşınacak veri yoktur. Tarayıcı deposunda veri tutulmaz.

## Gözlemlenebilirlik

Ortak kurallar [application-foundation alanında](../../../application-foundation/DOMAIN.md) yazılıdır:
etiket değerleri sabit kümelerdir, kümede olmayan değer `other` yazılır; soru ve arama metni, tablo ve
kolon adı hiçbir log olayına, ölçüme ve iz aralığına girmez.

- **Log olayı:** `explorer.search` (`mode`: `browse`, `name_only`, `full`; metnin karakter sayısı; katman
  başına sonuç sayısı; `elapsed_ms`). Öteki uçlar için standart HTTP tamamlanma logu (yol şablonu, durum,
  süre) yeterlidir.
- **Ölçümler:** `dwhnavigator_explorer_requests_total{endpoint,outcome}` (sayaç; `endpoint`: `galaxy`,
  `search`, `table`; `outcome`: `ok`, `not_found`, `not_ready`, `invalid`, `error`) ve
  `dwhnavigator_explorer_search_duration_seconds{mode}` (süre dağılımı; `mode` yukarıdaki üç değer).
- **İz (trace):** her tablo araması için içerik taşımayan bir `explorer search` aralığı; öznitelikleri
  `mode` ve sonuç sayısıdır.
- Ön yüz telemetri göndermez. Tüketen test: `app/backend/tests/unit/test_explorer_telemetry.py` (adlar,
  etiket kümeleri ve içerik sızmaması).

## Dağıtım etkisi

- Yeni çalışma zamanı bağımlılığı yoktur: harita tarayıcının kendi çizim alanıyla (canvas) çizilir,
  çizim kütüphanesi eklenmez. Harita bileşeni ön yüz paketinde ayrı ve gecikmeli yüklenen bir parçadır.
- Yeni sır, ağ çıkışı, ortam değişkeni ve chart değişikliği yoktur. Dışarıdan yazı tipi, betik ya da
  stil yüklenmez (kapalı ağ).
- Tablo araması gövdeyle gittiği için giriş katmanında adres uzunluğu ayarı gerekmez.

## Test stratejisi

- **Backend birim ve tümleştirme (örnek sözlükle):** test sözlüğünde iki grup, grubu olmayan bir
  tablo, iki şemada aynı adlı tablo, KVKK işaretli kolon ve birleştirme anahtarları
  (`CustomerPartyId`, `Period`, `DataDate`) bulunur. Tablo arama: "limit" yalnız ad katmanı,
  "doluluk oranı" ilk sırada içerik katmanı ve eşleşen kolon, "PartyId" kolon adı ya da içerik
  katmanı, boş metin göz atma (ilk 60), 3 karakterden kısa metin yalnız ad katmanı, 4.001 karakter
  422; analiz kilidi tutulurken aramanın cevap vermesi; içerik katmanının ana döngüyü bekletmediği
  (arama sürerken başka bir isteğin gecikmeden cevaplanması). Evren verisi: grup kuralı ve "Diğer",
  sıra, boş sözlük. Tablo ayrıntısı: alanlar, grup listesi, birleştirme anahtarı sırası, 404. Durum
  ucunun testleri question-analysis'tedir. Roller: oturumsuz 401, rolsüz 403, `kullanici` ve
  `yonetici` 200. İndeks hazır değilken 503.
- **Fark testleri:** kaynak `76e21a3` paketi test ortamında yan yana kurulur (düzenek
  [question-analysis](../004-question-analysis/PRD.md) PRD'sinindir); aynı sözlük, kelime listeleri
  ve ayarlarla altın setteki sorular, tablo adları ve kolon adı parçalarından oluşan bir sorgu
  kümesi için tablo arama, Evren verisi ve tablo ayrıntısı yanıtları kaynaktaki `App.objects`,
  `App.galaxy` ve `App.object_detail` çıktılarıyla `elapsed_ms` dışında aynıdır.
- **Ön yüz (Vitest, ön yüz test aracı):** yerleşim işlevinin aynı girdide aynı çıktıyı vermesi, küme
  sırası ve tonu; 14 piksel yakınlık seçimi; ad eşleme (büyük/küçük harf, ı/i, `Şema.ad`, tam
  anahtar, `vCampaign` belirsizliği, boşluklu metin); durum hapının dört durumu, önceliği, ipucu ve
  "Sunucuya ulaşılamadı"; tablo dosyası: sayılar, sıfırda devre dışı süzgeç, Türkçe harf duyarsız
  arama ve vurgulama, Enter ve Space ile satır açma, "Ek not yok" kuralı, en çok 14 komşu ve sırası,
  kopyalama bildirimi, geç gelen cevabın gösterilmemesi, odak tuzağı ve geri dönüşü, Esc ve "/";
  klavye erişimi: etkileşimli öğelerin odaklanması, Enter ve Boşluk, odak halkasının yalnız klavye
  odağında görünmesi, cevaptaki tablo düğmesinden dosya açma ve odak geri dönüşü; hareket azaltmada
  çizim döngüsünün durağan olması ve radar beklemesinin olmaması; sürüm değişince Evren verisinin
  yeniden yüklenmesi; bileşen dosyalarında sabit renk bulunmaması. Harita çizimi piksel piksel test
  edilmez; ekran görüntüsü yalnız görsel özellikler için kullanılır (kural 14).
- **Görsel eşdeğerlik:** kaynak `76e21a3` ve hedef aynı sözlükle yan yana çalıştırılır; aynı ekran
  boyutlarında (masaüstü 1440×900 ve telefon genişliği 390×844 piksel) açılış görünümü, yolculuk,
  cevap görünümü, tablo dosyası, liste görünümü ve oy alanının ekran görüntüleri yan yana
  karşılaştırılır (Acceptance 5).
- **Uçtan uca (tarayıcı, `e2e/data-dictionary/`):** Kabul kriterlerindeki L2 senaryoları; yıldız
  tıklaması birim testte, tablo açmanın klavye yolu uçtan uca testte doğrulanır.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

Kaynak vektör aramasını ADR-039 ile kaldırdı; bu PRD vektör veya gömme (embedding) kullanmaz.

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 3, 10, 11 ve 19'un backend testleri,
  rol denetimi ve kaynak paketle fark testleri geçer; tablo arama, Evren verisi ve tablo ayrıntısı
  yanıtları kaynakla `elapsed_ms` dışında aynıdır; analiz kilidi tutulurken arama cevap verir; telemetri
  testinde soru metni ve tablo adı log, ölçüm ve izde bulunmaz; tam kalite kapısı geçer.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 1, 2, 4–9 ve 12–18'in Vitest
  testleri geçer; OpenAPI dosyası ve üretilmiş ön yüz tipleri günceldir; katalogdaki anahtarlar
  kodla eşleşir.
- [ ] Acceptance 3: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da (geliştirici
  makinesinde konteynerleri birlikte çalıştıran düzen) örnek sözlükle `kullanici` olarak giriş
  yapılır; sol alttaki bilgi satırındaki tablo ve küme sayısı Evren verisiyle tutar; yalnız
  klavyeyle soru çubuğuna tek eşleşen bir tablo adı yazılınca dosya açılır ve analiz kaydı oluşmaz,
  kolon araması ve süzgeçler çalışır, odak halkası yalnız klavye odağında görünür, Esc sonrası odak
  soru çubuğuna döner; iki şemadaki ad yazılınca soru sorulur; bir soruda yolculuk ve sonuç
  takımyıldızı görünür (ekran görüntüsüyle); "hareketi azalt" öykünmesinde harita durağandır ve
  kayıtlı cevap beklemeden görünür; başka bir oturumda sözlük içe aktarılınca harita 60 saniye
  içinde yeni tablolarla kurulur; `yonetici` ve `kullanici` olarak ana ekranda yönetim bağlantısı
  görünmez (Requirement 1, 2, 7–9, 12–16).
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı (nonprod): gerçek sözlükle harita 390 yıldızı
  çizer; tablo arama yanıtı ölçülür ve 1 saniyenin altındadır; model kapatıldığında durum hapı
  "Modele ulaşılamıyor" der ve sebepte adres görünmez (Requirement 2, 5, 10). Küme dağıtımı bu kanıtın
  parçası değildir ve ayrı kullanıcı talimatı ister.
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı sözlükle çalıştırılır; masaüstü (1440×900) ve telefon genişliğinde
  (390×844 piksel) açılış görünümü, yolculuk, cevap görünümü, tablo dosyası, liste görünümü ve oy
  alanının ekran görüntüleri yan yana karşılaştırılır. Fark yalnız fabrikanın zorunlu kıldığı oturum
  alanında kabul edilir; renk, yazı, aralık, gölge, canlandırma ve yerleşimde başka fark bulunmaz
  (Requirement 1, 15, 17, Decision 3).

## Kararlar

Decision 4: Kural 32 yerel olmayan tıklanabilir öğe için rol, odak ve Enter/Space ister; çizim
alanındaki yıldızlar yalnız fareyle seçilir. Görünür yeni öğe eklenmez: çizim alanı süsleyici kalır
(ekran okuyucudan gizli) ve tablolara klavyeyle var olan yollardan ulaşılır — soru çubuğuna tablo
adını yazmak, cevaptaki ve tablo dosyasındaki tablo düğmeleri. Bütün etkileşimli öğeler odaklanır ve
odak halkası yalnız klavye odağında görünür (Requirement 15). Yıldızlar arasında ok tuşlarıyla
gezinme seçilmedi: 390 yıldızda uzamsal gezinme ekran okuyucu için kullanışsızdır.

Decision 5: Kural 32 anlamsal belirteç ister; kaynakta "Evren" paleti bileşen CSS'inde sabit
renklerdi. Kaynak CSS'in değerleri `globals.css`'e merkezi belirteçler (CSS değişkenleri) olarak
taşınır ve ana ekran ile yönetim ekranı aynı belirteçleri kullanır; kuralın isteği böyle karşılanır
ve görünüm değişmez. Küme tonu verinin kendisinden hesaplandığı için belirteç değil hesaptır,
doygunluk ve açıklığı belirteçtir.

Decision 6: Kural 32 paylaşılan kalıplar ister; tablo dosyası paylaşılan çekmece davranışıyla (odak
tuzağı, Esc, odağın geri dönüşü) kurulur ve arkadaki sayfayı kilitler (odak panelde kalır); görünümü
kaynaktaki panelin CSS değerleriyle aynıdır. Kaynakta panel `role="dialog"` taşıyordu ama odak
panelden çıkabiliyordu; arkadaki sayfa soluklaştırıldığı için panel davranışça zaten kilitliydi.

Decision 7: Kural 32 mümkünse yerel düğme ister; kolon satırlarındaki açma eylemi `div` yerine yerel
düğmedir. Görünüm değişmez.

Decision 8: Hareket azaltma tercihi tam uygulanır (Requirement 8); kaynakta yalnız CSS canlandırmaları
duruyordu, çizim alanı hareket etmeye ve soru akışı radar turunu beklemeye devam ediyordu. Bu bir
erişilebilirlik düzeltmesidir; tercihi açık olmayan kullanıcı için görünüm değişmez.

Decision 9: Tablo araması `POST /explorer/table-searches` gövdesiyle yapılır (kaynakta `GET
/api/objects?q=`). Gerekçe: yolculuk bu aramayı kullanıcının soru metniyle çağırır; adres satırındaki
metin giriş katmanının erişim loguna yazılır ve 4.000 karakterlik Türkçe bir soru adres uzunluğu
sınırlarını aşabilir. Arama hiçbir şey saklamaz; tekrarlanması aynı sonucu verir.

Decision 10: Sözlük boşken durum hapı "Sözlük yok" der (yeni). Kaynakta model bağlıysa hap "Hazır"
diyordu ve soru ancak sorulunca "Sözlük henüz içe aktarılmadı" cevabını alıyordu; ilk kurulumda
kullanıcı yanıltılmamalıdır. Öncelik ilk kurulum sırasını izler: sözlük, model, soru.

Decision 11: Evren verisi sayfalanmaz; harita bütün tabloları birlikte çizer. Yanıtın büyüklüğünü
sözlüğün tablo sayısı sınırlar (bugün 390); yanıt `total` taşır.

Decision 12: Yolculuk kaynaktaki gibi bir canlandırmadır; analistin gerçek adımlarını değil, model
kullanmayan tablo aramasının adaylarını gösterir. Gerçek ilerleme
[question-analysis](../004-question-analysis/PRD.md) PRD'sindeki canlı olay akışındadır. Hızlı gelen bir
cevabın radar turunu beklemesi kaynak tasarımıdır ve korunur; hareket azaltmada bekleme yoktur.

Decision 13: Ön yüz durum yanıtındaki `dictionary_version`'ı
([question-analysis](../004-question-analysis/PRD.md) Requirement 17) haritayı yenilemek için okur
(Requirement 16). Kaynakta bu bilgi `version` adıyla vardı ve ekranın okumadığı bir alan olarak
`4e829a7` commit'inde kaldırıldı (ADR-053).

Decision 14: Tablolar `DB.Şema.Obje` anahtarıyla adreslenir; anahtar sürümler arasında kararlıdır ve
[dictionary-management](../001-dictionary-management/PRD.md) ile aynı adresleme kullanılır. Ana ekranda
tablo dosyası için derin bağlantı (doğrudan o tabloyu açan adres) yoktur; kaynakta da yoktu.

Decision 15: Ana ekranda yönetim ekranına bağlantı yoktur (kaynakla aynı, ADR-047); yönetici yönetim
ekranını adresini (`/admin`) yazarak açar. Yetki her istekte backend'de rolle denetlenir;
bağlantının olmaması güvenlik önlemi değil, kaynak tasarımıdır.

Decision 16: Haritanın sürekli hareketini durduran bir düğme yoktur (kaynakla aynı); işletim
sisteminin "hareketi azalt" tercihine uyulur (Requirement 8). Gerekçe: görünür yeni öğe eklenmez.

Decision 17: Koyu "Evren" paleti uygulamanın tek temasıdır. Fabrikanın zorunlu kıldığı yeni ekranlar
(giriş, parola değiştirme, süper yöneticinin Kullanıcılar sayfası) kaynağın aynı belirteçleri ve
bileşen görünümüyle yapılır; bu ekranların sahibi
[user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) PRD'sidir.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Düşük donanım:** Kurum bilgisayarlarında ya da sanal masaüstünde grafik hızlandırma zayıfsa
  sürekli çizim işlemciyi yorar. Kare sınırı, sekme gizliyken durma ve hareket azaltma etkiyi
  sınırlar; gerçek cihazda ölçülmemiştir.
- **Hareketi durduracak denetim yok:** Gökyüzü sürekli ve kendiliğinden hareket eder; işletim
  sisteminin "hareketi azalt" tercihini bilmeyen kullanıcının hareketi durduracak bir denetimi
  yoktur (kaynakla aynı, Decision 16). Erişilebilirlik ölçütlerindeki "duraklat, durdur, gizle"
  maddesi yalnız bu tercihle karşılanır.
- **Klavyeyle tablo bulma:** Haritadaki tablolara klavyeyle ulaşmak tablonun adını bilmeyi ya da
  soru sormayı gerektirir; görünür bir tablo listesi yoktur (Decision 4).
- **Radar beklemesi:** Kayıtlı cevap anında dönse de ekran yaklaşık 5,2 saniye bekler; kullanıcılar bunu
  yavaşlık sanabilir (kaynak tasarımı, Decision 12).
- **Ad eşleme:** Soru çubuğuna yalnız bir tablo adı yazan kullanıcı analiz yerine tablo dosyasını görür;
  o tablo hakkında soru sormak için birden çok kelime yazmalıdır (kaynak davranışı).
- **Sözlüğün büyümesi:** Harita bütün tabloları birlikte çizer; tablo sayısı birkaç bine çıkarsa çizim ve
  Evren verisi ağırlaşır; bugün 390 tablo vardır.
- **Ana döngünün tıkanması:** İçerik katmanı ayrı iş parçacığında çalışmazsa her arama canlı olay
  akışlarını ve öteki istekleri yaklaşık 100 milisaniye bekletir; Requirement 10'daki test bunu yakalar.
- **Görsel sadakat:** Belirteçlere ve React'e geçişte renk, yoğunluk ve yerleşim kaynaktan
  kayabilir; kabul, kaynak ve hedefin ekran görüntülerinin yan yana karşılaştırılmasıyla verilir
  (Acceptance 5).
- **Fark testlerinin kapsamı:** Tablo aramasının içerik katmanı çekirdek motora bağlıdır; motorda
  bayt bayt eşitlik bozulursa arama sonuçları da kaynaktan ayrışır.
