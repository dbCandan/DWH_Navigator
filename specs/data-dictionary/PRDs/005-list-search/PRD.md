# PRD — list-search

Status: Accepted

Version: 1.1.0

Acceptance date: 2026-10-14

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi ilk kez 2026-10-08'de kabul etti;
2026-10-14'te ana ekranın girişsiz kullanılmasını istedi
([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)).

## Amaç

Kullanıcı aranacak terimleri tek sütunlu bir Excel listesiyle yükler. Uygulama listedeki her terimi
tek sorunun geçtiği analiz akışından ([question-analysis](../004-question-analysis/PRD.md)) sırayla
geçirir. Kullanıcı ilerlemeyi terim terim izler, listeyi durdurup kaldığı yerden sürdürür, liste
sürerken o ana kadarki raporu, bitince bütün liste için tek bir Excel raporu indirir. Liste ve her
terimin cevabı PostgreSQL veritabanında saklanır; sayfa kapansa ya da sunucu yeniden başlasa da
liste ve o ana kadarki cevaplar kaybolmaz.

## Aktörler ve sonuçlar

- **Ziyaretçi:** Ana ekranı giriş yapmadan kullanan kişi; tarayıcısının cihaz kimliğiyle tanınır
  ([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)
  Decision 1, 2). Liste yükler; kendi listelerinin ilerlemesini izler, durdurur, sürdürür; terim
  cevaplarını açar; rapor indirir. Ölçülebilir sonuç: kurala uyan bir listenin her
  terimi için ya analistin cevabı (VAR, KISMEN VAR, BULUNAMADI), ya "Analiz yapılamadı" ve sebebi,
  ya da güvenli bir hata iletisi saklanır; 200 terimlik bir listenin bütün terimleri tek Excel
  raporunda (Özet · Öneriler) terim başına bir satırla görünür; sunucu yeniden başladıktan sonra
  sürdürülen listede daha önce cevaplanmış hiçbir terim yeniden sorulmaz.
- **Yönetici (`yonetici`):** Yönetim ekranına hesabıyla girer; listeler üzerinde yetkisi yoktur ve
  ziyaretçilerin listelerini göremez (Decision 8). Ana ekranı kendisi kullandığında o tarayıcının
  ziyaretçisi olarak yalnız o ziyaretçinin listelerini görür. Başkalarının terim analizlerini
  [analysis-records](../008-analysis-records/PRD.md)'ın Analizler sayfasında görür.
- **İşletim ekibi:** Dağıtımı yapar; yeniden başlatma listeyi silmez, yarıda keser. Uygulama içi
  rol değildir.

## Değişmezler ve sınırlar

- Liste kendi analiz yolunu kurmaz: her terim tek sorunun geçtiği akıştan geçer; cevabı yalnız
  analist yazar, kural motorunun sıralaması gösterilmez (Decision 1). Analiz işi, analiz sırası,
  iptal mekanizması, kayıtlı cevaplar, cevap biçimi, cevap görünümü ve tek soru raporu
  [question-analysis](../004-question-analysis/PRD.md) PRD'sindedir. Bu PRD listeye özgü olanın
  sahibidir: yükleme ve okuma kuralları, liste işi, terim durumları, durdurma, sürdürme, yeniden
  başlamada yarıda kesilme, ara ve son rapor, listelerin saklanması ve ana ekrandaki liste arayüzü.
- Oylar ve oyların cevaba uygulanması [answer-feedback](../006-answer-feedback/PRD.md)
  PRD'sindedir; terim ayrıntısı o PRD'nin uygulama adımından geçer.
- Analiz kaydının veri modeli [analysis-records](../008-analysis-records/PRD.md)
  PRD'sindedir. Kayıtlı cevapların açık ya da kapalı olması, "aynı anlam" eşleşmesi ve en çok yaşı
  [search-settings](../009-search-settings/PRD.md) ayarlarıdır. Sözlük sürümü
  [dictionary-management](../001-dictionary-management/PRD.md) PRD'sindedir. Yönetim ekranının
  girişi ve rolleri [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md),
  ana ekranın girişsiz kullanımı ve ziyaretçi kimliği
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)
  PRD'sindedir.
- Kurumda aynı anda en çok bir liste çalışır; kural kişiden bağımsızdır (Decision 3).
- Bir liste onu yükleyen ziyaretçiye aittir; sahip ya bir hesap ya bir ziyaretçidir
  (anonymous-visitor Decision 5). Listeyi yalnız sahibi görür, durdurur ve sürdürür (Decision 8).
  Başka her ziyaretçi ve hesap için (`yonetici` dahil) yanıt, liste yokmuş gibi 404'tür.
- Yüklenen Excel dosyası saklanmaz ve kalıcı olarak hiçbir yere yazılmaz; yalnız terimler, başlık,
  okuma notları ve dosya adı saklanır (Decision 9). Dosya
  [dictionary-management](../001-dictionary-management/PRD.md)'ın ortak güvenli Excel okuyucusuyla ve
  bu PRD'nin satır ve sütun sınırlarıyla okunur (Requirement 2).
- Terim metni, dosya adı, başlık, cevap metni, tablo ve kolon adı uygulama günlüğüne (log) ve
  telemetriye (ölçüm ve iz) girmez.
- Raporlar istek anında üretilir, saklanmaz; oylar raporu değiştirmez; rapora yazılan her metin
  hücreye metin olarak yazılır ("=" ile başlayan metin formül olmaz).
- Okuma kuralları (`parse_term_sheet`) ve rapor biçimi (`write_list_report`) kaynakla aynı davranır
  (Decision 10).
- Arayüz yalnız Türkçedir.

## Mevcut davranış

Kaynak: bu deponun geçmişindeki `76e21a3`. Her maddenin sonundaki **Hedefte:** notu hedefteki
davranışı söyler.

- **Yükleme** (`src/vsa/web/server.py` `POST /api/list`, `App.list_start`): Gövde ham `.xlsx`
  baytlarıdır; dosya adı `X-Filename` başlığında gelir, yoksa `liste.xlsx` sayılır. Gövde 20 MB'ı
  aşarsa 413 döner (`MAX_UPLOAD`). Çalışan bir liste varsa dosya okunmadan "Bir liste zaten
  çalışıyor; bitmesini bekleyin ya da durdurun." (400) döner. Dosya geçici klasöre yazılıp okunur.
  İstek kimlik sormaz; isteği yapanın ağ adresi analiz kaydına yazılır. **Hedefte:**
  `POST /term-lists` kaynaktaki gibi ham Excel gövdesi ve `X-Filename` başlığıyla gelir (yükleme
  biçimi dictionary-management Decision 10); kaynaktaki gibi oturum istemez, ziyaretçinin cihaz
  kimliğini (`X-Device-Id`) ister; dosya saklanmaz; hatalar kararlı kodlarla 409, 413 ve 422 döner;
  listenin sahibi isteği yapan ziyaretçidir (Requirement 2–4, 14).
- **Okuma kuralları** (`src/vsa/loader.py` `load_term_list`, `parse_term_sheet`, `read_workbook`,
  `_sheet_rows`): Yalnız ilk sayfa aranır; diğer sayfalar yalnız "veri var mı" diye okunur. Her
  sayfada ilk 50 sütun (`MAX_LIST_COLUMNS`) ve en çok 2.001 satır (başlık ve altında 2.000 satır,
  `MAX_LIST_ROWS`) okunur; ötesinde dolu satır görülünce okuma durur. Hücredeki boşluklar
  sadeleşir. Veri yalnız A sütununda olmalıdır; ilk satır her zaman başlıktır ve aranmaz; boş
  satırlar ve Türkçe normalleştirmeyle aynı sayılan tekrarlar atlanır. Terim en çok 500 karakter
  (`MAX_TERM_CHARS`), liste en çok 200 farklı terimdir (`MAX_TERMS`). Başlık bilinen başlık
  kelimelerinden değilse, boş ya da tekrar satır varsa, başka sayfada veri varsa okuma notu üretilir.
  Hatalar dosyanın nasıl düzeltileceğini söyleyen Türkçe iletilerdir. **Hedefte:** aynı kurallar,
  sınırlar, notlar ve iletiler; sıkıştırma bombasına karşı açılmış boyut sınırı eklenir
  (Requirement 1–3, Decision 9).
- **Arka plan işi** (`ListJob`, `App._run_list`): Liste, sunucu içinde ayrı bir iş parçacığında
  (thread: aynı süreçte paralel yürüyen iş kolu) terim terim yürür. Her terim `_answer(terim, 5, …)`
  ile tek soru akışından geçer: önce kayıtlı cevap aranır (ADR-035), yoksa motorun tek kilidi
  beklenir ve analist çalışır; analistin cevabı kayıtlı cevaplara eklenir. Her terim analiz
  kaydına `origin` = `"<dosya adı> #<sıra>"` ile yazılır. **Hedefte:** liste sunucu sürecinde arka
  plan görevi olarak yürür; her terim question-analysis'in analiz işi olarak, sıraya tek tek girer;
  her terimin cevabı terim bitince veritabanına yazılır (Requirement 5, 6).
