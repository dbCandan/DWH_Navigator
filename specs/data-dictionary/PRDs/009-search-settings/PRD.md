# PRD — search-settings

Status: Accepted

Version: 1.0.0

Acceptance date: 2026-10-08

Domain: [data-dictionary](../../DOMAIN.md)

Kabul kaydı: Proje sahibi bu PRD'yi 2026-10-08'de, kaynak uygulamanın davranışının olduğu gibi
korunması yönergesi ve açık sorulardaki kararlarıyla kabul etti.

## Amaç

Yönetici, kural motorunun ve analistin ölçülmüş varsayılanlarla gelen **arama ve cevap ayarlarını**
yönetim ekranından denetlenmiş biçimde değiştirir; değişiklik yeniden başlatma olmadan uygulanır. Bu
PRD ayrıca **arama indeksinin** (sözlükten, terim sözlüğünden, durak kelimelerden ve ayarlardan
backend sürecinin belleğinde kurulan arama yapılarının) yaşam döngüsünün, yönetim ekranının
**Arama ve cevap** ve **Bakım** sayfalarının ve yedi sayfanın takıldığı **yönetim ekranı kabuğunun**
(kenar çubuğu, Ctrl K komut paleti, derin bağlantılar, çekmeceler, kaydedilmemiş değişiklik çubuğu,
masaüstünde tek ekran düzeni) sahibidir.

## Aktörler ve sonuçlar

- **Yönetici** (`yonetici`): Ayarları değiştirir, varsayılana döndürür, kaydeder ya da geri alır;
  arama indeksinin durumunu görür ve yeniden kurar; kayıtlı cevapları siler; yönetim ekranında kenar
  çubuğu, komut paleti ve derin bağlantılarla (bir öğeyi doğrudan açan adres) gezinir. Sonuç: kaydın
  yanıtı geldikten sonra başlayan her analiz yeni değerleri kullanır; bilinmeyen ya da geçersiz ayar
  hiçbir değeri değiştirmeden reddedilir; süren bir analiz kaydı bekletmez, kayıt da süren analizi
  bozmaz; 24 ayarın ve yedi sayfanın her birine komut paletinden ulaşılır.
- **Kullanıcı** (`kullanici`): Ayarları ve yönetim ekranını görmez. Sorusu, analizi başladığı anda
  hizmette olan motorla (kural motoru ve arama yapılarının bellekteki kopyası) sonuna kadar yürür;
  indeks yeniden kurulurken soru beklemez.
- **İşletim ekibi**: Uygulama açılışta indeksi kurana kadar hazır sayılmaz; kurulum olaylarını ve
  sürelerini içerik görmeden log ve ölçümlerden izler. Arama ayarları için ortam değişkeni yönetmez.
- **Geliştirici**: Varsayılanları ve ekranda olmayan sabitleri kodda değiştirir; değişiklikten önce
  ve sonra altın setle ölçer ([quality-evaluation](../010-quality-evaluation/PRD.md)).
- Diğer PRD'ler: [dictionary-management](../001-dictionary-management/PRD.md) sözlük içe aktarmayı,
  [vocabulary-management](../002-vocabulary-management/PRD.md) liste değişikliklerini bu PRD'nin
  değişiklik sırasından geçirir; [question-analysis](../004-question-analysis/PRD.md) motoru ve etkin
  ayarları buradan alır ve kayıtlı cevapları bu PRD'nin ayar bölümünü içeren parmak iziyle (cevabın
  hangi sözlük, liste, model ve ayarlarla yazıldığını gösteren özet) eşler;
  [analysis-records](../008-analysis-records/PRD.md), [dictionary-management](../001-dictionary-management/PRD.md),
  [vocabulary-management](../002-vocabulary-management/PRD.md) ve
  [llm-connection](../003-llm-connection/PRD.md) sayfaları bu PRD'nin kabuğuna takılır.

## Değişmezler ve sınırlar

- Ekrandan değiştirilebilen ayarların tek listesi ayar şemasıdır (Requirement 1). Şemada olmayan
  anahtar hiçbir yoldan yazılamaz.
- Model bağlantısı ayarları — adres (`endpoint`), model, API anahtarı, `temperature`, zaman aşımı
  (`timeout`), `reasoning_effort`, `seed` ve açık/kapalı (`enabled`) — bu şemada yoktur;
  [llm-connection](../003-llm-connection/PRD.md) PRD'sindedir. `llm.` ile başlayan anahtar bu PRD'nin
  uçlarında `Bilinmeyen ayar` olarak reddedilir. `analyst.max_tokens` modele gönderilen bir değer olsa
  da analistin ayarıdır ve bu şemadadır.
- Arama ayarları ürün verisidir: varsayılanları koddadır, değiştirilmiş değerleri PostgreSQL'dedir.
  Ortam değişkeni, dosya ya da Helm değeriyle verilmez ve ortama göre değişmez.
- Hizmetteki motor, veritabanına yazılmış son arama verisiyle (sözlük, iki liste, ayarlar) kurulmuştur.
  Arama verisini değiştiren işlem ya yeni motorla birlikte hizmete girer ya da hiç yazılmaz.
- İndeks kurulurken analizler beklemez; bir analiz başladığı andaki motoru sonuna kadar kullanır.
- Arama indeksi yalnız backend sürecinin belleğindedir; diske, PostgreSQL'e ya da paylaşılan önbelleğe
  (Redis) yazılmaz ve her an PostgreSQL'deki veriden yeniden üretilebilir.
- Ayar anahtarları ve sayılar dışında hiçbir ayar değeri, sözlük ya da liste içeriği, soru metni loga,
  ölçüme ve ize girmez.
- Sahip olunan veri: ayarların değiştirilmiş değerleri. Sözlük ve sürümü
  [dictionary-management](../001-dictionary-management/PRD.md), iki liste
  [vocabulary-management](../002-vocabulary-management/PRD.md), kayıtlı cevaplar ve analiz sırası
  [question-analysis](../004-question-analysis/PRD.md), giriş ve roller
  [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md), chart ve dağıtım
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  PRD'sindedir.

Decision 1: Ayar şeması kaynaktaki `web/settings_schema.py` şemasının bire bir karşılığıdır: bölümler,
anahtarlar, etiketler, yardım metinleri, türler, varsayılanlar, aralıklar, adımlar, gösterim biçimi,
uzman işareti ve etki aynıdır. Yalnız dosya ve klasör yolu alanları çıkar ve şemada dosyaya ya da
kaldırılan komuta değinen iki metin değişir (Requirement 1).

Decision 2: Yalnız varsayılandan farklı değerler saklanır; etkin değer koddaki varsayılanın üstüne
saklanan değerin konmasıyla bulunur (Requirement 4).

Decision 3: Arama verisini değiştiren her işlem süreç içindeki tek değişiklik sırasından “önce kur,
sonra yaz” düzeniyle geçer (Requirement 11).

