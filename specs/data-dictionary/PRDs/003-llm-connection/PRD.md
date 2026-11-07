# PRD — llm-connection

Status: Accepted

Version: 1.2.0

Acceptance date: 2026-11-04

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi ilk kez 2026-10-08'de, kaynak uygulamanın davranışının olduğu
gibi korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti. 2026-11-04'te uzunluk
sınırında kesilen model yanıtının ayrı hata sınıfıyla gösterilmesini ve bu durumda onarım
istenmemesini istedi (Requirement 8 ve 13, Decision 20) ve bu sürümü aynı gün kabul etti; aynı gün
farklı soranların analizlerinin paralel yürümesi için süreç geneli sohbet çağrısı sınırının
varsayılanının 5'e çıkmasını istedi (Requirement 1 ve 17, Decision 11) ve bu sürümü aynı gün kabul etti.

## Amaç

Yönetici, kurum içi model sunucularına bağlantıları (entegrasyonları) yönetim ekranının **Yapay
zekâ** sayfasından ekler, düzenler, siler, kaydetmeden dener (test eder), sunuculardaki modelleri
listeler ve cevabı yazacak tek aktif sohbet modelini seçer. Bağlantılar her ortamda PostgreSQL'de
durur; model sunucusunun istediği API anahtarı (sunucuya erişim için gizli anahtar) AES-256-GCM
(doğrulamalı şifreleme) ile şifrelenmiş saklanır ve tarayıcıya hiç dönmez.

Analist, bağlantı testi ve ölçüm betiği modele yalnız bu PRD'nin model portundan (iş katmanının
modele ulaştığı tek arayüz) gider. Port, modele giden isteği kaynak uygulamayla bayt bayt aynı kurar
(`temperature` 0, `seed` 42, `reasoning_effort` `"none"`, adım başına `max_tokens`, şemalı JSON
(yapılandırılmış metin) yanıt isteği, 900 saniye okuma süresi), yalnız kurum içi (özel ağ) adrese
gider, ölü sunucuyu beklemez ve süreç genelinde aynı anda süren sohbet çağrısı sayısını sınırlar
(varsayılan 5). Her model çağrısının içerik taşımayan özeti yalnız analiz kaydında saklanır.

## Aktörler ve sonuçlar

- `yonetici`: Yapay zekâ sayfasında entegrasyon ekler, "Bağlan ve modelleri getir" ile sohbet
  modelini seçer, "Test et" ile iki adımın (sunucu, sohbet modeli) sonucunu görür ve entegrasyonu
  aktif eder. Ölçülebilir sonuç: aktif ettikten sonra başlayan ilk analiz, uygulama yeniden
  başlatılmadan yeni modelle yapılır; kayıtlı API anahtarı hiçbir API yanıtında, logda ve ekranda
  görünmez.
- `kullanici`: Soru sorar ve toplu arama yapar; modelin durumunu ana ekranın durum göstergesinde
  görür ([dictionary-explorer](../007-dictionary-explorer/PRD.md)). Ölçülebilir sonuç: model
  sunucusu kapalıysa sağlık denetimi kapalı portta 1 saniyenin, yanıt vermeyen adreste 6 saniyenin
  altında sonuçlanır ve soru modele istek gitmeden "Analiz yapılamadı" ve bu PRD'deki sabit nedenle
  biter.
- **Uygulama yöneticisi (süper yönetici):** Rol atar; `yonetici`nin bu PRD'deki her yetkisini merkezi
  geçişle taşır.
- **İşletim ekibi** (uygulama rolü değildir): Runtime Secret'taki şifreleme anahtarını korur
  (`nonprod`'da dağıtım kancası bir kez üretir), backend'in ağ çıkışını yalnız seçilen model
  sunucusuna açar. Ölçülebilir sonuç: başarısız model çağrılarını `dwhnavigator_llm_calls_total`
  ölçümünden sonuç sınıfına göre görür; hiçbir log ve ölçümde soru, istem (modele giden talimat
  metni), model yanıtı veya adres bulunmaz.
- **Geliştirici:** Model değişikliğinden önce ve sonra altın setle ölçer
  ([quality-evaluation](../010-quality-evaluation/PRD.md)); ölçüm betiği modele bu portla gider.
- Diğer PRD'ler: [question-analysis](../004-question-analysis/PRD.md) istemleri ve JSON şemalarını
  kurar, modelin cevabını yorumlar, analizleri sırayla iş olarak yürütür, her analizde bu PRD'nin
  sağlık denetimini çağırır ve "Analiz yapılamadı" cevabını gösterir;
  [list-search](../005-list-search/PRD.md) aynı soru akışını kullanır;
  [analysis-records](../008-analysis-records/PRD.md) çağrı özetlerini analiz kaydında saklar ve
  gösterir; [search-settings](../009-search-settings/PRD.md) yönetim ekranı kabuğunda (kenar
  çubuğu, Ctrl K komut paleti) model durumunu ve bu sayfanın eylemlerini gösterir. Hepsi modele
  yalnız bu PRD'nin portuyla ulaşır.

## Değişmezler ve sınırlar

- Modele giden her istek (sohbet, model listesi, sağlık denetimi) yalnız özel ağ adresine gider. Bu
  kural kapatılamaz; ayar, API veya arayüzle istisna tanınamaz.
- Şifreli bağlantıda sunucu sertifikasının doğrulanması hiçbir ortamda kapatılamaz; ortamdaki vekil
  sunucu (proxy) kullanılmaz; yönlendirme (başka adrese gönderme yanıtı) izlenmez.
- Aynı istem, şema ve bağlantı için modele giden istek gövdesi kaynak `76e21a3` ile bayt bayt
  aynıdır; beyan edilmiş iki fark Requirement 6'dadır (Requirement 6–8).
- İstem, soru metni, sözlük içeriği, model yanıtı, model sunucusunun hata metni, adres ve API
  anahtarı uygulama loguna, OpenTelemetry (ölçüm ve iz toplama sistemi) sinyallerine, hata
  yanıtlarına ve çağrı özetine girmez.
- API anahtarı yalnız sunucu sınırındadır: PostgreSQL'de yalnız şifreli durur, yanıtta yalnız
  `has_key` bilgisi döner.
- Aynı anda en çok bir aktif sohbet modeli vardır; bu, veritabanı kısıtıyla korunur.
- İstem ve şema içeriği, analist adımları, analizlerin kuyruğu ve eşzamanlılığı, analizin durdurulması,
  kayıtlı cevaplar ve "Analiz yapılamadı" cevabının gösterimi
  [question-analysis](../004-question-analysis/PRD.md) PRD'sinindir. Çağrı özetinin analiz
  kaydındaki veri modeli ve gösterimi
  [analysis-records](../008-analysis-records/PRD.md) PRD'sinindir.

Decision 1: Modele erişim bir uygulama portu ile altyapı bağdaştırıcısı arasında ayrılır
(`technology-profile.yml` `llm_orchestration.generation_boundary`). Port üç işlem sunar:
**sohbet** (sistem istemi, kullanıcı içeriği, JSON şeması, `max_tokens` ve amaç alır; ayrıştırılmış
JSON nesnesini ya da sabit hata sınıfını ve her durumda çağrı özetini döndürür), **sağlık denetimi**
(ayakta, bağlı değil ya da yanıt vermiyor ve sınıf) ve **model listesi**. Analist, bağlantı testi ve
ölçüm betiği modele yalnız bu portla ulaşır; başka hiçbir modül model sunucusuna istek yapmaz.

Decision 2: Tek istek biçimi kaynaktaki gibi OpenAI uyumlu `POST <adres>/chat/completions` ve
akışsız (cevabın tek seferde geldiği) yanıttır; model listesi `GET <adres>/models`'tır. Başka istek
biçimi ve akışlı yanıt eklenmez.

Decision 3: Bağlantılar her ortamda yalnız yönetim ekranından (`yonetici`) yönetilir ve
PostgreSQL'de durur. Adres, model ve API anahtarı için ortam değişkeni yoktur. Kaynaktaki
`data/llm_integrations.yaml` dosyası, `settings.yaml` `llm:` bölümü (`LLMSettings`) ve dosyadan
ilk kayda taşıma yolu (`from_llm_settings`) kalkar; kaynak dosyalardan veri taşınmaz.

Decision 4: Ortam (`local` veya `nonprod`) `DWHNAVIGATOR_ENVIRONMENT` ayarından okunur;
`development` `local`, `staging` `nonprod` demektir, başka ya da okunamayan değer `nonprod` sayılır
([application-foundation alanı](../../../application-foundation/DOMAIN.md)). Ortamlar arasındaki tek
fark kabul edilen adres şemasıdır: şifresiz `http` yalnız `local`'de kabul edilir, `nonprod`'da
yalnız şifreli `https`; `nonprod`'un model ucu (RunAI) `https` olduğu için istisna yoktur (Decision
18).

## Mevcut davranış

Kaynak uygulama (bu deponun geçmişindeki `76e21a3`) bugün şöyle çalışır; hedefteki değişiklik her
maddede belirtilmiştir.

