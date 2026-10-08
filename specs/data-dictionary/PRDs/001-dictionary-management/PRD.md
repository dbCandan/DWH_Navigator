# PRD — dictionary-management

Status: Draft

Version: 0.1.0

Domain: [data-dictionary](../../DOMAIN.md)

## Amaç

Yönetici veri sözlüğünü şablondaki Excel'den içe aktarır, sözlüğü aynı şablona dışa aktarır ve boş
şablonu indirir. Uygulamanın tek sözlüğü veritabanında (PostgreSQL) sürümlü olarak durur; Excel yalnız
aktarım içindir ve hiçbir Excel sözlük olarak okunmaz. İçe aktarma ya tamamen olur ya hiç olmaz: şablona
uymayan dosya sözlüğe dokunmaz, yarım sözlük hiçbir an görünmez. Aynı içerik yeniden aktarılırsa sözlük
sürümü değişmez; böylece kayıtlı cevaplar ve oylar boşuna geçersiz olmaz.

Excel'in okunması (başlık eşleme, hücre metni, kırpma, eş anlamlıların bölünmesi, KVKK işareti, veri
seti grubu, uyarılar, içerik özeti ve sürüm) kaynak uygulamanın `76e21a3` sürümüyle bayt bayt aynıdır;
çünkü bu çıktı arama indeksine ve modele giden istemlere doğrudan girer. Bu PRD ayrıca yönetim ekranının
**Sözlük** sayfasını ve kaynaktaki `vsa dictionary import|export` komutunun yerine geçen backend
betiğini tanımlar.

## Aktörler ve sonuçlar

- **Yönetici (`yonetici`):** Sözlüğü içe aktarır (dosya seçerek ya da Excel'i yönetim ekranının bir
  sayfasına sürükleyip bırakarak), dışa aktarır, boş şablonu indirir; Sözlük sayfasında tabloları ve
  kayıtlarını içe aktarıldığı hâliyle görür; gerektiğinde önceki sürüme döner (Açık soru 1).
- **Kullanıcı (`kullanici`):** Sözlüğü değiştiremez ve bu PRD'nin uçlarını (API adreslerini)
  kullanamaz; tabloları ve kolonları ana ekranda [dictionary-explorer](../007-dictionary-explorer/PRD.md)
  ile gezer.
- **Geliştirici ve işletim ekibi:** Sözlüğü backend betiğiyle komut satırından içe ve dışa aktarır
  (yerel geliştirme ve acil durum için); uygulama içinde bir rol değildir.
- **Sözlüğü okuyan yetenekler:** [search-settings](../009-search-settings/PRD.md) arama indeksini bu
  PRD'nin okuma işleviyle kurar; [question-analysis](../004-question-analysis/PRD.md) sözlük sürümünü
  kayıtlı cevap parmak izinde ve raporda, [answer-feedback](../006-answer-feedback/PRD.md) oy
  ağırlığında, [analysis-records](../008-analysis-records/PRD.md) analiz kaydında ve Genel bakış
  kartında kullanır.

Ölçülebilir sonuç: Gerçek sözlük (11.136 kolon, 390 tablo, 0 uyarı) yönetim ekranından tek seferde içe
aktarılır ve sorular bu sözlükle cevaplanır; dışa aktarılıp değiştirilmeden geri yüklenen sözlük aynı
sürüm numarasını korur ve yeni sürüm açmaz; şablona uymayan dosya 422 alır ve etkin sözlük, sürümü ve
arama indeksi değişmez; aynı Excel kaynakta ve hedefte aynı sürüm numarasını, aynı kolon listesini, aynı
KVKK işaretlerini ve aynı uyarıları üretir.

## Değişmezler ve sınırlar

- Uygulamanın her an en çok bir **etkin sözlük sürümü** vardır; sözlük okuyan her yetenek onu kullanır.
  Sözlük yalnız şablondaki bir Excel'in içe aktarılmasıyla ya da önceki sürüme dönmeyle (Açık soru 1)
  değişir; ekranda tek tek tablo veya kolon düzenleme yoktur (kaynakta da yoktur).
- İçe aktarılan kayıtlar Excel'deki hücre metinleriyle ve şablon sütun adlarıyla saklanır. Ayrıştırılmış
  kolonlar (eş anlamlı listesi, KVKK işareti, veri seti grubu) saklanmaz; her okumada aynı kodla
  yeniden üretilir. Böylece dışa aktarma şablonu olduğu gibi geri verir.
- Arama indeksinin kurulması, ne zaman yeniden kurulacağı ve durumu
  [search-settings](../009-search-settings/PRD.md) PRD'sinindir; bu PRD indeksin yeniden kurulmasını
  yalnız ister ve sonucunu bildirir.
- Ana ekrandaki yıldız haritası, tablo arama ve tablo dosyası
  [dictionary-explorer](../007-dictionary-explorer/PRD.md); yönetim ekranı kabuğu (kenar çubuğu ve
  rozetleri, `Ctrl K` komut paleti, derin bağlantı biçimi) [search-settings](../009-search-settings/PRD.md);
  Genel bakış sayfası [analysis-records](../008-analysis-records/PRD.md); kelime listelerinin
  içe aktarılması [vocabulary-management](../002-vocabulary-management/PRD.md); giriş, oturum ve roller
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) PRD'sindedir.
- Sözlük kurum içi veridir: Excel, içe aktarılmış kayıtlar, tablo ve kolon adları, açıklamalar, Excel
  dosyasının adı, sayfa ve başlık adları ve uyarı metinleri uygulama loguna, telemetriye, Git'e ve test
  verisine girmez; yalnız veritabanında ve yöneticinin indirdiği Excel'de bulunur.

Decision 1: Excel okuma ve ayrıştırma kodu kaynaktan davranışı değişmeden taşınır:
`src/vsa/loader.py` içindeki `_cell`, `_resolve_columns`, `_REQUIRED`, `_OPTIONAL`, `split_synonyms`,
`_names`, `object_profiles`, `build_columns`, `_PII_MARKER`, `_sheet_rows`, `records`, `file_version`,
`formulas_as_text` ve `src/vsa/dictionary_store.py` içindeki `OBJECT_FIELDS`, `COLUMN_FIELDS`,
`TEMPLATE_NAME`, `_texts`, `_digest` ile `from_workbook`'un doğrulama sırası ve iletileri. Excel okuma
kütüphanesi kaynakla aynı seridir (`openpyxl` 3.1.x; kaynakta 3.1.5 ve `et-xmlfile` 2.0.0); yüklenen
dosyanın XML'i (Excel'in içindeki yapılandırılmış metin) `defusedxml` (XML saldırılarına karşı güvenli
ayrıştırıcı) ile okunur; pandas yoktur. Aynı Excel kaynakta ve hedefte aynı kolon listesini, tablo
profillerini, uyarıları, içerik özetini ve sürümü üretir; bu, kaynak paketle yan yana çalışan fark
testleriyle (aynı girdiyle kaynağı ve hedefi çalıştırıp çıktıları karşılaştıran testlerle) kanıtlanır.

Decision 2: Sözlük sürümünün biçimi `<12 onaltılık hane>-<Kolonlar kayıt sayısı>` olarak kalır
(onaltılık hane: 0–9 ve a–f). Excel raporu "Kaynak sözlük" satırındaki "11.136 satır" bilgisini sürümün
tireden sonraki kısmından okur ([question-analysis](../004-question-analysis/PRD.md)); biçim değişirse
rapor bozulur.

Decision 3: Bu PRD'nin bütün uçları yalnız `yonetici` rolüne açıktır; `kullanici` 403 alır. Ön yüzde
menüyü veya düğmeyi gizlemek yetki denetiminin yerini tutmaz; denetim backend'dedir.

## Mevcut davranış

Kaynak: `~/codes/kt-dwhnavigator`, `76e21a3`. Her maddenin sonunda hedefteki karşılığı yazılıdır.

- **Depo** (`src/vsa/dictionary_store.py`, ADR-049/050): Tek sözlük `data/dictionary.jsonl`
  dosyasıdır: ilk satır meta (`format` 1, `version`, `digest`, `source`, `imported_at`, `objects`,
  `columns`, `warnings` sayısı), ardından Objeler satırları (`type: object`) ve Kolonlar satırları
  (`type: column`), şablon alan adları ve hücre metinleriyle. Dosya yalnız içe aktarmayla yazılır; yeri
  `dictionary.store` ayarıyla değişir (Sözlük sayfasındaki "Dosya ayarları").
  **Hedefte:** Kayıtlar veritabanındaki sözlük tablolarındadır (Requirement 8, Veri ve geçiş); dosya,
  `.bak`, `.tmp` ve `dictionary.store` ayarı yoktur.
- **İçe aktarma akışı** (`src/vsa/web/server.py` `App.dictionary_import`): Gövde boşsa "Dosya boş".
  Gövde geçici klasöre `sozluk.xlsx` olarak yazılır; `from_workbook` okur ve doğrular (hata varsa hiçbir
  şey yazılmaz); `save` sözlüğü önce `.tmp` dosyasına yazıp `os.replace` ile tek adımda yerine koyar ve
  önceki dosyayı `dictionary.jsonl.bak` olarak saklar; ardından `reindex` indeksi kurar. İndeks kurulumu
  analizlerle aynı motor kilidini beklediği için süren bir analiz bitene kadar içe aktarma yanıtı bekler;
  indeks kurulamazsa sözlük değişmiş ama motor eski kalmış olur ve yanıt 500 "Sunucu hatası" döner.
  **Hedefte:** Okuma ve doğrulama yazmadan önce yapılır; ardından değişiklik
  [search-settings](../009-search-settings/PRD.md) PRD'sinin değişiklik sırasından "önce kur, sonra
  yaz" düzeniyle geçer: yeni sözlükle indeks kurulur, kurulum başarılıysa sürüm tek veritabanı
  işleminde (ya hepsi yazılır ya hiçbiri) yazılır, kurulamazsa hiçbir şey yazılmaz (Requirement 8–9).
