# Veri Sözlüğü Talep Analizi — Metodoloji

> Bu doküman, iş birimi taleplerini veri sözlüğüyle eşleştirirken izlenen adımları,
> kullanılan arama tekniklerini, tuzak tespit yöntemlerini ve rapor üretim kurallarını
> anlatır. Amaç, aynı kalitede çıktının bir ajan tarafından tekrarlanabilmesidir.
>
> **Sürüm:** 1.0 · **Tarih:** 27 Eylül 2026

---

## 0. Temel ilke

Bu iş bir **arama** işi değil, bir **analiz** işidir.

Naif yaklaşım şudur: sorudaki kelimeleri sözlükte ara, en çok eşleşen 5 satırı döndür.
Bu yaklaşım hemen her talepte yanlış cevap üretir, çünkü:

- İş birimi kolon değil **tablo** arar.
- Doğru cevap çoğu zaman sorudaki kelimeleri **içermez** ("limit doluluk" → `CardLimitFullnessToday` bulunur ama "mevduat dağılımı" → `TotalDeposit` + `CompanySectorCodeCurrP` kesişimi bulunmaz).
- Sözlükte aynı kelimeyi taşıyan yüzlerce **yanlış** aday vardır ("skor" araması ~400 satır döndürür, doğru cevap 5 tanesidir).
- Kolon adı ile içeriği **örtüşmeyebilir** (`CompanySectorAge` firma yaşıdır, sektörle ilgisi yoktur).

Bu yüzden akış şu sırayla ilerler: **kavramlara ayır → geniş ara → aday tabloları tam oku → tuzakları ayıkla → tablo seviyesinde değerlendir → gerekçelendir**.

---

## 1. Adım: Talebi kavramlara ayır

Rapor yazmadan önce talep şu beş boyuta ayrıştırılır. Bu ayrıştırma sonraki her adımı belirler.

| Boyut | Soru | Örnek ("sektör bazlı mevduat dağılımı") |
|---|---|---|
| **Ölçüt** | Hangi büyüklük isteniyor? | mevduat bakiyesi |
| **Kırılım** | Hangi eksende bölünecek? | sektör |
| **Zaman** | Anlık mı, dönemsel mi? | belirtilmemiş → hem anlık hem periyot arandı |
| **Granülerlik** | Müşteri, hesap, işlem? | müşteri |
| **Kapsam** | Bireysel/tüzel, hangi ürün ailesi? | belirtilmemiş → ikisi de kontrol edildi |

**Önemli kural:** Talepte belirtilmeyen boyut **varsayılmaz**, açık uç olarak taşınır ve raporun sonunda netleştirme sorusu olarak sorulur. Örnek: "müşterinin kredi kartlarının bilgisi" talebinde hangi bilgi (künye/limit/borç/işlem) belirtilmediği için dördü de sunuldu, sonra netleştirme soruldu.

**Kavram sayısı, kapsama oranının paydasıdır.** "Aylık + ürün kırılımlı + risk" üç kavramdır; bir tablonun kaç tanesini karşıladığı skorunu belirler.

---

## 2. Adım: Terminoloji köprüsü kur

Arama yapmadan önce, talepteki her kavramın sözlükte hangi kelimelerle geçebileceği listelenir. Bu liste olmadan arama kaçırır.

Üç kaynak kullanılır:

**(a) Katılım bankacılığı karşılıkları.** Sözlük bu terminolojiyle yazılmış:

| İş birimi der | Sözlükte geçer |
|---|---|
| kredi, kredi kullandırımı | fon kullandırım, finansman |
| faiz | kâr payı, profit share |
| mevduat | toplanan fon, katılma hesabı (vadeli), cari hesap (vadesiz) |
| leasing | icare, finansal kiralama |
| vadeli hesap | katılma hesabı |
| KMH | kredili mevduat hesabı (katılım tarafında cari hesap üzerinden) |