Decision 4: Backend tek kopya (replica) çalışır ve güncellemede eski ile yeni kopya aynı anda hizmet
vermez; bu varsayım [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
PRD'sinin tek kopya ve `Recreate` güncelleme kuralına (Decision 5) dayanır. Varsayım bozulursa durum
göstergesi ayrışmayı `stale` olarak gösterir (Requirement 15).

## Mevcut davranış

Kaynak uygulama `~/codes/kt-dwhnavigator` (`76e21a3`) bugün şöyle çalışır; hedefteki değişiklik her
maddede yazılıdır.

- **Ayarlar ve varsayılanlar** (`config.py`): ayarlar veri sınıflarıdır; varsayılanlar 2026-10-07'de
  ölçülen ayarlardır (294 soruda yaklaşık %89,8). `load_settings`, `data/settings.yaml` dosyasını
  (komut satırında `--settings` ile başka yol) varsayılanların üstüne yazar (`_merge`); bilinmeyen
  anahtar `Bilinmeyen ayar: <yol>` hatasıdır ve süreç başlamaz; `search.field_weights` sözlük
  olduğundan anahtarı denetlenmeden birleştirilir. `llm:` bölümü ve `data/llm_integrations.yaml` model
  bağlantısını verir (ADR-032). **Hedefte:** dosya yok; varsayılanlar kodda; değiştirilmiş değerler
  PostgreSQL'de (Requirement 4); saklanan değerler açılışta denetlenir (Requirement 5); model
  bağlantısı llm-connection'da.
- **Ayar şeması** (`web/settings_schema.py`): 8 bölüm kaydında 29 alan; `PAGES = ("llm", "search",
  "data")` ile Arama ve cevap (`search`) ve Bakım (`data`) sayfaları, ayrıca Sözlük (`dictionary`) ve
  Kelimeler (`words`) sayfalarına gömülü “Dosya ayarları”. Her alanın etkisi `anında` (motor kayıtlı
  indeksten yeniden yüklenir) ya da `indeks` (kelime indeksi yeniden kurulmalı); `advanced` alanlar
  “Uzman ayarları” altında; `format: pct` 0–1 değeri yüzde gösterir. **Hedefte:** 5 bölüm, 24 alan
  (Requirement 1).
- **Kaydetme** (`App.settings_save`, `coerce`, `to_yaml_tree`): gönderilen her anahtar denetlenir
  (`Bilinmeyen ayar: <anahtar>`, `<etiket>: açık/kapalı olmalı`, `<etiket>: sayı olmalı`,
  `<etiket>: tam sayı olmalı`, `<etiket>: <en az> ile <en çok> arasında olmalı`); bütün hatalar `; `
  ile birleşip HTTP 400 `{"error": ...}` olarak döner. Sayı alanına `"5"` gibi metin ve `true` (1
  sayılır) kabul edilir. Kayıt, **ekrandaki bütün alanların o anki değerini** varsayılana eşit olsa da
  `data/settings.yaml` dosyasına, ekranda olmayan anahtarları (`llm:` dahil) koruyarak yazar; bir kez
  kayıt yapmış kurulumda sonraki sürümün koddaki varsayılan değişikliği o kuruluma ulaşmaz. Ardından
  motor yenilenir; `indeks` etkili değişiklikler bellekteki `reindex_pending` listesine eklenir ve elle
  yeniden kurmayı bekler. Liste süreç yeniden başlayınca kaybolur ve açılış denetimi yalnız sözlük
  sürümüne baktığından indeks eski ağırlıklarla kalır. **Hedefte:** yalnız değiştirilmiş değerler
  saklanır (Requirement 4), indeksi etkileyen değişiklik kendiliğinden kurulur (Requirement 6), türler
  katıdır, hata 422'dir (Requirement 3).
- **Motoru yenileme** (`App.reload`): yeni motor (`Engine.from_index`) analiz kilidinin dışında kurulur
  ve tek atamayla değiştirilir; süren soru eski motorla biter (`test_settings_change_does_not_wait_for_a_running_question`);
  kolon özellikleri önbellekten yeniden kullanılır (`pipeline._features_for`). **Hedefte:** her
  değişiklik bu düzenle uygulanır (Requirement 12).
- **İndeks** (`index/store.py`, `index/bm25.py`, `pipeline.Engine`): `data/index` altında
  `columns.json`, `objects.json`, `bm25.json`, `meta.json` dosyaları (biçim 2). BM25 (kelime sıklığına
  dayalı arama yöntemi) kayıtları alan ağırlıklarını, `k1` ve `b` değerlerini ve (kolon özellikleri
  yoluyla) durak kelimeleri içerir; terim sözlüğü BM25'e girmez, yalnız sorgu genişletmede kullanılır;
  konu indeksi, terim genişletme ve analist kataloğu her motor kuruluşunda bellekte kurulur. `vsa serve`
  (`cli._index_problem`) indeks yoksa, okunamıyorsa, biçimi eskiyse ya da sözlük sürümü değiştiyse
  indeksi kurar ve HTTP sunucusunu ancak sonra açar. **Hedefte:** dosya yok; motor her açılışta
  PostgreSQL'den bellekte kurulur (Requirement 10).
- **Yeniden kurma** (`App.reindex`): `POST /api/reindex`, sözlük içe aktarma ve kelime listesi kaydı
  ya da içe aktarması çağırır. Ayarları yeniden okur, analiz kilidini (`App.lock`) alır: süren analizi
  (dakikalar) bekler ve yaklaşık 10 saniyelik kurulum boyunca yeni soruları “Sırada bekleme” adımında
  tutar; indeks dosyalarını yazıp yeniden yükler. Hata verirse yanıt HTTP 500
  `Sunucu hatası (ayrıntı sunucu kaydında)` olur; sözlük ya da liste dosyası çoktan yazılmış, motor eski
  kaldığından dosyalar ile motor bir sonraki başarılı kuruluma kadar ayrışır. **Hedefte:** önce kur,
  sonra yaz; analiz kilidi beklenmez (Requirement 11–12).
- **Durum** (`App.settings_get`, `admin.html` `indexState`): `GET /api/settings` sözlük sürümünü, son
  kurulum zamanını, kayıtlı cevap sayılarını (`AnswerStore.stats`, `cache_fingerprint(5)`) ve
  `reindex_pending` listesini döndürür; ekran `Güncel` / `Yeniden kurulmalı` / `Boş` durumunu bunlardan
  çıkarır ve durumu kendiliğinden yenilemez. **Hedefte:** ayrı indeks durumu ucu (Requirement 15).
- **Parmak izi** (`answer_cache.fingerprint`, ADR-035): `asdict(settings)` üzerinden `report`,
  `cache`, `index`, `dictionary` bölümleri ve iki liste yolu atılır; `llm` bölümünden yalnız `model`,
  `temperature`, `reasoning_effort`, `seed` kalır; üstüne biçim numarası, sözlük sürümü, terim grupları
  (`term`, eşdeğerler, `domain`, `note`), durak kelime kümesi, istenen tablo sayısı ve istemlerin
  özeti eklenir; SHA-256'nın ilk 16 karakteri. Böylece `cache.*` dışındaki her ayar değişikliği eski
  kayıtlı cevapları kullanılmaz kılar, değer geri alınınca eski cevaplar yeniden kullanılır.
  **Hedefte:** aynı (Requirement 7).
- **Kayıtlı cevapları silme** (`POST /api/admin/answers/clear`, `AnswerStore.clear`): dosyayı siler,
  silinen sayıyı döndürür; yedek tutulmaz. **Hedefte:** question-analysis'in `DELETE /saved-answers`
  ucu; Bakım sayfası onu kullanır (bu PRD'nin Requirement 16 ve 19'u).
- **Ekranda olmayan ayarlar**: `analyst.confusables`, `family_tables`, `family_extra`,
  `search_tables`, `evidence_columns`, `description_chars`, `full_table_columns` ve yalnız ölçümde
  kullanılan `scoring.min_answer_score`, `min_answer_coverage`, `rule_only_factor` yalnız
  `data/settings.yaml` elle düzenlenerek değişir. **Hedefte:** kodda sabit (Requirement 8,
  Decision 5).
- **Erişim** (`web/security.py` `AdminGuard`): `/admin`, `/api/admin`, `/api/settings`,
  `/api/reindex` ve `/api/llm` yolları `VSA_ADMIN_PASSWORD` ile HTTP Basic ister, parola yoksa
  yalnız sunucunun kendisinden açılır; POST istekleri `Sec-Fetch-Site`/`Origin` ile denetlenir.
  Uygulamadan yönetim ekranına bağlantı yoktur (ADR-047). **Hedefte:** oturum ve `yonetici` rolü
  (Requirement 26); başka siteden gelme denetimi bütün durum değiştiren isteklerde sürer
  ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 13);
  ana ekrandan yönetim ekranına yine bağlantı yoktur
  ([dictionary-explorer](../007-dictionary-explorer/PRD.md) Decision 15).
- **Yönetim ekranı kabuğu** (`web/static/admin.html`, ADR-051): kenar çubuğu, yedi sayfa,
  `#/sayfa/öğe` adresleri, Ctrl K komut paleti, sağdan açılan çekmece, alttaki kaydedilmemiş
  değişiklik çubuğu, masaüstünde tek ekran düzeni; tek dosya, dış kaynak yok. Görünüm kendi sabit
  renkleri ve degradeleriyle (“Evren” paleti) çizilir; onaylar tarayıcının `confirm()` penceresiyle
  alınır; tıklanabilir satırlar yalnız Enter ile açılır. **Hedefte:** React'te aynı işlev ve
  görünüm; onaylar yine tarayıcının `confirm()` penceresiyle (Requirement 20–25); kurallardan doğan,
  görünümü değiştirmeyen farklar Decision 10 ve 11'de.
- **Arama ve cevap, Bakım sayfaları**: Requirement 17–19'daki düzen. Bakım'da “Klasörler” kartı
  (`report.out_dir`, `index.dir`) vardır; uzman ayarları notu ve kural ipuçları bölümü
  `vsa eval --save` komutuna değinir. **Hedefte:** “Klasörler” kartı ve dosya ayarları kalkar, metinler
  değişir (Requirement 1, 17, 19).
- **Ana ekranın okuduğu ayar**: `GET /api/status`, Evren animasyonu için `analyst.shortlist` değerini
  döndürür. **Hedefte:** değer [question-analysis](../004-question-analysis/PRD.md) PRD'sinin durum
  ucunda (`GET /status`, `shortlist`) hizmetteki motorun ayarlarından, bu PRD'nin okuma işleviyle
  (Requirement 2) gelir; [dictionary-explorer](../007-dictionary-explorer/PRD.md) onu kullanır.
- **Kural 22 ile çelişki** (`rules/22-backend-yapilandirmasi.md`): kaynak ayarları komut satırında yolu
  verilen bir dosyadan okur ve `VSA_ADMIN_PASSWORD(_FILE)` değişkenini süreç ortamından doğrudan okur
  (`AdminGuard.from_env`); tipli tek ayar nesnesi yoktur. **Hedefte:** ortam yapılandırması yalnız
  iskeletin `DWHNAVIGATOR_` önekli tipli ayar nesnesinden (`app/backend/app/core/config.py`) okunur;
  arama ayarları ortam yapılandırması değil ürün verisidir; bu PRD yeni ortam anahtarı getirmez.
- **Kural 23 ile ilişki** (`rules/23-backend-onbellekleme.md`): (1) Bellekteki motor PostgreSQL'den
  türetilmiş veridir; kural 23'ün istediği dört öğe bu PRD'de tanımlıdır: işlem (motor kurulumu,
  Requirement 9), doğruluk sınırı (girdi kimliği, Requirement 9 ve 15), geçersiz kılma (değişiklik
  sırası, Requirement 11) ve kanıt (Test stratejisi). Motor isteğe bağlı bir hızlandırıcı değildir:
  motorsuz analiz yapılamaz, bu yüzden hata durumunda “açık çalışma” yerine hazırlık denetimi kapanır
  (Requirement 10). Redis kullanılmaz. (2) Kayıtlı cevaplar kural 23 anlamında bir önbellektir; anahtarı
  parmak izidir. Kaynakta anahtar başına kilit yoktur: aynı soru aynı anda iki kez sorulursa iki analiz
  de dakikalarca çalışır ve ikincisi öncekinin yerine yazılır (`AnswerStore.put`). Bu korumanın sahibi
  [question-analysis](../004-question-analysis/PRD.md)'tir. (3) Kaynak parmak izi fazla kapsamlıdır
  (terim grubunun `domain` ve `note` alanları cevabı etkilemez); yalnız gereksiz yeniden analize yol
  açtığı için korunur.

