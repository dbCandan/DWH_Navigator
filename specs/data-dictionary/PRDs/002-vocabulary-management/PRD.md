# PRD — vocabulary-management

Status: Accepted

Version: 1.0.0

Acceptance date: 2026-10-08

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

Yönetici **terim sözlüğünü** (kurumsal eş anlamlı grupları; “kredi” arayan “fon kullandırım”ı da
bulsun diye) ve **durak kelimeleri** (talep cümlesinde aramada yok sayılan dolgu kelimeleri: “ve”,
“hangi”, “bilgisi”) yönetim ekranının **Kelimeler** sayfasından ya da Excel ile düzenler. Kaydedilen
liste kaynaktaki kurallarla denetlenir, veritabanına (PostgreSQL) bütün olarak yazılır ve arama
indeksine hemen yansır: kaydın yanıtı geldikten sonra başlayan her analiz yeni listeyi kullanır. Yeni
bir kurulumda iki liste depodaki başlangıç listelerinden bir kez yüklenir; sonra yalnız yönetici
değiştirir.

## Aktörler ve sonuçlar

- **Yönetici** (`yonetici`): İki listeyi görür; terim grubu ekler, düzenler, siler; durak kelime ve
  grup ekler, çıkarır; her listeyi ayrı kaydeder, Excel'e aktarır ve Excel'den içe aktarır. Sonuç:
  kaydın yanıtı geldikten sonra başlayan her analiz yeni listeyi kullanır; kurallara uymayan liste
  hiçbir satırı değiştirmeden, sorunlu satırı ya da terimi adlandıran Türkçe iletiyle reddedilir;
  Excel'e aktarılıp değiştirilmeden geri yüklenen liste “değişiklik yok” sonucunu verir ve indeksi
  yeniden kurdurmaz.
- **Kullanıcı** (`kullanici`): Listeleri görmez ve değiştiremez. Sorusu, analizi başladığı anda
  geçerli olan listelerle cevaplanır; listeler değişince eski kayıtlı cevaplar ona yeniden verilmez
  ([question-analysis](../004-question-analysis/PRD.md)).
- **İşletim ekibi**: Yeni kurulumda başlangıç listelerinin göçle (veritabanı yapısını ve verisini
  sürüm sürüm kuran betik) bir kez yüklendiğini göç işinin olay kaydından görür; liste içeriğini
  logda görmez.
- **Geliştirici**: Başlangıç listelerini depoda tutar. Kurulu bir sistemin listesini kodla değil,
  yönetim ekranından ya da Excel ile değiştirir.
- [search-settings](../009-search-settings/PRD.md): Liste değişikliğini arama indeksine taşıyan
  değişiklik sırasını, indeks durumunu ve Kelimeler sayfasının takıldığı yönetim ekranı kabuğunu
  (kenar çubuğu, çekmece, bildirimler, çıkış onayı) sağlar.

## Değişmezler ve sınırlar

- İki liste vardır: **terim sözlüğü** (`terms`) ve **durak kelimeler** (`stopwords`). Bir liste her
  zaman bütün olarak değiştirilir; tek öğe güncelleyen uç yoktur.
- Ekrandan kaydetme ve Excel'den içe aktarma aynı denetimden geçer (Requirement 3 ve 4). Denetimden
  geçmeyen liste hiçbir satırı değiştirmez.
- Aynı terim ve aynı durak kelime kararı yalnız uygulamanın Türkçe normalleştirme yardımcısıyla
  (`fold`: büyük/küçük harfi ve Türkçe harfleri tek biçime indirir; “İŞLEM”, “işlem” ve “islem” aynı
  sayılır) verilir.
- Bir liste değişikliği ya yeni arama indeksiyle birlikte hizmete girer ya da hiç yazılmaz
  ([search-settings](../009-search-settings/PRD.md) değişiklik sırası).
- Başlangıç listeleri her veritabanında bir kez yüklenir; sonraki sürümler, açılışlar ve göçler kurulu
  listelere dokunmaz. Yönetici bir listeyi boşaltsa bile başlangıç listesi geri gelmez.
- Liste içeriği (terim, eşdeğer, alan, not, kelime, grup adı) uygulama loguna, ölçüme ve ize girmez;
  yalnız sayılar ve hata kodları girer.
- Sahip olunan veri: iki listenin satırları (güncel satırlar ve yazılımsal silinmiş, yani silindi
  olarak işaretlenip tabloda kalan eski satırlar) ve her listenin başlık kaydı (revizyon, içerik özeti). Arama indeksinin kurulması, durumu ve yönetim
  ekranı kabuğu [search-settings](../009-search-settings/PRD.md); kayıtlı cevaplar ve parmak izinin
  (cevabın hangi sözlük, liste, model ve ayarlarla yazıldığını gösteren özet) kullanımı
  [question-analysis](../004-question-analysis/PRD.md); giriş ve roller
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) PRD'sindedir.

Decision 1: Liste sırası korunur ve anlamlıdır: terim genişletme grupları sırayla okur, kayıtlı cevap
parmak izi terim listesini sırasıyla içerir. Ekran yeni terimi listenin başına, yeni durak kelimeyi
grubunun sonuna ekler (kaynakla aynı).

Decision 2: Motorun (kural motoru ve arama yapılarının bellekteki kopyası) okuduğu biçim kaynakla
aynıdır: terim grupları sırasıyla `TermGroup(term, equivalents, domain, note)`; durak kelimeler
çekirdeğin `load_stopwords` işlevinden geçmiş, katlanmış ve kökü alınmış biçimlerin kümesi (ör.
`bilgilerini` girdisi hem `bilgilerini` hem `bilgi` biçimini taşır). Aynı listeler için motorun
gördüğü değerler kaynak `76e21a3` ile bayt bayt aynıdır.

## Mevcut davranış

Kaynak uygulama (bu deponun geçmişindeki `76e21a3`) bugün şöyle çalışır; hedefteki değişiklik her
maddede yazılıdır.

