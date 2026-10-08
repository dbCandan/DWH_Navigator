# PRD — answer-feedback

Status: Draft

Version: 0.1.0

Domain: [data-dictionary](../../DOMAIN.md)

## Amaç

Kullanıcı her tablo önerisine ve cevabın bütününe 👍/👎 verir, 👎'ye isteğe bağlı bir gerekçe ekler.
Oylar saklanır ve aynı ya da aynı anlamdaki soru yeniden gösterildiğinde ekrandaki cevabı
şekillendirir: yeterince kişinin uygun bulmadığı tablo öneriler arasından çıkar ama gerekçesiyle
görünür kalır; kişilerin doğruladığı tablo işaretlenir ve öne geçebilir; gösterilen güven oylarla en
çok %15 kayar; cevapta olmayan ama doğrulanmış tablolar ayrıca listelenir. Cevabın bütününü
yeterince kişi yetersiz bulursa o sorunun kayıtlı cevabı silinir ve soru bir sonraki soruluşunda
yeniden analiz edilir. Oylar yalnız ekranı şekillendirir; Excel raporları değişmez.

## Aktörler ve sonuçlar

- **Kullanıcı (`kullanici`) ve yönetici (`yonetici`):** Aynı yetkiyle oy verir, gerekçe ekler, fikrini
  değiştirir; cevapta kendi oylarını basılı düğme olarak, başkalarının oylarını yalnız kişi sayısı,
  durum ve adsız gerekçe olarak görür. Ölçülebilir sonuç: aynı soruya iki kişinin 👎 verdiği tablo
  bir sonraki gösterimde önerilerden çıkıp "Kullanıcıların uygun bulmadığı tablolar" bölümünde
  gerekçesiyle görünür; iki kişinin cevaba 👎 vermesi o sorunun kayıtlı cevabını siler ve soru bir
  sonraki soruluşunda yeniden analiz edilir; bir kişinin aynı tabloya verdiği oy kaç kez gönderilirse
  gönderilsin tek oy sayılır.

## Değişmezler ve sınırlar

- Ağırlıklandırma kaynaktaki ADR-036 sayılarıyla aynıdır (Requirement 4–7); sabitler kodda durur,
  yönetim ekranından değişmez (Decision 1).
- Oy veren oturumdaki kullanıcıdır; istemcinin gönderdiği kimlik kabul edilmez. Kişi başına, her
  tablo ve cevap için yalnız son oy sayılır (Decision 2).
- Oylar yalnız ekrandaki görünümü şekillendirir: analizin kendisi, kayıtlı cevabın içeriği, analiz
  kaydı, Excel raporları ve liste satırları değişmez (Decision 8). Tek yan etki, cevap 👎
  çoğunluğunun kayıtlı cevabı silmesidir (Requirement 10).
- Oyları uygulamadaki bir hata cevabı düşürmez; cevap oysuz gösterilir (Decision 9).
- Kim hangi soruda hangi tabloya ne oy verdi bilgisi hiçbir uçtan dönmez; cevapta yalnız kişi
  sayıları, destek, durum, adsız en çok 3 gerekçe ve kullanıcının kendi oyları vardır (Decision 10).
- Sorunun metin anahtarı ve anlam anahtarı kayıtlı cevaplarınkiyle aynı işlevlerle hesaplanır. Bu
  işlevlerin, kayıtlı cevap deposunun ve kayıtlı cevabı silme işleminin sahibi
  [question-analysis](../004-question-analysis/PRD.md) PRD'sidir; bu PRD silmenin ne zaman
  tetiklendiğinin sahibidir.
- Cevap biçimi ve cevap görünümü [question-analysis](../004-question-analysis/PRD.md) PRD'sindedir.
  Bu PRD, cevaba eklenen oy alanlarının ve görünümdeki oy öğelerinin (oy düğmeleri, gerekçe paneli,
  rozetler, işaretler, kullanıcı bölümleri, cevap oyu) sahibidir. Liste terimlerinin cevapları
  [list-search](../005-list-search/PRD.md) PRD'sinden aynı uygulama adımıyla geçer.
- Bir tablonun sözlükte olup olmadığı ve görünen adı o anki sözlükten
  ([dictionary-management](../001-dictionary-management/PRD.md)) okunur; doğrulanmış ama sözlükte
  olmayan tablo gösterilmez.
- Soru metni, tablo anahtarı ve gerekçe uygulama günlüğüne (log) ve telemetriye (ölçüm ve iz)
  girmez.
- Giriş ve roller [user-accounts](../../../application-foundation/PRDs/001-user-accounts/PRD.md)
  PRD'sindedir.

## Mevcut davranış

Kaynak: `~/codes/kt-dwhnavigator` (`76e21a3`). Her maddenin sonundaki **Hedefte:** notu hedefteki
davranışı söyler.

- **Oy ucu** (`src/vsa/web/server.py` `POST /api/feedback`, `App.feedback`): Gövde `query`, `object`
  ya da `scope: "answer"`, `vote`, `note`, `voter`, `answer_at` ve ayrıca `rank`, `score`,
  `analyst`, `reused`, `report_id` taşır. `vote` `up` ya da `down` değilse 400 ("vote: up | down")
  döner. Soru metni 2.000 karakterde kesilir ve anahtarlar kesilmiş metinden hesaplanır; bu yüzden
  2.000 karakterden uzun bir soruya verilen oy o sorunun cevabına hiç eşleşmez. Tablo anahtarı 300,
  gerekçe 2.000, `voter` 64 karakterde sessizce kesilir; `voter` yoksa istemcinin ağ adresi yazılır.
  Satır, oy anındaki sözlük sürümüyle `data/feedback.jsonl` dosyasına eklenir. Yanıt `ok`, oy
  verilen tablonun ya da cevabın toplamı, `answer_rejected` ve `forgotten`'dır. **Hedefte:**
  `POST /votes`; oy veren oturumdaki kullanıcıdır; soru 4.000 karaktere kadar kabul edilir ve
  anahtarlar tam metinden hesaplanır; uzunluk aşımı kesilmez, 422 alır; tablo sözlükte olmalıdır;
  `rank`, `score`, `analyst`, `reused`, `report_id` yazılmaz; satırlar PostgreSQL veritabanındadır
  (Requirement 1, 2; Decision 4–7, 11).
