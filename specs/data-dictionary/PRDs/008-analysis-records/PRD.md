# PRD — analysis-records

Status: Accepted

Version: 1.0.2

Acceptance date: 2026-10-08

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

Her analiz işi — tek soru ya da toplu aramanın bir terimi — veritabanında bir **analiz kaydıdır**.
Kayıt iş kabul edilince açılır, iş bitince sonucu, tam cevabı, adımları ve süreleriyle tamamlanır:
kimin, ne zaman, hangi soruyu sorduğu; cevabı kimin yazdığı; sonuç, önerilen tablolar, model
çağrıları ve token (modelin okuduğu ve yazdığı metin parçası) sayıları. Yönetici, yönetim ekranının
**Genel bakış** sayfasında sistemin sağlığını, ilk kurulumda kalan adımları ve son etkinliği görür;
**Analizler** sayfasında biten analizleri süzer, bir kaydın adım adım zaman çizelgesini açar,
sürenin nereye gittiğini karşılaştırır ve kayıtları kalıcı olarak siler. Kayıtlar süresiz saklanır;
kendiliğinden silinmez, yalnız yönetici siler.

## Aktörler ve sonuçlar

- **Yönetici (`yonetici`):** İki sayfayı kullanır; bütün kullanıcıların biten analizlerini görür ve
  siler. Ölçülebilir sonuç: bir analiz bittikten sonra kaydı, Analizler sayfası açık ve "Canlı"
  açıkken en geç 15 saniye içinde listede soranın görünen adıyla görünür; kaydın ayrıntısı her adımın
  süresini ve her model çağrısının token sayısını gösterir.
- **Kullanıcı (`kullanici`):** Soru sorar ve toplu arama yapar; bu işlemler kaydı üretir. Kendi
  analizinin sonucunu ve raporunu, kayıt durdukça [question-analysis](../004-question-analysis/PRD.md)
  uçlarından alır. Yönetim sayfalarını göremez; bu PRD'nin API uçları (sunucunun istek kabul ettiği
  adresler) ona 403 (yetki yok) döner.
- **[question-analysis](../004-question-analysis/PRD.md):** Analizi iş olarak yürütür; kaydı kabulde
  açar, iş başlarken ve bitince günceller. Kayda hangi alanların ve adımların hangi anda yazıldığı,
  durum geçişleri ve tam cevabın okunması (sonuç ve rapor) orada tanımlıdır (Requirement 8, 16 ve 18).
- **[llm-connection](../003-llm-connection/PRD.md):** Model çağrılarının içerik taşımayan özetini ve
  model sunucusu denetiminin sonucunu verir; bunların tek kalıcı yeri bu kayıttır.

## Değişmezler ve sınırlar

Decision 1: Analiz kaydı ürün verisidir ve yalnız PostgreSQL'de (uygulamanın veritabanı) durur.
Dosyaya yazılmaz. İçeriği — soru, cevap, tablo adları, soranın adı, arama metni — uygulama günlüğüne
(log), ölçümlere (metrik) ve izlere (OpenTelemetry sinyalleri) kopyalanmaz.

Decision 2: Soran, oturumdaki kullanıcıdır (`public_id` ve görünen ad). İstemci adresi (IP) ve makine
adı tutulmaz; adresten makine adı bulmak için DNS sorgusu (ters DNS) yapılmaz.

Decision 3: Kaydın hiçbir alanı şunları taşımaz: modele giden istem (prompt), modelin ham yanıtı ya da
yanıttan parça, model sunucusunun adresi ve hata gövdesi, API anahtarı, istek başlıkları, ham istisna
(beklenmeyen hata) metni. Hata ve sebep alanlarında yalnız sabit hata kodu ve kullanıcıya gösterilen
güvenli Türkçe ileti bulunur. Gerekçe: kayıt silinene kadar bütün yöneticilere açıktır; sunucu
adresi ve hata gövdesi ağ ayrıntısı sızdırır; ham yanıt, var olmayan tablo denetiminden geçmemiş
metindir.

Decision 4: Kayıtları yönetim ekranında yalnız `yonetici` rolü görür ve siler; yetki her istekte
sunucuda denetlenir ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)).
Kaydı yalnız question-analysis'in iş hizmeti açar ve günceller; son duruma ulaşan kayıt bir daha
değişmez, yalnız silinir. Silme kalıcıdır; yedek tutulmaz.

- Kaydın `public_id`'si analiz işinin kimliğidir. Süren (`queued` sırada, `running` yürüyor) kayıt
  yönetim ekranında görünmez, yönetici silmesine girmez; son durumuna (`completed`,
  `failed`, `cancelled`, `interrupted`) ulaşınca görünür.
- Kaydın tam cevabını question-analysis'in sonuç ve rapor uçları okur. Yönetici kaydı silince o
  analizin sonucu ve raporu da açılamaz (Decision 15). Toplu arama terimlerinin cevapları
  [list-search](../005-list-search/PRD.md)'ün kendi tablolarında durur; kaydın silinmesi listeyi ve
  liste raporunu etkilemez.
- Toplu arama teriminin listesi, liste dosyasının adı ve terimin sırası list-search'ten gelir.
- Model çağrısı özetinin biçimi ve hata sınıfları llm-connection'dadır (Requirement 12, 13 ve 18);
  bu PRD onları adımların içinde saklar ve gösterir. Ayrı çağrı tablosu yoktur.
- Yönetim ekranının kabuğu — kenar çubuğu, Ctrl K komut paleti, adres biçimi ve derin bağlantılar
  (sayfayı ya da kaydı doğrudan açan adres), çekmece (yandan açılan panel), onay, `/`
  kısayolu — [search-settings](../009-search-settings/PRD.md) PRD'sindedir. Paletin "Son sorular"
  grubu bu PRD'nin liste ucunu, "Performans ayrıntıları" işlemi bu PRD'nin Analizler sayfasını
  kullanır.
- Genel bakış kartlarının verisinin sahipleri: sohbet modeli durumu llm-connection; sözlük
  [dictionary-management](../001-dictionary-management/PRD.md); arama indeksi search-settings;
  kayıtlı cevap özeti ve silme işlemi question-analysis (Requirement 15: `GET /saved-answers/summary`,
  `DELETE /saved-answers`). Bu PRD yalnız kartların gösterimini tanımlar.
- Kayıt yazma ya da güncelleme hatasının günlük olayı ve ölçümü question-analysis'tedir. Kayıt
  tablosunun göçü (veritabanı yapısını kuran betik)
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) yoluyla
  uygulanır.

## Mevcut davranış

Kaynak: `~/codes/kt-dwhnavigator` (`76e21a3`). Her maddenin sonundaki **Hedefte** notu bilinçli
değişikliktir.

- **Adım kaydı** (`src/vsa/trace.py`): `recording()` bloğu içinde açılan her adım (`span`) bellekte
  toplanır: açılış sırası (`id`), üst adım (`parent`), ad, tür (`step` adım, `llm` model çağrısı,
  `event` olay), analizin başından itibaren başlangıç (`start_ms`) ve süre (`ms`), durum (`ok`, `warn`,
  `error`), isteğe bağlı ayrıntı (`detail`) ve sayaçlar (`data`: `requests`, `prompt_tokens`,
  `completion_tokens`). Olay sıfır sürelidir ve varsayılan durumu `warn`'dır. Hatayla çıkılan ya da
  açık kalan adım `error` olur. `Laps` ardışık kardeş adımlar açar; `totals()` model çağrısı sayısını
  ve token toplamlarını verir. Kayıt bloğu yoksa bütün işlevler etkisizdir; bu yüzden komut satırı,
  `vsa eval` ve sözlük gezgini kayıt bırakmaz (`tests/test_trace.py`). **Hedefte:** aynı adım modeli
  kayda yazılır; ana adımlar sabit adım anahtarını, model çağrısı adımları çağrı özetini taşır
  (Requirement 3, Decision 9).