- **Depolama** (ADR-052): Terim sözlüğü `data/terms.jsonl` (satır başına bir grup: `term`,
  `equivalents` listesi, `domain`, `note`), durak kelimeler `data/stopwords.jsonl` (satır başına
  `word`, `group`). Dosya yolları `expansion.term_dictionary` ve `expansion.stopwords` ayarlarıdır ve
  Kelimeler sayfasının altındaki “Dosya ayarları” bölümünden değiştirilebilir. **Hedefte:** iki liste
  PostgreSQL tablolarındadır; dosya ve yol ayarı yoktur (Requirement 1;
  [search-settings](../009-search-settings/PRD.md) Requirement 1).
- **Motorun okuması** (`loader.py` `load_term_dictionary`, `load_stopword_file`; `pipeline.py`
  `Resources.from_settings`): terimi boş satır atlanır; eşdeğersiz grup okunur ama kaydetmede
  reddedilir; terim dosyası yoksa uyarıyla boş liste, durak kelime dosyası yoksa uyarıyla boş küme
  kullanılır. Durak kelimeler `text/normalize.py` `load_stopwords` ile katlanmış ve kökü alınmış
  biçim kümesine çevrilir; başlangıç listesinin 106 satırı 124 biçim verir. Terim grubunun `domain`
  ve `note` alanları aramada kullanılmaz, yalnız kayıtlı cevap parmak izine girer
  (`answer_cache.fingerprint`). **Hedefte:** motor listeleri tek okuma işlevinden alır
  (Requirement 2, Decision 2).
- **Başlangıç listeleri** (`cli.py` `_seed_word_lists`, `Dockerfile`): imaj iki dosyayı
  `src/vsa/defaults/` altına kopyalar; her komut açılışta dosya yoksa imajdakini `data/` altına yazar,
  var olan dosyaya (boş da olsa) dokunmaz. Geliştirici makinesinde depodaki dosyalar yerinde
  düzenlenir. **Hedefte:** veritabanı göçüyle bir kez yükleme (Requirement 9).
- **Yönetim uçları** (`web/server.py`): `GET /api/admin/words` iki listeyi ve dosya yollarını
  döndürür. `POST /api/admin/words/terms` ve `/api/admin/words/stopwords` `{"items": [...]}` ile
  listenin tamamını değiştirir: `check_terms` / `check_stopwords` denetler, `write_jsonl` dosyayı
  bütün olarak yazar ve öncekini `.bak` olarak saklar, ardından `App.reindex()` indeksi yeniden
  kurar; yanıt kayıt sayısı, geçen süre ve iki listenin son hâlidir. Hata yanıtı HTTP 400 ve
  `{"error": "<Türkçe ileti>"}`; bilinmeyen liste adı 404 `Kayıt bulunamadı`. Eşzamanlı iki kayıtta
  son yazan kazanır. `reindex()` analiz kilidini beklediği için süren bir analiz (dakikalar) kaydı
  bekletir; kurulum hata verirse dosya yazılmış, motor eski kalır ve ikisi ayrışır. **Hedefte:**
  `/vocabulary/{list}` uçları (API sözleşmesi); eşzamanlı iki kayıtta yine son yazan kazanır
  (Requirement 5, Decision 5); liste yeni indeksle birlikte ya hep ya hiç yazılır; `.bak` yerine
  yazılımsal silinmiş eski satırlar (Decision 4).
- **Terim denetimi** (`loader.py` `check_terms`): girdi nesne listesi değilse `Liste bekleniyordu`,
  5.000'den çok kayıtsa `En fazla 5000 kayıt`. Her kayıtta terim, eşdeğerler, alan ve not kırpılır;
  metin olmayan alan boş sayılır; eşdeğerlerden birebir aynı olanlar atılır, sıra korunur (katlama
  yapılmaz). İlk hata döner: `Satır {n}: terim boş`, `“{terim}”: en az bir eşdeğer gerekli`,
  `“{terim}” iki kez var (satır {i} ve {n})` (Türkçe katlamada aynı terim). `{n}` kaydın listedeki
  1'den başlayan sırasıdır; Excel'den gelen listede boş satırlar atlandıktan sonraki sıradır.
  **Hedefte:** aynı kurallar ve iletiler; ek uzunluk sınırları ve katı alan türleri (Requirement 3).
- **Durak kelime denetimi** (`check_stopwords`): boş kelimeli kayıt sessizce atlanır; boşluk içeren
  kelime `“{kelime}”: durak kelime tek kelime olmalı` ile reddedilir; Türkçe katlamada aynı olan
  kelimelerden ilki (kendi grubuyla) kalır, sonrakiler sessizce atılır. Başlangıç listesinde
  `mi`/`mı` ve `mu`/`mü` katlamada aynıdır: liste ilk kaydedişte 106 satırdan 104 satıra iner,
  motorun 124 biçimlik kümesi değişmez (kaynak testi `test_lists_go_to_excel_and_come_back` bunu not
  eder). **Hedefte:** aynı kurallar; başlangıç listesi kaynaktaki gibi 106 satırla, denetimden
  geçmeden yüklenir ve ilk kaydedişte 104 satıra iner (Requirement 9, Decision 10).
- **Excel** (`WORD_SHEETS`, `words_to_workbook`, `words_from_workbook`): biçim Requirement 6 ve 7'de.
  Dosya ham istek gövdesi ve `X-Filename` başlığıyla gelir; 20 MB sınırı (413
  `Dosya çok büyük (en fazla 20 MB)`); openpyxl salt okunur kipte ve `defusedxml` (XML saldırılarına
  karşı güvenli ayrıştırıcı) ile her sayfadan en çok 5.001 satır ve 20 sütun okunur. **Hedefte:** aynı
  biçim ve sınırlar; dosya kaynaktaki gibi ham istek gövdesi ve `X-Filename` başlığıyla gelir ve
  [dictionary-management](../001-dictionary-management/PRD.md)'ın ortak güvenli Excel okuyucusuyla
  okunur (Requirement 7).