## İşlevsel gereksinimler

Requirement 1: Ayar şeması aşağıdaki 5 bölüm ve 24 alandan oluşur. Etki `anında` (yeni motor
mevcut kelime indeksiyle kurulur) ya da `indeks` (kelime indeksi yeniden hesaplanır); ikisinde de
değişiklik kayıtla birlikte kendiliğinden uygulanır (Requirement 6). Yüzde biçimli alan 0–1 değerini
`%NN` olarak gösterir. ¹ işaretli metinler kaynaktan farklıdır; kalan bütün etiket, açıklama ve yardım
metinleri kaynaktakiyle aynıdır.

**`analyst` — Analist** (Arama ve cevap). Açıklama: `Cevabı sohbet modeli yazar: katalogdan aday
seçer, sonra adayların kolonlarını okur; malzeme büyüdükçe yavaşlar.`

| Anahtar | Etiket | Tür | Varsayılan | Aralık · adım | Etki | Uzman | Yardım |
|---|---|---|---|---|---|---|---|
| `analyst.shortlist` | Kolonları okunacak aday tablo sayısı | tam sayı | 14 | 3–30 · 1 | anında | — | 1. adımda modelin seçebileceği en fazla tablo. |
| `analyst.detail_columns` | Tam açıklamasıyla okunan kolon sayısı (tablo başına) | tam sayı | 8 | 0–60 · 1 | anında | — | En ilgili bu kadar kolon tam açıklamayla, kalanı “Ad [Rol]: özet” olarak gider. |
| `analyst.min_confidence` | Gösterilecek en düşük model güveni | ondalık, yüzde | 0,5 | 0–1 · 0,05 | anında | — | Modelin bundan az emin olduğu tablolar önerilmez (“bulunamadı” geçerli cevap). |
| `analyst.max_tokens` | Cevap için en fazla token | tam sayı | 8000 | 1000–32000 · 500 | anında | evet | 2. adımda modelin yazabileceği en uzun cevap. |

**`terms` — Eş anlamlılar ve terimler** (Arama ve cevap). Açıklama: `İş biriminin kelimelerini
sözlüğe bağlar: “kredi” arayan “fon kullandırım”ı da bulur.`

| Anahtar | Etiket | Tür | Varsayılan | Aralık · adım | Etki | Uzman | Yardım |
|---|---|---|---|---|---|---|---|
| `expansion.enabled` | Kurumsal terim sözlüğünü kullan | açık/kapalı | açık | — | anında | — | Katılım bankacılığı terimleri ve kısaltmalar (Yönetim → Kelimeler). ¹ |
| `expansion.synonyms` | Sözlüğün eş anlamlılarını kullan | açık/kapalı | açık | — | anında | — | Sözlüğün Synonyms kolonundaki eş anlamlılar. |
| `expansion.weight` | Eş anlamlı terimlerin ağırlığı | ondalık, yüzde | 0,6 | 0–1 · 0,05 | anında | evet | Kullanıcının kendi yazdığı kelimeler %100 sayılır. |

**`ranking` — Kural ipuçları (tablo sıralaması)** (Arama ve cevap; bölümün tamamı uzman ayarı).
Açıklama: `Kural puanı (beş parça) modele ipucu olur, cevap yazmaz; değiştirmeden önce ve sonra altın
setle ölçün.` ¹

| Anahtar | Etiket | Tür | Varsayılan | Aralık · adım | Etki | Yardım |
|---|---|---|---|---|---|---|
| `scoring.object.best_column` | En iyi eşleşen kolon | ondalık | 0,35 | 0–1 · 0,05 | anında | Tablodaki en iyi kolonun talebe uyumu. |
| `scoring.object.coverage` | Kavramları birlikte taşıma | ondalık | 0,21 | 0–1 · 0,05 | anında | Talepteki kavramların kaçı aynı tabloda. |
| `scoring.object.topic` | Konu uyumu | ondalık | 0,30 | 0–1 · 0,05 | anında | Tablonun bütün olarak talebin konusu olması; çok geniş tabloları dengeler. |
| `scoring.object.time` | Zaman kolonu | ondalık | 0,07 | 0–1 · 0,05 | anında | “Aylık”, “günlük” istenirse dönem/tarih kolonu var mı. İstenmezse sayılmaz. |
| `scoring.object.granularity` | Müşteri seviyesi | ondalık | 0,07 | 0–1 · 0,05 | anında | Müşteri bazlı talepte müşteri anahtarı var mı. |
| `search.top_k_objects` | Değerlendirilen tablo sayısı | tam sayı | 20 | 3–50 · 1 | anında | Soru başına kural motorunun sıraladığı tablo sayısı (ipucu havuzu). |
| `scoring.min_candidate_score` | İpucu listesine girecek en düşük kural puanı | ondalık, yüzde | 0,5 | 0–1 · 0,05 | anında | Bunun altındaki tablolar modele ipucu olarak gösterilmez. |

**`words` — Kelime araması** (Arama ve cevap; bölümün tamamı uzman ayarı). Açıklama: `Kolon adı, eş
anlamlı ve açıklamalarda BM25 araması; değerler indekse gömülü, değişince indeks yeniden kurulur.`

| Anahtar | Etiket | Tür | Varsayılan | Aralık · adım | Etki | Yardım |
|---|---|---|---|---|---|---|
| `search.field_weights.name` | Kolon adı ağırlığı | ondalık | 3,0 | 0–10 · 0,5 | indeks | — |
| `search.field_weights.synonyms` | Eş anlamlılar ağırlığı | ondalık | 2,0 | 0–10 · 0,5 | indeks | — |
| `search.field_weights.description` | Açıklama ağırlığı | ondalık | 1,0 | 0–10 · 0,5 | indeks | — |
| `search.field_weights.object` | Tablo adı ağırlığı | ondalık | 1,0 | 0–10 · 0,5 | indeks | — |
| `search.candidate_object_columns` | Aday tablo için taranan kolon | tam sayı | 1000 | 50–3000 · 50 | anında | Kavramları birlikte taşıyan tablolar kaçmasın diye geniş tutulur. |
| `search.bm25.k1` | BM25 k1 | ondalık | 1,2 | 0,1–3 · 0,1 | indeks | Aynı kelimenin tekrarı ne kadar sayılsın. |
| `search.bm25.b` | BM25 b | ondalık | 0,75 | 0–1 · 0,05 | indeks | Uzun açıklamalar ne kadar dengelensin. |

**`cache` — Önceki cevaplar** (Bakım). Açıklama: `Aynı ya da aynı anlamdaki soru analiz yerine kayıtlı
cevabı alır; sözlük, model ya da ayar değişince eskiler kullanılmaz.`

| Anahtar | Etiket | Tür | Varsayılan | Aralık · adım | Etki | Uzman | Yardım |
|---|---|---|---|---|---|---|---|
| `cache.enabled` | Önceki cevapları kullan | açık/kapalı | açık | — | anında | — | Kapalıyken her soru baştan analiz edilir; cevaplar yine saklanır. |
| `cache.meaning` | Aynı anlama gelen sorularda da kullan | açık/kapalı | açık | — | anında | — | Kelimesi farklı, kavramı aynı soru (ör. “müşteri no” / “hesap no”); kapalıyken yalnız aynı kelimeler. |
| `cache.max_age_days` | Cevap kaç gün geçerli | tam sayı | 30 | 0–365 · 1 | anında | evet | Daha eski cevaplar yeniden analiz edilir. 0 = süre sınırı yok. |

Kaynaktaki beş alan hedefte yoktur: `dictionary.store` (Sözlük sayfası), `expansion.term_dictionary` ve
`expansion.stopwords` (Kelimeler sayfası), `report.out_dir` ve `index.dir` (Bakım, “Klasörler”). Sözlük
ve listeler PostgreSQL'dedir, indeks bellektedir, Excel raporları saklanmaz.

Requirement 2: `GET /search-settings` şemayı (bölümler; her alanın anahtarı, etiketi, yardımı, türü,
biçimi, aralığı, adımı, etkisi, uzman işareti), 24 alanın etkin değerini ve varsayılanını döndürür.
Hizmetteki motorun ayarlarını başka yeteneklere veren tek okuma işlevi vardır (ör. durum ucundaki
`analyst.shortlist` değeri, [question-analysis](../004-question-analysis/PRD.md) Requirement 17; ana
ekranda [dictionary-explorer](../007-dictionary-explorer/PRD.md) kullanır); bu işlev veritabanındaki
değeri değil, hizmetteki motorun değerini verir.

Requirement 3: `PATCH /search-settings` `{"values": {"<anahtar>": <değer>}}` kabul eder ve her
anahtarı denetler: şemada olmayan anahtar `Bilinmeyen ayar: <anahtar>`; açık/kapalı alanda JSON
`true`/`false` dışı değer `<etiket>: açık/kapalı olmalı`; sayı alanında JSON sayısı dışı değer (metin
ve `true`/`false` dahil) `<etiket>: sayı olmalı`; tam sayı alanında küsuratlı değer
`<etiket>: tam sayı olmalı`; aralık dışı değer `<etiket>: <en az> ile <en çok> arasında olmalı`
(sınırlar kaynaktaki gibi `0.1` biçiminde yazılır). Bütün hatalar `; ` ile birleşerek tek 422 yanıtında
döner; kod, bilinmeyen anahtar varsa `search_setting_unknown`, yoksa `search_setting_invalid` olur.
Bir anahtar bile geçersizse hiçbir değer yazılmaz. Boş `values` hiçbir şey değiştirmez ve 200 döner.

