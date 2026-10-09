# PRD — question-analysis

Status: Accepted

Version: 1.0.2

Acceptance date: 2026-10-08

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

Kullanıcı doğal dildeki veri talebini yazar ("kart limit doluluk oranı nerede?"); uygulama talebi veri
sözlüğüne karşı analiz eder ve tablo seviyesinde, gerekçeli, sözlüğe karşı doğrulanmış bir cevap ile iş
birimine gönderilebilir bir Excel raporu verir. Cevabı kurum içindeki sohbet modeli (analist) iki adımda
yazar: önce bütün tablo kataloğundan aday tablo seçer, sonra adayların kolonlarını okuyup raporu yazar.
Kural motoru modele ipucu verir ve modelin yazdığı her tablo ve kolon adını sözlüğe karşı denetler.

Analiz sunucuda bir iş olarak yürür: kullanıcı ilerlemeyi kaynaktaki gibi Evren'in tarama
hareketiyle izler, istediğinde durdurur; tarayıcı bağlantısı koparsa ya da sekme kapanırsa iş sürer.
Aynı soru ya da aynı anlamdaki soru yeniden sorulduğunda önceki cevap (kayıtlı cevap) saniyeler
içinde yeniden verilir.

Bu PRD, kaynak uygulamanın (`kt-dwhnavigator`, `76e21a3`) çekirdek değerini taşır: kural motoru ve
analist kodu davranışı değişmeden backend'e geçer ve aynı girdilerle kaynakla bayt bayt aynı sonucu
verir. Bu, kaynak paketle yan yana çalışan fark testiyle kanıtlanır.

## Aktörler ve sonuçlar

- **Kullanıcı (`kullanici`):** Talebini yazar, analizi izler (sıradayken "sırada" bilgisini görür),
  durdurabilir, cevabı görür, Excel raporunu indirir, kayıtlı cevap yerine yeni analiz isteyebilir.
  Ölçülebilir sonuç: kabul edilen her talep dört son durumdan birine ulaşır (tamamlandı, hatayla
  bitti, durduruldu, yarıda kesildi; "tamamlandı" cevabı analistin cevabı, kayıtlı cevap ya da
  "Analiz yapılamadı" ve sebebidir); önerilen tablo ve kolonların sözlükte olmayanı 0'dır; başlatma
  yanıtı 2 saniye içinde döner; kayıtlı cevap 2 saniye içinde ekrandadır; "Durdur" analizi 5 saniye
  içinde bitirir.
- **Yönetici (`yonetici`):** Kullanıcının yapabildiklerini yapar; ayrıca kayıtlı cevap özetini görür ve
  bütün kayıtlı cevapları siler (düğme [search-settings](../009-search-settings/PRD.md) PRD'sinin
  **Bakım** sayfasındadır). Bu PRD ona başkasının analizine erişim vermez.
- **Geliştirici:** Fark testini (kaynak paketle hedefi aynı girdilerle yan yana çalıştırıp çıktıları
  karşılaştıran test) çalıştırır. Ölçülebilir sonuç: sentetik sözlükte ve varsa gerçek sözlükte fark
  sayısı 0.
- **İşletim ekibi (uygulama rolü değildir):** Aynı anda yürüyen analiz sayısını ve kuyruk sınırını ortam
  ayarıyla verir; analizleri içerik görmeden log ve ölçümlerden izler.
- **İç tüketiciler:** [list-search](../005-list-search/PRD.md) her terimi bu PRD'nin iş modeliyle
  yürütür; [answer-feedback](../006-answer-feedback/PRD.md) oyları cevaba uygular ve kayıtlı cevabı
  sildirir; [analysis-records](../008-analysis-records/PRD.md) analiz kaydını saklar ve gösterir;
  [dictionary-explorer](../007-dictionary-explorer/PRD.md) durum ucunu üst çubukta kullanır.

## Değişmezler ve sınırlar

- [Alan belgesindeki](../../DOMAIN.md) değişmezler bu PRD'nin bütün çıktısına uygulanır: cevap tablo
  seviyesindedir, var olmayan alan önerilmez, "bulunamadı" geçerli cevaptır, cevabı yalnız analist
  yazar, metin karşılaştırması yalnız Türkçe normalleştirme yardımcısıyla yapılır, ölçülmüş davranış
  korunur.
- Arama ve cevap ayarlarının şeması, ölçülmüş varsayılanları ve değiştirilmiş değerlerin saklanması ile
  arama indeksinin yaşam döngüsü [search-settings](../009-search-settings/PRD.md) PRD'sindedir; bu PRD
  ayarları yalnız okur.
- Sözlüğün içe aktarılması, sürümü ve PostgreSQL tabloları
  [dictionary-management](../001-dictionary-management/PRD.md); terim sözlüğü ve durak kelimeler
  [vocabulary-management](../002-vocabulary-management/PRD.md) PRD'sindedir.
- Oyların cevaba uygulanması ve kayıtlı cevabın oyla silinme kararı answer-feedback PRD'sindedir; bu PRD
  cevabı ve silme hizmetini sağlar.
- Analiz kaydının tablosu, temizliği ve yönetim ekranı analysis-records PRD'sindedir;
  bu PRD kayda neyin ve hangi adımların yazıldığını tanımlar (Requirement 18).
- Toplu arama list-search; Evren, tablo dosyası ve ana ekranın kabuğu (üst çubuk, durum göstergesi)
  dictionary-explorer; giriş ve roller
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md); dağıtım
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md); kalite
  ölçümü quality-evaluation PRD'sindedir.
- Soru metni, sözlük içeriği, tablo ve kolon adı, istem, model yanıtı, adres ve kullanıcı adı uygulama
  loguna ve telemetriye (ölçüm ve iz) girmez. Analiz kaydı ve kayıtlı cevap, soru ve cevap metni dahil,
  ürün verisidir ve yalnız PostgreSQL'dedir.
- Kayıtlarda kimlik oturumdaki kullanıcıdır (`public_id`, görünen ad); kaynaktaki istemci adresi,
  makine adı ve serbest "voter" metni kullanılmaz.
- Arayüz yalnız Türkçedir; metinler `app/frontend/src/locales/tr.json` dosyasındadır ve kaynaktaki gibi
  kalır.

Decision 1: Çekirdek bayt bayt korunur. Kaynaktaki saf modüller (Türkçe normalleştirme, terim
genişletme, kelime araması, kolon kuralları, tablo seviyesine toplama, konu uyumu, analist malzemesi ve
istemleri, doğrulama, metin içi ad denetimi, açıklama, rapor biçimi) backend'e davranışı değişmeden
taşınır. Aynı girdilerle kural sıralaması, modele giden istemler (modele verilen talimat ve malzeme) ve
sahte modelle analist cevabı kaynak `76e21a3` ile bayt bayt aynıdır (Requirement 1, 2). Taşıma bir
davranış değişikliği değildir; ağırlık, istem ya da model değişikliği ayrı iştir ve altın setle önce ve
sonra ölçülür ([quality-evaluation](../010-quality-evaluation/PRD.md)).

Decision 2: Analiz sunucuda iş olarak yürür: başlatma isteği hemen döner, ilerleme canlı olay
akışıyla (sunucunun tarayıcıya sürekli olay gönderdiği bağlantı) gelir, sonuç ayrı uçtan okunur, iş
durdurulabilir. Analiz süresince açık kalan tek istek kullanılmaz; kümenin giriş kapısındaki
(ingress) zaman aşımı bir analizi kesemez. Kaynaktaki "tek motor, tek kilit" seri çalışması korunur:
aynı anda yürüyen analiz sayısı her ortamda varsayılan olarak 1'dir (ayar 1–4; model sunucusu seri
çalışır, kalite ölçümleri seri yapıldı, paralel istek sonucu koşudan koşuya yaklaşık ±2 puan
oynatıyordu). Eşzamanlılık artırılmadan önce altın setle önce ve sonra ölçülür
([quality-evaluation](../010-quality-evaluation/PRD.md)). Bu iş modeli list-search PRD'sinin de
kullandığı modeldir.

Decision 3: Kayıtlı cevaplar kaynak kararı ADR-035'in anlamını korur (iki anahtar, parmak izi, 30 gün,
"Yeniden analiz et") ve PostgreSQL'de saklanır. Yalnız soru akışında (tek soru ve liste terimleri)
kullanılır; ölçüm betiği kullanmaz.

Decision 4: Model yalnız [llm-connection](../003-llm-connection/PRD.md) PRD'sinin uygulama portu
üzerinden çağrılır. Bu PRD istemleri kurar ve modelin yanıtını yorumlar. Bağlantı, kurum içi ağ
politikası, zaman aşımı, yeniden deneme, şemaya bağlı yanıt isteği, yanıttan yapılandırılmış metnin
(JSON) ayıklanması ve tek onarım denemesi, model sunucusu kontrolü ve hata sınıfları o PRD'dedir.

## Mevcut davranış

Kaynak: bu deponun geçmişindeki `76e21a3`. Her maddenin sonundaki **Hedefte:** notu neyin
değiştiğini ya da aynen kaldığını söyler.

### Soru akışı

- **Talep** (`src/vsa/web/server.py` `App.ask`, `POST /api/ask`): Gövde `query`, `top`, `ask_id`,
  `fresh`, `voter`. Talep kırpılır; boşsa "Talep metni boş", 4000 karakteri (`MAX_QUERY_CHARS`)
  aşarsa "Talep çok uzun (en fazla 4000 karakter)" ile 400 döner. `top` 1–10 aralığına sessizce
  kırpılır (varsayılan 5). `ask_id` istemciden gelir (en çok 64 karakter), yoksa üretilir. İstek analiz
  bitene kadar (45 saniye ile birkaç dakika) açık kalır. Soru ekranı kimliksizdir; kayda istemci adresi
  yazılır. **Hedefte:** `POST /analyses` işi kabul edip hemen döner; doğrulama hataları kararlı kodlu
  422'dir; aralık dışı `top` reddedilir; kimlik oturumdaki kullanıcıdır; iş kimliğini sunucu üretir
  (Requirement 4, 8).
- **Kayıtlı cevap araması** (`App._answer`, `App._reuse`, `src/vsa/answer_cache.py`,
  `src/vsa/web/answer_store.py`): `fresh` değilse ve `cache.enabled` açıksa "Önceki cevap araması"
  adımı çalışır: aynı parmak izli ve `cache.max_age_days` (30) günden yeni kayıtlar içinde önce aynı
  metin (`text_key`), sonra `cache.meaning` açıksa aynı anlam (`meaning_key`), en yenisi alınır. Cevap
  güncel sözlükle yeniden kurulur (`decode`; kolonu artık olmayan cevap kullanılmaz). Yöntem listesinin
  başına "Bu soru <gg.aa.yyyy SS:dd> tarihinde analiz edildi (<N> sn); kayıtlı cevap yeniden kullanıldı
  (sözlük, model ve ayarlar aynı). Yeni bir analiz için “Yeniden analiz et”." satırı eklenir (aynı
  anlamda "Aynı anlama gelen “<önceki soru>” sorusu …"); `reused_at`, `reused_match`, `reused_query`
  dolar; `query` yeni soru, `elapsed_ms` aramanın süresi olur. Kayıtlar `data/cache/answers.jsonl`
  dosyasındadır, açılışta belleğe okunur; en yeni 2000 kayıt (`MAX_ENTRIES`) tutulur, aynı metin ve
  parmak izli yeni cevap eskisinin yerini alır. Yalnız analistin cevabı ve yalnız motor analiz boyunca
  değişmediyse yazılır. Komut satırı (`vsa ask`, `vsa eval`) kayıtlı cevap kullanmaz. **Hedefte:** aynı
  kurallar; depo PostgreSQL; arama iş kabulünde ve sıra gelince yapılır; depo hatası analizi durdurmaz
  (Requirement 13–15).
- **Tek motor, tek kilit** (`App.lock`, `App._answer`): Kayıtlı cevap yoksa iş "Sırada bekleme"
  adımında motor kilidini 0,25 saniyede bir dener ve her denemede durdurulup durdurulmadığına bakar;
  kilidi alınca `Engine.analyze` çalışır. Aynı anda tek analiz yürür. Kilidin sırası garanti
  değildir; aynı soru iki kez beklerken iki kez analiz edilir. Ayar kaydı motoru kilitsiz yeniler
  (`App.reload`): süren analiz eski motorla biter, yeni motor sonrakilere geçer. **Hedefte:** açık,
  ilk gelen ilk çıkar sıralı kuyruk; aynı anda yürüyen analiz sayısı varsayılan 1; bekleyen
  kullanıcı yalnız sırada olduğunu görür, önündeki analiz sayısı gösterilmez; aynı soru tek kez
  analiz edilir (Requirement 9, 14, 20).
- **Motor girişi** (`src/vsa/pipeline.py` `Engine.analyze`, `Engine._unavailable`,
  `fallback_reason`; `src/vsa/llm/client.py` `health`): Sırasıyla: sözlük boşsa "Sözlük henüz içe
  aktarılmadı; Yönetim → Sözlük ekranından şablondaki Excel'i içe aktarın."; sohbet modeli yoksa
  "Sohbet modeli bağlı değil; Yönetim → Yapay zekâ sayfasından bir model bağlayın."; "Model sunucusu
  kontrolü" adımında sunucunun model listesi 5 saniyelik süreyle sorulur (sonuç 30 saniye saklanır) ve
  sunucu cevap vermezse sebep hemen yazılır (ölü sunucu beklenmez, kaynak kararı ADR-034); sonra
  "Analist akışı". Bu denetimlerden biri geçilemezse ya da analist sonuç veremezse cevap "Analiz
  yapılamadı: <sebep>" özetli, tablosuz `BULUNAMADI` cevaptır (kaynak kararı ADR-038). Analist
  sonuç veremezse sebep modelin hata metninden çıkarılır: bağlam aşımı → "Modelin bağlam penceresi
  tablo kataloğu için küçük (~70k token gerekir). …", zaman aşımı ya da `504` → "Model zamanında
  yanıt vermedi (zaman aşımı).", bağlantı → "Model sunucusuna ulaşılamadı.", diğer → "Model hatası:
  <hata metninin ilk 160 karakteri>". Sunucu kontrolünün sebebi model sunucusunun adresini ve teknik
  ayrıntıyı içerir (ör. "Model sunucusuna ulaşılamadı (http://…/v1): bağlantı reddedildi …").
  **Hedefte:** aynı sıra; sebep metinleri Requirement 5 tablosundadır ve adres ya da sunucunun ham
  hata metnini içermez.

### Kural motoru

- **Türkçe normalleştirme** (`src/vsa/text/normalize.py`): Büyük/küçük harf yalnız burada çevrilir:
  `I→ı`, `İ→i` (`tr_lower`); Türkçe harfler İngiliz alfabesine katlanır (`fold`); birleşik adlar
  parçalanır (`split_camel`: `CardLimitFullnessToday`, `IFRSStage`, `KKB_DATE`); 2 harften kısa parça
  ve durak kelime (katlanmış ve gövdelenmiş biçimiyle) atılır; basit ek atma uygulanır (`stem`: en uzun
  ek, kök en az 4 harf, en çok 3 tur); birleşik ad ayrıca tek parça olarak kalır. Başka modülde
  `.lower()`, `.upper()`, `.casefold()` yoktur (test denetler). **Hedefte:** aynı davranış; harf
  çevirisi ve katlama uygulamanın tek Türkçe metin yardımcısındadır (`app/domain/turkish_text.py`),
  normalleştirme ve parola politikası onu kullanır.