- **Kelimeler sayfası** (`web/static/admin.html` `Words`): düzen Requirement 10–13'te. Kart
  açıklamaları dosya yolunu yazar (`Dosya: data/terms.jsonl`), içe aktarma onayı
  `Önceki liste .bak olarak saklanır` der, sayfanın altında “Dosya ayarları” bölümü vardır. Yönetim
  sayfaları arasında gezinirken düzenlemeler bellekte kalır; sayfa kapanırken tarayıcı onay ister.
  **Hedefte:** aynı düzen ve görünüm; dosyaya değinen metinler ve bölüm kalkar (Requirement 13).
- **Kayıtlı cevaplara etkisi** (ADR-035): her terim listesi değişikliği parmak izini değiştirir;
  yalnız `domain` veya `note` değişse de değiştirir (bu alanlar cevabı etkilemez). Durak kelimede
  parmak izine kelime kümesi girer: kümeyi değiştirmeyen grup değişikliği parmak izini değiştirmez.
  **Hedefte:** aynı ([question-analysis](../004-question-analysis/PRD.md)).

## İşlevsel gereksinimler

Requirement 1: Her liste veritabanında sıralı öğe satırlarından ve bir başlık kaydından oluşur. Başlık
kaydı listenin revizyonunu (her yazılan değişiklikte bir artan tam sayı; başlangıç listesinde 1),
içerik özetini (sıralı öğelerin kararlı JSON biçiminden hesaplanan SHA-256 parmak izi), son
değişikliğin kaynağını (`baslangic`, `ekran`, `excel`), yapanı ve zamanını taşır. Terim öğesi `term`,
`equivalents` (sıralı metin listesi), `domain`, `note`; durak kelime öğesi `word`, `group` alanlarını
taşır. Okuma ucu öğeleri saklanan sırayla ve revizyonla döndürür.

Requirement 2: Motor için tek okuma işlevi vardır: terim gruplarını sırasıyla `TermGroup` olarak,
durak kelimeleri çekirdeğin `load_stopwords` işlevinden geçmiş küme olarak ve iki listenin içerik
özetlerini verir. Başlangıç listeleriyle sonuç, kaynakta `load_term_dictionary(data/terms.jsonl)` ve
`load_stopword_file(data/stopwords.jsonl)` sonucuyla aynıdır: 45 grup ve 124 biçim.

Requirement 3: Terim listesi Mevcut davranış bölümündeki `check_terms` kurallarıyla ve iletileriyle
denetlenir; ilk hata döner, hiçbir satır yazılmaz. Ek sınırlar (**yeni**; kaynakta yoktu): terim en
çok 200, her eşdeğer en çok 200, alan en çok 100, not en çok 1.000 karakter; bir grupta en çok 100
eşdeğer. İletileri: `Satır {n}: terim en fazla 200 karakter olabilir`,
`“{terim}”: eşdeğer en fazla 200 karakter olabilir`, `“{terim}”: alan en fazla 100 karakter olabilir`,
`“{terim}”: not en fazla 1000 karakter olabilir`, `“{terim}”: en fazla 100 eşdeğer olabilir`. İstek
gövdesinde alan türleri katıdır: `term`, `domain`, `note` metin, `equivalents` metin listesidir;
`domain` ve `note` verilmezse boş metin sayılır (kaynakta metin olmayan değer sessizce boşa
çevriliyordu).

Requirement 4: Durak kelime listesi `check_stopwords` kurallarıyla denetlenir: boş kelime atlanır,
boşluk içeren kelime reddedilir, Türkçe katlamada aynı olanlardan ilki grubuyla kalır. Ek sınırlar
(**yeni**): kelime en çok 100, grup adı en çok 200 karakter; iletileri
`“{kelime}”: durak kelime en fazla 100 karakter olabilir` ve
`“{kelime}”: grup adı en fazla 200 karakter olabilir`. Liste en çok 5.000 kayıttır. Grup aramayı
etkilemez; yalnız listeyi düzenler ve kelimenin neden listede olduğunu gösterir.

Requirement 5: Kaydetme (`PUT /vocabulary/{list}`) listenin tamamını taşır. Önce liste denetlenir
(Requirement 3–4); sonra istek [search-settings](../009-search-settings/PRD.md) değişiklik sırasına
girer ve sırası gelince güncel kayda karşı şu adımlarla işlenir: (1) denetlenmiş içerik saklanan
içerikle aynıysa hiçbir şey yazılmaz, revizyon değişmez, indeks yeniden kurulmaz ve yanıt
`changed: false` ile 200 döner (aynı isteğin tekrarı aynı sonucu verir); (2) yeni listeyle motor
kurulur; kurulum başarılıysa tek veritabanı işleminde (hep ya da hiç yazılan işlem) eski öğe
satırları yazılımsal silinir, yeni satırlar eklenir, başlık kaydının revizyonu bir artar, özet,
kaynak `ekran`, yapan ve zaman yazılır ve yeni motor hizmete alınır. Kurulum ya da yazma hata
verirse hiçbir satır değişmez, eski motor hizmette kalır ve yanıt 500 `search_index_build_failed`
olur. Sırada bekleme sınırını ([search-settings](../009-search-settings/PRD.md) Requirement 11) aşan
istek hiçbir şey yazılmadan 503 `search_change_busy` alır. İki yönetici aynı listeyi aynı anda
kaydederse kayıtlar sırayla işlenir ve sonraki kayıt öncekinin yerini alır (kaynakla aynı, Decision
5). Başarılı yanıt listenin yeni hâlini, `changed`, toplam süreyi (`elapsed_ms`) ve indeks durumunu
taşır.