**(b) Türkçe–İngilizce çiftleri.** Kolon adları İngilizce, açıklamalar Türkçe. Her kavram iki dilde de aranır: doluluk/fullness/utilization, kıdem/tenure, gecikme/delay/delinquency/DPD, temerrüt/default/PD.

**(c) Kısaltmalar ve kurum terimleri.** CIF, KKB, KRS, memzuç, IDM, EWS, DPD, NACE, TTC, LGD, IFRS 9.

Bu adım atlanırsa şu tip kaçırmalar olur: "mevduat" araması `TotalDeposit` alanını bulur ama `CurrentParticipation` (katılma hesabı bakiyesi) alanını bulmaz.

---

## 3. Adım: Çok turlu arama

Tek bir arama yeterli olmaz. Sırayla dört tür arama yapılır.

### 3.1 Geniş tarama — hangi objeler yoğun?

Kolon adı + açıklamada kavramı arar, sonucu **obje bazında sayar**. Amaç tekil kolon bulmak değil, konunun hangi tablolarda yoğunlaştığını görmek.

```python
t = (d.ColumnName + ' || ' + d.ColumnDescription).str.lower()
m = t.str.contains('kredi kart|credit card|kart limit')
print(d[m].groupby(['DAtabaseName','SchemaName','ObjectName','DatasetGroup'])
          .size().sort_values(ascending=False).head(25))
```

Çıktı, "hangi tablolar bu konunun merkezinde" sorusunu cevaplar. Tek bir kolonu eşleşen tablo ile 40 kolonu eşleşen tablo arasındaki fark burada görünür.

### 3.2 Obje adı taraması

Tablo adları çoğu zaman konuyu doğrudan söyler:

```python
sorted(set(d[d.ObjectName.str.lower().str.contains('card|kart')].ObjectName))
```

Bu tarama `vCreditCardList`, `vCardLimitFullness` gibi "tam isabet" tabloları ortaya çıkarır. Ayrıca `DatasetGroup` üzerinden de bakılır: sözlükte "Kart", "Mevduat", "Tüzel Mevduat" gibi hazır gruplar var.

### 3.3 Kesişim araması (kırılımlı talepler için kritik)

Talep iki kavramın kesişimiyse (sektör **ve** mevduat, ürün kırılımı **ve** risk), her kavram ayrı aranır, sonra **aynı objede ikisini birden taşıyanlar** bulunur:

```python
sek = t.str.contains('sektör|sektor|nace')
dep = t.str.contains('mevduat|katılma hesab|cari hesap|deposit|bakiye')
kesisim = sorted(set(d[sek].ObjectName) & set(d[dep].ObjectName))
```

Bu adım olmadan "sektör bazlı mevduat dağılımı" talebi doğru cevaplanamaz. Tek kavram araması ya sadece sektör boyut tablolarını ya da sadece bakiye tablolarını getirir.

Daha da güçlü varyantı, ürün kırılımlı taleplerde kullanılır — her ürün için ayrı bayrak çıkarıp objede kaç ürünün birlikte geçtiğini sayar:

```python
prod = {'kart':'kredi kart', 'konut':'konut', 'ihtiyac':'ihtiyaç', 'tasit':'taşıt|araç'}
g = pd.DataFrame({k: (t.str.contains(v) & t.str.contains('risk|bakiye')) for k,v in prod.items()})
g['obj'] = d.ObjectName
s = g.groupby('obj').sum(); s['n'] = (s>0).sum(axis=1)
print(s[s.n>=2].sort_values('n', ascending=False))
```

Bu, "kapsama oranı"nın pratikteki karşılığıdır.

### 3.4 Zaman ve anahtar kontrolü

Aday objelerde zaman ve granülerlik kolonları var mı:

```python
per = [c for c in x.ColumnName
       if any(k in c.lower() for k in ['period','datadate','trandate','reportdate'])]
key = [c for c in x.ColumnName
       if any(k in c.lower() for k in ['customerpartyid','customerid','accountnumber'])]
```