- **Kaydın yazılması** (`src/vsa/web/server.py` `App._answer`, `App._log_analysis`): Tek soru
  (`POST /api/ask`) ve toplu aramanın her terimi (`App._run_list`) aynı `_answer` akışından geçer;
  akış biterken `data/logs/analyses.jsonl` dosyasına bir satır eklenir: `id` (12 onaltılık karakter),
  `at` (satırın yazıldığı an; yerel saat, saat dilimsiz), `ip`, `host` (ters DNS ile bulunan makine
  adı), `query` (ilk 2.000 karakter), `origin` (toplu aramada `liste.xlsx #3`), `flow`, `model`,
  `verdict`, `summary` (ilk 500 karakter), `objects` (ilk 10 tablo anahtarı), `fallback`, `reused`
  (`at`, `query`, `match`), `error` (ilk 500 karakter), `ms`, `llm_calls`, `prompt_tokens`,
  `completion_tokens`, `dictionary_version`, `spans`. Dosyaya yazılamazsa günlüğe uyarı düşer, cevap
  yine döner. Süren analizin satırı yoktur; sunucu analiz sürerken yeniden başlarsa o analiz hiç
  kaydedilmez. **Hedefte:** kayıt veritabanındadır ve analiz işinin kendisidir: kabulde açılır, sonda
  tamamlanır, tam cevabı taşır; soran oturumdaki kullanıcıdır; zaman sorunun kabul edildiği an ve UTC
  (evrensel saat); soru tam saklanır; yarıda kesilen iş de kaydedilir (Requirement 1–2, Decision 2, 5,
  6, 11).