- **Terim genişletme** (`src/vsa/expansion/query_expander.py` `QueryExpander.expand`): Terim sözlüğü
  grupları iki yönlüdür; talepte en uzun ifade önce eşleşir (eşitlikte grubun kendi terimi). Eşleşen
  grubun diğer üyeleri kelime aramasına 0,6 ağırlıkla eklenir (yalnız yeni parçalar; kaynak kararı
  ADR-004: talep metni değişmez). "finansal" alanlı gruplar ölçüdür; notu "Kapsam:" ile başlayan grup
  eşleşince uyarı üretir. Sözlüğün eş anlamlılar kolonu (en çok 6 kelimelik ifadeler; 40'tan çok
  kolonda geçen tek kelime sayılmaz) eşleşen kolonları doğrudan aday havuzuna koyar. Kavramlar: zaman
  (aylık, günlük…), kırılım, ölçü (oran, adet, tutar) ve terimler; parantez içindeki kırılım değerleri;
  "değil", "hariç", "dışında" kavram olmaz. Kavram ağırlığı nadirliğe göredir (`_weigh_concepts`:
  log(1 + kolon sayısı / (kavramı taşıyan kolon + 1))); hiç geçmeyen kavram not edilir. **Hedefte:**
  aynen.
- **Kelime araması** (`src/vsa/index/bm25.py`, `src/vsa/features.py`; BM25, kelime sıklığına dayalı
  arama yöntemi): Her kolon bir belgedir; alanlar ağırlıklıdır (kolon adı 3, eş anlamlılar 2, açıklama
  1, tablo adı 1; `k1` 1,2, `b` 0,75); sonuçlar puana, eşitlikte belge sırasına göre dizilir.
  `Engine.rank_objects` bütün kolonları puanlar; ilk 1000 kolonun (`search.candidate_object_columns`)
  tabloları ve eş anlamlı eşleşmeleri aday havuzudur. **Hedefte:** aynen; indeks belleğe search-settings
  PRD'sindeki yaşam döngüsüyle kurulur.