"Aylık" istenen bir talepte `Period` kolonu olmayan tablo, içerik olarak mükemmel eşleşse bile talebi karşılamaz.

---

## 4. Adım: Aday tabloların TÜM kolonlarını oku

**Bu adım pazarlıksızdır ve en çok atlanan adımdır.**

İlk aramalar 5–8 aday obje verir. Her birinin bütün kolonları ve açıklamaları okunur:

```python
for o in adaylar:
    x = d[d.ObjectName == o]
    print('==', o, x.DAtabaseName.iloc[0], x.SchemaName.iloc[0], x.DatasetGroup.iloc[0], len(x))
    for c, s in zip(x.ColumnName, x.ColumnDescription):
        print(' -', c, '|', str(s)[:200])
```

Neden zorunlu:

1. **Doğru alan, arama terimini içermeyebilir.** `vCreditCardList` tablosunda "müşterinin kartları" ifadesi geçmez; ama `CardStatusCodeName`, `SupplementaryCardFlag`, `MainCustomerId` kolonlarını görünce tablonun kart künyesi olduğu anlaşılır.
2. **Kapsam farkları ancak burada görülür.** `TotalLimitFullness` ile `CardLimitFullnessToday` arasındaki fark (tüm limitler vs. yalnızca kart) yalnızca açıklamada yazar.
3. **Tuzaklar burada yakalanır** (bkz. Adım 5).
4. **Kısıt notları burada üretilir.** Raporun en değerli kısmı olan "Kısıt / Dikkat" kolonu, bu okumadan çıkar.

Pratik ölçü: 5 aday tablo × ortalama 30 kolon = 150 açıklama okunur. Bu, analizin en uzun adımıdır ve kısaltılırsa kalite düşer.

---

## 5. Adım: Tuzakları ayıkla

Dört tür tuzak vardır. Her aday için hepsi kontrol edilir.

### 5.1 Doğru kelime, yanlış kavram

Aynı kelimeyi taşıyan ama farklı şey ölçen alanlar. En yoğun örnek "skor":

| Alan | Görünen | Gerçek |
|---|---|---|
| `vCustomerBehaviours.*BehaviourScore` (~100 alan) | risk skoru | ürün/kanal eğilim (propensity) skoru |
| `vPersonKKB.CurrentScore` | müşteri KKB skoru | **personelin** KKB skoru |
| `vCarOwnerShipPrediction.CreditScore` | kredi skoru | araç sahipliği tahmin modelinin girdisi |

**Tespit yöntemi:** Adayın açıklamasında "ne ölçtüğü" ve "hangi bağlamda kullanıldığı" cümlelerine bakılır. Tablonun `DatasetGroup` değeri de güçlü ipucudur (Kampanya, Model Girdisi, İK gibi).

### 5.2 Kolon adı ile içerik uyuşmazlığı

Sözlükte 283 kolon bu şekilde işaretli. Gerçek örnekler:

| Kolon | Ad ne diyor | İçerik ne |
|---|---|---|
| `vPRCCustomerCorporateInfo.CompanySectorAge` | sektör yaşı | firma yaşı |
| `vForeignTradeScenarioandLabel.CustomerAge` | müşterinin yaşı | müşterilik kıdemi |
| `vCustomerGeneralInfo.CustomerAgeMonth` | müşterilik yaşı (ay) | kişinin yaşı (ay) |
| `vCreditCardLimit.CardLimitRatio` | limit doluluk oranı | limitin referans değere oranı |
| `vAccountBalanceSummary.AccountNumber` | hesap numarası | müşteri numarası (sözlükte "doğrulanmalı" bayraklı) |
| `vCreditCardList.CustomerId` | kart sahibi müşteri | **ek kart** sahibi; asıl müşteri `MainCustomerId` |