Requirement 4: Saklanan değer yalnız varsayılandan farklı olandır: kaydedilen değer varsayılana
eşitse o anahtarın saklanan değeri yazılımsal silinir (silindi olarak işaretlenir, okunmaz). Etkin
değer koddaki varsayılanın üstüne saklanan değerin konmasıyla bulunur. Koddaki bir varsayılan sonraki sürümde değişirse (altın setle ölçülerek),
o anahtarı değiştirmemiş her kurulum yeni varsayılanı kullanır.

Requirement 5: Süreç açılışında saklanan her değer şemaya karşı Requirement 3 kurallarıyla denetlenir.
Şemada olmayan anahtar ya da türü veya aralığı uymayan değer varsa `search_settings.startup_invalid`
olayı (anahtar ve neden sınıfı; değer yazılmaz) yazılır ve süreç hazır olmadan sıfırdan farklı çıkış
koduyla durur. Bir ayarı kaldıran ya da aralığını daraltan sürüm, aynı değişiklikte saklanan değeri
silen göçü (veritabanı yapısını ve verisini sürüm sürüm kuran betik) içerir.

Requirement 6: Ayar kaydı Requirement 11'deki değişiklik sırasından geçer: etkin değerlerle yeni
motor kurulur; kurulum başarılıysa saklanan değerler tek veritabanı işleminde (hep ya da hiç yazılan
işlem) yazılır ve yeni motor hizmete alınır. Yanıt döndükten sonra başlayan her analiz yeni değerleri
kullanır. `indeks` etkili altı alandan biri değişmişse kelime indeksi yeniden hesaplanır; yalnız
`anında` etkili alanlar değişmişse yeni motor mevcut kelime indeksini kullanır. Hiçbir etkin değer
değişmiyorsa yazma ve kurulum yapılmaz ve yanıt `changed: []` olur. Yanıt değişen anahtarları, etkin
değerleri, toplam süreyi (`elapsed_ms`) ve indeks durumunu taşır.

Requirement 7: Kayıtlı cevap parmak izine ([question-analysis](../004-question-analysis/PRD.md)) bu
PRD'nin ayarlarından `cache.*` dışındaki 21 şema alanı ve Requirement 8'deki 10 sabit girer;
`cache.enabled`, `cache.meaning` ve `cache.max_age_days` girmez, çünkü cevabı değil, kayıtlı cevabın
kullanılıp kullanılmayacağını belirler. Parmak izinin model bölümü (`model`, `temperature`,
`reasoning_effort`, `seed`) [llm-connection](../003-llm-connection/PRD.md) PRD'sinin etkin sohbet
modeli yapılandırmasından okunur. Parmak izi içerikten hesaplanır: bir ayar eski değerine dönerse o
değerle yazılmış kayıtlı cevaplar yeniden kullanılabilir. Parmak izi kaynaktaki
`answer_cache.fingerprint` işleviyle aynı girdilerden aynı biçimde hesaplanır ve aynı girdilerle aynı
değeri verir. Kayıtlı cevabın saklanması, aranması ve süresi question-analysis PRD'sindedir.

Requirement 8: Ekranda olmayan şu ayarlar kodda sabittir; hiçbir uç, dosya ya da ortam değişkeni
onları değiştiremez; değişiklik kod değişikliği ve altın set ölçümü ister (Decision 5):
`analyst.confusables` 6 (uyarılar için okunan benzer tablo), `analyst.family_tables` 2 (bilgi ailesi
başına terim aramasıyla eklenen tablo), `analyst.family_extra` 6 (bu yolla en fazla eklenen tablo),
`analyst.search_tables` 3 (1. adımın seçmediği, kelime aramasının en iyi tabloları),
`analyst.evidence_columns` 60 (bütün sözlükten benzer kolon), `analyst.description_chars` 420 (kolon
açıklaması başına karakter), `analyst.full_table_columns` 90 (bundan geniş tablolarda yalnız ilgili
kolonlar), `scoring.min_answer_score` 0,35, `scoring.min_answer_coverage` 0,5 ve
`scoring.rule_only_factor` 0,8 (son üçü yalnız ölçümde kullanılan kural cevabını şekillendirir).

Requirement 9: Bu PRD'de **arama indeksi**, backend sürecinin belleğinde kurulan arama yapılarının
tamamıdır: kolonların kelime özellikleri, BM25 kelime indeksi (kelime sıklığına dayalı arama yöntemi),
tablo konu indeksi, terim genişletme ve bunları kullanan motor (`Engine`); alan tanımındaki “arama
indeksi” bunun BM25 kısmıdır ve hepsi birlikte kurulup değiştirilir. Motorun **girdi kimliği** sözlük sürümünden
([dictionary-management](../001-dictionary-management/PRD.md)), terim ve durak kelime listelerinin
içerik özetlerinden ([vocabulary-management](../002-vocabulary-management/PRD.md) Requirement 1) ve
etkin ayarların içerik özetinden oluşur. Kurulum bütün girdileri tek tutarlı veritabanı görüntüsünden
okur. Girdilerin hangisinin kurulumu nasıl etkilediği:

| Değişiklik | Sahibi | Kelime indeksi yeniden hesaplanır mı | Tetikleyici adı |
|---|---|---|---|
| Süreç açılışı | bu PRD | evet | `startup` |
| Sözlük içe aktarma (yeni sözlük sürümü) | dictionary-management | evet | `dictionary` |
| Terim sözlüğü | vocabulary-management | hayır; terim genişletme yenilenir | `terms` |
| Durak kelimeler | vocabulary-management | evet | `stopwords` |
| `indeks` etkili ayar | bu PRD | evet | `settings` |
| Yalnız `anında` etkili ayar | bu PRD | hayır | `settings` |
| Elle yeniden kurma | bu PRD | evet | `manual` |
| Etkin sohbet modeli | llm-connection | kurulum yapılmaz | — |

Requirement 10: Süreç açılınca, veritabanı hazır olduğunda (iskeletin hazırlık denetimindeki koşul:
çalışma rolü bağlanır ve şema imajdaki göç başına ulaşmıştır) saklanan ayarları denetler
(Requirement 5) ve ilk motoru kurar (`startup`). İlk motor kurulana kadar
`/api/dwhnavigator/v1/readiness` (hazırlık denetimi) 503, `/api/dwhnavigator/v1/liveness` (canlılık
denetimi) 200 döner; analiz başlatma isteği [question-analysis](../004-question-analysis/PRD.md)
üzerinden 503 `search_index_not_ready` (`Arama indeksi hazırlanıyor; birkaç saniye sonra yeniden
deneyin.`) alır; değişiklik istekleri sırada bekler. Sözlük henüz içe aktarılmadıysa motor 0 kolonla
kurulur ve soru kaynaktaki `Sözlük henüz içe aktarılmadı…` sebebini alır. İlk kurulum hata verirse
`search_index.build` olayı `failed` sonucuyla yazılır ve süreç sıfırdan farklı çıkış koduyla durur.