- **Kolon kuralları** (`src/vsa/scoring/rules.py` `score_column`; kaynak kararları ADR-010, ADR-012):
  Aday tabloların her kolonu: 0,35 × göreli kelime puanı + 0,25 × kavram kapsaması (nadirlik
  ağırlıklı); ekler: kolon adı talepteki kelimeyle birebir +0,30, adda talep kavramları +0,20,
  açıklamada çok kelimeli kavram ifadesi +0,15, eş anlamlılar listesinde +0,15, terim sözlüğüyle
  eşleşme +0,10; cezalar: oran istenip kolon hazır oran değilse −0,15 ("Hazır oran değil; oran
  pay/payda alanlarından türetilmeli"), açıklama "X bazlı değil" diyorsa −0,10. Puan 0–1 arasına
  kırpılır (kırpılmamış değer eşitlik bozmada kullanılır); KVKK (kişisel verilerin korunması kanunu)
  işaretli kolona uyarı eklenir. **Hedefte:** aynen.
- **Tablo seviyesine toplama ve konu uyumu** (`src/vsa/scoring/aggregate.py` `aggregate`,
  `src/vsa/scoring/topic.py`, `src/vsa/scoring/combine.py`; kaynak kararları ADR-005, ADR-011,
  ADR-028): Tablo puanı, uygulanan bileşenlerin ağırlıklı ortalamasıdır: en iyi kolon 0,35, kavramları
  birlikte taşıma 0,21, konu uyumu 0,30, zaman kolonu 0,07 (talepte zaman varsa; aylıkta `Period` 1,
  `DataDate` 0,8…), müşteri seviyesi 0,07 (talep müşteri istiyorsa; müşteri anahtarı varsa 1, yoksa
  0,5). Uygulanmayan bileşenin ağırlığı paydan çıkar. Konu uyumu, her tablonun tek belge olduğu ikinci
  kelime indeksidir (tablo adı 4, profil 3, kolon adı 1, eş anlamlı 1, açıklama 0,3) ve adaylar içinde
  0–1'e ölçeklenir. Uzun biçimli ürün kırılımı (ürün adı ya da tipi kolonu) kapsamaya sayılır. Sıra:
  puan, eşitlikte ilk kolonun kırpılmamış puanı, sonra tablo anahtarı. Güven seviyesi gösterilen
  yüzdeye göredir (`level_for`: %80 ve üstü Yüksek, %50 ve üstü Orta, altı Düşük). **Hedefte:** aynen.
- **İpucu havuzu** (`Engine.rank_objects`, `Engine._column_relevance`, `Engine._hints`): Analist için
  en çok 60 tablo (`ANALYST_RULE_POOL`) sıralanır; puanı 0,5'ten (`scoring.min_candidate_score`) düşük
  olan atılır. Adımlar "Sorgu genişletme", "BM25 arama", "Kolon skorlama", "Tablo toplama ve konu
  uyumu" adlarıyla kaydedilir. Modele giden ipucu metni üç listedir: "Kural skoru en yüksek tablolar:"
  (ilk 15), "Talebin kavramlarını en çok BİRLİKTE taşıyan tablolar:" (en çok kavram, sonra puan; ilk
  15'ten birden çok kavram taşıyanlar), "Kelime eşleşmesi en güçlü kolonlar:" (ilk 25 kolon).
  **Hedefte:** aynen.

### Analist

- **1. adım — aday seçimi** (`src/vsa/llm/analyst.py` `build_catalog`, `shortlist`,
  `parse_shortlist`; `src/vsa/llm/analyst_prompts.py` `shortlist_system`, `shortlist_user`,
  `SHORTLIST_SCHEMA`; kaynak kararları ADR-029, ADR-040): Katalog, tablo başına bir satırdır, anahtara
  göre sıralıdır ve her soruda aynıdır (model sunucusu kataloğu bir kez okuyup saklayabilir):
  `T12 | DB.Şema.Obje | grup | N kolon | açıklama | Satır: … | Zaman: …`; açıklaması olmayan tabloda
  kolon adları. Sistem mesajı rol + kurallar (en az 6, en çok `analyst.shortlist` = 14 aday) +
  katalogdur; kullanıcı mesajı talep + ipuçları + yanıt örneğidir; yanıt sınırı 2500 belirteçtir
  (token, modelin metin parçası). Yanıttan adaylar (yalnız katalog kimliği; tam ad ya da tek eşleşen
  tablo adı da kabul; bilinmeyen kimlik sayılır), benzer tablolar (adaylarda olmayanlar), arama
  terimleri (en çok 12), bilgi aileleri (en çok 6, aile başına en çok 8 terim) ve talebin yorumu
  alınır. Yanıt gelmezse analiz yapılamaz. **Hedefte:** aynen.
- **Aile araması ve emniyet ağı** (`Engine._family_tables`, `Engine._searched_tables`): Aday varsa
  her bilgi ailesinin terimleriyle tablo seviyesinde arama yapılır; ailenin en iyi tablosunun %60'ından
  (`FAMILY_MIN_SHARE`) zayıf eşleşme alınmaz; aile başına 2 (`analyst.family_tables`), toplam 6
  (`analyst.family_extra`) tablo eklenir. Emniyet ağı, 1. adımın seçmediği en iyi 3 tabloyu
  (`analyst.search_tables`; profiller dahil tablo araması) ekler. **Hedefte:** aynen.
- **2. adım — malzeme ve istem** (`Engine.analyst_read`, `analyst.table_material`, `column_line`,
  `term_matcher`, `confusable_material`, `Engine._concept_evidence`; `analyst_system`,
  `analyst_user`, `ANALYST_SCHEMA`): Okunan tablolar = adaylar + eklenenler. Her tablo
  `### T12 · anahtar · Talep eden birim: … · N kolon · Satır: …` başlığıyla, talep kavramlarının hangi
  kolonda geçtiğini söyleyen satırla ("Talep kavramları (kelime eşleşmesi): …") ve eklenme sebebiyle
  gelir. En ilgili 8 kolon (`analyst.detail_columns`) tam açıklamasıyla (420 karakterde kelime
  sınırından kesilir), diğerleri `Ad [Rol]: özet` biçiminde gider; 90'dan (`analyst.full_table_columns`)
  geniş tabloda yalnız en ilgili 90 kolon satır alır, kalanı adıyla listelenir. İlgililik = kelime
  puanı + 0,5 × arama terimi eşleşmesi. Karıştırılabilir alanlar: benzer tabloların kolonları (en çok
  6 tablo, tablo başına 10 kolon), sözlüğün geri kalanından en çok 60 benzer alan ve 4 ya da daha çok
  tabloda geçen alanlar (ilk 8). Sistem mesajı rol + rapor kurallarıdır (öneri sayısı `top`); kullanıcı
  mesajı talep + yorum + aday tablolar + karıştırılabilir alanlar + yanıt örneğidir; yanıt sınırı 8000
  belirteçtir (`analyst.max_tokens`). Okunacak tablo yoksa model çağrılmaz; cevap "BULUNAMADI. Veri
  ambarı kataloğunda bu talebi karşılayan bir tablo bulunamadı." olur. **Hedefte:** aynen.
- **Model cevabının ayrıştırılması ve denetimi** (`src/vsa/llm/client.py` `chat_json`,
  `parse_json_reply`; `analyst.build_answer`, `Cleaner`, `MentionChecker`, `resolve_id`,
  `_resolve_column`, `without_typo_remarks`; kaynak kararı ADR-002): Yanıt şemaya bağlı istenir;
  düşünme blokları (`<think>`) ve kod çiti atılarak yapılandırılmış metin olarak ayrıştırılır, geçersizse
  bir kez onarım istenir (bu kısım llm-connection PRD'sine geçer). Öneri yalnız okunan tablolardan,
  kimlikle seçilir. Kolon adı tam ya da Türkçe katlamayla eşleşir; sözlükte olmayan kolon atılır;
  geçerli kolonu kalmayan öneri atılır. Güven 0–1'e kırpılır, 0,5'ten (`analyst.min_confidence`)
  düşükse öneri gösterilmez. Aynı tablo bir kez önerilir; öneriler güvene göre sıralanıp ilk `top`
  alınır. Serbest metinlerde katalog kimliği tablo adına çevrilir ("T177 tablosu" → "vX tablosu"),
  "vX (vX)" tekrarı silinir ve sözlükte olmayan tablo ya da kolon adı geçen cümle silinir
  (`MentionChecker.clean`; "ör." ve "vb." cümle sonu sayılmaz). Kolon adı yazım hatası uyarıları
  silinir. Silinen her ad ve cümle sayılır. **Hedefte:** aynen; silinen adlar loga yazılmaz
  (Requirement 1).
- **Asıl kavram** (`build_answer`, `Cleaner.core_columns`; kaynak kararları ADR-041, ADR-042,
  ADR-044): Model talebin asıl bilgisini (`core_concept`), onu taşıyan 1–3 kolonu (`core_columns`,
  "T12.Kolon") ve bulunup bulunmadığını (`core_found`) yazar. Öneri varken `core_found` yanlışsa, model
  "BULUNAMADI" dediyse ya da gösterilen kolonların hiçbiri okunan tablolarda yoksa öneriler ve kurgu
  boşaltılır, "İlgili" kapsamlı tek not eklenir ("“<asıl kavram>” bu tablolarda yok; yalnız yakın
  bilgiler var: <tablolar>.") ve sonuç BULUNAMADI olur. Alanı hiç olmayan yanıtta bu denetim yapılmaz.
  İkinci bir denetim çağrısı yoktur (ADR-044 reddedildi). **Hedefte:** aynen.
- **Kodun verdiği sıra** (`core_first`, `narrow_tables`, `NARROW_MARKERS`; kaynak kararı ADR-043):
  Asıl kavram kolonlarını en çok taşıyan tablo öne geçer; eşitlikte açıklamasında dar kitle ya da
  türetilmiş veri ifadesi ("model girdisi", "eğitim verisi", "akıllı hedefleme", "özel bankacılık
  müşterileri", "segmentasyonu girdisi" …) geçen tablo genel tablonun arkasına düşer; sonra güven gelir.
  Öne geçen tablo en yüksek güvenden düşük gösterilmez. Kolon gösterilmemişse modelin sırası kalır.
  **Hedefte:** aynen.
- **Sonuç etiketi ve eksik bilgi** (`_verdict_summary`, `with_verdict`; kaynak kararı ADR-045):
  Modelin etiketi (VAR, KISMEN VAR, BULUNAMADI; tanınmayan değer KISMEN VAR sayılır) önerilere göre
  düzeltilir: öneri yoksa BULUNAMADI (model başka dediyse özet "Talebi karşılayan, sözlükte doğrulanmış
  bir tablo bulunamadı." olur), öneri varken BULUNAMADI dediyse KISMEN VAR. Özet her zaman geçerli
  etiketle başlar ("KISMEN VAR. …"). Dikkat maddelerinden yazım hatası uyarıları atılır. Eksik bilgi
  (`missing`) yalnız KISMEN VAR'da ve en çok 3 maddedir. **Hedefte:** aynen.
- **Cevap nesnesi** (`Engine._analyze_llm`, `Engine.recommended_match`, `analyst.column_caveats`,
  `src/vsa/models.py` `AnalysisResult`): Her öneri bir tablo eşleşmesine dönüşür: güven ve seviye
  modelin güveninden; kolonlar kelime ilgililiğiyle, anahtar ve zaman kolonları "yapısal" rolüyle;
  kolon uyarıları modelin uyarı, dikkat ve not cümlelerinden o kolonu adlandıranlardır; tablo ipucu
  havuzundaysa kural motorunun bileşenleri ve kavramları "Ayrıntılar" için eklenir. Notların sonuna
  "Doğrulama" notu eklenir ("Önerilen tüm tablo ve alanlar veri sözlüğüne karşı doğrulandı[; sözlükte
  karşılığı olmayan N ad/cümle rapordan çıkarıldı]. Skorlar sözlük tanımlarına dayanır; …"); bu sayıya
  1. adımın bilinmeyen kimlikleri de katılır. Yöntem listesi dokuz satırdır (model; 1. adımın aday
  sayıları ve süresi; okunan adaylar; benzer tablolar; aile aramasıyla eklenenler; 2. adımın kolon
  sayısı ve süresi; ipucu notu; güven notu; doğrulama sayısı). `near_misses` analist cevabında hep
  boştur. `dictionary_source` sözlük dosyasının adıdır (`dictionary.jsonl`). **Hedefte:** aynen;
  `dictionary_source` yine `dictionary.jsonl`'dır (Decision 11).
- **Kural cevabı** (`Engine.rule_answer`, `src/vsa/scoring/explain.py`, `src/vsa/validate.py`):
  Kural motorunun kendi cevabı kullanıcıya hiç gösterilmez (kaynak kararı ADR-038); yalnız ölçüm ve
  testlerde kullanılır. **Hedefte:** taşınır, hiçbir uçtan ve ekrandan erişilmez (Decision 14).

### Durdurma, kayıt, rapor, durum

- **Durdurma** (`src/vsa/cancel.py`, `POST /api/ask/cancel`, `client._stoppable`): Her soruya bir
  durdurma belirteci verilir. "Durdur" belirteci tetikler: açık model bağlantıları kesilir (model
  sunucusu üretimi bırakır), sırada bekleyen soru bekleyişten çıkar, akış `Cancelled` ile biter ve
  kural cevabına düşmez. Yanıt `{"cancelled": true, "ask_id": …}`; bilinmeyen kimliğin durdurulması
  `{"ok": false}`. **Hedefte:** `POST /analyses/{analysis_id}/cancel`; sıradaki iş hemen düşer;
  tekrarlanan durdurma aynı son durumu döndürür (Requirement 11).
- **Analiz kaydı** (`App._log_analysis`, `src/vsa/trace.py`): Her soru, kayıtlı cevap ve hata dahil,
  `data/logs/analyses.jsonl` dosyasına bir satır yazar: kimlik, zaman, istemci adresi ve adresten
  çözülen makine adı, soru (2000 karakter), köken (liste terimi için "liste.xlsx #3"), akış (`analist`,
  `önbellek`, `yapılamadı`, `durduruldu`, `hata`), model, sonuç etiketi, özet (500 karakter),
  önerilen tablolar (10), sebep, kayıtlı cevap bilgisi, hata metni (500), süre, model çağrısı ve
  belirteç sayıları, sözlük sürümü ve adım zaman çizelgesi. Adımlar iç içe kaydedilir: "Önceki cevap
  araması", "Sırada bekleme", "Model sunucusu kontrolü", "Analist akışı" → "Kural motoru ipuçları" (→
  "Sorgu genişletme", "BM25 arama", "Kolon skorlama", "Tablo toplama ve konu uyumu"), "1. adım — aday
  seçimi" (→ "LLM çağrısı"), "Aile araması", "2. adım — kolon okuma ve rapor" (→ "LLM çağrısı"); anlık
  olaylar "Analiz yapılamadı", "Durduruldu", "Yanıt JSON değil — onarım isteniyor" (model yanıtının ilk
  200 karakteriyle) ve "Model bir özelliği reddetti — onsuz yeniden" (sunucunun hata metniyle).
  **Hedefte:** kayıt PostgreSQL'de, sahibi analysis-records; adres ve makine adı yerine kullanıcı;
  akışlar İngilizce sabit kodlarla saklanır; adım adları aynen, ana adımlar ayrıca canlı akışın adım
  anahtarını taşır; olaylar model yanıtı ve sunucu hata metni taşımaz; tam cevap kayda yazılır
  (Requirement 18).
- **Rapor** (`App.report`, `GET /api/report/<id>`, `src/vsa/report/excel.py` `write_ask_report`,
  `report_path`, `slugify`): Son 50 cevap bellekte tutulur (`MAX_REPORTS`); rapor istenince
  `data/out` altına `VSA_ask_<konu>_<YYYYMMDD_HHMM>.xlsx` yazılıp gönderilir. Sunucu yeniden başlarsa
  ya da 50 cevap aşılırsa rapor bulunamaz. **Hedefte:** rapor saklanan cevaptan bellekte üretilir, diske
  yazılmaz; analiz kaydı durdukça indirilir (Requirement 16).
- **Durum** (`App.status`, `GET /api/status`): kolon ve tablo sayısı, model adı, model durumu (`ok`,
  `none`, `down` ve sebep; sebep adres içerebilir), aday sayısı ayarı. Arayüz 60 saniyede bir sorar.
  **Hedefte:** `GET /status`; sebep adres içermez; `dictionary_version` eklenir (Requirement 17).
- **Günlük** (`App._answer`, `analyst.py`, `validate.py`): Hata günlüğü sorunun ilk 80 karakterini ve
  istisna metnini; doğrulama uyarıları sözlükte olmayan tablo ve kolon adlarını ve modelin yazdığı
  kimlikleri loga yazar. **Hedefte:** hiçbiri yazılmaz (Requirement 1).

### Arayüz (`src/vsa/web/static/index.html`)

- **Soru çubuğu** (`ask`, `stopAsk`, `setBusy`, `foldSearch`, `autosize`): Açılışta ortada "Hangi
  veriye ihtiyacınız var?" başlığı ve "Örn. Kredi kartı limit doluluk oranı verisine ihtiyacımız
  var, nerede?" örnekli çok satırlı kutu vardır; Enter gönderir, Shift+Enter alt satıra geçer, kutu
  180 piksele kadar büyür. İlk sorudan sonra çubuk üst çizgiye kayar ve orada kalır ("/" odaklar,
  Esc bırakır; hareket azaltma tercihine uyulur). Metin bir tablonun tam adıysa soru sorulmaz, tablo
  dosyası açılır. Analiz sürerken "Ara ↵" düğmesi "Durdur" olur (Esc de durdurur); durdurulunca
  "Analiz durduruldu. Soruyu düzenleyip yeniden arayabilirsiniz.", hata olunca "Analiz başarısız:
  <ileti>" yazılır. Sayfa aynı anda tek soru yürütür. İlerleme yalnız Evren'in tarama hareketiyle
  gösterilir; sıra ve adım gösterilmez. **Hedefte:** React'te aynı görünüm ve etkileşim; ilerleme
  yine tarama hareketiyle gösterilir, adım gösterilmez; iş sıradayken Evren'in bilgi satırı "sırada"
  der; sayfa yenilenince süren analize yeniden bağlanılır (Requirement 19, 20).
- **Cevap görünümü** (`answerView`, `foundBlock`, `overview`, `resultCard`, `sideCard`, `richOf`,
  `splitSummary`, `ruleNote`, `ruleShort`): Üst satırda sonuç rozeti, cevabı kimin yazdığı ("Analist
  · <model>" ya da "Analiz yapılamadı"), kayıtlı cevapsa "Önceki cevap · gg.aa.yyyy" ve "↻ Yeniden
  analiz et", soru ve "⬇ Excel raporu" vardır. "Bir bakışta": sonuç sözcüğü (✓ Bulundu, ◐ Kısmen
  bulundu, ✕ Bulunamadı), eksik bilgi ("eksik: …"), öneri sayısı, en iyi eşleşme (güven halkası, ad,
  kapsadığı bilgi, yol), diğer öneriler ve yan sütunda "Hangi tablo neyi karşılıyor" matrisi (●
  karşılıyor, ◐ değerleri üzerinden, ○ karşılamıyor; en çok 8 kavram). "Analistin özeti" ilk cümleyi
  başlık, gerisini metin olarak ve talebin yorumunu gösterir. Öneri satırları tek tek açılır: yol,
  kapsadığı bilgi, gerekçe, uyarılar, kolonlar (ilk 6, "+N kolon"), "Ayrıntılar" (kullanım önerisi,
  kavramlar, puan bileşenleri ve analist güveni). Yan sütunda "Önerilen kurgu", "Dikkat edilmesi
  gerekenler", "Notlar ve öneriler"; altta "Arama ayrıntıları" (kavramlar, genişletme terimleri,
  yöntem, süre, sözlük sürümü). Metindeki tablo adları öneriye ya da tablo dosyasına götüren düğme,
  kolon adları sabit genişlikli yazı olur. **Hedefte:** aynı işlev ve görünüm React'te; renkler
  kaynak CSS değerlerini taşıyan belirteçlerden (Requirement 21).
- **Model uyarısı** (`loadStatus`, `#model-warn`): Model bağlı değilse "Sohbet modeli bağlı değil: soru
  analiz edilemez. Yönetim → Yapay zekâ sayfasından bir model bağlayın.", ulaşılamıyorsa "<sebep>.
  Model çalışmadan soru analiz edilemez." çubuğun altında yazılır; 60 saniyede bir ve analist dışı her
  cevaptan sonra yenilenir. **Hedefte:** aynı metinler; sebep adres içermez (Requirement 22); uyarı
  satırının sahibi, durum göstergesiyle birlikte dictionary-explorer'dır.

### Sayısal değerler: ayar mı, sabit mi

**Ayarlar** — sahibi search-settings PRD'sidir; bu PRD yalnız okur. Model örnekleme değerleri
llm-connection PRD'sinindir. Kaynakta "ekranda" olmayanlar yalnız ayar dosyasıyla değişirdi.

| Ayar | Varsayılan | Kullanıldığı yer | Kaynakta ekranda |
|---|---|---|---|
| `search.candidate_object_columns` | 1000 | aday kolon havuzu | evet |
| `search.top_k_objects` | 20 | yalnız kural cevabının sınırı (+3 yakın aday) | evet |
| `search.field_weights` | ad 3, eş anlamlı 2, açıklama 1, tablo 1 | kelime indeksi | evet |
| `search.bm25.k1`, `b` | 1,2; 0,75 | kelime indeksi | evet |
| `expansion.enabled`, `synonyms`, `weight` | açık; açık; 0,6 | terim genişletme | evet |
| `scoring.min_candidate_score` | 0,5 | ipucu havuzu eşiği | evet |
| `scoring.object.*` | en iyi kolon 0,35; kapsama 0,21; zaman 0,07; müşteri 0,07; konu 0,30 | tablo puanı | evet |
| `scoring.min_answer_score`, `min_answer_coverage`, `rule_only_factor` | 0,35; 0,5; 0,8 | yalnız kural cevabı | hayır |
| `analyst.shortlist` | 14 | 1. adım en çok aday | evet |
| `analyst.detail_columns` | 8 | tam açıklamalı kolon | evet |
| `analyst.min_confidence` | 0,5 | öneri eşiği | evet |
| `analyst.max_tokens` | 8000 | 2. adım yanıt sınırı | evet |
| `analyst.confusables`, `family_tables`, `family_extra`, `search_tables` | 6; 2; 6; 3 | benzer tablo, aile araması, emniyet ağı | hayır |
| `analyst.evidence_columns`, `description_chars`, `full_table_columns` | 60; 420; 90 | 2. adım malzemesi | hayır |
| `cache.enabled`, `meaning`, `max_age_days` | açık; açık; 30 | kayıtlı cevap | evet |
| model `temperature`, `reasoning_effort`, `seed`, `timeout` | 0; `none`; 42; 900 sn | model isteği (llm-connection) | evet |

**Kod sabitleri** — sahibi bu PRD'dir; değişikliği altın setle önce ve sonra ölçülür.

| Sabit | Değer | Yer |
|---|---|---|
| `NEAR_MISS_COUNT` | 3 | `pipeline.py` (kural cevabı) |
| `ANALYST_HINT_TABLES`, `ANALYST_RULE_POOL`, `ANALYST_HINT_COLUMNS` | 15; 60; 25 | `pipeline.py` ipuçları |
| `FAMILY_MIN_SHARE`; ilgililik eki | 0,6; 0,5 × terim eşleşmesi | `pipeline.py` |
| 1. adım yanıt sınırı | 2500 belirteç | `analyst.py` (`shortlist` işlevi) |
| `STRUCTURAL`; `SPREAD_MIN_TABLES`; `CONFUSABLE_COLUMNS_PER_TABLE` | 14 kolon adı; 4; 10 | `analyst.py` |
| arama terimi; aile × terim; eksik bilgi; yaygın alan | 12; 6 × 8; 3; 8 ad × 12 tablo | `analyst.py` |
| `NARROW_MARKERS`; yazım hatası ifadeleri | 7 ifade; 3 ifade | `analyst.py` |
| `HIGH_THRESHOLD`, `MEDIUM_THRESHOLD` | 0,80; 0,50 | `combine.py` |
| kolon kuralı tabanı ve ekleri | 0,35; 0,25; +0,30; +0,20; +0,15; +0,15; +0,10; −0,15; −0,10; `NEGATION_WINDOW` 1 | `rules.py` |
| `MAX_RELATED_COLUMNS`; `RELATED_MIN_SHARE`; zaman ve müşteri kolon tabloları | 8; 0,6; sabit listeler | `aggregate.py` |
| `OBJECT_FIELD_WEIGHTS` | tablo adı 4; kolon adı 1; eş anlamlı 1; açıklama 0,3; profil 3 | `topic.py` |
| `GENERIC_SYNONYM_DF`; `MAX_PHRASE_LEN` | 40; 6 | `query_expander.py` |
| `MIN_STEM_LEN`; ek atma turu | 4; 3 | `normalize.py` |
| `CACHE_FORMAT`; `NEGATIONS`; parmak izi; istem özeti | 3; 13 kelime; 16 hane; 12 hane | `answer_cache.py` |
| `MAX_ENTRIES` | 2000 | `answer_store.py` |
| `MAX_QUERY_CHARS`; `top` | 4000; 1–10 (5) | `server.py` |
| `HEALTH_TTL`; `HEALTH_TIMEOUT`; `CONNECT_TIMEOUT` | 30 sn; 5 sn; 10 sn | `client.py` (sahibi llm-connection) |

**Hedefte:** ayarlar ayar, sabitler sabit kalır; değerler aynıdır.

## İşlevsel gereksinimler

Requirement 1: Kaynaktaki şu modüller backend'e taşınır ve davranışları değişmez:
`text/normalize.py`, `expansion/query_expander.py`, `index/bm25.py`, `features.py`,
`scoring/rules.py`, `scoring/aggregate.py`, `scoring/combine.py`, `scoring/topic.py`,
`scoring/explain.py`, `validate.py`, `llm/analyst.py` (`MentionChecker` dahil),
`llm/analyst_prompts.py`, `models.py`, `pipeline.py` (`Engine`), `answer_cache.py` (anahtarlar,
parmak izi, cevabın yapılandırılmış biçimi), `cancel.py`, `trace.py` ve `report/excel.py` (tek soru
raporu bu PRD'nin, liste raporu list-search PRD'sinindir). İzin verilen farklar yalnız şunlardır: (a)
içe aktarma yolları; (b) dosya okuyan kurucuların (`Engine.from_dictionary_file`, `Engine.from_index`,
`Resources.from_settings`) yerine PostgreSQL'den gelen veriyle kuran tek kurucu (Requirement 3); (c)
soru, tablo ya da kolon adı veya model çıktısı yazan log satırlarının kaldırılması ya da yalnız sayı
taşıyan olaya dönüşmesi; (d) parmak izinin ayarları search-settings ve llm-connection kaynaklarından
okuması (Requirement 13); (e) "Analiz yapılamadı" sebeplerinin eşlemesi (Requirement 5); (f) rapor
yazıcısının dosya yerine bayt üretmesi; (g) adım kaydının analiz kaydına yazılması; (h) model
istemcisinin llm-connection portuyla değişmesi (Requirement 24). Bu modüllerin büyük harfli bütün
sabitleri kaynakla aynı değeri taşır (sabit fark testi). Backend'de `.lower()`, `.upper()` ve
`.casefold()` yalnız uygulamanın tek Türkçe metin yardımcısındadır (`app/domain/turkish_text.py`).

Requirement 2: Aynı sözlük içeriği (kolonlar, sıraları, kimlikleri ve profilleri; sürüm dizgesi ve
kaynak adı iki tarafa aynı verilir), terim sözlüğü, durak kelimeler, ayarlar ve sahte model
yanıtlarıyla hedef şu çıktıları kaynak `76e21a3` ile bayt bayt aynı üretir: (1) genişletilmiş talep
(parçalar, kelime araması ağırlıkları, kavramlar, genişletme terimleri, eş anlamlı eşleşmeleri, kavram
ağırlıkları, bilinmeyen kavramlar); (2) `rank_objects` sıralaması, 60 sınırıyla ve varsayılan sınırla
(her tablonun puanı, seviyesi, bileşenleri, kapsadığı ve kapsamadığı kavramlar, kolonları, kolon
puanları, sinyalleri, uyarıları ve rolleri); (3) kolon ilgililiği; (4) kural cevabı; (5) ipucu metni;
(6) iki adımın sistem ve kullanıcı mesajları, yanıt şeması ve yanıt sınırı; (7) analist cevabı; (8)
kayıtlı cevap anahtarları (`text_key`, `meaning_key`) ve istem özeti (`prompts_digest`); (9) iki tarafa
aynı `generated_at` verilerek üretilen tek soru Excel raporunun içeriği ve biçimi (sayfa adları ve
sırası; her hücrenin değeri ve türü; yazı tipi, dolgu, kenarlık, hizalama, sayı biçimi; birleştirilmiş
hücreler; sütun genişlikleri ve satır yükseklikleri; dondurulmuş bölme; süzgeç; ızgara çizgisi) ve
dosya adının konu kısmı. Karşılaştırma kanonik yapılandırılmış metinle (anahtarlar sıralı, Türkçe
harfler kaçışsız, ondalık sayılar Python'un tam gösterimiyle, yani `repr` biçiminde) yapılır.
Karşılaştırma dışı yalnız şunlardır: `generated_at`, `elapsed_ms`, yöntem satırlarındaki saniye
değerleri, Requirement 5'te bilerek değişen sebep metinleri ve Excel dosya paketinin oluşturulma
bilgileri. Hedefin çıktıları Python'un karma tohumu (`PYTHONHASHSEED`) değişince de aynıdır.

Requirement 3: Motor PostgreSQL'deki veriden kurulur: kolonlar içe aktarma sırasıyla `0..N-1`
kimliğini alır ve bu sırayla gelir (sıranın saklanması dictionary-management PRD'sindedir); tablo
profilleri Objeler sayfasındandır; terim grupları liste sırasıyla, durak kelimeler küme olarak gelir
(vocabulary-management); ayarlar search-settings PRD'sinin ölçülmüş varsayılanları ve değiştirilmiş
değerleridir. PostgreSQL'den yüklenen sözlük, aynı Excel'in kaynak koduyla ayrıştırılmış haliyle aynı
sırada ve aynı alanlarla motora gelir (test). Motor; sözlük, kelime listeleri ya da indeksi etkileyen
ayar değişince yeniden kurulur (yaşam döngüsü search-settings'tedir). Her iş, yürümeye başladığı andaki
motoru ve etkin sohbet modelini (adı ve örnekleme değerleri) sabitler ve sonuna kadar onları kullanır;
sonraki değişiklik yalnız sonraki işlere uygulanır. Sözlük boşken soru "Sözlük henüz içe aktarılmadı;
Yönetim → Sözlük ekranından şablondaki Excel'i içe aktarın." cevabını alır.

Requirement 4: Talep gövdesi `query`, `top`, `fresh` alanlarını taşır. `query` metindir; baştaki ve
sondaki boşluk kırpılır; kırpılmış hali boşsa `422 query_empty` ("Talep metni boş"), 4000 karakteri
aşarsa `422 query_too_long` ("Talep çok uzun (en fazla 4000 karakter)"); sekme, satır sonu ve satır
başı dışındaki denetim karakterlerini (U+0000–U+001F, U+007F) taşırsa `422 query_invalid_characters`
("Talep metninde izin verilmeyen bir karakter var."). `top` 1–10 tam sayıdır (varsayılan 5); aralık
dışı ya da tam sayı olmayan değer `422 invalid_request`. `fresh` mantıksal değerdir (varsayılan
`false`). Bilinmeyen alan `422 invalid_request`; 32 KB'ı aşan gövde `413 request_too_large`. Analiz,
kaynaktaki gibi kırpılmış metinle yapılır.

Requirement 5: Analizin adımları kaynaktaki sıradadır: sözlük denetimi, sohbet modeli denetimi, model
sunucusu kontrolü (5 saniye süreli, sonucu 30 saniye saklanan kontrol; llm-connection), analist akışı.
Analist yürüyemezse cevap tablosuz `BULUNAMADI`'dır, özeti "Analiz yapılamadı: <sebep>", yöntemi tek
satır "Analiz yapılamadı — cevabı yalnız analist (sohbet modeli) yazar (ADR-038)", akışı
`unavailable`'dır. Sebep metni şudur; adres, istisna metni ya da sunucunun hata gövdesi içermez:

| Durum | Sebep |
|---|---|
| Sözlük yok | Sözlük henüz içe aktarılmadı; Yönetim → Sözlük ekranından şablondaki Excel'i içe aktarın. |
| Sohbet modeli bağlı değil | Sohbet modeli bağlı değil; Yönetim → Yapay zekâ sayfasından bir model bağlayın. |
| Sunucu kontrolü: bağlantı, ad çözümü, zaman aşımı, sertifika ya da ağ politikası | Model sunucusuna ulaşılamadı. |
| Sunucu kontrolü: HTTP 401 ya da 403 kodu | Model sunucusu yanıt vermedi: Sunucu HTTP <kod> döndürdü (API anahtarı eksik veya geçersiz) |
| Sunucu kontrolü: başka HTTP kodu | Model sunucusu yanıt vermedi: Sunucu HTTP <kod> döndürdü |
| Sunucu kontrolü: tanınmayan yanıt | Model sunucusu yanıt vermedi: Sunucu beklenmeyen bir yanıt döndürdü |
| Analist: bağlam penceresi aşıldı | Modelin bağlam penceresi tablo kataloğu için küçük (~70k token gerekir). Model sunucusunda daha geniş bağlam açın (vLLM: --max-model-len) veya Yönetim → Yapay zekâ'dan daha geniş bağlamlı bir sohbet modeli seçin. |
| Analist: zaman aşımı ya da HTTP 504 kodu | Model zamanında yanıt vermedi (zaman aşımı). |
| Analist: bağlantı kurulamadı (ret, ad çözümü, sertifika ya da ağ politikası) | Model sunucusuna ulaşılamadı. |
| Analist: onarım denemesinden sonra da geçerli yapılandırılmış yanıt yok | Model hatası: model geçerli JSON üretmedi |
| Analist: tanınmayan yanıt | Model hatası: beklenmeyen yanıt |
| Analist: başka HTTP kodu | Model hatası: HTTP <kod> |
| Analist: sebepsiz başarısızlık | Model yanıt vermedi. |

Durum, llm-connection PRD'sinin hata sınıfından çıkarılır; bağlam aşımı kendi sınıfıyla ayırt edilir.

Requirement 6: Doğrulama ve asıl kavram kuralları kaynak testleriyle korunur: öneri yalnız okunan
tablolardan ve yalnız katalog kimliği, tam ad ya da okunanlar içinde tek eşleşen tablo adıyla seçilir;
kolon adı tam ya da Türkçe katlamayla çözülür, çözülemeyen kolon ve kolonsuz öneri düşer ve sayılır;
0,5'in altındaki güven gösterilmez; aynı tablo bir kez, güvene göre ilk `top`; serbest metindeki
katalog kimliği tablo adı olur, "vX (vX)" tekrarı silinir, sözlükte olmayan ad geçen cümle silinir ve
sayılır; yazım hatası uyarıları uyarıdan ve dikkat maddelerinden atılır; asıl kavram yoksa ya da
kolonla gösterilmemişse öneriler "İlgili" notuna döner ve sonuç BULUNAMADI olur (kaynak kararları
ADR-041, ADR-042); öneriler asıl kavram kolonlarına, eşitlikte dar kitle işaretine, sonra güvene göre
dizilir ve öne geçen tablo en yüksek güveni alır (ADR-043); sonuç etiketi önerilere göre düzeltilir ve
özet etiketle başlar; eksik bilgi yalnız KISMEN VAR'da ve en çok 3 maddedir (ADR-045); "Doğrulama"
notu düşen ad ve cümle sayısını (1. adımın bilinmeyen kimlikleri dahil) söyler.

Requirement 7: Tamamlanan işin cevabı (`result`) kaynaktaki alanlarla döner: `query`, `verdict`,
`summary`, `objects[]` (`rank`, `key`, `database`, `schema`, `name`, `groups`, `score`, `level`,
`llm`, `components`, `covered`, `missing`, `long_format`, `dimension`, `reason`, `caveat[]`, `usage`,
`covers`, `columns[]`: `key`, `column`, `object`, `description`, `synonyms`, `pii`, `group`, `role`,
`signals`, `caveats`), `near[]` (analist cevabında boş), `notes[]` (`scope`, `title`, `text`),
`concepts`, `expansion`, `method`, `elapsed_ms`, `dictionary_version`, `llm_model`, `analyst`,
`fallback`, `interpretation`, `design`, `attention`, `reused` (`at`, `query`, `match` ya da `null`),
`missing`. Kaynaktaki `report_id` kalkar; rapor iş kimliğiyle alınır. Cevap, answer-feedback
PRD'sindeki oy uygulamasından o anki kullanıcı için geçirilerek döner; oy uygulaması hata verirse cevap
oysuz döner ve olay yazılır. "Analiz yapılamadı" cevabı da tamamlanmış cevaptır. `dictionary_source`
kaynaktaki gibi `dictionary.jsonl`'dır (Decision 11).

Requirement 8: Her analiz bir iştir. Durumlar: `queued` (sırada), `running` (yürüyor), `completed`
(tamamlandı; akış `analyst`, `reused` ya da `unavailable`), `failed` (beklenmeyen hatayla bitti; kod
`analysis_failed`, ileti "Analiz beklenmeyen bir hatayla durdu. Soruyu yeniden sorun; sorun sürerse
yöneticinize bildirin."), `cancelled` (durduruldu), `interrupted` (yarıda kesildi). Geçişler: kabulde
kayıtlı cevap bulunursa doğrudan `completed`, yoksa `queued`; `queued` → `running` → `completed` ya da
`failed`; `queued` ya da `running` → `cancelled` ya da `interrupted`. Son durumdan çıkış yoktur.
İşin sahibi onu başlatan kullanıcıdır; iş kimliği analiz kaydının `public_id` değeridir.

Requirement 9: Kuyruk ve eşzamanlılık: (a) tek süreç içi kuyruk ilk gelen ilk çıkar sırasıyla yürür;
(b) aynı anda yürüyen iş sayısı `DWHNAVIGATOR_ANALYSIS_CONCURRENCY` değerini (varsayılan 1; 1–4;
Decision 2) hiçbir anda aşmaz; (c) sırada bekleyen iş sayısı `DWHNAVIGATOR_ANALYSIS_QUEUE_LIMIT`
değerine (varsayılan 20; 1–200) ulaştıysa yeni tek soru `503 analysis_queue_full` alır ("Şu anda çok
sayıda analiz sırada; biraz sonra yeniden deneyin."), kabulde kayıtlı cevapla biten iş kuyruğa
girmediği için bu sınıra takılmaz; (d) kullanıcı başına iş sınırı yoktur: aynı kullanıcının yeni tek
soru isteği de sıraya girer (kaynakla aynı, Decision 23); (e) list-search bir listenin terimlerini
kuyruğa birer birer koyar: sonraki terim, önceki terim son duruma ulaşınca kuyruğun sonuna girer,
böylece eşzamanlılık 1 iken tek soru en çok bir liste teriminin bitmesini bekler; (f) bekleyen işin
önündeki iş sayısı (`ahead`: yürüyenler + önündeki bekleyenler) API'de ve canlı akışta bildirilir;
arayüz bu sayıyı göstermez (Requirement 20).

Requirement 10: Canlı ilerleme akışı `GET /analyses/{analysis_id}/events` yalnız işin sahibine
açılır; oturum, rol ve sahiplik akış açılmadan denetlenir, başarısızsa normal hata zarfı döner. Her
bağlantı `snapshot` olayıyla başlar (durum, `ahead`, yürüyen adım, geçen süre); iş son durumdaysa
hemen ardından son olay gelir. Sonra değişiklikler sırasıyla gelir: `queued` (`ahead` değişince),
`started`, `step` (adım anahtarı; `started`, `finished` ya da `error`; adım süresi) ve tek bir son
olay (`completed` akış ve sonuç etiketiyle, `failed` kod ve iletiyle, `cancelled`, `interrupted`);
son olaydan sonra sunucu akışı kapatır. Adım anahtarları sabit kümedir: `saved_answer_lookup`,
`queue`, `model_check`, `rule_hints`, `shortlist`, `family_search`, `analyst_report`. Olaylar soru
metni, tablo ve kolon adı, istem ve model yanıtı taşımaz. Olay yokken 15 saniyede bir canlılık
satırı (`: canlı`) gider. Bağlantı koparsa ya da erişim belirtecinin süresi bitince sunucu akışı
kapatırsa ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
Requirement 12) akış ucu çalışmayı bırakır, iş sürer (Decision 6). Yeniden bağlanan istemci son
aldığı olayın kimliğini `Last-Event-ID` başlığıyla gönderir; sunucu önce işin güncel durumunu
taşıyan `snapshot`'ı, ardından o kimlikten sonraki adım olaylarını sırasıyla yeniden gönderir
(olaylar iş süresince süreç belleğinde tutulur); başlık yoksa yalnız `snapshot` ve sonraki olaylar
gelir. Kullanıcı başına aynı anda en çok 5 açık akış olur; fazlası `429 too_many_streams`. Yanıt
`Content-Type: text/event-stream`, `Cache-Control: no-cache` ve `X-Accel-Buffering: no` başlıklarını
taşır.

Requirement 11: `POST /analyses/{analysis_id}/cancel` yalnız işin sahibine açıktır. Sıradaki iş
kuyruktan hemen çıkar ve `cancelled` olur. Yürüyen işte süren model çağrısının bağlantısı en geç 2
saniye içinde kapanır (model sunucusu istemcinin ayrıldığını görür), yeni model çağrısı başlamaz, iş
en geç 5 saniye içinde `cancelled` olur; kural cevabına ya da kısmi cevaba düşülmez, kayıtlı cevap
yazılmaz. Analiz kaydı `cancelled` akışı, `cancelled` kodlu "Kullanıcı durdurdu" hatası ve
"Durduruldu" olayıyla kapanır. Son durumdaki işin durdurulması hiçbir şeyi değiştirmez ve son durumu
`200` ile döndürür; tekrarlanan istek aynı sonucu verir.

Requirement 12: Süreç kapanırken (dağıtım, yeniden başlatma) yeni iş kabul edilmez (`503
analysis_unavailable`, "Uygulama yeniden başlıyor; biraz sonra yeniden deneyin."), sıradaki ve yürüyen
işler `interrupted` olarak kaydedilir ve açık akışlara `interrupted` olayı gider. Açılışta `queued` ya
da `running` kalmış kayıtlar (çökme sonrası) `interrupted` yapılır; güncellemede eski ve yeni süreç
birlikte çalışmadığı için
([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Decision 5) açılışta bu durumda görünen her kayıt yarıda kalmış bir işe aittir. Açılışta ilk arama
indeksi kurulana kadar yeni iş kabul edilmez: `503 search_index_not_ready`
([search-settings](../009-search-settings/PRD.md) Requirement 10). Yarıda kesilen iş kendiliğinden
yeniden başlatılmaz (Decision 21); arayüz "Analiz yarıda kesildi (uygulama yeniden başladı). Soruyu
yeniden sorun." yazar.

Requirement 13: Kayıtlı cevap anahtarları kaynaktaki gibidir. `text_key`: talebin Türkçe katlanmış
harf ve rakam dizileri, tek boşlukla (büyük/küçük harf, Türkçe harf, noktalama ve boşluk farkı önemsiz).
`meaning_key`: talepteki kavramların kanonik kümesi (her kavramın türü, değeri, alternatifleri ve
kırılım değeri işareti; bir terim grubunun bütün üyeleri aynı alternatifleri paylaşır), talepteki
sayılar ve olumsuzluk kelimeleri (`NEGATIONS`: yok, degil, haric, harici, disinda, olmayan, olmadan,
olmayanlar, hic, without, except, not, no); içerik kavramı yoksa boştur. Parmak izi, şu bileşenlerin
anahtarları sıralı kanonik metninden hesaplanan SHA-256 özetinin ilk 16 onaltılık hanesidir:
`CACHE_FORMAT` (3); sözlük sürümü; terim grupları (sırasıyla terim, eşdeğerler, alan, not); sıralı
durak kelimeler; `top`; istem özeti (istem modülündeki büyük harfli metin ve şema
sabitlerinin SHA-256 özetinin ilk 12 hanesi); search-settings'teki arama, genişletme, puanlama ve
analist ayarlarının tamamı; etkin sohbet modelinin adı, sıcaklığı, düşünme modu ve tohumu. Kayıtlı
cevap ayarları (`cache.*`) bileşen değildir. Bileşenlerden biri değişince eski kayıtlı cevaplar
kullanılmaz ama silinmez; bileşen eski değerine dönerse yeniden kullanılır.

Requirement 14: Kayıtlı cevabın kullanılması ve yazılması:
- Kullanım yalnız soru akışındadır (tek soru ve liste terimleri); quality-evaluation PRD'sinin ölçüm
  betiği kayıtlı cevap okumaz ve yazmaz.
- Arama `cache.enabled` kapalıysa ya da `fresh` ise yapılmaz. Aynı kiracıda, aynı parmak izli ve
  `cache.max_age_days` (0 = sınırsız) günden yeni kayıtlar içinde önce aynı `text_key`'in en yenisi
  ("aynı soru"), yoksa `cache.meaning` açık ve `meaning_key` boş değilse aynı `meaning_key`'in en
  yenisi ("aynı anlam") alınır.
- Bulunan cevap güncel sözlükle kurulur; kolonlarından biri sözlükte yoksa kullanılmaz ve analiz
  yapılır. Kullanılan cevapta yöntem listesinin başına Mevcut davranış bölümündeki satır eklenir (N,
  saklanan cevabın analiz süresidir; tarih İstanbul saatiyle, `Europe/Istanbul`); `reused` alanı
  `at` (gg.aa.yyyy SS:dd), `query` (önceki soru) ve `match` ("aynı soru" ya da "aynı anlam") taşır;
  `query` yeni sorudur; `elapsed_ms` aramanın süresidir.
- Arama iki kez yapılır: iş kabul edilirken (bulunursa iş kuyruğa girmeden `completed`, akış `reused`
  olur) ve iş yürümeye başlarken (o anki motorun parmak iziyle). Eşzamanlılık 1'den büyükken aynı
  `text_key` ve parmak izli bir iş yürüyorsa, `fresh` olmayan yeni iş yürümeye başlamadan önce onun
  bitmesini bekler, sonra arar. Aynı anda sorulan aynı soru tek kez analiz edilir.
- Cevap yalnız akışı `analyst` ise, iş durdurulmadıysa ve işin motoru bitişte hâlâ geçerli motorsa
  yazılır. `fresh` ile yapılan analiz de yazılır. Aynı kiracı, `text_key` ve parmak izli eski kayıt
  yenisiyle değişir. En yeni 2000 kayıt tutulur; fazlası en eskiden başlayarak silinir.
- Depo okuma ya da yazma hatası analizi durdurmaz: okuma hatasında analiz yapılır, yazma hatasında
  cevap yine döner; olay ve ölçüm üretilir.

Requirement 15: `GET /saved-answers/summary` (`yonetici`) toplam kayıt sayısını, güncel parmak
iziyle (`top` 5) kullanılabilecek kayıt sayısını ve en yeni kaydın zamanını döndürür.
`DELETE /saved-answers` (`yonetici`) kiracının bütün kayıtlı cevaplarını kalıcı siler ve silinen
sayıyı döndürür; tekrarı 0 döndürür. Bu iki uç kayıtlı cevapların tek uçlarıdır:
[search-settings](../009-search-settings/PRD.md) Bakım sayfasının "Önceki cevapları sil…" düğmesi
ile [analysis-records](../008-analysis-records/PRD.md) Genel bakış kartı ve "Temizle…" akışı onları
kullanır. answer-feedback PRD'sinin "cevaba 👎 çoğunluğu" kararı için iç hizmet, verilen `text_key`
ya da (boş değilse) `meaning_key` ile eşleşen kayıtları, parmak izinden bağımsız siler ve sayısını
döndürür. Silmeler kalıcıdır; yedek ve yazılımsal silme yoktur (Decision 9).

Requirement 16: `GET /analyses/{analysis_id}/report` yalnız işin sahibine açıktır ve `completed` iş
için (analistin, kayıtlı ya da "Analiz yapılamadı" cevabı) analiz kaydındaki cevaptan istek anında,
bellekte üretilir; diske ve veritabanına yazılmaz. Başka durumdaki iş `409 analysis_has_no_result`
("Bu analizin raporu yok."). Oylar rapora uygulanmaz (kaynak kararı ADR-036). Dosya adı
`VSA_ask_<konu>_<YYYYMMDD_HHMM>.xlsx` (konu: talebin ilk 40 karakteri katlanır, harf ve rakam
dışındakiler `_` olur, boşsa `talep`; zaman İstanbul saati). İçerik kaynaktaki gibidir:
- **Özet** sayfası: ızgara çizgisi yok; sütun genişlikleri 16, 46, 70, 10, 12. A1 "Veri Ambarı Veri
  Sözlüğü – İş Birimi Talep Analizi"; 2. satır A–C birleşik "Kaynak sözlük: <ad> (<satır sayısı>
  satır, <tablo sayısı> obje)" (satır sayısı sözlük sürümünün `-` işaretinden sonraki kısmıdır, binlik
  ayırıcı noktadır), D–E birleşik "Üretim: gg.aa.yyyy SS:dd"; 3. satır A–E birleşik "Cevabı üreten:
  Analist (dil modeli: <model>)" ya da "Cevabı üreten: Analiz yapılamadı — <sebep>" (analist değilse
  uyarı dolgusu). 5. satırdan başlayarak A'da kalın etiket, B–E birleşik değer: "Talep", "Sonuç" (sonuç
  dolgusu ve kalın), varsa "Eksik Bilgi" (virgülle), varsa "Talebin Yorumu"; satır yüksekliği, değerin
  120 karakterlik satır sayısı × 14 punto (en az 15 punto) olur. Bir boş satırdan sonra "Öneri Özeti"
  bölüm başlığı ve tablo: Sıra, Veritabanı.Şema.Obje, Kapsadığı Bilgi, Güven (`0.00`), Seviye (seviye
  dolgusu); öneri yoksa tek satır "-", "Sözlükte karşılığı bulunamadı", "-", "-", "-". Sonra "Güven
  Skoru Ölçeği": Yüksek %80–100, Orta %50–79, Düşük %0–49 ve anlamları.
- **Öneriler** sayfası: A1 "Öneriler – Güven Skoruna Göre İlk <N>" (N en az 1); A2 "Talep:", B2 talep;
  3. satır başlıkları: Sıra, Veritabanı, Şema, Obje, Veri Seti Grubu, İlgili Alanlar, Gerekçe, Kısıt /
  Dikkat, Güven Skoru, Güven Seviyesi, Kullanım Önerisi (genişlikler 6, 10, 8, 30, 20, 30, 70, 60, 10,
  11, 40); kolonlar satır sonuyla ayrılır; öneri yoksa tek satır ve gerekçe sütununda özet; Güven
  `0.00` biçimli; seviye dolgulu; bölme A4'te dondurulur; başlık satırından son satıra süzgeç.
- Yazı tipi Arial (gövde 10, başlık 14 kalın, bölüm 11 kalın, küçük 9); renkler: başlık dolgusu ve
  başlık yazısı 1F3864, Yüksek ve VAR C6EFCE, Orta, KISMEN VAR ve uyarı FFEB9C, Düşük ve BULUNAMADI
  FFC7CE; ince kenarlık BFBFBF.
- Kullanıcıdan ya da modelden gelen her metin hücreye metin olarak yazılır; "=" ile başlayan metin
  formül olmaz.

Requirement 17: `GET /status` (`kullanici`, `yonetici`) şunları döndürür: `columns` ve `objects`
(hizmetteki sözlüğün kolon ve tablo sayısı), `dictionary_version` (hizmetteki indeksin kurulduğu sözlük
sürümü; sözlük yoksa `""`), `llm` (bağlı sohbet modelinin adı; model bağlı değilse boş), `llm_state`
([llm-connection](../003-llm-connection/PRD.md) Requirement 12'deki model durumu nesnesi: `state` —
`ok`, `none` ya da `down` —, `model`, `code`, `reason`) ve `shortlist` (hizmetteki motorun
`analyst.shortlist` ayarı; [search-settings](../009-search-settings/PRD.md) Requirement 2'deki okuma
işleviyle). Sunucu kontrolü llm-connection'ın 5 saniyelik kontrolüdür ve sonucu 30 saniye saklanır.
`code` ve `reason` llm-connection'ın sabit sınıfı ve yoklama iletisidir (Requirement 13), adres
içermez. Arama indeksi henüz kurulmadıysa (açılış sırasında) uç 200 ile 0 kolon, 0 tablo ve boş sürüm
döner. Ucun tek sahibi bu PRD'dir; [dictionary-explorer](../007-dictionary-explorer/PRD.md) üst
çubuktaki durum göstergesinde kullanır ve `dictionary_version` değişince haritayı yeniler.

Requirement 18: Analiz kaydına (tablosu analysis-records'ta) şunlar yazılır:
- Kabulde: iş kimliği (`public_id`), kullanıcı (`public_id` ve görünen ad), köken (`question` ya da
  `list`; listede liste kimliği, liste dosyasının adı ve terim sırası), soru (en çok 4000 karakter),
  `fresh`, durum `queued`, kabul zamanı.
- Başlarken: durum `running`, başlama zamanı, sırada bekleme süresi.
- Bitişte: son durum ve akış (İngilizce sabit kodlar: `analyst`, `reused`, `unavailable`,
  `cancelled`, `failed`, `interrupted`; kaynaktaki `analist`, `önbellek`, `yapılamadı`, `durduruldu`,
  `hata` akışlarının ve yeni "yarıda kesildi"nin karşılığıdır; Türkçe görünen adları
  [analysis-records](../008-analysis-records/PRD.md) Requirement 2'dedir), model adı, sözlük sürümü,
  sonuç etiketi, özet, önerilen tablolar (en çok 10), "Analiz
  yapılamadı" sebebi, kayıtlı cevap bilgisi (`at`, `query`, `match`), hata kodu ve Türkçe iletisi,
  toplam süre, model çağrısı ve belirteç toplamları, adım zaman çizelgesi ve tam cevap. Tam cevap
  kayıtlı cevabın biçimidir (kaynaktaki `answer_cache.encode`), yalnız her kolonun sözlük satırı
  içine gömülüdür; böylece sözlük sonradan değişse de kayıt kendi başına açılır. Sonuç ucu ve rapor
  Requirement 7 biçimini bundan üretir.
- Adım adları ve iç içe yapısı kaynaktakiyle aynıdır (Mevcut davranış). Ana adımlar ayrıca
  Requirement 10'daki canlı akış adım anahtarını taşır: `saved_answer_lookup` ("Önceki cevap
  araması"), `queue` ("Sırada bekleme"), `model_check` ("Model sunucusu kontrolü"), `rule_hints`
  ("Kural motoru ipuçları"), `shortlist` ("1. adım — aday seçimi"), `family_search` ("Aile
  araması"), `analyst_report` ("2. adım — kolon okuma ve rapor"); alt adımlar ve olaylar anahtar
  taşımaz. Anahtarların aşamalara ve ekrandaki adlara eşlemesi analysis-records Requirement 3'tedir.
  Adım ayrıntıları yalnız sayı ve model adı taşır (ör. "12 kavram, 31 arama terimi", "14 aday, 3
  benzer tablo", "2 tablo eklendi", "7 tablo, 412 kolon"); "Önceki cevap araması" ayrıntısı eşleşme
  türü ve önceki sorunun ilk 120 karakteridir. "Yanıt JSON değil — onarım isteniyor" ve "Model bir
  özelliği reddetti — onsuz yeniden" olayları model yanıtı ve sunucu hata metni taşımaz; model çağrısı
  döndüğünde, o çağrının adımına yazılırlar, bu yüzden zaman çizelgesindeki yerleri yaklaşıktır.
  Başarısız model çağrısı adımı hata sınıfını taşır.
- Kayıt yazılamazsa cevap yine döner; olay ve ölçüm üretilir.

Requirement 19: Soru çubuğu kaynaktaki gibidir: açılış başlığı, örnekli kutu (erişilebilir adı
"Talep"), Enter ile gönderme, Shift+Enter ile alt satır, 180 piksele kadar büyüme, ilk sorudan sonra
üst çubuğa yerleşme ("/" odaklar, Esc bırakır; hareket azaltma tercihine uyulur), tam tablo adında
tablo dosyasını açma (dictionary-explorer). Sayfa aynı anda tek soru yürütür; analiz sürerken düğme
"Durdur" olur (erişilebilir adı "Analizi durdur", ipucu "Analizi durdur (Esc)") ve Esc de durdurur.
Kullanıcı başlatma yanıtı gelmeden durdurursa arayüz yanıtı bekler ve işi hemen durdurur. Sayfa
açılınca `GET /analyses/active` sorulur; sıradaki ya da yürüyen tek soru varsa sorusu çubukta
görünür ve ilerleme sürer. Hata kodları Türkçe iletilere eşlenir; sunucunun ham iletisi gösterilmez.
Soru çubuğunun görünümü kaynakla birebir aynıdır
([dictionary-explorer](../007-dictionary-explorer/PRD.md) Decision 3).

Requirement 20: İlerleme ve durdurma gösterimi kaynaktaki gibidir: ilerleme yalnız Evren'in tarama
hareketi ve bilgi satırıyla gösterilir ([dictionary-explorer](../007-dictionary-explorer/PRD.md)
Requirement 7); adım metni, geçen süre ve önündeki analiz sayısı gösterilmez. İş `queued` iken bilgi
satırının yolculuk günlüğünde "sırada" yazar; iş yürümeye başlayınca yolculuk kaynaktaki evrelerle
sürer (Decision 22). Kayıtlı cevapta cevap gelir. Akış paylaşılan istemciyle, oturum belirteci
başlıkta okunur; koparsa iş son duruma ulaşana kadar 1, 2, 4… en çok 30 saniye arayla, son alınan
olayın kimliği `Last-Event-ID` ile gönderilerek yeniden bağlanılır (Requirement 10). Durdurulunca
"Analiz durduruldu. Soruyu düzenleyip yeniden arayabilirsiniz." (durum bildirimi olarak), hatayla
bitince "Analiz başarısız: <kodun iletisi>", yarıda kesilince Requirement 12'deki ileti yazılır.
Tamamlanınca cevap `GET /analyses/{analysis_id}` ile alınır; akışı `unavailable` ise durum yeniden
sorulur.

Requirement 21: Cevap görünümü kaynaktaki öğeleri ve metinleri taşır: üst satır (sonuç rozeti;
"Analist · <model>" ya da "Analiz yapılamadı" ve ipucunda sebep; kayıtlı cevapta "Önceki cevap ·
gg.aa.yyyy", ipucunda "Bu soru …" ya da "Aynı anlama gelen “…” sorusu … tarihinde analiz edildi;
kayıtlı cevap gösteriliyor."; soru; "↻ Yeniden analiz et" yalnız kayıtlı cevapta ve `fresh` ile yeni
iş başlatır; "⬇ Excel raporu"). "Bir bakışta": sonuç sözcüğü ve simgesi, "eksik: …", "<N> tablo
önerildi" ya da "eşik üstünde tablo yok", en iyi eşleşme (güven halkası; yüzde ve seviye adı
yazılıdır, renk tek başına bilgi taşımaz), diğer öneriler ve açık başlayan "Hangi tablo neyi
karşılıyor" matrisi (en çok 8 kavram; ● ◐ ○ simgeleri erişilebilir adlarıyla; açıklama; "+N kavram
Ayrıntılar'da"). "Analistin özeti", "Analiz yapılamadı" kutusu, öneri satırları (bir anda tek satır
açık; klavyeyle açılır; kolonlar ilk 6 ve "+N kolon"; "Ayrıntılar"), kapalı başlayan ve sayı
gösteren yan kartlar ("Önerilen kurgu", "Dikkat edilmesi gerekenler", analist cevabında "Notlar ve
öneriler"), öneri yoksa "Sözlükte bu talebin doğrudan karşılığı bulunamadı. Talebi farklı ifadelerle
deneyin." ve "Arama ayrıntıları". Metindeki tablo adları öneriye ya da tablo dosyasına götüren
düğme, kolon adları sabit genişlikli yazıdır; model metni hiçbir zaman HTML (sayfa biçimlendirme
kodu) olarak yorumlanmaz. Excel raporu paylaşılan istemciyle, oturum belirteci başlıkta gönderilerek
indirilir ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
Requirement 12) ve dosya adı yanıt başlığından alınır. Güven halkası gibi dinamik görsel değerler
stil nesnesi (CSSOM) ya da SVG öznitelikleriyle verilir; çalışırken `<style>` öğesi ekleyen bileşen
kullanılmaz (katı içerik güvenlik politikası, user-accounts Requirement 14). Oy düğmeleri,
kullanıcıların reddettiği ve doğruladığı tablolar answer-feedback PRD'sinindir ve bu görünümde yer
alır. Cevap görünümü kaynakla birebir aynı görünür; renkler kaynak CSS'inin değerlerini taşıyan
belirteçlerdendir (Yüksek ve VAR başarı, Orta ve KISMEN VAR uyarı, Düşük ve BULUNAMADI yıkıcı;
[dictionary-explorer](../007-dictionary-explorer/PRD.md) Requirement 17).

Requirement 22: Soru çubuğunun altındaki uyarı satırı (sözlük yok, model bağlı değil, modele
ulaşılamıyor) durum göstergesinin parçasıdır; metinleri, önceliği ve 60 saniyelik yenilenmesi
[dictionary-explorer](../007-dictionary-explorer/PRD.md) Requirement 2'dedir. Bu PRD, akışı
`unavailable` olan her cevaptan sonra durumun yeniden okunmasını tetikler.

Requirement 23: `POST /analyses` oturumdaki kullanıcı başına 60 saniyede en çok 30 istek kabul eder;
aşılırsa `429 rate_limited` ("Çok sık soru gönderildi; bir dakika sonra yeniden deneyin."). Sayaç
kullanıcıya göredir, adrese göre değil.

Requirement 24: Katmanlar: veri sınıfları (`DictColumn`, `ObjectProfile`, `Dictionary`, `TermGroup`,
`Level`, `Verdict`, `ColumnHit`, `ObjectMatch`, `Note`, `AnalysisResult`) ve kayıtlı cevap tablosu
modeli `app/backend/app/domain/` altında; taşınan saf modüller, iş ve kuyruk yönetimi ve kayıtlı cevap
hizmeti `app/backend/app/services/analysis/` altında; kayıtlı cevap ve analiz kaydı yazımı
`app/backend/app/infrastructure/repositories/` altında; uçlar `app/backend/app/api/analyses/`, istek
ve yanıt modelleri `app/backend/app/schemas/analysis/` altındadır. Saf modüller ağ, veritabanı ve
dosya erişimi yapmaz. Motor, sunucunun istek karşılayan ana döngüsünü bekletmemek için ayrı bir iş
parçacığında çalışır; yalnız okuyan arama çağrıları (dictionary-explorer) iş kuyruğunu beklemez.
Analist modeli llm-connection'ın uygulama portundan kaynaktaki `LLMClient` sözleşmesiyle kullanır:
`available`, `model`, `health()`, `chat_json(system, user, schema, *, max_tokens)` (yapılandırılmış
yanıt ya da başarısızlık) ve başarısızlığın hata sınıfı. Her iş portun kendine ait bir görünümünü
kullanır: model anlık görüntüsü, durdurma belirteci, adım kaydı ve hata sebebi o işindir; kaynaktaki
paylaşılan `last_error` yarışı olmaz.

## API sözleşmesi

Uçlar `/api/dwhnavigator/v1` altındadır ve hepsi geçerli oturum belirteci (JWT) ister. Hata gövdesi
tek zarftır: `{"detail":{"code":"...","message":"..."}}`; istek kimliği `x-request-id` başlığıyla
döner. Uygulama arayüzü sözleşme dosyası (`OpenAPI`) ve ondan üretilen ön yüz tipleri aynı değişiklikte
güncellenir; canlı akış olaylarının içerikleri de sözleşmede bileşen şeması olarak yer alır.

**İş zarfı:** `analysis_id`, `state` (`queued`, `running`, `completed`, `failed`, `cancelled`,
`interrupted`), `origin` (`question`, `list`), `query`, `fresh`, `ahead` (yalnız `queued`), `step`
(yalnız `running`; adım anahtarı), `flow` (yalnız `completed`: `analyst`, `reused`, `unavailable`),
`error` (`code`, `message` ya da `null`), `created_at`, `started_at`, `finished_at` (evrensel saat,
ISO 8601 uluslararası tarih yazımıyla).

| Uç | Yetki | Başarı | Hatalar |
|---|---|---|---|
| `POST /analyses` | `kullanici`, `yonetici` | `202` iş zarfı ve `Location`; kayıtlı cevap bulunduysa zarf `completed` | `401`, `403`, `413 request_too_large`, `422 query_empty`, `query_too_long`, `query_invalid_characters`, `invalid_request`, `429 rate_limited`, `503 analysis_queue_full`, `analysis_unavailable`, `search_index_not_ready` |
| `GET /analyses/active` | `kullanici`, `yonetici` | `200` `{"analysis": <iş zarfı ya da null>}`: kullanıcının en son başlattığı, sıradaki ya da yürüyen tek soru işi | `401`, `403` |
| `GET /analyses/{analysis_id}` | işin sahibi | `200` iş zarfı; `completed` ise `result` (Requirement 7) | `401`, `403`, `404 analysis_not_found` |
| `GET /analyses/{analysis_id}/events` | işin sahibi | `200` `text/event-stream` (Requirement 10) | akış açılmadan hata zarfı: `401`, `403`, `404 analysis_not_found`, `429 too_many_streams` |
| `POST /analyses/{analysis_id}/cancel` | işin sahibi | `200` iş zarfı (son durum) | `401`, `403`, `404 analysis_not_found` |
| `GET /analyses/{analysis_id}/report` | işin sahibi | `200` Excel dosyası (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `Content-Disposition: attachment`) | `401`, `403`, `404 analysis_not_found`, `409 analysis_has_no_result` |
| `GET /status` | `kullanici`, `yonetici` | `200` `columns`, `objects`, `dictionary_version`, `llm`, `llm_state` (`state`, `model`, `code`, `reason`), `shortlist` | `401`, `403` |
| `GET /saved-answers/summary` | `yonetici` | `200` `total`, `usable`, `newest_at` | `401`, `403` |
| `DELETE /saved-answers` | `yonetici` | `200` `removed` | `401`, `403` |

Başka kullanıcının işi her uçta `404 analysis_not_found` döner; işin var olduğu da söylenmez.
`analysis_not_found` iletisi "Analiz bulunamadı.", `too_many_streams` iletisi "Çok sayıda açık izleme
bağlantısı var; diğer sekmeleri kapatın." şeklindedir.

**Canlı akış olayları:** Her olay `id:` satırı (iş içinde artan sıra; `snapshot` o ana kadarki son
olayın sırasını taşır; yeniden bağlanmada `Last-Event-ID` olarak geri gelir, Requirement 10) ve tek
`data:` satırında `type` alanlı yapılandırılmış metindir:
- `snapshot`: `analysis_id`, `state`, `ahead`, `step`, `elapsed_ms`; her bağlantının ilk olayı.
- `queued`: `ahead`.
- `started`.
- `step`: `key` (Requirement 10'daki küme), `status` (`started`, `finished`, `error`), `elapsed_ms`.
- `completed`: `flow`, `verdict` (`VAR`, `KISMEN VAR`, `BULUNAMADI`).
- `failed`: `code`, `message`.
- `cancelled`, `interrupted`.

Olay yokken 15 saniyede bir `: canlı` satırı gelir; son olaydan sonra sunucu akışı kapatır.

**Kaynaktaki karşılıklar:** `POST /api/ask` (analiz bitene kadar açık kalan istek) → `POST /analyses`,
canlı akış ve `GET /analyses/{analysis_id}`; `POST /api/ask/cancel` →
`POST /analyses/{analysis_id}/cancel`; `GET /api/report/<id>` → `GET /analyses/{analysis_id}/report`;
`GET /api/status` → `GET /status`; `POST /api/admin/answers/clear` → `DELETE /saved-answers`; ayar
ekranındaki kayıtlı cevap sayıları → `GET /saved-answers/summary`. `ask_id` ve `voter` alanları kalkar.

## Güvenlik ve yetkilendirme

- Kimlik ve roller [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
  PRD'sinden gelir; kaynakta soru ekranı kimliksizdi. Soru, durum ve iş uçları `kullanici` ve
  `yonetici` rollerine; kayıtlı cevap özeti ve silme yalnız `yonetici` rolüne açıktır.
- Bir işi yalnız başlatan kullanıcı okur, izler, durdurur ve raporunu alır; `yonetici` de başkasının
  işine bu uçlardan erişemez (analiz kayıtlarını analysis-records PRD'sinin ekranından görür).
- Canlı akış ilk baytı göndermeden önce oturumu, rolü ve sahipliği denetler. Oturum belirteci yalnız
  `Authorization` başlığındadır; bağlantı adresinde belirteç, soru metni ya da tablo adı yoktur. Bu
  yüzden ön yüz akışı ve rapor indirmeyi paylaşılan istemciyle yapar (Decision 17).
- Girdiler sunucuda doğrulanır (Requirement 4); istek gövdesi, akış sayısı, istek sıklığı ve kuyruk
  sınırlıdır (Requirement 9, 10, 23).
- Hata iletileri istisna metni, model sunucusunun adresi ve hata gövdesi, SQL ya da sunucu yolu
  içermez; ilişkilendirme için `x-request-id` kullanılır.
- Model metni arayüzde düz metin olarak gösterilir, HTML (sayfa biçimlendirme kodu) olarak
  yorumlanmaz; Excel'de formül olmaz. Rapor dosya adı yalnız harf, rakam ve `_` içerir.
- Soru metni ve sözlük içeriği istemle yalnız kurum içindeki modele gider; ağ politikası
  llm-connection PRD'sindedir.
- Kayıtlı cevap kullanıcıya özgü veri taşımaz; oylar cevaba okunurken o kullanıcı için uygulanır. Bu
  yüzden kayıtlı cevap kiracı içinde kullanıcılar arasında paylaşılır; "aynı anlam" eşleşmesinde
  önceki sorunun metni gösterilir (kaynakla aynı, Decision 24).
- Soru metni, tablo ve kolon adı, istem ve model yanıtı log, ölçüm ve izlere girmez; işaret dizesiyle
  sızıntı testi bunu denetler (Test stratejisi).

## Veri ve geçiş

- **Yeni tablo `saved_answer`** (Alembic göçüyle, yani sürümlü veritabanı şema değişikliğiyle; bu
  PRD'nin): `saved_answer_id` (iç kimlik), `public_id`, kiracı kapsamı, `query_text` (en çok 2000
  karakter; kaynakta da öyle), `text_key`, `meaning_key` (boş olabilir), `fingerprint` (16 hane),
  `result` (kaynaktaki `answer_cache.encode` biçiminde cevap: kolonlar yalnız anahtarlarıyla durur ve
  cevap okunurken Requirement 14'e göre güncel sözlükle yeniden kurulur; ortalama ~30 KB),
  `answered_at` (evrensel saat),
  `analysis_public_id` (cevabı üreten analiz kaydı; kayıt silinince boşalır), `props`, `created_at`,
  `updated_at`, `created_by` (cevabı üreten soruyu soran kullanıcı), `updated_by`. Kısıt: kiracı,
  `text_key`, `fingerprint` üçlüsü tekildir. Dizinler: (kiracı, `fingerprint`, `answered_at` azalan) ve
  (kiracı, `meaning_key`, `fingerprint`, `answered_at` azalan). Yazılımsal silme sütunları yoktur;
  rules/41 sapması göç ettirilmiş şema kapısında belgeli istisnadır (Decision 9).
- **Analiz kaydı:** Tablo analysis-records PRD'sinindir; bu PRD Requirement 18'deki alanların ve
  durumların yazılmasını ister. İş kimliği kaydın `public_id` değeridir.
- **Geçiş yok:** Kaynaktaki `data/cache/answers.jsonl` ve `data/logs/analyses.jsonl` taşınmaz; kayıtlı
  cevaplar ve analiz kayıtları boş başlar.
- **Fark testi verisi:** Sentetik sözlük, soru listesi ve kaynağın sentetik çıktıları depoda test verisi
  olarak durur (kurum verisi içermez). Gerçek sözlük, referans soruları ve onlarla üretilen çıktılar
  depoya, test verisine ve loga girmez.
- Kaynaktaki bellekteki rapor deposu (`MAX_REPORTS`) ve `data/out` klasörü kalkar.

## Gözlemlenebilirlik

- **Log olayları** (yapılandırılmış, içeriksiz; `request_id` ile): `analysis.accepted` (`analysis_id`,
  `origin`, `fresh`, `ahead`), `analysis.started` (`analysis_id`, `queue_wait_ms`),
  `analysis.finished` (`analysis_id`, `origin`, `outcome`, `verdict`, öneri sayısı, düşen ad ve cümle
  sayısı, model çağrısı ve belirteç sayıları, `duration_ms`, `error_code`),
  `analysis.interrupted_at_startup` (sayı), `analysis.record_write_failed` (`analysis_id`, aşama, hata
  sınıfı), `analysis.feedback_overlay_failed` (`analysis_id`), `saved_answer.failed` (işlem: `lookup`,
  `write`, `delete`; hata sınıfı), `saved_answer.cleared` (`removed`, kullanıcının `public_id` değeri),
  `analysis.report_generated` (`analysis_id`, `duration_ms`, `size_bytes`).
- **Ölçümler:**
  - `dwhnavigator_analyses_started_total{origin}`
  - `dwhnavigator_analyses_finished_total{origin,outcome}`
  - `dwhnavigator_analysis_duration_seconds{origin,outcome}` (kabulden bitişe, histogram)
  - `dwhnavigator_analysis_queue_wait_seconds{origin}` (histogram)
  - `dwhnavigator_analysis_step_duration_seconds{step}` (histogram)
  - `dwhnavigator_analysis_queue_length` ve `dwhnavigator_analyses_running` (anlık değer)
  - `dwhnavigator_analysis_verdicts_total{verdict}`
  - `dwhnavigator_analysis_validation_dropped_total` (sözlükte olmayan ad ve cümle sayısı; modelin
    uydurma göstergesi)
  - `dwhnavigator_saved_answer_lookups_total{result}` ve `dwhnavigator_saved_answer_writes_total{result}`
  - `dwhnavigator_analysis_streams_open` (açık canlı akış sayısı)
  - `dwhnavigator_analysis_reports_total{result}`

  Etiket kümeleri sabittir: `origin` `question` ya da `list`; `outcome` `analyst`, `reused`,
  `unavailable`, `failed`, `cancelled`, `interrupted`; `verdict` `var`, `kismen_var`, `bulunamadi`;
  `step` Requirement 10'daki yedi anahtar; arama `result` değeri `same_question`, `same_meaning`,
  `miss`, `disabled`, `error`; yazma `result` değeri `stored`, `skipped`, `error`; rapor `result`
  değeri `ok`, `error`. Kümede olmayan değer `other` yazılır. Kullanıcı, iş, soru, tablo ve model adı
  ölçüme girmez.
- **İz:** iş başına `analysis.run` aralığı (öznitelikler: köken, sonuç, sonuç etiketi, öneri sayısı,
  düşen sayı, model çağrısı sayısı) ve altında adım anahtarı adlı aralıklar; model çağrısı aralıkları
  llm-connection'dan gelir ve adım aralığına bağlanır. İçerik hiçbir aralığa girmez. Ortak kurallar ve
  saklama [application-foundation alanındadır](../../../application-foundation/DOMAIN.md). Tüketen
  test: `app/backend/tests/integration/test_telemetry_signals.py`.

## Dağıtım etkisi

- **Yeni ayarlar:** `DWHNAVIGATOR_ANALYSIS_CONCURRENCY` (1; 1–4) ve `DWHNAVIGATOR_ANALYSIS_QUEUE_LIMIT`
  (20; 1–200). Sır değildir; tipli ayarlar, `app/backend/.env.example`, yerel Compose ortam bloğu ve
  `helm/dwhnavigator/values-project.yaml` içindeki `backend.config` birlikte güncellenir;
  `python3 scripts/check-config-sync.py` geçer.
- **Giriş kapısı:** Canlı akış yanıtı tamponlanmamalı (uygulama `X-Accel-Buffering: no` gönderir) ve
  okuma zaman aşımı 15 saniyelik canlılık aralığından uzun olmalıdır; kurulumu
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindedir (Requirement 12). Başlatma ve okuma istekleri kısadır; analiz süresince açık kalan
  istek yoktur.
- **Tek kopya:** İşler ve kuyruk süreç belleğindedir; backend tek kopya (replica) çalışmalıdır ve
  güncellemede eski ve yeni süreç birlikte çalışmaz (`Recreate`, kubernetes-delivery Decision 5). İki
  kopya iki kuyruk, katlanmış eşzamanlılık ve kopyalar arasında bulunamayan işler demektir.
- **Yeniden başlama:** Her dağıtım süren ve sıradaki analizleri "yarıda kesildi" yapar
  (Requirement 12); kapanış bekleme süresi bunları kaydetmeye yetmelidir.
- **Bağımlılık:** Rapor için `openpyxl` (ve `et-xmlfile`) çalışma bağımlılığı olarak kabul kaydına
  girer (dictionary-management ve list-search de kullanır); `pandas` yoktur.
- **Göç:** `saved_answer` tablosu; geri alma tabloyu siler (kayıtlı cevap önbellektir, kayıp yalnız
  yeniden analiz demektir).

## Test stratejisi

- **Taşınan birim testleri:** Kaynaktaki `test_normalize.py` (doğrudan harf çevirisi denetimi hedefin
  analiz paketine uygulanır), `test_search.py`, `test_scoring.py`, `test_aggregate.py`,
  `test_topic.py`, `test_analyst.py`, `test_analyst_compact.py`, `test_answer_cache.py` (anahtar,
  parmak izi ve biçim bölümleri; depo testleri PostgreSQL deposu için yeniden yazılır) ve
  `test_cancel.py` (asılı kalan sahte model sunucusuyla gerçek bağlantının kesildiği test, hedefin
  portuyla) yalnız içe aktarma yolları değişerek geçer. Gerçek sözlük isteyen `test_golden.py`
  quality-evaluation ile taşınır; sözlük yoksa kaynaktaki gibi atlanır.
- **Sabit fark testi:** Taşınan her modülün büyük harfli sabitleri kaynak modüldekilerle ad ve değer
  olarak karşılaştırılır; istem özeti (`prompts_digest`) kaynaktakiyle aynıdır.
- **Fark testi (kaynakla bayt bayt aynılık):**
  - *Düzenek:* İki taraf aynı girdi dosyalarını okur ve aynı döküm kurallarıyla (yalnız standart
    kütüphane kullanan ortak döküm modülü; anahtarlar sıralı, Türkçe harfler kaçışsız, ondalıklar
    `repr`) satır başına bir soru ve ayar çeşidi yazar. Kaynak tarafı kaynak kopyasında, Python 3.12
    sanal ortamında ve kaynağın `requirements.lock` sürümleriyle (openpyxl 3.1.5, defusedxml 0.7.1,
    PyYAML 6.0.3) `vsa` paketini içe aktararak çalışır; kopyanın yolu `DWHNAVIGATOR_PARITY_SOURCE_DIR`
    ile verilir ve düzenek kopyanın ağaç özetinin `76e21a3` ağacıyla
    (`b499981ef340d5c54ba4ead74ee20b2ac6c75f33`) aynı olduğunu doğrular, değilse durur. Kaynak kodu
    hedef depoya kopyalanmaz. Hedef tarafı backend ortamında çalışır. Karşılaştırıcı satırları bayt
    bayt karşılaştırır ve ilk farklı soruyu, çeşidi ve alanı yazar.
  - *Sözlük:* Sentetik sözlük `app/backend/tests/fixtures/parity/sozluk_sentetik.xlsx`, depodaki bir
    üretici betikle belirlenimci üretilir: en az 60 tablo ve 1.500 kolon; Türkçe harfler ve İ/ı,
    birleşik ve alt çizgili adlar, sonunda boşluk olan ad, iki şemada aynı adlı tablo, 90'dan çok
    kolonlu tablo, açıklamasız (profilsiz) tablo, 40'tan çok kolonda geçen eş anlamlı, roller ve
    özetler, KVKK (kişisel veri) işaretli açıklama, "X bazlı değil" açıklaması, dar kitle ifadeleri,
    dönem ve günlük zaman kolonları, müşteri anahtarları, ürün kırılımı kolonu, eski `DAtabaseName`
    başlığı ve tekrarlanan kolon satırı. İki taraf da sözlüğü kendi içe aktarma koduyla okur;
    düzenek önce iki ayrıştırmanın kolonlarını, sıralarını, kimliklerini ve profillerini
    karşılaştırır, sonra iki motora aynı içeriği (aynı sürüm dizgesi ve kaynak adıyla) verir.
  - *Kelime listeleri:* depodaki başlangıç terim sözlüğü ve durak kelimeler (vocabulary-management),
    ayrıca "Kapsam:" notlu ve "finansal" alanlı birer ek grup.
  - *Sorular:* `app/backend/tests/fixtures/parity/sorular.yaml`, en az 150 soru: kaynak altın setinin
    8 sorusu (batch maddesi `b001` taşınmaz, [quality-evaluation](../010-quality-evaluation/PRD.md)) ve
    negatif setinin 5 sorusu ile sentetik sözlüğe yazılmış en az 137 soru (zaman, kırılım ve
    parantez içi değerler, ölçüler, olumsuzluk, sayı, terim grubu eşdeğeri, birebir kolon adı, Türkçe
    harfsiz yazım, büyük harfli İ/ı, yalnız noktalama, 4000 karaktere yakın talep, kavramsız talep,
    tablo adı).
  - *Ayar çeşitleri:* ölçülmüş varsayılanlar; terim genişletme kapalı; konu uyumu ağırlığı 0;
    `analyst.detail_columns` 0 ve `analyst.shortlist` 6; `search.candidate_object_columns` 50 ve
    `scoring.min_candidate_score` 0,3; `top` 3.
  - *Sahte model:* İki tarafta aynı kod. Yanıtları istemin içinden ve talebin SHA-256 özetinden
    türetilen belirlenimci seçimlerle kurar. 1. adımda ipucu listesindeki kimliklerden aday ve benzer
    tablo, bir bilinmeyen kimlik, kimlik yerine yazılmış bir tablo adı, talep kelimelerinden arama
    terimleri ve iki aile. 2. adımda malzemedeki tablo başlıklarından en çok 5 öneri (gerçek, küçük
    harfle yazılmış ve uydurma kolonlar; 0,5'in altında bir güven), uydurma tablo adı geçen cümle,
    katalog kimliği ve "vX (vX)" tekrarı, yazım hatası uyarısı, `core_columns`, `core_found`, sonuç
    etiketi ve eksik bilgi bileşimleri (alanların hiç olmadığı yanıt dahil), karıştırılabilir
    alanlardan gerçek ve uydurma tam ad geçen "Top 5 dışı" notu. Belirli sorularda senaryolu durumlar:
    1. adım yanıtsız, 2. adım yanıtsız, boş aday listesi, bağlam aşımı, zaman aşımı, bağlantı hatası,
    sunucu kontrolü başarısız.
  - *Karşılaştırılan:* Requirement 2'deki dokuz çıktı her soru ve çeşit için. Excel dosya baytlarıyla
    değil, openpyxl ile okunan sayfa, hücre ve biçim dökümüyle karşılaştırılır (paket zaman damgası ve
    kütüphane sürümü farkı nedeniyle).
  - *Karşılaştırma dışı:* yalnız Requirement 2'deki liste. Bilerek değişen sebep metinleri Requirement
    5 tablosuna karşı ayrı test edilir.
  - *Karma tohumu:* hedef tarafı `PYTHONHASHSEED=0` ve `PYTHONHASHSEED=4242` ile iki kez koşar.
  - *Sentetik anlık görüntü:* Kaynak tarafının sentetik çıktıları
    `app/backend/tests/parity/snapshots/source-76e21a3/` altında depoda durur. Olağan kalite kapısı
    hedefi bu anlık görüntüyle karşılaştırır; kaynak kopyası gerekmez ve test atlanmaz. Düzeneğin
    `--verify-snapshot` kipi anlık görüntüyü kaynak kopyasından yeniden üretir ve depodakiyle bayt bayt
    aynı olduğunu doğrular.
  - *Gerçek sözlük:* `DWHNAVIGATOR_PARITY_DICTIONARY` (depo dışındaki `VeriSozlugu.xlsx`) ve varsa
    `DWHNAVIGATOR_PARITY_QUESTIONS` (depo dışındaki referans soruları; kaynak kararı ADR-046'daki 129
    soruluk karşılaştırmanın soruları) verilince düzenek iki tarafı yan yana çalıştırır. Önce iki
    tarafın ayrıştırdığı sözlük karşılaştırılır, sonra dokuz çıktı. Çıktılar depo dışındaki geçici
    klasöre yazılır ve koşum sonunda silinir; kanıta yalnız soru, çeşit ve fark sayıları ile
    çıktıların SHA-256 özeti girer.
  - *Sahiplik:* Düzenek, girdileri, karşılaştırılan çıktılar ve eşik (0 fark) bu PRD'nindir. Kaynakla
    yan yana çalışan öteki karşılaştırmalar (ör. quality-evaluation Requirement 16'daki ölçüm çıktısı)
    bu düzeneği kullanır ve buraya bağlantı verir.
- **Hizmet testleri** (sahte motor ve sahte modelle, gerçek PostgreSQL): kuyruk sırası, eşzamanlılık
  üst sınırı (sahte modelin gördüğü en yüksek eşzamanlı istek ayarı aşmaz), kuyruk sınırı, aynı
  kullanıcının ikinci tek soru isteğinin sıraya girmesi, liste terimlerinin araya girmesi (tek soru
  en çok bir terim bekler), motorun ve modelin iş başına sabitlenmesi (iş sürerken ayar ve model
  değişir), aynı soru için tek analiz, `fresh`, yalnız analist cevabının ve geçerli motorun
  cevabının yazılması, depo hatasında analizin sürmesi, 2000 kayıt sınırı, aynı metinde yenisinin
  eskisinin yerini alması, unutma ve temizleme, `max_age_days` ve `meaning` anahtarları, kolonu
  silinmiş kayıtlı cevabın kullanılmaması, durum geçişleri, yeniden başlamada `interrupted` ve
  analiz kaydı alanları.
- **API testleri** (gerçek uygulama ve PostgreSQL): `401`, `403`, `404` (başka kullanıcının işi),
  Requirement 4'teki `422` ve `413` durumları; başarılı akışın olay sırası (`snapshot`, `queued`,
  `started`, adımlar, `completed`); canlılık satırı (testte kısaltılmış aralıkla); kopan bağlantıda
  işin sürmesi ve `Last-Event-ID` ile yeniden bağlanınca `snapshot` ve kaçırılan adım olayları; açık
  akış sınırı; sıradaki ve yürüyen işin durdurulması (asılı kalan sahte model sunucusu bağlantının 2
  saniye içinde kapandığını görür; iş 5 saniye içinde `cancelled`); tekrarlanan durdurma;
  `GET /analyses/active`; rapor (sayfa adları, hücreler, "=1+1" talebin metin kalması, `409`
  bitmemiş işte); sonuç zarfı ve oy uygulaması hata verince oysuz cevap; durum ucunda adres
  olmaması; hız sınırı; başlatma yanıtının ve kayıtlı cevabın 2 saniye sınırı.
- **Sızıntı testi:** Soruya, sözlüğe (tablo ve kolon adı) ve sahte model yanıtına konan ayırt edici
  işaret dizeleri log çıktısında, ölçüm etiketlerinde ve iz özniteliklerinde aranır, bulunmamalıdır;
  analiz kaydında ve kayıtlı cevapta bulunur (ürün verisi).
- **Ön yüz testleri** (Vitest test aracıyla): soru çubuğu (Enter, Shift+Enter, boş talep, Esc ile
  durdurma, "/" ile odak, tam tablo adı), başlatma yanıtından önce durdurma, sıradaki işte bilgi
  satırında "sırada" yazması ve adım metni ya da sayı gösterilmemesi, durdurma, hata ve yarıda
  kesilme iletileri, yeniden bağlanma, sayfa açılışında süren analize bağlanma, cevap görünümünün
  sabit cevaplardan çizilmesi ("Bir bakışta", matris simgeleri ve erişilebilir adları, yan kartlar,
  "Analiz yapılamadı" kutusu, kayıtlı cevap rozeti ve "Yeniden analiz et"in `fresh` göndermesi),
  raporun paylaşılan istemciyle indirilmesi (adreste belirteç yok), akışı `unavailable` olan
  cevaptan sonra durumun yeniden okunması; yerelleştirme anahtar denetimi.
- **Tarayıcı testi** (yerel Compose): Acceptance 7'deki akışlar.
- **Görsel eşdeğerlik:** kaynak `76e21a3` ve hedef aynı sözlükle ve aynı sahte ya da gerçek model
  cevabıyla yan yana çalıştırılır; soru çubuğu ve cevap görünümünün ekran görüntüleri aynı ekran
  boyutlarında karşılaştırılır (Acceptance 10).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

Kaynak vektör aramasını kaynak kararı ADR-039 ile kaldırdı; bu PRD gömme (metni sayı dizisine
çevirme) kullanmaz.

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: kaynaktan taşınan birim testleri yalnız içe
  aktarma yolları değişerek, sabit fark testi ve doğrudan harf çevirisi denetimi geçer
  (Requirement 1, 6).
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: hedefin sentetik sözlükteki çıktıları kaynak
  anlık görüntüsüyle bütün sorularda, ayar çeşitlerinde ve iki karma tohumunda 0 fark verir; sebep
  metinleri Requirement 5 tablosuna uyar (Requirement 2, 3, 5, 13, 16).
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: kaynak kopyası (ağaç özeti
  `b499981ef340d5c54ba4ead74ee20b2ac6c75f33`) olan geliştirici makinesinde fark düzeneği sentetik
  anlık görüntüyü bayt bayt aynı yeniden üretir ve hedefle 0 fark verir; koşum raporu soru, çeşit ve
  karşılaştırılan çıktı sayısını yazar (Requirement 2).
- [ ] Acceptance 4: L1 — Otomatik testlerden geçti: iş modeli, kuyruk, durdurma, yeniden başlama,
  kayıtlı cevap hizmeti ve analiz kaydı hizmet testleri gerçek PostgreSQL ile geçer (Requirement 3,
  8, 9, 11–15, 18).
- [ ] Acceptance 5: L1 — Otomatik testlerden geçti: API testleri ve sızıntı testi geçer; işaret
  dizeleri log, ölçüm etiketi ve iz özniteliklerinde bulunmaz (Requirement 4, 7, 10, 16, 17, 23).
- [ ] Acceptance 6: L1 — Otomatik testlerden geçti: ön yüz testleri, `OpenAPI` ve üretilmiş tip
  sapması kapısı, yerelleştirme anahtar denetimi ve katman yapısı denetimi geçer (Requirement 19–22,
  24).
- [ ] Acceptance 7: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da (yerel PostgreSQL,
  onaylı gerçek model ucu) tarayıcıda bir soru sorulur, ilerleme Evren'in tarama hareketiyle
  görünür, cevap "Bir bakışta" ile görünür, Excel raporu indirilip açılır; aynı soru yeniden
  sorulunca "Önceki cevap" 2 saniye içinde görünür ve "Yeniden analiz et" yeni analiz yapar;
  "Durdur" analizi 5 saniye içinde bitirir; iki kullanıcıyla ikincisinin sorusu sıraya girer ve
  bilgi satırında "sırada" görünür, sayı görünmez; sekme kapatılıp açılınca süren analize yeniden
  bağlanılır ve cevap gelir; log çıktısında soru metni ve tablo adı yoktur (Requirement 8–11, 14,
  16, 19–21).
- [ ] Acceptance 8: L2 — Gerçek istemci/ortamda doğrulandı: geliştirici makinesinde gerçek sözlük
  Excel'i ve varsa depo dışındaki referans sorularıyla fark düzeneği iki tarafı yan yana çalıştırır ve
  0 fark verir; kanıta yalnız sayılar ve çıktıların SHA-256 özeti yazılır, sözlük içeriği ve çıktılar
  depoya girmez (Requirement 2).
- [ ] Acceptance 9: L2 — Gerçek istemci/ortamda doğrulandı (nonprod): KT Rancher nonprod kümesinde
  kurum içi model ucuyla bir soru tarayıcıdan tamamlanır; ilerleme giriş kapısından tamponlanmadan
  gelir, 2 dakikayı aşan analizde akış kopmaz ya da kopunca yeniden bağlanır, "Durdur" çalışır, 1. adım
  bağlam aşımı vermez (Requirement 5, 10, 11). Küme dağıtımı bu kanıtın parçası değildir ve ayrı
  kullanıcı talimatı ister.
- [ ] Acceptance 10: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı sözlükle çalıştırılır; açılış görünümündeki soru çubuğu, üst
  çubuğa yerleşmiş soru çubuğu, süren analiz (Durdur düğmesi) ve cevap görünümünün (analist cevabı,
  kayıtlı cevap, "Analiz yapılamadı", öneri satırı ve yan kartlar açık) ekran görüntüleri masaüstü
  (1440×900) ve telefon genişliğinde (390×844 piksel) yan yana karşılaştırılır. Fark yalnız
  fabrikanın zorunlu kıldığı oturum alanında ve kaynakta olmayan durumların iletilerinde ("sırada",
  "yarıda kesildi") kabul edilir (Requirement 19–21).

## Kararlar

- Decision 5: Başlatma isteği hemen döner; ilerleme ayrı canlı akıştadır. Gerekçe: bir analiz 45
  saniye ile birkaç dakika sürer; giriş kapısı ve vekil sunucular uzun açık isteği keser. Ayrı akış
  koparsa iş sürer ve istemci yeniden bağlanır.
- Decision 6: Akış koparsa akış ucu kendi çalışmasını bırakır, analiz işi sürer. Gerekçe:
  rules/20'nin "bağlantı koptuktan sonra işi durdur" kuralı akış ucunun işine (olay göndermeye)
  uygulanır; analiz ayrı bir iştir ve kaynakta da tarayıcı ayrılınca sürüp cevabı kayıtlı cevaba
  yazıyordu. Kullanıcı sekmeyi kapatsa da analiz sürer ve cevap analiz kaydına ve kayıtlı cevaba
  yazılır. Analizi bitirmek isteyen kullanıcı "Durdur"u kullanır.
- Decision 7: Tek sorular ve liste terimleri aynı ilk gelen ilk çıkar kuyruğundadır; liste terimlerini
  birer birer koyar. Gerekçe: kaynakta kilit sırası garanti değildi; bu düzenle tek soru en çok bir
  liste teriminin bitmesini bekler.
- Decision 8: Kayıtlı cevap, iş yürümeye başlarken yeniden aranır. Gerekçe: rules/23 aynı anahtar için
  tek hesaplama ister; kaynakta aynı soru iki kez beklerken iki kez analiz ediliyordu. Cevap değişmez,
  yalnız boşa giden model çağrısı kalkar.
- Decision 9: Kayıtlı cevap bir önbellektir, kayıt sistemi değildir: silinince ya da kullanılamayınca
  soru yeniden analiz edilir. Bu yüzden satırlar kalıcı silinir ve tabloda rules/41'in yazılımsal silme
  sütunları yoktur; sapma göç ettirilmiş şema kapısında belgelenir. Cevabın kalıcı kaydı analiz
  kaydıdır.
- Decision 10: Tam cevap analiz kaydına yazılır; rapor istek anında ondan üretilir. Gerekçe: Excel
  raporları saklanmaz; kaynaktaki bellekte 50 cevap sınırı ve yeniden başlamada raporun kaybolması
  kalkar.
- Decision 11: `dictionary_source` kaynaktaki gibi `dictionary.jsonl`'dır
  ([dictionary-management](../001-dictionary-management/PRD.md) Requirement 17). Gerekçe: cevap ve
  rapor kaynakla bayt bayt aynı kalır; fark testi iki tarafa aynı adı verir.
- Decision 12: "Analiz yapılamadı" sebebi model sunucusunun adresini ve ham hata metnini içermez.
  Gerekçe: güvenli kodlama tabanı (rules/57) kullanıcıya iç adres ve sunucu ayrıntısı göstermeyi
  yasaklar; ayrıntı yöneticinin Yapay zekâ sayfasındaki bağlantı testindedir (llm-connection).
- Decision 13: Zamanlar evrensel saatle (UTC) saklanır, kullanıcıya İstanbul saatiyle (`Europe/Istanbul`)
  gösterilir: `generated_at`, raporun "Üretim" satırı, dosya adındaki zaman ve kayıtlı cevabın tarihi.
  Gerekçe: kaynak yerel Windows saatini kullanıyordu; konteyner saati evrensel saattir.
- Decision 14: Kural cevabı (`Engine.rule_answer`) taşınır ama hiçbir uçtan ve ekrandan erişilmez.
  Gerekçe: kaynak kararı ADR-038; ölçüm ve fark testi onu kullanır.
- Decision 15: Motor ayrı bir iş parçacığında çalışır; her iş kendi model görünümünü, durdurma
  belirtecini ve hata sebebini taşır. Gerekçe: motor uzun süren senkron (sırayla bekleyen) koddur ve
  sunucunun ana döngüsünü bekletmemelidir; kaynakta hata sebebi tek istemci nesnesinde paylaşılıyordu.
- Decision 16: `GET /status` bu PRD'nindir; dictionary-explorer üst çubukta tüketir ve
  `dictionary_version` ile haritayı yeniler. Gerekçe: durum
  soru akışının hazır olup olmadığını (sözlük, sohbet modeli) söyler; çubuğun altındaki model uyarısı da
  onu kullanır.
- Decision 17: Canlı akış ve rapor indirme paylaşılan istemciyle, oturum belirteci başlıkta gönderilerek
  yapılır; tarayıcının hazır olay okuyucusu (`EventSource`) ve adreste belirteç kullanılmaz. Gerekçe:
  rules/20 ve rules/58 belirteci adreste taşımayı yasaklar; hazır okuyucu başlık gönderemez.
- Decision 18: Sentetik sözlükte kaynağın çıktıları depoya anlık görüntü olarak alınır; gerçek sözlük
  ve çıktıları depoya girmez. Gerekçe: olağan kalite kapısı kaynak kopyası olmadan da aynılığı korur;
  sözlük kurum içi veridir (alan değişmezi).
- Decision 19: Taşınan modüllerde soru, sözlükte olmayan ad ya da model kimliği yazan log satırları
  kaldırılır; gerekirse yalnız sayı taşıyan olay kalır. Gerekçe: içerik loga girmez; cevap ve kayıt
  aynı kalır.
- Decision 20: Aralık dışı `top` reddedilir. Gerekçe: kaynak sessizce kırpıyordu; tipli doğrulama
  (rules/21) kararlı hata ister. Arayüz ve list-search her zaman 5 gönderir.
- Decision 21: Yeniden başlatmada yarıda kalan iş "yarıda kesildi" olur ve kendiliğinden yeniden
  başlatılmaz; kullanıcı soruyu yeniden sorar. Gerekçe: yeniden başlatma, kimsenin beklemediği
  analizler için model kapasitesi harcar.
- Decision 22: İlerleme kaynaktaki gibi yalnız Evren'in tarama hareketiyle gösterilir; adım metni ve
  önündeki analiz sayısı gösterilmez. Kaynakta olmayan sıra durumu, Evren'in bilgi satırına yazılan
  "sırada" sözüyle bildirilir. Gerekçe: görünür yeni öğe eklenmez; seri kuyrukta bekleme dakikalarca
  sürebildiği için kullanıcı analizinin sırada olduğunu bilmelidir.
- Decision 23: Kullanıcı başına iş sınırı yoktur; aynı kullanıcının yeni tek soru isteği de sıraya
  girer (kaynakla aynı). Sayfa aynı anda tek soru yürütür; birden çok sekmeden gelen istekleri
  kuyruk sınırı ve hız sınırı (Requirement 9, 23) sınırlar.
- Decision 24: Kayıtlı cevap kiracı içinde kullanıcılar arasında paylaşılır ve "aynı anlam"
  eşleşmesinde önceki sorunun metni gösterilir (kaynakla aynı). Gerekçe: cevap kullanıcıya özgü veri
  taşımaz; oylar cevaba okunurken o kullanıcı için uygulanır.
- Decision 25: Yönetici başkasının süren ya da sıradaki analizini durduramaz; durdurma yalnız işin
  sahibine açıktır (kaynakla aynı).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Fark testinin kapsamı:** Fark testi sahte modelle yapılır. Bayt bayt aynılık kodun aynılığıdır;
  gerçek modelin cevabı sunucuya, modele ve sürüme göre değişir. Cevap kalitesinin korunduğu altın
  setle ölçülür (quality-evaluation).
- **Nonprod modeli ölçülmedi:** Kaynak ölçümleri DGX Spark üzerindeki `gemma-4-31b` ile yapıldı;
  nonprod RunAI ucu başka bir model. Kalite, süre ve bağlam penceresi farklı olabilir (aşağıdaki
  bekleyen bilgi).
- **Seri kuyruk:** Eşzamanlılık 1 iken yoğun saatte bekleme uzar; askıda kalan bir model çağrısı,
  llm-connection'daki zaman aşımı (kaynakta 900 saniye) dolana kadar bütün kuyruğu bekletir; durdurma
  yalnız işin sahibine açıktır (Decision 25).
- **Kullanıcı başına sınır yok:** Bir kullanıcı birden çok sekmeden soru göndererek kuyruğu
  uzatabilir; kuyruk sınırı (20) ve hız sınırı (60 saniyede 30 istek) etkiyi sınırlar (Decision 23).
- **Dağıtım analizleri keser:** Her dağıtım backend'i yeniden başlatır; süren ve sıradaki analizler
  "yarıda kesildi" olur ve emek kaybolur.
- **Tek kopya şartı:** Backend birden çok kopya çalışırsa kuyruklar ayrılır, eşzamanlılık katlanır ve
  bir kopyadaki iş diğerinden bulunamaz.
- **Paylaşılan yanlış cevap:** Yanlış bir kayıtlı cevap, aynı ya da aynı anlamdaki soruyu soran
  herkese en çok 30 gün, cevaba 👎 çoğunluğu ya da temizleme olana kadar verilir. Anlam anahtarı
  farklı soruları aynı kavram kümesi saydığında da böyledir (kaynak davranışı).
- **Talep içinden yönlendirme:** Kullanıcı talebe modele talimat yazabilir; model çıktısı sözlüğe karşı
  denetlenir ama serbest metin (özet, gerekçe) kayıtlı cevapla başkalarına gidebilir. Metin her yerde
  düz metin olarak gösterilir.
- **Önceki sorunun görünmesi:** "Aynı anlam" eşleşmesinde başka bir kullanıcının soru metni görünür;
  soruya kişisel veri yazılmışsa başkası görür (Decision 24).
- **Kayıt boyutu:** Tam cevap (ortalama ~30 KB) her analiz kaydında ve kayıtlı cevapta durur; analiz
  kayıtları süresiz saklandığı için veritabanı yönetici silmedikçe büyür
  ([analysis-records](../008-analysis-records/PRD.md)).
- **Sürüm biçimi bağımlılığı:** Raporun "Kaynak sözlük" satırı satır sayısını sözlük sürümünün
  `-` işaretinden sonraki kısmından okur; dictionary-management sürüm biçimini değiştirirse satır
  sayısı yerine sürüm dizgesi görünür.
- **Python sürümü:** Hedefin Python sürümü kaynaktan (3.12) farklıysa Unicode tabloları harf
  çevirisini nadir karakterlerde değiştirebilir; fark testi hedefin kendi sürümüyle koşar ve bunu
  yakalar.
- **Süreç belleğindeki olaylar:** Kaçırılan adım olayları yalnız iş sürerken yeniden gönderilir; süreç
  yeniden başlarsa iş "yarıda kesildi" olur ve adımlar yalnız analiz kaydında kalır.
- **Bekleyen bilgi:** Test kümesindeki (nonprod) RunAI ucundaki `qwen36-35b-a3b-fp8` modelinin
  bağlam penceresinin (modelin tek istekte okuyabildiği metin miktarı) 1. adımın yaklaşık 70 bin
  belirteçlik tablo kataloğunu alıp almadığı bilinmiyor. Bilgi RunAI'yi işleten ekipten beklenir;
  gelmezse nonprod kabulünün (Acceptance 9) ilk sorusuyla ölçülür. Yetmezse her analiz "Modelin
  bağlam penceresi … küçük" sebebiyle biter ve nonprod kabulü engellenir; o durumda
  [llm-connection](../003-llm-connection/PRD.md)'da daha geniş bağlamlı bir model seçilir.