**Tespit yöntemi:** Her önerilen alanın açıklaması, kolon adının çağrıştırdığı anlamla karşılaştırılır. Uyuşmuyorsa mutlaka kısıt notuna yazılır. Sözlükteki `[ORİJİNAL AÇIKLAMA HATALIYDI — DÜZELTİLDİ]` ve `[BU OBJEDE FARKLI ANLAMDA — DOĞRULANMALI]` etiketleri bu tuzakların hazır işaretleridir.

### 5.3 Kapsam farkı

Alan doğru kavramı ölçer ama farklı bir evreni kapsar:

- `TotalLimitFullness` → kart değil, müşterinin tüm limitleri
- `VirmanIntrabankMoneyTransferCount` → kendi hesabına transfer, ama yalnızca banka içi
- `vProductRiskInfo` → risk doğru, ama yalnızca takipteki hesaplar
- `vRetailCustomerChurnTrainingInput` → değerler doğru, ama eğitim dönemine ait (güncel değil)

**Tespit yöntemi:** Açıklamadaki "yalnızca", "kapsar", "dahil", "hariç", "bağlamında" ifadeleri ve tablonun `DatasetGroup` değeri.

### 5.4 Hazır değer yok, türetme gerekiyor

Pay ve payda var ama oran yok; ya da işlem detayı var ama özet yok. Bu bir hata değil, ama rapor bunu **açıkça** söylemeli ve skoru düşürmeli:

- `TotalUsedLimitTL / CardLimit` → doluluk oranı türetilebilir
- `vFASTOutgoing` → gönderen = alıcı filtresiyle "kendi hesabına transfer" türetilebilir
- `vProjectRisk` → müşteri + ürün + ay seviyesine toplanması gerekir

---

## 6. Adım: Skorla

Skor rastgele verilmez, sabit bir rubriğe göre hesaplanır (detay: `docs/SCORING.md`).

**Taban değer** eşleşmenin niteliğine göre:

| Durum | Taban |
|---|---|
| Kolon adı veya açıklama birebir kavramı içeriyor, hazır değer | 0.90–0.95 |
| Kavram net karşılanıyor, küçük bir kapsam/birim belirsizliği var | 0.80–0.88 |
| İlişkili, ama kapsam/granülerlik farkı veya türetme gerekiyor | 0.55–0.78 |
| Dolaylı; yalnızca türetilebilir veya kısmi | 0.35–0.54 |
| Eşik altı | raporlanmaz |

**Düzeltmeler:**

- Talepte zaman kavramı var ve objede periyot kolonu var → +0.10
- Hazır değer yok, türetme gerekiyor → −0.15
- Granülerlik farkı (müşteri istendi, tablo işlem bazlı) → −0.10
- Kapsam farkı → −0.10
- `[MODEL TAHMİNİ — DOĞRULANMALI]` → ×0.85
- İsim/içerik uyumsuzluğu bayrağı → ×0.90

**Obje skoru** tek kolonun skoru değildir:

```
obje_skoru = 0.50 × en_iyi_kolon + 0.30 × kapsama_oranı
           + 0.10 × zaman_boyutu + 0.10 × granülerlik
```

Gerçek örnek: "aylık, ürün kırılımlı risk" talebinde kazanan tablo tek bir kolonu iyi eşleştiği için değil, konut/taşıt/tüketici/leasing kolonlarını **birlikte** taşıdığı ve `Period` kolonu olduğu için kazandı.

**Sonuç sayısı sabit değildir.** Beş satır doldurmak için zayıf aday eklenmez. Hiçbir aday eşiği geçmezse cevap "bulunamadı" olur — bu geçerli ve değerli bir cevaptır.

---

## 7. Adım: Cevabı kur

Rapor metni şu sırayla yazılır.

### 7.1 Sonuç cümlesi

Üç durumdan biri, tek cümlede, gerekçesiyle:

- **VAR** — "Doğrudan mevcut. Ana kaynak X."
- **KISMEN VAR** — "Çekirdek X'te hazır; A ve B alanları Y'den türetilmeli."
- **BULUNAMADI** — "Sözlükte doğrudan karşılığı yok; en yakın Z ama şu farkla."