Requirement 6: Dışa aktarma (`GET /vocabulary/{list}/export`) kaydedilmiş listeyi tek sayfalı Excel
olarak verir: sayfa adı `Terimler` ya da `DurakKelimeler`; ilk satır kalın başlık (`Terim`,
`Eşdeğerler`, `Alan`, `Not` ya da `Kelime`, `Grup`); her öğe bir satır; eşdeğerler tek hücrede `, `
ile birleşik; boş değer boş hücre; sütun genişlikleri Terim 28, Eşdeğerler 70, Alan 16, Not 50,
Kelime 24, Grup 24; ilk satır dondurulmuş; `=` ile başlayan metin formül değil metin olarak yazılır.
Dosya adı `TerimSozlugu_YYYYAAGG_SSDD.xlsx` ya da `DurakKelimeler_YYYYAAGG_SSDD.xlsx`; zaman İstanbul
saatidir (`Europe/Istanbul`). Dosya istek anında üretilir, saklanmaz.

Requirement 7: İçe aktarma (`POST /vocabulary/{list}/import`) bir `.xlsx` dosyası okur. Dosya ham
istek gövdesi ve `X-Filename` başlığıyla gelir ve
[dictionary-management](../001-dictionary-management/PRD.md)'ın ortak güvenli Excel okuyucusuyla
okunur (yükleme biçimi, 20 MB yükleme ve 100 MB açılmış boyut sınırı, güvenli XML ve bellekte okuma
orada: dictionary-management Requirement 2 ve Decision 10). Boş dosya 422 `vocabulary_file_empty`
(`Dosya boş`); 20 MB'ı aşan dosya 413 `upload_too_large` (`Dosya çok büyük (en fazla 20 MB)`); Excel
olarak açılamayan dosya 422 `vocabulary_workbook_unreadable`
(`Dosya Excel (.xlsx) olarak okunamadı.`); açılmış boyut sınırını aşan dosya aynı kodu okuyucunun
iletisiyle (`Dosya açıldığında çok büyük (en fazla 100 MB).`) alır. Bu listenin kendi sınırları: her
sayfadan en çok 5.001 satır ve 20 sütun okunur; sınırın ötesinde dolu satır varsa 422
`vocabulary_workbook_too_many_rows` (`Dosyada çok fazla satır var (en fazla 5000).`). Okunan sayfa
`Terimler` / `DurakKelimeler` adlı sayfadır, yoksa ilk sayfa. Başlıklar Türkçe katlanıp boşlukları
atılarak eşlenir: Terim ← `terim`, `term`; Eşdeğerler ← `esdegerler`, `esdeger`, `equivalents`; Alan
← `alan`, `domain`; Not ← `not`, `note`, `aciklama`; Kelime ← `kelime`, `word`, `durakkelime`; Grup
← `grup`, `group`. Terim listesinde Terim ya da Eşdeğerler, durak kelimede Kelime başlığı yoksa 422
`vocabulary_workbook_column_missing`
(`“Terim” sütunu bulunamadı; dışa aktarılan dosyanın başlıklarını koruyun (Terim, Eşdeğerler, Alan, Not).`;
eksik başlığın ve listenin adıyla). Bütün hücreleri boş satır atlanır; tam sayı değerli sayı hücresi
`5` olarak okunur; eşdeğer hücresi virgül, noktalı virgül, dikey çizgi ve satır sonundan bölünür.
Kayıt kalmazsa 422 `vocabulary_workbook_empty` (`“Terimler” sayfasında kayıt yok.` ya da
`“DurakKelimeler” sayfasında kayıt yok.`).

Requirement 8: İçe aktarılan kayıtlar Requirement 5'teki denetim ve değiştirme yolundan geçer; tek
farkı kaynağın `excel` yazılmasıdır. Dışa aktarılan dosya değiştirilmeden içe aktarılırsa sonuç
`changed: false` olur.

Requirement 9: Başlangıç listeleri bir veri göçüyle (Alembic) yüklenir. Göç, kaynak `76e21a3`'teki
`data/terms.jsonl` (SHA-256 `5d8e48cb8372814f34097ca76fe457831980b729181c939dac234852856e078b`, 45
satır) ve `data/stopwords.jsonl` (SHA-256
`0e9096525c2a6ba6d843cc23563dae8b3337c0c4ce77f52766aae8edd862595d`, 106 satır) dosyalarının depoya
alınmış birebir kopyalarını okur; parmak izi tutmazsa hata verip durur. Satırları kaynaktaki gibi
denetimden geçirmeden, dosyadaki sırayla ve olduğu gibi revizyon 1, kaynak `baslangic`, yapan boş
olarak yazar: 45 terim grubu ve 106 durak kelime (Decision 10). Katlamada aynı olan `mi`/`mı` ve
`mu`/`mü` satırları ayrı kalır; liste ekrandan ya da Excel'den ilk kaydedildiğinde Requirement 4
denetimiyle 104 satıra iner (kaynakla aynı). Bir listenin başlık kaydı zaten varsa (liste boş olsa
da) o liste için hiçbir şey yazmaz. Uygulama açılışı listeleri hiçbir zaman yüklemez veya
değiştirmez.

Requirement 10: Kelimeler sayfası (`/admin/kelimeler`, yalnız `yonetici`) kaynaktaki `admin.html`
ile birebir aynı görünür ([search-settings](../009-search-settings/PRD.md) Decision 11) ve iki kart
gösterir: üstte terim sözlüğü, altta durak kelimeler; masaüstünde sayfa yüksekliğini 3'e 2
paylaşırlar ve listeleri kendi içinde kayar ([search-settings](../009-search-settings/PRD.md) tek
ekran düzeni). Sayfa başlığı `Kelimeler`, açıklaması
`Terim sözlüğü sorguyu iş biriminin kelimeleriyle genişletir; durak kelimeler aramada yok sayılır.`.
Terim kartı: başlık `Terim sözlüğü · N` (arama süzerken `Terim sözlüğü · gösterilen / N`), arama
kutusu `Terim ya da eşdeğer ara…` (terim, eşdeğer, alan ve notta Türkçe katlamayla arar), düğmeler
`Excel'den içe aktar…` (ipucu `Excel'deki liste bu listenin yerini alır`), `Excel'e aktar` (ipucu
`Kaydedilmiş liste; düzenleyip geri içe aktarabilirsiniz`) ve `Yeni terim`; açıklama
`Bir gruptaki her kelime ötekileri de aratır: “kredi” arayan “fon kullandırım”ı da bulur.`; tablo
sütunları Terim, Eşdeğerler (etiketler), Alan, Not (tek satır, tamamı ipucunda; boş değer `—`). Boş
durumlar `Aramaya uyan terim yok.` ve `Terim yok; “Yeni terim” ile ekleyin.`. Satır fareyle ve
klavyeyle (odaklanınca Enter ya da Space) düzenleme çekmecesini açar.