- **Oy veren kimliği** (`src/vsa/web/static/index.html` `VOTER`): Her tarayıcı, tarayıcı deposunda
  (`localStorage` anahtarı `vsa-voter`) rastgele bir kimlik üretir; aynı kişi iki tarayıcıda iki kişi
  sayılır, başka bilgisayarda kendi oylarını görmez. Liste terimi ayrıntısı bu kimliği `?voter=` ile
  gönderir. **Hedefte:** kimlik oturumdaki kullanıcıdır; tarayıcı deposu, `voter` alanı ve parametresi
  kalkar (Decision 2).
- **Ağırlıklandırma** (`src/vsa/feedback.py` `assess`, `Tally`, `FeedbackView`, `_age_weight`;
  sabitler `SAME_WORDS = 1.0`, `SAME_MEANING = 0.6`, `OTHER_DICTIONARY = 0.5`,
  `HALF_LIFE_DAYS = 180.0`, `PRIOR = 2.0`, `REJECT_WEIGHT = 1.5`, `REJECT_SUPPORT = -0.3`,
  `APPROVE_SUPPORT = 0.2`, `SCORE_NUDGE = 0.15`, `ANSWER_REJECT_SHARE = 0.6`): Requirement 3–6'daki
  kurallar. **Hedefte:** aynı sayılar ve kurallar; saf işlevler olarak taşınır (Requirement 17).
- **Cevaba uygulama** (`feedback.apply`, `App._with_feedback`, `App._known`): Requirement 7'deki
  kurallar. Analist cevabında yakın aday listesi her zaman boştur (`src/vsa/pipeline.py`
  `_analyze_llm`, `near_misses=[]`); bu yüzden "doğrulanan yakın aday önerilere katılır" kuralı bugün
  hiç devreye girmez, doğrulanan ama cevapta olmayan tablolar "Kullanıcıların bu soru için
  doğruladığı diğer tablolar" bölümünde görünür. **Hedefte:** aynı (Requirement 7).
- **Hata dayanıklılığı** (`App._with_feedback`): Oyları uygulamada hata olursa hata günlüğe yazılır
  ve cevap oysuz döner. **Hedefte:** aynı; ayrıca ölçülür (Requirement 8).
- **Kayıtlı cevabı silme** (`App.feedback` → `src/vsa/web/answer_store.py` `AnswerStore.forget`):
  Cevap oyundan sonra cevap reddedilmiş sayılırsa aynı metin anahtarlı ya da aynı (boş olmayan) anlam
  anahtarlı bütün kayıtlı cevaplar, hangi parmak iziyle (sözlük, model ve ayar özeti) yazıldıklarına
  bakılmadan silinir. **Hedefte:** aynı (Requirement 10); silme question-analysis'in kayıtlı cevap
  hizmetiyle yapılır.
- **Okuma maliyeti** (`App._feedback_view` → `load_feedback`): Her oyda ve her cevap gösteriminde
  bütün oy dosyası baştan okunur. **Hedefte:** yalnız sorunun anahtarlarına uyan satırlar dizinle
  okunur (Requirement 18).
- **Oy arayüzü** (`index.html` `voteBar`, `tableVote`, `voteBadge`, `ring`, `resultCard`,
  `foundBlock`, `crowdSections`, `answerVote`, `answerView`): Requirement 11–13'teki öğeler ve
  metinler. **Hedefte:** React'te aynı öğeler ve metinler (Requirement 11–13).
- **Cevap oyunun görünmesi** (`answerView`): "Bu cevap işinize yaradı mı?" yalnız cevapta tablo
  önerisi ya da kullanıcıların uygun bulmadığı tablo varsa gösterilir; tablo önermeyen ("Bulunamadı")
  analist cevabına cevap oyu verilemez, bu yüzden yanlış bir "Bulunamadı" kayıtlı cevabı oyla
  silinemez. **Hedefte:** analistin yazdığı "Bulunamadı" cevabında da gösterilir; "Analiz
  yapılamadı" cevabında gösterilmez (Requirement 13, Açık soru 3).
- **Saklama:** Oylar süresiz tutulur; dosya yalnız büyür. **Hedefte:** 730 günü geçen oylar silinir
  (Requirement 16, Açık soru 1).
- **Raporlar** (`src/vsa/report/excel.py`): Excel raporları cevabı oylar uygulanmadan, yazıldığı
  gibi kullanır. **Hedefte:** aynı (Requirement 9).
- **Kaldırılmış araç:** Oylardan altın set adayı çıkaran `vsa feedback` komutu ADR-053 ile
  kaldırılmıştır; `rank`, `score`, `analyst`, `reused`, `report_id` alanlarını o komut okuyordu.
  **Hedefte:** yoktur; kaynak oylar taşınmaz (Decision 5).

## İşlevsel gereksinimler

Requirement 1: Oy `POST /votes` ile kaydedilir. İstek alanları:

- `query`: oy verilen cevabın sorusu, 1–4.000 karakter;
- `scope`: `table` (bir tablo önerisi) ya da `answer` (cevabın bütünü);
- `table_key`: `scope=table` iken zorunlu, sözlükteki tablo anahtarı (`Veritabanı.Şema.Obje`), en çok
  300 karakter, oy anındaki sözlükte bulunmalı; `scope=answer` iken verilmez;
- `vote`: `up` ya da `down`;
- `note`: isteğe bağlı gerekçe; baştaki ve sondaki boşluk atıldıktan sonra en çok 300 karakter;
- `answer_at`: isteğe bağlı; gösterilen cevabın yazıldığı an, saat dilimli.

Biçime uymayan istek ve bilinmeyen alan (örneğin `voter`) 422 alır; tablo o anki sözlükte yoksa 422
`vote_table_unknown` ("Bu tablo artık sözlükte yok; cevabı yenileyip yeniden deneyin.") döner.
Saklanan satır: oy veren kullanıcı (oturumdan), oy zamanı (sunucu saati, UTC: evrensel saat), soru
metni, metin anahtarı, anlam anahtarı, kapsam, tablo anahtarı, oy, gerekçe ve oy anındaki sözlük
sürümü. Yanıt 201'dir ve oy verilen tablonun ya da cevabın Requirement 5'teki toplamını (`votes`;
tablo oyunda sorunun metin ve anlam anahtarı ikisi de boşsa, örneğin soru yalnız noktalama
işaretinden oluşuyorsa, `null`), cevabın reddedilip reddedilmediğini (`answer_rejected`) ve silinen
kayıtlı cevap sayısını (`forgotten`) taşır.

Requirement 2: Sorunun metin anahtarı (soru kelimelerinin Türkçe normalleştirilmiş, tek boşluklu
hali) ve anlam anahtarı (sorudaki kavramların terim sözlüğüne göre kümesi; içerik kavramı yoksa boş)
sunucuda, sorunun tam metninden, kayıtlı cevapların kullandığı işlevlerle
([question-analysis](../004-question-analysis/PRD.md)) ve o anki terim sözlüğüyle hesaplanır.
İstemci anahtar gönderemez (Decision 11).

Requirement 3: Bir sorunun oyları okunurken metin anahtarı aynı olan ya da (boş değilse) anlam
anahtarı aynı olan satırlar alınır ve oy zamanına göre sıralanır (eşitlikte kayıt sırası). Her
kişinin her tablo için ve cevap için yalnız son satırı sayılır; kişi fikrini değiştirebilir. Aynı
oyu yeniden göndermek yeni satır yazar ama sonucu değiştirmez.

Requirement 4: Sayılan her oyun ağırlığı üç çarpanın çarpımıdır:

- eşleşme: satırın metin anahtarı sorununkiyle aynıysa 1,0 (aynı soru); değilse ve anlam anahtarı
  aynıysa 0,6 (aynı anlam);
- yaş: 0,5^(gün / 180); gün, oy zamanından bu yana geçen süredir (gelecekteyse 0); zamanı okunamayan
  satırda 1;
- sözlük: oy şu anki sözlük sürümünden farklı bir sürümde verilmişse 0,5, aynı sürümdeyse 1.

Örnekler: bugün aynı soruya verilen oy 1,0; bugün aynı anlamdaki soruya verilen oy 0,6; 180 gün önce
aynı soruya verilen oy 0,5; bugün başka sözlük sürümünde aynı soruya verilen oy 0,5.

Requirement 5: Her tablo ve cevap için toplam şöyle hesaplanır: `up` 👍 ağırlıklarının, `down` 👎
ağırlıklarının toplamıdır; ayrıca 👍 ve 👎 veren kişiler sayılır. Destek = (up − down) / (up + down +
2); −1 ile 1 arasıdır ve az oyda sıfıra yakın kalır (2, tek oyun tek başına karar vermemesi için bir
hayalî 👍 ve bir hayalî 👎'dür). Durum bu sırayla belirlenir:

- `rejected` (uygun bulunmadı): down ≥ 1,5 ve destek ≤ −0,3;
- `approved` (doğrulandı): up > 0 ve destek ≥ 0,2;
- `disputed` (görüşler karışık): up > 0 ve down > 0;
- `doubted` (şüpheli): down > 0;
- oy yoksa boş.

Böylece aynı soruya bugün iki kişinin 👎'si (down 2, destek −0,5) tabloyu reddeder, tek kişinin 👎'si
yalnız şüpheli yapar, tek kişinin 👍'ü (destek 0,33) doğrular. Toplam yanıtta kişi sayıları (`up`,
`down`), üç ondalığa yuvarlanmış destek (`support`), durum (`status`) ve sayılan 👎'lerin boş olmayan
gerekçelerinden en yeni 3'ü (`reasons`) olarak döner.

Requirement 6: Cevap oyları soruyu değil o cevabı yargılar: cevabın yazıldığı dakikadan önce
verilen cevap oyları sayılmaz (o dakika dahil olanlar sayılır); böylece yeni bir analiz, öncekini
emekliye ayıran 👎'leri devralmaz. Cevabın yazıldığı an verilmemişse bütün cevap oyları sayılır.
Kayıtlı cevap gösterildiğinde yazıldığı an ilk analizin anıdır. Cevap reddedilmiş sayılır: cevap
toplamında down ≥ 1,5 ve down / (up + down) ≥ 0,6. Örnek: iki kişinin 👎'si reddeder; iki 👎 ile iki
👍 reddetmez.

Requirement 7: Gösterilen her cevaba oylar şöyle uygulanır (kaynaktaki `feedback.apply`):

