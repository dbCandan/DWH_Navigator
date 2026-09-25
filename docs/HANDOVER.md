# Veri Sözlüğü Asistanı (VSA) — Proje Aktarım Dokümanı

> Bu doküman, projeyi sıfırdan ayağa kaldıracak geliştirici (veya Claude Code) için
> hazırlanmıştır. Projenin amacını, arkasındaki kararları, çalışma mantığını,
> teknik spesifikasyonunu ve yol haritasını içerir. Kod içermez; kod bu dokümana
> dayanarak yazılacaktır.
>
> **Sürüm:** 1.0 · **Tarih:** 26 Eylül 2026 · **Durum:** Geliştirme öncesi aktarım

---

## İÇİNDEKİLER

1. [Projenin amacı ve iş problemi](#1-projenin-amacı-ve-iş-problemi)
2. [Manuel prototipten öğrenilenler](#2-manuel-prototipten-öğrenilenler)
3. [Veri sözlüğü: yapı ve içerik](#3-veri-sözlüğü-yapı-ve-içerik)
4. [Çalışma mantığı (iş akışı)](#4-çalışma-mantığı-iş-akışı)
5. [Mimari](#5-mimari)
6. [Türkçe metin işleme](#6-türkçe-metin-işleme)
7. [Sorgu genişletme](#7-sorgu-genişletme)
8. [Obje seviyesine toplama](#8-obje-seviyesine-toplama)
9. [Skorlama rubriği](#9-skorlama-rubriği)
10. [LLM katmanı](#10-llm-katmanı)
11. [Doğrulama katmanı](#11-doğrulama-katmanı)
12. [Çıktı şeması (Excel)](#12-çıktı-şeması-excel)
13. [Değerlendirme ve golden set](#13-değerlendirme-ve-golden-set)
14. [Proje yapısı ve modüller](#14-proje-yapısı-ve-modüller)
15. [Ayarlar](#15-ayarlar)
16. [Alınmış kararlar (ADR)](#16-alınmış-kararlar-adr)
17. [Yol haritası](#17-yol-haritası)
18. [Kapalı ağ ve işletim notları](#18-kapalı-ağ-ve-işletim-notları)
19. [Açık sorular](#19-açık-sorular)
20. [Ek A — Gerçek analiz örnekleri](#ek-a--gerçek-analiz-örnekleri)
21. [Ek B — Kurumsal terim sözlüğü tohumu](#ek-b--kurumsal-terim-sözlüğü-tohumu)

---

## 1. Projenin amacı ve iş problemi

### 1.1 Problem

Banka içindeki iş birimi ekipleri, veri ambarında hangi tablonun veya alanın
ihtiyaçlarını karşıladığını bilmiyor. Tipik sorular:

- "Müşterilerin risk bilgilerini aylık ve ürün kırılımlı gösteren bir tablo var mı?"
- "Kredi kartı limit doluluk oranı verisine ihtiyacımız var, nerede?"
- "Şu 10 alandan oluşan bir tablo istiyoruz; bunlar ambarda mevcut mu?"

Bu sorular bugün veri ekibine e-posta/Teams üzerinden geliyor ve her biri manuel
analiz gerektiriyor. Elimizde 11.158 satırlık, açıklamaları zenginleştirilmiş bir
veri sözlüğü var. Uygulama bu sözlüğü kullanarak soruları otomatik cevaplayacak.

### 1.2 Çözülmesi gereken asıl zorluk

**Kelime dağarcığı farkı.** İş birimi "limit doluluk oranı" der, sözlükte
`CardLimitFullnessToday` yazar. İş birimi "ihtiyaç kredisi" der, katılım bankacılığı
terminolojisinde karşılığı "tüketici fon kullandırımı"dır. Uygulamanın başarısı
büyük ölçüde bu boşluğu kapatmasına bağlıdır. Basit bir metin araması bu işi yapamaz.

### 1.3 Uygulamanın yapacağı iş

Girdi: iş biriminin doğal dildeki talebi (tek soru) veya talep edilen hedef tablonun
alan listesi (Excel).

Çıktı: veri sözlüğünden seçilmiş en yakın tablo/alan önerileri. Her öneri şunları
taşır:
- Veritabanı.Şema.Obje ve ilgili alan adları
- **Gerekçe** — neden eşleştiği, sözlük tanımına dayanarak
- **Kısıt / Dikkat** — kapsam farkı, türetme ihtiyacı, karıştırılma riski
- **Güven skoru** (0–1) ve seviye etiketi (Yüksek/Orta/Düşük)
- **Kullanım önerisi**

Çıktı formatı: iş birimine doğrudan iletilebilecek Excel analiz raporu.

### 1.4 Başarı kriteri

- İş birimi sorusunun doğru cevabı (beklenen tablo) ilk 3 öneri içinde olmalı.
- Uygulama var olmayan bir alan önermemeli. Bu, güvenilirliğin ön koşuludur.
- Cevabı olmayan sorularda "bulunamadı" diyebilmeli; liste doldurmamalı.

---

## 2. Manuel prototipten öğrenilenler

Uygulama geliştirilmeden önce üç gerçek talep elle analiz edildi. Bu analizler hem
yöntemi ortaya çıkardı hem de golden set'in ilk maddelerini oluşturdu (Ek A).

Bu süreçte öğrenilen ve **koda taşınması zorunlu** dersler:

**(a) Arama kolon seviyesinde, cevap tablo seviyesinde olmalı.**
İş birimi kolon değil tablo arıyor. "Aylık ve ürün kırılımlı risk" talebinde kazanan
tablo, tek bir kolonu çok iyi eşleştiği için değil, konut/taşıt/tüketici/leasing
kolonlarını **birlikte** taşıdığı ve periyot kolonu olduğu için kazandı. Bu kural
atlanırsa çıktı "kolon listesi" gibi görünür ve iş birimine faydasız olur.

**(b) Zaman boyutu ayrı bir kriter.**
"Aylık" isteniyorsa, tabloda `Period` (YYYYMM) veya ay sonu değeri alan bir
`DataDate` bulunması skoru belirgin şekilde etkilemeli. Bir tablo içerik olarak
mükemmel eşleşse bile periyot kolonu yoksa talebi karşılamaz.

**(c) Hazır alan ile türetilebilir alan ayrımı kritik.**
"Limit doluluk oranı" için bazı tablolarda hazır oran var (`CardLimitFullnessToday`),
bazılarında pay ve payda var ama oran yok (`TotalUsedLimitTL` / `CardLimit`). İkisi
de geçerli cevap ama farklı skor almalı ve rapor bu farkı açıkça söylemeli.

**(d) İsim benzerliği tuzakları raporlanmalı.**
`vCreditCardLimit.CardLimitRatio` adı "doluluk oranı" gibi duruyor ama sözlük
açıklamasına göre farklı bir şey (kart limitinin bir referans değere oranı). Uygulama
bu tür riskleri kısıt notunda belirtmeli. Benzer şekilde `vCardLimitFullness` içindeki
`TotalLimitFullness` kart bazlı değil, müşterinin tüm limitlerini kapsıyor.

**(e) Sözlükteki "Eş anlamlılar/aranabilir terimler" bölümü en değerli sinyal.**
Manuel analizde eşleşmelerin çoğu bu bölüm sayesinde bulundu. İnsan eliyle yazılmış
bir sözlük genişletmesi; indekslemede yüksek ağırlık almalı.

**(f) Kalite bayrakları çıktıya taşınmalı.**
Sözlükteki 240 açıklama `[MODEL TAHMİNİ — DOĞRULANMALI]` etiketli. Böyle bir alan en
iyi eşleşme olsa bile iş birimi bunu bilmeli ve skor buna göre düşmeli.

**(g) Talepler iki farklı şekilde geliyor.**
Birincisi serbest metin sorusu, ikincisi hedef tablo tasarımı (TR başlık / EN başlık /
açıklama içeren bir tablo). İkincisi birincinin toplu çalıştırılmış hali ama çıktı
formatı farklı olmalı: alan bazında durum etiketi ve "hangi tek tablo en çok alanı
karşılıyor" analizi gerekiyor.

**(h) Netleştirme soruları raporun parçası olmalı.**
Manuel analizlerde en değerli çıktılardan biri "bu talep belirsiz, şunu netleştirin"
notlarıydı. Örnek: "risk bilgisi" banka içi risk mi, sektör geneli (KKB/Memzuç) mi?
"Para transferi" hangi kanalları kapsıyor (FAST, havale, SWIFT, virman)?

---

## 3. Veri sözlüğü: yapı ve içerik

### 3.1 Genel istatistikler (mevcut sürüm)

| Özellik | Değer |
|---|---|
| Satır (kolon) sayısı | 11.158 |
| Veritabanı | 3 (EDWDM 10.616, EDWBridge 459, ERPDM 83) |
| Şema | 31 |
| Obje (tablo/view) | 389 |
| Veri seti grubu | 66 |
| `[MODEL TAHMİNİ]` etiketli açıklama | 240 |
| Boş açıklama | 0 |

En yoğun veri seti grupları: Teminat, Fiyatlama Analitiği, Tüzel Sektör Talepleri, Kart.

### 3.2 Ana sayfa formatı (`Sheet1`)

Her satır bir kolonu tanımlar.

| Kolon | Zorunlu | Açıklama |
|---|---|---|
| `DAtabaseName` | Evet | Veritabanı adı. **Dikkat:** orijinal dosyada bu yazım hatası var; yükleyici her iki yazımı da kabul etmeli. |
| `SchemaName` | Evet | Şema adı (TRX, CON, MDL, CMP, AIS…) |
| `ObjectName` | Evet | Tablo/view adı. Bazı değerlerde baştan/sondan boşluk var, temizlenmeli. |
| `ColumnName` | Evet | Kolon adı. Aynı şekilde boşluk temizliği gerekli (`'SenderAccount '` gibi örnekler var). |
| `ColumnDescription` | Evet | Zenginleştirilmiş açıklama metni |
| `DatasetGroup` | Hayır | Veri seti grubu; boş olabilir |

### 3.3 Açıklama metninin yapısı

Açıklama serbest metindir ancak iki yapısal parça taşır.

**Eş anlamlılar bölümü.** Metnin sonunda:

```
Müşteriye bankada tanımlanan tekil müşteri numarasıdır (CIF). ...
Eş anlamlılar/aranabilir terimler: müşteri no, müşteri kimlik no, CIF, CIF no,
customer id, customer number.
```

Ayrıştırma kuralı: `"Eş anlamlılar/aranabilir terimler:"` kalıbından sonrası virgülle
bölünür. Varyasyonlar da yakalanmalı: `"Eş anlamlılar:"`, `"aranabilir terimler:"`.
Sonuç `synonyms: list[str]` alanına yazılır.

**Kalite bayrakları.** Metnin başında köşeli parantez içinde:

| Bayrak | Anlamı | Skora etkisi |
|---|---|---|
| `[MODEL TAHMİNİ — DOĞRULANMALI]` | Açıklama orijinalde boştu, üretildi | çarpan 0.85 |
| `[ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ. ...]` | Kaynak açıklama düzeltildi | Skoru etkilemez, rapora not |

Ayrıca bazı açıklamalarda serbest metin içinde "iş birimiyle doğrulanması önerilir"
uyarıları var; bunlar bayrak değil ama rapora taşınabilir.

### 3.4 Kalite bulguları sayfası (`Sheet2`, opsiyonel)

1.068 satırlık bir kalite bulguları listesi. Kategoriler: boş açıklama,
isimlendirme/içerik uyumsuzluğu (283 kolon), duplike kolon, yazım hatası.

Uygulama bu sayfayı **opsiyonel** okumalı: varsa bulgular ilgili kolona bayrak olarak
iliştirilir (skorda 0.90 çarpanı), yoksa uyarı verilip devam edilir.

### 3.5 Bilinen veri kalitesi sorunları

- 21 tekrarlanan `(ObjectName, ColumnName)` çifti → ilk kayıt tutulur, uyarı loglanır.
- 283 kolon isimlendirme/içerik uyumsuzluğu bayraklı.
- Bazı objelerde kanal tanımı belirsiz (örn. `KAS` ön ekli kolonların açıklamasında
  "PÖS/POS" ifadesi geçiyor, kolon adıyla örtüşmüyor).

### 3.6 Sürümleme

Yükleme sırasında dosyanın SHA-256 özeti (ilk 12 karakter) ve satır sayısı
hesaplanır: `a1b2c3d4e5f6-11158`. Bu değer indekse ve üretilen her Excel raporunun
Özet sekmesine yazılır. Böylece bir raporun hangi sözlük sürümüyle üretildiği
izlenebilir.

---

## 4. Çalışma mantığı (iş akışı)

Manuel analizde uygulanan adımların otomasyonu:

```
1. SORGU İŞLEME
   Talep normalize edilir, kavramlara ayrılır, eş anlamlılarla genişletilir.

2. ARAMA
   Kolon seviyesinde hibrit arama (BM25 + yoğun vektör) → ~100-120 aday.

3. YENİDEN SIRALAMA (opsiyonel)
   Cross-encoder reranker → ~30-40 aday.

4. OBJE SEVİYESİNE TOPLAMA
   Kolonlar tabloya göre gruplanır; kapsama oranı, zaman boyutu ve granülerlik
   hesaplanır → ~10 obje adayı.

5. SKORLAMA
   Kural bileşeni (deterministik) + LLM hakem bileşeni (opsiyonel).

6. DOĞRULAMA
   Önerilen her (obje, kolon) çifti sözlükte var mı kontrol edilir.

7. RAPOR
   Excel çıktısı üretilir.
```

### 4.1 İki çalışma modu

| Mod | Girdi | Çıktı |
|---|---|---|
| `ask` | Tek serbest metin sorusu | Top-N obje önerisi, gerekçeli |
| `batch` | Alan listesi içeren Excel (TR başlık / EN başlık / açıklama) | Her alan için top-N + alan bazlı durum etiketi + tablo seviyesi kapsama analizi |

`batch` modu `ask` modunu alan başına çalıştırır, ancak ek olarak şunu üretir:
**"Talep edilen N alanın kaçı tek bir tablodan karşılanabiliyor?"** Bu, hedef tablo
tasarımı taleplerinde en çok sorulan soru.

---

## 5. Mimari

### 5.1 Katman şeması

```
Kullanıcı talebi
       │
       ▼
┌──────────────────────────────┐
│ 1. Sorgu İşleme              │  text/normalize.py
│    normalize + genişletme    │  expansion/query_expander.py
└──────────────┬───────────────┘
               │ sparse_terms + dense_text + concepts
               ▼
┌──────────────────────────────┐
│ 2. Arama (hibrit)            │  index/bm25.py
│    BM25 + yoğun vektör       │  index/dense.py
│    → RRF birleştirme         │  index/hybrid.py
└──────────────┬───────────────┘
               │ ~120 kolon adayı
               ▼
┌──────────────────────────────┐
│ 3. Yeniden Sıralama (ops.)   │  index/rerank.py
└──────────────┬───────────────┘
               │ ~30-40 aday
               ▼
┌──────────────────────────────┐
│ 4. Obje Seviyesine Toplama   │  scoring/aggregate.py   ← KRİTİK
└──────────────┬───────────────┘
               │ ~10 obje
               ▼
┌──────────────────────────────┐
│ 5. Skorlama                  │  scoring/rules.py
│    kural + LLM hakem         │  scoring/combine.py, llm/judge.py
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ 6. Doğrulama                 │  validate.py
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ 7. Rapor (Excel)             │  report/excel.py
└──────────────────────────────┘
```

Orkestrasyon: `pipeline.py`. CLI: `cli.py`.

### 5.2 Teknoloji tercihleri

- **Python 3.11+**, tip ipuçları zorunlu, `ruff` + `mypy` temiz geçmeli.
- Çekirdek bağımlılıklar: `pandas`, `openpyxl`, `pyyaml`, `typer`, `rich`.
- Yoğun vektör için (M3): `sentence-transformers`, `faiss-cpu` — kapalı ağda wheel
  olarak temin edilmeli.
- BM25 saf Python ile yazılabilir (11 bin doküman için fazlasıyla yeterli, ek
  bağımlılık gerektirmez) veya `rank-bm25` kullanılabilir.
- I/O yalnızca `loader.py`, `report/`, `cli.py` içinde; diğer modüller saf fonksiyon.

### 5.3 İlk kilometre taşı ilkesi

**LLM'siz çalışan bir çekirdekle başlanmalı.** Arama katmanı sağlam olmadan LLM
eklemek sorunu gizler. M1 tamamlandığında uygulama, LLM olmadan, sadece BM25 +
kural skorlamasıyla golden set'teki üç maddeyi doğru cevaplayabilmeli.

---

## 6. Türkçe metin işleme

Bu katman atlanırsa isabet ciddi düşer. Tüm kurallar tek bir modülde
(`text/normalize.py`) toplanmalı ve başka yerde tekrarlanmamalı.

### 6.1 Türkçe küçük harf dönüşümü

`"İHTİYAÇ".lower()` Python'da yanlış sonuç verir (birleşik karakter üretir). Özel
eşleme tablosu kullanılmalı:

```
I → ı,  İ → i,  Ş → ş,  Ğ → ğ,  Ü → ü,  Ö → ö,  Ç → ç
```

**Kural:** Projede hiçbir modülde doğrudan `.lower()` çağrılmaz.

### 6.2 ASCII katlama

Kullanıcı "ihtiyac kredisi" veya "musteri" yazabilir. Hem Türkçe hem katlanmış biçim
indekslenmeli, sorgu da katlanmış biçimde aranmalı:

```
ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c, â→a, î→i, û→u
```

### 6.3 CamelCase ayrıştırma

`CardLimitFullnessToday` tek token olarak indekslenirse "limit doluluk" araması bu
kolonu **asla bulamaz**. Ayrıştırma zorunlu:

```
CardLimitFullnessToday  →  card limit fullness today
IFRSStage               →  ifrs stage          (ardışık büyük harf grubu korunur)
TOTALOUTSTANDINGBALANCE →  totaloutstandingbalance   (tamamı büyük, bölünemez)
KKB_DATE                →  kkb date
```

Hem orijinal hem ayrıştırılmış biçim saklanmalı (tam ad araması da çalışsın diye:
kullanıcı `CreditCardLimitRate` yazarsa birebir bulunmalı).

### 6.4 Hafif gövdeleme

Türkçe sondan eklemeli bir dildir: "transferi", "transferler", "transferlerin" aynı
köke inmeli. MVP için kural tabanlı ek kesme yeterli (uzun ekten kısaya doğru dene,
minimum kök uzunluğu 4 karakter):

```
lerinin, larının, lerine, larına, lerini, larını, lerin, ların,
leri, ları, ler, lar, nin, nın, nun, nün, in, ın, un, ün,
de, da, te, ta, den, dan, ten, tan, si, sı, su, sü, i, ı, u, ü, e, a
```

**Yükseltme adayı (M4):** Zemberek veya Snowball Türkçe analizörü.

### 6.5 Durak kelimeler

Aramada gürültü yaratan kelimeler temizlenmeli: `ve, veya, ile, için, bir, bu, mi,
var, yok, olan, gibi, göre, bazında, üzerinden, bilgisi, verisi, tablo, hangi,
nedir, mevcut, midir` + İngilizce karşılıkları.

**Dikkat:** "bilgisi", "verisi" gibi kelimeler durak listesindedir ama "risk bilgisi"
ifadesinde "risk" içerik kelimesidir. Durak temizliği token bazında yapılmalı, ifade
bazında değil.

### 6.6 İndeksleme alanları ve ağırlıklar

Her kolon için indekslenen metin üç alandan gelir:

| Alan | Varsayılan ağırlık | Not |
|---|---|---|
| Kolon adı (CamelCase ayrıştırılmış) | 3 | En güçlü sinyal |
| Eş anlamlılar bölümü | 2 | İnsan eliyle yazılmış, çok değerli |
| Açıklama metni | 1 | En uzun, en gürültülü |
| Obje adı | 1 | Zayıf ama faydalı sinyal |

---

## 7. Sorgu genişletme

### 7.1 Temel ilke

**Genişletme yalnızca seyrek (BM25) koluna uygulanır.** Yoğun vektör kolunda
kullanıcının orijinal ifadesi kullanılır.

Gerekçe: BM25 birebir kelime eşleşmesine bakar, "doluluk" ile "kullanım oranı"
arasında bağ kuramaz — genişletmenin asıl değeri burada. Embedding ise zaten anlamsal
yakınlığı yakalar; oraya eş anlamlı yığını eklemek sorgu vektörünü bulanıklaştırır ve
isabeti düşürür.

### 7.2 Üç genişletme kaynağı

**(a) Kurumsal terim sözlüğü — `config/term_dictionary.csv`**

Elle kurulur, deterministiktir, açıklanabilirdir. Katılım bankacılığı terimlerini
hiçbir genel model bilmediği için **en yüksek değeri bu kaynak üretir**. Format:

```csv
term,equivalents,domain,note
fon kullandırım,kredi|finansman|loan|credit,katılım,Katılım bankacılığında kredinin karşılığı
kâr payı,faiz|getiri|profit share|interest,katılım,
icare,leasing|finansal kiralama|ijara,katılım,
doluluk oranı,kullanım oranı|utilization|fullness|limit kullanımı,genel,
```

Eşleme **iki yönlüdür**: gruptaki her terim diğerlerini getirir. Başlangıç tohumu
Ek B'dedir; iş birimi geri bildirimiyle büyütülür.

**(b) Sözlüğün kendi eş anlamlılar bölümü**

Sözlükteki `Eş anlamlılar/aranabilir terimler:` bölümleri ters indekse çevrilir:

```
"cif"            → {EDWDM.TRX.vX.AccountNumber, EDWDM.MDL.vY.CustomerId, ...}
"limit doluluk"  → {EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday, ...}
```

Kullanıcı "CIF" yazdığında bu terimi taşıyan kolonlar doğrudan aday havuzuna girer.
Bu eşleşme skorlamada +0.15 bonus alır (en güvenilir tek sinyal).

**(c) LLM ile genişletme (opsiyonel)**

Local model eş anlamlı, İngilizce karşılık ve olası kolon adı varyasyonu üretir.

**Kritik kısıt:** LLM'in ürettiği terimler yalnızca **aday havuzunu genişletmede**
kullanılır, **skoru belirlemede kullanılmaz**. Aksi halde model bir kavramı yanlış
anladığında arama tamamen sapar. Genişletme terimleri orijinal sorgudan düşük ağırlık
alır (varsayılan 0.6).

### 7.3 Ters yönde genişletme (indeks zamanı)

Sorguyu genişletmek yerine **sözlüğü indeksleme anında genişletmek** de mümkün ve
çoğu zaman daha verimli:

Her kolon için local model bir kez çalışır, "bu alanı hangi ifadelerle ararlar?"
sorusuna 5-10 cevap üretir, bunlar indekse eklenir.

- **Avantaj:** maliyet sorgu başına değil sözlük başına. 11 bin satır için bir kez
  çalışır, sonra her arama hızlıdır.
- **Dezavantaj:** sözlük güncellendiğinde yeniden üretim gerekir.

En iyi sonuç ikisinin birlikte kullanılmasıyla alınır: indeks tarafında zengin
genişletme, sorgu tarafında hafif genişletme.

### 7.4 Kavram çıkarımı

Sorgu işleme aşamasında talep, bağımsız **kavramlara** ayrılmalı. Bu, obje kapsama
oranının hesaplanması için gereklidir (bkz. §8).

Örnek: *"Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı,
gayrimenkul, ihtiyaç kredisi) gösteren tablo"*

```
zaman:aylık
kırılım
terim:risk
terim:kredi kartı
terim:gayrimenkul
terim:ihtiyaç kredisi
terim:müşteri
```

LLM varsa bu ayrıştırmayı model yapar; yoksa kural tabanlı ipucu listeleriyle yapılır
(zaman ifadeleri, "kırılım/bazında/detay", "oran/yüzde", "adet/sayısı",
"tutar/toplam/bakiye" gibi kalıplar + kalan içerik kelimeleri).

---

## 8. Obje seviyesine toplama

**Bu bölüm projenin çekirdek iş kuralıdır. Refaktörlerde korunmalıdır.**

Arama kolon seviyesinde çalışır, ama iş birimi tablo arar. Kolon adayları tabloya
göre gruplanır ve obje skoru şöyle hesaplanır:

```
obje_skoru = 0.50 × en_iyi_kolon_skoru
           + 0.30 × kapsama_oranı
           + 0.10 × zaman_boyutu
           + 0.10 × granülerlik_uyumu
```

### 8.1 Bileşenler

**`en_iyi_kolon_skoru`** — objedeki en yüksek skorlu kolonun kural skoru (0–1).

**`kapsama_oranı`** — objede karşılanan farklı talep kavramı sayısı / talepteki toplam
kavram sayısı. Bir kolonun hangi kavramı karşıladığı, kolon adı + açıklama + eş
anlamlılar metninde kavram teriminin geçip geçmediğine bakılarak belirlenir.

**`zaman_boyutu`** — talepte zaman kavramı varsa (aylık, günlük, dönemsel), objede
bir zaman kolonu (`Period`, `DataDate`, `TranDate`, `KKB_DATE` vb.) olup olmadığı.
Talepte zaman kavramı yoksa bu bileşen 1.0 kabul edilir (cezalandırma yapılmaz).

**`granülerlik_uyumu`** — objede müşteri seviyesi anahtarı (`CustomerPartyId`,
`CustomerId`, `AccountNumber`) varsa 1.0; yalnızca işlem/hesap seviyesi anahtarı
varsa 0.5. Talep müşteri bazlı bir görünüm istiyorsa bu ayrım önemlidir.

### 8.2 Neden böyle

Gerçek örnek: "aylık ve ürün kırılımlı risk" talebinde `vPRCArrayAllotment` kazandı.
Tek bir kolonu mükemmel eşleştiği için değil; `ConsumerBalance`,
`HousingFinanceBalance`, `VehicleConsumerBalance`, `RealEstateTTKBalance`,
`LeasingBalance` kolonlarını **birlikte** taşıdığı ve `Period` kolonu olduğu için.

Yalnızca en iyi kolon skoruna bakılsaydı, tek bir "risk" kolonu olan başka bir tablo
öne çıkardı ve cevap yanlış olurdu.

### 8.3 Tablo birleştirme önerisi

Hiçbir tek tablo tüm kavramları karşılamıyorsa, ancak iki tablo birlikte karşılıyorsa,
rapor bunu belirtmeli. Gerçek örnek: `vPRCArrayAllotment` (ürün kırılımı var, kart
yok) + `vPRCArrayCard` (kart var) → `CustomerPartyId + Period` ile birleştirilebilir.

Bu özellik M5'te değerlendirilmeli: ortak anahtar kolonu (aynı ada sahip anahtar
kolonlar) ve aynı zaman kolonu formatı olan tablolar aday birleştirme çifti sayılır.

---

## 9. Skorlama rubriği

Amaç **tutarlılık**: aynı soru farklı zamanlarda aynı skoru almalı.

### 9.1 İki bileşenli skor

```
final = w_rule × rule_score + w_llm × llm_score
```

Varsayılan: `w_rule = 0.6`, `w_llm = 0.4`. LLM kapalıysa `w_rule = 1.0`.

Gerekçe: yalnızca model skoruna güvenilirse aynı soru farklı zamanlarda farklı sonuç
verir ve iş birimi bunu fark eder. Kural bileşeni deterministik ve açıklanabilirdir.

### 9.2 Kural bileşeni (rule_score)

Taban: normalize edilmiş (0–1) arama skoru. Üzerine:

| Sinyal | Etki | Örnek |
|---|---|---|
| Kolon adı birebir eşleşme | +0.30 | sorgu `CreditCardLimitRate` |
| Kolon adı talebi kapsıyor | +0.20 | "limit doluluk" ⊂ `CardLimitFullnessToday` |
| Açıklamada kavramlar geçiyor | +0.15 | açıklamada "limit doluluk oranı" ifadesi |
| Sözlük eş anlamlı eşleşmesi | +0.15 | en güvenilir tek sinyal |
| Kurumsal terim sözlüğü eşleşmesi | +0.10 | dolaylı eşleşme |
| Yalnızca LLM genişletmesiyle eşleşme | +0.00 | havuza girer, skor almaz |
| Talep edilen zaman boyutu var | +0.10 | "aylık" istendi, `Period` var |
| Hazır değer yok, türetme gerekli | −0.15 | oran istendi, pay/payda var |
| Granülerlik farkı | −0.10 | müşteri istendi, tablo işlem bazlı |
| Kapsam farkı | −0.10 | kart istendi, alan tüm limitleri kapsıyor |
| `[MODEL TAHMİNİ]` bayrağı | ×0.85 | açıklama doğrulanmamış |
| İsimlendirme/içerik uyumsuzluğu | ×0.90 | Sheet2 kalite bulgusu |

Sonuç 0–1 aralığına kırpılır.

### 9.3 Seviye eşikleri

| Skor | Seviye | Anlamı |
|---|---|---|
| 0.80 – 1.00 | **Yüksek** | Alan adı veya açıklaması sorulan kavramla doğrudan örtüşüyor |
| 0.50 – 0.79 | **Orta** | İlişkili; kapsam, granülerlik veya tanım farkı var |
| 0.00 – 0.49 | **Düşük** | Dolaylı ilişki; sorulan veri bu alandan türetilebilir |

### 9.4 Batch modu durum etiketi

| Etiket | Koşul |
|---|---|
| **Hazır** | En iyi eşleşme ≥ 0.80 ve türetme gerektirmiyor |
| **Kısmen hazır** | 0.50 – 0.79, veya ≥ 0.80 ama kapsam/format farkı var |
| **Türetilmeli** | Hazır kolon yok; işlem seviyesi tablodan hesaplanabilir |
| **Bulunamadı** | Tüm adaylar eşiğin altında |

### 9.5 Eşikler ve "bulunamadı"

- `min_candidate_score = 0.25` — altındaki adaylar hiç gösterilmez.
- `min_answer_score = 0.35` — hiçbir aday geçemezse cevap "Sözlükte doğrudan karşılığı
  bulunamadı" olur.
- **Sonuç sayısı sabit değildir.** Beş satır doldurmak için zayıf aday eklenmez; iki
  güçlü sonuç varsa iki sonuç döner. Yanlış öneri, öneri yokluğundan daha maliyetlidir.

### 9.6 Metin alanları

Her öneri üç metin taşır:

- **Gerekçe** — neden eşleşti. Sözlükteki tanıma atıf yapar.
- **Kısıt / Dikkat** — kapsam farkı, türetme ihtiyacı, kalite bayrağı, karıştırılma
  riski. Yoksa `-`.
- **Kullanım önerisi** — hangi durumda bu seçenek tercih edilmeli.

Kural tabanlı modda bu metinler sinyallerden şablonla üretilir; LLM modunda model yazar.

### 9.7 Kalibrasyon süreci

1. `tests/golden_set.yaml` referanstır.
2. `vsa eval` recall@1/3/5 ve MRR üretir.
3. Ağırlık değişikliği öncesi metrik kaydedilir, sonrası karşılaştırılır.
4. Regresyon varsa değişiklik geri alınır.

---

## 10. LLM katmanı

### 10.1 Modelin rolü

Model **arama yapmaz**, **alan adı üretmez**. Yaptığı tek iş:

1. Verilen aday listesinden seçim yapmak
2. Gerekçe ve kısıt notu yazmak
3. Kavramsal uyum skoru vermek

Ağır yük arama katmanındadır. Bu nedenle **7–14B sınıfı bir model yeterlidir**.

### 10.2 Model önerileri (kapalı ağ, local)

| Rol | Aday | Not |
|---|---|---|
| Embedding | BGE-M3 | Tek modelden hem yoğun hem seyrek vektör; hibrit aramayı tek modelle kurar |
| Embedding (alt.) | multilingual-e5-large | |
| Reranker | bge-reranker-v2-m3 | Cross-encoder, CPU'da da çalışır; ilk 100'ü 30'a indirirken kaliteyi artırır |
| Üretim | Qwen2.5 14B Instruct (quantize) | Türkçe gerekçe kalitesi test edilmeli |

Nihai seçim kurum donanımına ve Türkçe kalite karşılaştırmasına göre yapılmalı; karar
`docs/DECISIONS.md` içine yazılmalı.

### 10.3 Arayüz

OpenAI uyumlu `/v1/chat/completions` beklenir (vLLM, llama.cpp server, Ollama hepsi
bu arayüzü sunar). `llm/client.py` soyut bir arayüz tanımlamalı ve `NullClient`
(LLM kapalıyken) implementasyonu bulunmalı — böylece uygulama LLM olmadan da çalışır.

### 10.4 Kısıtlı üretim

Çıktı JSON şemasına zorlanmalı: vLLM'de `guided_json`, llama.cpp'de GBNF. Bu, parse
hatalarını sıfıra indirir.

**Daha önemlisi:** modele alan adı yazdırmak yerine aday listesindeki `candidate_id`
değerini seçtirmek, uydurma alan üretme riskini **yapısal olarak** ortadan kaldırır.

### 10.5 Prompt taslakları

**Sorgu genişletme — sistem:**

```
Sen bir bankacılık veri ambarı uzmanısın. Kullanıcının aradığı veri kavramı için
eş anlamlı ifadeler, İngilizce karşılıklar ve olası kolon adı varyasyonları
üreteceksin. Katılım bankacılığı terminolojisini dikkate al (kredi = fon
kullandırım, faiz = kâr payı, leasing = icare gibi).

SADECE JSON döndür. Açıklama, ön söz, markdown kullanma.
```

**Sorgu genişletme — kullanıcı:**

```
Aranan kavram: {query}

Şu şemada JSON üret:
{"synonyms_tr": [...], "terms_en": [...], "column_name_guesses": [...],
 "concepts": [...]}

- synonyms_tr: en fazla 8 Türkçe eş anlamlı/yakın ifade
- terms_en: en fazla 6 İngilizce karşılık
- column_name_guesses: en fazla 6 olası kolon adı (CamelCase)
- concepts: talebin ayrıştırıldığı bağımsız kavramlar
```

**Hakem — sistem:**

```
Sen bir veri ambarı analistisin. Kullanıcının talebine karşılık, sana verilen
ADAY LİSTESİNDEN en uygun alanları seçeceksin.

Kurallar:
- Yalnızca listedeki candidate_id değerlerini kullan. Yeni alan adı UYDURMA.
- Listede uygun aday yoksa boş liste döndür. Liste doldurmak için zorlama.
- Her seçim için gerekçeyi sözlük açıklamasına dayandır.
- Kapsam farkı, granülerlik farkı veya türetme ihtiyacı varsa kısıt alanında yaz.
- SADECE JSON döndür.
```

**Hakem — kullanıcı:**

```
TALEP: {query}

ADAYLAR:
[{"candidate_id": "c001", "object": "EDWDM.CMP.vCardLimitFullness",
  "column": "CardLimitFullnessToday", "dataset_group": "...",
  "description": "...", "flags": ["..."]}, ...]

Şu şemada JSON üret:
{"matches": [
  {"candidate_id": "c001", "confidence": 0.0-1.0,
   "reason": "Türkçe gerekçe, 1-2 cümle",
   "caveat": "Türkçe kısıt notu veya '-'",
   "usage": "Türkçe kullanım önerisi"}
]}
```

**İndeks zamanı genişletme (kolon başına bir kez):**

```
Alan: {object}.{column}
Açıklama: {description}

Bir iş birimi çalışanı bu alanı ararken hangi ifadeleri kullanır?
En fazla 8 kısa ifade, Türkçe ve İngilizce karışık olabilir.
SADECE JSON dizi döndür: ["...", "..."]
```

Sıcaklık 0.1–0.2. Tüm promptlar Türkçe; model Türkçe gerekçe üretir.

### 10.6 Hata toleransı

- JSON parse edilemezse bir kez `repair` promptu denenir, sonra kural tabanlı sonuca
  düşülür. **LLM hatası aramayı durdurmamalı.**
- `confidence` 0–1 aralığına kırpılır.
- Bilinmeyen `candidate_id` içeren satır düşürülür ve loglanır.

---

## 11. Doğrulama katmanı

`validate.py`, çıktıdaki her `(obje, kolon)` çiftini sözlükte arar. Bulunmayan satır
sessizce düşürülür ve `WARNING` seviyesinde loglanır.

Bu tek kontrol, bu tür uygulamalardaki en büyük güven kırıcıyı — var olmayan bir alan
önermeyi — ortadan kaldırır. Düşürülen satır sayısı aynı zamanda modelin halüsinasyon
eğiliminin ölçüsüdür ve izlenmelidir.

Doğrulama LLM açık olsun olmasın çalışmalı (kural tabanlı modda da koruyucu katman
olarak kalır).

---

## 12. Çıktı şeması (Excel)

### 12.1 Ortak tasarım kuralları

- Yazı tipi **Arial**
- Başlık satırı: koyu lacivert zemin `1F3864`, beyaz kalın yazı
- Güven skoru hücresi `0%` formatında
- Seviye hücresi renkli: Yüksek `C6EFCE`, Orta `FFEB9C`, Düşük `FFC7CE`
- Durum etiketi renkli: Hazır `C6EFCE`, Kısmen hazır `FFEB9C`, Türetilmeli `FCE4D6`,
  Bulunamadı `FFC7CE`
- Tüm veri hücrelerinde ince kenarlık ve `wrap_text`
- Kılavuz çizgileri kapalı, başlık satırı dondurulmuş, otomatik filtre açık

### 12.2 Mod `ask` — sekmeler

**Özet**
- Başlık, kaynak sözlük dosyası + sürüm özeti, üretim tarihi
- Talep metni
- Genel sonuç cümlesi (VAR / KISMEN VAR / BULUNAMADI + kısa gerekçe)
- Güven skoru ölçeği tablosu
- Yöntem notları (hangi katmanlar çalıştı, LLM kullanıldı mı, genişletme terimleri)

**Öneriler**

| Kolon | İçerik |
|---|---|
| Sıra | 1..N |
| Veritabanı / Şema / Obje | Üç ayrı kolon |
| Veri Seti Grubu | Sözlükten |
| İlgili Alanlar | Çok satırlı; objede eşleşen kolonlar |
| Gerekçe | Neden eşleşti |
| Kısıt / Dikkat | Kapsam farkı, türetme, kalite bayrağı |
| Güven Skoru | `0%` formatı |
| Güven Seviyesi | Yüksek / Orta / Düşük |
| Kullanım Önerisi | Hangi durumda tercih edilmeli |

**Alan Detayları** — önerilen her alanın sözlükteki tam açıklaması.
Kolonlar: Sıra, Obje, Alan Adı, Sözlük Açıklaması, Kalite Bayrağı.

**Notlar ve Öneriler** — kapsam notu, netleştirme soruları, top-N dışı kalan yakın
adaylar, veri kalitesi uyarıları, doğrulama notu.
Kolonlar: Kapsam, Başlık, Açıklama.

### 12.3 Mod `batch` — sekmeler

**Özet**
- Genel sonuç cümlesi
- Alan bazında durum tablosu: `#`, Talep Alanı (TR), Talep Alanı (EN), Durum,
  En İyi Eşleşme, Güven
- "Tek tablo kapsama" analizi: hangi tablo talep edilen kaç alanı karşılıyor
- Durum ve güven ölçeği açıklaması

**Alan Eşleştirme** — her talep alanı için top-N satır:
`#`, Talep Alanı (TR), Talep Alanı (EN), Talep Açıklaması, Durum, Öneri sırası,
Obje, Veri Seti Grubu, Önerilen Alan(lar), Gerekçe, Kısıt / Dikkat, Güven, Seviye

**Alan Detayları** — önerilen alanların sözlük tanımları (tekilleştirilmiş).

**Notlar ve Öneriler** — aynı yapı.

### 12.4 Dosya adlandırma

```
out/VSA_<mod>_<slug>_<YYYYMMDD_HHMM>.xlsx
```

`slug`: talebin ilk 40 karakterinden üretilen ASCII kısaltma.

---

## 13. Değerlendirme ve golden set

### 13.1 Neden gerekli

Sorgu genişletme bazen isabeti artırır, bazen gürültü getirir. Hangi
konfigürasyonun kazandığı sözlüğe ve iş biriminin dil alışkanlığına bağlıdır, baştan
kestirilemez. Ölçmeden ayar değiştirmek körlemesine gitmektir.

### 13.2 Metrikler

- **recall@1 / @3 / @5** — beklenen obje ilk N'de mi
- **MRR** — ortalama karşılıklı sıra
- **Alan bazlı doğruluk** (batch modu) — beklenen kolon önerilenler arasında mı
- **Doğrulamada düşürülen satır oranı** — halüsinasyon göstergesi

### 13.3 Golden set formatı

`tests/golden_set.yaml`:

```yaml
- id: q001
  query: "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak
          (kredi kartı, gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo var mı?"
  expected_objects:
    - EDWDM.MDL.vPRCArrayAllotment
    - EDWDM.MDL.vPRCArrayCard
    - EDWDM.CON.vProjectRisk
  expected_columns:
    - EDWDM.MDL.vPRCArrayAllotment.ConsumerBalance
    - EDWDM.MDL.vPRCArrayAllotment.HousingFinanceBalance
    - EDWDM.MDL.vPRCArrayAllotment.Period
  notes: "Kredi kartı kırılımı vPRCArrayAllotment'ta yok; vPRCArrayCard ile
          CustomerPartyId + Period üzerinden birleştirilmeli."
  source: manuel-analiz-2026-09
```

**Kural:** Mevcut maddeler silinmez, yalnızca eklenir. Hedef 30–50 madde. İş
biriminden gelen her doğrulanmış talep sete eklenir.

### 13.4 Karşılaştırılacak konfigürasyonlar

| Konfigürasyon | Amaç |
|---|---|
| Genişletmesiz BM25 | Taban çizgi |
| + kurumsal terim sözlüğü | Elle kurulan sözlüğün katkısı |
| + sözlük içi eş anlamlı indeksi | En değerli sinyalin katkısı |
| + LLM genişletme | Ek kazanç var mı, gürültü getiriyor mu |
| + yoğun vektör (hibrit) | M3 kazancı |
| + reranker | M3 kazancı |

---

## 14. Proje yapısı ve modüller

```
vsa/
├─ CLAUDE.md                     # Claude Code için proje yönergesi
├─ README.md
├─ pyproject.toml
├─ config/
│   ├─ settings.example.yaml
│   ├─ term_dictionary.csv       # kurumsal terim sözlüğü (Ek B tohumu)
│   └─ stopwords_tr.txt
├─ docs/
│   ├─ ARCHITECTURE.md
│   ├─ SCORING.md
│   ├─ DATA_CONTRACT.md
│   ├─ OUTPUT_SCHEMA.md
│   ├─ PROMPTS.md
│   ├─ ROADMAP.md
│   ├─ DECISIONS.md
│   └─ OPERATIONS.md
├─ src/vsa/
│   ├─ config.py                 # ayar yükleme (YAML + varsayılanlar)
│   ├─ models.py                 # DictColumn, ColumnHit, ObjectMatch, AnalysisResult
│   ├─ loader.py                 # sözlük okuma, eş anlamlı/bayrak ayrıştırma, sürüm
│   ├─ text/normalize.py         # Türkçe normalizasyon (TEK nokta)
│   ├─ index/bm25.py             # alan ağırlıklı BM25
│   ├─ index/dense.py            # yoğun vektör (M3)
│   ├─ index/hybrid.py           # RRF birleştirme, min-max normalize
│   ├─ index/rerank.py           # cross-encoder (M3)
│   ├─ expansion/query_expander.py  # terim sözlüğü + eş anlamlı ters indeks + LLM
│   ├─ scoring/rules.py          # kural tabanlı kolon skorlaması
│   ├─ scoring/aggregate.py      # obje seviyesine toplama (KRİTİK)
│   ├─ scoring/combine.py        # kural + LLM birleştirme, seviye/durum etiketi
│   ├─ llm/client.py             # soyut arayüz + NullClient + local endpoint
│   ├─ llm/judge.py              # aday değerlendirme
│   ├─ validate.py               # sözlüğe karşı doğrulama
│   ├─ report/excel.py           # Excel rapor üretimi
│   ├─ pipeline.py               # orkestrasyon
│   └─ cli.py                    # typer tabanlı CLI
├─ tests/
│   ├─ golden_set.yaml
│   ├─ test_normalize.py         # Türkçe küçük harf, CamelCase, gövdeleme
│   ├─ test_loader.py            # eş anlamlı ve bayrak ayrıştırma
│   ├─ test_scoring.py           # rubrik kuralları
│   ├─ test_aggregate.py         # obje toplama mantığı
│   └─ test_golden.py            # golden set üzerinde recall
├─ eval/run_eval.py
└─ data/
    ├─ dictionary.xlsx           # (gizli, repoya girmez)
    └─ index/                    # üretilen indeks dosyaları
```

### 14.1 CLI komutları

```bash
vsa index --dictionary data/dictionary.xlsx    # indeksi kurar
vsa ask "kredi kartı limit doluluk oranı"      # tekil soru, Excel üretir
vsa ask "..." --no-excel --top 5               # terminale yazdırır
vsa batch --input data/requests.xlsx --out out/
vsa eval                                       # golden set metrikleri
```

### 14.2 Kodlama standartları

- Python 3.11+, tip ipuçları zorunlu, `ruff` + `mypy` temiz.
- Saf fonksiyonlar tercih edilir; I/O yalnızca `loader.py`, `report/`, `cli.py`.
- Her yeni skorlama kuralı bir testle birlikte gelir.
- Kullanıcıya dönük metinler (rapor başlıkları, gerekçeler) **Türkçe**; kod, değişken
  adı, commit mesajları **İngilizce**.
- Hiçbir modülde doğrudan `.lower()` çağrılmaz — `text/normalize.py` kullanılır.

---

## 15. Ayarlar

`config/settings.yaml` (örneği `settings.example.yaml` olarak repoda durur):

```yaml
dictionary:
  path: data/dictionary.xlsx
  sheet: Sheet1
  quality_sheet: Sheet2        # opsiyonel

index:
  dir: data/index

search:
  top_k_columns: 120
  top_k_objects: 10
  field_weights:
    name: 3
    synonyms: 2
    description: 1
  bm25:
    k1: 1.2
    b: 0.75

expansion:
  enabled: true
  weight: 0.6                  # genişletme terimlerinin ağırlığı
  term_dictionary: config/term_dictionary.csv

scoring:
  w_rule: 0.6
  w_llm: 0.4
  min_candidate_score: 0.25
  min_answer_score: 0.35
  object:
    best_column: 0.50
    coverage: 0.30
    time: 0.10
    granularity: 0.10
  flag_penalty:
    model_estimated: 0.85
    naming_mismatch: 0.90

llm:
  enabled: false
  endpoint: ""                 # OpenAI uyumlu /v1/chat/completions
  model: ""
  temperature: 0.1
  timeout: 120

report:
  out_dir: out
```

---

## 16. Alınmış kararlar (ADR)

### ADR-001 — Kapsam sınırlaması koda gömülmez

**Bağlam.** Bir iş birimi belirli ön eke sahip objelerin (`vPRC*`) önerilmemesini
istedi. Başka ekiplerde benzer kısıtlar çıkabilir.

**Karar.** Uygulama sözlükte ne varsa onu arar. Kapsam daraltma, yüklenen sözlük
dosyası üzerinden yapılır. Uygulamada filtre parametresi yoktur.

**Gerekçe.** Kapsam kuralları ekip ve zamana göre değişir; koda gömülürse her
değişiklik sürüm gerektirir. Sözlük zaten sürümlenen bir girdidir.

**Sonuç.** Farklı kapsamlar için farklı sözlük dosyası ve indeks kullanılır.

---

### ADR-002 — LLM aday listesinden seçim yapar, üretim yapmaz

**Bağlam.** Modelin var olmayan alan adı üretmesi bu tür uygulamalardaki en büyük
güven kırıcı.

**Karar.** Modele 30–40 aday verilir; model yalnızca `candidate_id` döndürür. Çıktı
ayrıca sözlüğe karşı doğrulanır.

**Gerekçe.** Halüsinasyonu yapısal olarak engeller, küçük modelle çalışmayı mümkün
kılar, maliyeti düşürür.

**Sonuç.** `llm/judge.py` + `validate.py`. Doğrulanamayan satır düşürülür ve loglanır.

---

### ADR-003 — Skor iki bileşenli

**Bağlam.** Yalnızca LLM skoru kullanılırsa aynı soru farklı zamanlarda farklı skor alır.

**Karar.** `final = 0.6 × kural + 0.4 × llm`. LLM yoksa kural bileşeni tek başına çalışır.

**Gerekçe.** Tutarlılık, açıklanabilirlik ve LLM'siz çalışabilme.

**Sonuç.** `scoring/combine.py`; ağırlıklar ayarlardan değiştirilebilir.

---

### ADR-004 — Sorgu genişletme yalnızca seyrek kola uygulanır

**Bağlam.** Eş anlamlı genişletmesi BM25'te büyük fayda sağlar; yoğun vektörde sorgu
vektörünü bulanıklaştırır.

**Karar.** Genişletilmiş terimler BM25 koluna, orijinal ifade yoğun kola gider.

**Gerekçe.** Embedding zaten anlamsal yakınlığı yakalar; genişletme orada gürültü üretir.

**Sonuç.** `QueryExpander` iki ayrı çıktı döndürür: `sparse_terms`, `dense_text`.

---

### ADR-005 — Obje seviyesine toplama zorunlu

**Bağlam.** Arama kolon seviyesinde çalışır ama iş birimi tablo arar.

**Karar.** Obje skoru = en iyi kolon + kapsama oranı + zaman boyutu + granülerlik.

**Gerekçe.** Manuel analizlerde kazanan tablolar, talebin birden fazla kavramını
birlikte karşıladıkları için kazandı.

**Sonuç.** `scoring/aggregate.py`. Refaktörlerde korunması gereken çekirdek kural.

---

### ADR-006 — "Bulunamadı" geçerli bir cevap

**Bağlam.** Sabit sayıda sonuç döndürme zorunluluğu zayıf adayların listeye girmesine
yol açar ve güveni düşürür.

**Karar.** Eşik altındaki adaylar gösterilmez; hiçbiri eşiği geçmezse "bulunamadı" denir.

**Gerekçe.** Yanlış öneri, öneri yokluğundan daha maliyetlidir.

---

### ADR-007 — Kalite bayrakları çıktıya taşınır

**Bağlam.** Sözlükteki 240 açıklama model tahminidir ve doğrulanmamıştır.

**Karar.** Bu alanlar skorda cezalandırılır (×0.85) ve raporda açıkça gösterilir.

**Gerekçe.** İş birimi bir alanı kullanmadan önce açıklamasının doğrulanmamış olduğunu
bilmeli.

---

### ADR-008 — LLM'siz çalışabilirlik korunur

**Bağlam.** Local LLM kurulumu gecikirse veya servis düşerse uygulama çalışmaya devam
etmeli.

**Karar.** Kural tabanlı mod her zaman desteklenir; LLM opsiyonel katmandır. LLM
hatası aramayı durdurmaz, kural sonucuna düşülür.

**Gerekçe.** Kapalı ağda model servisi bağımlılığı operasyonel risk yaratır.

---

## 17. Yol haritası

### M1 — Çekirdek (LLM'siz çalışan MVP)

**Amaç:** LLM olmadan, sadece arama + kural skorlamasıyla anlamlı sonuç üretmek.
Arama katmanı sağlam olmadan LLM eklemek sorunu gizler.

- Sözlük yükleme, eş anlamlı ve bayrak ayrıştırma, sürüm özeti
- Türkçe normalizasyon (küçük harf, ASCII katlama, CamelCase, hafif gövdeleme)
- Alan ağırlıklı BM25 indeksi
- Kurumsal terim sözlüğü + sözlük içi eş anlamlı ters indeksi
- Kural tabanlı skorlama ve obje seviyesine toplama
- `ask` modu Excel raporu
- CLI: `index`, `ask`

**Kabul kriteri:** Golden set'teki üç maddede beklenen obje ilk 5'te.

### M2 — Değerlendirme altyapısı

- `eval/run_eval.py`: recall@1/3/5, MRR
- Golden set'i 30–50 maddeye çıkarma (iş biriminden gerçek talepler)
- Konfigürasyon karşılaştırma raporu

### M3 — Hibrit arama

- Yoğun vektör indeksi (BGE-M3 veya e5-large)
- RRF ile birleştirme
- Cross-encoder reranker
- Kazancın M2 metrikleriyle doğrulanması

### M4 — LLM katmanı

- Local endpoint istemcisi, JSON şema zorlaması
- Hakem katmanı
- LLM ile sorgu genişletme (yalnızca seyrek kola)
- İndeks zamanı ters genişletme
- Zemberek/Snowball gövdeleme yükseltmesi

### M5 — Batch modu

- Talep tablosu okuma (TR / EN / açıklama)
- Alan bazlı durum etiketi
- "Tek tablo kapsama" analizi
- Tablo birleştirme önerisi (ortak anahtar + zaman kolonu tespiti)
- Batch Excel raporu

### M6 — Arayüz

- Slack/Teams botu veya basit web arayüzü (FastAPI + tek sayfa)
- Rapor indirme, sözlük sürümü gösterimi

**Not:** İş biriminin ayrı bir uygulamaya gitmesi yerine mevcut mesajlaşma
platformundan erişmesi kullanım oranını belirgin artırır.

### M7 — Geri bildirim döngüsü

- Onay/ret butonu ve kaydı
- **Onaylanan eşleşmede sorgu terimini ilgili kolonun eş anlamlılar listesine ekleme
  akışı** — sözlük kullanıldıkça zenginleşir
- Onaylanan talepleri golden set'e aktarma
- Sözlük zenginleştirme önerileri raporu

---

## 18. Kapalı ağ ve işletim notları

### 18.1 Kurulum kısıtları

- Uygulama hiçbir dış adrese çıkmaz. Yeni bağımlılık eklenirken bu kontrol edilmeli.
- Wheel'ler kuruma alınmalı: `pandas`, `openpyxl`, `pyyaml`, `typer`, `rich`;
  dense için `sentence-transformers`, `faiss-cpu`.
- Model ağırlıkları yerel dizinden yüklenir; yol ayarlardan verilir.
- Sözlük kurum içi veridir; indeks dosyaları da aynı gizlilik sınıfındadır.
  `data/` dizini `.gitignore` içinde olmalı.

### 18.2 İndeks yaşam döngüsü

`vsa index` çalıştırıldığında `data/index/` altında üretilenler:

| Dosya | İçerik |
|---|---|
| `columns.json` / `.parquet` | Normalize edilmiş kolon kayıtları |
| `bm25.json` | Terim frekansları, doküman uzunlukları |
| `synonym_index.json` | Eş anlamlı → kolon id ters indeksi |
| `meta.json` | Sözlük SHA-256, satır sayısı, üretim zamanı, ayar özeti |

Sözlük değiştiğinde indeks yeniden kurulur. Rapor üretiminde `meta.json` içindeki SHA
ile mevcut sözlük karşılaştırılır; uyumsuzsa uyarı verilir.

### 18.3 Loglama

- Her sorgu için: sorgu metni, genişletme terimleri, aday sayısı, seçilen objeler,
  skorlar, süre.
- Doğrulamada düşürülen satırlar `WARNING` seviyesinde (halüsinasyon göstergesi).
- Kişisel veri loglanmaz. Sorgu metinleri iş birimi terminolojisi içerir; saklama
  süresi kurum politikasına göre belirlenmeli.

### 18.4 Performans beklentisi

- 11 bin satırlık sözlük için BM25 indeksi bellekte birkaç MB.
- LLM'siz sorgu yanıtı: saniyenin altı.
- LLM'li: model ve donanıma bağlı, 5–15 saniye.
- Batch modda alan başına bir sorgu; 10 alanlık tablo LLM'li modda 1–3 dakika
  sürebilir. Paralelleştirme M5'te değerlendirilmeli.

### 18.5 KVKK notu

Sözlükte kişisel veri taşıyan alanlar var (`CustomerName`, `ReceiverIdentityNumber`,
`SenderTaxNumber` vb.). Uygulama bu alanları önerirken raporda maskelenmiş
alternatiflerin varlığını belirtmeli (örn. `MaskedReceiverIdentityId`). Bu, gerekçe
şablonlarına bir kural olarak eklenebilir: kolon açıklamasında "KVKK" veya "kişisel
veri" ifadesi geçiyorsa kısıt notuna uyarı düşülür.

---

## 19. Açık sorular

Geliştirmeye başlamadan netleştirilmesi gerekenler:

1. **Donanım.** Embedding ve LLM hangi donanımda koşacak? GPU var mı, VRAM ne kadar?
   Bu, model boyutu seçimini belirler.
2. **Sözlük güncelleme sıklığı.** İndeks yeniden kurulumu otomatik mi olacak, manuel mi?
3. **Erişim yetkisi.** Her iş birimi tüm sözlüğü görebilecek mi, yoksa şema/veri seti
   grubu bazlı kısıt gerekecek mi? (ADR-001 gereği bu, farklı sözlük dosyalarıyla
   çözülür — ama kimin hangi dosyaya erişeceği kararı gerekiyor.)
4. **Rapor saklama.** Üretilen Excel'ler nerede saklanacak, gizlilik sınıfı nedir?
5. **Arayüz tercihi.** Slack mi, Teams mi, web mi? (M6 kapsamı buna göre şekillenir.)
6. **Terim sözlüğü sahipliği.** `term_dictionary.csv` kim tarafından, hangi süreçle
   güncellenecek?

---

## EK A — Gerçek analiz örnekleri

Bu üç analiz elle yapıldı ve golden set'in ilk maddeleridir. Uygulamanın bunları
yeniden üretebilmesi M1'in kabul kriteridir.

### A.1 Talep: aylık ve ürün kırılımlı müşteri riski

> "Müşterilerin risk bilgilerini aylık bazda ve kırılımlı olarak (kredi kartı,
> gayrimenkul, ihtiyaç kredisi vb.) gösteren bir tablo mevcut mudur?"

**Beklenen kavramlar:** zaman:aylık, kırılım, terim:risk, terim:kredi kartı,
terim:gayrimenkul, terim:ihtiyaç, terim:müşteri

**Sonuç (tüm sözlük):**

| # | Obje | Alanlar | Güven | Gerekçe özeti |
|---|---|---|---|---|
| 1 | `EDWDM.MDL.vPRCArrayAllotment` | `Period`, `ConsumerBalance`, `HousingFinanceBalance`, `VehicleConsumerBalance`, `RealEstateTTKBalance`, `LeasingBalance`, `CustCashRisk`, `NonCashRisk` | %85 | Müşteri bazında, YYYYMM periyotlu; ürün bazlı bakiye/limit/maks bakiye. **Kısıt:** kredi kartı ayrı kolon değil |
| 2 | `EDWDM.MDL.vPRCArrayCard` | `Period`, `LimitInfoPersonalCC`, `PersonalCreditCardSumAmount`, `CreditCardLimitRate` | %75 | 1'deki kart boşluğunu aynı periyot yapısında tamamlıyor |
| 3 | `EDWDM.IDM.vKKBGGCI` | `FINANCETYPE`, `TOTALOUTSTANDINGBALANCE`, `CREDITLIMIT`, `KKB_DATE` | %60 | Ürün türü kırılımı net; **kısıt:** KKB sorgu bazlı, düzenli aylık seri değil |

**Aynı talep, `vPRC*` hariç tutulduğunda:**

| # | Obje | Güven |
|---|---|---|
| 1 | `EDWDM.CON.vProjectRisk` (`DataDate`, `ProductName`, `RiskAmountTL`, `CardRefNumberId`, `KTStatusName`) | %80 |
| 2 | `EDWDM.CON.vProductRiskInfo` (`TranDate`, `ProductName`, `ProfitableTotalRiskTL`, `CardLegalAmount`) | %65 |
| 3 | `EDWDM.IDM.vKKBGGCI` | %60 |

**Öğrenilen:** Aynı talebe farklı kapsamda farklı doğru cevap var. Kapsam sözlük
üzerinden yönetilmeli (ADR-001).

### A.2 Talep: kredi kartı limit doluluk oranı

**Sonuç (tüm sözlük):**

| # | Obje.Alan | Güven | Not |
|---|---|---|---|
| 1 | `EDWDM.MDL.vPRCCard.CreditCardLimitRate` | %95 | Açıklamada birebir "limit doluluk oranı" |
| 2 | `EDWDM.CMP.vCardLimitFullness.CardLimitFullnessToday` (+Avg30/60/90d) | %92 | Güncel + dönemsel ortalamalar |
| 3 | `EDWDM.MDL.vPRCArrayCard.CreditCardLimitRate` | %90 | `Period` var → aylık seri |
| — | `EDWDM.CMP.vCardLimitFullness.TotalLimitFullness` | %65 | **Kapsam farkı:** kart değil, tüm limitler |
| — | `EDWDM.CON.vCreditCardLimit.TotalUsedLimitTL / CardLimit` | %55 | Türetilebilir |

**Tuzak:** `vCreditCardLimit.CardLimitRatio` doluluk oranı **değildir** — kart
limitinin bir referans değere oranıdır. İsim benzerliği yanıltıcı; rapor bunu
belirtmeli.

### A.3 Talep: hedef tablo eşleştirme (10 alan, para transferi özeti)

İş birimi şu alanlardan oluşan bir tablo istedi:
`CustomerId`, `TransferType`, `Period`, `TransferCount`, `TotalTransferAmountTL`,
`DistinctTransactionPersonCount`, `DistinctBankCount`, `OwnAccountTransferCount`,
`OwnAccountTransferDistinctBankCount`, `OwnAccountTotalAmountTL`

**Sonuç:** Kısmen var. Çekirdek `EDWDM.TRX.vCustomerMoneyTransferSummary` tablosunda
müşteri + periyot bazında hazır.

| Talep Alanı | Durum | En iyi eşleşme | Güven |
|---|---|---|---|
| CustomerId | Hazır | `vPRCArrayMoneyTransfer.CustomerId` | %95 |
| TransferType | Kısmen | `vCustomerMoneyTransferSummary` — yön kolon adlarına gömülü | %60 |
| Period | Hazır | `vCustomerMoneyTransferSummary.Period` | %100 |
| TransferCount | Hazır | kanal bazlı `*Count` kolonlarının toplamı | %85 |
| TotalTransferAmountTL | Hazır | kanal bazlı `*AmountTL` kolonları | %88 |
| DistinctTransactionPersonCount | Türetilmeli | `vFASTOutgoing.ReceiverIdentityNumber` (DISTINCT) | %65 |
| DistinctBankCount | Türetilmeli | `vFASTOutgoing.ReceiverBankName` (DISTINCT) | %68 |
| OwnAccountTransferCount | Kısmen | `vFASTOutgoing` gönderen=alıcı filtresi | %65 |
| OwnAccountTransferDistinctBankCount | Türetilmeli | `vFASTOutgoing` filtre + DISTINCT banka | %60 |
| OwnAccountTotalAmountTL | Kısmen | `vCustomerMoneyTransferSummary.VirmanIntrabankMoneyTransferAmountTL` | %62 |

**Öğrenilenler:**
- Geniş (wide) formatta kodlanmış kırılımlar (`FASTIncomingCount`,
  `OutgoingIntrabankMoneyTransferCount`) unpivot gerektirir; uygulama bunu fark edip
  kısıt notuna yazmalı.
- "Kendi hesabına transfer" için hazır alan (`Virman*`) ile türetilmiş alan farklı
  kapsamlar taşıyor; ikisi de sunulmalı, fark açıkça yazılmalı.
- Netleştirme soruları raporun parçası: hangi kanallar dahil (FAST, havale, SWIFT,
  KAS, virman)? Klasik EFT beklentisi var mı?

---

## EK B — Kurumsal terim sözlüğü tohumu

`config/term_dictionary.csv` başlangıç içeriği. İş birimi geri bildirimiyle
büyütülecek. Format: `term,equivalents,domain,note` — eşleme iki yönlüdür.

```csv
term,equivalents,domain,note
fon kullandırım,kredi|finansman|loan|credit|kullandırım,katılım,Katılım bankacılığında kredinin karşılığı
kâr payı,faiz|getiri|profit share|interest|kar payı,katılım,
icare,leasing|finansal kiralama|ijara|kiralama,katılım,
murabaha,vadeli satış|cost plus financing,katılım,
sukuk,kira sertifikası|islamic bond,katılım,
katılma hesabı,mevduat|vadeli hesap|participation account,katılım,
tahsis,limit|kredi limiti|allotment|facility,kredi,
memzuç,risk merkezi|TBB risk merkezi|toplam risk,risk,
donuk alacak,takipteki alacak|NPL|non performing|tahsili gecikmiş,risk,
canlı risk,performing|aktif risk|live risk,risk,
nakdi risk,cash risk|nakit kredi riski,risk,
gayrinakdi risk,non cash risk|teminat mektubu riski|gayri nakdi,risk,
teminat mektubu,TM|letter of guarantee|garanti mektubu,risk,
doluluk oranı,kullanım oranı|utilization|fullness|limit kullanımı|limit doluluk,kart,
limit,tanımlı limit|credit limit|card limit,kart,
kredi kartı,KK|credit card|kart,kart,
banka kartı,debit card|debit kart,kart,
nakit avans,cash advance|nakit çekim,kart,
ihtiyaç kredisi,tüketici kredisi|consumer loan|ihtiyaç finansmanı|bireysel kredi,ürün,
konut kredisi,mortgage|housing finance|konut finansmanı,ürün,
taşıt kredisi,araç kredisi|vehicle loan|otomobil kredisi,ürün,
KMH,kredili mevduat hesabı|overdraft|artı para,ürün,
müşteri numarası,CIF|müşteri no|customer id|customer number|müşteri kimlik no,anahtar
müşteri SKEY,customer party id|party id|DWH müşteri no|surrogate key,anahtar
hesap numarası,account number|hesap no,anahtar
periyot,dönem|ay yıl|YYYYMM|period|month,zaman
veri tarihi,data date|rapor tarihi|iş tarihi|dönem sonu,zaman
işlem tarihi,transaction date|tran date|transfer date,zaman
para transferi,EFT|havale|money transfer|transfer|gönderim,işlem
FAST,anlık transfer|instant transfer|fonların anlık ve sürekli transferi,işlem
virman,hesaplar arası transfer|kendi hesabına transfer|internal transfer,işlem
SWIFT,uluslararası transfer|yurt dışı transfer|international transfer,işlem
alıcı,karşı taraf|receiver|beneficiary|lehtar,işlem
gönderen,sender|gönderici|remitter,işlem
bakiye,balance|tutar|meblağ,finansal
tutar,amount|meblağ|toplam,finansal
adet,sayı|count|işlem adedi|sayısı,finansal
gecikme gün sayısı,DPD|days past due|overdue day,risk
temerrüt olasılığı,PD|probability of default,risk
içsel derecelendirme,rating|IDM|internal rating|not,risk
IFRS 9 aşaması,stage|UFRS 9|evre,risk
KKB,kredi kayıt bürosu|credit bureau|findeks,dış veri
KRS,kredi referans sistemi,dış veri
segment,müşteri sınıfı|customer class|sınıf|bireysel kobi ticari kurumsal,müşteri
şube,branch|şube kodu,organizasyon
kanal,channel|işlem kanalı|dijital şube ATM,organizasyon
```

---

## SON SÖZ — Geliştirmeye başlarken

Öncelik sırası:

1. **Önce arama katmanını doğru kur.** Türkçe normalizasyon ve CamelCase ayrıştırma
   olmadan hiçbir şey çalışmaz. Bu iki şey en başta ve testlerle yazılmalı.
2. **Sözlüğün eş anlamlılar bölümünü ciddiye al.** Elinizdeki en değerli sinyal bu.
3. **Obje seviyesine toplamayı atlama.** Kolon listesi döndüren bir uygulama iş
   birimine faydasızdır.
4. **LLM'i en sona bırak.** Arama zayıfken LLM eklemek sorunu gizler.
5. **Golden set'i erken kur ve büyüt.** Ölçmeden ayar değiştirme.
6. **Var olmayan alan önerme.** Doğrulama katmanı pazarlıksızdır.
