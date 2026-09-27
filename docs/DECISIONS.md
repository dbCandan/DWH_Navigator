# Karar Kayıtları (ADR)

ADR-001 … ADR-008 için bkz. `HANDOVER.md` §16. Bu dosya, geliştirme sırasında alınan
yeni kararları tutar.

---

## ADR-009 — Müşteri numarası ve hesap numarası aynı kavramdır

**Tarih.** 2026-09-26

**Bağlam.** Sözlükte `AccountNumber` kolonu çoğu objede müşteri numarası (CIF), bazı
objelerde hesap numarası anlamında tanımlanmış; 25 kolon `[BU OBJEDE FARKLI ANLAMDA —
DOĞRULANMALI]` bayrağı taşıyor.

**Karar.** Proje sahibi bu iki kavramı iş açısından aynı kabul ediyor.
- Terim sözlüğünde `müşteri numarası` ve `hesap numarası` tek grupta birleştirildi.
- `AccountNumber` türü kolonlardaki (kolon adı `...AccountNumber` ile biten) "farklı
  anlamda / hesap numarası anlamında" bayrakları yükleme sırasında düşürülür.
- `AccountNumber` müşteri seviyesi anahtar sayılır (granülerlik bileşeni, §8.1).

**Sonuç.** `loader.py` → `_is_account_number_note`. Diğer `NEEDS_VERIFICATION` bayrakları
etkilenmez.

---

## ADR-010 — Zaman ve granülerlik yalnızca obje seviyesinde puanlanır

**Tarih.** 2026-09-26

**Bağlam.** HANDOVER §9.2 kolon kural skoruna "+0.10 zaman boyutu" ve "−0.10 granülerlik
farkı" koyuyor; §8 aynı iki sinyali obje skorunda ayrı bileşen olarak tekrar sayıyor.

**Karar.** Bu iki sinyal yalnızca obje skorunda (§8) kullanılır; kolon kural skorunda
yoktur.

**Gerekçe.** Çift sayım, zaman kolonu olan tabloları orantısız öne çıkarır ve ağırlık
kalibrasyonunu zorlaştırır. Zaman bir kolonun değil tablonun özelliğidir.

---

## ADR-011 — Uygulanamayan obje bileşenleri ağırlıktan çıkarılır

**Tarih.** 2026-09-26

