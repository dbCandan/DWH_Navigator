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