Requirement 11: Terim çekmecesi (sağdan açılan düzenleme paneli): başlık terim ya da `Yeni terim`, alt
yazı `Değişiklik kartta birikir; “Kaydet ve indeksi kur” ile geçerli olur.`; alanlar Terim (yer
tutucu `ör. fon kullandırım`), Eşdeğerler (çok satırlı; yardım
`Satır başına (ya da virgülle) bir kelime veya ifade; gruptaki her biri ötekileri de aratır.`), Alan
(var olan alanlardan öneri; yardım `Gruplamak için; ör. katılım, genel.`), Not (yardım
`İsteğe bağlı açıklama.`); düğmeler `Sil` (yalnız var olan terimde), `Vazgeç`, `Uygula` / `Ekle`.
Eşdeğerler satır sonu, virgül ve dikey çizgiden bölünür, kırpılır, birebir tekrarlar atılır. Terim ya
da eşdeğer boşsa `Eksik bilgi` / `Terim ve en az bir eşdeğer gerekli.`, katlamada aynı terim varsa
`Bu terim zaten var` / `“{terim}” — onu düzenleyin.` bildirimi çıkar ve çekmece açık kalır. Yeni terim
listenin başına eklenir. Ekrandaki denetim yalnız kolaylıktır; bağlayıcı denetim sunucudadır.

Requirement 12: Durak kelime kartı: başlık `Durak kelimeler · N`, Excel düğmeleri, açıklama
`Aramada yok sayılan tek kelimeler; talep cümlesinin dolgusu kavram sanılmasın diye.`; gruplar
listede ilk göründükleri sırayla, her biri ad (boşsa `Grupsuz`), kelime sayısı, `×` ile çıkarılabilen
kelime etiketleri ve `+ kelime` kutusuyla gösterilir. Kutuya yazılan metin Enter ile boşluk ve
virgülden bölünerek gruba eklenir; listede katlamada zaten olan kelime eklenmez, hiçbiri yeni değilse
`Zaten listede` bildirimi çıkar. Kartın altında `Yeni grup adı`, `kelimeler (boşluk ya da virgülle)`
alanları ve `Grup ekle` düğmesi vardır; ad ya da kelime boşsa
`Grup adı ve en az bir kelime gerekli` bildirimi çıkar.

Requirement 13: Değişiklikler kartta birikir. Kaydedilmemiş değişikliği olan kartta
`Kaydedilmemiş değişiklik var; kaydedince arama indeksi yeniden kurulur (~10 sn).` çubuğu, `Geri al`
ve `Kaydet ve indeksi kur` düğmeleri görünür. Kayıt başarılıysa `Terim sözlüğü kaydedildi` /
`Durak kelimeler kaydedildi` başlığı ve `N kayıt; indeks yeniden kuruldu (X sn).` satırı,
`changed: false` ise `N kayıt; değişiklik yok.` satırı; hata varsa `Kaydedilemedi` ve sunucunun
iletisi gösterilir. İçe aktarmada yalnız `.xlsx` seçilebilir (başka
uzantıda `Excel (.xlsx) dosyası seçin`); kaynaktaki gibi tarayıcının onay penceresi
`“{dosya}” terim sözlüğünün yerini alsın mı?` (durak kelimede `durak kelime listesinin`) sorar,
kaydedilmemiş değişiklik varsa `Kaydedilmemiş değişiklikler atılır.` ekler ve
`Önceki liste ekrandan geri yüklenemez; gerekirse önce “Excel'e aktar” ile saklayın. Arama indeksi yeniden kurulur (~10 sn).`
der; sürerken `İçe aktarılıyor…` / `{dosya} okunuyor, denetleniyor ve indeks kuruluyor.`, sonunda
`… içe aktarıldı` ya da `İçe aktarılamadı` bildirimi çıkar. Bir listenin kaydı ya da içe aktarılması
öteki listenin kaydedilmemiş değişikliklerini korur. `Excel'e aktar` kaydedilmiş listeyi indirir;
dosya oturum belirtecini taşıyan paylaşılan istemciyle indirilir (düz bağlantı belirteç taşımaz;
[user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 12).
Yönetim sayfaları arasında gezinmek düzenlemeleri korur; yönetim ekranından çıkarken ya da sekmeyi
kapatırken onay istenir ([search-settings](../009-search-settings/PRD.md)). Kaynaktaki `Dosya: …`
açıklamaları ve “Dosya ayarları” bölümü yoktur. Kelimeler sayfasına bırakılan dosya sözlük içe
aktarmasını başlatmaz ([dictionary-management](../001-dictionary-management/PRD.md)).

Requirement 14: Başarılı bir liste değişikliğinin yanıtı döndükten sonra başlayan her analiz yeni
listeyi kullanır; o anda süren analizler başladıkları listeyle biter
([search-settings](../009-search-settings/PRD.md)). Değişiklik kayıtlı cevap parmak izini Mevcut
davranış bölümündeki gibi değiştirir; eski kayıtlı cevaplar silinmez, yalnız kullanılmaz
([question-analysis](../004-question-analysis/PRD.md)).

Requirement 15: Bütün uçlar `yonetici` rolü ister; `kullanici` 403, oturumsuz istek 401 alır.
Kelimeler menü öğesi ve sayfası yalnız `yonetici`'ye görünür; bu gizleme yetki denetiminin yerini
tutmaz.

## API sözleşmesi

Bütün uçlar `/api/dwhnavigator/v1` altındadır, geçerli oturum ve `yonetici` rolü ister. `{list}`
`terms` ya da `stopwords` değerini alır; başka değer 404 `vocabulary_list_not_found` döner. OpenAPI
(API tanım dosyası) `specs/openapi/dwhnavigator-api.yaml` ve üretilmiş ön yüz tipleri aynı
değişiklikte güncellenir. Hata gövdesi tek hata zarfıdır: `{"detail":{"code":"...","message":"..."}}`.

| Yöntem ve yol | İstek özü | Yanıt özü | Hatalar |
|---|---|---|---|
| `GET /vocabulary/{list}` | — | `list`, `revision`, `items[]` | 401, 403, 404 |
| `PUT /vocabulary/{list}` | `items[]` | `list`, `revision`, `items[]`, `changed`, `elapsed_ms`, `index` | 422 denetim kodları; 500 `search_index_build_failed`; 503 `search_change_busy` |
| `GET /vocabulary/{list}/export` | — | `.xlsx` dosyası, `Content-Disposition: attachment` | 401, 403, 404 |
| `POST /vocabulary/{list}/import` | ham Excel gövdesi, `X-Filename` | `PUT` ile aynı | 413 `upload_too_large`; 415 `unsupported_media_type`; 422 `vocabulary_file_empty`, `vocabulary_workbook_unreadable`, `vocabulary_workbook_too_many_rows`, `vocabulary_workbook_column_missing`, `vocabulary_workbook_empty` ve denetim kodları; 500 `search_index_build_failed`; 503 `search_change_busy` |

Terim öğesi `{"term": "...", "equivalents": ["..."], "domain": "...", "note": "..."}`, durak kelime
öğesi `{"word": "...", "group": "..."}`. `index` alanının biçimi
[search-settings](../009-search-settings/PRD.md) `GET /search-index` yanıtıdır.

Denetim kodları (422): `vocabulary_items_invalid` (`Liste bekleniyordu`), `vocabulary_too_many_items`
(`En fazla 5000 kayıt`), `vocabulary_term_empty`, `vocabulary_term_without_equivalents`,
`vocabulary_term_duplicate`, `vocabulary_stopword_not_single_word`, `vocabulary_value_too_long`,
`vocabulary_too_many_equivalents`. Bu kodlarda `message` yalnız gönderilen içerikten kurulan Türkçe
cümledir; ekran onu olduğu gibi gösterir (Decision 6).

## Güvenlik ve yetkilendirme

- Rol denetimi her uçta arka uçtadır; giriş ve roller
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) PRD'sindedir.
  Kaynaktaki `VSA_ADMIN_PASSWORD` HTTP Basic koruması ve “parola yoksa yalnız bu makineden” kuralı
  kalkar; yerine oturum belirteci (istek başlığında taşınan imzalı kimlik) ve rol gelir.
  `Sec-Fetch-Site`/`Origin` denetimi bütün durum değiştiren isteklerde sürer (user-accounts
  Requirement 13).