Requirement 11: Arama verisini değiştiren her işlem — sözlük içe aktarma, terim ve durak kelime
kaydı ve içe aktarması, ayar kaydı ve elle yeniden kurma — süreç içindeki tek değişiklik sırasından
geçer; aynı anda yalnız bir değişiklik uygulanır. Adımlar: (1) sıra gelince güncel girdiler tek
tutarlı veritabanı görüntüsünden okunur ve değişiklik bellekte uygulanır; (2) yeni motor hizmetteki
motorun yanında kurulur; (3) kurulum başarılıysa değişiklik tek veritabanı işleminde yazılır; (4)
yazma başarılıysa yeni motor tek atamayla hizmete alınır ve istek yanıt döner. (2) ya da (3) hata
verirse hiçbir şey yazılmaz, hizmetteki motor değişmez, son başarısız deneme durumda görünür ve
istek 500 `search_index_build_failed` (`Arama indeksi kurulamadı; değişiklik kaydedilmedi.`) alır.
Sırada 20 saniyeden uzun bekleyen istek hiçbir şey yazılmadan 503 `search_change_busy`
(`Başka bir değişiklik uygulanıyor; biraz sonra yeniden deneyin.`) alır; sırada bekleme ve kurulum
(Requirement 13) birlikte
[kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
Requirement 12'deki 60 saniye kuralının altında kalır. Başlamış bir değişiklik, istemci bağlantıyı
kopardığında da yarıda kalmaz: tamamlanır ya da hiç yazılmaz. Girdi kimliği değişmeyen istek kurulum
yapmadan döner; elle yeniden kurma bunun dışındadır.

Requirement 12: Kurulum analiz kilidini (question-analysis'teki “tek motor, tek kilit” sırası) almaz;
süren ya da sırada bekleyen analizi beklemez, analizler de kurulumu beklemez. Bir analiz, çalışmaya
başladığı anda hizmette olan motoru sonuna kadar kullanır; sırada bekleyen analiz motoru sırası gelince
alır. Toplu aramada ([list-search](../005-list-search/PRD.md)) her terim kendi analizi başlarken motoru
alır. Sözlük gezgini ve Evren okumaları ([dictionary-explorer](../007-dictionary-explorer/PRD.md)) istek
anında hizmetteki motoru kullanır ve analiz kilidini beklemez. Kurulum sürerken API istekleri yanıt
vermeye devam eder; `/liveness` 1 saniye içinde döner.

Requirement 13: Değişmeyen parçalar (kolon özellikleri, kelime indeksi) yeniden kullanılsa da kurulan
motor, aynı girdilerle baştan kurulmuş motorla aynı sonucu verir: aynı sorularda kural sıralaması ve
modele giden istemler bayt bayt aynıdır. Gerçek sözlükle (yaklaşık 11 bin kolon) nonprod'da tam kurulum
en çok 30 saniye, yalnız `anında` etkili ayar değişikliği en çok 15 saniye sürer (kaynakta tam kurulum
yaklaşık 10 saniye); böylece sırada bekleme dahil her değişiklik isteği 60 saniyenin altında biter.

Requirement 14: Bakım sayfasındaki `Arama indeksini yeniden kur` düğmesi ve komut paletindeki aynı
işlem (`POST /search-index/rebuilds`) güncel girdilerle motoru, girdiler değişmemiş olsa da baştan kurar
(`manual`). Başarılıysa `Arama indeksi kuruldu` / `N kolon · M tablo · X sn`, değilse
`İndeks kurulamadı` ve sunucunun iletisi bildirilir.

Requirement 15: `GET /search-index` şu alanları döndürür: `state` (`building`: ilk kurulum ya da bir
değişiklik sürüyor; `ready`: hizmetteki motorun girdi kimliği veritabanındakiyle aynı; `stale`: değişiklik
sürmediği hâlde kimlikler farklı), `stale_inputs` (farklı girdiler: `dictionary`, `terms`, `stopwords`,
`settings`), hizmetteki motorun `columns`, `objects`, `dictionary_version`, `built_at`, `build_ms` ve
`trigger` değerleri, süren değişikliğin türü ve başlangıç zamanı, son başarısız denemenin zamanı ve türü.
Hata metni ve içerik döndürülmez. Tek kopya varsayımı altında `stale` yalnız veritabanı başka bir süreç
ya da elle değiştirildiğinde görülür; ilk görülüşünde `search_index.stale_detected` olayı yazılır, düzeltme
elle yeniden kurmadır.

Requirement 16: Bakım sayfasının kayıtlı cevap bloğu (Requirement 19) kayıtlı cevap özetini ve silmeyi
[question-analysis](../004-question-analysis/PRD.md) Requirement 15'teki `GET /saved-answers/summary`
(`total`, `usable`, `newest_at`) ve `DELETE /saved-answers` (`removed`) uçlarıyla okur ve yapar;
uçların, saklamanın ve silme biçiminin sahibi question-analysis'tir. Silinen cevap geri gelmez;
sonraki sorular baştan analiz edilir.

Requirement 17: **Arama ve cevap** sayfası (`/admin/arama`): başlık `Arama ve cevap`, açıklama
`Analistin okuyacağı malzeme ve arama ipuçları; değişiklikler “Kaydet ve uygula” ile geçerli olur.`.
Uzman olmayan bölümler (Analist, Eş anlamlılar ve terimler) kart olarak sıralanır; kart içindeki uzman
alanlar `Uzman ayarları (N)` başlıklı katlanır bölümdedir. Ardından `Uzman ayarları` alanı gelir: not
`Çoğu durumda değiştirmek gerekmez; önce ve sonra altın setle ölçün.` ¹ ve her uzman bölümü (Kural
ipuçları, Kelime araması) başlığı ve `N ayar` etiketiyle katlanır; açılınca bölüm açıklaması ve alanlar
görünür.

Requirement 18: Her ayar satırı etiketi (ipucunda anahtar), `indeks` etkili alanda `indeks` etiketini
(ipucu `Kaydedince arama indeksi yeniden kurulur` ¹), tek satırlık yardım metnini (tamamı ipucunda) ve
türüne göre denetimi gösterir: açık/kapalı alanda anahtar düğme; yüzde alanında kaydırıcı ve `%NN`
okuması; öteki sayılarda kaydırıcı ve sayı kutusu (adım 0,1'den küçükse iki, 1'den küçükse bir ondalık).
`↺` düğmesi değeri varsayılana döndürür (ipucu `Varsayılana dön: <değer>`). Kaydedilmemiş değişikliği
olan satır ve varsayılandan farklı değer taşıyan satır ayrı işaretlerle gösterilir. Değişiklik hemen
kaydedilmez, kabuktaki taslağa girer (Requirement 23).

Requirement 19: **Bakım** sayfası (`/admin/bakim`): başlık `Bakım`, açıklama
`Arama indeksi ve önceki cevaplar.` ¹, sağda Sözlük sayfasına giden `Sözlük` (sözlük yoksa
`Sözlüğü içe aktar`) bağlantısı. **Arama indeksi** kartı: durum etiketi (`Güncel`, `Kuruluyor`,
`Yeniden kurulmalı`, 0 kolonda `Boş`), açıklama
`Sözlükten üretilen kelime indeksi; içe aktarmada kendiliğinden, terim / durak kelime / ağırlık değişince yeniden kurulur.`,
`Sözlük` satırı (`N kolon · sürüm XXXXXXXX`, sözlük yoksa `yok`), `Son kurulum` satırı (zaman ya da
`—`), `stale` durumunda `İndeks veritabanıyla uyuşmuyor: <farklı girdiler>.`, son deneme başarısızsa
`Son kurulum denemesi başarısız oldu (<zaman>); değişiklik kaydedilmedi.`,
`Arama indeksini yeniden kur` düğmesi (`stale` durumunda birincil) ve `birkaç saniye` notu. **Önceki
cevaplar** kartı: `cache` bölümünün alanları ve altında `Kayıtlı cevaplar` bloğu: `Kayıtlı` satırı
(`N · bugünkü sözlük, model ve ayarlarla geçerli: M`, hiç yoksa `henüz yok`), `En yeni` satırı, not
`Silmek gerekmez: değişiklikte eskiler zaten kullanılmaz; tek yanlış cevap için uygulamada “Yeniden analiz et” yeterli.`
ve kayıtlı cevap yokken devre dışı `Önceki cevapları sil…` düğmesi. Düğme onay penceresinde
`Kayıtlı N cevap silinsin mi?` ve
`Sonraki sorular baştan analiz edilir. Silinen cevaplar geri gelmez.` der (tarayıcının onay
penceresi, Requirement 24); sonuçta `Önceki cevaplar silindi` / `N cevap silindi.` ya da
`Silinemedi` bildirimi çıkar. Kaynaktaki “Klasörler” kartı yoktur.

Requirement 20: Yönetim ekranı kabuğu, uygulamanın istemci yönlendiricisinde `/admin` altında
çalışır: `/admin` adresi `/admin/genel`'e yönlenir; sayfalar `/admin/genel`, `/admin/analizler`,
`/admin/sozluk`, `/admin/kelimeler`, `/admin/yapay-zeka`, `/admin/arama`, `/admin/bakim` ve yalnız
süper yöneticiye açık `/admin/kullanicilar`
([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) Requirement 16); öğe
adresleri `/admin/analizler/<public_id>` ([analysis-records](../008-analysis-records/PRD.md)) ve
`/admin/sozluk/<DB.Şema.Obje>` ([dictionary-management](../001-dictionary-management/PRD.md))
sayfayı açıp öğenin çekmecesini gösterir; yeni sekmede de aynı öğeyi açar. Bilinmeyen `/admin/...`
adresi uygulamanın “bulunamadı” sayfasını gösterir. Kabuk yalnız `yonetici` için açılır; başka rol
iskeletin “yetkisiz” ekranını görür. Tarayıcı sekmesinin başlığı `<Sayfa adı> · DWH Navigator`'dır;
sayfa değişince açık çekmece kapanır ve sayfa başa kayar.

Requirement 21: Kenar çubuğu: üstte logo, `DWH Navigator` ve `Yönetim` (Genel bakış'a gider);
`Ara veya git…` düğmesi ve `Ctrl K` işareti; menü üç grupta: `İzleme` (Genel bakış —
`Sistem sağlığı ve son etkinlik`; Analizler — `Sorulan sorular, cevaplar ve adım adım süreler`),
`Veri ve model` (Sözlük — `Veri sözlüğü: içe/dışa aktarma ve tablolar`; Kelimeler —
`Terim sözlüğü ve durak kelimeler`; Yapay zekâ — `Cevabı yazan sohbet modeli ve bağlantıları`),
`Ayarlar` (Arama ve cevap — `Analistin okuduğu malzeme ve arama ipuçları`; Bakım —
`Arama indeksi ve önceki cevaplar` ¹; grubun sonunda yalnız süper yöneticiye görünen Kullanıcılar,
sayfası user-accounts Requirement 16'dadır; fabrikanın zorunlu kıldığı bu öğe öteki menü öğeleriyle
aynı görünümdedir); açıklamalar ipucudur, geçerli sayfa işaretlidir. Menü rozetleri: Yapay zekâ'da
model durumu noktası (llm-connection durumu), Sözlük'te sözlük içe aktarılmamışsa `!`, Arama ve
cevap'ta kaydedilmemiş ayar sayısı, Bakım'da kaydedilmemiş ayar sayısı ya da indeks `stale` ise `!`.
Altta sistem durumu üç satırdır: sohbet modeli (model adı, `Model yanıt vermiyor` ya da
`Model bağlı değil`; [llm-connection](../003-llm-connection/PRD.md)), sözlük (`N tablo · M kolon` ya
da `Sözlük yok`; dictionary-management), indeks (`İndeks güncel`, `İndeks kuruluyor`,
`İndeks yeniden kurulmalı` ya da `İndeks boş`); sistem durumunun altında oturum alanı (görünen ad,
`Parolamı değiştir` ve `Çıkış`; davranışı user-accounts Requirement 16'dadır; fabrikanın zorunlu
kıldığı bu alan kaynağın kenar çubuğu biçimine en az müdahaleyle, sistem durumu satırlarıyla aynı
görünüm ve belirteçlerle yerleşir); en altta `← Uygulamaya dön` (ana ekran `/`). Durumlar kabuk
açılınca, sayfa değişince ve her işlemden sonra okunur; indeks `building` iken 2 saniyede bir
yeniden okunur.

Requirement 22: Komut paleti `Ctrl K` (macOS'ta `Cmd K`) ya da `Ara veya git…` düğmesiyle açılır ve
kapanır; arama kutusu `Sayfa, ayar, işlem, tablo ya da soru ara…`. Boş aramada `Sayfalar` ve `İşlemler`
gösterilir. Yazılan metin Türkçe katlanır ve boşluktan bölünür; her kelimesi başlıkta ya da alt yazıda
geçen öğe eşleşir; sıralama kelime başına başlıkta geçerse 3, alt yazıda geçerse 1 puan ve başlık o
kelimeyle başlıyorsa ek 2 puandır; en çok 60 sonuç grup başlıklarıyla gösterilir, eşleşme yoksa
`Eşleşen bir şey yok.`. ↑/↓ seçer, Enter çalıştırır, Esc ya da dışına tıklama kapatır; altta `↑↓ seç`,
`Enter git`, `Esc kapat` yazar. Gruplar ve öğeler: `Sayfalar` (yedi sayfa; süper yöneticide
Kullanıcılar da), `İşlemler` (Requirement 25
tablosu), `Ayarlar` (24 alanın her biri; alt yazı `<sayfa> · <bölüm> — <yardım>`; seçince sayfa açılır,
katlanmış bölüm açılır, satır ortaya kaydırılıp kısa süre vurgulanır ve denetimine odaklanılır),
`Tablolar` (sözlük tabloları; dictionary-management) ve `Son sorular` (en yeni 200 analiz;
analysis-records).

Requirement 23: Ayar değişiklikleri kabuğa bağlı bir taslakta tutulur ve yönetim sayfaları arasında
gezinirken korunur; sunucudan yeni değerler okunduğunda kaydedilmemiş taslak değerleri kalır. Taslakta
en az bir değişiklik varsa altta çubuk görünür: `N değişiklik kaydedilmedi`, değişiklik olan sayfaların
adları, `Geri al` (bütün taslak kayıtlı değerlere döner) ve `Kaydet ve uygula` (değişen bütün
anahtarlarla tek `PATCH`; sürerken `Kaydediliyor…`). Başarıda `Kaydedildi ve uygulandı` ve
`Değişen: <etiketler>` (yoksa `—`) satırı, kelime indeksi yeniden hesaplandıysa
`Arama indeksi yeniden kuruldu (X sn).` ¹ satırı; hatada `Kaydedilemedi` ve sunucunun iletisi
bildirilir ve taslak korunur. Kaydedilmemiş ayar ya da liste değişikliği
([vocabulary-management](../002-vocabulary-management/PRD.md)) varken yönetim ekranından çıkmak
(`← Uygulamaya dön`, sekmeyi kapatma, yenileme) onay ister; yönetim sayfaları arasında geçiş onay
istemez.

Requirement 24: Çekmece sağdan açılan, odağı içinde tutan bir pencere panelidir: başlık, isteğe bağlı
alt yazı, gövde, isteğe bağlı alt düğme alanı ve geniş türü vardır; açılınca ilk giriş alanına odaklanır;
Esc, `Kapat (Esc)` düğmesi, dışına tıklama ya da sayfa değişimiyle kapanır. Klavye: Esc önce paleti,
sonra çekmeceyi kapatır; yazı alanında değilken ve palet ya da çekmece açık değilken `/` sayfanın arama
kutusuna odaklanır. Bildirimler kaynaktaki bildirim görünümüyle gösterilir (başarı yaklaşık 6,5, hata 11
saniye görünür). Sunucuya ulaşılamazsa en çok 15 saniyede bir `Sunucuya ulaşılamadı` /
`Bağlantıyı denetleyip sayfayı yenileyin.` bildirimi çıkar; ağ hatası oturumu kapatmaz (rules/31).
Onaylar kaynaktaki gibi tarayıcının `confirm()` penceresiyle alınır; metinleri `tr.json`'dadır.

Requirement 25: Masaüstünde (en az 921 piksel genişlik ve 600 piksel yükseklik) her sayfa tek ekrandır:
sayfa pencere yüksekliğini doldurur; başlık ve özetler yerinde durur; uzun listeler (analizler,
tablolar, terimler, durak kelimeler, son sorular, entegrasyonlar) kendi içinde kayar; ayar sayfaları
genişliğe göre en az 460 piksellik 2–3 sütuna dizilir; sayfa genişlik sınırı yoktur; sayfa ve kart
açıklamaları ile yardım metinleri tek satırdır, tamamı ipucundadır; kaydedilmemiş değişiklik çubuğu
göründüğünde sayfa ona yer açar. 920 piksel ve daha dar ekranda kenar çubuğu üst çubuğa dönüşür: menü
yana kayar, grup başlıkları ve sistem durumu gizlenir, `Ara veya git…` tam genişliktedir; açıklamalar
sarılır. 600 pikselden alçak ekranda ve telefonda normal sayfa akışı sürer. Sayfalar kabuğa şu katkılarla
takılır; bu PRD yalnız kabuğu ve kendi iki sayfasını tanımlar, öteki sayfaların içeriği sahiplerinindir:

| Sayfa | Sahibi | Rozet | Komut paleti katkısı |
|---|---|---|---|
| Genel bakış | [analysis-records](../008-analysis-records/PRD.md) | — | — (indeks kartı bu PRD'nin Requirement 15'ini, kayıtlı cevap kartı question-analysis Requirement 15'i okur) |
| Analizler | analysis-records | — | `Performans ayrıntıları`; `Son sorular` öğeleri |
| Sözlük | [dictionary-management](../001-dictionary-management/PRD.md) | sözlük yoksa `!` | `Sözlüğü Excel'den içe aktar`, `Sözlüğü Excel olarak dışa aktar`, `Boş sözlük şablonunu indir`; `Tablolar` öğeleri |
| Kelimeler | [vocabulary-management](../002-vocabulary-management/PRD.md) | — | — |
| Yapay zekâ | [llm-connection](../003-llm-connection/PRD.md) | model durumu | `Yeni model entegrasyonu`, `Model envanteri` |
| Arama ve cevap | bu PRD | kaydedilmemiş ayar sayısı | `Ayarlar` öğeleri |
| Bakım | bu PRD | kaydedilmemiş ayar sayısı ya da `!` | `Arama indeksini yeniden kur` |
| Kullanıcılar (yalnız süper yönetici) | [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md) | — | — |
| (kabuk) | bu PRD | — | `Uygulamaya dön` |

Paletten başlatılan indirmeler (sözlük ve şablon) sahibinin ucunu ortak API istemcisiyle, oturum
belirteci başlıkta gönderilerek çağırır (user-accounts Requirement 12).

Requirement 26: Bu PRD'nin bütün uçları `yonetici` rolü ister; `kullanici` 403, oturumsuz istek 401
alır. Arama ve cevap, Bakım ve kabuğun menüsü yalnız `yonetici`'ye görünür; bu gizleme yetki
denetiminin yerini tutmaz.

## API sözleşmesi

Bütün uçlar `/api/dwhnavigator/v1` altındadır ve hazırlık ile canlılık denetimi dışında geçerli oturum
ve `yonetici` rolü ister. OpenAPI (API tanım dosyası) `specs/openapi/dwhnavigator-api.yaml` ve üretilmiş
ön yüz tipleri aynı değişiklikte güncellenir. Hata gövdesi tek hata zarfıdır:
`{"detail":{"code":"...","message":"..."}}`.

| Yöntem ve yol | İstek özü | Yanıt özü | Hatalar |
|---|---|---|---|
| `GET /search-settings` | — | `sections[]` (`id`, `page` `search`/`data`, `title`, `intro`, `advanced`, `fields[]`: `key`, `label`, `help`, `type` `bool`/`int`/`float`, `format`, `min`, `max`, `step`, `effect` `immediate`/`reindex`, `advanced`), `values{}`, `defaults{}` | 401, 403 |
| `PATCH /search-settings` | `values{}` | `changed[]`, `values{}`, `elapsed_ms`, `index` | 422 `search_setting_unknown`, `search_setting_invalid`; 500 `search_index_build_failed`; 503 `search_change_busy` |
| `GET /search-index` | — | Requirement 15 alanları | 401, 403 |
| `POST /search-index/rebuilds` | — | Requirement 15 alanları, `elapsed_ms` | 500 `search_index_build_failed`; 503 `search_change_busy` |
| `GET /readiness` (iskeletin; oturumsuz) | — | ilk motor kurulana kadar 503 | — |

`index` alanı `GET /search-index` yanıtıdır. Bakım sayfasının kullandığı `GET /saved-answers/summary` ve
`DELETE /saved-answers` [question-analysis](../004-question-analysis/PRD.md) PRD'sinin uçlarıdır
(bu PRD'nin Requirement 16'sı). Ekran `search_setting_unknown` ve
`search_setting_invalid` kodlarında sunucunun Türkçe iletisini olduğu gibi gösterir (Decision 12).
Değişiklik sırasını kullanan öteki uçlar (sözlük içe aktarma, liste kaydı ve içe aktarması) 500
`search_index_build_failed` ve 503 `search_change_busy` kodlarını aynı anlamla döndürür.

## Güvenlik ve yetkilendirme

- Rol denetimi her uçta arka uçtadır ([user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md));
  kaynaktaki `AdminGuard` parolası ve “yalnız bu makineden” kuralı yerine oturum belirteci (istek
  başlığında taşınan imzalı kimlik) ve rol gelir; `Sec-Fetch-Site`/`Origin` denetimi bütün durum
  değiştiren isteklerde sürer (user-accounts Requirement 13). Ön yüzdeki gizleme kolaylıktır.
- Ayar değerleri yalnız sayı ve açık/kapalıdır; sır taşımaz. Model anahtarı ve adresi bu PRD'nin hiçbir
  ucundan okunamaz ya da yazılamaz.
- Kayıtlı cevapları silmek geri alınamaz; onay penceresinden geçer ve yapan olay kaydına yazılır.
- Kurulum hatası kullanıcıya yalnız kod ve sabit Türkçe iletiyle döner; istisna metni, yığın izi ya da
  veritabanı ayrıntısı yanıta ve ize girmez (rules/57).
- Sorgular parametrelidir ve etkin kiracı (`platform`) kapsamında çalışır.

## Veri ve geçiş

- Yeni tablo `search_setting`, Alembic göçüyle eklenir: kiracı, `setting_key` (şema anahtarı), `value`
  (JSON değeri) ve zorunlu sütun bloğu (rules/41). Kayıt bir anahtar-değer eşlemidir; kimliği kararlı
  doğal anahtar `setting_key`'dir ve `public_id` taşımaz (rules/41'in eşlem tabloları için tanıdığı
  biçim). Silinmemiş satırlarda kiracı içinde `setting_key` tekildir. Değer varsayılana dönünce satır
  yazılımsal silinir. Tablo ve sütun açıklamaları (rules/43) göçe girer.
- Arama indeksi saklanmaz; kayıtlı cevap tablosu question-analysis'in, liste tabloları
  vocabulary-management'ın, sözlük tabloları dictionary-management'ındır.
- Kaynak `data/settings.yaml` taşınmaz (kurulu bir kaynak sürüm yoktur); kaynağın ölçülmüş varsayılanları
  koddaki varsayılanlardır.

## Gözlemlenebilirlik

- Log olayları: `search_index.build` (tetikleyici, sonuç `ok`/`failed`, süre, kolon ve tablo sayısı,
  hata sınıfı), `search_change.busy` (tetikleyici), `search_index.stale_detected` (farklı girdiler),
  `search_settings.changed` (değişen anahtarlar, etki `immediate`/`reindex`, kullanıcı `public_id`),
  `search_settings.startup_invalid` (anahtar, neden sınıfı). Kayıtlı cevap silme olayı
  question-analysis'tedir (`saved_answer.cleared`). Ayar değeri, sözlük ya da liste içeriği ve hata
  metni yazılmaz.
- Ölçümler: `dwhnavigator_search_index_builds_total{trigger,outcome}`,
  `dwhnavigator_search_index_build_duration_seconds{trigger}` (dağılım),
  `dwhnavigator_search_index_ready` (hizmette motor varsa ve durum `ready` ise 1, değilse 0) ve
  `dwhnavigator_search_changes_total{trigger,outcome}`. `trigger` `startup`, `dictionary`, `terms`,
  `stopwords`, `settings`, `manual`; `builds_total` için `outcome` `ok`/`failed`, `changes_total` için
  `applied`, `unchanged`, `failed`, `busy`; kümede olmayan değer `other` olarak yazılır. Kullanıcı,
  ayar anahtarı ve sözlük sürümü ölçüme girmez.
- İz (trace): her değişiklik için `search_change.apply` aralığı (tetikleyici, sonuç) ve altında
  `search_index.build` aralığı (tetikleyici, sonuç, kolon ve tablo sayısı). Ortak kurallar ve saklama
  süresi [application-foundation alanında](../../../application-foundation/DOMAIN.md) tanımlıdır.
  Tüketen test: `app/backend/tests/integration/test_search_index_signals.py`.

## Dağıtım etkisi

- `search_setting` tablosu dağıtımdaki göç işiyle uygulanır; uygulama açılışta şema değiştirmez.
- Yeni ortam değişkeni, sır veya ağ çıkışı yoktur; `python3 scripts/check-config-sync.py` etkilenmez.
- [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md) PRD'sinden
  beklenenler: backend tek kopya ve güncellemede eski ile yeni kopyanın aynı anda hizmet vermediği
  güncelleme biçimi (`Recreate`, Decision 4); hazırlık denetiminin ilk motor kurulumunu bekleyecek süre
  payı (Requirement 10, 13); bellek sınırının değişiklik sırasında iki motoru birden taşıyacak büyüklükte
  olması (nonprod'da Acceptance 5 ile ölçülür). Yönetim kayıtları ve sözlük içe aktarma, giriş
  katmanının (ingress; kümeye gelen isteği uygulamaya ileten giriş) okuma süresine bağlı 60 saniye
  kuralına (kubernetes-delivery Requirement 12) uyar: sırada bekleme en çok 20, tam kurulum en çok 30
  saniyedir (kaynakta kurulum ~10 sn; Requirement 11 ve 13); bu sınırı aşabilecek yönetim işlemi iş
  olarak tanımlanır.
- Ön yüzde `/admin` altındaki adresler istemci yönlendiricisinin sayfalarıdır; sunucu tarafında ayrı
  yol yoktur.

## Test stratejisi

- **Fark testi (kaynak paketle yan yana):** hedef şemanın 24 alanı kaynak `settings_schema.SECTIONS`
  ile anahtar, etiket, yardım, tür, varsayılan, aralık, adım, biçim, uzman ve etki olarak aynıdır (¹
  işaretli metinler ve çıkarılan beş alan dışında); hedefin varsayılanları kaynak `Settings()` ile
  aynıdır; aynı ayar, sözlük sürümü, listeler, model değerleri ve tablo sayısıyla parmak izi kaynakla
  aynı değeri verir; değişmeyen parçaları yeniden kullanan motor ile baştan kurulan motor ve kaynak
  motor aynı sorularda aynı sıralamayı ve aynı istemleri üretir.
- **Birim:** `PATCH` denetim iletileri ve kodları (bilinmeyen anahtar, `llm.endpoint`, metin ve
  `true` verilen sayı alanı, küsuratlı tam sayı, aralık, birden çok hatanın birleşmesi), varsayılana
  eşit değerin saklanmaması, etki sınıflandırması, parmak izine `cache.*` alanlarının girmemesi ve
  geri alınan değerin eski parmak izini vermesi.
- **Gerçek PostgreSQL ve HTTP:** açılışta saklanan geçersiz değerin süreci durdurması; ilk kurulum
  bitene kadar hazırlık 503, canlılık 200; değişiklik sırasında kurulum ya da yazma hatası enjekte
  edilince hiçbir satırın değişmemesi ve eski motorun hizmette kalması; aynı anda iki değişikliğin
  sırayla uygulanması ve 20 saniyeyi aşan beklemede 503; analiz kilidi tutulurken (süren analiz)
  değişikliğin beklemeden tamamlanması ve süren analizin eski motorla bitmesi; kurulum sırasında
  canlılığın 1 saniyede dönmesi; veritabanı elle değiştirilince `stale` ve olayın bir kez yazılması;
  401 ve 403; telemetri sinyalleri.
- **Ön yüz (Vitest ve tarayıcı testi):** adresler, yönlendirme ve “bulunamadı”, rol kapısı, sekme
  başlığı, kenar çubuğu ve rozetler, komut paleti (kısayol, süzme, puanlama, ok tuşları, Enter, Esc,
  ayara odaklanma), çekmece davranışı, `/` kısayolu, ayar satırları (varsayılana dönüş, işaretler,
  yüzde okuması), taslağın sayfalar arasında korunması, `Geri al`, `Kaydet ve uygula`, çıkış onayı,
  Bakım durum etiketleri ve silme onayı; tek ekran düzeni ve dar ekran için ekran görüntüsü
  karşılaştırması; yerelleştirme anahtar eşliği.
- **Görsel eşdeğerlik:** kaynak `76e21a3` ve hedef aynı sözlük ve ayarlarla yan yana çalıştırılır;
  kabuk, komut paleti, çekmece, kaydedilmemiş değişiklik çubuğu, Arama ve cevap ve Bakım
  sayfalarının ekran görüntüleri aynı ekran boyutlarında karşılaştırılır (Acceptance 6).

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: Requirement 1–8 birim, gerçek PostgreSQL ve kaynak
  paketle yan yana fark testleri geçer; şemanın 24 alanı ve varsayılanları kaynakla aynıdır, parmak izi
  aynı girdilerle kaynakla aynı değeri verir, saklanan geçersiz değer süreci başlatmaz.
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: Requirement 9–16 tümleştirme testleri geçer
  (önce kur sonra yaz, hata enjeksiyonunda değişiklik yok, sıra ve 503, analiz kilidi tutulurken
  beklememe, analizin kendi motoruyla bitmesi, hazırlık 503'ten 200'e, kurulumda canlılık, `stale`,
  401/403, telemetri sinyalleri); OpenAPI ve üretilmiş tipler günceldir;
  tam kalite kapısı geçer.
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: Requirement 17–26 ön yüz testleri ve yerelleştirme
  anahtar eşliği geçer.
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel Docker Compose ve PostgreSQL ile
  tarayıcıda yönetici `/admin`'e girer; Ctrl K ile `BM25 k1` ayarına gider, değeri değiştirip
  `Kaydet ve uygula` ile kaydeder ve `Arama indeksi yeniden kuruldu` bildirimini görür; `Önceki
  cevapları kullan` ayarını kapatınca indeks kurulmadan uygulanır; değeri `↺` ile varsayılana döndürünce
  veritabanında o anahtar için silinmemiş satır kalmaz; `/admin/sozluk/<DB.Şema.Obje>` adresi yeni
  sekmede tablonun çekmecesini açar; kaydedilmemiş değişiklikle `← Uygulamaya dön` onay ister;
  Bakım'da `Önceki cevapları sil…` sayıyı sıfırlar; backend yeniden başlatılınca hazırlık denetimi ilk
  kurulum bitene kadar 503, sonra 200 döner; `kullanici` oturumu `/admin`'i göremez ve uçlardan 403 alır
  (Requirement 6, 10, 16, 19–23, 26).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı (nonprod): gerçek sözlük içe aktarılmış
  nonprod kurulumunda açılışta ilk kurulum, tam yeniden kurma (en çok 30 saniye) ve yalnız `anında`
  etkili ayar değişikliği (en çok 15 saniye) süreleri ölçülür; yeniden kurma sırasında kap bellek
  sınırını aşmaz ve süren bir analiz kesintisiz biter (Requirement 12–13). Küme dağıtımı ayrı kullanıcı
  talimatıyla yapılır.
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı: görsel eşdeğerlik. Yerel Compose'da
  hedef ile kaynak `76e21a3` aynı sözlük ve ayarlarla çalıştırılır; kenar çubuğu ve rozetler, komut
  paleti (Ctrl K), bir çekmece, kaydedilmemiş değişiklik çubuğu, Arama ve cevap ve Bakım
  sayfalarının ekran görüntüleri masaüstü (1440×900) ve telefon genişliğinde (390×844 piksel; kenar
  çubuğunun üst çubuğa dönüştüğü düzen) yan yana karşılaştırılır. Fark yalnız fabrikanın zorunlu
  kıldığı öğelerde (kenar çubuğundaki oturum alanı, süper yöneticinin Kullanıcılar menü öğesi) ve
  dosya ayarlarının kalkmasından doğan metinlerde (¹ işaretliler, "Klasörler" kartı) kabul edilir
  (Requirement 17–25, Decision 11).

## Kararlar

Decision 5: Ekranda olmayan 10 ayar kodda sabittir (Requirement 8). Hedefte ayar dosyası yoktur; bu
değerler yalnız geliştiricinin altın setle ölçerek değiştirdiği değerlerdir ve ölçülmüş davranışın
korunması değişmezi kod incelemesinden geçmeyen bir değişiklik yolu bırakmamayı ister. Değişiklik
kod incelemesi ve altın set ölçümüyle yapılır; ölçüm betiğinin farklı değerleri deneme yolu
[quality-evaluation](../010-quality-evaluation/PRD.md) PRD'sindedir.

Decision 6: İndeks diske ya da veritabanına yazılmaz; her açılışta ve her değişiklikte PostgreSQL'den
kurulur. Kök dosya sistemi salt okunurdur, kurulum kaynakta yaklaşık 10 saniyedir ve saklanan indeksin
girdileriyle uyuşmaz kalması (kaynakta kaybolan `reindex_pending`) ortadan kalkar.

Decision 7: Hazırlık denetimi ilk motor kurulumunu bekler (Requirement 10). Kaynakta da HTTP sunucusu
indeks hazır olmadan açılmıyordu; motorsuz analiz yapılamadığı için yarım hizmet vermek yerine kopya
hazır sayılmaz.

Decision 8: “Önce kur, sonra yaz” düzeni (Decision 3), kurulumu başarısız bir sözlük içe aktarmasının
veritabanına yazılıp eski motorun yeni sözlükte olmayan kolonu önermeye devam etmesini önler (“var
olmayan alan önerilmez” değişmezi). Kaynakta dosya ile motor bu durumda ayrışıyordu.

Decision 9: Değişiklik isteği, değişiklik hizmete girene kadar bekler ve süreyi döndürür; kaynakta da
kayıt indeks kurulana kadar bekliyor ve ekran süreyi gösteriyordu. Sıra 20 saniyeyle sınırlıdır:
değişiklikler seyrektir, yöneticinin beklemesi yerine yeniden denemesi daha açıktır ve sırada bekleme
ile kurulum (en çok 30 saniye, Requirement 13) birlikte 60 saniye kuralının altında kalır
(kubernetes-delivery Requirement 12).

Decision 10: Yönetim ekranı adresleri iskeletin istemci yönlendiricisiyle yol tabanlıdır (`/admin/...`);
kaynaktaki `#/` adresleri kalkar (rules/30). Sayfa adları kaynaktakiyle aynıdır.

Decision 11: Yönetim ekranı kaynaktaki `admin.html` ile görsel olarak birebir aynı kurulur: yedi
sayfa, kenar çubuğu, Ctrl K komut paleti, çekmeceler ve alt çubuk aynı CSS değerleri (renkler,
degradeler, yazı tipleri, aralıklar, gölgeler, canlandırmalar, kırılma noktaları), mümkün olduğunca
aynı DOM düzeni ve sınıf adları, aynı Türkçe metinler ve aynı etkileşimlerle. Kaynak CSS'in
değerleri `globals.css`'e ana ekranla ortak merkezi belirteçler (CSS değişkenleri; “Evren” paleti,
[dictionary-explorer](../007-dictionary-explorer/PRD.md) Requirement 17 ve Decision 5) olarak
taşınır; rules/32'nin anlamsal belirteç isteği böyle karşılanır ve görünüm değişmez. İskeletin kendi
varsayılan görünümü kullanılmaz. Görünür yeni öğe eklenmez; yalnız fabrikanın zorunlu kıldığı oturum
alanı ve süper yöneticinin Kullanıcılar sayfası eklenir ve kaynağın aynı belirteçleri ve bileşen
görünümüyle yapılır. Kabuk, komut paleti ve çekmeceler çalışırken `<style>` öğesi ekleyen bileşen
kullanmaz; dinamik görsel değerler tarayıcının stil nesnesi (CSSOM) ya da SVG öznitelikleriyle
verilir (katı içerik güvenlik politikası, user-accounts Requirement 14). Tıklanabilir tablo
satırları Enter ve Space ile de açılır ve klavye odağı yalnız klavyeyle gezinirken görünen odak
halkasıyla gösterilir (kaynaktaki `:focus-visible` kuralı); onaylar kaynaktaki gibi tarayıcının
`confirm()` penceresiyle alınır.

Decision 12: Ayarların etiket, yardım ve bölüm metinleri arka uçtaki şemadadır ve API ile gelir, çünkü
doğrulama iletileri aynı etiketi kullanır; ekranın kendi metinleri `app/frontend/src/locales/tr.json`
dosyasındadır. Proje tek dillidir (`tr`, rules/33); ikinci dil eklenirse şema metinleri kataloğa taşınır.
Ekran `search_setting_unknown` ve `search_setting_invalid` kodlarında sunucunun iletisini olduğu gibi
gösterir, çünkü ileti yalnız şema etiketinden ve gönderilen anahtardan kurulur; öteki kodlarda kendi
yerelleştirilmiş iletisini kullanır (rules/31).

Decision 13: Saklanan geçersiz değer süreci durdurur (Requirement 5): sessizce varsayılana dönmek
cevapları fark edilmeden değiştirirdi. Kaynakta ayar dosyasındaki bilinmeyen anahtar da süreci
başlatmıyordu.

Decision 14: İndeksi etkileyen ayar kaydedilince indeks kendiliğinden kurulur; kaynaktaki “indeks
bekliyor” durumu ve elle kurma adımı kalkar. Bağlayıcı mimari karar 5 bunu ister ve yeniden başlatmada
kaybolan bekleme listesi sorununu kapatır.

Decision 15: `stale` durumu yalnız ayrışmayı gösterir ve kendiliğinden düzeltme yapmaz; tek kopya
varsayımında görülmemesi gerekir, görülürse olay yazılır ve yönetici elle yeniden kurar.

Decision 16: `PATCH` türleri katıdır (Requirement 3); kaynaktaki `"5"` metnini ve `true` değerini sayı
sayma davranışı API'nin tipli sözleşmesine (rules/21) uymadığı için kalkar. Ekran her zaman doğru türü
gönderdiğinden kullanıcıya görünür fark yoktur.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama ([Plan](plan.md), [Görevler](tasks.md)).

## Riskler

- **Bellek:** Değişiklik sırasında hizmetteki motorla yeni motor birlikte bellektedir; bellek sınırı
  küçükse kap yeniden başlar ve hizmet kesilir. Sınır nonprod'da gerçek sözlükle ölçülmelidir.
- **Tek kopya varsayımı:** Kopya sayısı artarsa ya da güncellemede iki kopya birlikte çalışırsa bir
  kopyadaki değişiklik ötekinin belleğine ulaşmaz; durum `stale` gösterir ama düzeltme elle yapılır.
- **Açılış süresi:** Her yeniden başlatmada uygulama, ilk motor kurulana kadar hizmet vermez; gerçek
  sözlükle süre nonprod'da ölçülür.
- **Uzun kayıt:** Gerçek sözlükte tam kurulum 30 saniyeyi aşarsa sırada bekleme ile birlikte 60
  saniyelik sınır aşılabilir; istemci zaman aşımı görür, sunucu değişikliği yine tamamlar ya da hiç
  yazmaz. Süre nonprod'da ölçülür (Acceptance 5); sınır aşılıyorsa değişiklik iş olarak yeniden
  tanımlanır.
- **Varsayılan değişikliği:** Koddaki varsayılanın değişmesi, o ayarı değiştirmemiş bütün kurulumların
  cevaplarını değiştirir; değişiklik altın setle önce ve sonra ölçülmeden yapılmamalıdır.
- **Sürüm geçişi:** Bir ayarı kaldıran ya da aralığını daraltan sürüm saklanan değeri temizlemezse
  süreç açılmaz (Decision 13); göç bu durumu kapsamalıdır.
- **Gereksiz yeniden analiz:** Parmak izi terim notu ve alanı gibi cevabı etkilemeyen girdileri de
  içerdiğinden kayıtlı cevaplar bazen gereksiz yere kullanılmaz.
