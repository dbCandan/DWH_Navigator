# Chat Metodolojisi ile Uygulamanın Karşılaştırması

> Karşılaştırılan: `docs/VSA_Analiz_Metodolojisi.md` (Claude chat ajanının anlattığı yöntem) ile
> uygulamanın bugünkü analist akışı (ADR-029, `src/vsa/llm/analyst.py`, `pipeline.py`).
> Amaç: dokümandakileri doğrudan uygulamak değil, farkları ve hangisinin neden daha iyi
> olduğunu görmek; önerileri ölçüme dayandırmak.
>
> Tarih: 27 Eylül 2026

---

## 1. Özet

- **Yöntemin omurgası aynı.** Talebi ayrıştır → geniş ara → aday tabloları tam oku → tuzakları
  ayıkla → tablo seviyesinde değerlendir → gerekçelendir → sözlüğe karşı doğrula. Uygulama
  bu omurgayı dün gece kurdu (analist akışı). Chat ile aradaki fark, adımların *varlığında*
  değil, *nasıl* yapıldıklarında.
- **En büyük yapısal fark:** chat ajanı **araç kullanan, çok turlu** bir ajan: pandas ile
  istediği aramayı yazıyor, sonucu görüp yeni arama yapıyor (Adım 3'teki dört tur). Uygulama
  ise **iki sabit çağrı** yapıyor (katalogdan aday seçimi → adayları okuyup rapor). Arama
  turlarının bir kısmını uygulama deterministik olarak kendisi yapıp modele kanıt olarak
  veriyor (kural sıralaması, "birlikte taşıma" listesi, aile araması, kavram kanıtı).
- **Doküman, skoru sabit bir rubrikle hesapladığını söylüyor; uygulamada skor modelin
  kararı.** Bu, uygulamanın en belirgin eksiği: aynı talepte skorlar çalıştırmadan
  çalıştırmaya değişebiliyor ve düzeltme kuralları (MODEL TAHMİNİ ×0.85, türetme −0.15…)
  uygulanmıyor. Öneri: modelden yapılandırılmış bulgular alıp skoru kodda hesaplamak (§4.1).
- **Dokümanın 12. bölümündeki "uygulamaya çeviri" tablosu eski mimariyi tarif ediyor**
  (kural skoru + LLM hakem). Ölçümümüz bunun işe yaramadığını gösterdi (ask recall@1 %38).
  Chat'in kalitesi formülden değil, **bir modelin aday tabloları okuyup karar vermesinden**
  geliyor. Formül kanıt ve düzeltme olarak değerli, sıralayıcı olarak değil.
- Dokümandaki her şeyi uygulamaya gerek yok; aşağıda "uygula / uygulama / ölç" diye
  işaretlenmiş 10 madde var. En yüksek getirili üçü: **deterministik skor**, **yapılandırılmış
  talep ayrıştırma + netleştirme bağlantısı**, **otomatik kalite kontrol**.

---

## 2. Adım adım karşılaştırma

| # | Metodoloji adımı | Chat nasıl yapıyor | Uygulama nasıl yapıyor | Durum |
|---|---|---|---|---|
| 1 | Talebi 5 boyuta ayır (ölçüt, kırılım, zaman, granülerlik, kapsam); belirtilmeyeni varsayma | Açık tablo; açık uçlar netleştirme sorusuna döner | 1. adımda serbest metin "yorum" + bilgi aileleri; kural katmanında kavram çıkarımı (zaman, kırılım, ölçü) | **Kısmi.** Boyutlar yapılandırılmış değil; açık uç → netleştirme bağı modele bırakılmış |
| 2 | Terminoloji köprüsü (katılım bankacılığı, TR–EN, kısaltmalar) | Her kavram için elle liste | `config/term_dictionary.csv` + sözlük içi eş anlamlılar + istemdeki katılım sözlüğü + modelin aile terimleri | **Var.** Kısaltma listesi (CIF, KRS, memzuç, NACE, TTC, LGD) istemde eksik |
| 3.1 | Geniş tarama, **obje bazında sayım** | `groupby(obje).size()` | Kural sıralaması (kolon BM25 → obje toplama) + tablo BM25 (uzunluk normalize) ipucu olarak | **Farklı felsefe.** Bizde geniş tablolar cezalandırılıyor; chat ham yoğunluğa bakıyor |
| 3.2 | Obje adı / DatasetGroup taraması | `str.contains('card')` | Katalogun tamamı (ad + grup + tüm kolon adları) modelde; tablo BM25'te ad ×4 | **Var, daha kapsamlı** |
| 3.3 | **Kesişim araması** (iki kavramı aynı objede taşıyan) | Küme kesişimi | "Kavramları birlikte taşıyan tablolar" ipucu + her adayın başında "kavram ✓ kolon" kanıtı (dün eklendi) | **Var** (ölçüm §3) |
| 3.4 | Zaman / anahtar kolonu kontrolü | Liste ile kontrol | Kural katmanında zaman ve granülerlik bileşeni; analistte yalnız istemde | **Kısmi.** Analist cevabında deterministik kontrol yok |
| 4 | Aday tabloların **tüm** kolonlarını oku | 5–8 tablo, açıklama 200 karakter | 14 aday + aile aramasıyla ≤6 tablo, açıklama 420 karakter, 90 kolondan genişlerde ilgili 90'ı | **Var, daha geniş** |
| 5 | 4 tuzak türü (yanlış kavram, ad/içerik uyuşmazlığı, kapsam farkı, türetme) | Açıklama okuyarak | İstem kuralları + "benzer tablolar" + sözlüğün geri kalanından benzer alanlar + kalite bayrakları malzemede | **Var.** Kapsam ipucu kelimeleri ("yalnızca", "hariç", "bağlamında") işaretlenmiyor |
| 6 | **Sabit skor rubriği** + düzeltmeler + obje formülü | Rubrik (doküman `docs/SCORING.md`'ye atıf yapıyor ama dosya yok) | Modelin verdiği güven; rubriğin bantları istemde, düzeltmeler yok | **Eksik** (§4.1) |
| 7 | Cevap: sonuç cümlesi, öneriler, top-N dışı, netleştirme ("cevap nasıl değişir") | Elle yazım | Model yazıyor, aynı bölümler | **Var.** "Cevap nasıl değişir" zorunlu değil |
| 8 | Excel 4 sekme, Alan Detayları **birebir** açıklama, biçim | openpyxl | Aynı 4 sekme ve biçim | **Neredeyse aynı.** Alan Detayları'nda baştaki bayrak metni ayrı sütunda, açıklama "gövde" olarak yazılıyor |
| 8.3 | Her obje.kolon `assert` ile doğrulanır | assert | `validate` + `MentionChecker`: uydurma kolon düşer, uydurma ad geçen cümle silinir, sayı rapora yazılır | **Var, daha sıkı** (serbest metni de tarıyor) |
| 9 | Kalite kontrol listesi (10 madde) | Elle | Bir kısmı yapısal (doğrulama, bayrak görünürlüğü); çoğu modele bırakılmış | **Kısmi** (§4.3) |
| 10 | Adım adım, çok turlu ajan | Evet (3. ve 4. adım ayrı turlar) | İki sabit tur | **Farklı** (§4.6) |

---

## 3. Ölçüm (golden set, bulut gemma-4-31b)

Chat'in dört analizi golden set'e q004–q007 olarak eklendi; toplam 8 serbest metin talebi.

| | Kural + hakem (eski) | Analist v1 | Analist v2 |
|---|---|---|---|
| recall@1 | 0.38 | 0.88 | 0.75 |
| recall@3 | 0.62 | 1.00 | 1.00 |
| recall@5 | 0.75 | 1.00 | 1.00 |
| MRR | 0.55 | 0.94 | 0.88 |
| beklenen kolon | 0.48 | 0.76 | 0.86 |
| tuzak ihlali | 0 | 1 | 0 |
| negatif set yanlış cevap | 0.00 | 0.00 | 0.00 |

Her sütun tek koşu; 8 maddede bir maddelik oynama 0.125 eder. Aynı talebin tekrarında model
farklı sıralama verebildiği için v1 ile v2 arasındaki recall@1 farkı gürültüden ayrılamıyor —
bu da §4.1'in (deterministik skor) ve tekrar ölçümünün gerekçesi.

v2 = aile araması (Adım 2+3'ün otomatik karşılığı) + kavram kanıtı (Adım 3.3) + kolon
seviyesinde kısıt. v1'de chat'in birincil tablosunun kaçtığı iki talep vardı:

- **Kredi risk skoru** — `vIFRSAccountStatus` (içsel not + PD) aday bile olmuyordu. Chat'in
  2. adımdaki terminoloji köprüsü (temerrüt/default/PD) tam bu açığı kapatıyor. v2'de model
  talebin "temerrüt olasılığı" ailesini `PD, temerrüt olasılığı` terimleriyle yazıyor, tablo
  araması `vIFRSAccountStatus` ve `vExpectedCreditLoss`'u okunacaklara ekliyor (doğrulandı).
- **Sektör bazlı mevduat** — `vCustomerGeneralInfo` adaydı ama önerilmedi. Chat'in 3.3
  kesişim araması tam bu durum için. v2'de her adayın başında "sektör ✓
  CompanySectorCodeCurrP · mevduat ✓ TotalDeposit" kanıtı var.

v2 sonucu: `vCustomerGeneralInfo` 2. sıraya çıktı (v1'de ilk 5'te yoktu), ama 1. sırada yine
`vEExportProductUsage` (e-ihracat müşterileri) var; istemdeki "evreni dar tablolar geri planda"
kuralı modeli ikna etmedi. `vIFRSAccountStatus` artık okunuyor ama model KKB ve EWS tablolarını
öne koyuyor. İkisi de "kural istemde yazılı ama skora yansımıyor" durumu: §4.1'deki
`scope_gap` bulgusu kodda puan düşürseydi e-ihracat tablosu birinci olamazdı.

Doğrulamanın gerçek bir örneği (v2 kaydından): model `EDWDM.HRM.vPersonKKB` yazdı; tablonun
doğru adı `ERPDM.HRM.vPersonKKB`. Cümle rapordan silindi ve sayısı rapora yazıldı. Doküman
Adım 8.3'teki `assert`'ün serbest metne genişletilmiş hali.

**Toplu talep (batch):** Analist yolu b001'de kural yolunun gerisinde kaldı (recall@5 0.70'e
karşı 0.90; kolon 0.57'ye karşı 0.86). Varsayılan olarak kapalı (`analyst.batch: false`).
Doküman batch'i ayrıca ele almıyor; chat'te batch analizi yapılmadığı için karşılaştırma yok.

---

## 4. Öneriler

Her madde: ne, neden, nasıl, risk. "Uygula" = ölçümle doğrulanacak şekilde yapılmalı;
"uygulama" = gerek yok veya zararlı; "ölç" = önce deneme.

### 4.1 Skoru modelden al, kodda hesapla — **uygula (en yüksek öncelik)**

**Ne:** Doküman Adım 6'daki rubrik. Model güveni doğrudan yazmak yerine her öneri için
yapılandırılmış bulgular döndürür: `match` (birebir / net / ilişkili / dolaylı),
`needs_derivation`, `scope_gap`, `granularity_gap`, `time_fit`. Skor kodda:
taban bandı + düzeltmeler + bayrak çarpanları (MODEL TAHMİNİ ×0.85, ad/içerik uyumsuzluğu
×0.90, bunlar zaten `scoring.flag_penalty`'de).

**Neden:** (1) Aynı talep iki kez sorulduğunda farklı güven çıkabiliyor; iş birimi bunu
tutarsızlık olarak görür. (2) Bayrak cezaları bugün analist cevabına hiç uygulanmıyor.
(3) Skor denetlenebilir olur: "neden %72?" sorusunun cevabı ayrıntıda görünür.

**Risk:** Modelin bulgu etiketleri de değişebilir, ama etiket değişimi skor değişiminden
daha az olur ve görünürdür. `vsa eval` ile tutarlılık ölçülür (aynı talep 3 kez).

### 4.2 Yapılandırılmış talep ayrıştırma — **uygula**

**Ne:** 1. adım şemasına Adım 1'in beş boyutu: `olcut`, `kirilim`, `zaman`, `granulerlik`,
`kapsam`; her biri `{deger, belirtildi_mi}`. Belirtilmeyen her boyut için 2. adımda
netleştirme notu **zorunlu** ve "cevap nasıl değişir" cümlesi zorunlu (Adım 7.4).

**Neden:** Dokümanın en çok vurguladığı kural "belirtilmeyeni varsayma". Bugün bu modelin
iyi niyetine kalmış. Boyutlar ayrıca §4.3'teki otomatik kontrollerin girdisi olur (zaman
istendiyse periyot kolonu var mı?).

### 4.3 Otomatik kalite kontrol + tek onarım turu — **uygula**

**Ne:** Adım 9'daki listenin koda çevrilebilen maddeleri, rapor yazıldıktan sonra:

| Kontrol | Nasıl |
|---|---|
| Talebin her kavramı en az bir öneride karşılanıyor mu? | Kural katmanının kavramları × önerilen kolonlar (`covers`) |
| Zaman istendiyse önerilerde periyot kolonu var mı? | `time_component` (zaten var) |
| Türetme gerekiyorsa açıkça söylenmiş mi? | Hazır kolon yoksa kısıtta "türet" geçmeli |
| KVKK alanı önerildiyse uyarı var mı? | `has_pii` (140 kolon) |
| MODEL TAHMİNİ / DOĞRULANMALI alan önerildiyse kısıtta geçiyor mu? | Bayraklar |

Eksik bulunursa ya deterministik not eklenir ya da modele "şu maddeler eksik" diye tek bir
onarım turu yapılır.

**Neden:** Dokümanın 11. bölümündeki hataların çoğu (bayrak gizleme, belirsizliği varsayma,
türetmeyi söylememe) böyle yakalanır; bugün hiçbiri garanti değil.

### 4.4 Yoğunluk sayımını ipuçlarına ekle — **ölç**

**Ne:** Adım 3.1: kavramı taşıyan kolon **sayısı** obje bazında (`groupby().size()`). Bizim
tablo BM25'i uzunluk normalizasyonuyla geniş tabloları cezalandırıyor; chat ham sayıya
bakıyor. İkisi farklı sinyal: sayım "konunun merkezi" tablolarını (40 kart kolonu olan
`vCreditCardBalanceSummary`) öne çıkarır, ama 200 kolonlu model girdilerini de çıkarır.

**Nasıl:** 1. adımın ipuçlarına üçüncü liste olarak "kavramı en çok kolonda taşıyan tablolar
(sayı)". Karar yine modelde. Golden set ile önce/sonra.

### 4.5 Kapsam ipucu kelimelerini işaretle — **uygula (küçük)**

**Ne:** Adım 5.3: açıklamada "yalnızca, sadece, hariç, dahil değil, bağlamında, kapsamında"
geçen kolonlara malzemede `[KAPSAM]` etiketi. Model bu cümleleri gözden kaçırmasın.

### 4.6 Araç kullanan çok turlu ajan — **ölç (orta vadeli)**

**Ne:** Chat'in asıl gücü: arama sonucunu görüp yeni arama yazabilmesi. Uygulamada karşılığı,
modele üç araç vermek: `kolon_ara(desen)`, `tablo_oku(ad)`, `kesisim(kavram1, kavram2)`;
model birkaç tur çağırır, sonra raporu yazar.

**Neden ölç:** Kalite tavanı daha yüksek, ama (1) gemma-4-31b'nin araç kullanımı
güvenilirliği ölçülmedi, (2) süre ve tutarlılık kötüleşebilir, (3) bugünkü iki çağrı zaten
chat'in ilk 4 tablosunu buluyor. Önce A100'de, `vsa lab` ile iki mimari karşılaştırılmalı.

### 4.7 Terminoloji köprüsünü genişlet — **uygula (küçük)**

Dokümandaki kısaltmalar (CIF, KKB, KRS, memzuç, IDM, EWS, DPD, NACE, TTC, LGD, IFRS 9) ve
TR–EN çiftleri (doluluk/fullness/utilization, kıdem/tenure, gecikme/delay/delinquency/DPD,
temerrüt/default/PD) `config/term_dictionary.csv`'ye ve istemdeki sözlüğe eklenir.
Terim sözlüğü değişince `vsa index` gerekir.

### 4.8 Alan Detayları'nda açıklamayı birebir yaz — **uygula (küçük)**

Doküman 8.2: açıklama **özetlenmeden, birebir**. Bugün "gövde" (baştaki bayrak ve eş anlamlı
bölümü ayrılmış) yazılıyor ve eş anlamlılar sona ekleniyor. `raw_description` yazılırsa
sözlükle karakter karakter aynı olur; bayrak zaten ayrı sütunda.

### 4.9 Skor formülünü sıralayıcı olarak geri getirmek — **uygulama**

Dokümanın 6. adımındaki obje formülü (0.50 / 0.30 / 0.10 / 0.10) HANDOVER §8'in formülü; eski
akış bunu kullanıyordu ve kredi kartı talebinde doğru tabloyu 11. sıraya koydu. Chat de bu
formülü "anlatıyor", ama sonuçlarındaki sıralama bir modelin okumasından geliyor. Formül
§4.1'deki gibi **modelin bulgularını puana çevirmek** için kullanılmalı, adayları sıralamak
için değil.

### 4.10 Dokümandaki sayıları düzelt — **bilgi**

Doküman "283 kolon ad/içerik uyumsuzluğu" diyor; sözlükte (Sheet2) 242. `docs/SCORING.md`'ye
atıf var ama dosya yok. Chat ajanı bu değerleri kendi okumasından yazmış olabilir; referans
alınmadan önce doğrulanmalı.

---

## 5. Önerilen sıra

1. §4.1 deterministik skor + §4.2 yapılandırılmış ayrıştırma (birlikte; aynı şema değişikliği)
2. §4.3 kalite kontrol (4.2'nin boyutlarını kullanır)
3. Küçükler: §4.5, §4.7, §4.8
4. Ölçüm: tam golden set; ayrıca aynı talebin 3 kez tekrarında skor ve sıralama tutarlılığı
5. §4.4 ve §4.6 ayrı denemeler olarak, A100 üzerinde

Her adımdan önce ve sonra `vsa eval --save`; regresyon varsa geri alınır.