- **Akış** (`_log_analysis`): `durduruldu` (kullanıcı durdurdu), `hata` (sonuç yok), `önbellek`
  (kayıtlı cevap yeniden verildi, ADR-035), `analist` (analist yazdı), `yapılamadı` ("Analiz
  yapılamadı", ADR-038). Model alanı `analist`, `yapılamadı` ve `durduruldu`'da o anki sohbet modeli,
  `önbellek`'te kayıtlı cevabı yazan model, `hata`'da boştur. **Hedefte:** aynı beş akış ve yarıda
  kesilen iş için altıncı akış, İngilizce sabit kodlarla saklanır ve ekranda Türkçe adlarla görünür
  (Requirement 2, Decision 12).
- **Kayda giren ham içerik:** Başarısız model çağrısı adımının ayrıntısı `last_error` metnidir; bu metin
  model sunucusunun adresini ve hata gövdesinden 600 karaktere kadar parçayı içerebilir
  (`src/vsa/llm/client.py` `_post`, `_get`, `chat_json`). "Yanıt JSON değil — onarım isteniyor" olayı
  modelin ham yanıtının ilk 200 karakterini, "Model bir özelliği reddetti — onsuz yeniden" olayı
  sunucunun hata iletisinden 300 karakteri taşır. "Model sunucusuna ulaşılamadı (\<adres>)" sebebi
  adresiyle `fallback` ve `summary` alanlarına girer; `error` ham istisna metnidir. Ayrıca
  `log.exception("Analiz başarısız: %s", query[:80])` sorunun ilk 80 karakterini uygulama günlüğüne
  yazar. **Hedefte:** Decision 1 ve 3; Requirement 4.
- **Rapor ve liste** (`App.report`, `MAX_REPORTS`; `App.lists`, `MAX_LISTS`): Son 50 cevap ve en çok 5
  bitmiş liste yalnız bellekte durur; analiz satırından bağımsızdır. **Hedefte:** tek soru raporu
  analiz kaydındaki tam cevaptan üretilir (question-analysis Requirement 16); liste cevapları
  list-search'ün tablolarındadır.
- **Liste ucu** (`GET /api/admin/analyses`, `App.analyses`): Dosyanın son 3.000 satırını
  (`ADMIN_LIST_LIMIT`) en yeni önce, adımlar olmadan, adım adına göre toplanmış sürelerle (`steps`)
  döndürür. Süzme, göstergeler, grafik ve "Daha fazla" tarayıcıda bu 3.000 satırdan hesaplanır; daha
  eski kayıt hiçbir yerde görünmez. **Hedefte:** süzme, sayfalama ve göstergeler sunucuda, bütün
  biten kayıtlar üzerinden (Requirement 6–9, Decision 7).
- **Ayrıntı ucu** (`GET /api/admin/analysis/<id>`, `App.analysis`): Kaydı bütün adımlarıyla döndürür;
  kayıt son 3.000 satırda yoksa 404 "Kayıt bulunamadı". **Hedefte:** Requirement 10.
- **Silme** (`POST /api/admin/analyses/clear`, `App.clear_analyses`): Gövde `{"ids": [...]}` ya da
  `{"all": true}`; ikisi de yoksa 400 "Silinecek analiz seçilmedi" — hiçbir şey kendiliğinden
  silinmez. Dosya yeniden yazılır, yedek bırakılmaz; yanıt `{removed, kept}`
  (`tests/test_web.py::test_clear_analyses`). **Hedefte:** ekranın tuttuğu kimlik listesi yerine süzgeç
  ve "bu ana kadar" sınırı gönderilir (Requirement 11, Decision 8).
- **Saklama:** Kayıtlar süresiz tutulur, yalnız elle silinir. `docs/GUVENLIK.md` kalan risk 5:
  `data/logs/` soru metinleri ve istemci adresleri içerir. **Hedefte:** aynı; kayıtlar süresiz
  saklanır ve yalnız yönetici siler (Requirement 11, 12); istemci adresi tutulmaz (Decision 2).
- **Koruma** (`src/vsa/web/security.py` `AdminGuard`, ADR-047): `/admin` ve `/api/admin/*`,
  `VSA_ADMIN_PASSWORD` ile tarayıcının parola kutusunu (HTTP Basic) ister; parola yoksa yalnız
  sunucunun kendisinden açılır. **Hedefte:** oturum ve `yonetici` rolü (Decision 4).
- **Genel bakış** (`src/vsa/web/static/admin.html` `PAGES.genel`, ADR-051): üç adımlı "Kuruluma devam"
  kartı, dört sağlık kartı, "Son 7 gün" kartı (dört gösterge `Analyses.kpi`, 14 günlük grafik, "Tüm
  analizler" bağlantısı) ve "Son sorular" (en yeni 100 kayıt). Veriler `/api/settings`, `/api/llm`,
  `/api/admin/dictionary` ve `/api/admin/analyses` uçlarından birlikte okunur; biri okunamazsa yalnız
  ona bağlı kart "…" gösterir. **Hedefte:** aynı düzen ve metinler; göstergeler, grafik ve son sorular
  bu PRD'nin uçlarından, kartların verisi kendi PRD'lerinden gelir (Requirement 13–15).
- **Analizler** (`Analyses`): araç çubuğu (dönem, "Cevabı yazan", "Soran", arama, "Canlı"), süzgece
  uyan satırlardan dört gösterge, 150'şer satırlık liste ve "Daha fazla", 15 saniyelik canlı
  yenileme (ayrıntı açıkken durur), ayrıntı çekmecesi (`openDetail`, `detail`), aşama özeti
  (`PHASES`, `phasesOf`: 1 saniyeden kısa sırada bekleme gösterilmez), katlanmış zaman çizelgesi
  (`timeline`), ↑/↓ ile kayıtlar arasında gezinme ve Esc, "Performans" çekmecesi (`perf`),
  "Temizle…" (`clear`, tarayıcının iki onay kutusu). "Soran", makine adı ya da IP'dir (yoksa
  "bilinmiyor"); ayrıntının alt satırı IP'yi de gösterir. **Hedefte:** aynı işlev ve görünüm; soran
  görünen addır, IP gösterilmez; onaylar kaynaktaki gibi tarayıcının onay penceresiyle alınır
  (Requirement 16–22).
- **Komut satırı ve ölçüm:** `vsa ask` ve `vsa eval` kayıt yazmaz. **Hedefte:** ölçüm betiği de kayıt
  yazmaz ([quality-evaluation](../010-quality-evaluation/PRD.md)).

## İşlevsel gereksinimler

Requirement 1: Her analiz işinin bir kaydı vardır: tek soru, toplu aramanın her terimi ve kabulde
kayıtlı cevapla biten analiz dahil. Kaydı question-analysis'in iş hizmeti işin kabulünde açar, iş
başlarken ve son duruma ulaşınca aynı kaydı günceller (question-analysis Requirement 8 ve 18); her
yazma tek işlemde (transaction: ya tamamı ya hiçbiri yazılan veritabanı işlemi) yapılır. Son duruma
ulaşan kayıt bir daha değişmez. Ölçüm betiği, sözlük gezgini, bağlantı testi ve bu PRD'nin uçları kayıt
açmaz.

Requirement 2: Kaydın alanları şunlardır; sınırı aşan metin sınırda kesilir:

- `public_id` (dışa açık kimlik; analiz işinin kimliği);
- soran kullanıcı (kullanıcı kaydına bağ; ekranda güncel görünen adı);
- durum: `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted` (geçişler
  question-analysis Requirement 8);
- akış (son durumda; question-analysis Requirement 18'deki İngilizce kodlar ve Türkçe görünen
  adları): `analyst` "Analist", `reused` "Önceki cevap", `unavailable` "Yapılamadı", `cancelled`
  "Durduruldu", `failed` "Hata", `interrupted` "Yarıda kesildi" (kaynaktaki `analist`, `önbellek`,
  `yapılamadı`, `durduruldu`, `hata` akışlarının karşılığı);
- zamanlar, UTC (evrensel saat): kabul (`asked_at`), başlama ve bitiş; sırada bekleme süresi (ms);
- soru metni, tam (en çok 4.000 karakter; sınırı question-analysis koyar) ve yeniden analiz istenip
  istenmediği (`fresh`);
- köken: `question` ya da `list`; listede listenin `public_id`'si, liste dosyasının adı (en çok 255
  karakter) ve terimin listedeki sırası (1'den başlar);
- model: cevabı yazan sohbet modelinin adı (`reused`'da kayıtlı cevabı yazan model; `failed` ve
  `interrupted`'da boş olabilir);
- sonuç: VAR, KISMEN VAR, BULUNAMADI ya da boş;
- cevap özeti (ilk 500 karakter) ve önerilen tablolar (cevaptaki sırayla en çok 10 `DB.Şema.Obje`
  anahtarı);
- tam cevap: biçimi question-analysis Requirement 18'dedir; yalnız question-analysis'in sonuç ve
  rapor uçları okur, bu PRD'nin uçları döndürmez;
- cevaplanamama sebebi: `unavailable`'da kullanıcıya gösterilen sebep, en çok 500 karakter;
- yeniden kullanılan cevap (`reused`'da): ilk yazıldığı zaman, sorusu ve eşleşme türü
  (`same_question` "aynı soru", `same_meaning` "aynı anlam");
- hata (`failed`, `cancelled` ve `interrupted`'da): sabit kod (en çok 64 karakter) ve güvenli Türkçe
  ileti (en çok 500 karakter); durdurmada kod `cancelled`, ileti "Kullanıcı durdurdu";
- toplam süre (kabulden bitişe, ms), model çağrısı sayısı, giriş ve çıkış token toplamları;
- sözlük sürümü;
- Requirement 3'teki altı aşamanın süresi ve adımlar.

Requirement 3: Her adım şunları taşır: sıra numarası (0'dan, açılış sırası), üst adımın sıra
numarası (yoksa boş), ad (en çok 120 karakter), tür (`step`, `llm`, `event`), varsa sabit adım
anahtarı, analizin başından itibaren başlangıç (ms), süre (ms), durum (`ok`, `warn`, `error`) ve
ayrıntı (en çok 300 karakter, boş olabilir). `llm` türündeki adım llm-connection'ın çağrı özetini
taşır (Requirement 18: entegrasyonun `public_id`'si, model, başlangıç, bekleme ve süre, sonuç, son
HTTP kodu, istek sayısı, bırakılan özellikler, onarım istenip istenmediği, giriş ve çıkış token'ı);
"Model sunucusu kontrolü" adımı denetimin sonucunu taşır (Requirement 12 ve 18: sonuç, HTTP kodu,
süre, önbellekten mi). Model çağrısı sayısı `llm` adımlarının sayısı, token toplamları bu adımların
özetlerinin toplamıdır. Analiz bittiğinde açık kalan adım bitiş anında kapanır ve `error` olur. Bir
kayıtta en çok 500 adım saklanır; fazlası yazılmaz, kayıt `steps_truncated` işaretini taşır ve zaman
çizelgesinin sonunda "Adım sınırı aşıldı; sonraki adımlar kaydedilmedi." yazar. Aşamalar ve bunlara
sayılan adım anahtarları (question-analysis'in canlı akışta kullandığı sabit küme, Requirement 10):

| Aşama | Ekrandaki ad | Not | Adım anahtarı | Kaynaktaki adım adı |
|---|---|---|---|---|
| `queue` | Sırada bekleme | başka bir soru bitene kadar | `queue` | Sırada bekleme |
| `saved_answer_lookup` | Önceki cevap araması | aynı ya da aynı anlama gelen soru | `saved_answer_lookup` | Önceki cevap araması |
| `model_check` | Model sunucusu kontrolü | — | `model_check` | Model sunucusu kontrolü |
| `rule_hints` | Arama (kural motoru) | sözlükte kelime araması | `rule_hints` | Kural motoru ipuçları |
| `analyst_pick` | Analist: tablo seçimi | model katalogdan aday tabloları seçer | `shortlist`, `family_search` | 1. adım — aday seçimi; Aile araması |
| `analyst_write` | Analist: kolonları okuma ve rapor | model adayların kolonlarını okur, cevabı yazar | `analyst_report` | 2. adım — kolon okuma ve rapor |

Bir aşamanın süresi, o aşamanın anahtarlarını taşıyan `step` türündeki adımların sürelerinin
toplamıdır. Anahtarı yalnız tablodaki ana adımlar taşır; alt adımlar ve olaylar taşımaz, böylece aynı
süre iki kez sayılmaz.

Requirement 4: Kayıt Decision 3'teki içeriği taşımaz. Adım ayrıntılarını question-analysis tanımlar
(Requirement 18); bu PRD şu sınırları koyar: model çağrısı adımının ayrıntısı yalnız model adı ve
başarısızlıkta llm-connection'ın sabit hata sınıfıdır (Requirement 13); yanıtın JSON (yapılandırılmış
metin biçimi) olmadığını bildiren olay yalnız deneme sırasını; modelin bir istek özelliğini
reddettiğini bildiren olay yalnız bırakılan özelliğin adını taşır; "Model sunucusu kontrolü" ve
cevaplanamama sebebi sunucu adresi içermez. Ayırt edici bir işaret dizesi modelin yanıtına, model
sunucusunun hata gövdesine ve sunucu adresine konduğunda bu dize hiçbir kayıtta ve bu PRD'nin hiçbir
API yanıtında bulunmaz.

Requirement 5: Yönetim ekranının uçları yalnız son durumdaki kayıtları okur ve siler: liste, özet,
günlük sayılar, soran listesi, ayrıntı ve silme `queued` ve `running` kayıtları görmez. Süren işin
kaydı ayrıntı ucunda 404 alır, hiçbir silme isteğiyle silinmez.

Requirement 6: Liste, süzgeçlere uyan kayıtları kabul zamanına göre en yeni önce (eşitlikte en son
açılan önce) sayfalı döndürür: sayfa boyutu varsayılan 150, en çok 500. Süzgeçler:

- dönem: `today` (İstanbul saatiyle bugün 00.00'dan beri), `7d` (son 7×24 saat, varsayılan), `30d`
  (son 30×24 saat), `all`;
- akış: altı akıştan biri;
- soran: kullanıcının `public_id`'si;
- metin: en çok 200 karakter; soru, model adı, cevap özeti, liste dosyası adı ve tablo anahtarlarında
  geçen alt dize olarak, uygulamanın Türkçe harf katlama yardımcısıyla (İ/ı farkını gideren
  normalleştirme) aranır — "İŞLEM", "işlem" ve "islem" aynı kayıtları bulur;
- `until`: bu andan sonra kabul edilen kayıtlar listeye girmez; dönem `until`'e göre hesaplanır;
  verilmezse sunucunun o anki zamanıdır.

Yanıt satırları, toplam kayıt sayısını, sayfa bilgisini ve `snapshot_at` değerini (listenin hesaplandığı
an, yani kullanılan `until`) taşır. Satır alanları: `public_id`, kabul zamanı, soran (`public_id`,
görünen ad), soru, köken, akış, model, sonuç, önerilen tablolar, cevaplanamama sebebi, hata kodu ve
iletisi, toplam süre. Satır cevap özetini, tam cevabı ve adımları taşımaz.

Requirement 7: Özet, Requirement 6'daki süzgeçlerle şunları döndürür: kayıt sayısı; en yeni kabul
zamanı; sonucu olan kayıt sayısı; tablo önerilen (sonucu VAR ya da KISMEN VAR olan) kayıt sayısı;
akışa göre kayıt sayıları; `analyst` akışındaki kayıtların süre ortancası (%50) ve %90 değeri; bütün
kayıtların süre ortancası, %90 değeri ve en uzunu; her aşama için ortalama süre ve o aşaması olan kayıt
sayısı (yalnız aşama süresi sıfırdan büyük kayıtlar, Requirement 3'teki sırayla); model çağrısı, giriş
ve çıkış token toplamları; soran başına kayıt sayısı (çoktan aza, eşitlikte ada göre). Yüzdelikler
kaynaktaki `quantile` gibi sıralı değerler arasında doğrusal aradeğerlemeyle hesaplanır; kayıt yoksa
süre değerleri boştur.

Requirement 8: Günlük sayılar, son N günün (varsayılan 14, en çok 31) her biri için İstanbul saatiyle
takvim gününe göre, en eskiden yeniye ve kaydı olmayan günler sıfırla, tablo önerilen kayıt sayısını ve
geri kalan kayıtların (BULUNAMADI ve sonucu boş olanlar) sayısını döndürür.

Requirement 9: Soran listesi, son durumdaki kaydı bulunan bütün kullanıcıları (`public_id`, görünen ad)
görünen ada göre sıralı döndürür; Analizler sayfasının "Soran" seçimini doldurur.

Requirement 10: Ayrıntı, Requirement 6'daki satır alanlarına ek olarak cevap özetini, yeniden
kullanılan cevap bilgisini, model çağrısı ve token toplamlarını, sözlük sürümünü, başlama ve bitiş
zamanını, sırada bekleme süresini, altı aşamanın süresini, `steps_truncated` işaretini ve bütün
adımları döndürür; tam cevabı döndürmez. Yok, süren ya da silinmiş kayıt için
yanıt 404 `analysis_record_not_found`'dır.

Requirement 11: Silme yalnız açık bir seçimle yapılır: ya süzgeçler (dönem, akış, soran, metin) ve
`until` ile süzgece uyan kayıtlar, ya da `all=true` ile `until`'den önce kabul edilen bütün kayıtlar;
ikisinde de yalnız son durumdaki kayıtlar (Requirement 5). `until` zorunludur; ne süzgeç ne `all=true`
verilmişse yanıt 422 `analysis_delete_scope_missing`'dir ve hiçbir şey silinmez. Silme kaydı tam
cevabı ve adımlarıyla tek işlemde kalıcı olarak kaldırır; o analizin sonucu ve raporu question-analysis
uçlarında da açılmaz; o kaydı gösteren kayıtlı cevap bağı boşalır, kayıtlı cevabın kendisi silinmez.
`until`'den sonra kabul edilen kayıt silinmez. Yanıt silinen kayıt sayısını ve kalan toplam kayıt
sayısını taşır. Aynı istek tekrarlanırsa ikinci yanıt 0 silinen döner ve başka kayda dokunmaz.

Requirement 12: Kayıtlar süresiz saklanır (kaynakla aynı). Hiçbir kayıt yaşı yüzünden kendiliğinden
silinmez; kayıt yalnız yöneticinin Requirement 11'deki silmesiyle kalkar. Saklama süresi ayarı ve
zamanlanmış silme işi yoktur (Decision 16).

Requirement 13: Genel bakış (`/admin/genel`, yönetim ekranının açılış sayfası) başlığı "Genel bakış",
açıklaması "Sistemin durumu ve son etkinlik; her ayara ve işleme Ctrl K ile gidilir." olan sayfadır ve
dört sağlık kartı gösterir:

| Kart | Değer | Açıklama satırı | Düğme |
|---|---|---|---|
| Sohbet modeli | Model adının son "/" işaretinden sonraki parçası; model yoksa "Bağlı değil" | "<bağlantı adı> üzerinden · yanıt veriyor"; yanıt vermiyorsa "Yanıt vermiyor: \<sebep>"; model yoksa "Model yokken sorular cevaplanamaz." | Yanıt veriyorsa "Bağlantılar", değilse "Bağla" → Yapay zekâ sayfası |
| Sözlük | "\<n> tablo"; sözlük yoksa "İçe aktarılmadı" | "\<n> kolon · <kaynak dosya adı> · <içe aktarma zamanı>"; yoksa "Şablondaki Excel'i içe aktarın; o zamana kadar soru cevaplanmaz." | Sözlük yoksa "İçe aktar", varsa "Sözlük" → Sözlük sayfası |
| Arama indeksi | "Güncel", "Kuruluyor", "Yeniden kurulmalı" ya da "Boş" | "Son kurulum \<zaman>"; yeniden kurulmalıysa "Değişen: <farklı girdiler>"; boşsa "Sözlük içe aktarılınca kurulur." | Yeniden kurulmalıysa "Şimdi kur" |
| Önceki cevaplar | "\<n> geçerli" | "Toplam \<n> · aynı ya da aynı anlamdaki soru beklemeden gelir"; hiç yoksa "Henüz kayıtlı cevap yok." | "Yönet" → Bakım sayfası |

Kartın rengi durumunu gösterir (iyi, uyarı, hata). Sohbet modeli kartı llm-connection'ın sunucu
denetimini (Requirement 12) ve etkin bağlantının adını, arama indeksi kartı search-settings'in indeks
durumunu (Requirement 15), önceki cevaplar kartı question-analysis'in `GET /saved-answers/summary`
ucunu (Requirement 15) kullanır. Bir kaynak okunamazsa yalnız o kart "…" gösterir; diğer kartlar ve
sayfanın geri kalanı çalışır. "Şimdi kur" indeksi search-settings'teki yeniden kurma işlemiyle kurar,
bitince sonucu bildirir ve kartları yeniler.

Requirement 14: "Kuruluma devam" kartı üç adımın hepsi yapılmadıkça sayfanın en üstünde görünür ve
yapılan adım sayısını "n/3" olarak gösterir: 1) "Sözlüğü içe aktarın" (sözlük varsa yapıldı), 2) "Sohbet
modelini bağlayın" (sohbet modeli yanıt veriyorsa yapıldı), 3) "İlk soruyu sorun" (son durumdaki en az
bir analiz kaydı varsa yapıldı). Yapılmamış adımın "Git" bağlantısı sırasıyla Sözlük sayfasına, Yapay
zekâ sayfasına ve uygulamanın ana ekranına gider. Bütün kayıtlar silinirse üçüncü adım yeniden
yapılmamış görünür (kaynakta da böyledir).

Requirement 15: "Son 7 gün" kartı, son 7×24 saatin kayıtları için dört gösterge verir:

- "Soru": kayıt sayısı; alt satır "son: <en yeni kabul zamanı>";
- "Tablo önerilen": tablo önerilen kayıtların sonucu olan kayıtlara oranı (yüzde); alt satır "x/y
  cevapta";
- "Analist cevapladı": `analyst` ve `reused` kayıtlarının bütün kayıtlara oranı; alt satır,
  `unavailable`, `failed` ya da `interrupted` kayıt varsa "N soru cevaplanamadı", yoksa `reused` kayıt
  varsa "N önceki cevaptan", yoksa "hepsi";
- "Tipik süre": `analyst` kayıtlarının süre ortancası; alt satır "%90: <süre>"; `analyst` kaydı yoksa
  "–" ve "yeni analiz yok".

Payda sıfırsa gösterge "–"dir. Göstergelerin altında son 14 günün yığılmış çubuk grafiği (her gün
"tablo önerildi" ve "önerilmedi / cevaplanamadı" iki parçadır; çubuğun ipucu "<gün/ay>: N soru (x tablo
önerildi, y önerilmedi)"; gün ve ay iki hanelidir ve tarayıcının Türkçe kısa tarihiyle yazılır, ör.
"27/09"; tarih etiketi aynı biçimde iki günde bir) ve "Tüm analizler" bağlantısı vardır. "Son
sorular" kartı en yeni 100 kaydı zaman, sonuç rozeti, soru ve akış etiketiyle listeler; satır kaydın
ayrıntısını Analizler sayfasında açar; kayıt yoksa "Henüz soru sorulmadı." yazar. **Yeni davranış:**
`interrupted` kaynakta yoktu; "cevaplanamadı" sayısına ve grafiğin ikinci parçasına girer.

Requirement 16: Analizler sayfası (`/admin/analizler`) başlığı "Analizler", açıklaması "Sorular,
cevaplar, cevabı kimin yazdığı ve sürenin nereye gittiği; ayrıntı için satıra tıklayın.", düğmeleri
"Yenile", "Performans" ve "Temizle…"dir. Araç çubuğunda dönem düğmeleri ("Bugün", "7 gün" varsayılan,
"30 gün", "Tümü"), "Cevabı yazan" seçimi ("Cevabı yazan: hepsi" ve altı akış), "Soran" seçimi ("Herkes"
ve Requirement 9'daki kişiler), "Soru, tablo ya da model ara…" arama kutusu (yazma bittikten 300 ms
sonra istek gider; kabuğun `/` kısayolu bu kutuya odaklanır) ve "Canlı" anahtarı vardır. Altında
Requirement 15'teki dört gösterge süzgece uyan bütün kayıtlar üzerinden hesaplanır. Liste başlığı
"Sorular · <Bugün | Son 7 gün | Son 30 gün | Tüm zamanlar> · <sayı>"dır. Tablo sütunları: "Ne zaman";
"Soru ve cevap" (soru; toplu arama terimiyse yanında "📄 <liste dosyası adı> #<sıra>"; alt satırda
sonuç rozeti ve ilk tablonun adı ile "+N tablo", tablo yoksa sebep ya da hata iletisi); "Cevabı yazan"
(akış etiketi ve soranın görünen adı); "Süre". Sonuç rozeti, sonuç yoksa durdurulan kayıtta "durdu",
diğerlerinde "—"dir. Liste 150'şer satır gösterir; kalan varsa "Daha fazla (N kaldı)" düğmesi aynı
`until` ile sonraki sayfayı listenin sonuna ekler. Süzgeç değişince liste baştan ve yeni `until` ile
yüklenir. Boş durumlar: hiç kayıt yoksa "Henüz kayıtlı analiz yok. Uygulamada bir soru sorulduğunda
burada görünür.", süzgeçle eşleşen yoksa "Bu süzgeçle eşleşen soru yok."; okuma hatasında "Analizler
okunamadı: \<ileti>".

Requirement 17: "Canlı" açıkken (varsayılan), Analizler sayfası seçiliyken, tarayıcı sekmesi
görünürken ve ayrıntı çekmecesi kapalıyken liste ve göstergeler 15 saniyede bir yeni `until` ile
yenilenir; gösterilen satır sayısı ve kaydırma konumu korunur. Anahtarın ipucu "15 sn'de bir yenilenir
(ayrıntı açıkken durur)"dur. "Yenile" düğmesi aynı yenilemeyi hemen yapar.

Requirement 18: Satıra tıklamak ya da satıra odaklanmışken Enter veya Boşluk tuşu kabuğun çekmecesini
açar ve adres kaydın derin bağlantısı (`/admin/analizler/<public_id>`, adres biçimi search-settings
Requirement 20) olur; bu bağlantıyla gelen kayıt sayfa açılınca, yeni sekmede de doğrudan açılır.
Çekmecenin başlığı sorudur; alt satırı "\<tarih saat> · \<soran> · <toplam süre>"dir. İçeriği:

- "Cevap": sonuç rozeti ve özet (özetin başındaki "VAR", "KISMEN VAR" ya da "BULUNAMADI" sözcüğü ve
  ardındaki ayraç atılarak);
- "Önerilen tablolar": tablo adı etiketleri; ipucunda tam anahtar;
- "Cevabı yazan": akış etiketi ve açıklaması — "Dil modeli (\<model>)"; "Önceki cevap: aynı soru ·
  \<zaman> · \<model>" ya da "Önceki cevap: aynı anlama gelen “\<soru>” · \<zaman> · \<model>"; "Analiz
  yapılamadı"; "Kullanıcı durdurdu"; "Hata"; "Yarıda kesildi (uygulama yeniden başladı)";
- "Toplu arama": liste dosyası adı ve sıra (varsa);
- "Model kullanımı": "N çağrı · X giriş + Y çıkış token" (çağrı varsa);
- sebep varsa uyarı kutusunda "Neden cevaplanamadı: \<sebep>"; hata varsa hata kutusunda "Hata:
  \<ileti>";
- "Süre nereye gitti · toplam <süre>": aşamaların toplam süre içindeki payını gösteren yığılmış çubuk
  ve her aşamanın adı, süresi ve notuyla liste; 1 saniyeden kısa "Sırada bekleme" gösterilmez;
- katlanmış "Adım adım zaman çizelgesi" (Requirement 19);
- en altta "↑ / ↓ ile önceki ve sonraki analiz · Esc ile kapat".

Requirement 19: Zaman çizelgesi adımları ağaç sırasıyla listeler: her adım üst adımının altında,
kardeşler başlangıç zamanına (eşitlikte sıra numarasına) göre, derinliğe göre içeri kaydırılmış. Her
adımın çubuğu toplam süre içindeki başlangıcına ve süresine göre yerleşir; `error` durumundaki adımın
adının önünde "✕" vardır. İpucu ad, tür ("adım", "model çağrısı", "olay"), "+<başlangıç> · <süre>",
token varsa "<giriş> → <çıkış> token", başarısız model çağrısında hata sınıfının Türkçe metni ve
ayrıntıyı gösterir. Ayrıntı, durumu `ok` olmayan ya da türü `step` olan adımın altında ayrı satır
olarak da yazılır. Açıklama satırı "adım", "model çağrısı", "bekleme / olay" renklerini gösterir. Adım
yoksa (örneğin yarıda kesilen işte) "Bu analiz için adım kaydı yok." yazar.

Requirement 20: Ayrıntı çekmecesi açıkken ve odak bir yazı alanında değilken ↓ listede bir sonraki,
↑ bir önceki kaydı açar; yalnız yüklenmiş satırlar arasında gezinir, sonda ve başta durur. Esc
çekmeceyi kapatır (kabuğun kuralı, search-settings Requirement 24) ve adres listeye döner.

Requirement 21: "Performans" düğmesi ve komut paletinin "Performans ayrıntıları" işlemi bir çekmece
açar: başlık "Performans", alt satır "<dönem> · N soru (süzgeçle)". İçerik, Requirement 7'deki
özetten: "Aşama başına ortalama süre" (aşama başına yatay çubuk ve süre; ipucunda kayıt sayısı);
"Süre dağılımı: yarısı \<ortanca> altında, %90'ı <%90> altında; en uzun \<en uzun>."; "Model
kullanımı" ("N model çağrısı · X giriş + Y çıkış token" ya da "Bu dönemde model çağrısı yok.");
"Kullanıcılar" (soran başına "N soru"). Bir kişiye tıklamak "Soran" süzgecini o kişiye ayarlar ve
çekmeceyi kapatır. Süzgeçte kayıt yoksa "Bu süzgeçte soru yok." yazar.

Requirement 22: "Temizle…" düğmesi süzgeçte kayıt yoksa "Silinecek analiz yok" bildirimini ("Süzgeç
boş.") gösterir. Kayıt varsa tarayıcının onay penceresi (search-settings Requirement 24) sorar: dönem
"Tümü" ve başka süzgeç yoksa "Kayıtlı N analizin tamamı silinsin mi?", değilse "Süzgeçteki N analiz
(<dönemin küçük harfli adı>) silinsin mi?" — akış, soran ya da metin süzgeci varsa parantezin içine
", süzgeçli" eklenir (örnek: "Süzgeçteki 12 analiz (son 7 gün, süzgeçli) silinsin mi?"). İki sorunun
altında "Silinen analizler kalıcı olarak silinir, yedek tutulmaz. Kullanıcılar bu analizlerin
sonucunu ve raporunu da açamaz." yazar (ikinci cümle yenidir; Decision 15). Onayda Requirement 11'deki
silme isteği gider: ilk durumda `all=true`, ikincisinde süzgeçler; ikisinde de `until` listenin
`snapshot_at` değeridir. Ardından "Analizler silindi" bildirimi ("N analiz silindi; M kaldı.")
gösterilir ve ikinci onay sorulur: "Kayıtlı cevaplar da silinsin mi? Silinmezse aynı ya da aynı
anlamdaki sorular yeniden analiz edilmeden kayıtlı cevaptan gelir." Evet denirse kayıtlı cevapları
silme işlemi (question-analysis Requirement 15, `DELETE /saved-answers`) çağrılır ve "Önceki
cevaplar silindi" ("N cevap silindi.") bildirilir. Hata olursa "Silinemedi" ve ileti gösterilir.
Sonunda liste ve göstergeler yeniden yüklenir.

Requirement 23: İki sayfanın bütün metinleri kaynaktaki Türkçe metinlerdir ve
`app/frontend/src/locales/tr.json` kataloğundadır; akış etiketleri "● Analist", "↻ Önceki cevap", "!
Yapılamadı", "■ Durduruldu", "✕ Hata" ve yeni "↯ Yarıda kesildi"dir. Zaman, süre ve sayı biçimleri
Türkçe yerel ayarıyla kaynaktaki gibidir: bugünkü zaman "bugün 14:05", bu yılın tarihi "08/10
14:05", önceki yılın tarihi "08.10.2025 14:05" (tarayıcının Türkçe kısa tarihleri); süre 1 saniyeden kısaysa "850 ms", 10 saniyeden
kısaysa "4,5 sn", 1 dakikadan kısaysa "45 sn", değilse "2 dk 05 sn"; token sayısı "950", "12,3 k",
"1,2 M"; sayılar "1.234". Masaüstünde sayfa tek ekrandır ve uzun listeler kendi içinde kayar
(search-settings Requirement 25). İki sayfanın görünümü kaynaktaki `admin.html` ile birebir aynıdır;
frontend kurallarının (rules/30–34) istekleri görünümü değiştirmeden karşılanır
([search-settings](../009-search-settings/PRD.md) Decision 11). Grafik, yığılmış çubuk ve zaman
çizelgesindeki dinamik genişlik ve konumlar tarayıcının stil nesnesi (CSSOM) ya da SVG
öznitelikleriyle verilir; çalışırken `<style>` öğesi ekleyen bileşen kullanılmaz
([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 14).

## API sözleşmesi

Bütün API uçları `/api/dwhnavigator/v1` altındadır, geçerli oturum ve `yonetici` rolü ister ve hatayı
`{"detail":{"code":"...","message":"..."}}` biçiminde döner. `{public_id}` UUID (rastgele üretilmiş 36
karakterlik kimlik) biçimindedir. Zamanlar saat dilimli ISO 8601 metnidir (örnek
`2026-10-08T11:05:00Z`). Uçlar yalnız son durumdaki kayıtları okur ve siler (Requirement 5). Kaydın
açılması ve güncellenmesi API ucu değildir; question-analysis bu PRD'nin servisini doğrudan çağırır.

| Yöntem ve yol | İstek | Başarılı yanıt | Hatalar |
|---|---|---|---|
| `GET /analysis-records` | `period` (`today`, `7d`, `30d`, `all`; varsayılan `7d`), `flow`, `asked_by`, `q` (en çok 200 karakter), `until`, `page` (1'den), `page_size` (1–500, varsayılan 150) | 200: `items[]` (Requirement 6), `total`, `page`, `page_size`, `snapshot_at` | 401, 403, 422 `invalid_filter` |
| `GET /analysis-records/summary` | `period`, `flow`, `asked_by`, `q`, `until` | 200: Requirement 7 alanları | 401, 403, 422 `invalid_filter` |
| `GET /analysis-records/daily-counts` | `days` (1–31, varsayılan 14) | 200: `days[]`: `date` (`YYYY-MM-DD`), `with_tables`, `without_tables` | 401, 403, 422 `invalid_filter` |
| `GET /analysis-records/askers` | — | 200: `items[]`: `public_id`, `display_name` | 401, 403 |
| `GET /analysis-records/{public_id}` | — | 200: Requirement 10 alanları | 401, 403, 404 `analysis_record_not_found` |
| `DELETE /analysis-records` | `until` (zorunlu) ve süzgeçler (`period`, `flow`, `asked_by`, `q`) ya da `all=true` | 200: `deleted_count`, `remaining_count` | 401, 403, 422 `analysis_delete_scope_missing`, 422 `invalid_filter` |

401 ve 403'ün kodları [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
PRD'sindedir. Kaynak karşılıkları: `GET /api/admin/analyses` → `GET /analysis-records`,
`GET /api/admin/analysis/<id>` → `GET /analysis-records/{public_id}`,
`POST /api/admin/analyses/clear` → `DELETE /analysis-records`. Kaynaktaki
`POST /api/admin/answers/clear` karşılığı question-analysis'in `DELETE /saved-answers` ucudur
(Değişmezler). OpenAPI (API tanım dosyası) ve üretilmiş ön yüz tipleri aynı değişiklikte
güncellenir.

## Güvenlik ve yetkilendirme

- Rol ve kiracı kapsamı (tek kiracı `platform`) her istekte sunucuda denetlenir; ön yüzdeki menü
  gizlemesi yalnız kolaylıktır. `kullanici` rolündeki istek 403 alır.
- Kayıt kişisel veri taşır: soranın kimliği, soru metni ve cevap. Yönetim ekranında yalnız
  `yonetici` görür; günlüğe ve telemetriye girmez (Decision 1); süresiz saklanır ve yalnız yönetici
  silince kalkar (Requirement 11, 12); silme kalıcıdır (Decision 13). Kaydın sahibi kendi analizini
  yalnız question-analysis'in sahiplik denetimli uçlarından görür.
- Soru, özet ve adım ayrıntıları kullanıcı ya da model kaynaklı metindir; ön yüzde yalnız düz metin
  olarak gösterilir, HTML (sayfa biçimleme kodu) olarak işlenmez. Böylece bir sorunun içine yazılan
  betik yöneticinin tarayıcısında çalışmaz.
- Arama metni sorguya yalnız parametre olarak gider; `%`, `_` ve `\` işaretleri kaçışlanır, metin önce
  Türkçe harf katlamadan geçer. Süzgeç değerleri (dönem, akış, UUID, zaman, sayfa) tip ve aralıkla
  doğrulanır; geçersiz değer 422 alır.
- Derin bağlantı yalnız kaydın `public_id`'sini taşır; soru metni ve arama metni adrese (URL) konmaz.
- Ters DNS ve istemci adresi kullanımı kalkar; sunucu kayıt için dışarıya istek yapmaz.
- Toplu silme açık seçim, onay penceresi ve `until` sınırı ister; silen kişi ve silinen sayı günlüğe
  yazılır (Gözlemlenebilirlik).

## Veri ve geçiş

- Yeni tablo `analysis_record` Alembic göçüyle (veritabanı yapısını sürüm sürüm kuran betik) eklenir;
  şemanın sahibi SQLAlchemy modelleridir (kodda tanımlı tablo modelleri, rules/40). Tablo zorunlu
  sütun bloğunu (rules/41) taşır. Sapma: silme fizikseldir, `is_deleted` her zaman `false` kalır
  (Decision 13); sapma göç ettirilmiş şema testinde doğrulanır.
- Sütunlar: `analysis_record_id` (iç kimlik), `public_id`, kiracı bağı, soranın kullanıcı bağı
  (`app_user` tablosuna dış anahtar, yani veritabanı bağı; hesaplar silinmez, yalnız pasifleştirilir —
  user-accounts), durum, akış, `asked_at`, başlama ve bitiş zamanı, sırada bekleme süresi, soru,
  `fresh`, köken türü, liste `public_id`'si, liste dosyası adı ve terim sırası, model, sonuç, cevap
  özeti, tablo anahtarları dizisi, tam cevap, cevaplanamama sebebi, yeniden kullanılan cevabın zamanı,
  sorusu ve eşleşmesi, hata kodu ve iletisi, toplam süre, model çağrısı ve token toplamları, sözlük
  sürümü, altı aşama süresi sütunu, `steps_truncated`, adımlar ve arama anahtarı.
- Tam cevap ve adımlar kaydın içinde ayrı JSONB alanlarında (veritabanının yapılandırılmış metin
  sütunu) durur (Decision 10). Adım öğesinin biçimi, çağrı özetinin alanları ve bütün sabit değerler
  (durum, akış, köken, sonuç, eşleşme, aşama, adım anahtarı, adım türü ve durumu) sütun açıklamalarında
  yazılır (rules/43). Yazmadan önce adımlar biçim ve uzunluk sınırıyla doğrulanır.
- Liste bağı değer olarak tutulur: liste `public_id`'si ve dosya adı kayıtta saklanır, liste tablosuna
  dış anahtar kurulmaz (Decision 14).
- Arama anahtarı; soru, model adı, cevap özeti, liste dosyası adı ve tablo anahtarlarının Türkçe harf
  katlamasından geçmiş birleşimidir; kayıt son duruma ulaşınca üretilir, API'de dönmez.
- Dizinler: kiracı + durum + kabul zamanı (azalan) + iç kimlik (liste ve sıralama); kiracı + soran +
  kabul zamanı ("Soran" süzgeci).
- question-analysis'in kayıtlı cevap tablosu cevabı üreten kaydı gösterir; kayıt silinince bu bağ
  boşalır (question-analysis Veri ve geçiş). Oylar ([answer-feedback](../006-answer-feedback/PRD.md))
  ve list-search tabloları bu tabloya bağ kurmaz.
- Kaynaktaki `data/logs/analyses.jsonl` taşınmaz; kaynak `data/` dosyalarından veri taşıma yoktur. Hedef
  boş başlar.

## Gözlemlenebilirlik

- Yapılandırılmış günlük olayı: `analysis_record.deleted` (silinen sayı, kapsam `filter` ya da
  `all`, silen kullanıcının `public_id`'si). Soru, cevap, tablo, model adı, görünen ad ve arama
  metni bu olaylara girmez. Liste ucunun `q` parametresi de günlüğe girmez; taban istek günlüğü
  yalnız rota şablonunu (adresin değişken kısımları çıkarılmış hali) yazar (rules/25). Kaydın
  yazılamaması question-analysis'in `analysis.record_write_failed` olayıdır.
- Ölçüm: yöneticinin sildiği kayıt sayısı `dwhnavigator_analysis_records_deleted_total` (etiketsiz).
  Kullanıcı, kayıt, akış ve model ölçüm etiketine girmez. Bu PRD yeni iz aralığı (trace span)
  eklemez.
- Ortak kurallar ve sinyal saklama süresi
  [application-foundation alanındadır](../../../application-foundation/DOMAIN.md). Tüketen test:
  `app/backend/tests/integration/test_telemetry_signals.py`.

## Dağıtım etkisi

- Yeni tablo dağıtımdaki göç adımıyla uygulanır
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)).
- Yeni ortam ayarı, chart nesnesi, sır veya ağ çıkışı yoktur.
- Hacim: tam cevap ortalama ~30 KB, adımlar ~5 KB'tır; bir kayıt yaklaşık 35 KB tutar. Toplu arama
  200 terimlik listelerle kısa sürede binlerce kayıt üretir; 100.000 kayıt yaklaşık 3,5 GB'tır.
  Kayıtlar süresiz saklandığı için tablo yalnız yönetici sildikçe küçülür; kalıcı disk boyutu plan
  aşamasında beklenen yıllık hacimle doğrulanır.

## Test stratejisi

- **Birim:** aşama sürelerinin adım anahtarlarından ve model çağrısı/token toplamlarının çağrı
  özetlerinden hesabı; açık kalan adımın `error` olması; uzunluk kesmeleri; 500 adım sınırı; yüzdelik
  hesabının kaynaktaki `quantile` ile aynı girdide aynı sonucu vermesi; göstergelerin kaynaktaki
  `Analyses.kpi` ve `perf` hesabıyla aynı sonucu vermesi (aynı örnek kayıt kümesi iki yoldan
  hesaplanır).
- **Gerçek PostgreSQL ile:** kabulde açma, başlarken ve sonda güncelleme ve son durumdan sonra
  değişmeme; süren kaydın uçlarda görünmemesi, ayrıntıda 404 alması ve silinmemesi; dönem sınırları
  (İstanbul saatiyle gece yarısı çevresi); akış, soran ve Türkçe harfli metin araması ("İŞLEM",
  "işlem", "islem"); `%` ve `_` içeren arama; sıralama eşitlikleri ve sayfalama; `until` sonrası
  kaydın listede ve silmede dışarıda kalması; özetin ve günlük sayıların (sıfır günler dahil) sabit
  veri kümesinde beklenen değerler; `all=true`, süzgeçli silme, kapsamsız silmede 422 ve tekrarlanan
  silmede 0; silinen kaydın tam cevabının gitmesi ve kayıtlı cevap bağının boşalması; `kullanici`'ya
  403, oturumsuza 401, olmayan kayda 404; kabul zamanı bir yıldan eski son durumdaki kaydın backend
  yeniden açıldıktan sonra yerinde kalması (Requirement 12).
- **Veri sızıntısı:** sahte model sunucusu yanıtına, hata gövdesine ve adresine konan ayırt edici
  işaret dizesi kayıtlarda ve bu PRD'nin API yanıtlarında aranır; bulunmamalıdır (Requirement 4).
- **Ön yüz (Vitest, ön yüz test aracı):** sağlık kartlarının bütün durumları ve bir kaynağın
  okunamaması; kurulum adımları; göstergelerde "–"; grafik ipuçları; son sorular bağlantıları; araç
  çubuğu ve istek parametreleri; canlı yenilemenin durduğu koşullar; "Daha fazla"nın aynı `until`'i
  kullanması; altı akış için çekmece içeriği; zaman çizelgesinin sırası ve girintisi; ↑/↓, Esc ve derin
  bağlantı; Performans çekmecesi ve kişiye tıklama; Temizle akışının iki onayı ve gönderdiği
  parametreler; metinlerin `tr.json`'dan gelmesi.
- **Tarayıcı (Playwright, uçtan uca tarayıcı testi):** Acceptance 4 ve 5'teki akışlar.
- **Görsel eşdeğerlik:** kaynak `76e21a3` ve hedef aynı sözlükle ve aynı soruların sorulmasıyla
  oluşan kayıtlarla yan yana çalıştırılır; iki sayfanın ve çekmecelerin ekran görüntüleri aynı ekran
  boyutlarında karşılaştırılır (Acceptance 6).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: gerçek PostgreSQL ile arka uç testleri
  Requirement 1–3 ve 5–12'yi doğrular; göç ettirilmiş şema testi zorunlu bloğu ve fiziksel silme
  sapmasını doğrular; OpenAPI kayıtlı dosyayla aynıdır.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: veri sızıntısı testi Requirement 4'ü doğrular;
  telemetri testi silme olayını ve ölçümünü doğrular.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: ön yüz testleri Requirement 13–23'ü doğrular;
  yerelleştirme anahtar eşliği testi geçer.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da (geliştirici makinesindeki
  Docker ortamı) `kullanici` rolündeki bir hesap bir soru sorar ve küçük bir toplu arama başlatır; aynı
  anda Analizler sayfası açık olan `yonetici` süren analizi listede görmez, biten kayıtları 15 saniye
  içinde soranın görünen adıyla ve toplu arama terimlerinde "📄 <liste dosyası adı> #<sıra>" ile görür;
  ayrıntıda aşama özeti, zaman çizelgesi ve token sayıları görünür; ↑/↓ ile kayıtlar arasında gezinir;
  derin bağlantı yeni sekmede aynı kaydı açar; Genel bakış'ta son 7 gün göstergeleri, 14 günlük grafik
  ve son sorular bu kayıtları içerir (Requirement 1–3, 5, 13–20).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da `kullanici` rolündeki
  hesap `GET /analysis-records`'ta 403 alır; yönetici "Cevabı yazan: Durduruldu" süzgeciyle yalnız
  durdurulan kaydı siler, diğer kayıtlar kalır ve kullanıcı silinen analizin raporunu artık
  indiremez; liste yüklendikten sonra biten kayıt "Tümü" silmesinde kalır; backend analiz sürerken
  yeniden başlatılınca kayıt "Yarıda kesildi" olarak görünür; veritabanında IP ya da makine adı
  sütunu ve değeri yoktur (Requirement 2, 11, 22, Decision 2).
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı sözlükle ve aynı soruların sorulmasıyla oluşan kayıtlarla
  çalıştırılır; Genel bakış, Analizler, ayrıntı çekmecesi ve Performans çekmecesinin ekran
  görüntüleri masaüstü (1440×900) ve telefon genişliğinde (390×844 piksel) yan yana karşılaştırılır.
  Fark yalnız fabrikanın zorunlu kıldığı oturum alanında kabul edilir (Requirement 13–23).

## Kararlar

- Decision 5: Kayıt, analiz işinin kendisidir: question-analysis işi kabul edince kaydı açar ve aynı
  kaydı sonuna kadar günceller; ayrı bir iş tablosu yoktur. Gerekçe: aynı analiz için iki satır
  olmaz; sonuç ve rapor kayıttan okunur; kaynakta yeniden başlamada kaybolan analizler "Yarıda
  kesildi" olarak görünür.
- Decision 6: Ekranda ve süzgeçlerde kullanılan zaman kabul zamanıdır (`asked_at`); kaynak satırın
  yazıldığı anı (analizin bitişini) gösteriyordu. Gerekçe: dakikalar süren analizde "ne zaman soruldu"
  sorusuna doğru cevap verir; bitiş zamanı ayrıntıda durur. "Bugün" ve 14 günlük grafiğin gün sınırları
  İstanbul saatiyle (`Europe/Istanbul`) hesaplanır; kaynakta tarayıcının saatiyle hesaplanıyordu ve
  kullanıcılar Türkiye'dedir.
- Decision 7: Süzme, sayfalama ve göstergeler sunucuda hesaplanır. Gerekçe: kaynaktaki 3.000 satır
  sınırı kalkar, bütün kayıtlar sayılır, tarayıcıya binlerce satır taşınmaz.
  Hesap yöntemi kaynaktaki `Analyses.kpi`, `perf` ve `quantile` ile aynıdır.
- Decision 8: Toplu silme, ekranın gösterdiği satırların kimlik listesi yerine süzgeç ve `until` ile
  yapılır. Gerekçe: sunucu sayfalamasında ekran bütün kimlikleri tutmaz; `until`, listeyi gördükten
  sonra gelen kaydın yanlışlıkla silinmesini önler. Kaynaktaki gibi hiçbir şey kendiliğinden
  silinmez.
- Decision 9: Ana adımlar question-analysis'in sabit adım anahtarını taşır, aşama bu anahtardan
  bulunur ve aşama süreleri kayıtta toplanmış olarak saklanır. Gerekçe: kaynak aşamaları adım
  adlarından buluyordu; bir adımın adı değişince gruplama sessizce bozulur. Anahtar kümesi canlı
  akışla aynıdır; toplanmış süreler, özet hesabını adımları okumadan yapar.
- Decision 10: Adımlar ve tam cevap ayrı tablolar yerine kaydın JSONB alanlarında durur. Gerekçe:
  ikisi de yalnız kayıtla birlikte okunur ve silinir; ayrı tablo, zincirleme silme ve yüz binlerce
  satır gerektirirdi.
- Decision 11: Soru metni tam saklanır; kaynak ilk 2.000 karakteri yazıyordu. Gerekçe: dosya boyutu
  kaygısı kalkar, yönetici sorunun tamamını görür; soru uzunluğu sınırı (4.000) question-analysis'tedir.
- Decision 12: Durum, akış, köken ve eşleşme değerleri İngilizce sabit kodlarla saklanır ve API'den
  döner; Türkçe adları ön yüz kataloğundadır. Akış kodları question-analysis'in sonuç etiketleriyle
  aynıdır (`analyst`, `reused`, `unavailable`, `failed`, `cancelled`, `interrupted`). Gerekçe: kararlı
  API sözleşmesi ve rules/33.
- Decision 13: Tablo zorunlu sütun bloğunu taşır ama silme fizikseldir; yazılımsal silme (satırı
  silindi diye işaretleme) kullanılmaz. Gerekçe: silinen kaydın sorusu, cevabı ve soranı veritabanında
  kalmamalıdır; kaynakta da silme yedeksiz ve kalıcıdır.
- Decision 14: Toplu arama listesine bağ değer olarak tutulur (rules/42 sapması). Gerekçe: list-search
  listeleri kayıtlardan önce silebilir (kişi başına en yeni 5 liste); kayıt, liste silindikten sonra
  da hangi listenin kaçıncı terimi olduğunu ve dosya adını göstermelidir.

- Decision 15: Yöneticinin bir analiz kaydını silmesi, kullanıcının o analizin sonucunu ve raporunu
  da kaldırır; onay penceresi bunu açıkça söyler (Requirement 22). Gerekçe: kayıt analiz işinin
  kendisidir (Decision 5); tek soru raporu ve sonuç kayıttaki tam cevaptan üretilir ve silme
  gizlilik ve temizlik içindir. Toplu arama listeleri ve raporları kendi tablolarında durduğu için
  etkilenmez.
- Decision 16: Kayıtlar süresiz saklanır; saklama süresi ayarı ve kendiliğinden silme yoktur
  (kaynakla aynı). Gerekçe: proje sahibinin kararı; kayıtları yalnız yönetici "Temizle…" ile siler.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama ([Plan](plan.md), [Görevler](tasks.md)).

## Riskler

- **Kişisel veri birikimi:** Sorular, cevaplar ve soranlar süresiz saklanır; yönetici silene kadar
  tek tabloda durur ve bütün yöneticilere açıktır (Decision 16). Veritabanı yedeği alınmadığı için
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md))
  silinen kayıt hiçbir yerde kalmaz ve geri getirilemez.
- **Silme kullanıcıyı etkiler:** Yöneticinin "Temizle…" işlemi kullanıcıların o analizlerin sonucunu ve
  raporunu da kaldırır (Decision 15).
- **Hacim:** Tam cevapla bir kayıt ~35 KB tutar; toplu arama binlerce kayıt üretir ve kayıtlar
  süresiz saklandığı için tablo zamanla büyür; "Tümü" döneminde özet sorgusu yavaşlayabilir. Liste
  ve özetin yanıt süresi plan aşamasında gerçekçi hacimle ölçülür.
- **Adım anahtarı:** Aşamaları question-analysis'in adım anahtarları belirler; bir ana adım anahtarsız
  yazılırsa o adımın süresi "Süre nereye gitti" ve Performans görünümünde hiçbir aşamada görünmez.
- **Yarıda kesilen iş:** Çökmede bellekteki adımlar kaybolur; böyle bir kayıt "Yarıda kesildi"
  olarak görünür ama zaman çizelgesi boştur.
- **Teşhis kaybı:** Ham model yanıtı ve sunucu hata gövdesi kayda girmediği için modelin geçersiz JSON
  ürettiği durumlar kayıttan teşhis edilemez; teşhis için sabit hata sınıfı, istek sayısı ve onarım
  bilgisi kalır.
- **Geniş silme:** Metin süzgeciyle silme, Türkçe harf katlaması yüzünden beklenenden çok kaydı
  kapsayabilir; onay penceresi silinecek sayıyı gösterir.
