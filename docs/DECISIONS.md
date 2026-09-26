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