- Yüklenen dosya yalnız `.xlsx` olarak açılabiliyorsa kabul edilir; boyut, satır ve sütun sınırı
  okumadan önce ya da okurken uygulanır; dosya ortak güvenli Excel okuyucusuyla (güvenli XML, bellekte
  okuma; [dictionary-management](../001-dictionary-management/PRD.md) Requirement 2) okunur, diske ve
  veritabanına yazılmaz.
- Dışa aktarılan her hücre metin olarak yazılır (`=` ile başlayan metin formül olmaz).
- Ekran öğeleri düz metin olarak gösterir; öğe içeriği HTML olarak yorumlanmaz.
- Kayıt ve içe aktarma yapanı başlık kaydına ve olay kaydına kullanıcı `public_id` değeriyle yazar;
  liste içeriği ve dosya adı loga girmez.
- Sorgular parametrelidir ve etkin kiracı (`platform`) kapsamında çalışır.

## Veri ve geçiş

- Şemanın sahibi SQLAlchemy modelleridir; tablolar Alembic göçüyle oluşur (rules/40). Kiracı kapsamı
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) modeline uyar.
  - `vocabulary_list`: liste başına bir satır; `public_id` `terms` ya da `stopwords`; `revision`,
    `content_digest`, `last_source` (`baslangic`, `ekran`, `excel`) ve zorunlu sütun bloğu (rules/41;
    `updated_by` son değiştiren).
  - `vocabulary_term`: `position`, `term`, `term_key` (Türkçe katlanmış terim), `equivalents` (sıralı
    metin dizisi), `domain`, `note` ve zorunlu blok.
  - `vocabulary_stopword`: `position`, `word`, `word_key` (Türkçe katlanmış kelime), `group_name` ve
    zorunlu blok.
- Silinmemiş satırlarda kiracı içinde `term_key` ve her tabloda `position` tekildir (silinmemiş
  satırlara kısmi tekil dizin). `word_key` tekil değildir: başlangıç listesi katlamada aynı olan
  kelimeleri ayrı satırlarda taşır (Decision 10); ekrandan ve Excel'den gelen liste Requirement 4
  denetiminden geçtiği için tekrar içermez. Öğe satırları dışarıdan adreslenmez ve `public_id`
  taşımaz (rules/41'den bilinçli sapma, Decision 3). Liste değişince eski öğe satırları yazılımsal
  silinir (`is_deleted`, `deleted_at`, `deleted_by`); bu satırlar okunmaz, ekranda gösterilmez ve
  geri yüklenmez (Decision 4).
- Tablo ve sütun açıklamaları (rules/43) göçe girer: tabloların amacı ve sahibi bu PRD, `last_source`
  değerleri, `*_key` sütunlarının Türkçe katlama anlamı ve `position` sırasının anlamı.
- Başlangıç verisi Requirement 9 göçüdür. Kaynak dosyaların birebir kopyaları göçün yanında
  `schema/alembic/seed/vocabulary/` altında parmak izleriyle depoya girer ve sonradan değiştirilmez.
- Kaynak `data/` dosyalarından taşıma yoktur (kurulu bir kaynak sürüm yoktur). Bir kaynak kurulumunda
  elle düzenlenmiş liste varsa, kaynağın `Excel'e aktar` çıktısı aynı biçimde hedefe içe aktarılabilir
  (Requirement 7).

## Gözlemlenebilirlik

- Log olayları: `vocabulary.saved` (liste, kaynak `ekran`/`excel`, öğe sayısı, yeni revizyon,
  `changed`, süre, kullanıcı `public_id`), `vocabulary.rejected` (liste, kaynak, hata kodu),
  `vocabulary.seed` (göç işi: liste, öğe sayısı, sonuç `loaded`/`skipped`/`failed`). Terim, eşdeğer,
  kelime, grup, not ve dosya adı yazılmaz.
- Yeni ölçüm (metrik) eklenmez. Liste değişikliğinin indeks kurulumu
  [search-settings](../009-search-settings/PRD.md) ölçümlerine `terms` / `stopwords` tetikleyicisiyle
  girer.
- 413 ve 422 yanıtları kodlarıyla standart istek loguna düşer.

## Dağıtım etkisi

- Yeni tablolar ve başlangıç verisi göçü dağıtımdaki göç işiyle uygulanır
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md));
  uygulama açılışta şema ya da veri değiştirmez. Başlangıç dosyaları göç işinin imajına girer.