- **Tek çalışan liste** (`list_start`, `list_resume`): Herhangi bir liste çalışırken yenisi
  başlatılamaz, başka liste sürdürülemez; kural kurum genelidir. **Hedefte:** aynı kural;
  veritabanı kısıtıyla güvence altındadır; ileti, çalışan listenin isteği yapana mı başkasına mı ait
  olduğunu söyler (Requirement 4, Decision 3).
- **Durumlar ve anlık durum** (`ListJob.state`, `ListJob.snapshot`, `src/vsa/web/serialize.py`
  `list_item`): Terimin durumu cevabı varsa "bitti", hatası varsa "hata", çalışan terimse
  "çalışıyor", liste durdurulduysa "durduruldu", değilse "sırada"dır. Anlık durum; liste adı,
  başlık, notlar, çalışıyor ve durduruldu bayrakları, toplam, biten (cevaplanan ve hatalı) sayısı,
  geçen süre, kalan süre tahmini (biten terimlerin ortalama süresi × kalan terim) ve terim
  satırlarını verir. Terim hatası ham istisna metnidir (`str(exc)`). **Hedefte:** aynı alanlar ve
  durumlar; liste durumu tek alanda (sürüyor, tamamlandı, durduruldu, yarıda kesildi); terim
  hatasında yalnız güvenli Türkçe ileti (Requirement 7, 18).
- **Durdurma** (`App.list_cancel`, `src/vsa/cancel.py` `Token`): Durdurma listenin iptal belirtecini
  tetikler; çalışan terimin model bağlantıları kesilir, kilit bekleyen terim beklemeden çıkar.
  Durdurulan terim cevapsız kalır, hata sayılmaz. **Hedefte:** aynı; durdurmayı yalnız sahibi yapar;
  süre sınırı 5 saniyedir (Requirement 8).
- **Sürdürme** (`App.list_resume`): Cevabı olan terimler korunur; cevapsız ve hatalı terimler
  sırayla yeniden sorulur; duraklama geçen süreye sayılmaz; her terimi cevaplanmış listede "Bu
  listenin bütün terimleri cevaplandı; devam edecek terim yok." döner. "Analiz yapılamadı" sonucu
  cevap sayılır, yeniden sorulmaz; ekran "Model çalışınca bu terimleri yeniden arayın." der. "▶
  Devam et" düğmesi yalnız durdurulmuş ve cevapsız terimi kalmış listede görünür; durdurulmadan
  bitmiş ama hatalı terimi olan listede görünmez. **Hedefte:** aynı kurallar ve aynı düğme;
  sürdürmeyi yalnız sahibi yapar; yarıda kesilen liste durdurulmuş liste gibi sürdürülür
  (Requirement 9, 17).
- **Saklama** (`App.lists`, `MAX_LISTS = 5`): Listeler bellektedir; çalışmayan en çok 5 liste, kimin
  olduğuna bakılmadan tutulur; sunucu yeniden başlayınca hepsi kaybolur. Listeleri sıralayan
  `GET /api/list` ucu ADR-053 ile kaldırılmıştır; sayfa yenilenince liste bir daha bulunamaz.
  **Hedefte:** listeler veritabanında kalıcıdır; sahip (ziyaretçi) başına en yeni 5 liste tutulur;
  ana ekran sayfa açılışında ziyaretçinin en yeni listesini bulur (Requirement 15, 16, Decision 14).
- **Sayfadan ayrılma** (`src/vsa/web/static/index.html` `Bulk`, `pagehide` olayında
  `navigator.sendBeacon(".../cancel")`): Sayfa kapanınca ya da yenilenince çalışan liste durdurulur;
  sayfa listenin tek sahibidir. **Hedefte:** liste sayfadan bağımsız sürer (Requirement 11, Decision 13).
- **Yeniden başlama:** Sunucu yeniden başlayınca çalışan liste ve bütün cevapları kaybolur.
  **Hedefte:** liste "yarıda kesildi" olur, cevaplanmış terimler korunur, sahibi sürdürür
  (Requirement 10, Decision 2).
- **Terim ayrıntısı** (`App.list_item`, `GET /api/list/<id>/item/<n>?voter=`): Cevaplanmış terimin
  tam cevabı tek soru cevabıyla aynı biçimde döner; oylar istemcinin gönderdiği `voter` kimliğiyle
  uygulanır; terimin tek soru raporu bellekte tutulan en çok 50 rapordan (`MAX_REPORTS`) birine
  bağlanır, sonra kaybolur. **Hedefte:** oylar isteği yapan ziyaretçiye göre uygulanır (`voter`
  sorgu parametresi yerine `X-Device-Id`); terimin raporu saklanan cevaptan her istekte üretilir
  (Requirement 12).
- **Rapor** (`src/vsa/report/excel.py` `write_list_report`, `_list_summary`, `_list_suggestions`,
  `_item_state`; `App.list_report`): Tek çalışma kitabı, iki sayfa: Özet (terim başına satır) ve
  Öneriler (bütün terimlerin önerileri, terim sütunuyla). Liste sürerken de alınabilir. Dosya
  `data/out` altına yazılıp gönderilir; adı `VSA_liste_<dosya adından kısa ad>_<YYYYMMDD_HHMM>.xlsx`;
  zamanlar sunucunun yerel saatidir. **Hedefte:** aynı içerik ve biçim; bellekte üretilip gönderilir,
  diske yazılmaz; zamanlar İstanbul saatidir (Requirement 13, Decision 10).
- **Komut satırı** (`src/vsa/cli.py` `vsa ask -i`, `_ask_list`): Aynı listeyi terminalde sırayla
  cevaplar ve rapor yazar; kayıtlı cevap kullanmaz, analiz kaydı yazmaz. **Hedefte:** kaldırılır
  (Decision 11).
- **Arayüz** (`index.html` `Bulk`): Arama çubuğundaki Excel düğmesi ve sayfaya sürükle-bırak, ret
  açıklaması, liste görünümü, 1,5 saniyede bir yoklama, terim ayrıntısı, üst çubukta "Liste" hapı.
  Sürdürme hatası tarayıcının açılır uyarı penceresiyle (`alert`) gösterilir. **Hedefte:** React'te
  aynı işlev, görünüm ve metinler; sayfa açılışında ziyaretçinin en yeni listesi hapla bulunur
  (Requirement 17).

## İşlevsel gereksinimler

Requirement 1: Liste tek, sabit bir biçimdedir ve hiçbir şey tahmin edilmez: çalışma kitabının
yalnız ilk sayfası aranır; terimler yalnız A sütunundadır; ilk satır her zaman başlıktır ve
aranmaz; altındaki her satır bir terimdir. Hücredeki baştaki, sondaki ve art arda boşluklar tek
boşluğa iner; tam sayı değerli sayı hücresi "5.0" değil "5" okunur. Boş satırlar atlanır; Türkçe
normalleştirme yardımcısıyla (büyük-küçük harf ve Türkçe harf farkını yok sayan karşılaştırma)
aynı sayılan tekrarlardan yalnız ilk geçeni aranır; sondaki boş satırlar sayılmaz. Okuma şu notları
bu sırayla üretir ve liste bunları saklar: başlık bilinen başlık kelimelerinden değilse "İlk satır
(“{başlık}”) başlık sayıldı ve aranmadı.", boş satır varsa "{n} boş satır atlandı.", tekrar varsa
"{n} tekrar eden terim atlandı (ilk geçtiği satır arandı).", ilk sayfadan başka veri taşıyan sayfa
varsa "Yalnız ilk sayfa okundu; şu sayfalardaki veriler alınmadı: {sayfa adları}." Bilinen başlık
kelimeleri kaynaktaki kümedir (`_HEADER_WORDS`: terim, terimler, talep, talepler, soru, sorular,
arama, kavram, kavramlar, term, terms, query, queries, request, requests, liste, aranacak,
aranacaklar, ihtiyac, konu); başlık normalleştirilip sonundaki boşluk, iki nokta ve nokta atılarak
karşılaştırılır.

Requirement 2: Dosya [dictionary-management](../001-dictionary-management/PRD.md)'ın ortak güvenli
Excel okuyucusuyla okunur: yükleme biçimi (ham gövde, `Content-Type`, `X-Filename`), 20 MB gövde ve
100 MB açılmış boyut sınırı, güvenli XML ayrıştırıcı ve dosya sistemine yazmadan bellekte okuma orada
tanımlıdır (dictionary-management Requirement 2 ve Decision 10). Bu PRD'nin hata kodları ve kendi
sınırları:

- Gövde 20 MB'ı aşarsa dosya okunmadan 413 `upload_too_large` ("Dosya çok büyük (en fazla 20 MB)")
  döner.
- Dosya `.xlsx` çalışma kitabı olarak açılamazsa (eski `.xls`, `.csv`, bozuk dosya) 422
  `term_list_not_xlsx` döner.
- Açılmış toplam boyut sınırı aşılırsa hiçbir sayfa okunmadan 422 `term_list_too_large_unpacked`
  döner (Decision 9).
- Her sayfada yalnız ilk 50 sütun ve en çok 2.001 satır (başlık ve altında 2.000 satır) okunur;
  sınırın ötesinde dolu bir satır görülünce okuma durur ve 422 `term_list_too_many_rows` döner;
  ötesindeki boş satırlar yok sayılır. Kural, kaynakta olduğu gibi her sayfaya uygulanır.
- Terim en çok 500 karakterdir; uzun satır 422 `term_list_term_too_long` alır. Boş ve tekrar
  satırlar ayıklandıktan sonra en çok 200 terim kalır; fazlası 422 `term_list_too_many_terms` alır.
- Hücre formülü çalıştırılmaz, yalnız dosyada kayıtlı değer okunur.

Requirement 3: Ret iletileri kaynaktaki Türkçe metinlerdir ve dosyanın nasıl düzeltileceğini söyler:
"Dosya Excel (.xlsx) olarak okunamadı.", "Dosyada sayfa yok.", "Dosya boş.", "Terimler A sütununda
olmalı; dosyada veri {sütunlar} sütununda.", "Liste tek sütunlu olmalı; dosyada {sütunlar}
sütunlarında veri var. Terimleri A sütununa yazıp diğer sütunları silin.", "İlk satır başlık
olmalı; A1 hücresi boş.", "Başlığın (“{başlık}”) altında aranacak terim yok." iletilerinin her biri
"Beklenen biçim: A sütununda, ilk satırda bir başlık (ör. “Terim”), altında her satırda bir terim."
ile biter; "Dosyada çok fazla satır var (en fazla 2000); listeyi bölüp ayrı ayrı yükleyin.",
"{n}. satır çok uzun ({k} karakter). Her satıra kısa bir terim ya da soru yazın (en fazla 500).",
"Listede {n} terim var; tek seferde en fazla 200. Listeyi bölüp ayrı ayrı yükleyin." kendi başına
durur. Biçim hataları (boş dosya, sayfasız dosya, yanlış sütun, birden çok sütun, boş başlık,
terimsiz başlık) 422 `term_list_layout_invalid` kodunu taşır. Arayüz reddi "“{dosya adı}”
yüklenemedi." başlığıyla, iletiyi "Beklenen biçim" kısmı olmadan, altında örnek tabloyla (A1
"Terim"; altında "kredi kartı limit doluluk oranı", "sektör bazlı mevduat dağılımı", "müşterinin
kredi risk skoru"; B sütunu boş) ve dört kuralla gösterir: "Tek sütun: terimler yalnız A sütununda;
diğer sütunlar boş.", "İlk satır başlıktır: her zaman başlık sayılır ve aranmaz (ör. “Terim”).",
"Her satırda bir terim: boş satırlar ve tekrarlar atlanır; en fazla 200 terim.", "Yalnız ilk sayfa
okunur."