- **Okuma sınırları** (`server.py` `_body`, `MAX_UPLOAD`, `REQUEST_TIMEOUT`;
  `dictionary_store.py` `MAX_IMPORT_ROWS`; `loader.py` `read_workbook`, `_sheet_rows`): İstek gövdesi en
  çok 20 MB'tır (413 "Dosya çok büyük (en fazla 20 MB)"); `Content-Length` başlığı zorunludur (yoksa
  411); istemci isteğini 120 saniyede göndermelidir. Excel salt okunur ve yalnız hücre değerleri okunarak
  açılır; dosyadaki **bütün** sayfalar okunur; her sayfada en çok 200.000 satır kabul edilir (fazlası
  doluysa "Dosyada çok fazla satır var (en fazla 200,000)." — sayı İngilizce binlik ayracıyla yazılır);
  sondaki boş satırlar atılır; sütun sayısı sınırsızdır.
  **Hedefte:** 20 MB ve 200.000 satır sınırları korunur; yalnız iki şablon sayfası okunur; sayfa başına
  100 sütun ve açılmış boyut sınırı eklenir; sayı Türkçe ayraçla yazılır (Requirement 2, Decision 7).
  Gövdenin parça parça gönderilmesi reddedilmez, 20 MB sınırı okunurken uygulanır; yavaş gönderen
  istemcinin süre sınırı uygulamanın değil giriş katmanının ve sunucunun ayarıdır
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)).
- **Başlık eşleme** (`loader.py` `_REQUIRED`, `_OPTIONAL`, `_resolve_columns`;
  `dictionary_store.py` `TEMPLATE_NAME`): Kolonlar sayfasında başlıklar büyük/küçük harf, boşluk ve
  Türkçe harf farkı gözetilmeden şablon adlarıyla eşlenir: eski kaynak dosyadaki yazım hatalı
  `DAtabaseName` ya da `Database Name` kabul edilir ve `DatabaseName` adıyla saklanır. ADR-049 `Rol` ve
  `Ozet` eş yazımlarını da sayar; ancak Türkçe eş yazımlar (`rol`, `ozet`, `esanlamlilar`) `76e21a3`'ten
  önce `4e829a7` commit'iyle kaldırılmıştır: böyle bir başlık tanınmaz, ek sütun olarak saklanır ve
  ilgili alan (`Role`, `Summary`, `Synonyms`) **uyarısız boş** kalır. Objeler sayfasında başlık eşleme
  yoktur; alanlar birebir şablon adıyla okunur.
  **Hedefte:** Eşleme kuralı aynıdır (Decision 1, Decision 5); şablondaki bir sütun başlık satırında
  yoksa uyarı verilir (yeni, Requirement 6).
- **Hücre metni** (`loader.py` `_cell`, `dictionary_store.py` `_texts`): Boş ve NaN (sayı olmayan
  değer) hücre `""` olur; tam sayı değerli ondalık sayı `"5"` olarak okunur (`"5.0"` değil); her değer
  metne çevrilip baştan ve sondan kırpılır. Ambarda adının sonunda boşluk bulunan 55 kolon sözlükte
  kırpılmış adla durur (SQL yazarken gerçek adın sonundaki boşluğa dikkat edilmelidir); yükleyici yine
  de her adı kırpar. Her kayıt bütün şablon alanlarını (boşsa `""`) ve sayfadaki öteki sütunları (ek
  sütunlar, başlık sırasıyla) taşır; aradaki tamamen boş satırlar da kayıt olarak saklanır.
  **Hedefte:** Aynı (Decision 1).