Bu cümle iş biriminin okuyacağı tek cümle olabilir, o yüzden en başa konur ve kesin bir yargı içerir.

### 7.2 Öneri tablosu

Her satırda: obje, ilgili alanlar, gerekçe, kısıt, güven, kullanım önerisi.

**Gerekçe nasıl yazılır:** Sözlükteki tanıma dayanır, genel laf etmez.

- Kötü: "Bu tablo kart bilgisi içeriyor."
- İyi: "Kart bazında tekil kayıt tutuyor; marka, ürün segmenti, statü ve asıl/ek kart ilişkisi burada. `CardRefNumber` ile diğer kart tablolarına bağlanabiliyor."

**Kısıt nasıl yazılır:** Somut ve eyleme dönük.

- Kötü: "Dikkatli kullanılmalı."
- İyi: "Bu tabloda `CustomerId` ek kart sahibini gösterir; asıl müşteri `MainCustomerId` alanındadır. Yanlış alan seçilirse sonuç hatalı olur."

### 7.3 Top-N dışı adaylar

Eşiğe yakın ama listeye girmeyen tablolar ayrı bir paragrafta belirtilir. İş birimi bazen tam da bunu arıyordur ve neden elendiğini bilmek ister.

### 7.4 Netleştirme soruları

Adım 1'de açık kalan boyutlar buraya döner. Her soru, cevabın nasıl değişeceğini de söyler:

> "'Risk bilgisi' banka içi risk mi, sektör geneli (KKB/Memzuç) mi? Banka içi ise 1 ve 2, sektör geneli ise 3 numaralı öneri öne çıkar."

Bu, raporun en çok geri dönüş alan bölümüdür.

---

## 8. Adım: Excel raporunu üret

### 8.1 Sekme yapısı (dört sekme, sabit)

| Sekme | İçerik | Kimin için |
|---|---|---|
| **Özet** | Talep, sonuç cümlesi, öneri özeti (5 satır), dikkat blokları, güven ölçeği | Yönetici / hızlı bakış |
| **Öneriler** | Top-5 tam detay: gerekçe, kısıt, kullanım önerisi | Analist |
| **Alan Detayları** | Her önerilen alanın sözlükteki **tam** açıklaması + kalite bayrağı | Geliştirici |
| **Notlar ve Öneriler** | Tuzaklar, netleştirmeler, top-5 dışı adaylar, kapsam notları | Hepsi |

Talebe göre Özet sekmesine ek bloklar konur: çok adayın yanlış olduğu taleplerde "Dikkat: ... olmayan alanlar", kesişim gerektiren taleplerde "Önerilen Kurgu" (hangi tablolar hangi anahtarla birleştirilecek).

### 8.2 Alan Detayları sekmesi neden zorunlu

Sözlük açıklamaları **birebir** kopyalanır, özetlenmez. Üç sebep:

1. İş birimi kaynağı görmeden güvenmez.
2. Kalite bayrağı (`MODEL TAHMİNİ`) burada görünür.
3. Rapor, sözlüğün kendisine karşı doğrulanabilir hale gelir.

### 8.3 Kod pratikleri

**Her alan adı sözlüğe karşı doğrulanır.** Uydurma alan önerme riskini yapısal olarak kaldıran tek yöntem:

```python
def desc(o, c):
    r = d[(d.ObjectName == o) & (d.ColumnName == c)]
    assert len(r), (o, c)          # alan yoksa üretim durur
    return r.ColumnDescription.iloc[0]
```

Bu assert sayesinde, yanlış hatırlanan bir anahtar kolon (`CustomerId` yerine `CustomerPartyId`) rapora girmeden yakalanır. Pratikte bu birkaç kez gerçekten devreye girdi.

**Diğer kurallar:**