**Bağlam.** HANDOVER §8.1: talepte zaman kavramı yoksa zaman bileşeni 1.0 kabul edilir.
Bu, alakasız sorulara bile %20'lik "bedava" puan verir; ilgisiz bir soru
`min_answer_score` (0.35) eşiğini geçip "bulunamadı" yerine zayıf öneri üretebilir
(ADR-006'ya aykırı).

**Karar.** Talepte zaman kavramı yoksa zaman bileşeni, müşteri bazlı görünüm istenmiyorsa
granülerlik bileşeni hesaba katılmaz; kalan bileşenlerin ağırlıkları toplamı 1 olacak
şekilde yeniden ölçeklenir.

**Gerekçe.** Cezalandırmama ilkesi (§8.1) korunur, ancak alakasız sorular yapay puan
almaz.

---

## ADR-012 — Kolon kural skorunun tabanı

**Tarih.** 2026-09-26

**Bağlam.** HANDOVER §9.2 "taban: normalize edilmiş (0–1) arama skoru" diyor. Aday
kümesinde max'a göre normalize edilen BM25 her sorguda en iyi adaya 1.0 verir; mutlak bir
anlam taşımaz ve "bulunamadı" kararını imkânsız kılar.

**Karar.** `taban = 0.35 × göreli_bm25 + 0.25 × kolon_kavram_kapsaması`. Kavram
kapsaması (kolon metninin karşıladığı talep kavramı oranı) mutlak bir ölçüdür. §9.2'deki
bonus/ceza tablosu bunun üzerine uygulanır.

**Sonuç.** `scoring/rules.py`. Katsayılar `vsa eval` ile kalibre edilir.

---

## ADR-013 — Kavram kapsaması bilgi ağırlıklıdır; cevap için kapsama eşiği

**Tarih.** 2026-09-26

**Bağlam.** Kapsama oranı tüm kavramları eşit sayıyordu. "Müşteri" sözlükte 5.803 kolonda
geçerken "sıcaklık" hiç geçmiyor; ilgisiz sorular yaygın kavramları karşılayarak %50 kapsama
alıyor ve öneri üretiyordu (negatif sette yanlış cevap oranı %60).

**Karar.**
- Her içerik kavramı, sözlükteki yaygınlığına göre IDF ağırlığı alır:
  `log(1 + N / (df + 1))`. Kolon ve obje kapsaması bu ağırlıklarla hesaplanır.
- En iyi objenin kapsaması `min_answer_coverage` (0.5) altındaysa cevap BULUNAMADI olur.
- Sözlükte hiç geçmeyen kavramlar raporda "Kapsam" notu olarak listelenir.

**Sonuç.** Negatif set yanlış cevap oranı %60 → %0; golden set gerilemedi.

---

## ADR-014 — Uzun format kırılım (boyut kolonu) kapsama sayılır

**Tarih.** 2026-09-26

**Bağlam.** Ek A.1 (vPRC* hariç) ve A.3: kırılım bazı tablolarda ayrı kolonlarla (geniş
format), bazılarında `ProductName` / `FINANCETYPE` gibi bir boyut kolonunun değerleriyle
(uzun format) veriliyor. Token eşleşmesi uzun formatı göremiyordu.

**Karar.** Kırılım istenen talepte parantez içinde sayılan terimler "kırılım değeri"dir.
Bir obje bu değerleri kolon olarak taşımıyor ama genel bir ürün boyut kolonu taşıyorsa
(`...Name/Type/Code` + ürün ipucu; tek ürün ailesine ait olmayan), değerler kapsanmış
sayılır ve rapora "uzun format, değerlerin varlığı doğrulanmalı" kısıtı düşülür.

---

## ADR-015 — Obje aday havuzu kolon havuzundan geniştir

**Tarih.** 2026-09-26

**Karar.** Obje adayları BM25'in ilk 400 kolonundan (`candidate_object_columns`) toplanır;
kolon havuzu (`top_k_columns`) 120 kalır. §8 gereği kavramları birlikte karşılayan tablo,
tek tek kolonları zayıf olsa da değerlendirilmelidir. Sözlükte ~390 obje olduğundan
maliyet önemsizdir.

---

## ADR-016 — Batch modu: çekirdek tablo ve yapısal alanlar

**Tarih.** 2026-09-26

**Bağlam.** Hedef tablo taleplerinde (Ek A.3, QuestionList-1/2) alanları tek tek sormak
işe yaramıyor: `Period` veya `CustomerId` gibi genel alanlar yüzlerce tabloda var ve ancak
talebin geri kalanını karşılayan tablo bağlamında anlam kazanıyor.

**Karar.**
- Çekirdek tablo skoru = tüm alan skorlarının toplamı × (0.5 + 0.5 × zaman uyumu). Zaman
  düzeyi talebin zaman alanından çıkarılır (`Period` → aylık, `Date` → günlük) ve eşitlik
  bozucu değil çarpandır: aylık hedef tablo aylık kaynaktan beslenmelidir.
- En iyi 8 çekirdek aday, her alan için ayrıca skorlanır (2. tur); ilk 3'e bağlam bonusu
  (+0.10 / +0.05) verilir.
- Müşteri anahtarı ve zaman alanı, çekirdek tabloda varsa oradan alınır (Hazır).

**Sonuç.** `batch.py`. Ek A.3 alanlarında recall@3 0.00 → 0.90.

---

## ADR-017 — Batch modu: ölçü uyumu, türetme ve kanal toplamları

**Tarih.** 2026-09-26

**Karar.**
- **Ölçü uyumu:** Tekil sayım isteyen alan ("farklı banka sayısı") bir tutar kolonuyla
  karşılanamaz; böyle adaylar, isteği karşılayabilen tüm adayların arkasına sıralanır.
- **Tekil sayım türetmesi:** Varlığın kendisi (banka, alıcı) aranır; çekirdek tablonun veri
  seti grubundaki varlık kolonlu tablolar her zaman değerlendirilir ve +0.10 alan bonusu
  alır. Öneri `COUNT(DISTINCT <varlık kolonu>)` olarak raporlanır. Varlık kolonu adı ya da
  kimliği taşımalı; kart/hesap numarası (`BankCardNo`) sayılmaz.
- **Kanal toplamları:** Çekirdek tablo bir sayı/tutar alanını kanal/yön kırılımlı kolon
  ailesi olarak taşıyorsa (`FASTIncomingCount`, `KASIncomingCount`, …) cevap oradan verilir
  ve Ek A.3'teki manuel analize uygun olarak **Hazır** sayılır; toplama notu eklenir.
- **Terim kapsam notları:** Terim sözlüğünde `note` alanı "Kapsam:" ile başlayan grup
  eşleştiğinde not kolona kısıt olarak düşer ve alan en fazla **Kısmen hazır** olur
  (ör. virman yalnızca banka içi transferi kapsar).

**Sonuç.** Ek A.3 durum etiketi doğruluğu 0.50 → 0.90.

---

## ADR-018 — Yerel model sunucusu: LM Studio, OpenAI uyumlu API, standart kütüphane

**Tarih.** 2026-09-26

**Bağlam.** HANDOVER §10.3 OpenAI uyumlu `/v1/chat/completions` bekliyor; §19 donanım sorusu
açık. Geliştirme makinesi: Intel Core Ultra 7 265H, 32 GB RAM, NVIDIA GPU yok (Intel Arc
tümleşik), LM Studio kurulu.

**Karar.**
- İstemci (`llm/client.py`) yalnızca standart kütüphane kullanır; kapalı ağa ek wheel
  gerekmez. LM Studio, vLLM, llama.cpp server ve Ollama ile aynı kod çalışır.
- Embedding: **BGE-M3** (GGUF Q8_0, 635 MB, `gpustack/bge-m3-GGUF`), 1024 boyut, çok dilli.
  Doküman önerisiyle aynı; Türkçe kelime dağarcığı farkını yakalıyor ("ihtiyaç kredisi" ~
  "tüketici finansmanı fon kullandırım" 0.66, ilgisiz cümle 0.43).
- Sohbet modeli makinedeki modeller arasından ölçümle seçilir (bkz. ADR-019 sonuçları).
- Model adları ve uç nokta `config/settings.yaml` içindedir (repoya girmez).

---

## ADR-019 — Hibrit arama ve LLM hakemin birleşimi

**Tarih.** 2026-09-26

**Karar.**
- **Hibrit (M3):** Vektör kolu kullanıcının özgün cümlesiyle sorgulanır (ADR-004). İlk 200
  kolonun objeleri aday havuzuna eklenir; kolon arama bileşeni
  `(1 − 0.35) × göreli BM25 + 0.35 × normalize kosinüs` olur (min–max, ilk 200 aralığında).
  HANDOVER'daki RRF yerine bu karışım seçildi: kural skoru mutlak bir 0–1 ölçeğe
  dayandığı için (ADR-012) sıra tabanlı RRF skoru anlamını kaybettiriyordu.
- **Hakem (M4):** İlk 8 obje, en fazla 5 alanlı ve kısaltılmış açıklamalarla modele verilir;
  model yalnızca `t1…t8` kimliklerini seçer. `final = 0.6 × kural + 0.4 × LLM`; seçilmeyen
  veya görülmeyen objeler LLM = 0 alır, böylece "hiçbiri uygun değil" cevabı skoru
  doğal olarak düşürür. Hata → kural sonucu (ADR-008).
- Batch modunda hakem kapalıdır (alan başına LLM çağrısı CPU'da dakikalar sürer).

---

## ADR-020 — Web arayüzü standart kütüphane ile sunulur

**Tarih.** 2026-09-26

**Karar.** `http.server.ThreadingHTTPServer` + tek HTML sayfası (CSS/JS gömülü, dış kaynak
yok). FastAPI/uvicorn eklenmedi: kapalı ağa taşınacak bağımlılık sayısı artmıyor ve araç
tek ekip içindir. Motor tek kilitle korunur. Geri bildirim `data/feedback.jsonl`'e yazılır
(M7 başlangıcı).

---

## ADR-021 — Hakem modeli: qwen3.5-9b, Vulkan (Intel GPU), düşünme kapalı

**Tarih.** 2026-09-26

**Ölçüm.** Aynı aday listeleriyle (golden set'in 4 serbest metin maddesi + 3 negatif madde)
makinedeki üç sohbet modeli hakem olarak denendi (`eval/bench_llm.py`):

| Model | Doğru üst seçim (7) | Negatifte boş liste (3) | Geçerli JSON | Ort. süre |
|---|---|---|---|---|
| **qwen/qwen3.5-9b** (6,6 GB) | **7/7** | **3/3** | 7/7 | 45 sn |
| qwen/qwen3-coder-30b (MoE, 14,6 GB) | 5/7 | 1/3 | 7/7 | 37 sn |
| google/gemma-3-12b (8,2 GB) | 4/7 | 2/3 | 7/7 | 69 sn |

Gemma ve coder modeli "uzay gemisi yakıt seviyesi" için gemi teminatı tablosunu seçti
(uydurma eğilimi); qwen3.5 boş liste döndürdü ve gerekçeleri sözlük alanlarına dayandı.

**Karar.**
- Hakem: `qwen/qwen3.5-9b`, bağlam 8192.
- Çalışma zamanı: LM Studio `llama.cpp-win-x86_64-vulkan-avx2@2.46.0`; Intel Arc tümleşik GPU
  (17,9 GB paylaşımlı bellek) CPU'ya göre 2,1× hızlı (aynı istem 110 sn → 52 sn).
- `reasoning_effort: none`: qwen3.5 aksi hâlde tüm token bütçesini gizli düşünmeye harcayıp
  boş içerik döndürüyor.
- Bu dizüstünde LLM'li bir soru ~45–90 sn sürüyor (HANDOVER §18.4 hedefi 5–15 sn, GPU'lu
  sunucu için). Kurum donanımında model/boyut yeniden ölçülmeli; `bench_llm.py` bunun için.

---

## ADR-022 — Skor ağırlıkları: 0.75 × kural + 0.25 × LLM

**Tarih.** 2026-09-26

**Bağlam.** ADR-003'ün varsayılanı 0.6/0.4. Hibrit arama + qwen3.5-9b hakemle golden set
(`eval/history.jsonl`):

| Konfigürasyon | ask R@1 | ask MRR | Negatif yanlış cevap |
|---|---|---|---|
| Hibrit, hakem yok | 1.00 | 1.000 | 0.00 |
| Hakem 0.4, yalnız alan listesi | 0.75 | 0.875 | 0.00 |
| Hakem 0.4, + kural kanıtı (kapsanan/eksik kavram, zaman) | 0.75 | 0.875 | 0.00 |
| **Hakem 0.25, + kural kanıtı** | **1.00** | **1.000** | **0.00** |

0.4 ağırlıkta hakem, kapsam varyantında manuel listede olmayan (ama makul) bir tabloyu
birinciliğe taşıyordu. 0.25'te sıralamayı ancak kural skorları yakınken değiştiriyor;
gerekçe/kısıt metinlerini yazmaya ve "uygun aday yok" kararını güçlendirmeye devam ediyor.

**Karar.** Varsayılan `w_rule = 0.75`, `w_llm = 0.25`. Hakeme adayların kapsanan/eksik
kavramları, zaman kolonu ve uzun format bilgisi verilir. Golden set büyüdükçe yeniden
kalibre edilmeli (§9.7).

---

## ADR-023 — Keşfet ekranı LLM dışındaki tüm arama katmanlarını kullanır

**Tarih.** 2026-09-26

**Karar.** Keşfet araması üç katmanlı: (1) **ad** — tablo/şema/veri seti grubu metni
içerir (anlık, en üstte); (2) **içerik** — sohbet modeli hariç tam arama hattı
(Türkçe normalizasyon, terim sözlüğü, sözlük eş anlamlıları, BM25, BGE-M3 vektör araması,
obje seviyesine toplama; `rank_objects(use_llm=False)`); (3) **kolon adı** — bir kolon adı
metni içerir. Her sonuç eşleşme türünü, tablo skorunu ve eşleşen kolonları gösterir;
tablo açıldığında bu kolonlar vurgulanır. 3 karakterden kısa aramalar yalnız ad katmanını
kullanır. LLM hakem burada kullanılmaz (arama başına ~40 sn).

**Ek bulgu.** Windows'ta `localhost` önce IPv6'ya (`::1`) çözülüyor; yalnız IPv4 dinleyen
LM Studio'ya her istek ~2 sn gecikmeyle ulaşıyordu. İstemci `localhost`'u `127.0.0.1`'e
çeviriyor: Keşfet araması 2.100 ms → ~100 ms; hakem çağrıları da ~2 sn kısaldı.

---

## ADR-024 — İkinci arayüz tasarımı: "Evren"

**Tarih.** 2026-09-26

**Karar.** Arayüzün iki görünümü var; başlıktaki **✦ Evren / ◧ Klasik** düğmesiyle geçilir,
seçim tarayıcıda saklanır. Klasik tasarım değişmedi. Evren, aynı DOM ve JS üzerinde
`html[data-skin="evren"]` kapsamlı stil + bir canvas katmanıdır:
- Veri ambarı bir galaksi olarak çizilir: 390 tablonun her biri bir yıldız, veri seti
  grubuna göre kümelenmiş (`/api/galaxy`), yavaş dönen, fareyle paralaks.
- **Arama bir yolculuktur** (kullanıcı isteği: dönen/akan yıldız değil, ilerleyen bir rota):
  1. arama kutusundan radar dalgaları — rota planlanıyor;
  2. LLM'siz Keşfet sorgusuyla (~100 ms) gelen **gerçek** aday tablolar arasından en yakın
     komşu rotası çizilir; keşif aracı rotada ilerler, her durakta tablo adı ve skoru yanar;
  3. LLM hakem çalışırken rota ilk 8 finaliste daralır, araç finalistler arasında tur atar
     ve okunan tablo etiketlenir;
  4. cevap gelince araç 1. sonuca iner (varış dalgası); sonuçlar takımyıldızı olarak kalır.
  Sol alttaki seyir defteri gerçek sayıları yazar (`11.136 kolon → 25 aday → 8 finalist →
  5 sonuç`). Batch'te aday ön sorgusu olmadığı için araç önce en büyük kümeleri dolaşır.
- Keşfet sorgusu motor kilidini kullanmaz (yalnız okur); böylece LLM'li bir soru sürerken
  hem aday ön sorgusu hem Keşfet anında cevap verir.
- Yıldıza tıklamak tabloyu Keşfet'te açar.
- Cam paneller, dönen ışık halkalı arama kutusu, 3B eğilen kartlar, iki sütunlu sonuçlar.
- LLM tümleşik GPU'yu paylaştığı için animasyon 30 fps (hakem beklenirken 20 fps) ile
  sınırlıdır; zaman gerçek saate bağlıdır (seyrek karede yolculuk yavaşlamaz); `prefers-reduced-motion` açıksa hareket kapanır. Dış kaynak yoktur.


## ADR-025 — Model laboratuvarı: hakem seçimi ölçümle yapılır

**Bağlam.** Hakem modeli (§10) ve sıcaklığı şimdiye kadar tek seferlik betiklerle seçildi;
yeni model geldikçe elle tekrar gerekiyordu, tutarlılık (aynı girdiye aynı cevap) ölçülmüyordu.

**Karar.** `vsa lab` ve Ayarlar → Model laboratuvarı. Her yapılandırma (model × sıcaklık ×
düşünme modu) aynı sabit aday listelerini görür: golden set ask soruları, Ek A.3'ün doğrulanmış
talep alanları (yapısal alanlar hariç) ve negatif sorular; her soru birkaç kez sorulur.
Beklenen tablo aday listesinde yoksa vaka doğruluğa sayılmaz, tutarlılığa sayılır.
Kalite = 0.45·hakem doğruluğu + 0.25·nihai doğruluk + 0.15·aynı seçim + 0.15·aynı sıra
− 0.5·güven sapması. Geçersiz JSON veya uydurma aday kimliği (ADR-002) yapılandırmayı eler.
Kaliteleri 0.02 içinde olanlardan hızlısı önerilir. Düşünme modu model başına otomatik
bulunur (none → low → gönderme). Sonuçlar `eval/lab.json`'a birikir.

**Sonuç.** Model değişikliği bir tıklık ölçüm + "Uygula" ile yapılır; karar sayılara dayanır.

## ADR-026 — Bulut modelleri yalnız ölçüm için (NVIDIA API kataloğu)

**Bağlam.** Bu laptopta (Intel iGPU) büyük modeller soru başına dakikalar sürüyor; üretim ise
daha güçlü GPU'lu makinelerde çalışacak. Hangi açık modelin üretime kurulacağına karar vermek
için büyük modellerin kalitesini ölçmek gerekiyor. Kullanıcı, ölçüm için verinin kurum
dışına çıkmasını kabul etti (2026-09-26).

**Karar.** `cloud` ayarları (varsayılan kapalı; NVIDIA `integrate.api.nvidia.com/v1`, OpenAI
uyumlu). Bulut modelleri laboratuvarda `cloud:` önekiyle ölçülür; uygulamanın hakemi hiçbir
zaman buluta bağlanmaz ve ekran bulut satırları için "Uygula" sunmaz. Ölçüm sırasında dışarı
çıkan: test soruları, aday tabloların adları, veri seti grupları, kolon adları ve açıklamaları
(müşteri verisi yok). İstemci 429/5xx'te bekleyip yeniden dener; modelin reddettiği özellikleri
(sistem mesajı, JSON şeması, düşünme parametresi) ilk HTTP 400'den öğrenip onsuz devam eder.
Anahtar tarayıcıya gönderilmez.

**Sonuç.** Açık ağırlıklı bir modelin bulutta ölçülen kalitesi, aynı model kurum içi GPU'ya
kurulduğunda da geçerlidir; kapalı modeller (yalnız bulutta olanlar) referans niteliğindedir.

**Güncelleme (2026-09-26, kullanıcı kararı).** Kullanıcı hakemi de buluta almaya karar verdi:
`llm.provider: cloud`, model `google/gemma-4-31b-it` (NVIDIA), sıcaklık 0, düşünme kapalı,
`llm.seed: 42`. Sohbet bulutta, embedding (bge-m3, vektör indeksi) yerelde kalır
(`SplitClient`). Bu ayarla uygulamadaki her soruda aday tabloların adları, kolon adları ve
açıklamaları NVIDIA'ya gider; müşteri verisi gitmez. Servis erişilemezse hakem sessizce devre
dışı kalır ve sonuç kural tabanlıdır (ADR-008). Gerekçe (laboratuvar): gemma-4-31b hakem
doğruluğu %85 / nihai %88 ile en doğru model; seed'siz tutarlılığı %81 idi — seed ile yeniden
ölçüldü (eval/lab.json, `|s42` satırı). Üretimde aynı açık model kurum içi GPU'ya kurulup
`provider: local` ile çalıştırılabilir.

**Seed ölçümü (2026-09-26).** seed 42 ile 3 tekrarda aynı seçim %81 → %88; hakem doğruluğu
%85, nihai %87. Modelin ilk tercihi 16/16 vakada her tekrarda aynı; oynama yalnız kuyrukta
(2 vakada 0,60–0,65 güvenli üçüncü aday bazen ekleniyor), nihai 1. tablo 16'da 1 vakada
değişti. Neden: paylaşımlı sunucunun toplu işlemesi; seed tam belirlenimcilik sağlamıyor.
Çoğunluk oyu (hakemi N kez çağırıp ortalama) önerildi; kullanıcı gerek görmedi — mevcut
haliyle kalır. Kurum içi GPU'da tek kullanıcılı çalışmada sorun beklenmez.

## ADR-027 — Arayüz tek ekran, tek görünüm

**Karar (2026-09-26, kullanıcı kararı).** Web arayüzünde yalnız soru sorma ekranı kalır;
"Hedef tablo" (toplu talep) ve "Keşfet" sekmeleri ile sekme şeridi kaldırıldı. Klasik görünüm
ve açık/koyu tema düğmesi de kaldırıldı; tek görünüm Evren'dir (ADR-024), ayarlar sayfası da
onu kullanır.

**Gerekçe.** İş birimi kullanıcısı tek bir şey yapar: talebini yazar, cevabı okur. Ekranlar
sadeleştirildi: açılışta yalnız başlık ve arama çubuğu; soru sorulunca çubuk yukarı kayıp
sayfanın başlığı olur: üst satırın ortasına, cevapla aynı genişlik ve hizaya oturur, soru içinde
kalır. Üst satırda ayrı bir panel yoktur; logo solda, durum ve ayar sağda doğrudan galaksinin
üzerindedir, kaydırınca arkada yumuşak bir perde belirir. Analiz sürerken çubuğun kenarında bir
ışık dolaşır, logodaki pusula iğnesi arar ve cevapta yerine oturur; aşama bilgisi altta tek satır
(2026-09-27, kullanıcı geri bildirimi: "sağ üstte düğme", "panelin içinde" ve "cevabın üstünde
ayrı kutu" denemeleri bütünlüklü bulunmadı). Sonuç ekranında cevap ve tablo kartları öne çıkar; kavram kapsaması, skor
bileşenleri, notlar ve yöntem kapalı "Ayrıntılar" bölümlerindedir.

**Sonuç.** Toplu talep yalnız `vsa batch` ile yapılır; `/api/batch` ve `/api/objects` sunucuda
kalır (galaksi, aramada aday tabloları `/api/objects`'ten çeker). Alt bilgi yalnız sözlük
dosyasının güncellenme tarihini gösterir (`/api/status` → `updated`).

## ADR-028 — Tablo seviyesinde konu uyumu

**Karar (2026-09-26).** Obje skoruna beşinci bileşen eklendi: **konu uyumu** (`topic`,
`scoring/topic.py`). İki parçası var:
- *Seyrek:* her tablo tek bir BM25 dokümanıdır (tablo adı ×4, kolon adları, eş anlamlılar,
  açıklamalar ×0.3). BM25 uzunluk normalizasyonu geniş tabloları doğal olarak cezalandırır.
- *Yoğun:* her tablo için bir profil metni (adı, kolon adları, Türkçe eş anlamlılar;
  `index/dense.py::object_text`) bge-m3 ile vektörlenir (`object_vectors.npy`,
  `vsa index --dense` kurar, ~45 sn). Sorgu vektörüne en yakın 15 tablo aday havuzuna da
  eklenir. Model çok dilli olduğu için "günlük kredi kartı işlemleri" ile
  `vDailyCreditCardTransactionPool` ortak kelime olmadan eşleşir.
Konu = 0.4 × seyrek + 0.6 × yoğun, her ikisi aynı talebin adayları içinde 0–1'e ölçeklenir.

Ağırlıklar: en iyi kolon 0.35, kapsama 0.21, zaman 0.07, granülerlik 0.07, konu 0.30.
İlk dördü §8'in 5:3:1:1 oranını korur; konu uyumu olmadığında (batch modu, vektör indeksi
yok) ADR-011 gereği yeniden normalize olur ve eski davranış birebir döner. Batch modu konu
uyumunu kullanmaz (alan arar, tablo değil; ADR-016/017 ayarları korunur).

**Gerekçe.** Kapsama "kavram tablonun herhangi bir kolonunda geçiyor mu" diye bakar; 80–200
kolonlu model girdisi ve rapor tabloları neredeyse her kavramı taşıdığı için kapsama ve en
iyi kolon tavana çıkıyor, sıralamayı eşitlik bozucular belirliyordu. Türkçe talep ile
İngilizce tablo/kolon adları arasındaki köprü de yalnız terim sözlüğüne kalıyordu.

**Ölçüm (hakem kapalı).** Golden set değişmedi (ask recall@1 1.00, batch 0.70/0.80/0.90,
negatif set yanlış cevap 0). Cevabı sözlükte açıkça bulunan 30 gerçekçi iş sorusunda doğru
tablo 1. sırada %30 → %47, ilk 3'te %53 → %60, ilk 5'te %60 → %73. Kalan kaçırmaların çoğu
yine geniş model girdisi tabloları (`vRetailCustomerChurn*`, `vCrossSell*`): bunlar için
tablo türü bilgisi (model girdisi / rapor / ana tablo) sözlüğe eklenirse ayrıca ele alınabilir.

## ADR-029 — Analist akışı: cevabı LLM yazar, kurallar doğrular

**Karar (2026-09-26, kullanıcı kararı).** LLM açıkken `ask` cevabını kural motoru değil, bir
analist gibi çalışan model yazar (`llm/analyst.py`, istemler `llm/analyst_prompts.py`):

1. **Aday seçimi (katalog).** Modele sözlükteki *bütün* tablolar verilir: id, tam ad, veri seti
   grubu, kolon sayısı ve tüm kolon adları (~70k token, sistem mesajında; her talepte aynı olduğu
   için vLLM önek önbelleği kataloğu bir kez okur). Kural motorunun sıralaması ve "talebin
   kavramlarını birlikte taşıyan tablolar" listesi ipucu olarak eklenir. Model talebi yorumlar,
   6–10 aday tablo, yanıltıcı "benzer" tablolar ve benzer alanları bulmak için arama kelimeleri seçer.
2. **Kolon okuma ve rapor.** Adayların bütün kolonları sözlük açıklamaları ve kalite
   bayraklarıyla (90 kolondan geniş tablolarda talebe en ilgili 90'ının açıklaması, kalanı adıyla)
   ve sözlüğün geri kalanından benzer alanlar (tuzak adayları, "çok tabloda geçen" alanlar)
   modele verilir. Model elle yapılan analizlerin biçiminde yazar: sonuç, ≤5 öneri (Kapsadığı
   Bilgi, İlgili Alanlar, Gerekçe, Kısıt / Dikkat, Kullanım Önerisi, güven), Önerilen Kurgu,
   Dikkat Edilmesi Gerekenler ve Uyarı / Netleştirme / Top 5 dışı / Türetme / Yaygınlık notları.
3. **Doğrulama (ADR-002).** Öneri yalnızca 1. adımın adaylarından seçilebilir (id, tam ad veya
   adaylar içinde tek anlamlı tablo adı). Her kolon kendi tablosunda aranır, yoksa düşer. Her
   serbest metin `MentionChecker` ile taranır: sözlükte olmayan `DB.Şema.Obje(.Kolon)`,
   `vObje.Kolon` veya `vObje` geçen cümle silinir. Silinenlerin sayısı rapora yazılır.
   `min_confidence` (0.5) altı öneri gösterilmez; öneri kalmazsa cevap BULUNAMADI (ADR-006).
4. **Yedek (ADR-008).** Model kapalıysa, bir adım hata verir ya da zaman aşımına uğrarsa kural
   tabanlı cevap (hakem dahil) döner. `analyst.enabled: false` eski akışa geri alır.

Güven skoru analist değerlendirmesidir; kural skoru `rule_score` olarak Ayrıntılar'da kalır.
Batch modu değişmedi (kural tabanlı, hakemsiz). `vsa eval`, model açıkken analist cevabını ölçer.

**Gerekçe.** Kullanıcı aynı talepleri Claude chat'te sözlüğün tamamını okutarak analiz etti;
chat'in cevabı doğru, uygulamanınki uzaktı. Teşhis ("Müşterinin kredi kartlarının bilgisi"):
chat'in 5 tablosu kural sıralamasında 11., 18., 24., 39., 47. sıradaydı; ilk 10'u adında
"CreditCard" geçen churn girdisi, pazarlama izni, KKB özeti tabloları doldurmuştu. 118 adayın
skoru 0.64–0.86 arasına sıkışmıştı (kapsama hepsinde 1.0). Hakem yalnız ilk 10'u gördüğü için
doğru tabloyu hiç görmüyordu. Sorun aramadaydı: "kart bilgisi" talebinin cevabı, kavramın geçtiği
kolonlar değil, *konusu kart olan* tablolardır — bunu kural değil tabloları okuyan bir model
ayırt eder. Aynı model (gemma-4-31b) kataloğu görünce chat'in ilk 4 tablosunu aynı sırayla buldu.

**Bedel.** Soru başına iki büyük çağrı: bulutta ~2–5 dk (1. adım ~70 sn, 2. adım 1.5–4 dk; 2.
adımın süresi yazılan rapordan gelir). Her soruda kataloğun tamamı ve adayların açıklamaları
modele gider (meta veri; müşteri verisi değil). Üretimde şirketin A100'leri: gemma-4-31b bf16
tek A100-80GB'a sığar; vLLM `--enable-prefix-caching` ile katalog önbellekte kalır, 1. adım
saniyelere iner. `llm.timeout` 900 sn.

**Ölçüm (`vsa eval`, 2026-09-27, bulut gemma-4-31b).** Golden set'e kullanıcının chat analizleri
q004–q007 olarak eklendi (8 ask maddesi). Aynı kod, aynı model:

| | Kural + hakem (eski) | Analist akışı |
|---|---|---|
| ask recall@1 | 0.38 | **0.88** |
| ask recall@3 | 0.62 | **1.00** |
| ask recall@5 | 0.75 | **1.00** |
| ask MRR | 0.55 | **0.94** |
| beklenen kolonlar | 0.48 | **0.76** |
| negatif set yanlış cevap | 0.00 | 0.00 |

Batch metrikleri değişmedi (batch kural tabanlı). İlk koşuda 1 tuzak ihlali çıktı (q002:
`TotalLimitFullness` kolon seviyesinde kısıtsız listelendi); modelin kısıt/uyarı cümlelerinden
kolonu ananlar artık o kolonun kısıtı olarak da taşınıyor (`column_caveats`). Kalan açık:
q005'te chat'in 1. önerisi `vCustomerGeneralInfo`, q006'da `vIFRSAccountStatus` (içsel rating +
PD) ilk 5'e girmedi — doğru tablo ailesi (sektör boyutu, KKB/EWS skorları) bulundu ama
"birincil" tablo kaçtı (bu ölçüm 14 aday ve "evreni dar tablolar geri planda" kuralıyla yapıldı).
Sıradaki adım: 1. adımda bilgi ailesi başına aday garantisi (ör. PD/rating ailesi) ve üretimde
A100 üzerinde daha büyük/yerel modelle karşılaştırma (`vsa lab`).

**Ek (2026-09-27): aile araması, kavram kanıtı, batch.**
- *Aile araması.* 1. adım talebin bilgi ailelerini ve her aile için kolon adı / açıklama
  terimlerini de döndürür ("temerrüt olasılığı: PD, temerrüt olasılığı"). Her aile için tablo
  seviyesinde BM25 (`scoring/topic.py` indeksi) en iyi 2 tabloyu okunacaklara ekler (en fazla
  6). Model katalogda `vIFRSAccountStatus`'u atlasa da aile araması onu okutur.
- *Kavram kanıtı.* 2. adımda her adayın başında kural katmanının eşleşmesi yazar ("sektör ✓
  CompanySectorCodeCurrP · mevduat ✓ TotalDeposit") — §8'in "birlikte taşıma" kuralı modele
  kanıt olarak. Kararı model verir.
- *Batch.* Toplu talep için analist yolu yazıldı (çekirdek tablo + alan başına durum ve ≤3
  kaynak, 12'şerli parçalar), ama b001'de kural yolunun gerisinde kaldı (recall@5 0.70 / 0.90,
  kolon 0.57 / 0.86). Varsayılan kapalı: `analyst.batch: false`.

Ölçüm (v2, tek koşu): ask recall@1 0.75, @3 1.00, @5 1.00, MRR 0.88, kolon 0.86, tuzak ihlali
0, negatif 0. v1'e göre kolon +0.10 ve tuzak 1 → 0; recall@1 bir madde düştü (q005'te
`vEExportProductUsage` 1., `vCustomerGeneralInfo` 2. — v1'de ilk 5'te yoktu). Tek koşuda bu
fark model değişkenliğinden ayrılamıyor. Sonraki adımlar `docs/METODOLOJI_KARSILASTIRMASI.md`
§4: deterministik skor (modelden yapılandırılmış bulgu), yapılandırılmış talep ayrıştırma,
otomatik kalite kontrol, tekrar ölçümüyle tutarlılık.

**Ek (2026-09-27): 1. adım parçalı + uzlaştırma.** Tek parça katalog (~65k token) NVIDIA'nın
ücretsiz katmanında yavaş ve zaman zaman 504; laptopta yerel model ~20 dk/soru (okuma ~75, yazma
~4 token/sn); Google AI Studio ücretsiz katmanı gemma-4-31b için dakikada 16k giriş tokenı
tanıyor. Kullanıcı kararıyla NVIDIA'da kalındı ve 1. adım ikiye ayrıldı:
- *1a — parçalar (paralel):* katalog `analyst.catalog_chunks` (5) parçaya bölünür; bir veri seti
  grubunun tabloları aynı parçada kalır (grup parçadan büyükse bölünür), parçalar ~11.7k token.
  Her parça "emin değilsen dahil et" kuralıyla en fazla 8 aday önerir (kaçırmamak için).
- *Havuz:* parçaların adayları + kural motorunun kavramları birlikte taşıyan 8 tablosu + ilk 5
  tablosu, en fazla 40 tablo. Her tablo için adı, grubu, talebe en ilgili 12 kolon adı ve neden
  aday olduğu.
- *1b — uzlaştırma:* model havuzu yan yana görür (parçalar birbirini görmediği için puanları
  kıyaslanamaz) ve 1. adımın bütün çıktısını üretir: final 14 aday, yorum, bilgi aileleri, benzer
  tablolar. Başarısız olursa havuzun ilk adaylarıyla devam edilir.
2. adım, aile araması ve doğrulama değişmedi. `catalog_chunks: 1` eski tek parça akışıdır
(büyük bağlamlı hızlı sunucu, ör. A100 + vLLM önek önbelleği).

**Ek (2026-09-27): NVIDIA modeli değişti (ADR-026).** `google/gemma-4-31b-it` NVIDIA'da istek
kabul edip cevap dönmüyor (90–120 sn zaman aşımı); katalogdaki 82 modelin yalnız 6'sı cevap
veriyor, çoğu 404 (hesaba kapalı) veya 410 (kaldırıldı). Google AI Studio ücretsiz katmanı analist
akışını taşımıyor (16k giriş tokenı/dk). Canlı modeller 115–146k tokenlık istekle denendi;
gerçek soruda (`kredi kartı limit doluluk oranı`) `nvidia/nemotron-3-super-120b-a12b` 47 sn,
`nvidia/nemotron-3-ultra-550b-a55b` 179 sn'de uyarısız analist cevabı verdi, ikisi de
`vCardLimitFullness`'ı 1. sıraya koydu. Kullanıcı kararıyla (golden set ölçümü yapılmadan)
`nemotron-3-super` devreye alındı. Google Gemma cevabı `<thought>…</thought>` bloğuyla başlar ve
içinde taslak JSON olur; `parse_json_reply` bu bloğu da siler.

## ADR-030 — Yönetim ekranı (`/admin`) ve analiz izleri

**Karar (2026-09-27, kullanıcı isteği).** Ayarlar ve analiz izleme tek bir yönetim ekranında,
`/admin` adresinde toplanır; uygulamada bu adrese bağlantı yoktur, adres elle yazılır. Eski
`/ayarlar` adresi ve ana ekrandaki ⚙ düğmesi kaldırıldı. Bu bir gizleme, **erişim denetimi
değil**: adresi bilen herkes açabilir ve `/api/settings` gibi API uçları da korumasızdır.

**İz.** `vsa.trace` (saf modül) bir isteğin adımlarını span olarak toplar: sırada bekleme, kural
motoru kolları (genişletme, BM25, anlamsal arama, kolon skorlama, toplama), analistin 1a parçaları
/ 1b uzlaştırması / aile araması / 2. adımı, hakem, kurala dönüş ve her LLM çağrısı (süre, token,
HTTP 429/503 beklemeleri, reddedilen özellikler). Kayıt açılmadıkça her çağrı işlemsizdir; CLI,
eval ve Keşfet araması iz tutmaz. Paralel parçalar izi `trace.carry` ile taşır.

**Kayıt.** Sunucu her `/api/ask` için `data/logs/analyses.jsonl` dosyasına bir satır yazar:
zaman, IP, makine adı (ters DNS; kullanıcı girişi olmadığı için "kullanıcı" = makine), soru,
akış (analist / yedek / kural / hata), model, sonuç, önerilen tablolar, toplam süre, LLM çağrı ve
token sayıları ve bütün spanlar. Dosya `data/` altındadır (gitignore), kurum içi soru metni içerir.
Ekran son 3000 kaydı okur; liste spansız gelir, zaman çizelgesi satıra tıklanınca yüklenir.