Requirement 4: Kurumda çalışan bir liste varsa yeni liste dosya okunmadan 409 `term_list_running`
alır. İleti, çalışan listenin sahibi isteği yapan ziyaretçiyse "Bir liste zaten çalışıyor;
bitmesini bekleyin ya da durdurun.", değilse "Başka bir kullanıcının listesi çalışıyor; bitince
yeniden deneyin." olur; başkasının listesinin adı ve sahibi söylenmez. Çalışan liste yoksa ve açılışta ilk arama
indeksi henüz kurulmadıysa dosya okunmadan 503 `search_index_not_ready` ("Arama indeksi
hazırlanıyor; biraz sonra yeniden deneyin.") döner; uygulama kapanırken 503 `analysis_unavailable`
döner ([question-analysis](../004-question-analysis/PRD.md)). Boş gövde de dosya olarak okunur ve
"Dosya Excel (.xlsx) olarak okunamadı." iletisiyle 422 `term_list_not_xlsx` alır (kaynakla aynı).
Okuma başarılıysa tek işlemde liste kaydı
(dışa açık kimlik `public_id`, sahip olarak isteği yapan ziyaretçi ile kayıt anındaki IP adresi
ve makine adı (anonymous-visitor Requirement 7), dosya adı, başlık, okuma notları,
terim sayısı, başlangıçtaki sözlük sürümü, durum "sürüyor",
başlangıç zamanı) ve terimleri sırayla yazılır; yanıt 201 ve Requirement 7'deki anlık durumdur;
liste hemen yürümeye başlar. İki başlatma isteği aynı anda gelse de en çok biri başarılı olur;
diğeri 409 alır (Decision 3).

Requirement 5: Terimler dosyadaki sırayla, her biri question-analysis'in tek soru akışından en çok
5 tablo önerisiyle ve kayıtlı cevap kullanımına izin verilerek (yeniden analiz zorlanmadan)
cevaplanır (Decision 6). Liste terimlerini analiz sırasına tek tek verir: bir terimin analizi
bitmeden sıradaki terim sıraya girmez ve liste kendi iki terimini aynı anda çalıştırmaz
(Decision 4). Böylece liste sürerken sorulan tek soru, listenin kalan terimlerini değil, en çok o
anda çalışan terimin bitmesini bekler. Her terimin analizi liste sahibi ziyaretçinin analizi olarak
analiz kaydına yazılır ve kayıt, terimin hangi listenin kaçıncı terimi olduğunu gösterir (kaynakta
`origin` = `"<dosya adı> #<sıra>"`; alanın biçimi [analysis-records](../008-analysis-records/PRD.md)
PRD'sinindir).

Requirement 6: Bir terim bitince cevabı hemen, tek işlemde veritabanına yazılır: cevap, cevabın
nasıl üretildiği (analist, kayıtlı cevap ya da "Analiz yapılamadı"), sonuç (VAR, KISMEN VAR,
BULUNAMADI), terimin süresi ve bitiş zamanı; aynı işlemde listenin biten terim sayısı ve geçen
süresi güncellenir. Cevap sözlükten bağımsız, kendi içinde tam saklanır: önerilen her tablonun ve
kolonun adı, açıklaması, eş anlamlıları, kişisel veri (KVKK) işareti ve veri seti grubu dahil
(Decision 5). Sözlük
sonradan yeniden içe aktarılsa ya da bir kolon sözlükten çıksa da terim ayrıntısı ve raporlar
cevabın yazıldığı gibi açılır. Analistin yazdığı terim cevabı, tek soruda olduğu gibi kayıtlı
cevaplara eklenir ([question-analysis](../004-question-analysis/PRD.md)); kayıtlı cevapla
cevaplanan terim "önceki cevap" olarak işaretlenir.

Requirement 7: Anlık durum şu alanları taşır: kimlik, dosya adı, sahip (dışa açık kimlik ve görünen
ad; sahip ziyaretçiyse görünen ad boştur), başlık, okuma notları, liste durumu (`running` sürüyor, `completed` tamamlandı, `cancelled`
durduruldu, `interrupted` yarıda kesildi), durdurma istendi bayrağı, toplam terim, biten terim
(cevaplanan ve hatalı), geçen süre, kalan süre tahmini, yükleme ve bitiş zamanı, başlangıçtaki
sözlük sürümü ve terim satırları. Terim durumu cevabı varsa `answered`, hatası varsa `error`,
çalışan terimse `running`, liste durdurulmuş ya da yarıda kesilmişse `stopped`, değilse
`queued`'dur. Kalan süre tahmini liste çalışırken ve en az bir terim bitmişse biten terimlerin
ortalama süresi çarpı kalan terim sayısıdır, aksi halde boştur. Geçen süre listenin çalıştığı
dilimlerin toplamıdır; durdurma ya da yarıda kesilme ile sürdürme arası sayılmaz. Terim satırı;
sıra, terim, durum, sonuç, özet (cevabın özeti ya da hatanın güvenli iletisi), eksik bilgi, en iyi
tablo (anahtar, ad, güven, seviye; oylardan etkilenmemiş ilk öneri), cevabın nasıl üretildiği
(`analyst`, `reused`, `unavailable`) ve süreyi taşır; terimin tam cevabını taşımaz. Anlık durum en
çok 200 terim satırı içerdiği için sayfalanmaz.

Requirement 8: Sahip "Durdur" dediğinde liste "durdurma istendi" olur; 5 saniye
içinde listenin yeni bir model çağrısı başlamaz, çalışan terimin model çağrıları kesilir (iptal
mekanizması [question-analysis](../004-question-analysis/PRD.md) PRD'sindedir) ve liste
"durduruldu" olur. Durdurma anında çalışan terim cevapsız kalır, hata sayılmaz; o ana kadar
cevaplanan terimler saklı kalır. Çalışmayan listeyi durdurmak hiçbir şeyi değiştirmez ve aynı anlık
durumu döndürür.

Requirement 9: Sahip, çalışmayan (durdurulmuş, yarıda kesilmiş ya da tamamlanmış) listesini
sürdürür. Cevabı olan terimler korunur ve yeniden sorulmaz; "Analiz yapılamadı" sonucu da cevap
sayılır ve yeniden sorulmaz. Cevapsız (durdurulmuş ya da yarıda kesilmiş) ve hatalı terimler dosya
sırasıyla yeniden sorulur (kaynakla aynı, `App.list_resume`). Kurumda başka çalışan liste varsa 409
`term_list_running`; yeniden sorulacak terim yoksa 409 `term_list_nothing_to_resume` ("Bu listenin
bütün terimleri cevaplandı; devam edecek terim yok.") döner; liste zaten çalışıyorsa anlık durum
değişmeden döner. Sürdürülen listenin geçen süresine aradaki bekleme eklenmez.

Requirement 10: Sunucu süreci kapatılırken (dağıtım, yeniden başlatma) çalışan liste "yarıda
kesildi" olarak işaretlenir ve çalışan terim cevapsız kalır. Süreç beklenmedik biçimde ölürse
işaretleme açılışta yapılır: durumu "sürüyor" kalmış liste "yarıda kesildi" olur. Backend tek kopya
çalıştığı ve güncellemede eski ve yeni süreç birlikte çalışmadığı için
([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Decision 5) açılışta "sürüyor" görünen liste başka bir süreçte yürüyor olamaz; iki sürecin
çakışmasına karşı ayrı kilit tutulmaz. Süreç çalışırken liste görevi beklenmedik biçimde sonlanırsa
her dakika yapılan denetim, bu süreçte görevi olmayan "sürüyor" listeyi "yarıda kesildi" yapar.
Yarıda kesilen liste kendiliğinden sürdürülmez; sahibi onu
"Devam et" ile (Requirement 9) sürdürür (Decision 2). Kesilmeden önce cevaplanan terimler
kaybolmaz.

Requirement 11: Liste sayfadan bağımsızdır: sayfayı kapatmak ya da yenilemek veya tarayıcının
ağdan düşmesi listeyi durdurmaz (Decision 13). Ziyaretçi aynı tarayıcıda sayfayı yeniden açtığında
en yeni listesini üst çubuktaki "Liste" hapından açar (Requirement 15, 17).

Requirement 12: Terim ayrıntısı, cevaplanmış terimin tam cevabını tek soru cevabıyla aynı biçimde ve
aynı görünümle döndürür; dönmeden önce oylar isteği yapan ziyaretçiye göre uygulanır
([answer-feedback](../006-answer-feedback/PRD.md), anonymous-visitor Requirement 5). Cevaplanmamış terim için 404
`term_list_item_not_answered` döner. Ayrıntıdaki "⬇ Excel raporu" o terimin tek soru raporunu
(biçimi [question-analysis](../004-question-analysis/PRD.md) PRD'sindedir) saklanan cevaptan
üretir. Ayrıntıdaki "↻ Yeniden analiz et" tek soru olarak çalışır ve listenin saklanan cevabını
değiştirmez.

Requirement 13: Liste raporu tek çalışma kitabıdır ve kaynaktaki `write_list_report` ile aynı içerik
ve biçimdedir:

- **Özet** sayfası: başlık "Veri Ambarı Veri Sözlüğü – Toplu Talep Analizi"; "Liste" (dosya adı),
  "Kaynak sözlük" (kaynaktaki gibi `dictionary.jsonl` ve listenin başladığı andaki sözlük sürümü;
  [dictionary-management](../001-dictionary-management/PRD.md) Requirement 17), "Üretim", "Sonuç"
  ("{n} terim: {a} VAR, {b} KISMEN VAR, {c} BULUNAMADI"; cevapsız terim varsa ", {k} cevapsız",
  liste durdurulmuş ya da yarıda kesilmişse " — liste durduruldu, rapor yarım"), "Cevabı üreten"
  ("{n} terim analist (dil modeli)"; analiz edilemeyen terim varsa uyarı rengiyle ", {m} terim
  analiz edilemedi — model bağlı değil ya da çalışamadı (Yöntem sütunu)"), okuma notu varsa notları
  yan yana yazan "Dosya" satırı; altında terim başına bir satır: #, Terim (Öneriler sayfasındaki ilk
  satırına bağlantı), Sonuç, En İyi Tablo, Güven, Seviye, Özet, Yöntem ("Analist", "Yapılamadı" ya
  da "-"), Süre (sn), Eksik Bilgi.
- **Öneriler** sayfası: bütün terimlerin önerileri alt alta; sütunlar #, Terim, Sıra,
  Veritabanı.Şema.Obje, Veri Seti Grubu, Kapsadığı Bilgi, İlgili Alanlar, Gerekçe, Kısıt / Dikkat,
  Güven, Seviye, Kullanım Önerisi; önerisi olmayan terim tek satırdır ve Gerekçe sütununda cevabın
  özeti, hata iletisi ya da durum yazar.
- Cevapsız terimin sonucu liste çalışıyorsa "BEKLİYOR", durdurulmuş ya da yarıda kesilmişse
  "DURDURULDU", hatalıysa "HATA"dır. Renkler, sütun genişlikleri, süzgeç, dondurulmuş başlık ve
  sayı biçimleri kaynakla aynıdır.
- Rapor liste sürerken de alınır (ara rapor). İstek anında saklanan cevaplardan bellekte üretilir
  ve saklanmaz. Dosya adı `VSA_liste_<dosya adından kısa ad>_<YYYYMMDD_HHMM>.xlsx`'tir; "Üretim" ve
  dosya adındaki zaman raporun istendiği andır ve İstanbul saatiyle yazılır (Decision 10).
- Oylar raporu değiştirmez. Her metin hücreye metin olarak yazılır.

Requirement 14: Bütün uçlar oturum istemez; geçerli bir `X-Device-Id` ister ve isteği yapan
ziyaretçiyi ondan tanır
([anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)
Requirement 3). Başlık yoksa ya da geçersizse yanıt `400 device_id_required` olur. Anlık durum,
terim ayrıntısı, raporlar, durdurma ve sürdürme yalnız listeyi yükleyen ziyaretçiye açıktır.
Başkasının listesine erişen herkes (başka ziyaretçi; oturum belirteci gönderen `yonetici` dahil)
liste yokmuş gibi 404 `term_list_not_found` alır. Sahiplik her istekte sunucuda, `platform`
kiracısı kapsamında denetlenir (anonymous-visitor Decision 4).

Requirement 15: Listeler ucu, yalnız isteği yapan ziyaretçinin saklanan listelerini en yeni üstte
(aynı zamanda yüklenenler kimliğe göre) döndürür; ana ekran sayfa açılışında hap için en yeni
listeyi buradan bulur. Yanıt sayfalıdır (varsayılan 20, en çok 100 satır) ve her satır kimlik, dosya
adı, sahip, durum, durdurma istendi bayrağı, toplam, biten, yükleme ve bitiş zamanını taşır.

Requirement 16: Her sahibin (ziyaretçi ya da hesap) en yeni 5 listesi veritabanında kalıcı olarak
saklanır. Ziyaretçi altıncı listesini yüklediğinde en eski listesi terimleriyle birlikte, yeni listenin yazıldığı
işlemde kalıcı silinir (Decision 14). Süreye bağlı silme yoktur. Liste silmek o listenin
terimleriyle yapılmış analiz kayıtlarını silmez; terimlerin cevapları
[analysis-records](../008-analysis-records/PRD.md)'ta kalır.

Requirement 17: Ana ekranın liste arayüzü kaynaktaki işlevle React'te kurulur; kaynaktaki metinler
aynen `app/frontend/src/locales/tr.json`'a taşınır:

- Arama çubuğundaki Excel düğmesi (ipucu "Excel listesiyle ara · A sütunu, ilk satır başlık",
  erişilebilir adı "Excel listesiyle toplu arama"), yalnız `.xlsx` seçtiren dosya penceresi ve
  sayfanın herhangi bir yerine sürükle-bırak (arama çubuğu aydınlanır: "Excel listesini bırakın" ·
  "A sütunu · ilk satır başlık · altında her satırda bir terim").
- Yüklenirken "“{dosya adı}” okunuyor…"; reddedilirse Requirement 3'teki açıklama. Ziyaretçinin
  kendi listesi çalışırken yeni dosya bırakılırsa yükleme yapılmaz, çalışan liste gösterilir.
- Liste görünümü: dosya adı; ilerleme ("{n}/{N} terim tamamlandı" ve tahmin varsa " · kalan ≈
  {süre}"; "Durduruldu · {n}/{N} terim cevaplandı"; yeni "Yarıda kesildi · {n}/{N} terim
  cevaplandı"; "Tamamlandı · {N} terim, {süre}") ve " · başlık: “{başlık}”"; "■ Durdur" (liste
  çalışırken), "▶ Devam et" (liste durdurulmuş ya da yarıda kesilmişse ve cevapsız terimi kalmışsa,
  kaynakla aynı koşul; ipucu "Cevaplanan terimler korunur; kalan terimler sırayla aranır"), en az
  bir terim bitmişse "⬇ Şimdiye kadarki rapor" (çalışırken) ya da "⬇ Excel raporu"; ilerleme çubuğu;
  "ℹ" işaretli okuma notları; analiz edilemeyen terim varsa "{n} terim analiz edilemedi (model bağlı
  değil ya da çalışamadı). Model çalışınca bu terimleri yeniden arayın."
- Terim satırı: sıra; terim; "ÖNCEKİ CEVAP" ("Bu terim daha önce analiz edilmişti; kayıtlı cevap
  kullanıldı") ya da "YAPILAMADI" ("Bu terim analiz edilemedi (model bağlı değil ya da
  çalışamadı)") etiketi; en iyi tablo ve güveni; "eksik: …"; hata iletisi; durum (sonuç adı ya da
  "SIRADA", "ARANIYOR", "HATA", "DURDU"); süre ("{n} sn", bir dakikadan uzunsa "{n} dk").
  Cevaplanmış satıra tıklayınca cevap satırın altında açılır ya da kapanır ("Yükleniyor…"); yalnız
  durumu değişen satırlar yeniden çizilir, açık cevaplar yerinde kalır.
- Yoklama (sayfanın durumu belli aralıkla yeniden sorması): liste görünümü ya da hap görünürken ve
  liste çalışırken anlık durum 1,5 saniyede bir istenir; liste çalışmıyorsa istenmez (Decision 7).
- Hap: liste görünümü açık değilken üst çubukta "Liste {n}/{N}" (çalışırken yanan noktayla) ya da
  "Liste sonucu" görünür ("Toplu aramaya dön"); tıklayınca listeye döner. Sayfa açılışında
  ziyaretçinin saklanan listesi varsa hap en yenisi için görünür.
- Sürdürme hatası kaynaktaki gibi tarayıcının uyarı penceresiyle (`alert`) gösterilir; durdurma
  isteği başarısız olursa ileti gösterilmez, liste görünümü yenilenir.
- Liste arayüzünün görünümü kaynakla birebir aynıdır; görünür yeni öğe eklenmez
  ([dictionary-explorer](../007-dictionary-explorer/PRD.md) Decision 3; görsel eşdeğerlik kanıtı
  orada Acceptance 5).
- İlerleme çubuğunun genişliği gibi dinamik değerler tarayıcının stil nesnesi (CSSOM) ile verilir;
  çalışırken `<style>` öğesi ekleyen bileşen kullanılmaz
  ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 14).

Requirement 18: Bir terimin analizi beklenmedik bir hatayla biterse terim `error` olur; anlık
duruma, ekrana ve rapora yalnız güvenli Türkçe ileti gider: "Bu terim analiz edilirken beklenmeyen
bir hata oluştu; listeyi sürdürerek yeniden deneyin." İstisna metni, sunucu yolu ve model adresi
gitmez; ayrıntı yalnız sunucu günlüğündedir ve terim metnini içermez. Bir terimin hatası sonraki
terimleri durdurmaz.

Requirement 19: Okuma kuralları ve rapor biçimi ağ, veritabanı ve dosya erişimi yapmayan saf
işlevlerdir; liste işi `services` katmanında; veritabanı erişimi `infrastructure` deposundadır;
Excel'i bellekte açma ve açılmış boyut denetimi dictionary-management'ın ortak güvenli Excel
okuyucusundadır.

## API sözleşmesi

Ön ek `/api/dwhnavigator/v1`. Bütün uçlar oturum belirteci ve kiracı başlığı istemez; geçerli
`X-Device-Id` başlığı ister (Requirement 14); başlık yoksa ya da geçersizse her uç `400
device_id_required` döner. "Sahip" listeyi yükleyen ziyaretçidir. Hata zarfı
`{"detail":{"code":"...","message":"..."}}` biçimindedir. `{list_id}` listenin dışa açık kimliği
(`public_id`), `{position}` terimin listedeki sırasıdır (1'den başlar). Şema doğrulama hataları
(ör. geçersiz sayfa değeri) ortak zarfla 422 döner.

| Uç | Yetki | Başarı | Hatalar |
|---|---|---|---|
| `POST /term-lists` (ham Excel gövdesi, `X-Filename`) | ziyaretçi (`X-Device-Id`) | 201 → anlık durum (Requirement 7) | 400 `device_id_required`; 409 `term_list_running`; 413 `upload_too_large`; 415 `unsupported_media_type`; 422 `term_list_not_xlsx`, `term_list_too_large_unpacked`, `term_list_too_many_rows`, `term_list_layout_invalid`, `term_list_term_too_long`, `term_list_too_many_terms`; 503 `search_index_not_ready`, `analysis_unavailable` |
| `GET /term-lists?page=&page_size=` | ziyaretçi (yalnız kendi listeleri) | 200 → satırlar (`id`, `name`, `owner`, `status`, `stop_requested`, `total`, `done`, `created_at`, `finished_at`) ve sayfa bilgisi (`page`, `page_size`, `total`) | 400 `device_id_required`; 422 |
| `GET /term-lists/{list_id}` | sahip | 200 → anlık durum | 400 `device_id_required`; 404 `term_list_not_found` |
| `GET /term-lists/{list_id}/items/{position}` | sahip | 200 → terimin tam cevabı (question-analysis cevap biçimi ve answer-feedback alanları) | 400 `device_id_required`; 404 `term_list_not_found`, `term_list_item_not_answered` |
| `GET /term-lists/{list_id}/items/{position}/report` | sahip | 200 → terimin tek soru Excel raporu (indirme dosyası) | 400 `device_id_required`; 404 `term_list_not_found`, `term_list_item_not_answered` |
| `GET /term-lists/{list_id}/report` | sahip | 200 → liste Excel raporu (indirme dosyası) | 400 `device_id_required`; 404 `term_list_not_found` |
| `POST /term-lists/{list_id}/cancel` | sahip | 200 → anlık durum (`stop_requested: true`; çalışmayan listede değişmeden) | 400 `device_id_required`; 404 `term_list_not_found` |
| `POST /term-lists/{list_id}/resume` | sahip | 200 → anlık durum (zaten çalışıyorsa değişmeden) | 400 `device_id_required`; 404 `term_list_not_found`; 409 `term_list_running`, `term_list_nothing_to_resume`; 503 `search_index_not_ready`, `analysis_unavailable` |

Anlık durum alanları: `id`, `name`, `owner` (`public_id`, `display_name`; ziyaretçide
`display_name` boş), `header`, `notes[]`,
`status` (`running`, `completed`, `cancelled`, `interrupted`), `stop_requested`, `total`, `done`,
`elapsed_ms`, `eta_ms` (boş olabilir), `created_at`, `finished_at`, `dictionary_version`, `items[]`
(`position`, `term`, `state` (`queued`, `running`, `answered`, `error`, `stopped`), `verdict`,
`summary`, `missing[]`, `best` (`key`, `name`, `score`, `level`; boş olabilir), `flow` (`analyst`,
`reused`, `unavailable`; cevapsızsa boş), `elapsed_ms`). Zamanlar saat dilimini taşıyan ISO 8601
metnidir (uluslararası tarih-saat yazımı).

Kaldırılan uçlar: kaynaktaki `POST /api/list`, `GET /api/list/<id>`,
`GET /api/list/<id>/item/<n>`, `POST /api/list/<id>/cancel`, `POST /api/list/<id>/resume`,
`GET /api/list/<id>/report` ve `voter` sorgu parametresi; yerlerini yukarıdaki uçlar alır.

## Güvenlik ve yetkilendirme

- Görme, durdurma, sürdürme ve indirme yetkisi her istekte sunucuda, `X-Device-Id`'den tanınan
  ziyaretçinin sahipliğine göre denetlenir; sorgular `platform` kiracısı kapsamındadır. Görme yetkisi
  olmayan liste 404 alır. Cihaz kimliği bir kimlik bilgisi değildir: onu bilen biri o ziyaretçinin
  listelerini görebilir; kimliğin taşınması, saklanması ve loglardan uzak tutulması
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md) Güvenlik
  bölümündedir.
- Yüklenen dosya yalnız isteğin işlendiği süre boyunca bellekte tutulur (dosya sistemine yazılmaz),
  istek bitince bırakılır; kalıcı olarak hiçbir yere yazılmaz. Dosya adı yalnız ad
  kısmıyla saklanır, hiçbir yol ya da komut kurmaz (Decision 12).
- Dosya ortak güvenli Excel okuyucusuyla
  ([dictionary-management](../001-dictionary-management/PRD.md) Requirement 2) ve sayfa başına 2.001
  satır ve 50 sütun sınırlarıyla okunur; formüller çalıştırılmaz (Requirement 2).
- Rapor hücrelerine yazılan terim, soru ve model metni formül olamaz; rapor dosya adı yalnız küçük
  harf, rakam ve alt çizgiden oluşur ve indirme başlığına güvenle yazılır.
- Cihaz kimliği adrese (URL) konmaz; raporlar ana ekranın ortak API istemcisiyle `X-Device-Id`
  başlığı taşıyan istekle alınıp tarayıcıda dosya olarak kaydedilir.
- Hata iletileri istisna metni, sunucu yolu, model adresi ya da başka kullanıcının listesi
  hakkında bilgi içermez (Requirement 4, 18).
- Terimlerin analizleri liste sahibi ziyaretçinin adına yapılır ve analiz kaydına o ziyaretçiyle
  yazılır; listeyi yalnız sahibi sürdürebildiği için kimse başkası adına analiz başlatamaz.
- Durum değiştiren uçlar (yükleme, durdurma, sürdürme) siteler arası istek denetiminden geçer
  ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 13;
  anonymous-visitor Güvenlik bölümü).

## Veri ve geçiş

- Yeni tablo `term_list` (bu PRD'nin): dışa açık kimlik, kiracı, sahip (hesap ya da ziyaretçi;
  `owner_id` hesap tablosuna, ziyaretçi sütunu `visitor` tablosuna bağ, tam biri dolu; kayıt anındaki
  IP adresi ve makine adı; sütunların sahibi
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md) "Veri ve
  geçiş" bölümüdür), dosya adı, başlık, okuma notları, durum (`running`, `completed`, `cancelled`,
  `interrupted`), durdurma istendi bayrağı, çalışan terimin sırası (boş olabilir), terim sayısı,
  başlangıçtaki sözlük sürümü, son çalışma diliminin başlangıcı,
  önceki dilimlerin toplam süresi, bitiş zamanı ve ortak zorunlu sütunlar (rules/41). Kiracı başına
  yalnız bir "sürüyor" satırına izin veren kısmi benzersiz dizin (yalnız `running` satırlarına
  uygulanan tekillik kuralı; Decision 3); hesap sahibi ve yükleme zamanı ile ziyaretçi sahibi ve
  yükleme zamanı üzerinde dizinler (listeleme ve sahip başına 5 liste kuralı).
- Yeni tablo `term_list_item` (bu PRD'nin): listeye bağ ve terimin sırası (ikisi birlikte birincil
  anahtardır; dışa açık kimlik yoktur, rules/41'deki bağlı satır istisnası), terim, cevap
  (kendi içinde tam cevap; JSONB: PostgreSQL'in yapılandırılmış veri sütunu), cevabın nasıl
  üretildiği (`analyst`, `reused`, `unavailable`), sonuç, hata kodu ve güvenli iletisi, süre, bitiş
  zamanı. Sütun ve tablo açıklamaları göçle veritabanına yazılır (rules/43).
- Liste silinince terimleri aynı işlemde silinir. En eski listenin silinmesi kalıcıdır, yazılımsal
  silme (satırı silindi diye işaretleyip tutma) değildir: amaç verinin tutulmamasıdır (Requirement
  16).
- Terimin analiz kaydı ([analysis-records](../008-analysis-records/PRD.md)) listeye ve sıraya
  değer olarak işaret eder; o alanın sahibi analysis-records PRD'sidir. Liste silinmesi analiz
  kaydını silmez.
- Listede saklanan IP adresi ve makine adı kişisel veridir; liste silinince onunla birlikte silinir
  (anonymous-visitor "Veri ve geçiş").
- Şemanın sahibi SQLAlchemy modelleridir; değişiklik Alembic göçüyle (veritabanı yapısını sürüm
  sürüm kuran betik) gelir; göç geri alınıp yeniden uygulanabilir.
- Kaynaktan taşınacak veri yoktur: listeler kaynakta yalnız bellekteydi.

## Gözlemlenebilirlik

- Yapılandırılmış günlük olayları: `term_list.started` (liste kimliği, sahibin (ziyaretçi ya da hesap)
  dışa açık kimliği, terim sayısı; cihaz kimliği, IP adresi ve makine adı yazılmaz), `term_list.stop_requested` (liste kimliği),
  `term_list.resumed` (liste kimliği, yeniden sorulacak terim sayısı), `term_list.finished` (liste
  kimliği, durum, analist, kayıtlı cevap, analiz yapılamadı ve hata sayıları, çalışma süresi),
  `term_list.interrupted` (liste kimliği, sebep `shutdown`, `startup` ya da `check`),
  `term_list.upload_rejected` (hata kodu), `term_list.report_downloaded` (liste kimliği, tür `list`
  ya da `item`), `term_list.term_failed` (liste kimliği, hata sınıfının adı; terim analiz sırasına
  verilemedi ve `error` oldu), `term_list.run_failed` (liste kimliği, hata sınıfının adı; liste görevi
  beklenmedik biçimde sonlandı, dakikalık denetim listeyi yarıda keser). Terim metni, dosya
  adı, başlık, cevap, tablo ve kolon adı yazılmaz. Arka planda yürüyen listenin olayları listeyi
  başlatan ya da sürdüren isteğin istek kimliğini (`request_id`) taşır.
- Ölçümler: başlatılan listeler `dwhnavigator_term_lists_started_total`; biten listeler
  `dwhnavigator_term_lists_finished_total{status}` (`status`: `completed`, `cancelled`,
  `interrupted`); biten terimler `dwhnavigator_term_list_terms_total{outcome}` (`outcome`:
  `analyst`, `reused`, `unavailable`, `error`; durdurulan terim sayılmaz); reddedilen yüklemeler
  `dwhnavigator_term_list_uploads_rejected_total{reason}` (`reason`: Requirement 2 ve 3'teki hata
  kodları, `term_list_running`; kümede olmayan değer `other`); çalışan liste sayısı
  `dwhnavigator_term_lists_running` (0 ya da 1); indirilen raporlar
  `dwhnavigator_term_list_reports_total{kind}` (`kind`: `list`, `item`). Ziyaretçi, hesap, liste ve
  terim ölçüme girmez.
- İz: listeye ait ayrı iz aralığı yoktur; her terimin analizi question-analysis PRD'sindeki analiz
  izini üretir. Ortak kurallar ve saklama süresi
  [application-foundation alanında](../../../application-foundation/DOMAIN.md) tanımlıdır. Tüketen
  test: `app/backend/tests/integration/test_telemetry_signals.py`.

## Dağıtım etkisi

- Yeni göç (`term_list`, `term_list_item`). Yeni sır, yeni ağ çıkışı, Kubernetes kurulum paketinde
  (chart) yeni nesne ve yeni ortam ayarı yoktur; 2.001 satır, 50 sütun, 500 karakter, 200 terim, 5
  liste ve 1,5 saniye sabittir (20 MB ve 100 MB ortak okuyucunundur).
- Yükleme gövdesi: küme giriş kapısının (ingress) gövde sınırı, daha büyük dosyayı uygulamaya
  ulaşmadan 413 ile keser (ingress-nginx'in varsayılanı 1 MB). Kurala uyan bir liste dosyası
  genellikle 1 MB'ın çok altındadır; sınırın değeri sözlük içe aktarmasıyla ortaktır ve
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindedir.
- Kapanış: sunucu kapsayıcısının kapanırken beklenen süresi listeyi "yarıda kesildi" olarak
  işaretlemeye ve çalışan terimin model çağrısını kesmeye yetmelidir (birkaç saniye). Güncellemede eski
  ve yeni süreç birlikte çalışmaz (`Recreate`; kubernetes-delivery Decision 5); bu PRD'nin
  Requirement 10'undaki açılış denetimi buna dayanır.
- Yoklama yükü: açık sayfa başına 1,5 saniyede bir küçük istek; vekil sunucuda ek ayar gerekmez.
- Veritabanı boyutu: tam saklanan cevaplarla liste başına birkaç MB (200 terim × yaklaşık 30 KB);
  sahip başına en çok 5 liste ve çalışan liste.

## Test stratejisi

- **Okuma kuralları:** Kaynaktaki `tests/test_loader.py` liste testleri (`test_term_list_parsing`,
  `test_term_list_file`, `test_term_list_rejects_unclear_files`, `test_term_list_limit`) aynen
  taşınır. Fark testi (aynı girdiyi kaynak ve hedef kodla çalıştırıp çıktıları karşılaştıran test):
  kaynak paketin `parse_term_sheet` işleviyle hedefinki, örnek satır kümelerinde aynı terimleri,
  başlığı, notları ve hata iletilerini verir. Eklenen testler: 2.001 ve 2.002 satır sınırı, ikinci
  sayfadaki fazla satır, 50. sütunun ötesi, açılmış boyutu 100 MB'ı aşan dosya, boyutu 20 MB'ı aşan
  gövde, `.xls` ve `.csv` dosyası, dosya adı temizleme.
- **Rapor:** Aynı liste girdisiyle kaynaktaki `write_list_report` ve hedefin çalışma kitabı hücre
  hücre aynıdır (değer, yazı tipi, dolgu, birleşik hücre, bağlantı, süzgeç, dondurulmuş satır, sayı
  biçimi); çalışırken, durdurulmuş, yarıda kesilmiş ve hatalı terimli listeler; "=" ile başlayan
  terimin metin kalması; İstanbul saatiyle "Üretim".
- **Hizmet testleri** (gerçek PostgreSQL, sahte analiz): dosya sırası; terimlerin sıraya tek tek
  girmesi ve liste sürerken sorulan tek sorunun en çok bir terim beklemesi; her terimden sonra
  kalıcı yazma; durdurmada 5 saniye içinde yeni model çağrısı olmaması; sürdürmede cevaplanmış
  terimin yeniden sorulmaması (kaynaktaki `test_term_list_resumes_after_stop` senaryosu dahil);
  "Analiz yapılamadı" terimlerinin yeniden sorulmaması, hatalı terimlerin yeniden sorulması;
  kapanışta ve açılış denetiminde "yarıda kesildi"; süreçte görevi olmayan "sürüyor" listenin
  dakikalık denetimle "yarıda kesildi" olması; iki başlatma isteğinin yarışında tek kazanan; kayıtlı
  cevap kullanımı ve "önceki cevap" işareti; sözlük yeniden içe aktarıldıktan sonra terim
  ayrıntısının ve raporun açılması; beklenmeyen hatada güvenli ileti.
- **Sunucu ucu (API) testleri:** oturumsuz isteğin `X-Device-Id` ile çalışması, başlıksız ya da
  geçersiz başlıkla 400 `device_id_required`; 404, 409, 413, 422 kodları; 409 iletisinin çalışan
  listenin sahibi ziyaretçiyle isteği yapan ziyaretçinin karşılaştırılmasıyla seçilmesi; sahibin
  görmesi, başka cihaz kimliğinin ve oturum belirteci gönderen yöneticinin bütün liste uçlarında 404
  alması; terim analizlerinin analiz kaydına sahip ziyaretçiyle yazılması; terim ayrıntısında
  oyların isteği yapan ziyaretçiye göre uygulanması; sayfalama ve sıralama; ziyaretçi başına en yeni
  5 liste (altıncı yüklenince en eskisinin silinmesi, analiz kayıtlarının kalması);
  kaynaktaki `test_term_list_end_to_end` ve `test_term_list_rejects_bad_files` senaryoları; günlükte
  terim metni ve dosya adı bulunmaması.
- **Ön yüz testleri (Vitest):** Excel düğmesi ve sürükle-bırak, ret açıklaması, ilerleme metinleri,
  düğmelerin görünme koşulları, satır etiketleri ve durumları, yalnız değişen satırın yeniden
  çizilmesi, ayrıntının açılıp kapanması, yoklamanın liste bitince durması, hap ve sayfa açılışında
  en yeni listeyle geri gelmesi, "Devam et" düğmesinin kaynaktaki koşulla görünmesi, sürdürme
  hatasının uyarı penceresiyle gösterilmesi, liste isteklerinin ve rapor indirmelerinin oturum
  belirteci olmadan `X-Device-Id` başlığıyla gitmesi.
- **API tanım dosyası (OpenAPI):** kayıtlı yapıtla aynıdır; ön yüz tipleri ondan üretilir.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

Bu yetenek vektör ya da gömme (metni sayı dizisine çeviren yöntem) kullanmaz; kaynak vektör
aramasını ADR-039 ile kaldırdı.

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: taşınan okuma testleri ve `parse_term_sheet`
  fark testi geçer; sınır testleri 413 ve 422 kodlarını doğrular (Requirement 1–3).
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: rapor fark testi, kaynaktaki
  `write_list_report` ile hücre hücre aynılığı ve formül korumasını doğrular (Requirement 13).
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: gerçek PostgreSQL ve sahte analizle hizmet
  testleri sırayı, tek tek sıraya girmeyi, kalıcı yazmayı, durdurmayı, sürdürmeyi, yarıda kesilmeyi,
  tek çalışan listeyi, kendi içinde tam cevabı ve güvenli hata iletisini doğrular (Requirement 4–10,
  18, 19).
- [ ] Acceptance 4: L1 — Otomatik testlerden geçti: sunucu ucu (API) testleri cihaz kimliğiyle
  tanınmayı, görünürlüğü, listelemeyi, terim ayrıntısını, terim raporunu ve sahip başına 5 liste
  kuralını doğrular; API tanım dosyası
  kayıtlı yapıtla aynıdır (Requirement 4, 12, 14–16).
- [ ] Acceptance 5: L1 — Otomatik testlerden geçti: ön yüz testleri ve tip sapması kapısı geçer
  (Requirement 17); telemetri testi Gözlemlenebilirlik bölümündeki sinyalleri ve günlükte terim
  metni bulunmadığını doğrular.
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose ortamında (uygulamanın
  geliştirici makinesinde kapsayıcılarla çalışan kurulumu) bağlı bir sohbet modeliyle tarayıcıdan
  10 terimlik liste yüklenir; ilerleme terim terim görünür; liste durdurulup
  sürdürülür; ara rapor ve son rapor indirilir ve Excel'de Türkçe karakterlerle açılır; terim
  ayrıntısı açılır ve oy verilebilir; günlük çıktısında terim metni bulunmaz (Requirement 1, 5–9,
  12, 13, 17).
- [ ] Acceptance 7: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da liste sürerken sayfa
  kapatılıp açılır ve liste sürmeye devam eder; sunucu kapsayıcısı yeniden başlatılır ve liste
  "Yarıda kesildi" görünür; "Devam et" sonrası analiz kayıtları cevaplanmış hiçbir terimin yeniden
  sorulmadığını gösterir (Requirement 6, 10, 11).
- [ ] Acceptance 8: L2 — Gerçek istemci/ortamda doğrulandı: iki ayrı tarayıcı bağlamıyla (iki
  ziyaretçi, oturumsuz) ikinci ziyaretçi birincinin listesini göremez, raporunu indiremez, durduramaz
  ve sürdüremez (404); ikinci ziyaretçi kendi listesini başlatamaz (409, başkasının listesi
  iletisiyle); yönetim ekranına giren `yonetici` listeye erişemez (404) (Requirement 4, 8, 9, 14,
  15).
- [ ] Acceptance 9: L2 — Gerçek istemci/ortamda doğrulandı, nonprod: canlı olmayan test kümesinde
  (nonprod) giriş kapısı (ingress) üzerinden liste yüklenir, yoklama çalışır ve liste tamamlanır;
  liste sürerken yapılan dağıtım listeyi "Yarıda kesildi" yapar ve liste sürdürülerek tamamlanır
  (Requirement 2, 10, 17).

## Kararlar

- Decision 1: Liste her terimi tek sorunun geçtiği akıştan geçirir (ADR-033); listeye özgü analiz,
  sıralama ya da istem (prompt) yoktur. Gerekçe: ölçülen cevap kalitesi bu akışındır; ayrı bir yol
  ayrı bakım ve ayrı ölçüm ister.
- Decision 2: Liste kalıcıdır: liste ve her terimin cevabı terim bitince veritabanına yazılır;
  sunucu yeniden başlayınca liste "yarıda kesildi" olur ve kendiliğinden sürdürülmez, sahibi
  "Devam et" ile sürdürür. Gerekçe: her dağıtım sunucuyu yeniden başlatır ve 200
  terimlik liste yaklaşık iki buçuk saat sürer; bellekte tutmak (kaynak) emeği kaybettirir.
  Kendiliğinden sürdürme, dağıtımdan sonra kimse izlemezken model sunucusunu saatlerce meşgul eder
  ve süreci düşüren bir hata varsa her açılışta yeniden düşürür.
- Decision 3: Kurumda aynı anda tek liste çalışır (kaynakla aynı). Gerekçe: model sunucusu seri
  çalışır; iki liste birlikte hiçbirini hızlandırmaz, tek soruların bekleme süresini uzatır.
  Veritabanındaki kısmi benzersiz dizin, iki isteğin yarışında tek kazanan bırakır.
- Decision 4: Liste terimlerini analiz sırasına tek tek verir. Gerekçe: bütün terimler birden sıraya
  girseydi, ardından sorulan tek soru 200 terimin arkasında kalırdı; kaynakta da tek soru en çok
  çalışan terimi bekliyordu.
- Decision 5: Terim cevabı sözlükten bağımsız, tam saklanır. Gerekçe: kayıtlı cevaplar kolonları
  yalnız anahtarlarıyla saklar ve sözlük değişince kullanılamaz olur (onlar için doğru davranış
  budur); liste ise kullanıcının raporudur ve sözlük yeniden içe aktarılsa da açılmalıdır.
- Decision 6: Liste kayıtlı cevapları kullanır ve analistin yazdığı terim cevaplarını kayıtlı
  cevaplara ekler; listeye özel "yeniden analiz" seçeneği yoktur (kaynakla aynı). Gerekçe: aynı
  terim tek soruda ve listede aynı cevabı alır; kayıtlı cevaplar ayarla kapatılabilir
  ([search-settings](../009-search-settings/PRD.md)); tek terimi yenilemek için ayrıntıda
  "↻ Yeniden analiz et" vardır.
- Decision 7: İlerleme yoklamayla alınır; canlı olay akışı (SSE: sunucunun tarayıcıya sürekli olay
  gönderdiği bağlantı) kullanılmaz. Gerekçe: liste sayfadan bağımsız ve saatlerce sürer; uzun
  bağlantılar vekil sunucu zaman aşımına takılır ve sayfa her açıldığında yeniden kurulmalıdır;
  anlık durum küçük ve sınırlıdır (en çok 200 satır); kaynak da yokluyordu.
- Decision 8: Liste onu yükleyen ziyaretçiye aittir; yalnız o ziyaretçi (aynı cihaz kimliği) görür,
  durdurur ve sürdürür; `yonetici` rolünün listeler üzerinde ayrı bir yetkisi ve yönetici görünümü
  yoktur (kaynakla aynı; sahipliğin ziyaretçiye göre olması
  [anonymous-visitor](../../../application-foundation/PRDs/003-anonymous-visitor/PRD.md)
  Requirement 5 ve Decision 8'dir). Gerekçe: kaynakta listeyi yalnız onu başlatan sayfa görüyordu;
  terimler ve cevaplar ziyaretçinin iş talepleridir; yönetici analiz kayıtlarında herkesin terim
  analizlerini zaten görür; sürdürme analizleri sahibin adına başlatır.
- Decision 9: Yüklenen dosya saklanmaz; açılmış boyutu 100 MB ile sınırlıdır. Gerekçe: Excel kurum
  içi veridir ve kapsayıcıda dosya deposu yoktur; 20 MB'lık sıkıştırılmış bir dosya açılınca
  gigabaytlarca yer tutabilir (sıkıştırma bombası). Kurala uyan en büyük liste (2.000 satır × 500
  karakter) açılınca birkaç MB'tır; 100 MB, başka sayfalarında veri taşıyan olağan çalışma
  kitaplarına da yer bırakır.
- Decision 10: Okuma kuralları ve rapor biçimi kaynakla aynıdır; yarıda kesilen liste raporda
  durdurulmuş liste gibi yazılır; rapordaki zamanlar İstanbul saatidir, saklanan zamanlar UTC
  (evrensel saat). Gerekçe: rapor biçimi korunan çekirdeğin parçasıdır ve kullanıcılar ona alışkındır;
  yarıda kesilmenin kullanıcı için anlamı durdurmayla aynıdır ve yeni bir rapor durumu biçimi
  değiştirirdi; kaynak sunucunun yerel saatini yazıyordu, kapsayıcı ise UTC çalışır.
- Decision 11: `vsa ask -i` komut satırı kaldırılır; toplu arama yalnız arayüzden ve sunucu
  uçlarındandır (bağlayıcı mimari karar 10). Gerekçe: komut satırı kayıtlı cevap kullanmıyor ve
  analiz kaydı yazmıyordu; aynı liste iki yolda farklı sonuç verebiliyordu.
- Decision 12: Dosya adı yalnız ad kısmıyla saklanır (klasör kısmı atılır), denetim karakterleri
  çıkarılır, en çok 255 karakterdir; boş kalırsa `liste.xlsx` olur. Gerekçe: ad yalnız gösterilir ve
  rapor adına kısaltılarak girer; tarayıcının gönderdiği ad güvenilmez girdidir.

- Decision 13: Liste sayfadan bağımsız sürer: sayfayı kapatmak ya da yenilemek listeyi durdurmaz;
  kaynaktaki sayfa kapanınca durdurma (`pagehide` olayında `sendBeacon`) kalkar. Gerekçe: liste
  veritabanında kalıcıdır ve ziyaretçi onu sayfayı yeniden açınca haptan bulur; kaynakta liste
  başka yoldan bulunamadığı için sayfa kapanınca durduruluyordu.
- Decision 14: Her sahibin (ziyaretçi ya da hesap) en yeni 5 listesi saklanır; altıncı liste
  yüklenince en eskisi silinir ve süreye bağlı silme yoktur. Gerekçe: kaynakta da en çok 5 bitmiş
  liste tutuluyordu (`MAX_LISTS`); hedefte sınır sahip başınadır ve liste yeniden başlatmada kaybolmaz. Silinen
  listenin terim cevapları analiz kayıtlarında kalır.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Uzun süre ve bekleme.** Model sunucusu seri çalıştığı için 200 terimlik liste yaklaşık iki buçuk
  saat sürer (terim başına yaklaşık 45 saniye). Tek çalışan liste kuralı yüzünden başka kullanıcının
  listesi bu süre boyunca başlatılamaz; listeyi yalnız sahibi durdurabildiği için yönetici de
  bekleyen kullanıcı adına onu durduramaz (Decision 8). Tek sorular terimlerin arasına girer ama her
  biri bir terim kadar bekleyebilir.
- **Kalan süre tahmini yanıltabilir.** Kayıtlı cevapla saniyede biten terimler ortalamayı düşürür;
  tahmin, analiz gerektiren terimler kaldığında gerçek süreden kısa görünür.
- **Liste sürerken sözlük değişirse** sonraki terimler yeni sözlükle cevaplanır; rapordaki "Kaynak
  sözlük" listenin başladığı andaki sürümü yazar.
- **Yeniden başlatmada boşa giden çağrı.** Kapanış anında süren terimin model çağrısı kesilir ve
  sürdürmede baştan sorulur; yarıda kesilen liste sahibi dönüp "Devam et" demedikçe yarım kalır.
- **Veritabanı büyür.** Cevaplar tam saklandığı için liste başına birkaç MB yer tutar; kişi başına 5
  liste sınırı büyümeyi sınırlar.
- **Eski listelere ekrandan ulaşılamaz.** Ana ekran yalnız ziyaretçinin en yeni listesini haptan
  açar; saklanan öteki dört liste yalnız API'den okunur (kaynakta da sayfa yenilenince liste
  bulunamıyordu).
- **Katı biçim.** İlk satır her zaman başlıktır; başlıksız yüklenen listenin ilk terimi aranmaz (not
  gösterilir). 50. sütunun ötesindeki veri hiç okunmaz; yalnız orada veri taşıyan dosya "boş"
  sayılır. Satır sınırı ikinci sayfalara da uygulandığı için büyük bir ikinci sayfa "çok fazla
  satır" hatası verir (kaynak davranışı).
- **Liste satırı ile ayrıntı farklı görünebilir.** Satırdaki en iyi tablo oylardan etkilenmez;
  ayrıntıda oylar sırayı değiştirebilir.
- **Yoklama yükü.** Açık her sayfa liste sürerken 1,5 saniyede bir en çok 200 satırlık anlık durum
  ister; çok sayıda açık sayfa sunucuya küçük ama sürekli yük bindirir.
- **Cihaz kimliğinin değişmesi.** Tarayıcı verisi silinirse, başka tarayıcı ya da gizli pencere
  kullanılırsa cihaz kimliği değişir; ziyaretçi kendi listesini göremez, durduramaz ve sürdüremez
  (liste sürer, terim analizleri analiz kayıtlarına yazılır; anonymous-visitor Riskler). Çalışan
  böyle bir listeyi kimse durduramadığı için başka listeler o liste bitene kadar 409 alır.
