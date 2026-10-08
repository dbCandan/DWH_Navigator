# data-dictionary alanı

## Amaç ve sonuçlar

İş birimleri doğal dildeki veri taleplerini ("kart limit doluluk oranı nerede?") veri ambarının veri
sözlüğüne (yaklaşık 11 bin kolon, 390 tablo) karşı sorar. Cevap **tablo seviyesindedir**: hangi
tablonun talebi karşıladığı, güven derecesi, gerekçesi, hangi kolonların kullanılacağı ve iş
birimine gönderilebilir bir Excel raporu. Cevabı kurum içi sunucudaki sohbet modeli (LLM, büyük dil
modeli) yazar; kurallı arama motoru modele ipucu verir ve modelin yazdığını sözlüğe karşı denetler.

Bu alan, `kt-vibecoding/kt-dwhnavigator` deposundaki DWH Navigator (Veri Sözlüğü Asistanı, `vsa`)
uygulamasının `76e21a3` sürümündeki davranışını fabrika yapısına taşır. Kaynak davranış esastır;
hedefteki her farklılık ilgili PRD'de (ürün gereksinim belgesi) açıkça yazılır. Kaynak uygulamanın
ölçülmüş cevap kalitesi (2026-10-07: 294 soruda yaklaşık %89,8, 50 soruluk kör sette %90,0) taşıma
sırasında korunur.

## Aktörler

- **Kullanıcı:** İş birimi çalışanı veya veri analisti. Soru sorar, Excel listesiyle toplu arama
  yapar, sözlükte tablo ve kolon gezer, cevaplara ve tablolara 👍/👎 verir, Excel raporu indirir.
- **Yönetici:** Kullanıcının yapabildiklerine ek olarak yönetim ekranını kullanır: sözlüğü içe ve
  dışa aktarır, terim sözlüğünü ve durak kelimeleri düzenler, model bağlantılarını yönetir, arama ve
  cevap ayarlarını değiştirir, analiz kayıtlarını görür ve siler, kayıtlı cevapları temizler.
- **Uygulama yöneticisi (süper yönetici):** Rol atar. Kimliği ve yetkisi `application-foundation`
  alanındadır.
- **Geliştirici:** Kalite ölçümünü (altın set) çalıştırır; ağırlık, istem (prompt) veya model
  değişikliğinden önce ve sonra ölçer.
- **İşletim ekibi:** Ortam ayarlarını, sırları ve dağıtımı yönetir; uygulama içinde bir rol değildir.

## Ortak dil

- **Sözlük (veri sözlüğü):** Veri ambarındaki tabloların ve kolonlarının açıklamaları. Uygulamanın
  tek sözlüğü PostgreSQL'dedir. Excel yalnız aktarım içindir: şablondaki Excel içe aktarılınca
  sözlüğün yerini alır, sözlük aynı şablona dışa aktarılır. Hiçbir Excel sözlük olarak okunmaz.
- **Sözlük şablonu:** İki sayfalı Excel. **Objeler** (ObjectKey, ad, ObjectDescription, Grain,
  KeyColumns, TimeColumns, BusinessDomain, DatasetGroup) ve **Kolonlar** (DatabaseName, SchemaName,
  ObjectName, ColumnName, ColumnDescription, Synonyms, Role, Summary).
- **Tablo (obje):** Sözlükteki tablo veya görünüm; anahtarı her zaman `DB.Şema.Obje`'dir (aynı ad iki
  şemada olabilir).
- **Kolon:** Tablonun alanı: ad, açıklama, eş anlamlılar, rol (Anahtar, Kod, Ad, Zaman, Ölçü, Bayrak,
  Metin), en çok 70 karakterlik özet ve açıklamadan türetilen KVKK işareti.
- **Sözlük sürümü:** İçe aktarılan içeriğin özetinden belirlenen sürüm. Aynı içerik yeniden aktarılırsa
  sürüm değişmez; böylece kayıtlı cevaplar ve arama indeksi boşuna geçersiz olmaz.
- **Terim sözlüğü:** Kurumsal eş anlamlı grupları (terim, eşdeğerleri, alan, not). Kelime aramasını
  genişletir.
- **Durak kelimeler:** Aramada yok sayılan, gruplanmış kelimeler.
- **Arama indeksi:** Sözlük, terim sözlüğü ve durak kelimelerden kurulan BM25 kelime indeksi (kelime
  sıklığına dayalı arama yöntemi).
- **Talep (soru):** Kullanıcının doğal dildeki veri talebi; en çok 4.000 karakter.
- **Kural motoru:** Türkçe normalleştirme, terim genişletme, BM25 araması, kolon kuralları ve tablo
  seviyesine toplama. Kullanıcıya cevap yazmaz; yalnız modele ipucu verir ve modelin cevabını denetler.
- **Analist (analist akışı):** Sohbet modeliyle iki adım: 1) bütün tablo kataloğundan aday tablo
  seçimi, 2) adayların kolonlarını okuyup raporu yazma. Cevabı yalnız analist yazar.
- **Analiz:** Bir talebin cevabı: **sonuç** (VAR, KISMEN VAR veya BULUNAMADI), tablo önerileri (güven
  Yüksek/Orta/Düşük, gerekçe, kapsadığı bilgi, kolonlar), önerilen kurgu, dikkat notları, eksik bilgi
  ve cevabı kimin yazdığı. Model yoksa veya çalışamazsa analiz "Analiz yapılamadı" ve sebebidir.