- Kolon/obje adlarında `.str.strip()` — sözlükte sondan boşluklu değerler var
- `drop_duplicates(['ObjectName','ColumnName'])` — 21 tekrarlı kayıt var
- `DAtabaseName` yazımı (kaynaktaki hata) korunur veya iki yazım da kabul edilir
- Biçim: Arial, başlık `1F3864` zemin beyaz yazı, güven `0%` formatı, seviye renkli (Yüksek `C6EFCE` / Orta `FFEB9C` / Düşük `FFC7CE`), durum renkli, `wrap_text`, kılavuz çizgileri kapalı, başlık dondurulmuş, otomatik filtre açık
- Satır yüksekliği alan sayısına göre hesaplanır: `max(110, 14*len(alanlar)+20)`

---

## 9. Kalite kontrol listesi

Rapor tamamlandıktan sonra, teslim öncesi:

- [ ] Önerilen her `obje.kolon` sözlükte gerçekten var mı? (assert ile otomatik)
- [ ] Talebin her kavramı en az bir öneride karşılanıyor mu?
- [ ] Zaman kavramı istendiyse, önerilerde periyot kolonu var mı?
- [ ] Her öneride kısıt notu var mı, yoksa "-" mi? (boş bırakılmaz)
- [ ] İsim/içerik uyumsuzluğu olan alanlar uyarıya dönüştü mü?
- [ ] `MODEL TAHMİNİ` bayraklı alanlar raporda görünüyor mu?
- [ ] Türetme gerektiren öneriler açıkça "türetilmeli" diyor mu?
- [ ] Netleştirme sorusu, cevabın nasıl değişeceğini söylüyor mu?
- [ ] Sonuç cümlesi tek başına okunduğunda anlamlı mı?
- [ ] KVKK kapsamındaki alanlar için uyarı var mı?

---

## 10. Ajan için prompt iskeleti

Aşağıdaki iskelet, bir ajana bu metodolojiyi uygulatmak için kullanılabilir. Tek seferde değil, **adım adım** çalıştırılmalıdır — özellikle 3 ve 4. adımlar ayrı turlar olmalıdır.

```
Sen bir veri ambarı analistisin. Elinde 11.158 satırlık bir veri sözlüğü var
(kolonlar: DAtabaseName, SchemaName, ObjectName, ColumnName, ColumnDescription,
DatasetGroup). İş biriminden gelen talebi bu sözlükle eşleştireceksin.

ADIM 1 — Talebi ayrıştır:
Ölçüt / Kırılım / Zaman / Granülerlik / Kapsam boyutlarını çıkar.
Belirtilmeyen boyutu VARSAYMA, açık uç olarak not et.

ADIM 2 — Terminoloji köprüsü:
Her kavram için sözlükte geçebilecek karşılıkları listele:
katılım bankacılığı terimi, İngilizce karşılık, kısaltma.
(kredi=fon kullandırım, faiz=kâr payı, mevduat=katılma hesabı+cari hesap,
leasing=icare, doluluk=kullanım oranı/fullness/utilization)

ADIM 3 — Arama (birden fazla tur):
a) Kavramı kolon adı + açıklamada ara, sonucu OBJE bazında say.
b) Obje adlarında ve DatasetGroup değerlerinde ara.
c) Talep iki kavramın kesişimiyse, her kavramı ayrı arayıp
   aynı objede ikisini birden taşıyanları bul.
d) Aday objelerde periyot ve müşteri anahtarı kolonu var mı kontrol et.

ADIM 4 — Aday tabloları TAM oku:
İlk 5-8 aday objenin BÜTÜN kolonlarını ve açıklamalarını oku.
Bu adımı atlama; kısıt notları ve tuzaklar yalnızca burada görünür.

ADIM 5 — Tuzakları ayıkla, her aday için kontrol et:
- Doğru kelime yanlış kavram mı? (skor → eğilim skoru olabilir)
- Kolon adı içerikle uyuşuyor mu? (CompanySectorAge = firma yaşı)
- Kapsam farkı var mı? ("yalnızca", "kapsar", "hariç" ifadeleri)
- Hazır değer mi, türetme mi gerekiyor?

ADIM 6 — Skorla:
Taban: birebir 0.90-0.95 / net 0.80-0.88 / kapsam farkı 0.55-0.78 / dolaylı 0.35-0.54
Düzeltme: zaman karşılanıyor +0.10, türetme -0.15, granülerlik -0.10,
kapsam farkı -0.10, MODEL TAHMİNİ ×0.85
Obje skoru = 0.50×en iyi kolon + 0.30×kapsama + 0.10×zaman + 0.10×granülerlik
Eşik altındaki adayı RAPORLAMA. Liste doldurmak için zayıf aday EKLEME.

ADIM 7 — Raporu yaz:
Sonuç cümlesi (VAR / KISMEN VAR / BULUNAMADI + gerekçe)
Top-5 tablo: obje, alanlar, gerekçe (sözlük tanımına dayalı), kısıt (somut),
güven, kullanım önerisi
Top-5 dışı yakın adaylar
Netleştirme soruları (her soru cevabın nasıl değişeceğini söylesin)

ADIM 8 — Excel üret (4 sekme):
Özet / Öneriler / Alan Detayları (sözlük açıklaması BİREBİR) / Notlar
Her obje.kolon çiftini sözlüğe karşı assert ile doğrula.
```