- Yeni ortam değişkeni, sır, ağ çıkışı veya chart değişikliği yoktur. Kayıt ve içe aktarma isteğinin
  süresi sırada bekleme ve indeks kurulumunu içerir ve 60 saniye kuralı içinde biter
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  Requirement 12; sıra ve kurulum süreleri [search-settings](../009-search-settings/PRD.md)
  Requirement 11 ve 13).

## Test stratejisi

- **Birim:** `check_terms` ve `check_stopwords` kurallarının her dalı ve iletisi (boş terim,
  eşdeğersiz grup, katlamada iki kez geçen terim, çok kelimeli durak kelime, katlamada aynı durak
  kelimelerin ilkinin grubuyla kalması, kırpma, eşdeğerlerde birebir tekrar atma, yeni uzunluk
  sınırları, 5.000 sınırı); Excel okuma (başlık eş adları, eksik başlık, boş sayfa, satır sınırı,
  sayı hücresi, eşdeğer bölme, adlı sayfa yoksa ilk sayfa); Excel yazma (sayfa adı, başlık, genişlik,
  dondurma, `=` ile başlayan metin) ve dışa aktarılıp geri yüklenen listenin değişmemesi.
- **Fark testi (kaynak paketle yan yana):** aynı listeler için Requirement 2 okuma işlevinin verdiği
  `TermGroup` dizisi ve durak kelime kümesi kaynağın `load_term_dictionary` ve `load_stopword_file`
  sonucuyla aynıdır; başlangıç listeleriyle 45 grup ve 124 biçim; aynı listeyle kaynağın
  `check_terms` / `check_stopwords` çıktısı ve hata iletisi hedefinkiyle aynıdır.
- **Gerçek PostgreSQL:** başlangıç göçünün üç durumu (boş veritabanı: 45 grup ve 106 kelime,
  revizyon 1; başlık kaydı varken: hiçbir şey yazmaz; parmak izi tutmayan kopya: göç durur);
  başlangıç listesinin ilk kaydedişte 104 satıra inmesi; kaydetmenin hep ya da hiç yazması (kurulum
  ve yazma hatası enjekte edilince satır ve revizyon değişmez, eski motor hizmettedir); aynı
  içerikte `changed: false`; art arda iki kayıtta sonrakinin geçerli olması; eski satırların
  yazılımsal silinmesi ve okunmaması; içe aktarma hata kodları; 401 ve 403; kiracı kapsamı.
- **Ön yüz (Vitest):** terim arama ve süzme sayısı, çekmecede ekleme, düzenleme, silme ve ekran
  denetimleri, durak kelime ekleme, çıkarma ve yeni grup, kaydedilmemiş değişiklik çubuğu ve
  `Geri al`, kayıt ve içe aktarma bildirimleri, onay penceresi metni, bir listenin kaydında ötekinin
  taslağının korunması, satırın klavyeyle açılması.
- **Görsel eşdeğerlik:** kaynak `76e21a3` ve hedef aynı başlangıç listeleriyle yan yana
  çalıştırılır; Kelimeler sayfası ve terim çekmecesinin ekran görüntüleri aynı ekran boyutlarında
  karşılaştırılır (Acceptance 5).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 2–4 ve 6–7 birim testleri ile kaynak
  paketle yan yana fark testleri geçer; başlangıç listeleriyle motorun gördüğü 45 grup ve 124 biçim
  kaynakla bayt bayt aynıdır.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 1, 5, 8, 9, 14 ve 15 gerçek
  PostgreSQL ve API testleri geçer (göçün üç durumu, hep ya da hiç yazma, `changed: false`, son
  yazanın kazanması, yazılımsal silme, hata kodları, 401/403); OpenAPI ve üretilmiş tipler
  günceldir; tam kalite kapısı geçer.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Kelimeler sayfasının Vitest testleri
  Requirement 10–13'ü doğrular; yerelleştirme anahtar eşliği testi geçer.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel Docker Compose ve PostgreSQL ile
  boş veritabanında Kelimeler sayfası 45 terim grubu ve 106 durak kelime gösterir; yönetici bir
  terim grubu ekleyip kaydeder, `indeks yeniden kuruldu` bildirimini görür ve sözlük gezgininin
  içerik araması ([dictionary-explorer](../007-dictionary-explorer/PRD.md)) yeni eşdeğerle grubun
  terimine bağlı kolonları bulur; listeyi Excel'e aktarıp değiştirmeden içe aktarınca
  `değişiklik yok` görür; çok kelimeli durak kelime içeren Excel'i yükleyince satır değişmeden ret
  iletisi görür; iki tarayıcı oturumundan art arda yapılan kayıtta sonuncusu geçerli olur;
  `kullanici` oturumu sayfayı göremez ve uçlardan 403 alır (Requirement 5, 7–10, 13–15). Sözlük
  gezgini adımı dictionary-explorer PRD'si uygulanmadan açık kalır.
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı başlangıç listeleriyle çalıştırılır; Kelimeler sayfası (iki kart,
  kaydedilmemiş değişiklik çubuğu) ve terim çekmecesinin ekran görüntüleri masaüstü (1440×900) ve
  telefon genişliğinde (390×844 piksel) yan yana karşılaştırılır. Fark yalnız dosya deposunun
  kalkmasından doğan metinlerde ("Dosya: …", "Dosya ayarları") ve fabrikanın zorunlu kıldığı oturum
  alanında kabul edilir (Requirement 10–13).