- **Asıl kavram:** Talebin asıl istediği bilgi; model onu taşıyan 1-3 kolonu adıyla gösterir, kod bu
  kolonları aday tablolarda doğrular.
- **Kayıtlı cevap:** Aynı soru veya aynı anlamdaki soru için yeniden verilen önceki analiz. Sözlük,
  terim listeleri, model veya ayar değişince geçersiz olur.
- **Toplu arama (liste):** Tek sütunlu Excel listesindeki her terimin aynı soru akışından geçirilmesi;
  arka planda yürür, durdurulup sürdürülebilir, tek birleşik rapor üretir.
- **Geri bildirim (oy):** Bir tablo önerisine veya cevabın bütününe 👍/👎 ve isteğe bağlı gerekçe.
  Kişi başına son oy sayılır; sonraki cevapların sırasını, güvenini ve görünürlüğünü etkiler.
- **Analiz kaydı:** Her analizin kim tarafından, ne zaman, hangi akışla yapıldığı, adımları ve süreleri.
- **Model bağlantısı (entegrasyon):** OpenAI uyumlu bir model sunucusunun adresi, isteğe bağlı API
  anahtarı ve sohbet modeli. Aynı anda tek aktif sohbet modeli vardır.
- **Arama ve cevap ayarları:** Kural motoru ve analistin ölçülmüş varsayılanlarla gelen ayarları;
  yönetim ekranından değiştirilir.
- **Altın set:** Kalite ölçümünün soruları ve beklenen cevapları; maddeler silinmez, yalnız eklenir.

## Değişmezler

- **Tablo seviyesinde cevap:** Arama kolon seviyesinde yapılır, cevap tablo seviyesinde verilir.
- **Var olmayan alan önerilmez:** Her önerilen tablo ve kolon sözlüğe karşı doğrulanır. Model tabloyu
  yalnız aday kimliğiyle seçer; modelin yazdığı her metin taranır ve sözlükte olmayan tablo veya
  kolon adı geçen cümle silinir.
- **"Bulunamadı" geçerli cevaptır:** Eşiğin altındaki aday gösterilmez, liste doldurulmaz.
- **Cevabı yalnız analist yazar:** Model yoksa, ulaşılamıyorsa veya çalışamıyorsa sonuç "Analiz
  yapılamadı" ve sebeptir; kural motorunun sıralaması kullanıcıya gösterilmez.
- **Kapsam koda gömülmez:** Hangi tabloların kapsamda olduğu sözlükle yönetilir.
- **Türkçe harf kuralı:** Metin karşılaştırması yalnız uygulamanın Türkçe normalleştirme
  yardımcısıyla yapılır (İ/ı sorunu); doğrudan büyük/küçük harf çevirisi kullanılmaz.
- **Ölçülmüş davranış korunur:** Aynı sözlük, ayar ve model için kural sıralaması ve modele giden
  istemler kaynak uygulamayla bayt bayt aynıdır. Ağırlık, istem veya model değişikliği altın setle
  önce ve sonra ölçülmeden yapılmaz; gerileme varsa geri alınır. Altın set maddeleri silinmez.
- **Sözlük kurum içi veridir:** Sözlüğün kendisi (Excel ve içe aktarılmış hali), büyük referans
  ölçüm seti, kullanıcı soruları ve cevaplar Git'e, test verisine ve uygulama loglarına girmez;
  yalnız PostgreSQL'de ve kullanıcının indirdiği raporda bulunur. Depoda yalnız terim sözlüğü ve
  durak kelimelerin başlangıç listeleri, küçük altın set ve ölçüm geçmişi (yalnız metrikler) durur
  (kaynakta da böyledir).
- **Excel güvenliği:** Rapora yazılan her metin hücreye metin olarak yazılır ("=" ile başlayan metin
  formül olmaz); yüklenen Excel güvenli XML ayrıştırıcısıyla ve boyut, satır, sütun sınırıyla okunur.
- **Model yalnız kurum içindedir:** Modele giden istek yalnız kurum içi (özel ağ) adrese gider; dış
  ağa, buluta ve başka bir adrese çıkış yoktur.
- **Zaman:** Zamanlar UTC olarak saklanır; ekranda ve Excel raporlarında İstanbul saatiyle
  (`Europe/Istanbul`) gösterilir.
- **Sırlar sunucuda kalır:** Model API anahtarı yalnız sunucu sınırındadır; arayüze, Git'e ve loga
  girmez, PostgreSQL'e şifrelenmiş yazılır.

## Sahip olunan veri

PostgreSQL'de: sözlük ve sürüm bilgisi, terim sözlüğü, durak kelimeler, arama ve cevap ayarlarının
değiştirilmiş değerleri, model bağlantıları (API anahtarı şifreli), analiz kayıtları (soru metni,
cevap, adımlar ve süreleri, soran kullanıcı), kayıtlı cevaplar, geri bildirim oyları, toplu arama
işleri ve terim sonuçları. Arama indeksi bu veriden kurulur. Excel raporları istek anında üretilir,
saklanmaz.

## Harici sınırlar

- **Kurum içi model sunucusu:** OpenAI uyumlu sohbet API'si (`/v1/chat/completions`) ve model listesi
  (`/v1/models`).
- Kimlik ve dağıtım `application-foundation` alanındadır.

## İş yetkinliği yol haritası

[Yol haritası](roadmap.md).