- **Kolon ayrıştırma** (`loader.py` `build_columns`, `split_synonyms`): Veritabanı, şema, obje veya
  kolon adı boş olan satır "Satır N: eksik veritabanı/şema/obje/kolon, atlandı" uyarısıyla atlanır (N,
  başlık 1. satırdayken Excel'deki satır numarasıdır); aynı `DB.Şema.Obje.Kolon` ikinci kez gelirse ilk
  kayıt tutulur ("Tekrarlanan kolon, ilk kayıt tutuldu: …"). Eş anlamlılar yalnız `Synonyms` hücresinden
  okunur; virgülle ayrılır, parantez ve köşeli parantez içindeki virgüller bölmez, her parçanın sonundaki
  nokta atılır. Veri seti grubu yalnız Objeler sayfasından, `DB.Şema.Obje` anahtarının birebir (büyük/küçük
  harf duyarlı) eşleşmesiyle gelir. `Role` ve `Summary` doğrulanmaz (ADR-037'deki yedi rol ve 70
  karakter sınırı denetlenmez). Kolonların sırası Excel'deki sıradır.
  **Hedefte:** Aynı (Decision 1).
- **KVKK işareti** (`loader.py` `_PII_MARKER`, `models.py` `DictColumn.has_pii`): Kolonun açıklaması
  ile ham `Synonyms` hücresi bir boşlukla birleştirilir ve içinde `kvkk|kişisel\s+veri` metin kalıbı
  (düzenli ifade) büyük/küçük harf duyarsız aranır; bulunursa kolon KVKK işaretlidir. Olumsuz cümle de
  işaretler: "KVKK kapsamında değildir." yazan kolon işaretlidir (`tests/test_loader.py`). İşaret
  şablonda ayrı bir sütun değildir ve dışa aktarılmaz. Analist malzemesinde kolon satırına `[KVKK]`
  eklenir (`llm/analyst.py` `column_line`); kural motoru kolona KVKK uyarısı ekler (`scoring/rules.py`).
  **Hedefte:** Aynı kalıp ve aynı yanlış pozitif davranış; işaret istemlere girdiği için bayt bayt
  korunur (Decision 1).
- **Objeler** (`loader.py` `object_profiles`): Anahtar `ObjectKey`, boşsa
  `DatabaseName.SchemaName.ObjectName`'dir; anahtarı boş satır atlanır; aynı anahtar iki kez gelirse
  sonraki geçerlidir; `TimeColumns` virgülle bölünür; `KeyColumns` saklanır ve dışa aktarılır ama motor
  okumaz; hiçbir kolonla eşleşmeyen Objeler satırı uyarısız saklanır. Objeler sayfası yoksa "“Objeler”
  sayfası yok: tablo açıklamaları ve gruplar olmadan aktarıldı." uyarısı listenin başına eklenir.
  **Hedefte:** Aynı (Decision 1).
- **İki şemadaki aynı ad** (kaynak `CLAUDE.md` "Sözlükte dokümanda olmayan ayrıntılar"): `vCampaign`
  hem `CFM` hem `CMP` şemasında vardır; bu yüzden tablo anahtarı her zaman `DB.Şema.Obje`'dir ve iki
  tablo ayrı kayıt, ayrı tablo, ayrı grup üyesidir. **Hedefte:** Aynı; test verisinde iki şemada aynı
  adlı tablo bulunur (Test stratejisi).
- **Doğrulama hataları** (`dictionary_store.py` `from_workbook`): Excel açılamazsa "Dosya Excel (.xlsx)
  olarak okunamadı."; `Kolonlar` sayfası yoksa "“Kolonlar” sayfası yok (dosyadaki sayfalar: …). Şablonu
  indirip ona göre doldurun."; sayfada kayıt yoksa "“Kolonlar” sayfasında kolon yok."; zorunlu başlık
  yoksa "Sözlükte zorunlu kolon bulunamadı: databasename (mevcut: …)"; hiç geçerli satır yoksa "Geçerli
  kolon satırı yok (veritabanı, şema, obje ve kolon adı dolu olmalı)." HTTP durumu 400'dür.
  **Hedefte:** Aynı iletiler; durum 422 ve kararlı hata kodu (Requirement 5).
- **Sürüm ve içerik özeti** (`loader.py` `file_version`; `dictionary_store.py` `_digest`, `save`,
  `load_dictionary`): Sürüm, yüklenen dosyanın baytlarından hesaplanan SHA-256 parmak izinin (içerik
  değişince değişen özet) ilk 12 onaltılık hanesi, tire ve Kolonlar sayfasındaki kayıt sayısıdır (boş ve
  hatalı satırlar dahil; gerçek sözlükte `…-11136`). İçerik özeti, Objeler ve Kolonlar kayıtlarının
  anahtarları sıralanmış JSON (yapılandırılmış metin) hâlinin SHA-256 parmak izinin ilk 12 hanesidir.
  `save`, yeni içeriğin özeti dosyadakiyle aynıysa eski sürüm numarasını korur (ör. dışa aktarılıp geri
  yüklenen sözlük); farklıysa dosya baytlarından gelen numara geçerli olur. `load_dictionary`, dosya elle
  değiştirilmişse (özet tutmuyorsa) sürümü `<yeni özet>-<kolon kaydı sayısı>` yapar. Sürüm kayıtlı cevap
  parmak izine (`answer_cache.fingerprint`), oy ağırlığına (başka sürümde verilen oy 0,5 sayılır,
  `feedback.py` `OTHER_DICTIONARY`), analiz kaydına, toplu arama raporuna ve tek soru raporunun "Kaynak
  sözlük: dictionary.jsonl (11.136 satır, 390 obje)" satırına (`report/excel.py` `_dictionary_line`)
  girer. Aynı içerik yeniden aktarılınca meta (kaynak adı, zaman) güncellenir, `.bak` aynı içerikle
  değişir (gerçek önceki sözlük kaybolur) ve indeks yine kurulur.
  **Hedefte:** Sürüm ve özet hesabı aynıdır; aynı içerik yeni sürüm açmaz ve önceki sürümü silmez
  (Requirement 7, Decision 6).
- **Uyarılar:** İçe aktarma yanıtı ilk 20 uyarıyı, meta yalnız uyarı sayısını taşır; `load_dictionary`
  her açılışta her uyarıyı `log.info` ile uygulama loguna yazar (uyarılar tablo ve kolon adı içerir).
  Sözlük sayfası yalnız "İçe aktarmada N uyarı vardı (ör. tekrarlanan ya da eksik satırlar atlandı)."
  yazar. **Hedefte:** Uyarılar loga yazılmaz; sayısı ve ilk 20'si sürümle saklanır ve Sözlük sayfasında
  görünür (Requirement 6, Decision 12).
- **Sözlüksüz açılış** (`dictionary_store.py` `empty`, `pipeline.py` `Engine.analyze`, ADR-050):
  Sözlük yoksa uygulama boş sözlük ve boş indeksle açılır ve loga dosya yolunu içeren bir uyarı yazar;
  soru "Analiz yapılamadı: Sözlük henüz içe aktarılmadı; Yönetim → Sözlük ekranından şablondaki Excel'i
  içe aktarın." cevabını alır; `/api/status` 0 kolon döner; dışa aktarma 404 ile dosya yolunu içeren
  "Uygulama sözlüğü yok: … Yönetim → Sözlük'ten içe aktarın." iletisini verir; Sözlük sayfası bırakma
  alanını gösterir; kenar çubuğunda Sözlük'ün yanında "!" rozeti çıkar. **Hedefte:** Aynı davranış;
  iletilerde yol yoktur (Requirement 11).
- **Dışa aktarma** (`dictionary_store.py` `export`, `server.py` `dictionary_export`): İki sayfa
  (`Objeler`, `Kolonlar`); başlık satırı şablon alanları ve ardından ek sütunlar; boş metin boş hücre
  olur; "=" ile başlayan metin formül değil metin olarak yazılır (`formulas_as_text`); başlık satırı
  dondurulur. Dosya adı `VeriSozlugu_YYYYMMDD_HHMM.xlsx` (sunucunun yerel saatiyle), boş şablon
  `VeriSozlugu_sablon.xlsx`; dosya geçici klasörde üretilir. Dışa aktarılıp geri yüklenen sözlük aynı
  kayıtları ve aynı sürümü verir (`tests/test_dictionary_store.py` `test_export_round_trip_and_template`).
  **Hedefte:** Aynı içerik; dosya bellekte üretilir ve saat İstanbul saatidir (Requirement 12).
- **Yönetim uçları** (`server.py`): `GET /api/admin/dictionary` (dosya yolu, dosya var mı, motorun
  kullandığı sürüm, meta, tablo listesi, dosya boyutu, okuma hatası), `GET /api/admin/dictionary/table/<anahtar>`
  (bir tablonun Objeler kaydı ve Kolonlar kayıtları, yazıldığı gibi; yinelenen ve hatalı satırlar
  dahil), `GET /api/admin/dictionary/export`, `GET /api/admin/dictionary/template`,
  `POST /api/admin/dictionary/import` (ham Excel gövdesi, dosya adı `X-Filename` başlığında). Erişim
  `AdminGuard` ile denetlenir: `VSA_ADMIN_PASSWORD` varsa HTTP Basic (tarayıcının parola penceresi),
  yoksa yalnız sunucunun kendisinden; POST istekleri başka siteden gelme denetiminden geçer. Hata gövdesi
  `{"error": "…"}`'dır. **Hedefte:** Oturum ve `yonetici` rolü; `/api/dwhnavigator/v1/dictionary…`
  uçları ve tek hata zarfı (API sözleşmesi).
- **Sözlük sayfası** (`src/vsa/web/static/admin.html` `PAGES.sozluk`, `importDictionary`,
  `fileSettings`): Başlık "Sözlük", açıklama "Tek sözlük: data/dictionary.jsonl; Excel yalnız içe ve
  dışa aktarım içindir.", düğmeler "Excel'den içe aktar…", "Excel olarak dışa aktar" (sözlük varsa) ve
  "Boş şablon". Sözlük yokken bırakma alanı ("Sözlük henüz yok — şablondaki Excel'i buraya bırakın ya da
  tıklayıp seçin" / "İçe aktarılınca arama indeksi kurulur ve sorular bu sözlükle cevaplanır.") ve
  şablonu anlatan "Şablon" kartı ("Boş şablonu indir"). Sözlük varken bilgi kartı (Tablo, Kolon, Kaynak
  dosya, İçe aktarıldı, Sürüm — ilk 12 hane, tamamı ipucunda —, Boyut (KB); "✓ İndeks güncel" ya da
  "İndeksi kur"; uyarı sayısı iletisi) ve Tablolar kartı: grup seçimi "Tüm gruplar (N)", arama "Tablo,
  grup veya açıklama ara…" (anahtar, grup, alan ve açıklamada Türkçe harf duyarsız), başlık "Tablolar ·
  N" ya da "Tablolar · M / N", sütunlar Tablo (ad, altında `DB.Şema`), Grup, Kolon, Açıklama; ilk 200
  satır ve "Daha fazla (N)"; boş sonuçta "Aramaya uyan tablo yok.". Satıra tıklama ya da Enter derin
  bağlantıyı (doğrudan o tabloyu açan adres) `#/sozluk/<DB.Şema.Obje>` açar; çekmecede (sayfanın yanından
  açılan ayrıntı paneli) tablo açıklaması ya da "Tablo açıklaması yok.", Grup, Alan, Satır, Anahtar,
  Zaman bilgileri ve "Kolonlar · N" tablosu (Kolon ve altında özet, Rol, Açıklama, Eş anlamlılar). En
  altta katlanır "Dosya ayarları". İçe aktarmada yalnız `.xlsx` kabul edilir ("Excel (.xlsx) dosyası
  seçin"); sözlük varsa tarayıcının onay penceresi "“ad” mevcut sözlüğün yerini alsın mı? Önceki sürüm
  .bak olarak saklanır; arama indeksi yeniden kurulur (~10 sn)." sorar; bildirimler "İçe aktarılıyor…",
  "Sözlük içe aktarıldı" (kolon ve tablo sayısı, kaynak, "İndeks kuruldu; sorular bu sözlükle
  cevaplanır.", ilk üç uyarı) ve "İçe aktarılamadı". Excel yönetim ekranının Kelimeler dışındaki her
  sayfasına bırakılabilir; bırakırken sayfayı kaplayan "Sözlüğü içe aktarmak için Excel dosyasını
  bırakın" alanı görünür. Motorun sürümü dosyadakinden farklıysa sayfa indeksi eskimiş sayar.
  **Hedefte:** Aynı düzen ve metinler; yol, Boyut ve "Dosya ayarları" kalkar; onay penceresi
  uygulamanın kendi iletişim kutusudur; indirmeler oturumla yapılır; uyarı listesi, içe aktaran kişi ve
  önceki sürüm görünür (Requirement 13–15).
- **Komut satırı** (`src/vsa/cli.py` `cmd_dictionary_import`, `cmd_dictionary_export`):
  `vsa dictionary import X.xlsx` sözlüğü yazar, ilk 10 uyarıyı basar ve kendi sürecinde indeksi kurar;
  çalışan arayüz yeni sözlüğü ancak konteyner yeniden başlatılınca kullanır (`docs/KURULUM.md` §7).
  `vsa dictionary export Y.xlsx [--template]` sözlüğü ya da boş şablonu yazar. Hata iletisi standart
  hataya yazılır, çıkış kodu 2'dir. **Hedefte:** Backend betiği (Requirement 16).
- **Eşzamanlılık:** İki içe aktarma arasında kilit yoktur; son yazan kazanır. **Hedefte:** Aynı anda
  yalnız bir içe aktarma ya da sürüm değişikliği yürür (Requirement 8).

## İşlevsel gereksinimler

Requirement 1: Şablon iki sayfalıdır. **Objeler** sayfasının alanları sırasıyla `ObjectKey`,
`DatabaseName`, `SchemaName`, `ObjectName`, `ObjectDescription`, `Grain`, `KeyColumns`, `TimeColumns`,
`BusinessDomain`, `DatasetGroup`; **Kolonlar** sayfasının alanları sırasıyla `DatabaseName`,
`SchemaName`, `ObjectName`, `ColumnName`, `ColumnDescription`, `Synonyms`, `Role`, `Summary`'dir. Boş
şablon (`VeriSozlugu_sablon.xlsx`) bu iki sayfayı bu sırayla, yalnız başlık satırıyla ve başlık satırı
dondurulmuş olarak verir.

Requirement 2: İçe aktarma isteğinin gövdesi Excel dosyasının kendisidir. `Content-Type`
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` ya da `application/octet-stream`
olmalıdır; başka tür 415 `unsupported_media_type` alır. Dosya adı, yüzde kodlamalı (adın istek
başlığında güvenle taşınması için kodlanmış) UTF-8 (standart metin kodlaması) metin olarak `X-Filename`
başlığında gelir. Sınırlar şu sırayla uygulanır:
1. Gövde en çok 20 MB'tır; `Content-Length` daha büyükse ya da okunurken sınır aşılırsa okuma kesilir ve
   413 `upload_too_large` "Dosya çok büyük (en fazla 20 MB)" döner. Boş gövde 422 `dictionary_file_empty`
   "Dosya boş" alır.
2. Dosya diske yazılmadan bellekte açılır (konteynerin 64 MiB'lık `/tmp`'si kullanılmaz). `.xlsx`
   sıkıştırılmış bir paket olduğu için içindeki dosyaların açılmış toplam boyutu ölçülür; 100 MB'ı
   aşarsa dosya okunmadan reddedilir (yeni sınır, Decision 7).
3. Yalnız `Objeler` ve `Kolonlar` sayfalarının satırları okunur; öteki sayfaların yalnız adı (hata
   iletisi için) okunur (yeni, Decision 7).
4. Her sayfada en çok 200.000 veri satırı kabul edilir; sondaki boş satırlar sayılmaz.
5. Her sayfada en çok 100 sütun okunur; başlık satırında 101. sütun doluysa dosya reddedilir (yeni sınır,
   Decision 7).
6. Dosya adının klasör kısmı atılır, denetim karakterleri (görünmeyen kontrol karakterleri) silinir, ad
   en çok 255 karaktere kısaltılır; ad boş kalırsa `sozluk.xlsx` kullanılır.

Okuma ve doğrulama, isteklere cevap veren ana döngüyü durdurmamak için ayrı bir iş parçacığında (arka
planda paralel çalışan kod yolunda) yapılır; bu sürede veritabanına hiçbir şey yazılmaz.

Yükleme biçimi (Decision 10), 1., 2. ve 6. adımlar, güvenli XML ayrıştırıcı (`defusedxml`) ve dosya
sistemine yazmadan bellekte okuma **ortak güvenli Excel okuyucusudur**; sahibi bu PRD'dir.
[vocabulary-management](../002-vocabulary-management/PRD.md) ve [list-search](../005-list-search/PRD.md)
aynı okuyucuyu kullanır ve yalnız kendi sayfa, satır ve sütun sınırlarını verir; 3.–5. adımlardaki
sınırlar sözlüğe özgüdür.

Requirement 3: Kolonlar başlıkları kaynaktaki `_resolve_columns` kuralıyla büyük/küçük harf, boşluk ve
Türkçe harf farkı gözetilmeden şablon adlarıyla eşlenir ve şablon adıyla saklanır (`DAtabaseName` →
`DatabaseName`). Zorunlu başlıklar `DatabaseName`, `SchemaName`, `ObjectName`, `ColumnName`,
`ColumnDescription`; isteğe bağlı başlıklar `Synonyms`, `Role`, `Summary`'dir. `Rol`, `Ozet`,
`EsAnlamlilar` gibi Türkçe adlar tanınmaz ve ek sütun olarak saklanır (Decision 5). Objeler başlıkları
birebir şablon adıyla okunur. Şablonda olmayan her başlık ek sütun olarak, başlık satırındaki sırayla
saklanır ve dışa aktarılır.

Requirement 4: Her hücre `_cell` kuralıyla metne çevrilir (boş ve NaN `""`, tam sayı değerli ondalık
sayı ondalıksız, her metin baştan ve sondan kırpılmış); her kayıt bütün şablon alanlarını ve bütün ek
sütunları taşır (`_texts`); aradaki boş satırlar kayıt olarak kalır. Kolonlar kayıtları `build_columns`,
Objeler kayıtları `object_profiles` ile Mevcut davranış bölümündeki kurallarla ayrıştırılır: eksik
alanlı satırın atlanması, yinelenen kolonda ilk kaydın tutulması, eş anlamlıların bölünmesi, veri seti
grubunun Objeler'den birebir anahtarla gelmesi, Objeler'de anahtar kuralı ve aynı anahtarda sonraki
kaydın geçerli olması. KVKK işareti, açıklama ile ham `Synonyms` hücresinin bir boşlukla birleştirilmiş
metninde `kvkk|kişisel\s+veri` kalıbının büyük/küçük harf duyarsız aranmasıyla türetilir; "KVKK
kapsamında değildir." gibi olumsuz cümle de işaretler. `Role` ve `Summary` doğrulanmaz.

Requirement 5: Şablona uymayan dosya 422 `dictionary_workbook_invalid` alır ve hiçbir kayıt yazılmaz.
`message`, kaynaktaki Türkçe iletidir: "Dosya Excel (.xlsx) olarak okunamadı.", "“Kolonlar” sayfası yok
(dosyadaki sayfalar: <adlar ya da ->). Şablonu indirip ona göre doldurun.", "“Kolonlar” sayfasında kolon
yok.", "Sözlükte zorunlu kolon bulunamadı: <başlık> (mevcut: <başlıklar>)", "Geçerli kolon satırı yok
(veritabanı, şema, obje ve kolon adı dolu olmalı).", "Dosyada çok fazla satır var (en fazla 200.000).";
yeni sınırlar için "Dosya açıldığında çok büyük (en fazla 100 MB)." ve "“<sayfa>” sayfasında en fazla 100
sütun olabilir.". İleti yalnız yükleyen yöneticiye döner ve loga yazılmaz.

Requirement 6: Uyarılar kaynaktaki metinlerle ve sırayla üretilir: "“Objeler” sayfası yok: tablo
açıklamaları ve gruplar olmadan aktarıldı." (en başta), "Satır N: eksik veritabanı/şema/obje/kolon,
atlandı", "Tekrarlanan kolon, ilk kayıt tutuldu: <DB.Şema.Obje.Kolon>". **Yeni:** sayfa var ama şablondaki
bir alanın sütunu başlık satırında yoksa "“<sayfa>” sayfasında şablondaki “<alan>” sütunu yok; bu alan
boş aktarıldı." uyarısı Objeler sayfası uyarısından sonra, öteki uyarılardan önce eklenir. Objeler'de
`ObjectKey` ile `DatabaseName`, `SchemaName`, `ObjectName` üçlüsü birbirinin yerine geçtiğinden bu
alanlar için uyarı yalnız ikisi de eksikse verilir (Decision 5). Uyarı sayısı ve ilk 20 uyarı sürümle
saklanır, içe aktarma yanıtında ve Sözlük sayfasında gösterilir; uyarılar uygulama loguna yazılmaz.

Requirement 7: Sürüm ve içerik özeti kaynaktaki gibi hesaplanır: sürüm, yüklenen dosyanın baytlarının
SHA-256 parmak izinin ilk 12 onaltılık hanesi, `-` ve Kolonlar kayıt sayısıdır (`file_version`); içerik
özeti `_digest`'tir. Yeni içeriğin özeti etkin sürümünkiyle aynıysa yeni sürüm oluşmaz: etkin sürüm,
sürüm numarası, önceki sürüm ve içe aktarma bilgileri değişmeden kalır; yanıt 200 ve `changed: false`
döner; arama indeksi yalnız etkin sürümden kurulmamışsa yeniden kurulur (Decision 6). Özet farklıysa
dosya baytlarından gelen sürüm numarasıyla yeni sürüm oluşur (201, `changed: true`); bu numara daha
önceki bir sürümünkiyle aynı olabilir (aynı dosya yeniden yüklenirse) ve benzersiz olması gerekmez. Sürüm
numarası arama indeksine, kayıtlı cevap parmak izine, oy ağırlığına, analiz kaydına ve rapora sözlüğün
okuma işleviyle (Requirement 10) geçer; bu kullanımların kuralları ilgili PRD'lerdedir.

Requirement 8: Yeni sürüm tek veritabanı işleminde yazılır: sürüm kaydı, bütün Objeler ve Kolonlar
kayıtları (Excel sırasıyla), etkin sürümün "önceki" yapılması ve en eski sürümün budanması (Requirement
14) birlikte ya kalıcı olur ya hiç olmaz. İşlem yarıda kalırsa (süreç çökmesi dahil) etkin sözlük ve
sürümü değişmez; okuyan hiçbir istek yarım sözlük görmez. Aynı anda yalnız bir içe aktarma ya da sürüm
değişikliği yürür: PostgreSQL kilidi (aynı anda tek işe izin veren veritabanı kilidi) arayüzden ve
betikten gelen işlerin hepsini kapsar; kilit alınamazsa istek beklemeden 409
`dictionary_import_in_progress` "Başka bir sözlük içe aktarması sürüyor; bitince yeniden deneyin." alır.
Kilit yalnız yazma sırasında tutulur; dosyanın okunup doğrulanması kilitten önce yapılır. Veritabanı
kısıtı aynı anda en çok bir etkin ve en çok bir önceki sürüm bulunmasını güvenceye alır.

Requirement 9: Doğrulanmış yeni sürüm [search-settings](../009-search-settings/PRD.md) PRD'sinin
değişiklik sırasından (Requirement 11) "önce kur, sonra yaz" düzeniyle geçer: yeni sözlükle arama
indeksi kurulur; kurulum başarılıysa sürüm Requirement 8'deki gibi yazılır ve yeni indeks hizmete
alınır. Kurulum ya da yazma başarısızsa hiçbir kayıt yazılmaz, etkin sözlük ve hizmetteki indeks
değişmez ve istek 500 `search_index_build_failed` alır; sırada bekleme sınırı aşılırsa 503
`search_change_busy` döner (iki kod da search-settings'teki anlamıyla). İçe aktarma yanıtı `index`
alanında hizmetteki indeksin durumunu taşır (biçimi search-settings `GET /search-index` yanıtıdır).
Süren bir analiz başladığı indeksle biter.

Requirement 10: Sözlüğün tek okuma işlevi; etkin sürümün Objeler ve Kolonlar kayıtlarını Excel
sırasıyla ve kaynaktaki kayıt biçiminde (bütün şablon alanları ve ek sütunlar, metin olarak), sürüm
numarasını, kaynak adını (Requirement 17) ve uyarıları verir. Arama indeksi ve sözlük okuyan her yetenek
yalnız bu işlevi kullanır. İşlev her okumada içerik özetini yeniden hesaplar; saklanan özetle tutmazsa
(kayıtlar veritabanında elle değiştirilmiş demektir) kaynaktaki kural uygulanır: sürüm
`<yeni özet>-<Kolonlar kayıt sayısı>` olur ve `dictionary.integrity_mismatch` olayı yazılır.

Requirement 11: Etkin sürüm yokken (ilk kurulumda) okuma işlevi boş sözlük verir: kayıt yok, sürüm `""`,
kaynak adı `""`. Uygulama bu durumda açılır ve çalışır. Görünür sonuçlar: soru "Analiz yapılamadı:
Sözlük henüz içe aktarılmadı; …" cevabını alır ([question-analysis](../004-question-analysis/PRD.md));
ana ekranın durum bilgisi 0 kolon ve 0 tablo gösterir ([dictionary-explorer](../007-dictionary-explorer/PRD.md));
dışa aktarma ve tablo uçları 404 `dictionary_not_imported` "Sözlük henüz içe aktarılmadı." döner;
Sözlük sayfası bırakma alanını gösterir; yönetim kenar çubuğunda Sözlük'ün yanında "!" rozeti ("Sözlük
henüz içe aktarılmadı"), Genel bakış'ta sözlük kartı ve ilk kurulum adımı görünür
([search-settings](../009-search-settings/PRD.md), [analysis-records](../008-analysis-records/PRD.md)).
Sözlüksüz açılış loga dosya yolu ve içerik taşımayan `dictionary.empty` olayını yazar.

Requirement 12: Dışa aktarma, etkin sürümün kayıtlarını kaynaktaki `export` biçiminde yazar: `Objeler`
ve `Kolonlar` sayfaları; başlık satırı şablon alanları ve ardından sürümün ek sütunları (içe
aktarmadaki sırayla); her kayıt bir satır; boş metin boş hücre; "=" ile başlayan metin formül değil
metin; başlık satırı dondurulmuş. Dosya bellekte üretilir ve saklanmaz; adı
`VeriSozlugu_YYYYMMDD_HHMM.xlsx`, saat İstanbul saatidir (`Europe/Istanbul`). Dışa aktarılan dosya
değiştirilmeden içe aktarılırsa içerik özeti aynıdır ve yeni sürüm oluşmaz (Requirement 7). Etkin sürüm
yoksa 404 `dictionary_not_imported`.

Requirement 13: Sözlük sayfası (yalnız `yonetici`) kaynaktaki düzeni ve metinleri korur (Mevcut
davranış), şu farklarla:
- Açıklama satırı "Tek sözlük uygulamanın veritabanındadır; Excel yalnız içe ve dışa aktarım içindir."
  olur; "Boyut" bilgisi ve "Dosya ayarları" bölümü kalkar.
- Bilgi kartında "İçe aktaran" (kişinin görünen adı ya da betikle yapıldıysa "Betik") bulunur.
- Uyarı sayısı iletisinin altında saklanan ilk 20 uyarı katlanır bir listede görünür.
- İndeks etkin sürümden kurulmamışsa "✓ İndeks güncel" yerine "İndeksi kur" düğmesi görünür; düğme
  [search-settings](../009-search-settings/PRD.md) PRD'sindeki yeniden kurma ucunu çağırır.
- Önceki sürüm varsa bilgi kartında "Önceki sürüm: <sürümün ilk 12 hanesi> · <tarih> · <kaynak dosya>"
  satırı ve "Önceki sürüme dön" düğmesi bulunur (Requirement 14).
- Tablo listesi ve çekmece içe aktarılmış kayıtları yazıldığı gibi gösterir (yinelenen ve hatalı
  satırlar dahil); bu, ana ekrandaki tablo dosyasının gösterdiği ayrıştırılmış görünümden bilerek
  farklıdır.
- Tablo ayrıntısı derin bağlantıyla açılır; adres biçimi yönetim ekranı kabuğundadır
  ([search-settings](../009-search-settings/PRD.md)). Tablo satırının birincil eylemi klavyeyle de
  erişilebilir bir düğme ya da bağlantıdır.
- Yükleniyor, boş, hata ve bildirim durumları paylaşılan ön yüz bileşenleriyle gösterilir; bütün
  metinler `app/frontend/src/locales/tr.json` kataloğundadır.

Requirement 14: En çok iki sürümün kayıtları saklanır: etkin sürüm ve bir önceki sürüm (kaynaktaki
`.bak` dosyasının karşılığı). Yeni sürüm oluşunca etkin sürüm "önceki", eski önceki sürüm "budanmış"
olur: budanan sürümün Objeler ve Kolonlar kayıtları silinir; sürüm kaydı (kim, ne zaman, hangi dosya,
sayılar) yumuşak silinmiş (silinmeden silindi olarak işaretlenmiş) olarak kalır. Yönetici "Önceki
sürüme dön" ile önceki sürümü özgün sürüm numarasıyla etkin yapar; o anki etkin sürüm önceki olur, yani
iki sürüm arasında gidip gelinebilir. Geri dönüş uygulamanın onay iletişim kutusuyla sorulur ("Sözlük
<sürümün ilk 12 hanesi> sürümüne dönülsün mü? Şimdiki sözlük önceki sürüm olarak saklanır; arama
indeksi yeniden kurulur."), Requirement 8'deki kilidi kullanır ve indeksi Requirement 9'daki gibi yeniden
kurdurur. Bu gereksinim Açık soru 1'e bağlıdır.

Requirement 15: İçe aktarma etkileşimi:
- "Excel'den içe aktar…" dosya seçicisi ve Excel'in yönetim ekranının Kelimeler dışındaki herhangi bir
  sayfasına bırakılması aynı akışı başlatır; bırakma sırasında sayfayı kaplayan "Sözlüğü içe aktarmak
  için Excel dosyasını bırakın" alanı görünür. Kelimeler sayfasına bırakılan dosya bu akışı başlatmaz
  (orada kelime listeleri içe aktarılır: [vocabulary-management](../002-vocabulary-management/PRD.md)).
  Boş durumdaki bırakma alanı klavyeyle (Enter ve Space) de dosya seçicisini açar.
- Uzantısı `.xlsx` olmayan dosya istek gönderilmeden "Excel (.xlsx) dosyası seçin" bildirimiyle
  reddedilir.
- Etkin sözlük varsa uygulamanın onay iletişim kutusu sorar: "“<dosya adı>” mevcut sözlüğün yerini alsın
  mı? Önceki sürüm saklanır; arama indeksi yeniden kurulur (~10 sn)."
- İşlem sürerken "İçe aktarılıyor…" / "<dosya adı> okunuyor, doğrulanıyor ve indeks kuruluyor."
  bildirimi görünür. Yeni sürümde "Sözlük içe aktarıldı" bildirimi "<kolon> kolon · <tablo> tablo
  (<kaynak>)", "İndeks kuruldu; sorular bu sözlükle cevaplanır." ve varsa "<N> uyarı: <ilk üç uyarı,
  · ile ayrılmış>" satırlarını gösterir. İçerik aynıysa "Sözlük değişmedi" bildirimi "İçerik etkin
  sürümle aynı (sürüm <ilk 12 hane>); yeni sürüm oluşmadı." der. İndeks kurulamazsa sözlük değişmez ve
  istek hata kodu döner (Requirement 9). Hata durumunda "İçe aktarılamadı"
  bildirimi `dictionary_workbook_invalid` için sunucunun Türkçe `message` metnini, öteki kodlar için
  katalogdaki metni gösterir. Ardından sayfa ve yönetim kabuğunun durumu yenilenir.
- Dışa aktarma ve boş şablon oturumlu bir istekle indirilir; erişim belirteci (oturumu kanıtlayan
  anahtar) adres satırına konmaz
  ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 12).
  Kaydedilen dosyanın adı yanıttaki `Content-Disposition` başlığından alınır.

Requirement 16: Backend betiği `python -m app.scripts.dictionary` üç komut sunar: `import <yol>` dosyayı
Requirement 2–8 ile aynı kurallarla ve aynı kilitle içe aktarır (`-` verilirse dosya standart girdiden
okunur); `export <yol>` sözlüğü, `template <yol>` boş şablonu yazar (`-` standart çıktıdır). Çıktı
kaynaktakine benzer (dosya yolu yerine sürüm, sayılar Türkçe biçimde): "Aktarıldı: 11.136 kolon · 390
tablo (sürüm …)" ve en çok 10 uyarı ("• …"); içerik
aynıysa "Değişmedi: içerik etkin sürümle aynı (sürüm …)"; dışa aktarmada "Yazıldı: <yol>". Hata iletisi
standart hataya yazılır ve çıkış kodu 2'dir. Betikle yapılan içe aktarmada içe aktaran kişi boş, kanal
`betik` olarak kaydedilir. Betik çalışan backend'in bellekteki indeksini kurmaz; çıktısının son satırı
"Çalışan uygulama yeni sözlüğü indeks yeniden kurulunca kullanır (Yönetim → Bakım → İndeksi yeniden
kur)." der ve Sözlük sayfası indeksi eskimiş gösterir.

Requirement 17: Sözlüğün kaynak adı, etkin sürümün içe aktarıldığı Excel dosyasının adıdır (ör.
`VeriSozlugu.xlsx`). Okuma işlevi (Requirement 10) motora sözlük kaynağı olarak bu adı verir; analiz
sonucundaki ve raporlardaki "Kaynak sözlük" bilgisi bu adı gösterir (kaynakta her zaman
`dictionary.jsonl`). Bu gereksinim Açık soru 2'ye bağlıdır.

Requirement 18: Yönetim uçları API sözleşmesi bölümündeki gibidir: sözlük durumu (etkin ve önceki sürüm
özeti, indeksin kurulduğu sözlük sürümü); tablo listesi (içe aktarılmış Kolonlar kayıtlarının
`DB.Şema.Obje` anahtarına göre sayımı; grup, alan, açıklama ve satır tanımı Objeler'den; anahtara göre
kod noktası sırasıyla — Python'un düz metin karşılaştırması —; sayfalı); tek tablonun kayıtları
(Objeler kaydı ya da `null` ve Kolonlar kayıtları, Excel sırasıyla; anahtar için Kolonlar kaydı yoksa 404
`dictionary_table_not_found`). Tablolar sürümler arasında kararlı doğal anahtarları (`DB.Şema.Obje`) ile,
sürümler `public_id` ile adreslenir (Decision 8).

## API sözleşmesi

Bütün uçlar `/api/dwhnavigator/v1` altındadır, geçerli oturum ve `yonetici` rolü ister. Hata gövdesi tek
hata zarfıdır: `{"detail":{"code":"...","message":"..."}}`; `message` Türkçe ve güvenlidir; istek kimliği
`x-request-id` başlığıyla döner. OpenAPI dosyası (API tanım dosyası)
`specs/openapi/dwhnavigator-api.yaml` ve üretilmiş ön yüz tipleri aynı değişiklikte güncellenir.

**Sürüm özeti** şu alanları taşır: `public_id`, `version`, `source_name`, `imported_at` (evrensel saat,
ISO 8601 uluslararası tarih biçimiyle), `imported_by` (`{public_id, display_name}` ya da betikle yapıldıysa `null`), `channel`
(`arayuz` ya da `betik`), `object_count`, `column_count`, `row_count`, `warning_count`.

| Yöntem ve yol | Rol | İstek özü | Başarı | Hatalar |
|---|---|---|---|---|
| `GET /dictionary` | `yonetici` | — | 200: `active` (sürüm özeti ve `warnings[]`, en çok 20) ya da `null`; `previous` (sürüm özeti) ya da `null`; `index_dictionary_version` (hizmetteki indeksin kurulduğu sürüm; boş indekste `""`) | 401, 403 |
| `GET /dictionary/tables` | `yonetici` | `page` (≥ 1), `page_size` (1–1000, varsayılan 1000) | 200: `items[]` (`key`, `name`, `group`, `domain`, `description`, `grain`, `columns`), `total`, `page`, `page_size` | 404 `dictionary_not_imported`, 422 `invalid_request` |
| `GET /dictionary/tables/{table_key}` | `yonetici` | anahtar yüzde kodlamalı; `/` içeren anahtar da desteklenir | 200: `key`, `object` (Objeler kaydı ya da `null`), `columns[]` (Kolonlar kayıtları; şablon alanları ve ek sütunlar) | 404 `dictionary_not_imported`, 404 `dictionary_table_not_found` |
| `POST /dictionary/imports` | `yonetici` | Excel gövdesi, `X-Filename` | 201 `changed: true` ya da 200 `changed: false`: `version` (sürüm özeti), `warnings[]` (en çok 20), `index` (search-settings `GET /search-index` yanıtı) | 409 `dictionary_import_in_progress`, 413 `upload_too_large`, 415 `unsupported_media_type`, 422 `dictionary_file_empty`, 422 `dictionary_workbook_invalid`, 500 `search_index_build_failed`, 503 `search_change_busy` |
| `GET /dictionary/export` | `yonetici` | — | 200: Excel; `Content-Disposition: attachment; filename="VeriSozlugu_YYYYMMDD_HHMM.xlsx"` | 404 `dictionary_not_imported` |
| `GET /dictionary/template` | `yonetici` | — | 200: Excel; `filename="VeriSozlugu_sablon.xlsx"` | — |
| `POST /dictionary/versions/{public_id}/activation` | `yonetici` | — | 200: `version` (yeni etkin sürümün özeti), `index`; hedef zaten etkinse değişiklik yapmadan 200 | 404 `dictionary_version_not_found` (yok ya da budanmış), 409 `dictionary_import_in_progress`, 500 `search_index_build_failed`, 503 `search_change_busy` |

Her uçta ortak hatalar 401 `not_authenticated` ve 403 `forbidden`'dır. Kaynaktaki `GET/POST
/api/admin/dictionary…` uçlarının karşılığı bu tablodur; dosya yolu, dosya boyutu ve okuma hatası
alanlarının karşılığı yoktur. Son uç (geri dönüş) Açık soru 1'e bağlıdır.

## Güvenlik ve yetkilendirme

- Kimlik ve rol [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) ile
  gelir. Kaynaktaki `AdminGuard`, HTTP Basic parolası (`VSA_ADMIN_PASSWORD`) ve "yalnız sunucunun
  kendisinden" istisnası kalkar. Erişim belirteci istek başlığında taşındığı için tarayıcı onu başka
  siteden gelen isteğe kendiliğinden eklemez; kaynaktaki başka siteden gelme (CSRF: başka bir sitenin
  kullanıcı adına istek göndermesi) denetimi yine de bütün durum değiştiren isteklerde ek savunma olarak
  sürer (user-accounts Requirement 13).
- Rol denetimi backend'de, her uçta yapılır; `kullanici` 403 alır. Betik veritabanına doğrudan yazdığı
  için yalnız backend konteynerine erişimi olan geliştirici ve işletim ekibi çalıştırabilir.
- Yükleme güvenliği: tür, boyut, açılmış boyut, sayfa, satır ve sütun sınırları (Requirement 2); XML
  saldırılarına karşı güvenli ayrıştırıcı; dosya diske yazılmaz, hiçbir parçası çalıştırılmaz; hücreler
  yalnız metin olarak işlenir. Excel'deki formüller hesaplanmaz, saklı değerleri okunur.
- Excel çıktısı: "=" ile başlayan her metin formül değil metin olarak yazılır (CWE-1236, Excel formül
  enjeksiyonu).
- Gizlilik: sözlük içeriği, dosya adı, sayfa ve başlık adları, uyarılar ve doğrulama iletileri loga ve
  telemetriye girmez. Doğrulama iletisi yalnız dosyayı yükleyen yöneticiye, kendi dosyasının sayfa ve
  başlık adlarıyla döner. HTTP tamamlanma logu yalnız yol şablonunu (`/dictionary/tables/{table_key}`)
  yazar; ham yol ve tablo anahtarı yazılmaz.
- Bütün sorgular parametrelidir ve tek kiracı `platform` kapsamında çalışır; tablo anahtarı sorguya
  değer olarak geçer.

## Veri ve geçiş

Şemanın sahibi SQLAlchemy modelleridir (veritabanı yapısını tanımlayan Python sınıfları); tablolar
Alembic göçüyle (veritabanı yapısını sürüm sürüm kuran betikle) oluşur. Her tablo ve sütun anlamını açıklayan veritabanı yorumunu taşır (kural 43).

- **`dictionary_version`** (sözlük sürümü): kural 41'in zorunlu bloğunu tam taşır (`public_id`, `props`,
  oluşturma/güncelleme bilgileri, yumuşak silme: kaydı silmeden silindi olarak işaretleme). Alanlar: kiracı, `status` (`active`, `previous`,
  `pruned` — anlamları yorumda yazılı), `version` (metin, benzersiz değil), `content_digest` (12
  onaltılık hane), `source_name` (en çok 255 karakter), `channel` (`arayuz`, `betik`), `imported_at`
  (saat dilimli zaman), içe aktaran kullanıcıya bağ (`created_by`; betikte boş), `row_count`,
  `column_count`, `object_count`, `warning_count`, `warnings` (ilk 20 uyarı metni),
  `object_extra_headers` ve `column_extra_headers` (ek sütunların sıralı adları; dışa aktarma sırası
  için). Kısıt: yumuşak silinmemiş satırlar arasında kiracı başına en çok bir `active` ve en çok bir
  `previous`. Budanan sürüm `pruned` ve yumuşak silinmiş olur; satırı silinmez.
- **`dictionary_object_record`** (Objeler kaydı) ve **`dictionary_column_record`** (Kolonlar kaydı):
  anahtar (sürüm, sayfadaki sıra); şablon alanları ayrı metin sütunlarıdır (boş değer `""`, `NULL`
  değil): Objeler için `object_key`, `database_name`, `schema_name`, `object_name`,
  `object_description`, `grain`, `key_columns`, `time_columns`, `business_domain`, `dataset_group`;
  Kolonlar için `database_name`, `schema_name`, `object_name`, `column_name`, `column_description`,
  `synonyms`, `role`, `summary`. Ek sütunlar `props.extra_cells` anahtarında (başlık → metin) durur.
  Kolonlar kayıtlarında (sürüm, `database_name`, `schema_name`, `object_name`) dizini tablo aramasını
  hızlandırır. Bu iki tablo sürümün değişmez, yalnız eklenen parçasıdır: `public_id`, güncelleme
  bilgileri ve yumuşak silme taşımaz; `props` ve `created_at` taşır; sürüm budanınca kayıtları servis
  aynı işlemde siler (kural 41 ve 42 sapması, Decision 8). Sürüme bağ kısıtlayıcı yabancı anahtardır;
  basamaklı silme yoktur.
- **Hacim:** sürüm başına en çok 200.000 Kolonlar ve 200.000 Objeler kaydı; bugün 11.136 Kolonlar ve
  yaklaşık 390 Objeler kaydı. Kayıtları saklanan en çok iki sürüm olduğundan tablolar bugün yaklaşık
  23.000 satırla sınırlıdır; budanan sürüm başına bir küçük sürüm satırı kalır.
- **Geçiş:** Kaynağın `data/` dosyalarından veri taşınmaz (kurulu bir kaynak sürüm yoktur).
  `dictionary.jsonl`, `.bak`, `.tmp` ve `dictionary.store` ayarı hedefte yoktur. İlk kurulumda sözlük,
  yönetim ekranından şablondaki Excel (gerçek sözlük `VeriSozlugu.xlsx`, depo dışında) içe aktarılarak
  oluşur.

## Gözlemlenebilirlik

Ortak kurallar [application-foundation alanında](../../../application-foundation/DOMAIN.md) yazılıdır:
etiket değerleri sabit kümelerdir, kümede olmayan değer `other` yazılır; sözlük içeriği, tablo ve kolon
adı, dosya adı ve kullanıcı adı hiçbir log olayına, ölçüme ve iz aralığına girmez.

- **Log olayları:** `dictionary.import` (`outcome`: `created`, `unchanged`, `invalid`, `too_large`,
  `unsupported_type`, `conflict`, `error`; `channel`; `version`; `row_count`, `column_count`,
  `object_count`, `warning_count`; `duration_ms`; hata kodu; kullanıcı `public_id`),
  `dictionary.export` (`kind`: `dictionary`, `template`; `version`; kullanıcı `public_id`),
  `dictionary.version_activated` (`from_version`, `to_version`, kullanıcı `public_id`),
  `dictionary.pruned` (`version`, silinen Objeler ve Kolonlar kaydı sayısı), `dictionary.empty`
  (açılışta etkin sürüm yok), `dictionary.integrity_mismatch` (`stored_digest`, `actual_digest`). Sürüm
  ve özetler içerik değil, parmak izidir.
- **Ölçümler:** `dwhnavigator_dictionary_imports_total{outcome,channel}` (sayaç),
  `dwhnavigator_dictionary_import_duration_seconds{outcome}` (süre dağılımı; okuma, doğrulama ve yazma),
  `dwhnavigator_dictionary_exports_total{kind}` (sayaç), `dwhnavigator_dictionary_active_columns` ve
  `dwhnavigator_dictionary_active_tables` (etkin sürümün geçerli kolon ve tablo sayısı). Etiket kümeleri
  yukarıdaki sabit değerlerdir.
- **İz (trace):** her içe aktarma için içerik taşımayan bir `dictionary import` aralığı; öznitelikleri
  `outcome`, `channel`, `row_count` ve süredir.
- Tüketen test: `app/backend/tests/unit/test_dictionary_telemetry.py` (ad, etiket kümesi ve içerik
  sızmaması).

## Dağıtım etkisi

- **Bağımlılık:** `openpyxl` (Excel okuma ve yazma kütüphanesi; kaynakla aynı seri, 3.1.x),
  `et-xmlfile` (onun yardımcı kütüphanesi) ve `defusedxml` (güvenli XML ayrıştırıcı) çalışma zamanı
  bağımlılığı olarak `app/backend/requirements.in`'e ve `dependency-admission.json` kabul kaydına girer.
  Excel raporu da aynı kütüphaneleri kullandığı için ([question-analysis](../004-question-analysis/PRD.md))
  bağımlılığı önce uygulanan PRD ekler; ikincisi yeniden eklemez. Yeni sürüme geçiş kural 54'ün
  güncelleme penceresine ve fark testlerinin yeniden geçmesine bağlıdır.
- **Göç:** Sözlük tabloları Alembic göçüyle (veritabanı yapısını sürüm sürüm kuran betikle) eklenir ve
  dağıtımdaki göç adımıyla uygulanır
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md));
  uygulama açılırken şema değiştirmez.
- **Giriş katmanı:** İçe aktarma gövdesi 20 MB'a kadar çıkar. Kümede ingress'in (dışarıdan gelen
  istekleri karşılayan giriş katmanı) gövde sınırı 20 MB olmalıdır (giriş katmanındaki nginx
  sunucusunun varsayılanı 1 MB'tır);
  yerel Compose'daki (geliştirici makinesinde konteynerleri birlikte çalıştıran düzen) ters vekil
  (isteği uygulamaya ileten ara sunucu) için de aynısı geçerlidir. İçe aktarma isteği okuma, sırada
  bekleme ve indeks kurulumunu içerir (Requirement 9) ve 60 saniye kuralı içinde biter (kaynakta
  kurulum ~10 sn; sıra ve kurulum süreleri [search-settings](../009-search-settings/PRD.md)
  Requirement 11 ve 13'tedir). Gövde sınırının ve 60 saniye kuralının sahibi
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)'dir
  (Requirement 11 ve 12).
- **Kaynak:** 20 MB'lık ya da 200.000 satırlık bir Excel'in okunması backend'in bellek ve işlemci
  kullanımını kısa süreliğine artırır; backend tek kopya çalışır.
- **Betik:** `app/backend/app/scripts/dictionary.py` backend imajındadır; kök dosya sistemi salt okunur
  olduğundan kümede dosya standart girdi ve çıktıyla (`-`) taşınır.
- Yeni sır, yeni ağ çıkışı ve yeni ortam değişkeni yoktur. `dictionary.store` ayarı kalktığı için ayar
  karşılığı da yoktur.

## Test stratejisi

- **Birim (saf işlevler):** başlık eşleme (`DAtabaseName`, `Database Name`, büyük harfli başlık; `Rol`,
  `Ozet`, `EsAnlamlilar` tanınmaz, ek sütun olur ve yeni uyarıyı üretir), hücre metni (`2024`, `1.0` →
  `"1"`, boş, NaN, kırpılan sondaki boşluk `"vCardLimitFullness "`), eksik alanlı satır ve yinelenen
  kolon uyarıları ve satır numaraları, eş anlamlıların bölünmesi (parantez içindeki virgül, sondaki
  nokta), KVKK işareti ("KVKK", "kişisel veri", "KİŞİSEL VERİ", "KVKK kapsamında değildir" işaretli; yalnız
  `Synonyms` hücresinde geçen ifade işaretli), grup eşleşmesi (büyük/küçük harf farkıyla eşleşmeyen
  anahtar), Objeler anahtar kuralı ve yinelenen anahtar, iki şemada aynı adlı tablo (`vCampaign`),
  sürüm biçimi (12 hane, `-`, boş ve hatalı satırlar dahil kayıt sayısı), içerik özetinin alan sırasından
  bağımsız ve satır sırasına bağlı olması, sınırlar (200.001 dolu satır reddedilir, sondaki boş satırlar
  sayılmaz, 101. başlık sütunu reddedilir, açılmış boyutu sınırı aşan dosya okunmadan reddedilir, 20
  MB'ı aşan gövde 413), "=" ile başlayan metnin dışa aktarmada metin kalması.
- **Fark testleri:** kaynak `76e21a3` paketi test ortamında yan yana kurulur (düzenek
  [question-analysis](../004-question-analysis/PRD.md) PRD'sinindir); örnek Excel ve test verisi
  için kolon listesi, tablo profilleri, KVKK işaretleri, uyarılar (yeni uyarılar hariç), içerik
  özeti, sürüm ve dışa aktarılan Excel'in hücre değerleri karşılaştırılır ve aynıdır. Gerçek sözlük
  (`VeriSozlugu.xlsx`) yalnız depo dışındaki bir yoldan verilirse çalışır, verilmezse test atlanır;
  sözlük Git'e ve test verisine girmez.
- **Gerçek PostgreSQL:** içe aktarma işleminin bölünmezliği (kayıtların yarısı yazıldıktan sonra yapay
  hata → etkin sürüm ve kayıtlar değişmez), indeks kurulumu hata verince hiçbir kaydın yazılmaması ve
  500 `search_index_build_failed`, aynı anda iki içe aktarma (biri 409; arayüz ve betik
  birlikte), aynı içeriğin yeniden aktarılması (yeni sürüm yok, önceki sürüm korunur, `changed: false`),
  dışa aktar → içe aktar (sürüm aynı), saklama ve budama (en çok iki sürümün kayıtları; budanan sürüm
  satırı yumuşak silinmiş), önceki sürüme dönüş ve geri (özgün sürüm numarası), boş sözlük durumu ve 404
  `dictionary_not_imported`, tablo listesi ve tek tablo kayıtları (yinelenen satırlar dahil, Excel
  sırası, `/` içeren anahtar), rol denetimi (oturumsuz 401, `kullanici` 403), okuma işlevinin sırayı
  koruması ve elle değiştirilmiş kayıtta sürüm kuralı, göç ve zorunlu sütun kapısı (kayıt tablolarının
  belgelenmiş sapmaları dahil).
- **Veri sızıntısı:** test Excel'indeki tablo, kolon ve dosya adına konan ayırt edici bir işaret dizesi
  log çıktısında, ölçümlerde ve iz aralıklarında aranır; bulunmamalıdır.
- **Ön yüz (Vitest, ön yüz test aracı):** boş durum ve klavyeyle dosya seçme, `.xlsx` denetimi, onay
  iletişim kutusu, bildirimler (yeni sürüm, değişmedi, indeks kurulamadı, hata kodları), Kelimeler
  dışındaki sayfalara bırakma, tablo listesi süzme, arama ve "Daha fazla", derin bağlantıyla çekmece,
  önceki sürüm satırı ve geri dönüş onayı, eskimiş indeks uyarısı, indirmelerin oturumlu istekle yapılması
  ve adreste erişim belirteci bulunmaması.
- **Uçtan uca (tarayıcı, `e2e/data-dictionary/`):** Kabul kriterlerindeki L2 senaryoları.

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

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 1, 3–7 ve 12'nin birim testleri ile
  kaynak paketle fark testleri geçer; örnek Excel için kolon listesi, tablo profilleri, KVKK işaretleri,
  uyarılar (yeni uyarılar hariç), içerik özeti, sürüm ve dışa aktarılan hücreler kaynakla aynıdır. Gerçek
  sözlük depo dışından verildiğinde 11.136 kolon, 390 tablo, 0 uyarı ve `-11136` sonekli sürüm görülür.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 2, 8–11, 14, 16 ve 18'in gerçek
  PostgreSQL testleri geçer: sınırlar, işlem bölünmezliği, 409 çakışması, aynı içerik, saklama ve budama,
  önceki sürüme dönüş, boş sözlük, rol denetimi, betik; veri sızıntısı testinde işaret dizesi log, ölçüm
  ve izde bulunmaz; göç ve zorunlu sütun kapısı ile tam kalite kapısı geçer.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Requirement 13 ve 15'in Vitest testleri geçer;
  OpenAPI dosyası ve üretilmiş ön yüz tipleri günceldir.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da yerel PostgreSQL ile
  `yonetici` olarak giriş yapılır; örnek Excel Genel bakış sayfasına bırakılarak içe aktarılır, Sözlük
  sayfasında sayılar, uyarılar ve "İçe aktaran" görünür; bir tablo derin bağlantıyla açılır; sözlük dışa
  aktarılıp değiştirilmeden geri yüklenince "Sözlük değişmedi" ve aynı sürüm görülür; şablona uymayan
  dosya hata verir ve sözlük değişmez; ikinci bir Excel içe aktarılıp "Önceki sürüme dön" ile ilk sürüme
  dönülür. `kullanici` olarak Sözlük sayfası görünmez ve `/dictionary` ucu 403 döner; ana ekranın durum
  bilgisi yeni kolon sayısını gösterir (Requirement 7, 8, 13–15).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı (nonprod): gerçek sözlük Excel'i (depo
  dışında) nonprod yönetim ekranından giriş katmanı üzerinden içe aktarılır; 11.136 kolon ve 390 tablo
  görünür ve bir soru bu sözlükle cevaplanır (Requirement 2, 9). Küme dağıtımı bu kanıtın parçası
  değildir ve ayrı kullanıcı talimatı ister.

## Kararlar

Decision 4: Kayıtlar hücre metni olarak, şablon alan adlarıyla saklanır; ayrıştırılmış kolonlar
saklanmaz. Gerekçe: dışa aktarma şablonu olduğu gibi geri verir, içerik özeti kaynaktaki gibi
hesaplanabilir ve ayrıştırma tek yerde, kaynakla bayt bayt aynı koddadır.

Decision 5: Türkçe başlık eş yazımları (`Rol`, `Ozet`, `EsAnlamlilar`) tanınmaz; hedef ADR-049'u değil
`76e21a3`'teki kodu izler. Bu adlarla gelen sütunun sessizce boş kalması `Role` ve `Summary`'nin analist
malzemesine girmesi nedeniyle cevap kalitesini fark ettirmeden düşürebileceğinden, şablondaki bir alanın
sütunu eksikse uyarı verilir (yeni). Uyarı istemleri ve sıralamayı etkilemez.

Decision 6: Etkin sürümle aynı içerik yeni sürüm açmaz, önceki sürümü ve içe aktarma bilgilerini
değiştirmez. Gerekçe: kaynakta aynı içerik `.bak` dosyasının yerine geçip gerçek önceki sözlüğü
kaybettiriyordu; içe aktarmanın tekrarlanması aynı sonucu vermelidir. İndeks etkin sürümden kurulmamışsa
yine kurulur; böylece aynı içeriği yeniden aktarmak eskimiş indeksi düzeltmenin bir yolu olarak kalır.

Decision 7: Yeni yükleme sınırları: açılmış toplam boyut en çok 100 MB, sayfa başına en çok 100 sütun ve
yalnız iki şablon sayfasının okunması. Gerekçe: 20 MB'lık sıkıştırılmış bir dosya çok daha büyük bir
içeriğe açılabilir ve sütun sınırı olmadan tek satır binlerce boş hücreye genişleyebilir; backend tek
kopya çalıştığından bu durum bütün kullanıcıları etkiler. Gerçek sözlük bu sınırların çok altındadır
(8 ve 10 şablon alanı, 11.136 satır).

Decision 8: Tablolar `public_id` ile değil `DB.Şema.Obje` anahtarıyla adreslenir; bu anahtar sürümler
arasında kararlıdır ve derin bağlantılar ile ana ekran aynı anahtarı kullanır. Kayıt tabloları sürümün
değişmez, yalnız eklenen parçası olduğundan `public_id`, güncelleme bilgisi ve yumuşak silme taşımaz;
budanan sürümün kayıtları silinir, sürüm satırı yumuşak silinir (kural 41 ve 42 sapması; göç ettirilmiş
şema kapısı bu sapmaları doğrular). Gerekçe: her içe aktarma on binlerce satır ekler; kayıtlar Excel'den
yeniden üretilebilir; kim, ne zaman, hangi dosyayı içe aktardı bilgisi sürüm satırında kalır.

Decision 9: Dışa aktarılan dosyanın adındaki saat İstanbul saatidir (`Europe/Istanbul`); veritabanındaki
bütün zamanlar evrensel saatle (UTC) saklanır ve ekranda tr-TR biçiminde İstanbul saatiyle gösterilir
(alan değişmezi).

Decision 10: İçe aktarma gövdesi ham Excel dosyasıdır (çok parçalı form değil); dosya adı `X-Filename`
başlığındadır. Gerekçe: kaynakla aynı biçimdir ve yeni bir form ayrıştırma bağımlılığı
(`python-multipart`) gerektirmez. Aynı yükleme biçimini [vocabulary-management](../002-vocabulary-management/PRD.md)
ve [list-search](../005-list-search/PRD.md) de kullanır; ön yüzde paylaşılan istemcinin ikili gövde
gönderme ve ikili yanıt indirme yeteneği bu üç PRD için ortaktır ve önce uygulanan PRD ile gelir.

Decision 11: Excel'in okunup doğrulanması kilitten ve veritabanı işleminden önce, ayrı bir iş
parçacığında yapılır; kilit yalnız yazma sırasında tutulur. Gerekçe: uzun okuma başka bir içe aktarmayı
ve isteklere cevap veren ana döngüyü bekletmez.

Decision 12: Uyarılar uygulama loguna yazılmaz (tablo ve kolon adı içerir); sayısı ve ilk 20'si sürümle
saklanır ve Sözlük sayfasında gösterilir. Kaynakta uyarıların tamamı yalnız logda görülebiliyordu.

## Açık sorular

1. **Önceki sürüm (`.bak` karşılığı) ve geri dönüş:** Kaynak her içe aktarmada önceki sözlüğü
   `dictionary.jsonl.bak` dosyası olarak saklıyordu ve geri dönüş dosyanın elle kopyalanmasıydı; hedefte
   dosya ve dosya erişimi yoktur. Öneri: yalnız bir önceki sürümün kayıtları saklanır; Sözlük sayfasındaki
   onaylı "Önceki sürüme dön" düğmesi önceki sürümü özgün sürüm numarasıyla etkin yapar (kayıtlı cevaplar
   ve oylar o sürüme göre yeniden geçerli olur) ve indeksi yeniden kurdurur; daha eski sürümlerin
   kayıtları silinir, içe aktarma bilgileri kalır (Requirement 14 ve geri dönüş ucu).
2. **Rapor ve analizde görünen sözlük kaynak adı:** Kaynakta raporun "Kaynak sözlük" satırı her zaman
   uygulamanın kendi dosyasının adını (`dictionary.jsonl`) gösterir; hedefte bu dosya yoktur. Öneri:
   etkin sürümün içe aktarıldığı Excel'in adı gösterilir (ör. "Kaynak sözlük: VeriSozlugu.xlsx (11.136
   satır, 390 obje)"); fark testleri bu alanı karşılaştırma dışında tutar (Requirement 17).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Yanlış ama geçerli Excel:** Şablona uyan ama yanlış ya da eski bir sözlük etkin sözlüğün yerini alır
  ve cevaplar bozulur. Onay iletişim kutusu, uyarılar ve önceki sürüme dönüş (Açık soru 1) etkiyi
  sınırlar; içe aktarmanın kendisi içeriğin doğruluğunu bilemez.
- **Türkçe başlıklar:** `Rol` veya `Ozet` başlıklı bir Excel roller ve özetler boş aktarılır; yeni uyarı
  bunu görünür kılar ama içe aktarmayı durdurmaz.
- **Kütüphane sürümü:** `openpyxl`'in başka bir serisi hücre değerlerini farklı okursa (sayı, tarih)
  sürüm ve kolonlar kaynaktan ayrışır; sürüm kaynakla aynı seride tutulur ve fark testleri her yükseltmede
  yeniden çalışır.
- **Giriş katmanı sınırları:** Giriş katmanının (ingress) gövde sınırı ayarlanmazsa içe aktarma
  uygulamaya ulaşmadan 413 alır; okuma, sırada bekleme ve kurulum 60 saniyeyi aşarsa yanıt beklenirken
  504 alır, sunucu değişikliği yine tamamlar ya da hiç yazmaz ve yönetici başarısız sanmış olabilir.
  Sözlük sayfası yenilenince gerçek durum görünür.
- **Bellek:** Sınırdaki bir Excel'in okunması tek kopya backend'de geçici bellek artışı yaratır ve süren
  analizleri yavaşlatabilir.
- **Betik ve çalışan uygulama:** Betikle yapılan içe aktarma indeks yeniden kurulana kadar sorulara
  yansımaz; Sözlük sayfası bu durumu eskimiş indeks olarak gösterir.
- **KVKK yanlış pozitifi:** "KVKK kapsamında değildir." gibi cümleler de işaretlenir; davranış
  istemlere girdiği için bilerek korunur, düzeltilmesi ayrı bir ölçümlü değişiklik ister
  ([quality-evaluation](../010-quality-evaluation/PRD.md)).