---

## 11. Sık yapılan hatalar

| Hata | Sonuç | Önlem |
|---|---|---|
| Tek arama turu yapmak | Kesişim gerektiren talepler kaçar | Adım 3'teki dört turu da uygula |
| Aday tabloları tam okumamak | Kısıt notu üretilemez, tuzaklar kaçar | Adım 4 pazarlıksız |
| En iyi kolonu tablo skoru saymak | Yanlış tablo kazanır | Kapsama oranını hesapla |
| Her talebe 5 satır döndürmek | Güven kaybı | Eşik altını raporlama |
| Sözlük açıklamasını özetlemek | Doğrulanabilirlik kaybolur | Alan Detayları'na birebir kopyala |
| Alan adını hafızadan yazmak | Var olmayan alan önerisi | `assert` ile doğrula |
| Belirsizliği varsayımla kapatmak | Yanlış cevap, sessiz hata | Netleştirme sorusu sor |
| Kalite bayraklarını gizlemek | İş birimi doğrulanmamış alanı kullanır | Bayrağı rapora taşı |
| Genel gerekçe yazmak ("ilgili tablo") | Rapor değersizleşir | Sözlük tanımına atıf yap |

---

## 12. Bu metodolojinin uygulamaya çevrilmesi

Yukarıdaki adımların otomatik karşılıkları:

| Metodoloji adımı | Uygulama karşılığı |
|---|---|
| 1 — Kavram ayrıştırma | `extract_concepts()` / LLM ile `concepts` çıkarımı |
| 2 — Terminoloji köprüsü | `config/term_dictionary.csv` + sözlük eş anlamlı ters indeksi |
| 3 — Çok turlu arama | Hibrit arama (BM25 + yoğun vektör), alan ağırlıkları |
| 4 — Tam okuma | Aday objenin tüm kolonlarını LLM'e bağlam olarak verme |
| 5 — Tuzak ayıklama | Kalite bayrakları + LLM hakem katmanı + kısıt üretimi |
| 6 — Skorlama | `scoring/rules.py` + `scoring/aggregate.py` |
| 7 — Rapor metni | LLM (gerekçe/kısıt/kullanım önerisi) veya şablon |
| 8 — Excel | `report/excel.py` + `validate.py` |

Otomasyonda en kritik iki nokta: **Adım 4'ün bağlamını daraltmamak** (aday objenin tüm kolonları modele verilmeli, sadece eşleşen kolon değil) ve **Adım 8'deki doğrulamayı atlamamak**.