- **Bağlantının yeri** (`src/vsa/config.py` `load_settings`, `read_integrations`,
  `write_integrations`; `src/vsa/web/llm_admin.py` `LLMAdmin.items`): Entegrasyonlar
  `data/llm_integrations.yaml` dosyasında, API anahtarı düz metin olarak durur (dosya başlığı "API
  anahtarları içerir: repoya girmez, paylaşmayın."). Dosya yoksa `settings.yaml` `llm:` bölümü
  geçerlidir; ekran onu "Mevcut bağlantı" adıyla gösterir ve ilk değişiklikte dosyaya yazar ("Bu
  bağlantı ayar dosyasından okundu; ilk değişiklikte … dosyasına yazılır."). Dosyadaki bilinmeyen
  alanlar (kaldırılan vektör aramasından kalan gömme modeli) okunurken atılır. **Hedefte:**
  PostgreSQL'de `llm_integration` tablosu, anahtar şifreli; dosya, `llm:` bölümü, taşıma yolu ve eski
  alan toleransı yoktur (Decision 3, Requirement 3 ve 20).
- **Alanlar ve doğrulama** (`src/vsa/llm/integrations.py` `Integration`, `validate`,
  `normalize_endpoint`, `new_id`; `LLMAdmin.save`): Bir entegrasyon addan türetilen kimliği
  (`dgx-spark-1`), adı, API adresini, isteğe bağlı anahtarı, aktifliği, sohbet modelini,
  `temperature` (0,0; 0–2), `timeout` (900 sn; 5–3600), `reasoning_effort` (`none`; `none`, `low`,
  `medium`, `high` ya da boş = gönderme), `seed` (42; −1 = gönderme) ve son test sonucunu taşır.
  Adres kırpılır, sondaki `/` ile yapıştırılmış `/chat/completions` veya `/models` atılır; şema
  `http`/`https` değilse ya da ana makine yoksa "API adresi http:// veya https:// ile başlayan tam
  bir adres olmalı (ör. http://10.0.0.5:8000/v1)". Ad boş olamaz ve Türkçe katlamayla (uygulamanın
  harf normalleştirmesi) benzersizdir. Hatalar `; ` ile birleşip 400 döner; uzunluk sınırı yoktur.
  **Hedefte:** aynı alanlar, varsayılanlar ve aralıklar; kimlik `public_id`; ada, modele, adrese ve
  anahtara uzunluk ve karakter sınırı; adrese şema ve özel ağ denetimi; hata 422 (Requirement 2).
- **Tek aktif sohbet modeli** (`holder`, `conflicts`, `LLMAdmin.save`, `set_active`, `_conflict`):
  Sohbet modeli olmayan entegrasyon aktif yapılamaz ("Önce bu entegrasyon için bir sohbet modeli
  seçin"); kayıtta ise aynı durum sessizce pasif kaydedilir. Başka bir entegrasyon aktifken aktif
  etme istenirse hiçbir şey kaydedilmez, yanıt `{"ok": false, "conflict": [...]}` olur; arayüz
  "“…” (Sohbet modeli) şu an bu rolde aktif. Pasif yapılıp yerine bu entegrasyon kullanılsın mı?"
  diye sorar ve `replace: true` ile öncekini pasif yapar. **Hedefte:** aynı kural; çakışma 409,
  kayıtta da modelsiz aktifleştirme 422; tek aktiflik veritabanı kısıtıyla (Requirement 4).
- **Değişikliğin uygulanması** (`LLMAdmin._store`, `src/vsa/web/server.py` `App.reload`): Her
  kayıt, aktif/pasif ve silme dosyayı yeniden yazar ve motoru (`Engine.from_index`) baştan kurar;
  süren analiz eski motorla biter, sıradaki analiz kilidi aldığında yeni motoru kullanır.
  **Hedefte:** motor yeniden kurulmaz; her analiz model adımlarına başlamadan hemen önce yürürlükteki
  bağlantıyı PostgreSQL'den bir kez okur ve analiz boyunca onu kullanır (Requirement 5).
- **İstek gövdesi** (`src/vsa/llm/client.py` `OpenAICompatibleClient._chat_json`, `_post`):
  `POST <adres>/chat/completions`, `Content-Type: application/json`, anahtar varsa
  `Authorization: Bearer <anahtar>`. Gövde Python `json.dumps` varsayılanıyla yazılır (ASCII dışı
  karakterler `\uXXXX` biçiminde kaçışlı, ayraçlar `", "` ve `": "`); alan sırası `model`,
  `messages` (sistem ve kullanıcı), `temperature`, `max_tokens`, boş değilse `reasoning_effort`, 0
  ya da büyükse `seed`, sonra şemalı yanıt isteği `response_format`. Analistin 1. adımı `max_tokens`
  2500, 2. adımı `analyst.max_tokens` (8000), bağlantı testi 60 gönderir. Adresteki `localhost`
  Windows'taki gecikme yüzünden `127.0.0.1`'e çevrilir. **Hedefte:** gövde bayt bayt aynı;
  Windows'a özgü `localhost` çevirisi kalkar (Requirement 6, Decision 6).
- **Özellik uyarlaması** (`OpenAICompatibleClient._adapt`): Sunucu 400 koduyla bir özelliği
  reddederse istemci o özelliği bırakıp aynı isteği yeniden gönderir: hata metni "developer
  instruction" ya da "system instruction" içeriyorsa sistem istemi kullanıcı mesajının başına
  katlanır; "json mode", "response_format", "response_mime_type" ya da "schema" içeriyorsa
  `response_format`, "reasoning" ya da "thinking" içeriyorsa `reasoning_effort`, "seed" içeriyorsa
  `seed` gönderilmez. Bir çağrıda en çok 3 uyarlama yapılır; öğrenilen durum istemci nesnesinde kalır
  ve motor yeniden kurulana kadar (her ayar, sözlük veya bağlantı değişikliği) sonraki çağrılar o
  özellik olmadan gider. Uyarlama, sunucu metninin 160 karakteriyle uygulama loguna, 300 karakteriyle
  analiz izine olay olarak yazılır. **Hedefte:** aynı kurallar ve sıra; öğrenilen durum bağlantı
  alanları değişene ya da süreç yeniden başlayana kadar bellekte kalır; sunucu metni hiçbir yere
  yazılmaz (Requirement 7, Decision 12). Yalnız hedefte bir ek vardır: RunAI'deki vLLM, Qwen
  modelinde `reasoning_effort: "none"`'ı 400 ile reddeder ve düşünmeyi yalnız
  `chat_template_kwargs: {"enable_thinking": false}` kapatır; bu yüzden reddedilen değer `"none"`
  ise yeniden gönderilen istek bu alanı taşır, sunucu onu da reddederse o da bırakılır
  (Requirement 7 kural 3 ve 5, Decision 19).
- **Yanıt ayrıştırma ve onarım** (`parse_json_reply`, `_chat_json`): Cevap
  `choices[0].message.content`'tir; `<think>…</think>` ve `<thought>…</thought>` blokları ile kod
  çitleri atılır, metin JSON değilse ilk `{` ile son `}` arası denenir. JSON nesnesi çıkmazsa bir kez
  onarım istenir (modelin yanıtının ilk 2000 karakteri ve "Yanıtın geçerli JSON değil. SADECE şemaya
  uyan JSON döndür." eklenir); yine çıkmazsa "model geçerli JSON üretmedi". `choices` yoksa
  "beklenmeyen yanıt". Onarım olayı analiz izine modelin yanıtından 200 karakter yazar. Her başarılı
  yanıttaki `usage.prompt_tokens` ve `usage.completion_tokens` analiz izine eklenir. Sunucunun
  yanıtın neden bittiğini bildirdiği `choices[0].finish_reason` okunmaz; uzunluk sınırında kesilen
  yanıt da onarılmak istenir ve aynı sınırla yine kesilip "model geçerli JSON üretmedi" olur.
  **Hedefte:** aynı ayrıştırma ve onarım; olaya model metni yazılmaz; uzunluk sınırında kesilen
  geçersiz yanıt için onarım istenmez ve sonuç ayrı sınıftır (Requirement 8, Decision 20).
- **Süreler ve yeniden deneme** (`_stoppable`, `CONNECT_TIMEOUT`): Bağlanma en çok 10 saniye sürer
  (yanıt vermeyen sunucu soruyu 900 saniye tutmasın diye); okuma süresi bağlantının `timeout`
  değeridir. Zaman aşımı, bağlantı hatası ve 400 dışındaki sunucu hataları yeniden denenmez. `urllib`
  ortamdaki vekil sunucu ayarını kullanır, yönlendirmeyi izler, yanıt boyutunu sınırlamaz.
  **Hedefte:** süreler ve yeniden denememe kuralı aynı; vekil yok, yönlendirme izlenmez, yanıt 4 MiB
  ile sınırlı (Requirement 9 ve 10, Decision 7).
- **Durdurma** (`src/vsa/cancel.py` `Token`, `client.py` `_abort`): Kullanıcı analizi durdurunca
  açık model bağlantısı kesilir (model sunucusu üretimi bırakır); bağlanırken gelen durdurma da
  işlenir; durdurma model hatası sayılmaz. **Hedefte:** aynı (Requirement 11).
- **Ölü sunucu beklenmez** (ADR-034; `OpenAICompatibleClient.health`, `HEALTH_TIMEOUT` 5,
  `HEALTH_TTL` 30, `_HEALTH`; `src/vsa/pipeline.py` `Engine.analyze`): Her analizden önce
  `GET <adres>/models` 5 saniyelik süreyle denenir; sonuç adrese göre 30 saniye bütün istemcilerce
  paylaşılır; sunucu yoksa analiz modele gitmeden "Analiz yapılamadı" ve nedenle biter. Ana ekranın
  60 saniyede bir okuduğu `/api/status` `llm_state` (`ok`, `none`, `down`) ile yönetim ekranının
  `/api/llm` `engine.chat_down` alanı aynı denetimi kullanır. Neden metni sunucu adresini içerir
  ("Model sunucusuna ulaşılamadı (http://…): bağlantı reddedildi — adres/port yanlış ya da sunucu
  kapalı"). **Hedefte:** aynı süreler; önbellek bağlantıya göre tutulur ve bağlantı değişince
  boşalır; metinde adres yoktur (Requirement 12, Decision 14).
- **Hata metinleri** (`_why`, `_error_text`, `LLMError`, `pipeline.fallback_reason`): Sunucunun
  hata gövdesinden 600 karaktere kadar metin hata nesnesine girer; bağlantı testi bunun 300
  karakterini, analiz nedeni ("Model hatası: …") 160 karakterini kullanıcıya gösterir;
  `log.warning("LLM çağrısı başarısız: %s", …)` aynı metni uygulama loguna, analiz izindeki çağrı
  ayrıntısı `"<model> — <hata>"` biçiminde 300 karakterini analiz kaydına yazar. Bilinmeyen bağlantı
  hatasında istisna metni olduğu gibi gösterilir. **Hedefte:** sabit hata sınıfları ve Türkçe neden
  tablosu; sunucu gövdesi yalnız sınıflandırma ve uyarlama için okunur, hiçbir yere yazılmaz
  (Requirement 13, Decision 13).
- **Model listesi ve envanter** (`OpenAICompatibleClient.list_models`, `LLMAdmin.models`,
  `inventory`, `INVENTORY_TIMEOUT` 6): `GET <adres>/models` (10 sn) ve adres `/v1` ile bitiyorsa LM
  Studio'nun (ekibin kullandığı model sunucusu uygulaması) `GET <kök>/api/v0/models` ucu (3 sn;
  hatası yok sayılır) okunur: model kimliği, tür, yüklü mü, bağlam uzunluğu (`max_context_length`,
  `max_model_len`, `context_length` ya da `context_window`), sahip, nicemleme (`quantization`) ve
  kullanımda mı. Envanter bütün entegrasyonları en çok 8'i aynı anda, her biri 6 saniyelik süreyle
  sorar; ulaşılamayan sunucu hata olarak listelenir. **Hedefte:** aynı; tek istekte yürüdükleri için
  toplam süreleri sınırlıdır (Requirement 9 ve 14).
- **Bağlantı testi** (`LLMAdmin.test`, `_candidate`, `TEST_CHAT_TIMEOUT` 180, `TEST_QUESTION`,
  `TEST_SCHEMA`): Formdaki kaydedilmemiş değerlerle iki adım çalışır: "Sunucu" (`/models`, "Bağlantı
  kuruldu; sunucuda N model var") ve sunucu adımı geçtiyse "Sohbet modeli" (sistem istemi "Kısa ve
  doğru cevap ver. SADECE JSON döndür.", soru "Türkiye'nin başkenti neresidir?", `{"cevap": metin}`
  şeması, `max_tokens` 60, okuma süresi `timeout` ile 180'in küçüğü; "Cevap verdi: “Ankara”"). Model
  sunucunun listesinde yoksa nedenin sonuna " (model sunucunun listesinde yok)" eklenir. Karttaki
  "Test et" sonucu (`at`, `ok`, `summary`) entegrasyona yazar. Formda anahtar boşsa kayıtlı anahtar
  kullanılır — adres değiştirilmiş olsa bile. **Hedefte:** aynı adımlar ve metinler; sohbet adımı en
  çok 30 saniye sürer (kaynakta 180; 60 saniye kuralı, Requirement 9); kayıtlı anahtar yalnız
  kaydedildiği adres kökenine (şema, ana makine ve port) gider (Requirement 15 ve 16).
- **Anahtarın korunması** (`Integration.public`, `LLMAdmin.save`, `LLMAdmin.state`): Anahtar
  tarayıcıya dönmez, yalnız `has_key`; boş anahtar alanı kayıtlı anahtarı korur, "Kayıtlı anahtarı
  sil" (`clear_key`) siler; adres değişse de anahtar korunur. `/api/llm` yanıtı sunucudaki dosya
  yolunu (`path`) da döndürür. **Hedefte:** aynı gizlilik; adres kökeni (şema, ana makine ve port)
  değişince yeni anahtar girilmemişse kayıtlı anahtar silinir; yanıtta dosya yolu yoktur
  (Requirement 3, Decision 9).
- **Kurum dışı adres** (`is_internal`, `INTERNAL_SUFFIXES`; ADR-031): Özel aralıklar, makinenin
  kendi adresi, bağlantı yerel adresleri, `100.64.0.0/10`, noktasız ad ve `.local`, `.lan`,
  `.internal`, `.intranet`, `.corp`, `.localhost` sonekli adlar kurum içi sayılır; değilse kartta
  "Kurum dışı adres" uyarısı çıkar ama bağlantı engellenmez; ad çözülmez. **Hedefte:** uyarı yerine
  yasak; ad çözülür, çözülen bütün adresler ve bağlanılan adres özel ağda olmalıdır (Requirement 10,
  Decision 15).
- **Eşzamanlılık** (`ThreadingHTTPServer`, `App.lock`): Analizler tek kilitle sırayla yürür, bir
  analizdeki çağrılar ardışıktır; bağlantı testi ve envanter kilide girmez, analizle aynı anda model
  sunucusuna gidebilir; aynı anda kaç sohbet çağrısı yapılacağını sınırlayan kural yoktur.
  **Hedefte:** analizlerin kuyruğu ve eşzamanlılığı [question-analysis](../004-question-analysis/PRD.md)
  PRD'sindedir; bu PRD süreç geneli sohbet çağrısı sınırı koyar (Requirement 17, Decision 11).
- **Çağrı sayaçları** (`src/vsa/trace.py` `span(…, trace.LLM)`, `count`, `Trace.totals`;
  `App._log_analysis`): Her sohbet çağrısı analiz izinde bir "LLM çağrısı" aralığıdır; başarılı yanıt
  sayısı ve token (modelin metin birimi) sayıları aralığa eklenir; analiz kaydı
  (`data/logs/analyses.jsonl`) toplam çağrı ve token sayılarını taşır. Bağlantı testi, model listesi
  ve envanter hiçbir yere kaydedilmez. **Hedefte:** port her sohbet çağrısı için içerik taşımayan
  çağrı özeti döndürür; özetin tek kalıcı yeri analiz kaydıdır, ayrı çağrı tablosu yoktur
  (Requirement 18, Decision 8).
- **Yetki** (`src/vsa/web/security.py` `AdminGuard`, `cross_site`; ADR-047): `/api/llm` uçları
  yönetim parolasıyla (HTTP Basic, `VSA_ADMIN_PASSWORD`) ya da parola yoksa yalnız sunucunun
  kendisinden açılır; değişiklik istekleri `Sec-Fetch-Site`/`Origin` denetiminden geçer.
  `docs/GUVENLIK.md` bulgu 3, bağlantı testinin sunucudan başka adrese istek yapmasını yalnız bu
  parolayla sınırlar. **Hedefte:** oturum ve `yonetici` rolü
  ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)) ile özel ağ
  ve ağ çıkış kuralları (Güvenlik ve yetkilendirme, Requirement 21).
- **Arayüz** (`src/vsa/web/static/admin.html` `AI`, `modelState`, `Shell.refresh`; ADR-032,
  ADR-051): Yapay zekâ sayfası etkin model kartı, entegrasyon kartları, üç adımlı düzenleyici
  çekmece (Bağlantı; Model ve "Gelişmiş"; Test) ve model envanteri çekmecesi sunar; çakışma ve silme
  onayını tarayıcının `confirm` penceresiyle sorar. **Hedefte:** React'te aynı işlev, görünüm ve
  metinler; onaylar yine tarayıcının `confirm` penceresiyle; kurum dışı adres yasaklandığı ve dosya
  kalktığı için "Kurum dışı adres" etiketi ve dosya iletisi kalkar (Requirement 19).
- **Komut satırı ve kurulum** (`vsa ask`, `vsa eval`; `docs/KURULUM.md` §5): Komut satırı da
  bağlantıyı aynı dosyalardan okur; kurulum belgesi ekran kullanılmayacaksa bağlantının
  `settings.yaml` `llm:` bölümüne yazılıp konteynerin yeniden başlatılmasını önerir ve örnek adres
  olarak `http://dgx-spark:8000/v1` verir. **Hedefte:** `vsa ask` kalkar; ölçüm betiği modele bu
  portla ve PostgreSQL'deki bağlantıyla gider, hangi bağlantıyla ölçüldüğü
  [quality-evaluation](../010-quality-evaluation/PRD.md) PRD'sindedir; dosyaya yazma yolu kalkar.

## İşlevsel gereksinimler

Requirement 1: Tipli ayarlar (`DWHNAVIGATOR_` önekli ortam değişkenleri) üç tanedir:

- `DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY` (sır, isteğe bağlı): rastgele 32 baytın standart base64
  yazımı. Doluysa ve bu biçimde değilse süreç başlamaz ve hata iletisi değeri yankılamaz. Boşsa API
  anahtarı kaydedilemez (Requirement 3) ve kayıtlı anahtarlar okunamaz (`key_unreadable`). Anahtarın
  anlamının sahibi bu PRD'dir; değeri `nonprod`'da dağıtım kancası bir kez üretir, yerelde fabrikanın
  yerel sır üretimi verir
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  Requirement 7 ve 17).
- `DWHNAVIGATOR_LLM_CA_BUNDLE`: model sunucusunun sertifikasını doğrulayan güven dosyasının yolu;
  boşsa imajın sistem güven deposu. Dosya okunamıyorsa süreç başlamaz.
- `DWHNAVIGATOR_LLM_MAX_CONCURRENT_CALLS`: süreç geneli sohbet çağrısı sınırı; varsayılan 5,
  aralık 1–8 (Requirement 17).

Şunlar ayar değil, koddaki sabitlerdir: bağlanma 10 sn; sağlık denetimi 5 sn ve 30 sn önbellek;
model listesi 10 sn; LM Studio ayrıntı ucu 3 sn; envanter sunucu başına 6 sn ve en çok 8 paralel;
test sohbet adımı en çok 30 sn (kaynakta 180); tek istekte yürüyen yönetim çağrılarının toplam üst
süreleri (Requirement 9); yanıt en çok 4 MiB; `User-Agent` başlığı
`DWHNavigator-Backend/1.0 (internal data dictionary; httpx)`. Bağlantı adresi, model ve API anahtarı
için ayar yoktur (Decision 3).

Requirement 2: Kaydedilen ve test edilen her entegrasyonun alanları şu kurallarla doğrulanır:

- `name`: kırpılır; 1–100 karakter; denetim karakteri içermez.
- `endpoint`: kırpılır, sondaki `/` ile yapıştırılmış `/chat/completions` ya da `/models` atılır; en
  çok 2048 karakter; şema `local`'de `http` ya da `https`, `nonprod`'da yalnız `https` (Decision 4);
  ana makine dolu; kullanıcı adı ve parola (`kullanıcı:parola@`), sorgu (`?`), parça (`#`), boşluk
  ve denetim karakteri yok; port 1–65535.
- `chat_model`: kırpılır; 0–256 karakter; denetim karakteri içermez.
- `temperature`: 0–2, varsayılan 0,0. `timeout_seconds`: tam sayı, 5–3600, varsayılan 900.
  `reasoning_effort`: `none`, `low`, `medium`, `high` ya da boş (gönderme), varsayılan `none`.
  `seed`: tam sayı, −1 (gönderme) ile 2147483647 arası, varsayılan 42.
- `api_key`: 1–4096 karakter, boşluk ve denetim karakteri içermez; değer hiçbir iletide yankılanmaz.

Biçim ve aralık hataları birlikte 422 `llm_integration_invalid` ile döner, iletiler kaynaktaki gibi
`; ` ile birleşir ve kaynak metinleri korunur ("Ad boş olamaz", "API adresi http:// veya https://
ile başlayan tam bir adres olmalı (ör. http://10.0.0.5:8000/v1)", "Sıcaklık 0 ile 2 arasında
olmalı", "Zaman aşımı 5 ile 3600 saniye arasında olmalı", "Düşünme modu geçersiz", "Sayısal
alanlardan biri geçersiz"). Yeni iletiler: `nonprod`'da şema hatası "Bu ortamda API adresi https://
ile başlamalı"; adres kuralı "API adresi kullanıcı adı, parola, sorgu veya # parçası içeremez";
seed "Seed -1 ile 2147483647 arasında olmalı"; uzunluk "{alan} en çok {n} karakter olabilir"; anahtar
"API anahtarı geçersiz karakter içeriyor". Biçim geçtikten sonra kayıtta şu denetimler yapılır: ad,
silinmemiş entegrasyonlar arasında Türkçe katlamayla benzersiz olmalıdır, değilse 409
`llm_integration_name_taken` ("“{ad}” adında bir entegrasyon zaten var"); adres çözülemezse 422
`llm_endpoint_unresolved` ("sunucu adı çözülemedi — adresi kontrol edin"); çözülen adreslerden biri
özel ağ dışındaysa 422 `llm_endpoint_not_private` ("Adres kurum ağı dışında; yalnız kurum içi model
sunucusu bağlanabilir."). Kiracı başına en çok 50 entegrasyon tanımlanır; aşan oluşturma 409
`llm_integration_limit` ("En çok 50 entegrasyon tanımlanabilir.") alır (Decision 17).

Requirement 3: Kaydetme, anahtar ve silme şöyle çalışır:

- Oluşturma ad ve adres ister, diğer alanlar varsayılanını alır; `activate` verilmezse entegrasyon
  pasif kaydedilir. Güncelleme kısmidir: gönderilmeyen alan korunur.
- `api_key` gönderilmezse kayıtlı anahtar korunur, dolu gelirse şifrelenip yazılır, `""` gelirse
  silinir. Güncellemede adresin kökeni (şema, ana makine ve port) değişmiş ve yeni anahtar
  verilmemişse kayıtlı anahtar silinir ve yanıt `key_cleared: true` taşır (Decision 9).
- `DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY` boşken dolu `api_key` 422 `llm_key_storage_unavailable`
  ("Bu ortamda API anahtarı saklanamıyor; şifreleme anahtarı tanımlı değil.") alır; anahtarsız
  entegrasyon kaydedilir ve kullanılır.
- Adres ya da sohbet modeli değişince son test sonucu silinir.
- Yanıt API anahtarını ve şifreli değerini hiçbir zaman taşımaz; yalnız `has_key` döner.
- Silme yazılımsal silmedir (satır silinmez, silinmiş işaretlenir): şifreli anahtar boşaltılır,
  aktiflik kalkar. Aktif entegrasyon silinirse sohbet modeli boşta kalır ve sonraki analizler
  `not_configured` nedenini alır.
- Kayıt, aktif/pasif yapma ve silme yeniden başlatma gerektirmez; sonraki analiz yeni durumu kullanır
  (Requirement 5).

Requirement 4: Aynı anda en çok bir silinmemiş entegrasyon aktiftir; PostgreSQL'de kiracı başına
aktif satırlara uygulanan kısmi benzersiz dizinle (yalnız aktif ve silinmemiş satırlarda geçerli
benzersizlik kuralı) korunur. Sohbet modeli boş entegrasyon aktif yapılamaz: kayıtta
`activate: true` ile, aktif etme ucunda ve aktif entegrasyonun modeli boşaltılmak istendiğinde 422
`llm_chat_model_required` ("Önce bu entegrasyon için bir sohbet modeli seçin") döner. Başka bir
entegrasyon aktifken aktif etme (kayıtta ya da aktif etme ucunda) `replace` doğru değilse hiçbir şey
değiştirmeden 409 `llm_chat_role_taken` döner ve ileti aktif olanın adını taşır. `replace: true`
ile öncekini pasif yapmak ve yenisini aktif etmek tek veritabanı işlemidir. Eşzamanlı iki aktif
etmeden en çok biri başarılı olur, diğeri 409 alır.

Requirement 5: Port, analizin model adımları başlamadan hemen önce (analiz sırasını bekledikten
sonra) aktif entegrasyonu PostgreSQL'den bir kez okur: adres, çözülmüş API anahtarı, sohbet modeli,
`temperature`, `timeout_seconds`, `reasoning_effort`, `seed` ve `public_id`. Analizin bütün
çağrıları bu anlık görüntüyü kullanır; analiz sürerken yapılan değişiklik sonraki analizden
itibaren geçerlidir (Decision 16). Aktif entegrasyon ya da sohbet modeli yoksa sonuç
`not_configured`, kayıtlı anahtar açılamıyorsa `key_unreadable`'dır; anahtarı açılamayan bağlantıyla
anahtarsız istek gönderilmez. Anlık görüntünün `model`, `temperature`, `reasoning_effort` ve `seed`
alanları [question-analysis](../004-question-analysis/PRD.md) PRD'sindeki kayıtlı cevap parmak
izine girer (kaynak `answer_cache._LLM_KEYS`); adres, anahtar, ad ve zaman aşımı girmez.

Requirement 6: Sohbet isteği `POST <adres>/chat/completions` olarak gider. Başlıklar
`Content-Type: application/json`, `User-Agent` (Requirement 1) ve anahtar varsa
`Authorization: Bearer <anahtar>`'dır; anahtar yoksa `Authorization` başlığı hiç gönderilmez. Gövde
baytları kaynaktaki `json.dumps(gövde).encode("utf-8")` ile aynı yazılır: ASCII dışı karakterler
`\uXXXX` biçiminde kaçışlı, ayraçlar `", "` ve `": "`, alanlar sıralanmadan (Decision 6). Alanlar bu
sırayla gelir:

1. `model`;
2. `messages`: sistem iletisi (`"role": "system"`, içerik sistem istemi) ve kullanıcı iletisi
   (`"role": "user"`, içerik kullanıcı içeriği);
3. `temperature` (ondalık sayı; varsayılan `0.0`);
4. `max_tokens` (çağıranın verdiği tam sayı);
5. `reasoning_effort` (yalnız boş değilse; varsayılan `"none"`);
6. `seed` (yalnız 0 ya da büyükse; varsayılan `42`);
7. `response_format`: önce `"type": "json_schema"`, sonra `"json_schema"` nesnesi; bu nesnede
   sırasıyla `"name": "result"`, `"strict": true` ve `"schema": <şema>`.

`stream` ve başka alan gönderilmez; tek ayrık durum, Requirement 7 kural 3'ün yeniden gönderilen
istekte 5. sıraya (`reasoning_effort`'ın yerine) koyduğu `chat_template_kwargs` alanıdır. İlk istek
bu alanı hiçbir zaman taşımaz. Aynı girdiler ve aynı sunucu yanıtları için sunucunun aldığı gövde
dizisi, Requirement 7 ve 8'deki uyarlama ve onarım tekrarları dahil, kaynak `76e21a3`
`OpenAICompatibleClient`'ın gönderdiğiyle bayt bayt aynıdır. Beyan edilmiş iki fark vardır: bu alan
(Decision 19) ve uzunluk sınırında kesilen geçersiz yanıttan sonra kaynağın gönderdiği onarım
isteğinin gönderilmemesi (Requirement 8, Decision 20). Başlıklar bu karşılaştırmaya girmez.

Requirement 7: Yalnız 400 kodlu yanıtta, yanıt gövdesinin ilk 600 karakteri uygulamanın Türkçe
katlama yardımcısıyla (`fold`: Türkçe kurallarla küçük harf ve aksansız biçim) çevrilip şu sırayla
denetlenir; ilk uyan kural uygulanır ve aynı istek o özellik olmadan yeniden gönderilir:

1. Sistem iletisi hâlâ ayrıysa ve metin "developer instruction" ya da "system instruction"
   içeriyorsa sistem istemi, araya iki satır sonu (`\n\n`) konarak ilk kullanıcı iletisinin başına
   katlanır ve `system` rolü gönderilmez.
2. `response_format` hâlâ gönderiliyorsa ve metin "json mode", "response_format",
   "response_mime_type" ya da "schema" içeriyorsa `response_format` gönderilmez.
3. `reasoning_effort` hâlâ gönderiliyorsa ve metin "reasoning" ya da "thinking" içeriyorsa
   `reasoning_effort` gönderilmez. **Hedefte:** gönderilen değer `"none"` idiyse (bağlantı düşünmeyi
   kapalı istiyorsa) yeniden gönderilen istek onun yerine, `max_tokens`'tan sonra ve `seed`'den önce,
   `"chat_template_kwargs": {"enable_thinking": false}` taşır (gövde yine `json.dumps`
   varsayılanıyla yazılır). `low`, `medium` ve `high` reddedildiğinde kaynaktaki gibi yalnız alan
   bırakılır.
4. `seed` hâlâ gönderiliyorsa ve metin "seed" içeriyorsa `seed` gönderilmez.
5. **Hedefte:** `chat_template_kwargs` gönderiliyorsa ve metin "chat_template_kwargs",
   "enable_thinking" ya da "template" içeriyorsa `chat_template_kwargs` gönderilmez. Kural kaynağın
   dört kuralından sonra gelir; onların sırası ve önceliği değişmez.

Bir sohbet çağrısında en çok 3 uyarlama yapılır; uyan kural yoksa ya da sınır dolduysa çağrı
Requirement 13 sınıfıyla biter. Öğrenilen durum aynı bağlantının sonraki çağrılarında da geçerlidir;
bağlantı alanlarından biri (adres, anahtar, model, `temperature`, `timeout_seconds`,
`reasoning_effort`, `seed`) değişince ya da süreç yeniden başlayınca sıfırlanır (Decision 12).
Bağlantı testi kendi boş durumuyla başlar ve analizlerin durumunu değiştirmez. Bırakılan özellikler
çağrı özetine sırasıyla `system_role`, `response_format`, `reasoning_effort`, `seed`,
`chat_template_kwargs` olarak yazılır; düşünmenin kapatılması da öğrenilen durumun parçasıdır, yani
aynı bağlantının sonraki çağrıları ilk istekten itibaren `chat_template_kwargs` ile (ya da o da
bırakıldıysa onsuz) gider. Sunucu metni, model yanıtı ve modelin düşünme metni hiçbir yere yazılmaz.

Requirement 8: Başarılı yanıtın gövdesi JSON nesnesi olmalı ve `choices[0].message` taşımalıdır;
değilse sonuç `invalid_response` olur ve onarım istenmez. Modelin metni
`choices[0].message.content`'tir (boşsa `""`). Ayrıştırma kaynak `parse_json_reply` ve onun
`_THINK`, `_FENCE` düzenli ifadeleriyle aynıdır: `<think>…</think>` ve `<thought>…</thought>`
blokları, sonra satır başındaki ve satır sonundaki kod çiti işaretleri (üç ters tırnak, isteğe bağlı
`json` sözcüğüyle) atılır; metin JSON olarak okunur, okunamazsa ilk `{` ile son `}` arası denenir;
sonuç JSON nesnesi değilse (dizi, sayı, metin) geçersizdir. Geçerli bir JSON nesnesi çıkan yanıt,
`finish_reason` ne olursa olsun kabul edilir. Geçersiz yanıtta `choices[0].finish_reason` tam
olarak `"length"` ise (sunucu yanıtı çağıranın verdiği `max_tokens` sınırında kesti) onarım
istenmez ve sonuç `output_truncated`'dır; bu ilk yanıtta da onarım yanıtında da geçerlidir.
`finish_reason` yoksa, boşsa ya da başka bir değerse kaynaktaki yol izlenir: ilk yanıt geçersizse
bir kez onarım istenir: mesajlara `{"role": "assistant", "content": <yanıtın ilk 2000 karakteri>}`
ve `{"role": "user", "content": "Yanıtın geçerli JSON değil. SADECE şemaya uyan JSON döndür."}`
eklenir. İkinci yanıt da geçersizse sonuç `invalid_json`'dır. Uyarlama tekrarları bu iki yanıt
sınırına sayılmaz. Her başarılı yanıttaki `usage.prompt_tokens` ve `usage.completion_tokens`
değerleri (yoksa 0) çağrı özetinde toplanır; kesilen yanıtınkiler de toplanır.

Requirement 9: Bağlantı kurma (ad çözme, bağlanma ve şifreli bağlantı el sıkışması) en çok 10
saniye ile işlemin süresinin küçüğü kadar sürer. Sonrasında her gönderme ve okuma işlemi en çok şu
kadar bekler: sohbet çağrısında bağlantının `timeout_seconds` değeri, test sohbet adımında
`timeout_seconds` ile 30'un küçüğü, model listesinde 10, sağlık denetiminde 5, LM Studio ayrıntı
ucunda 3, envanterde sunucu başına 6 saniye. Yeniden deneme yoktur: zaman aşımı, bağlantı hatası,
şifreli bağlantı hatası ve 400 dışındaki her sunucu hatası çağrıyı ilk denemede bitirir; tekrar
yalnız Requirement 7 uyarlaması ve Requirement 8 onarımıdır (Decision 7).

Model listesi, bağlantı testi ve envanter tek istek olarak yürür ve
[kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Requirement 12'deki 60 saniye kuralını aşmayacak toplam üst süreyle sınırlıdır (bağlanma ve LM Studio
ayrıntı ucu dahil): model listesi en çok 10 saniye; bağlantı testi en çok 40 saniye (sunucu adımı 10,
sohbet adımı yer beklemesi dahil 30); envanter sunucu başına en çok 10, toplamda en çok 50 saniye.
Süresi dolan adım ya da sunucu `timeout` sınıfıyla döner.

Requirement 10: Her istekten önce adın çözüldüğü bütün adresler ve bağlantının gerçekten kurulduğu
karşı adres özel ağda olmalıdır: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`,
`169.254.0.0/16`, `100.64.0.0/10`, `::1/128`, `fe80::/10`, `fc00::/7` (IPv6 içine gömülü IPv4
adresi IPv4 olarak denetlenir). Değilse istek gövdesi gönderilmeden sonuç `network_policy_denied`
olur. `https` adreste sunucu sertifikası `DWHNAVIGATOR_LLM_CA_BUNDLE` ya da imajın sistem güven
deposuyla doğrulanır ve ana makine adı eşleşmelidir; doğrulama kapatılamaz. Ortamdaki vekil sunucu
değişkenleri (`HTTP_PROXY`, `HTTPS_PROXY` ve benzerleri) yok sayılır. 3xx (yönlendirme) yanıtı
izlenmez ve `upstream_status` olur. Yanıt, sıkıştırılmışsa açıldıktan sonra, 4 MiB'ı aşarsa okuma
kesilir ve sonuç `response_too_large` olur.

Requirement 11: Analiz durdurulunca (durdurmanın kendisi
[question-analysis](../004-question-analysis/PRD.md) PRD'sindedir) süren model isteğinin bağlantısı
en çok 1 saniye içinde kapatılır ve bağlantı yeniden kullanılmak üzere havuza dönmez; yer bekleyen
çağrı hiç gönderilmez. Sonuç `cancelled`'dır, model hatası sayılmaz; ardından uyarlama ve onarım
yapılmaz.

Requirement 12: Sağlık denetimi, anahtar varsa `Authorization` başlığıyla `GET <adres>/models`
isteğidir; 2xx kodlu bir JSON nesnesi gelirse sunucu ayaktadır, modelin listede olması aranmaz.
Sonuç aktif bağlantı başına 30 saniye bellekte tutulur ve süreçteki bütün istekler onu paylaşır;
bağlantı alanlarından biri değişince önbellek boşalır (Decision 14).
[question-analysis](../004-question-analysis/PRD.md) her analizde sohbet isteğinden önce bu
denetimi çağırır; sunucu ayakta değilse analiz sohbet isteği gönderilmeden biter. Kapalı portta
(bağlantı reddi) denetim 1 saniyenin, yanıt vermeyen adreste 6 saniyenin altında sonuçlanır. Model
durumu nesnesi şunları taşır: `state` (`ok`, `none` ya da `down`), `model` (aktif sohbet modeli;
`none`'da boş), `code` (Requirement 13 sınıfı; `ok`'ta boş) ve `reason` (`down`'da Requirement 13
yoklama iletisi, `none`'da "Sohbet modeli bağlı değil", `ok`'ta boş). Yönetim yanıtında ayrıca aktif
entegrasyonun adı vardır. Aynı nesne ana ekrana
[question-analysis](../004-question-analysis/PRD.md) PRD'sinin durum ucuyla (`GET /status`,
`llm_state`; durum göstergesi [dictionary-explorer](../007-dictionary-explorer/PRD.md)'dadır), yönetim
ekranının kabuğuna ve Genel bakış kartına `GET /llm-integrations` ile verilir.

Requirement 13: Başarısız her çağrı ve yoklama (sağlık denetimi, model listesi, envanter) sabit bir
sınıfa eşlenir. Kullanıcıya ve yöneticiye yalnız sınıfın sabit Türkçe metni ve varsa HTTP kodu
gösterilir; adres, sunucunun hata gövdesi, istisna metni ve anahtar hiçbir iletide yer almaz.
Sunucu gövdesi yalnız Requirement 7 uyarlaması ve `context_exceeded` ayrımı için okunur.

| Sınıf | Ne zaman | Kısa neden (test adımı, yoklama) |
|---|---|---|
| `not_configured` | Aktif entegrasyon ya da sohbet modeli yok | Sohbet modeli bağlı değil |
| `key_unreadable` | Kayıtlı anahtar açılamıyor (şifreleme anahtarı yok, değişmiş ya da değer bozulmuş) | Kayıtlı API anahtarı okunamadı; anahtarı yeniden girin |
| `network_policy_denied` | Ad özel ağ dışına çözülüyor ya da bağlanılan adres özel ağ dışında | adres kurum ağı dışında; istek gönderilmedi |
| `name_unresolved` | Ad çözülemedi | sunucu adı çözülemedi — adresi kontrol edin |
| `connect_refused` | Bağlantı reddedildi | bağlantı reddedildi — adres/port yanlış ya da sunucu kapalı |
| `connect_error` | Başka bir bağlantı hatası | bağlantı kurulamadı |
| `tls_error` | Sertifika doğrulanamadı ya da şifreli bağlantı kurulamadı | güvenli bağlantı kurulamadı — sunucu sertifikası doğrulanamadı |
| `timeout` | Bağlanma ya da okuma süresi doldu | sunucu zamanında yanıt vermedi — adres erişilemez olabilir |
| `unauthorized` | 401 ya da 403 kodu | Sunucu HTTP {kod} döndürdü (API anahtarı eksik veya geçersiz) |
| `context_exceeded` | 2xx dışı yanıt gövdesinin ilk 600 karakteri "context" ile birlikte "exceed", "size" ya da "length" içeriyor (400'de önce uyarlama denenir) | modelin bağlam penceresi yetmedi |
| `upstream_status` | Diğer 2xx dışı yanıtlar (3xx dahil) | Sunucu HTTP {kod} döndürdü |
| `invalid_response` | Gövde JSON nesnesi değil ya da beklenen alan yok | yoklamada "yanıt JSON değil — adres OpenAI uyumlu API'nin /v1 adresi mi?", sohbette "beklenmeyen yanıt" |
| `output_truncated` | Yanıttan JSON nesnesi çıkmadı ve `finish_reason` `"length"` (yanıt `max_tokens` sınırında kesildi; Requirement 8) | model cevabı uzunluk sınırında kesildi |
| `invalid_json` | Onarımdan sonra da JSON nesnesi çıkmadı | model geçerli JSON üretmedi |
| `response_too_large` | Açılmış yanıt 4 MiB'ı aştı | yanıt izin verilen boyutu aştı |
| `cancelled` | Analiz durduruldu | durduruldu |

Yoklama iletisi, `network_policy_denied`, `name_unresolved`, `connect_refused`, `connect_error`,
`tls_error`, `timeout` ve `invalid_response` sınıflarında "Model sunucusuna ulaşılamadı: {kısa
neden}", diğer sınıflarda yalnız kısa nedendir. Analiz yapılamadığında kullanıcıya gösterilen sebep
bu sınıflardan çıkarılır; sebep metinlerinin tek tablosu
[question-analysis](../004-question-analysis/PRD.md) Requirement 5'tedir (kaynak
`pipeline.fallback_reason` ve `Engine.analyze` ile aynı; adres ve sunucu gövdesi olmadan).

Requirement 14: Model listesi `GET <adres>/models` yanıtının `data[]` öğelerini okur. Adres `/v1`
ile bitiyorsa ayrıca LM Studio'nun `GET <kök>/api/v0/models` ucu okunur; bu ucun hatası yok sayılır.
Her model için `id`, `type`, `loaded` (doğru, yanlış ya da bilinmiyor), `context`
(`max_context_length`, `max_model_len`, `context_length` ya da `context_window`; yoksa boş), `owner`
(`owned_by` ya da `publisher`), `quant` ve `in_use` (aktif entegrasyonun sohbet modeli mi) döner.
Envanter silinmemiş bütün entegrasyonları entegrasyon sırasıyla, en çok 8'i aynı anda sorar;
ulaşılamayan sunucu `ok: false`, sınıf ve yoklama iletisiyle listelenir, istek hata vermez.

Requirement 15: Bağlantı testi, kayıtlı entegrasyonun değerlerinin üstüne formda gönderilen
değerleri koyar ve hiçbir şeyi kaydetmeden iki adım çalıştırır:

1. **Sunucu:** model listesi (10 sn); başarıda "Bağlantı kuruldu; sunucuda N model var".
2. **Sohbet modeli:** yalnız 1. adım geçtiyse ve sohbet modeli doluysa; sistem istemi "Kısa ve doğru
   cevap ver. SADECE JSON döndür.", kullanıcı içeriği "Türkiye'nin başkenti neresidir?", şema kaynak
   `TEST_SCHEMA` (yalnız zorunlu `cevap` metin alanı olan, başka alana izin vermeyen nesne),
   `max_tokens` 60, okuma süresi `timeout_seconds` ile 30'un küçüğü (Requirement 9). Başarıda "Cevap
   verdi: “{cevabın ilk 40 karakteri}”"; başarısızlıkta Requirement 13 kısa nedeni, model sunucunun
   listesinde yoksa sonuna " (model sunucunun listesinde yok)" eklenir.

Her adım `name`, `ok`, `code`, `detail` ve `ms` (süre) döndürür. Sohbet adımı Requirement 6–10
kurallarına ve Requirement 17 sınırına tabidir; yer beklemesi adımın süresine sayılır ve süre
dolarsa adım `timeout` ile biter. `record: true` yalnız `public_id` verilip başka bağlantı alanı
gönderilmediğinde kabul edilir ve sonucu (`at` UTC zamanı, `ok`, "Sunucu: ✓; Sohbet modeli: ✓"
biçiminde `summary`) entegrasyona yazar; bu yazma bağlantı değişikliği sayılmaz. Test aktif
bağlantıyı değiştirmez.

Requirement 16: Kayıtlı API anahtarı yalnız kaydedildiği adresin kökenine (şema, ana makine ve port)
gönderilir. Test ve model listesinde `public_id` verilip formda anahtar yoksa, formdaki adresin kökeni
kayıtlı adresinkiyle aynıysa kayıtlı anahtar kullanılır; farklıysa istek anahtarsız gider. Şifreli
değer kiracıya, entegrasyonun `public_id`'sine ve adres kökenine bağlıdır (Requirement 20); satırın
adresi veritabanında doğrudan başka kökene çevrilirse anahtar açılmaz ve sonuç `key_unreadable` olur.

Requirement 17: Süreçte aynı anda süren `/chat/completions` isteği sayısı, analiz, bağlantı testi ve
ölçüm dahil, `DWHNAVIGATOR_LLM_MAX_CONCURRENT_CALLS` değerini aşmaz (Decision 11). Yer bekleyen
çağrı geliş sırasıyla bekler; bekleme iptal edilebilir ve iptal edilen bekleme istek göndermez;
bekleme süresi çağrı özetine `wait_ms` olarak yazılır. `/models` istekleri (sağlık denetimi, model
listesi, envanter) bu sınıra girmez; envanter kendi içinde en çok 8 paralel istek yapar. Analizlerin
kuyruğu ve eşzamanlılık sınırı bu sınırın yerine geçmez ve
[question-analysis](../004-question-analysis/PRD.md) PRD'sindedir. Backend tek kopya çalıştığı için süreç sınırı aynı zamanda dağıtım geneli sınırdır.

Requirement 18: Port her sohbet çağrısı için (uyarlama ve onarım tekrarlarıyla birlikte tek çağrı)
içerik taşımayan bir çağrı özeti döndürür: `purpose` (`analysis`, `connection_test` ya da
`evaluation`), entegrasyonun `public_id`'si, `model`, `started_at` (UTC), `wait_ms`, `duration_ms`,
`outcome` (`ok` ya da Requirement 13 sınıfı), son `http_status`, `requests` (gönderilen istek
sayısı), `adaptations` (bırakılan özellikler, sırasıyla), `repaired` (onarım istendi mi),
`prompt_tokens` ve `completion_tokens`. Sağlık denetimi `outcome`, `http_status`, `duration_ms` ve
`cached` (önbellekten mi) döndürür. Özette istem, soru, şema, model yanıtı, sunucu hata gövdesi,
adres, anahtar ve başlık yoktur. Analizdeki çağrı özetlerinin tek kalıcı yeri analiz kaydıdır: hangi
adıma yazıldıkları [question-analysis](../004-question-analysis/PRD.md), veri modeli ve gösterimi
[analysis-records](../008-analysis-records/PRD.md) PRD'sindedir; analiz kaydındaki model kullanımı
toplamları (çağrı, giriş ve çıkış token'ı) bu özetlerden türetilir. Bu PRD çağrı özeti için tablo
kurmaz; analiz dışındaki çağrılar (bağlantı testi, model listesi, envanter, sağlık denetimi)
PostgreSQL'e yazılmaz, tek istisna testin `record` sonucudur (Decision 8). Ölçüm betiğinin çağrı
özetleriyle ne yapacağı [quality-evaluation](../010-quality-evaluation/PRD.md) PRD'sindedir.

Requirement 19: Yönetim ekranının **Yapay zekâ** sayfası React'te kaynaktaki işlev ve görünümle
(kaynak `admin.html` ile birebir aynı; [search-settings](../009-search-settings/PRD.md) Decision 11)
yeniden kurulur; kaynak `admin.html` `AI` bölümündeki bütün görünür metinler aynen
`app/frontend/src/locales/tr.json`'a taşınır:

- **Başlık:** "Yapay zekâ", "Cevabı kurum içi sohbet modeli yazar; bu rolü tek aktif entegrasyon
  üstlenir, değişiklikler anında geçerli." ve "Model envanteri" düğmesi.
- **Etkin model kartı:** "Etkin sohbet modeli · talebi okur, cevabı yazar", model adı ya da "Bağlı
  model yok"; "{ad} üzerinden · yanıt veriyor", "{ad} — yanıt vermiyor: {neden}" ya da "Model
  bağlanana kadar sorular “Analiz yapılamadı” cevabını alır."; aktif model varsa "Test et" ve her
  zaman "Yeni entegrasyon".
- **Entegrasyon kartları** ("Entegrasyonlar · N"): ad, adres, aktif/pasif anahtarı; Aktif/Pasif,
  Anahtar kayıtlı/Anahtarsız ve "✓ Test {zaman}", "✗ Test {zaman}" ya da "Test edilmedi"
  etiketleri; sohbet modeli ya da "Model seçilmedi — “Modeller” ya da “Düzenle” ile seçin."; "Test
  et", "Modeller" (Model, Bağlam, Durum ve "Sohbet modeli yap" sütunlu tablo), "Düzenle", "Sil".
  Boş listede "Henüz entegrasyon yok; OpenAI uyumlu bir model sunucusu ekleyin (vLLM, Ollama, LM
  Studio, llama.cpp…)." ve "Entegrasyon ekle".
- **Düzenleyici çekmece** ("Yeni entegrasyon" ya da "{ad} — düzenle"): 1 Bağlantı (Ad, API adresi,
  maskeli API anahtarı "•••••• kayıtlı — değiştirmek için yazın", "Kayıtlı anahtarı sil", "Bağlan ve
  modelleri getir"); 2 Model (öneri listeli sohbet modeli; sunucu tek model bildirirse kendiliğinden
  seçilir; "Gelişmiş" altında Sıcaklık, Zaman aşımı (sn), Düşünme modu, Seed); 3 Test ("Bu
  ayarlarla test et", adımlar ✓/✗, ayrıntı ve süreyle); alt çubukta "Kaydedince aktif et" (yeni
  kayıtta işaretli) ya da "Aktif kalsın", "Vazgeç", "Ekle"/"Kaydet". Düzenlemede modeller
  kendiliğinden getirilir.
- **Model envanteri çekmecesi:** "Bütün entegrasyonların sunucularında şu an sunulan modeller",
  Türkçe katlamayla süzen "Model ara…" kutusu, Model / Entegrasyon / Bağlam sütunları, pasif ve
  "Sohbet" etiketleri, ulaşılamayan sunucu için "{ad}: {neden}" uyarısı.
- **Onaylar ve bildirimler:** Çakışma ("“{ad}” (Sohbet modeli) şu an bu rolde aktif. Pasif yapılıp
  yerine bu entegrasyon kullanılsın mı?") ve silme ("“{ad}” entegrasyonu silinsin mi?", aktifse
  "Aktif olduğu için sohbet modeli boşta kalır; sorular cevaplanamaz.") onayları kaynaktaki gibi
  tarayıcının onay penceresiyle (`confirm`) sorulur; bildirimler kaynaktakiyle aynıdır ("Entegrasyon
  eklendi", "Aktif edildi" … "uygulama yeni bağlantıyla çalışıyor.", "Test başarılı",
  "Kaydedilemedi" vb.).
- **Değişenler:** "Kurum dışı adres" etiketi ve "Bu bağlantı ayar dosyasından okundu…" iletisi
  kalkar. `nonprod`'da API adresi yardım metni "/v1 ile biten https:// adresi." olur. Şifreleme
  anahtarı yoksa anahtar alanı kapalıdır ve "Bu ortamda API anahtarı saklanamıyor; şifreleme anahtarı
  tanımlı değil." yazar. Kayıtta `key_cleared` dönerse "Adres değiştiği için kayıtlı anahtar
  silindi." bildirimi çıkar.

Sayfa `kullanici`ya görünmez; görünmemek yetki denetimi değildir (Requirement 21). Kenar çubuğu
rozeti, sistem durumu satırı ve Ctrl K komut paletindeki "Yeni model entegrasyonu" ile "Model
envanteri" eylemleri [search-settings](../009-search-settings/PRD.md) PRD'sinin sahip olduğu yönetim
ekranı kabuğundadır; bu sayfa düzenleyiciyi ve envanteri dışarıdan açılabilir kılar. Genel bakıştaki
"Sohbet modeli" kartı ve "Sohbet modelini bağlayın" kurulum adımı
[analysis-records](../008-analysis-records/PRD.md) PRD'sindedir ve bu PRD'nin Requirement 12
nesnesini kullanır.

Requirement 20: API anahtarı kabul edilmiş `cryptography` paketinin AES-256-GCM (doğrulamalı
şifreleme) uygulamasıyla, her değer için rastgele 96 bitlik tek kullanımlık sayıyla şifrelenir ve
`v1.<tek kullanımlık sayı>.<şifreli değer>` biçiminde saklanır (parçalar, adreslerde de bozulmayan
base64 metin yazımıyla). Şifreleme bağlamı kiracı, entegrasyonun `public_id`'si ve adres kökenidir;
başka satıra ya da başka kökene taşınan değer açılmaz. Şifreleme anahtarı
`DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY`'dir; veritabanına, loga ve yanıta yazılmaz. Yanlış anahtar,
değiştirilmiş değer ve başka bağlam aynı biçimde `key_unreadable` olur; şifreleme kütüphanesinin
iletisi dışarı çıkmaz. Anahtar döndürme (eski değerleri yeni anahtarla yeniden şifreleme) kapsam
dışıdır; şifreleme anahtarı değişirse yönetici API anahtarını yeniden girer (Decision 10).

Requirement 21: Bu PRD'nin bütün uçları geçerli oturum ve `yonetici` rolü ister: oturumsuz istek
401, `kullanici` 403 alır; süper yönetici merkezi geçişle girer
([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)). Denetim hem
yönlendiricide hem hizmette yapılır. `PUT` aynı gövdeyle tekrarlanınca aynı sonucu verir ve değişmeyen
satırı yazmaz. Aktif etme yarışını veritabanı kısıtı belirler (Requirement 4); aynı adla eşzamanlı
iki oluşturmadan biri 409 `llm_integration_name_taken` alır; diğer alan güncellemelerinde son yazan
geçerlidir. Silinmiş ya da bulunmayan entegrasyona her istek 404 `llm_integration_not_found` alır.

Requirement 22: Soru metnine, istemlere, şemaya, model yanıtına ve sunucunun hata gövdesine konan
ayırt edici bir işaret dizesi uygulama logunda, OpenTelemetry sinyallerinde, API hata yanıtlarında ve
çağrı özetlerinde bulunmaz. API anahtarı hiçbir API yanıtında, logda, izde ve PostgreSQL'de açık
metin olarak bulunmaz. Analiz kaydındaki soru ve cevap metni ürün verisidir ve
[analysis-records](../008-analysis-records/PRD.md) PRD'sinin konusudur.

## API sözleşmesi

Bütün uçlar `/api/dwhnavigator/v1` altındadır ve geçerli oturum ister. OpenAPI dosyası (API'nin
makinece okunan tanımı) `specs/openapi/dwhnavigator-api.yaml` ve üretilmiş ön yüz tipleri aynı
değişiklikte güncellenir. Hata gövdesi tek hata zarfıdır: `{"detail":{"code":"...","message":"..."}}`;
istek kimliği `x-request-id` başlığıyla döner. Bozuk gövde ya da bilinmeyen alan 422
`invalid_request` alır.

| Uç | Yetki | İstek özü | Başarı | Hatalar |
|---|---|---|---|---|
| `GET /llm-integrations` | `yonetici` | — | 200: `items[]` (`public_id`, `name`, `endpoint`, `has_key`, `active`, `chat_model`, `temperature`, `timeout_seconds`, `reasoning_effort`, `seed`, `last_test` {`at`, `ok`, `summary`} ya da `null`, `created_at`, `updated_at`; oluşturma sırasıyla), `total`, `active` ({`public_id`, `name`, `model`} ya da `null`), `model_state` (Requirement 12), `environment` (`local`/`nonprod`), `accepts_http`, `key_storage` (anahtar saklanabilir mi) | 401, 403 |
| `POST /llm-integrations` | `yonetici` | `name`, `endpoint`; isteğe bağlı `api_key`, `chat_model`, `temperature`, `timeout_seconds`, `reasoning_effort`, `seed`, `activate`, `replace` | 201: `item` ve `GET` yanıtının alanları | 401, 403, 409 (`llm_integration_name_taken`, `llm_integration_limit`, `llm_chat_role_taken`), 422 (`llm_integration_invalid`, `llm_endpoint_unresolved`, `llm_endpoint_not_private`, `llm_chat_model_required`, `llm_key_storage_unavailable`) |
| `PUT /llm-integrations/{public_id}` | `yonetici` | kısmi alanlar; `api_key` yok = koru, `""` = sil; isteğe bağlı `activate`, `replace` | 200: `item`, `key_cleared`, `GET` yanıtının alanları | 401, 403, 404 `llm_integration_not_found`, 409 ve 422 (`POST` ile aynı) |
| `PUT /llm-integrations/{public_id}/active` | `yonetici` | `active`, `replace` | 200: `GET` yanıtının alanları | 401, 403, 404, 409 `llm_chat_role_taken`, 422 `llm_chat_model_required` |
| `DELETE /llm-integrations/{public_id}` | `yonetici` | — | 200: `GET` yanıtının alanları | 401, 403, 404 |
| `POST /llm-integrations/models` | `yonetici` | `public_id` ve/veya `endpoint`, `api_key` | 200: `ok`, `code`, `message`, `models[]` (`id`, `type`, `loaded`, `context`, `owner`, `quant`, `in_use`), `ms`; sunucu hatası `ok: false` ile | 401, 403, 404, 422 `llm_integration_invalid` (adres yoksa "API adresi girilmedi") |
| `GET /llm-integrations/inventory` | `yonetici` | — | 200: `servers[]` (`public_id`, `name`, `active`, `ok`, `code`, `message`, `models[]`) | 401, 403 |
| `POST /llm-integrations/test` | `yonetici` | `public_id` ve/veya bağlantı alanları (`name` yok sayılır), `record` | 200: `ok`, `steps[]` (`name`, `ok`, `code`, `detail`, `ms`); bağlantı hatası `ok: false` ile | 401, 403, 404, 422 (`llm_integration_invalid`; `record` başka alanla gelirse `invalid_request`) |

Test ve model listesi uçları yalnız Requirement 2'nin biçim denetimini istek öncesinde yapar; ad
çözme ve özel ağ denetimi istek sırasında yapılır ve sonucu `ok: false` ile sınıf olarak döner.
Kaynak uçların karşılığı: `GET /api/llm` → `GET /llm-integrations`; `POST /api/llm/save` →
`POST /llm-integrations` ya da `PUT /llm-integrations/{public_id}`; `POST /api/llm/activate` →
`PUT /llm-integrations/{public_id}/active`; `POST /api/llm/delete` → `DELETE`;
`POST /api/llm/models`, `GET /api/llm/inventory` ve `POST /api/llm/test` → aynı adlı uçlar. Ana
ekranın durum ucu (`GET /status`, kaynak `/api/status`)
[question-analysis](../004-question-analysis/PRD.md) PRD'sinindir; bu PRD yalnız içindeki model
durumu nesnesini (Requirement 12) belirler.

## Güvenlik ve yetkilendirme

- Kimlik ve rol [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
  ile gelir; bütün uçlar `yonetici` ister (Requirement 21). Kaynaktaki yönetim parolası
  (`VSA_ADMIN_PASSWORD`, `AdminGuard`) ve "parola yoksa yalnız sunucunun kendisinden" kuralı kalkar.
  Menünün gizlenmesi yetki denetimi değildir.
- **Sunucu üzerinden başka adrese istek (SSRF):** Model listesi, envanter ve bağlantı testi,
  yöneticinin yazdığı adrese backend'den istek yapar. Sınırlar: yalnız `yonetici`; Requirement 10
  özel ağ denetimi (ad çözme ve bağlanılan adres); asıl sınır olarak
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindeki, yalnız model sunucusuna açık ağ çıkış kuralı; yönlendirme izlenmez; yanıt olarak
  yalnız sabit sınıf, model kimlikleri ve test cevabının ilk 40 karakteri döner, sunucu gövdesi
  yankılanmaz. Bu, kaynak `docs/GUVENLIK.md` bulgu 3'teki "yalnız parolayla erişilebilir"
  önleminin yerini alır.
- **API anahtarı:** PostgreSQL'de yalnız şifreli durur (Requirement 20); şifreleme anahtarı
  Runtime Secret'ta olduğu için veritabanı dökümü tek başına anahtarı açmaz. Anahtar ve şifreli
  değeri yanıta, loga, ize ve hata iletisine girmez; doğrulama hatası değeri yankılamaz; kayıtlı
  anahtar başka adres kökenine gönderilmez (Requirement 16). Kaynakta anahtar `data/` biriminde düz
  metindi (`docs/GUVENLIK.md` kalan risk 5).
- **Şifresiz bağlantı:** `http` yalnız `local`'de kabul edilir (Decision 4).
  Şifresiz bağlantıda API anahtarı, soru ve sözlük metni ağda açık gider (kaynak kalan risk 4).
- **Modele giden içerik:** Soru metni ve sözlük içeriği (tablo ve kolon açıklamaları, özetler)
  yalnız kurum içi model sunucusuna gider; `nonprod`'da başka ürünlerle paylaşılan kurum içi RunAI
  ucuna gönderimi proje sahibi onayladı (Decision 18). Sözlük yalnız tanım metinleridir, müşteri
  verisi işlenmez (kaynak kalan risk 6).
- **Değişiklik izi:** Her değişiklik `updated_by` ve `updated_at` sütunlarına ve
  `llm_integration.changed` olayına (yapan kullanıcının `public_id`'si, değişen alan adları) yazılır.

## Veri ve geçiş

Bu PRD PostgreSQL'e tek tablo ekler: `llm_integration`. Tablo kiracının model bağlantılarını tutar.

| Sütun | Anlam |
|---|---|
| `llm_integration_id` | İç kimlik; API'ye çıkmaz |
| `public_id` | Dış kimlik; boş olmayan, benzersiz |
| `tenant_id` | Sahip kiracı; `tenant.tenant_id` dış anahtarı (silme kısıtlı) |
| `name` | Görünen ad (1–100 karakter) |
| `name_key` | Adın Türkçe katlanmış biçimi; silinmemiş satırlarda kiracı içinde benzersiz |
| `endpoint` | Normalleştirilmiş adres (en çok 2048 karakter) |
| `api_key_ciphertext` | API anahtarının `v1.<…>.<…>` biçimindeki AES-256-GCM çıktısı; anahtar yoksa boş. Açık anahtar hiçbir sütunda yoktur |
| `active` | Aktif sohbet modeli mi; kiracıda silinmemiş satırlar arasında en çok bir `true` (kısmi benzersiz dizin); `true` iken `chat_model` boş olamaz (denetim kısıtı) |
| `chat_model` | Sohbet modeli kimliği (en çok 256 karakter; boş olabilir) |
| `temperature` | 0–2 arası ondalık sayı, varsayılan 0 |
| `timeout_seconds` | 5–3600, varsayılan 900 |
| `reasoning_effort` | `none`, `low`, `medium`, `high` ya da boş (gönderme); varsayılan `none`; kod yansıması alan modelindeki sabit küme |
| `seed` | −1 (gönderme) ile 2147483647 arası, varsayılan 42 |
| `last_test_at`, `last_test_ok`, `last_test_summary` | Kaydedilen son test (UTC zaman, sonuç, "Sunucu: ✓; Sohbet modeli: ✓" biçiminde özet); adres ya da model değişince boşalır |
| zorunlu blok | `props`, `created_at`, `updated_at`, `created_by`, `updated_by`, `is_deleted`, `deleted_at`, `deleted_by` (rules/41); silinmemiş satırlar için kısmi dizin |

Aralıklar ve `reasoning_effort` kümesi veritabanında denetim kısıtıdır; tablo ve sütun açıklamaları
veritabanındadır (rules/43). Uygulama satırı silmez, yazılımsal siler ve şifreli anahtarı boşaltır.
Tabloyu tek bir genişletici göç (veritabanı şema değişikliği) kurar; geri alınırsa tablo ve kayıtlı
bağlantılar silinir, analizler bir bağlantı yeniden girilene kadar `not_configured` alır.

Taşınacak eski veri yoktur: kaynak `data/llm_integrations.yaml` düz metin anahtar içerdiği ve
kaynak `data/` dosyalarından veri taşınmadığı için aktarılmaz; `settings.yaml` `llm:` bölümü
okunmaz. Yönetici bağlantıyı ilk kurulumda Yapay zekâ sayfasından girer. Çağrı özetleri için tablo
yoktur (Requirement 18). Uyarlama durumu, sağlık önbelleği ve çağrı sınırı süreç belleğindedir,
kalıcı değildir.

## Gözlemlenebilirlik

- **Log olayları:**
  - `llm.call`: `request_id`, `purpose`, entegrasyonun `public_id`'si, `model`, `outcome`,
    `http_status`, `requests`, `adaptations`, `repaired`, `wait_ms`, `duration_ms`, `prompt_tokens`,
    `completion_tokens`; çağıran verdiyse analizin `public_id`'si.
  - `llm.probe`: `request_id`, `operation` (`health`, `models`, `inventory`), varsa entegrasyonun
    `public_id`'si, `outcome`, `http_status`, `duration_ms`, `cached`.
  - `llm_integration.changed`: `action` (`created`, `updated`, `activated`, `deactivated`,
    `deleted`, `key_cleared`), entegrasyonun `public_id`'si, değişen alan adları (değerleri değil;
    anahtar için yalnız `api_key` adı), işlemi yapan kullanıcının `public_id`'si.
  - `llm_integration.key_unreadable`: entegrasyonun `public_id`'si; aynı bağlantı sürümü için süreç
    başına bir kez.
  - İstisna kayıtları yalnız istisnanın sınıf adını taşır. Hiçbir olayda istem, soru, model yanıtı,
    sunucu hata gövdesi, adres, anahtar ve entegrasyon adı (yöneticinin serbest metni) yoktur.
- **Ölçümler:**
  - `dwhnavigator_llm_calls_total{purpose,outcome}` (sayaç)
  - `dwhnavigator_llm_call_duration_seconds{purpose,outcome}` (süre dağılımı)
  - `dwhnavigator_llm_inflight_calls` ve `dwhnavigator_llm_waiting_calls` (süren ve yer bekleyen
    sohbet isteği sayısı)
  - `dwhnavigator_llm_tokens_total{kind}` (`kind`: `prompt`, `completion`)
  - `dwhnavigator_llm_adaptations_total{feature}` (`feature`: `system_role`, `response_format`,
    `reasoning_effort`, `seed`, `chat_template_kwargs`)
  - `dwhnavigator_llm_probes_total{operation,outcome}`

  Etiket kümeleri sabittir: `purpose` 3 değer, `outcome` `ok` ve Requirement 13'ün 16 sınıfı,
  `operation` 3, `kind` 2, `feature` 5 değer; kümede olmayan değer `other` yazılır. Model,
  entegrasyon, kullanıcı ve analiz kimliği etikete girmez.
- **İz (trace):** Her sohbet çağrısı için `llm chat` aralığı (öznitelikler: `purpose`, `outcome`,
  `http_status`, `requests`, uyarlama sayısı, `repaired`) ve her yoklama için `llm probe` aralığı
  (`operation`, `outcome`, `cached`). Adres, model, istem, yanıt ve hata metni aralığa girmez.
- Ortak kurallar ve saklama süresi
  [application-foundation alanında](../../../application-foundation/DOMAIN.md) tanımlıdır. Tüketen
  testler: `app/backend/tests/unit/test_llm_adapter.py` (ölçüm adları, etiket kümeleri, aralık
  öznitelikleri) ve `app/backend/tests/integration/test_llm_integrations_api.py` (değişiklik
  olayları).

## Dağıtım etkisi

- **Ayarlar:** Requirement 1'deki üç anahtar `app/backend/.env.example` dosyasına (şifreleme anahtarı
  için yalnız "sırdır; yerelde fabrikanın yerel sır üretimi verir, o gelene kadar `app/infra/.env`'e
  yazılır" açıklaması), yerel Compose backend ortam bloğuna
  (`DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY: "${DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY:-}"`, güven dosyası
  ve çağrı sınırı) ve dağıtıma eklenir: şifreleme anahtarı `dwhnavigator-runtime` Runtime Secret'ına,
  sır olmayan iki ayar gerekirse `helm/dwhnavigator/values-project.yaml` `backend.config`'e;
  `python3 scripts/check-config-sync.py` geçer.
- **Secret:** `helm/dwhnavigator/deploy-hooks.sh` `DWHNAVIGATOR_SETTINGS_ENCRYPTION_KEY`'i ilk
  dağıtımda bir kez üretir, sonraki dağıtımlarda kümedekini korur, Azure gizli değişkeni verilirse
  onu kullanır; değer çıktıya, komut argümanına ve Git'e girmez. Kanca
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sinindir.
- **İmaj:** Model sunucusunun sertifikasını imzalayan kurum kök sertifikası backend imajının sistem
  güven deposuna eklenir. `nonprod` RunAI ucunu kullandığı için (Decision 18) bu kök, DWH Code
  Review imajına eklenen `corporate-inference-root.crt` ile aynıdır; dosya dağıtım öncesi parmak
  iziyle doğrulanır. İmaj tanımı
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindedir.
- **Bağımlılık:** `httpx` bugün yalnız geliştirme bağımlılığıdır (`app/backend/requirements-dev.in`);
  çalışma zamanı bağımlılığı olarak `app/backend/requirements.in`'e ve `dependency-admission.json`
  kabul kaydına girer. `cryptography` bugün `PyJWT[crypto]` üzerinden dolaylı gelir; doğrudan
  kullanıldığı için `requirements.in`'e açıkça yazılır ve kabul kaydına girer.
  `app/backend/requirements-llm.in` (LangChain) etkinleştirilmez (Decision 5).
- **Ağ çıkışı:** Backend model için yalnız seçilen model sunucusunun adresine ve portuna çıkabilir.
  `nonprod`'daki RunAI ucu için DWH Code Review'da gözlenen adres `10.14.3.99/32`, TCP 443'tür ve
  dağıtım öncesi yeniden doğrulanır (kubernetes-delivery'deki bekleyen bilgi). Kural
  (kubernetes-delivery Requirement 10) ve yerel Compose'un model sunucusuna erişimi
  (`app/infra/.env`'de `COMPOSE_PROFILES=local-egress` ile açılan yerel çıkış kapısı,
  kubernetes-delivery Requirement 17)
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindedir; bu kural bu PRD'nin Requirement 10'undaki uygulama içi denetimin asıl sınırıdır.
- **Göç:** `llm_integration` tablosu göç işiyle (Job) kurulur; çalışma zamanı veritabanı rolü tabloda
  yalnız veri okur ve yazar.
- **Kaldırılanlar:** Kaynak `data/llm_integrations.yaml`, `settings.yaml` `llm:` bölümü ve
  `docs/KURULUM.md` §5'teki "dosyaya yazıp yeniden başlat" yolu.

## Test stratejisi

- **Birim:** Requirement 2 alan sınırları ve iletileri; adres normalleştirme ve köken karşılaştırması;
  Ortama göre şema kuralı; şifreleme (yanlış anahtar, değiştirilmiş değer, başka satır, başka köken,
  anahtar biçimi); Requirement 4 kuralları; gövde kurucusunun sabit örneklerle bayt eşitliği;
  Requirement 7 uyarlama sırası ve 3 sınırı; `parse_json_reply` (kaynak `tests/test_llm.py`
  örnekleri); Requirement 13 sınıf ve metin tablosu ve yoklama iletisi; sağlık
  önbelleği (sahte saatle 30 sn, bağlantı değişince boşalma); ayar doğrulaması.
- **Fark testi:** Kaynak `vsa` paketi (`76e21a3`) test ortamına ayrıca kurulur. Kaynak
  `OpenAICompatibleClient` ve hedef bağdaştırıcı, gelen istekleri bayt olarak kaydeden aynı sahte
  sunucuya (gerçek ağ bağlantısıyla, `127.0.0.1` adresinde) aynı istem, şema ve `max_tokens` ile
  gider.
  Senaryolar: düz yanıt; kod çitli ve `<think>`/`<thought>` bloklu yanıt; sistem, şema, düşünme ve
  seed reddi (tek tek ve art arda, kaynak `tests/test_client.py` metinleriyle); JSON olmayan ilk yanıt
  ve onarım; iki kez JSON olmayan yanıt; `choices` yok; 401; 500; 504; bağlam aşımı metinli 400;
  `seed` −1 ve boş `reasoning_effort`. Sunucunun aldığı gövde dizisi bayt bayt aynı, dönen JSON
  nesnesi eşit olmalıdır. Tek beyan edilmiş fark, `reasoning_effort: "none"` reddinden sonraki
  isteklerdeki `chat_template_kwargs` alanıdır (Requirement 7 kural 3); kaynak kaydı değişmez, fark
  testte kaynağın baytlarına bu alan eklenerek karşılaştırılır. İkinci beyan edilmiş fark uzunluk
  sınırında kesilen yanıttır (Decision 20): `finish_reason: "length"` taşıyan JSON olmayan yanıtta
  hedefin sunucusu yalnız ilk isteği alır, kaynağınki onarım isteğini de; karşılaştırma kaynağın
  ilk isteğiyle yapılır. Kesilmiş ama geçerli JSON yanıtı ve `finish_reason`'sız JSON olmayan yanıt
  senaryoları kaynakla farksızdır. Düşünme kapatma yolu (ret, alanın
  reddi, hatırlanması, `low`/`medium`/`high`'ın değişmemesi) birim testlerindedir. Analiz sebebi
  metinleri [question-analysis](../004-question-analysis/PRD.md) Requirement 5'in testlerindedir.
- **Sahte sunucuyla gerçek ağ bağlantısı:** askıda kalan sunucu (zaman aşımı), 4 MiB aşımı, 307
  yönlendirmesi, test sertifika otoritesiyle imzalanmamış sertifika, ortamda `HTTPS_PROXY`
  tanımlıyken doğrudan bağlantı, genel adrese çözülen ad ve bağlantı anında adres değiştiren sahte
  ad çözücü (sunucu gövde almaz), kapalı port (sağlık denetimi 1 sn altı), yanıt vermeyen adres (6 sn
  altı), durdurmada bağlantının 1 sn içinde kapanması, askıda kalan sunucuda model listesinin 10,
  bağlantı testinin 40, envanterin 50 saniyede bitmesi (Requirement 9).
- **Eşzamanlılık:** sınır 2 verilip 5 eşzamanlı çağıranda sahte sunucunun gördüğü en yüksek
  eşzamanlı sohbet isteği 2'dir; ayarsız varsayılan 5'tir; bekleyen çağrı iptal edilince sunucuya istek gitmez; envanterde en çok 8 eşzamanlı `/models`
  isteği görülür.
- **API ve PostgreSQL tümleşik:** oluşturma, güncelleme, aktif etme, silme, model listesi, envanter ve
  test uçları gerçek uygulama üzerinden; roller (oturumsuz 401, `kullanici` 403, süper yönetici
  geçer); 409 ve 422 durumları; eşzamanlı iki aktif etmede ve aynı adla iki oluşturmada birinin 409
  alması; yazılımsal silmede şifreli anahtarın boşalması; köken değişince anahtarın silinmesi;
  şifreleme anahtarı yokken anahtar kaydının reddi; tabloda yalnız şifreli değer; kayıttan sonra
  yeniden başlatmadan sonraki analizin yeni bağlantıyı kullanması (sahte port ile); göçün uygulanıp
  geri alınması; zorunlu sütun ve açıklama kapıları.
- **Veri sızıntısı:** Soruya, istemlere, şemaya, sahte model yanıtına ve sahte sunucu hata gövdesine
  konan işaret dizesi log çıktısında, bellek içi OpenTelemetry dışa aktarıcısında, API hata
  yanıtlarında ve çağrı özetlerinde aranır; API anahtarı değeri yanıtlarda, logda ve tabloda aranır.
- **Ön yüz:** Vitest ile kart durumları, düzenleyici akışı (modelleri getirme, tek modelin
  kendiliğinden seçilmesi, test adımları), çakışma ve silme onayları, anahtar alanının "kayıtlı"
  görünümü ve silme seçeneği, şifreleme anahtarı yokken kapalı anahtar alanı, `nonprod` yardım metni,
  envanter süzgeci, `kullanici`'de sayfanın görünmemesi; tarayıcı testiyle ekle → test et → aktif et
  akışı (rules/14).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

Bu yetenek vektör araması ve gömme kullanmaz; kaynak vektör aramasını ADR-039 ile kaldırdı.

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 1–5, 16, 20 ve 21 birim ve
  PostgreSQL tümleşik testleri geçer: alan sınırları ve iletileri, tek aktiflik kısıtı (eşzamanlı iki
  aktif etmede biri 409), köken değişince anahtarın silinmesi, şifreleme anahtarı yokken anahtar
  kaydının 422 alması, tabloda yalnız şifreli değer, roller, göçün uygulanıp geri alınması, zorunlu
  sütun ve açıklama kapıları; `python3 scripts/check-config-sync.py` geçer.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 6, 7, 8 ve 13 fark testleri kaynak
  `76e21a3` paketiyle yan yana geçer: Test stratejisindeki her senaryoda sahte sunucunun aldığı istek
  gövdeleri, Requirement 6'daki iki beyan edilmiş fark dışında, bayt bayt aynıdır, dönen JSON
  nesnesi eşittir, hata sınıfı ve neden metni Requirement 13 tablosundakidir. `finish_reason:
  "length"` taşıyan JSON olmayan yanıtta sunucu tek istek alır, sonuç `output_truncated`'dır ve
  çağrı özetinde `repaired` yanlıştır.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Requirement 9, 10, 11, 12 ve 17 sahte sunucu
  testleri geçer: özel ağ dışı adreste ve güvenilmeyen sertifikada sunucu istek gövdesi almaz;
  yönlendirme izlenmez; 4 MiB aşımı kesilir; ortam vekili kullanılmaz; sağlık denetimi kapalı portta
  1 saniyenin, yanıt vermeyen adreste 6 saniyenin altında biter ve 30 saniye önbellekten döner;
  durdurmada bağlantı 1 saniye içinde kapanır; sınır 2 iken 5 eşzamanlı çağıranda sunucunun gördüğü
  eşzamanlı sohbet isteği 2'yi aşmaz; ayarsız sınır 5'tir.
- [ ] Acceptance 4: L1 — Otomatik testlerden geçti: Requirement 14, 15, 18 ve 22 testleri geçer:
  envanter ve test adımları; işaret dizesi log çıktısında, OpenTelemetry sinyallerinde, API hata
  yanıtlarında ve çağrı özetlerinde bulunmaz; Gözlemlenebilirlik bölümündeki ölçüm adları ve etiket
  kümeleri doğrulanır; tam kalite kapısı geçer.
- [ ] Acceptance 5: L1 — Otomatik testlerden geçti: Requirement 19 ön yüz testleri geçer; OpenAPI
  dosyasının ve üretilmiş tiplerin güncelliği doğrulanır.
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı: Yerel Compose ve PostgreSQL ile, yerel
  çıkış kapısı açıkken (kubernetes-delivery Requirement 17), yönetici
  tarayıcıdan geliştiricinin erişebildiği kurum içi bir model sunucusunu ekler, modelleri getirir,
  iki test adımını ✓ görür ve aktif eder; ana ekranda bir soru analistin cevabıyla tamamlanır ve
  analiz kaydında model, süre ve token sayılı çağrı özetleri görünür; ikinci bir entegrasyon aktif
  edilince yeniden başlatmadan sonraki soru yeni modeli kullanır; model sunucusuna erişim kesilince
  sonraki soru 6 saniyenin altında "Analiz yapılamadı: Model sunucusuna ulaşılamadı: …" ile biter;
  API anahtarı girilen entegrasyonun satırında yalnız şifreli değer bulunur (Requirement 3, 5, 12,
  15, 18, 19).
- [ ] Acceptance 7: L2 — Gerçek istemci/ortamda doğrulandı: `nonprod` ayarlarıyla
  (`DWHNAVIGATOR_ENVIRONMENT=staging`) yerelde çalışan sürümde `http` adresli entegrasyon 422 alır,
  `https` adresli entegrasyon kaydedilir ve test edilir; şifreleme anahtarı verilmeden API anahtarı
  kaydı 422 alır, anahtarsız entegrasyonla bir soru tamamlanır (Requirement 1–3, Decision 4).
- [ ] Acceptance 8: L2 — Gerçek istemci/ortamda doğrulandı (nonprod): KT Rancher `vibecode-test`
  kümesindeki sürümde yönetici RunAI ucunu
  (`https://runai.gpudtx.kuveytturk.com.tr/inference/qwen36-35b-a3b-fp8/v1`, Decision 18) ekler,
  test eder ve aktif eder; bir soru kümede tamamlanır; ağ çıkış kuralının izin vermediği bir özel
  adrese bağlantı testi `timeout` ya da `connect_error` verir. Kümeye dağıtım ayrı kullanıcı
  talimatı ister.
- [ ] Acceptance 9: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı entegrasyonlarla çalıştırılır; Yapay zekâ sayfası, düzenleyici
  çekmecenin üç adımı ve model envanteri çekmecesinin ekran görüntüleri masaüstü (1440×900) ve
  telefon genişliğinde (390×844 piksel) yan yana karşılaştırılır. Fark yalnız Requirement 19'daki
  "Değişenler" maddesinde ve fabrikanın zorunlu kıldığı oturum alanında kabul edilir (Requirement
  19).

## Kararlar

Decision 5: Bağdaştırıcı doğrudan `httpx` (HTTP istemci kütüphanesi) ile yazılır; LangChain
(`requirements-llm.in`) etkinleştirilmez. Gerekçe: kaynak davranış tek bir akışsız istek, kaynağa
özgü özellik uyarlaması ve JSON onarımıdır; hazır bir entegrasyon bu baytları ve kuralları korumaz.
DWH Code Review aynı yolu seçti.

Decision 6: İstek gövdesini bağdaştırıcının kendisi `json.dumps` varsayılanıyla yazar ve hazır bayt
olarak gönderir; `httpx`'in gövdeyi kendisinin yazdığı yol kullanılmaz. Gerekçe: o yol gövdeyi farklı
ayraç ve harf kaçışıyla yazar; model aynı içeriği görse de ölçülmüş davranışın kanıtı baytları
karşılaştıran fark testidir.

Decision 7: Yeniden deneme yoktur (kaynakla aynı). Gerekçe: okuma süresi 900 saniyedir ve bir
yeniden deneme soruyu 15 dakika daha bekletir; ölü sunucuyu sağlık denetimi yakalar; kullanıcı soruyu
"Yeniden analiz et" ile yeniden çalıştırabilir.

Decision 8: Çağrı özetinin tek kalıcı yeri analiz kaydıdır; bu PRD çağrı tablosu kurmaz ve analiz
dışındaki çağrıları PostgreSQL'e yazmaz. Gerekçe: kaynakta da model çağrıları analiz kaydının
adımlarıydı; ayrı bir tablo aynı bilgiyi iki yerde tutardı. Bağlantı
testi, model listesi ve sağlık denetimi işletim için log olayı ve ölçümle izlenir.

Decision 9: Kayıtlı API anahtarı adres kökenine bağlıdır: köken değişirse yeni anahtar girilmedikçe
silinir, testte başka kökene gönderilmez, şifreleme bağlamı kökeni içerir. Gerekçe: kaynakta adres
değiştirilip test edilince kayıtlı anahtar yeni adrese gidiyordu; yönetici hesabını ele geçiren biri
anahtarı kendi sunucusuna yönlendirip okuyabilirdi. DWH Code Review'ın SQL Server parolası için aynı
kuralı vardır.

Decision 10: Anahtar şifrelemesi DWH Code Review'daki yapıyla aynıdır; şifreleme anahtarını
`nonprod`'da dağıtım kancası bir kez üretir. Şifreleme anahtarı yoksa API anahtarı saklanmaz (kapalı
taraf), anahtarsız bağlantılar çalışır. Yerelde şifreleme anahtarını fabrikanın yerel sır üretimi
verir (fabrika bağımlılığı,
[kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Requirement 17); o gelene kadar geliştirici Git'in yok saydığı `app/infra/.env` dosyasına yazar.
Gerekçe: kurum içi sunucuların çoğu (ekibin LM Studio'su, RunAI ucu) anahtar istemez; anahtar
yokken de anahtarsız bağlantıyla çalışılabilir.

Decision 11: Süreç geneli sohbet çağrısı sınırının varsayılanı 5'tir. Gerekçe: farklı soranların
analizleri paralel yürür ve aynı anda en çok 4 analiz vardır
([question-analysis](../004-question-analysis/PRD.md) Decision 27); bir analizin çağrıları ardışık
olduğu için her analiz bir yer kullanır, beşinci yer bir bağlantı testinin analizlerle aynı anda
yapılmasına yeter. Model sunucusu istekleri kendisi sıraya koyuyorsa (örneğin paralel isteği kapalı
bir LM Studio) uygulamadaki paralellik sunucuda seri yanıtlanır. `nonprod` değeri RunAI kapasite
sahibinin isteğiyle `values-project.yaml`'dan değiştirilebilir.

Decision 12: Uyarlama durumu bağlantı alanlarına bağlıdır; sözlük içe aktarma ve arama ayarı
değişikliği onu sıfırlamaz. Gerekçe: hedefte motor yeniden kurulmaz; kaynaktaki sıfırlanma yalnız
reddedilecek bir isteği yeniden göndermekti, başarılı istek gövdesi aynıdır.

Decision 13: Hata nedenleri sabit sınıflardan üretilir; sunucunun hata metni gösterilmez, loga ve
kayda yazılmaz. Gerekçe: kaynakta sunucu metni (istemin parçalarını yankılayabilir), adres ve
istisna metni kullanıcıya ve loga gidiyordu; kaynağın sade Türkçe nedenleri (bağlantı reddi, ad
çözülemedi, zaman aşımı, bağlam penceresi) sınıf olarak korunur.

Decision 14: Sağlık denetimi kaynaktaki sürelerle kalır (5 saniye, 30 saniye önbellek); önbellek
adres yerine bağlantıya bağlıdır ve bağlantı değişince boşalır. Gerekçe: ADR-034 "ölü sunucu
beklenmez"; yönetici anahtarı ya da adresi düzeltince eski "yanıt vermiyor" sonucu 30 saniye
sürmemelidir.

Decision 15: "Kurum dışı adres" uyarısının yerini yasak alır. Gerekçe: alanın değişmezi "Model
yalnız kurum içindedir"; kaynak yalnız uyarıyordu ve adı çözmediği için kurum içi gibi görünen bir ad
dış adrese çözülebiliyordu.

Decision 16: Yürürlükteki bağlantı her analizde PostgreSQL'den okunur; bellekte ayrı önbellek ya da
değişiklik bildirimi kurulmaz. Gerekçe: analiz dakikalar sürer, tek satırlık okuma bunun yanında
önemsizdir ve değişikliğin ne zaman geçerli olduğu kesinleşir (sonraki analiz).

Decision 17: Kiracı başına en çok 50 entegrasyon tanımlanır. Gerekçe: liste sayfalanmadan `total`
ile döner ve envanter her sunucuya istek yapar; ekip birkaç sunucu kullanır.

Decision 18: `nonprod`'un sohbet modeli kurum içi RunAI ucundaki `qwen36-35b-a3b-fp8`'dir
(`https://runai.gpudtx.kuveytturk.com.tr/inference/qwen36-35b-a3b-fp8/v1`; şifreli ve anahtarsız;
DWH Code Review ve Grafoword'ün `nonprod`'da kullandığı uç). Soru metni ve sözlük içeriğinin bu
paylaşılan kurum içi uca gönderilmesini proje sahibi onayladı. `nonprod` iş birimlerine açılmadan
önce geliştirici bu modeli [quality-evaluation](../010-quality-evaluation/PRD.md) PRD'sindeki altın
set ve büyük referans setle ölçer; sonuç kaynağın `gemma-4-31b` ölçümünün (294 soruda yaklaşık
%89,8) gerisinde kalırsa model seçimi yeniden proje sahibine gelir. Gerekçe: ölçülmüş model ekibin
DGX Spark sunucusundaki `gemma-4-31b`'dir ama o sunucu şifresiz `http` kullanır ve kümeden erişimi
bilinmez; RunAI ucu şifreli, anahtarsız ve kümeden kullanılmaktadır.

Decision 19: `reasoning_effort: "none"` reddedilince yeniden gönderilen istek düşünmeyi
`chat_template_kwargs: {"enable_thinking": false}` ile kapatır; sunucu bu alanı da reddederse o da
bırakılır ve bağlantı için hatırlanır (Requirement 7 kural 3 ve 5). İlk istek kaynakla bayt bayt aynı
kalır. Gerekçe: `nonprod`'daki RunAI vLLM'i Qwen modelinde `"none"`'ı 400 ile reddeder, `low`
düşünmeyi kapatmaz ve kaynağın uyarlaması alanı bırakınca düşünme açık kalır; bağlantı testi ve
analizler "model geçerli JSON üretmedi" ile biter. Ek alan yalnız sunucu düşünme kapatmayı
reddettiğinde gider, bu yüzden kaynağın ölçüldüğü sunucularda gövde değişmez. Karar geliştiricinindir
(2026-10-09).

Decision 20: Uzunluk sınırında kesilen geçersiz yanıt (`finish_reason: "length"`) onarılmak
istenmez ve `output_truncated` sınıfıyla biter. Gerekçe: onarım isteği aynı `max_tokens` sınırıyla
gider, bütün istemi (analistin 1. adımında yaklaşık 48 bin token'lık tablo kataloğunu) yeniden
gönderir ve yine kesilir; kaynakta bu durum giriş token'ını iki katına çıkarıp "model geçerli JSON
üretmedi" ile bitiyor, gerçek neden (yanıt bütçesinin yetmemesi) görünmüyordu. `max_tokens`
değerleri ve istemler değişmez; bu yüzden cevap kalitesi ölçümü gerekmez. Kesilmiş ama geçerli JSON
yanıtı kaynaktaki gibi kabul edilir. Karar proje sahibinindir (2026-11-04).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Ölçülmemiş model:** `nonprod` modeli (`qwen36-35b-a3b-fp8`) ölçülmüş modelden (`gemma-4-31b`)
  farklıdır ve bu modelle hiç ölçülmedi; cevap kalitesi kaynaktakinden düşük olabilir (kaynağın
  küçük altın setinde başka bir Qwen modeli `qwen3.8-27b` ilk sıra isabetinde 0,625'te kaldı,
  `gemma-4-31b` 0,875). Ölçüm iş birimlerine açılmadan önce yapılır (Decision 18). Fark testleri
  yalnız kodun aynı davrandığını kanıtlar, modelin kalitesini değil.
- **Düşünen model:** RunAI'deki Qwen modeli cevaptan önce gizli akıl yürütme yazan bir modeldir;
  düşünme açık kalırsa 1. adımın 2500 token'lık (modelin metin birimi) ve bağlantı testinin 60
  token'lık bütçesini tüketir ve sonuç `output_truncated` ("model cevabı uzunluk sınırında
  kesildi") olur; sunucu `finish_reason` bildirmezse `invalid_json`. Requirement 7 kural 3
  düşünmeyi `chat_template_kwargs` ile kapatır (Decision 19); bağlantıda `low`, `medium` ya da
  `high` seçilirse düşünme açık kalır ve aynı risk sürer. Başka bir sunucu bu alanı reddetmeden yok
  sayarsa da risk sürer.
- **Bağlam penceresi:** Analistin 1. adımı yaklaşık 70 bin token'lık tablo kataloğu gönderir;
  seçilen modelin bağlam penceresi yetmezse her soru `context_exceeded` ile biter. RunAI modelinin
  bağlam penceresi bekleyen bilgidir ([question-analysis](../004-question-analysis/PRD.md) Riskler).
- **Uzun bekleme:** Okuma süresi 900 saniyedir ve yeniden deneme yoktur; paylaşılan uçta yoğunlukta
  iki adımlı bir soru 30 dakikaya kadar sürebilir ya da zaman aşımıyla bitebilir.
- **Soğuk model:** Model sunucusu modeli ilk istekte belleğe yüklüyorsa (kaynaktaki 180 saniyelik test
  payının nedeni) bağlantı testinin sohbet adımı 30 saniyede `timeout` verebilir; yönetici testi model
  yüklendikten sonra tekrarlar.
- **Yönetici yetkisi:** `yonetici` bağlantıyı başka bir kurum içi sunucuya çevirip bütün soruları ve
  sözlük içeriğini oraya gönderebilir. Sınır, yalnız seçilen model sunucusuna açık ağ çıkış kuralıdır;
  değişiklik `llm_integration.changed` olayında yapan kişiyle görünür.
- **Anahtar kaybı:** Şifreleme anahtarı silinir ya da değişirse kayıtlı API anahtarları açılmaz;
  anahtarlı bağlantıyla analizler, yönetici anahtarı yeniden girene kadar `key_unreadable` ile biter.
  Anahtarsız uçlar etkilenmez.
- **Adres değişimi:** Model sunucusunun adresi değişirse daraltılmış ağ çıkış kuralı çağrıları keser;
  adres her dağıtımda doğrulanmalıdır.
- **Sertifika:** Model sunucusunun sertifikası imajdaki kurum kök sertifikasıyla doğrulanamazsa (kök
  değişir ya da süresi dolar) bütün çağrılar `tls_error` verir; imaj yenilenmelidir.
- **Tek kopya varsayımı:** Çağrı sınırı, uyarlama durumu ve sağlık önbelleği süreç belleğindedir;
  backend birden çok kopyayla çalıştırılırsa sınır kopya başına olur.
- **Davranış farkı:** Kurum dışı adresler (kaynakta yalnız uyarı) ve `nonprod`'da `http` artık
  reddedilir; kaynakta bulut modelleriyle yapılan denemeler hedefte yapılamaz. Bu bilinçli bir
  kısıttır.