- Her önerilen tabloya toplamı eklenir (`votes`; oyu yoksa boş). Oyu olan tablonun güveni güven ×
  (1 + 0,15 × destek) olur, 0 ile 1 arasına sınırlanır ve dört ondalığa yuvarlanır; önceki değer
  `score_before`'da kalır; seviye yeni güvenle yeniden belirlenir (tam yüzdeye yuvarlanmış değer %80
  ve üstüyse Yüksek, %50–79 Orta, altı Düşük).
- Durumu `rejected` olan öneri öneriler listesinden çıkar ve `rejected` listesine geçer; gizlenmez.
- Yakın adaylardan durumu `approved` olan önerilere `promoted` işaretiyle katılır, `rejected` olan
  `rejected` listesine geçer, diğerleri yakın aday kalır.
- Cevapta hiç yer almayan, durumu `approved` olan ve o anki sözlükte bulunan tablolar `endorsed`
  listesinde (anahtar, ad, şema, toplam) desteğe göre azalan sırayla yer alır.
- Öneriler yeni güvene göre azalan sıralanır (eşitlikte önceki sıra korunur) ve sıra numaraları
  1'den yeniden verilir.
- Cevaba `feedback` eklenir: cevap toplamı (`answer`), `answer_rejected`, kullanıcının kendi oyları
  (`mine`: yalnız aynı soru metniyle verdiği son oylar; tablo anahtarı → `up`/`down`, cevap için boş
  anahtar) ve cevabın yazıldığı an (`answer_at`; arayüz cevap oyunda geri gönderir).

Requirement 8: Oylar, cevabın istemciye verildiği her yerde, vermeden hemen önce oturumdaki
kullanıcıyla uygulanır: tek sorunun yeni ya da kayıtlı cevabı
([question-analysis](../004-question-analysis/PRD.md)) ve liste teriminin ayrıntısı
([list-search](../005-list-search/PRD.md)). Uygulama hata verirse cevap oylar uygulanmadan döner;
hata günlüğe yalnız hata sınıfıyla yazılır ve ölçülür; kullanıcıya hata gösterilmez.

Requirement 9: Oylar yalnız ekrandaki görünümü değiştirir: tek soru raporu ve liste raporu cevabın
yazıldığı gibi üretilir; kayıtlı cevabın içeriği, analiz kaydı ve liste anlık durumundaki en iyi
tablo oylardan etkilenmez.

Requirement 10: Cevap oyu kaydedildikten sonra cevap Requirement 6'ya göre reddedilmiş sayılırsa, o
sorunun metin anahtarıyla aynı ya da (boş değilse) anlam anahtarıyla aynı bütün kayıtlı cevaplar,
hangi sözlük, model ve ayarla yazılmış olurlarsa olsunlar silinir; yanıttaki `forgotten` silinen
kayıtlı cevap sayısıdır. Silme question-analysis'in kayıtlı cevap hizmetiyle yapılır. Silinecek
kayıtlı cevap kalmamışsa (sonraki oylar, aynı anda gelen iki oy) `forgotten` 0'dır ve hata oluşmaz.
Aynı soru bir sonraki soruluşunda yeniden analiz edilir.

Requirement 11: Her tablo önerisinin kartında "İşinize yarar mı?" sorusu, "👍 Evet" ve "👎 Hayır"
düğmeleri bulunur; kullanıcının o soruda o tabloya verdiği son oy basılı görünür (`mine`). Oy
tıklanınca hemen gönderilir; 👍 sonrası "Teşekkürler." yazar. 👎 sonrası gerekçe paneli açılır:
hazır gerekçeler ("Konu farklı", "Gereken kolon yok", "Eski / kullanılmıyor", "Doğru ama yetersiz"),
serbest metin kutusu (en çok 300 karakter, "Neden? (isteğe bağlı)", Enter ile gönderilir) ve
"Gönder". Gerekçe ikinci bir 👎 olarak gider ve "Gerekçe kaydedildi, teşekkürler." yazar.
Gönderilemezse "Kaydedilemedi: {ileti}" yazar. Aynı düğmeler ve gerekçe paneli cevap oyunda
etiketsiz kullanılır. Metinler kaynaktaki gibi `app/frontend/src/locales/tr.json`'a taşınır.

Requirement 12: Oy rozetleri ve işaretleri kaynaktaki metinlerledir:

- Rozet: doğrulanmış tablo "✓ {n} kişi doğruladı"; reddedilmiş "✕ {n} kişi uygun bulmadı"; şüpheli
  "⚠ {n} kişi uygun bulmadı"; karışık "Görüşler karışık · {a} 👍 {b} 👎"; diğer oylu tablo
  "{a} 👍 {b} 👎"; önerilere katılmış yakın aday "↑ Kullanıcı onayıyla eklendi". Rozetin açıklaması
  "Bu soruda (ya da aynı anlamdaki sorularda) kullanıcı oyları: {a} 👍, {b} 👎" satırını, gerekçe
  varsa "Gerekçeler: …" satırını ve güven değiştiyse "Güven, oylarla %{önce} → %{sonra}" satırını
  taşır.
- Öneri satırında "↑" (kullanıcı onayıyla eklendi), "✓" ({n} kişi doğruladı) ya da "!" ({n} kişi
  uygun bulmadı) işareti; güven halkasının ve satırın açıklamasında "oylardan önce %{önce}"; "En
  iyi eşleşme" ve diğer öneri satırlarında doğrulanan tablo için "✓" ("Kullanıcılar doğruladı").
- Sayı ve durum yalnız renkle değil yazıyla da verilir.

Requirement 13: Cevap görünümünde:

- `endorsed` varsa "Kullanıcıların bu soru için doğruladığı diğer tablolar" bölümü tablo adını,
  şemayı ve "✓ {n} kişi"yi gösterir; tıklanınca tablonun sözlükteki kolonları açılır
  ([dictionary-explorer](../007-dictionary-explorer/PRD.md)).