## Kararlar

Decision 3: Öğe satırları (`vocabulary_term`, `vocabulary_stopword`) dışarıdan adreslenmez; liste
bütün olarak okunur ve yazılır. Bu yüzden `public_id` taşımazlar; liste başlık kaydı `public_id`
olarak sabit liste adını (`terms`, `stopwords`) kullanır. Zorunlu bloğun kalanı (iç kimlik, `props`,
denetim ve yazılımsal silme sütunları) uygulanır.

Decision 4: Kaynaktaki tek düzeyli `.bak` dosyasının yerine, değiştirilen listenin satırları
yazılımsal silinmiş olarak tabloda kalır (rules/41). Ekrandan geri yükleme yoktur (kaynakta da yoktu);
yanlış bir içe aktarmadan dönüş için önerilen yol, değişiklikten önce `Excel'e aktar` ile kopya
almaktır ve onay penceresi bunu söyler.

Decision 5: Eşzamanlı iki kayıtta kaynaktaki gibi son yazan kazanır; kayıt revizyon denetimi yapmaz
(Requirement 5). Kayıtlar search-settings değişiklik sırasında tek tek işlendiği için iki kayıt
birbirine karışmaz; sonraki kayıt öncekinin yerini alır. Revizyon numarası yalnız bilgi ve olay
kaydı içindir.

Decision 6: Denetim iletileri sunucuda, kaynaktaki Türkçe metinle kurulur ve yalnız yöneticinin
gönderdiği içerikten (terim, kelime, satır numarası) oluşur; uygulama ayrıntısı taşımaz. Ekran bu
kodlarda iletiyi olduğu gibi gösterir; diğer kodlarda kendi yerelleştirilmiş iletisini kullanır
(rules/31). Proje tek dillidir (`tr`).

Decision 7: Uzunluk ve eşdeğer sayısı sınırları (Requirement 3–4) yenidir: güvenilmeyen girdi
sunucuda uzunlukla sınırlanır (rules/57). Başlangıç listelerindeki en büyük değerler terimde 20,
eşdeğerde 35, alanda 12, notta 142, durak kelimede 12, grup adında 48 karakter ve bir grupta 8
eşdeğerdir; sınırlar bunların çok üstündedir.

Decision 8: Başlangıç listeleri, kardeş projenin kural içe aktarmasındaki gibi parmak izi denetimli bir
veri göçüyle yüklenir (Requirement 9). Göç her veritabanında bir kez çalışır, işletim ekibinden elle
adım istemez ve kaynaktaki “var olan dosyaya dokunma” davranışını korur.

Decision 9: Liste uçları sayfalama yapmaz: liste ekranda bütün olarak düzenlenir ve en çok 5.000
öğedir. Bu, rules/21'deki liste uçlarında sayfalama kuralının bilinçli istisnasıdır; uç bir koleksiyon
değil tek bir belge (liste) döndürür.

Decision 10: Başlangıç listeleri kaynak dosyalarındaki gibi, denetimden geçmeden yüklenir: durak
kelimeler 106 satırdır. Gerekçe: kaynakta da başlangıç dosyası olduğu gibi kullanılır ve ilk
kaydedişte 104 satıra iner; motorun kullandığı 124 biçimlik küme iki durumda da aynıdır. Bu yüzden
katlanmış durak kelimeye tekil dizin konmaz.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama ([Plan](plan.md), [Görevler](tasks.md)).

## Riskler

- **Eşzamanlı düzenleme:** İki yönetici aynı listeyi aynı anda düzenlerse son kaydeden öncekinin
  değişikliğini uyarısız siler (kaynakla aynı, Decision 5).
- **Yanlış içe aktarma:** Yanlış bir Excel listenin tamamının yerini alır. Onay penceresi ve önceden
  `Excel'e aktar` önerisi bunu azaltır; ekrandan geri yükleme yoktur, eski satırlar yalnız veritabanında
  yazılımsal silinmiş olarak kalır.
- **Ayırıcı içeren eşdeğer:** Noktalı virgül içeren bir eşdeğer (çekmece noktalı virgülden bölmez)
  Excel'e aktarılıp geri yüklenince iki eşdeğere bölünür; kaynakta da böyledir.
- **Gereksiz yeniden analiz:** Terim grubunun yalnız alanı ya da notu değişse de parmak izi değişir ve
  kayıtlı cevaplar kullanılmaz; bir sonraki benzer soru dakikalar süren analizle yeniden cevaplanır.
- **Kayıt süresi:** Her kayıt indeksin yeniden kurulmasını bekler (kaynakta yaklaşık 10 saniye); büyük
  sözlükte süre uzarsa giriş katmanının 60 saniyelik süre sınırına yaklaşabilir
  ([search-settings](../009-search-settings/PRD.md) Riskler).
- **Başlangıç dosyasının değişmesi:** Depodaki başlangıç kopyası sonradan değişirse yeni kurulumlarda
  göç parmak izi denetiminde durur; dosyalar göçle birlikte sabittir. Yeni terimler kurulu sistemlere
  yönetim ekranından ya da Excel ile eklenir.
- **Ekran ile sunucu katlaması:** Ekranın arama ve tekrar denetimindeki katlama sunucununkinden çok az
  farklı olabilir (ör. `â`); bağlayıcı karar sunucudadır.