- `rejected` varsa kapalı açılır bölüm "Kullanıcıların uygun bulmadığı tablolar ({n})" açıklamayı
  ("Analiz bu tabloları önerdi ama birden fazla kullanıcı bu soru için uygun bulmadı; öneriler
  arasından çıkarıldı.") ve soluk tablo kartlarını gösterir; gerekçeler rozetin açıklamasındadır.
- Cevap oyu bölümü "Bu cevap işinize yaradı mı?": oy varsa "Bu cevabı {n} kişi değerlendirdi: {a}
  faydalı, {b} yetersiz buldu."; oy sonrasında kayıtlı cevap silindiyse "Bu cevabı birden fazla kişi
  yetersiz buldu: kayıtlı cevap silindi, bu soru bir dahaki sefere yeniden analiz edilecek.",
  silinmediyse ve oy 👎 ise "Not alındı. Tablo kartlarındaki 👍/👎 hangi önerinin yanlış olduğunu da
  gösterir.". Bölüm tablo önerisi ya da reddedilmiş tablo olan cevapta ve analistin yazdığı
  "Bulunamadı" cevabında gösterilir; "Analiz yapılamadı" cevabında gösterilmez (Açık soru 3).
- Kayıtlı cevap gösteriliyor ve cevap reddedilmiş görünüyorsa cevabın üstünde "Bu kayıtlı cevabı
  kullanıcılar yetersiz buldu; “Yeniden analiz et” ile güncel bir analiz alın." uyarısı çıkar.

Requirement 14: Liste teriminin ayrıntısında verilen oy, o terimin metniyle sorulmuş tek soruya
verilmiş oy gibidir; liste terimleri ve tek sorular birbirinin oylarından aynı kurallarla etkilenir.

Requirement 15: Ham oy kayıtları (kim, hangi soruda, hangi tabloya, ne oy verdi) hiçbir uçtan dönmez
ve yönetim ekranında gösterilmez (Açık soru 2). Cevaplarda yalnız kişi sayıları, destek, durum, adsız
en çok 3 gerekçe ve oturumdaki kullanıcının kendi oyları bulunur. Gerekçeler arayüzde düz metin
olarak gösterilir, biçimlendirme ya da bağlantı olarak yorumlanmaz.

Requirement 16: Verilişinden bu yana saklama süresi geçen oylar günde en az bir kez kalıcı silinir;
süre `DWHNAVIGATOR_FEEDBACK_RETENTION_DAYS` ayarıyla 180–3.650 gün arasında verilir, varsayılanı
730 gündür (Açık soru 1). Silme işi başarısız olursa cevaplar etkilenmez; iş bir sonraki çalışmada
yeniden dener.

Requirement 17: Ağırlıklandırma ve uygulama (`assess`, `apply` ve sabitleri) ağ, veritabanı ve dosya
erişimi yapmayan saf işlevler olarak taşınır. Aynı oy satırları (tarayıcı kimliği yerine kullanıcı
kimliğiyle) ve aynı cevapla kaynaktaki `vsa.feedback` ile aynı sonucu verir; bu, kaynak paketle yan
yana çalışan fark testiyle (aynı girdiyi kaynak ve hedef kodla çalıştırıp çıktıları karşılaştıran
test) kanıtlanır.

Requirement 18: Bir sorunun oyları okunurken yalnız metin anahtarı ya da anlam anahtarı uyan satırlar
dizin üzerinden okunur; oy tablosunun bütünü okunmaz. Okuma süresi oy tablosunun büyüklüğüyle değil,
o soruya uyan satır sayısıyla büyür; sorgu planının dizin kullandığı testle doğrulanır.

## API sözleşmesi

Ön ek `/api/dwhnavigator/v1`. Uç geçerli oturum belirteci ister. Hata zarfı
`{"detail":{"code":"...","message":"..."}}` biçimindedir; şema doğrulama hataları ortak zarfla 422
döner.

| Uç | Yetki | Başarı | Hatalar |
|---|---|---|---|
| `POST /votes` | `kullanici`, `yonetici` | 201 → `votes` (`up`, `down`, `support`, `status`, `reasons[]`) ya da `null`, `answer_rejected`, `forgotten` | 401; 403 rol; 422 biçim ve bilinmeyen alan; 422 `vote_table_unknown` |

Cevaba eklenen alanlar (cevap döndüren uçlarda: [question-analysis](../004-question-analysis/PRD.md)
cevapları ve [list-search](../005-list-search/PRD.md) terim ayrıntısı; bu PRD'nin Requirement 7'si):

- her öneride ve yakın adayda `votes` (toplam ya da boş), oyu olanda `score_before`, önerilere
  katılmış yakın adayda `promoted: true`;
- cevapta `rejected[]` (öneriyle aynı biçim), `endorsed[]` (`key`, `name`, `schema`, `votes`) ve
  `feedback` (`answer`, `answer_rejected`, `mine`, `answer_at`).

Kaldırılan: kaynaktaki `POST /api/feedback`, `voter` alanı ve `?voter=` parametresi; istekteki
`rank`, `score`, `analyst`, `reused`, `report_id` alanları.

## Güvenlik ve yetkilendirme

- Uç oturum ve `kullanici` ya da `yonetici` rolü ister; oy verenin kimliği yalnız oturumdan alınır.
  Sorgular etkin kiracı (kurum) kapsamındadır.
- Bütün alanlar sunucuda tip, uzunluk ve biçimle doğrulanır; uzun değer kesilmez, reddedilir; tablo
  anahtarı sözlüğe karşı denetlenir (Decision 6, 7).
- Ham oy kayıtları hiçbir yanıtta yer almaz; gerekçeler başka kullanıcılara adsız ve düz metin olarak
  gösterilir (Requirement 15).
- Hız sınırı yoktur: her oy kimliklidir ve kişi başına son oy sayıldığı için bir kişinin çok
  sayıda oyu ağırlığını artırmaz.
- Soru metni, tablo anahtarı ve gerekçe günlüğe yazılmaz; günlükte kullanıcının yalnız dışa açık
  kimliği (`public_id`) bulunur.

## Veri ve geçiş

- Yeni tablo `answer_vote` (bu PRD'nin): kiracı, oy veren kullanıcı (kullanıcı tablosuna bağ;
  kullanıcı pasifleştirilse de oy kalır), oy zamanı (`created_at`), soru metni (en çok 4.000
  karakter), metin anahtarı, anlam anahtarı (boş olabilir), kapsam (`table`, `answer`), tablo
  anahtarı (cevap oyunda boş), oy (`up`, `down`), gerekçe (boş olabilir), sözlük sürümü ve ortak
  zorunlu sütunlar. Tablo yalnız eklenen bir akıştır: satır güncellenmez ve dışa açık kimlik
  (`public_id`) taşımaz (rules/41'deki yalnız eklenen akış istisnası; Decision 3). Dizinler: kiracı ve
  metin anahtarı; kiracı ve anlam anahtarı (yalnız boş olmayanlar); oy zamanı (saklama silmesi).
  Tablo ve sütun açıklamaları göçle veritabanına yazılır (rules/43).
- Saklama silmesi kalıcıdır, yazılımsal silme (satırı silindi diye işaretleyip tutma) değildir: amaç
  verinin tutulmamasıdır (Requirement 16).
- Kayıtlı cevaplar bu PRD'nin tablosu değildir; silme question-analysis'in hizmetiyle yapılır.
- Kaynaktaki `data/feedback.jsonl` taşınmaz (kurulu bir kaynak sürüm yoktur); oylar boş başlar.
- Şemanın sahibi SQLAlchemy modelleridir; değişiklik Alembic göçüyle (veritabanı yapısını sürüm
  sürüm kuran betik) gelir; göç geri alınıp yeniden uygulanabilir.

## Gözlemlenebilirlik

- Yapılandırılmış günlük olayları: `feedback.vote_recorded` (kapsam, oy, gerekçe var mı, kullanıcının
  dışa açık kimliği), `feedback.saved_answers_forgotten` (silinen kayıtlı cevap sayısı),
  `feedback.apply_failed` (yalnız hata sınıfının adı), `feedback.retention_run` (silinen oy sayısı,
  süre, sonuç). Soru metni, tablo anahtarı ve gerekçe yazılmaz.
- Ölçümler: verilen oylar `dwhnavigator_feedback_votes_total{scope,vote}` (`scope`: `table`,
  `answer`; `vote`: `up`, `down`); cevap reddiyle silinen kayıtlı cevaplar
  `dwhnavigator_feedback_saved_answers_forgotten_total`; oyları uygulama hataları
  `dwhnavigator_feedback_apply_failures_total`; saklama işinin sildiği oylar
  `dwhnavigator_feedback_retention_deleted_votes_total`; saklama işinin son başarılı çalışma zamanı
  `dwhnavigator_feedback_retention_last_success_timestamp_seconds` (1970'ten bu yana geçen saniye;
  48 saatten eskiyse iş durmuş demektir). Kullanıcı, soru ve tablo ölçüme girmez.
- İz: ayrı iz aralığı yoktur; oy isteği sunucunun istek aralığına bağlıdır. Ortak kurallar ve saklama
  süresi [application-foundation alanında](../../../application-foundation/DOMAIN.md) tanımlıdır.
  Tüketen test: `app/backend/tests/integration/test_telemetry_signals.py`.

## Dağıtım etkisi

- Yeni göç (`answer_vote`).
- Yeni ortam ayarı `DWHNAVIGATOR_FEEDBACK_RETENTION_DAYS` (varsayılan 730, 180–3.650); sır değildir,
  `app/backend/.env.example`, yerel Compose ortam bloğu ve Kubernetes kurulum paketinin (chart) proje
  değer dosyası `helm/dwhnavigator/values-project.yaml` (`backend.config`) birlikte güncellenir;
  `python3 scripts/check-config-sync.py` geçer.
- Saklama işi sunucu sürecinin içinde çalışır; backend tek kopya çalıştığı ve güncellemede eski ve
  yeni süreç birlikte çalışmadığı için
  ([kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  Decision 5) iş tek süreçte yürür ve ayrı kilit gerekmez; aynı silme tekrarlanırsa aynı sonucu verir.
- Yeni sır, yeni ağ çıkışı ve kurulum paketinde yeni nesne yoktur.

## Test stratejisi

- **Birim testleri:** Kaynaktaki `tests/test_feedback.py` testlerinin tamamı aynen taşınır (son oyun
  tek sayılması, tek 👎'nin şüphe, iki 👎'nin red olması, desteğin güveni itip sırayı değiştirmesi,
  doğrulanan yakın adayın katılması, `endorsed`'un yalnız sözlükteki tablolarla dolması, benzer soru,
  eski oy ve başka sözlük ağırlıkları, ilgisiz sorunun yok sayılması, cevap reddinin iki kişi ve
  çoğunluk istemesi, `mine`, oysuz cevabın değişmemesi, cevap oylarının o cevabı yargılaması).
  Eklenenler: eşik sınırları (down tam 1,5; destek tam −0,3 ve tam 0,2; pay tam 0,6), aynı kişinin
  metin ve anlam eşleşmeli satırları arasında son oy, gerekçelerin en yeniden eskiye ilk 3'ü,
  `endorsed` sıralaması, güven itmesiyle seviye değişimi (%79 → %83 Yüksek), 0–1 sınırlaması, aynı
  dakikadaki cevap oyunun sayılması.
- **Fark testi:** Üretilmiş oy satırı kümeleri ve cevaplarla kaynaktaki `vsa.feedback.assess` ve
  `apply` ile hedefin işlevleri aynı çıktıyı verir.
- **Sunucu ucu (API) testleri (gerçek PostgreSQL):** kaynaktaki `test_feedback`,
  `test_answer_votes_drop_the_kept_answer` ve `test_ask_carries_earlier_votes` senaryoları
  kullanıcı kimliğiyle; doğrulama (`vote`, `scope`, eksik ya da bilinmeyen `table_key`, 301
  karakterlik gerekçe, 4.001 karakterlik soru, `voter` alanı); oy verenin oturumdan alınması;
  2.000 karakterden uzun soruda anahtarın tam metinden hesaplanıp cevaba eşleşmesi; cevap reddinde
  kayıtlı cevabın silinmesi ve ikinci oyda `forgotten` 0; sorgu planında dizin kullanımı; günlükte
  soru, tablo ve gerekçe bulunmaması.
- **Cevap uçlarında:** tek sorunun yeni ve kayıtlı cevabına, liste terimi ayrıntısına oyların
  uygulanması; uygulamaya hata sokulduğunda cevabın oysuz dönmesi ve ölçümün artması; tek soru ve
  liste raporunun oylardan önce ve sonra aynı hücreleri taşıması; liste anlık durumundaki en iyi
  tablonun değişmemesi.
- **Saklama işi:** süreyi bir gün aşan oyun silinmesi, bir gün kalan oyun kalması, işin
  tekrarlanmasının aynı sonucu vermesi, iş hatasının cevapları etkilememesi.
- **Ön yüz testleri (Vitest):** düğmelerin basılı durumu, 👍 ve 👎 iletileri, gerekçe paneli ve hazır
  gerekçeler, Enter ve "Gönder", hata iletisi, rozet metinleri ve açıklamaları, satır işaretleri,
  `endorsed` ve `rejected` bölümleri, cevap oyu bölümünün görünme koşulları ve oy sonrası iletileri,
  kayıtlı cevap uyarısı, tarayıcı deposuna yazılmaması.

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

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: taşınan ve eklenen birim testleri ile
  `assess`/`apply` fark testi geçer (Requirement 3–7, 17).
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: gerçek PostgreSQL ile sunucu ucu (API) testleri
  kaydı,
  doğrulamayı, oturumdan alınan kimliği, tam metinden anahtarı, kayıtlı cevabın silinmesini,
  ham oy kaydının dönmemesini ve dizinle okumayı doğrular; API tanım dosyası (OpenAPI) kayıtlı
  yapıtla aynıdır (Requirement 1, 2, 10, 15, 18).
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: cevap uçlarında oyların uygulanması, hata
  dayanıklılığı, raporların ve liste satırının oylardan etkilenmemesi ve liste terimi oylarının tek
  soruyu etkilemesi doğrulanır (Requirement 8, 9, 14).
- [ ] Acceptance 4: L1 — Otomatik testlerden geçti: saklama işi testleri ve telemetri testi geçer
  (Requirement 16; Gözlemlenebilirlik).
- [ ] Acceptance 5: L1 — Otomatik testlerden geçti: ön yüz testleri ve tip sapması kapısı geçer
  (Requirement 11–13).
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose ortamında (uygulamanın
  geliştirici makinesinde kapsayıcılarla çalışan kurulumu) bağlı bir sohbet modeliyle üç kullanıcı
  aynı soruyu sorar; iki kullanıcı en iyi tabloya gerekçeli 👎 verir; üçüncü
  kullanıcının ekranında tablo "Kullanıcıların uygun bulmadığı tablolar"da gerekçesiyle görünür;
  bir 👍 verilen tablo "✓ 1 kişi doğruladı" rozetini ve "oylardan önce" güvenini gösterir; aynı
  cevabın Excel raporu oy öncesiyle aynıdır (Requirement 5, 7, 9, 11–13).
- [ ] Acceptance 7: L2 — Gerçek istemci/ortamda doğrulandı: iki kullanıcı kayıtlı bir cevaba 👎
  verir; "kayıtlı cevap silindi" iletisi görünür ve aynı soru yeniden sorulunca analiz kaydında yeni
  analiz görünür; kullanıcı başka bir tarayıcıdan girince kendi oyları basılı görünür (Requirement 6,
  7, 10, 13).

## Kararlar

- Decision 1: Ağırlık sabitleri ve kuralları kaynakla aynıdır ve kodda durur; yönetim ekranından
  değişmez. Gerekçe: ADR-036'nın ölçülerek seçilmiş davranışı korunur. Altın set oyları kullanmadığı
  için bu sabitler onunla ölçülemez; değiştirmek bu PRD'nin değişmesini gerektirir.
- Decision 2: Oy veren oturumdaki kullanıcıdır (bağlayıcı mimari karar 8). Gerekçe: tarayıcı kimliği
  bir kişiyi birden çok kişi sayabiliyordu; "kişi başına son oy" kuralı ancak gerçek kimlikle
  anlamlıdır; kullanıcı her bilgisayarda kendi oylarını görür.
- Decision 3: Oy satırları yalnız eklenir; "son oy" okunurken seçilir. Gerekçe: kaynak da tarihçeyi
  tutup okurken seçiyordu; satırı kişi ve soru başına güncellemek, aynı soru metninin anlam anahtarı
  terim sözlüğüyle değiştiğinde eski "aynı anlam" eşleşmesini silerek sonucu kaynaktan ayırırdı.
- Decision 4: İstemci sorunun metnini ve cevabın yazıldığı anı gönderir; anahtarları sunucu hesaplar
  (kaynakla aynı). Gerekçe: oyu analiz kaydının kimliğine bağlamak oyları analiz kaydının saklama
  süresine ve biçimine bağımlı kılardı; kimliği belli bir kullanıcının bir soruya oy vermesi, o
  soruyu sorup oy vermesinden farklı bir etki doğurmaz.
- Decision 5: `rank`, `score`, `analyst`, `reused` ve `report_id` saklanmaz. Gerekçe: hiçbir hesap
  bunları okumaz; okuyan `vsa feedback` ADR-053 ile kaldırıldı; gereksiz veri tutulmaz.
- Decision 6: Tablo anahtarı oy anındaki sözlükte bulunmalıdır. Gerekçe: var olmayan tabloya oy
  anlamsızdır ve tabloyu şişirir; kaynak bu denetimi yalnız doğrulanmış tabloları gösterirken
  yapıyordu.
- Decision 7: Gerekçe en çok 300 karakterdir; daha uzun istek kesilmez, reddedilir. Gerekçe: ekran
  zaten 300 karakterle sınırlıyordu; kaynak sunucu 2.000 karakterde sessizce kesiyordu ve sessiz
  kesme kullanıcının yazdığını bozar.
- Decision 8: Oylar yalnız ekrandaki görünümü şekillendirir (ADR-036). Gerekçe: rapor iş birimine
  gönderilen belgedir ve analizin kendisini yansıtmalıdır; oylar zamanla değişir.
- Decision 9: Oyları uygulamadaki hata cevabı düşürmez. Gerekçe: oylar yardımcıdır; cevap dakikalar
  süren bir analizin sonucudur.
- Decision 10: Ham oy kayıtları hiçbir uçtan dönmez (Açık soru 2). Gerekçe: kimin hangi tabloyu
  uygun bulmadığı kişisel bir değerlendirmedir; görünümü şekillendirmek için kişi sayısı ve gerekçe
  yeterlidir.
- Decision 11: Anahtarlar sorunun tam metninden hesaplanır. Gerekçe: kaynakta 2.000 karakterde
  kesilmiş metinden hesaplanıyordu; daha uzun sorularda oy, cevabın anahtarına hiç eşleşmiyordu.

## Açık sorular

1. **Oylar ne kadar saklansın?** Kaynakta oylar süresiz tutuluyordu; bir oyun ağırlığı 180 günde
   yarıya, iki yılda on altıda birin altına iner. Öneri: 730 gün (iki yıl); süre
   `DWHNAVIGATOR_FEEDBACK_RETENTION_DAYS` ayarıyla 180–3.650 gün arasında değiştirilebilir; daha eski
   oylar günde bir silinir (Requirement 16).
2. **Kim neye ne oy verdi bilgisini kim görebilsin?** Kaynakta oylar adsız tarayıcı kimliğiyle
   tutuluyor ve yalnız toplamlar gösteriliyordu; hedefte her oy gerçek bir kullanıcıya bağlıdır.
   Öneri: arayüzde ve uçlarda kimse görmez; kullanıcılar ve yöneticiler yalnız kişi sayılarını,
   durumu ve adsız gerekçeleri görür; ham kayıt yalnız veritabanındadır ve yönetim ekranına oy
   sayfası eklenmez (Requirement 15).
3. **Tablo önermeyen ("Bulunamadı") analist cevabına da "Bu cevap işinize yaradı mı?" sorulsun mu?**
   Kaynakta bu cevaplara oy verilemiyor; yanlış bir "Bulunamadı" kayıtlı cevap olarak (en çok 30 gün)
   herkese yeniden verilebiliyor ve ancak biri "Yeniden analiz et" derse yenileniyor. Öneri: Evet;
   analistin yazdığı "Bulunamadı" cevabında da sorulur ve iki kişinin 👎'si kayıtlı cevabı siler;
   "Analiz yapılamadı" cevabında sorulmaz (Requirement 13).

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama

## Riskler

- **Az kişiyle büyük etki.** Tek kişinin 👍'ü bir tabloyu "doğrulandı" yapar ve güvenini yaklaşık %5
  artırır; iki kişinin 👎'si tabloyu öneriler arasından çıkarır. Yanlış ya da kötü niyetli oylar
  ekrandaki cevabı değiştirir; oylar kimlikli olduğu için izlenebilir ama arayüzde görünmez.
- **Anlam anahtarı terim sözlüğüne bağlıdır.** Terim sözlüğü değişince aynı sorunun anlam anahtarı da
  değişebilir; eski "aynı anlam" oyları eşleşmez, aynı soru metniyle verilen oylar sürer.
- **Gerekçeler serbest metindir** ve başka kullanıcılara adsız gösterilir; kullanıcı gerekçeye kişisel
  veri yazabilir.
- **Yakın aday yolu bugün boştur.** Analist cevabında yakın aday olmadığından doğrulanan tablo
  önerilere katılmaz, ayrı bölümde kalır; öneri listesine yalnız analist ekleyebilir.
- **Ekran ile rapor farklı görünebilir.** Rapor oylardan etkilenmediği için ekrandaki sıra ve güven
  rapordakinden farklı olabilir.
- **Dakika hassasiyeti.** Cevabın yazıldığı dakika içinde önceki cevaba verilmiş bir oy yeni cevaba
  da sayılabilir.
- **Süresiz saklama seçilirse** (Açık soru 1 kabul edilmezse) oy tablosu yalnız büyür; okuma dizinle
  sınırlı kalır ama veritabanı büyür ve kişiye bağlı veri süresiz tutulur.
