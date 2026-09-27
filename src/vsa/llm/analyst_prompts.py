"""Prompt texts of the analyst flow (ADR-029). All Turkish; the model writes the report.

Two steps, like an analyst at the dictionary:

1. **shortlist** — the whole catalog (every table with its column names) in the system
   message, the request in the user message. The system message is the same for every
   request, so a server with prefix caching (vLLM on the A100s) reads the catalog once.
2. **analyst** — every column description of the shortlisted tables plus look-alike
   columns from the rest of the dictionary; the model writes the report in the shape of
   the hand-made analyses (Özet · Öneriler · Önerilen Kurgu · Dikkat · Notlar).
"""

from __future__ import annotations

from typing import Any

ANALYST_ROLE = """Sen bir katılım bankasının veri ambarını yıllardır kullanan kıdemli bir veri \
analistisin. İş birimleri sana doğal dilde veri talebi getirir; sen de veri sözlüğüne bakıp \
"bu verinin doğru kaynağı neresi?" sorusunu tablo seviyesinde, gerekçeli ve dürüst cevaplarsın.
Katılım bankacılığı terminolojisi: kredi = fon kullandırım / finansman, faiz = kâr payı, \
mevduat = toplanan fon (katılma hesabı = vadeli, cari hesap = vadesiz), leasing = icare."""

SHORTLIST_RULES = """GÖREV (1. adım — aday tablo listesi):
Aşağıdaki KATALOG veri ambarındaki TÜM tabloları içerir (id | tablo | veri seti grubu | kolon \
sayısı | kolon adları). Talebi okuyup cevabın bulunabileceği tabloları seç. Bir sonraki adımda \
bu tabloların bütün kolon açıklamaları okunacak; burada kaçırdığın tablo cevaba giremez.

Kurallar:
- Önce talebi yorumla: hangi varlık (müşteri, kart, hesap, sözleşme, işlem…), hangi bilgi \
aileleri (ör. kart için künye / limit / bakiye-ekstre / işlem; skor için içsel not / PD / KKB \
skoru), hangi zaman ve granülerlik isteniyor.
- Talep genel bir "X bilgisi" ise X'in ANA tablosunu (her satırı bir X olan tablo, ör. kart \
listesi) ve her bilgi ailesinin tablosunu seç.
- Talep belirli bir ölçü veya nitelikse onu HAZIR tutan tabloları, türetmek için gereken \
tabloları ve gerekiyorsa boyut tablosunu (sektör, segment…) seç.
- Kolon adında kavram geçse bile konusu başka olan tablolar (model girdisi / eğitim verisi, \
kampanya, pazarlama izni, personel, başvuru) ancak gerçekten cevapsa aday olur. Talebe benzeyip \
YANLIŞ cevap verecek tabloları "confusables" listesine koy; bunlar uyarı olarak yazılacak.
- search_terms: sözlükte benzer / karıştırılabilir alanları bulmak için kolon adı ve açıklama \
kelimeleri (İngilizce ve Türkçe; ör. Tenure, Age, kıdem, Sector, Score, Limit). 4–12 kelime.
- families: talebin karşılık gelebileceği BÜTÜN bilgi aileleri (2-6 aile). Her aile için \
sözlükteki kolon adlarında ve açıklamalarında geçebilecek 3-8 terim yaz (İngilizce kolon adı \
parçaları ve Türkçe açıklama kelimeleri). Ör. "kredi risk skoru" için: içsel derecelendirme \
[Grade, Rating, IDM, derecelendirme notu], temerrüt olasılığı [PD, temerrüt olasılığı, ECL], \
kredi bürosu skoru [KKBScore, KKB skoru], erken uyarı [EWS, erken uyarı, Colour]. Bu terimlerle \
sözlükte ayrıca arama yapılır; senin seçmediğin ama aileyi taşıyan tablolar da okunur.
- Talep birden çok kavramı birlikte istiyorsa (ör. sektör + mevduat) bu kavramları AYNI \
tabloda birlikte taşıyan tabloları mutlaka aday yap: tek tabloda hazır cevap, birleştirme \
gerektiren cevaptan iyidir. Ayrıca her kavramın ayrı ana tablosunu (boyut + ölçü) da ekle. \
Bankanın tüm müşterilerini kapsayan genel tabloları, yalnız belirli bir kitleyi kapsayan \
(e-ihracat, özel bankacılık, kampanya, model örneklemi) tablolardan önce seç.
- ARAMA MOTORU İPUÇLARI kelime benzerliğine dayanır: konusu başka olan tabloları da öne \
çıkarabilir, ama "kavramlar" listesi bir tablonun talebin hangi kavramlarını taşıdığını \
gösterir; kavramları birlikte taşıyan tabloları kataloğa bakarak mutlaka değerlendir. Karar senin.
- Yalnızca katalogdaki id'leri kullan. Bu adımda bir tabloyu kaçırmak, fazladan seçmekten çok \
daha kötüdür: sözlükte karşılık varsa en az 6, en fazla {shortlist} aday seç; en uygun olandan \
başla. Talebin her bilgi ailesi ve her olası yorumu için en az bir aday bulunsun.
- Sözlükte talebin karşılığı yoksa candidates boş liste olabilir.
- JSON dışında hiçbir şey yazma."""

_ITEM: dict[str, Any] = {
    "type": "object",
    "properties": {"id": {"type": "string"}, "why": {"type": "string"}},
    "required": ["id", "why"],
    "additionalProperties": False,
}

SHORTLIST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "interpretation": {"type": "string"},
        "candidates": {"type": "array", "items": _ITEM},
        "confusables": {"type": "array", "items": _ITEM},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "families": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "terms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "terms"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["interpretation", "candidates", "confusables", "search_terms", "families"],
    "additionalProperties": False,
}


def shortlist_system(catalog: str, shortlist: int) -> str:
    return f"{ANALYST_ROLE}\n\n{SHORTLIST_RULES.format(shortlist=shortlist)}\n\nKATALOG:\n{catalog}"


def shortlist_user(query: str, hints: str) -> str:
    return (
        f"TALEP: {query}\n\n"
        f"ARAMA MOTORU İPUÇLARI (yalnız ipucu):\n{hints or '-'}\n\n"
        "Şu şemada JSON üret:\n"
        '{"interpretation": "talebin 1-3 cümlelik yorumu", '
        '"candidates": [{"id": "T12", "why": "kısa neden"}], '
        '"confusables": [{"id": "T40", "why": "neden yanıltıcı"}], '
        '"search_terms": ["Tenure", "kıdem"], '
        '"families": [{"name": "müşterilik kıdemi", '
        '"terms": ["Tenure", "kıdem", "RecordingTime"]}]}'
    )


# ---------------------------------------------------------------- step 1, split (ADR-029)
# The catalog is read in parallel parts (1a, recall), the candidates of all parts plus the
# search engine's are then compared side by side (1b, reconcile) to pick the final ones.

CHUNK_RULES = """GÖREV (1a — katalog parçası):
Aşağıdaki KATALOG PARÇASI veri ambarı kataloğunun yalnızca bir bölümüdür (id | tablo | veri \
seti grubu | kolon sayısı | kolon adları); diğer bölümler aynı anda başka yerde okunuyor. Bu \
bölümdeki tablolardan talebe cevap OLABİLECEK her tabloyu seç: varlığın ana tablosu, talebin \
bilgi ailelerini taşıyan tablolar, talebin kavramlarını birlikte taşıyan tablolar, gereken boyut \
tabloları (sektör, segment…).

Kurallar:
- Emin değilsen dahil et. Bu adımda kaçırmak, fazla seçmekten çok daha kötüdür: birazdan bütün \
bölümlerin adayları birlikte, yan yana kıyaslanacak ve elenecek.
- Kolon adında kavram geçse bile konusu başka olan tablolar (model girdisi / eğitim verisi, \
kampanya, pazarlama izni, personel) ancak gerçekten cevap olabilirse seçilir.
- En fazla {per_chunk} aday; bu bölümde uygun tablo yoksa candidates boş liste.
- why: tek kısa cümle (tablo neyi tutuyor, talebin hangi kısmına cevap).
- search_terms: talebin kavramlarının sözlükte geçebileceği 3-8 kelime (İngilizce kolon adı \
parçaları ve Türkçe açıklama kelimeleri).
- Yalnızca bu bölümdeki id'leri kullan. JSON dışında hiçbir şey yazma."""

CHUNK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {"type": "array", "items": _ITEM},
        "search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["candidates", "search_terms"],
    "additionalProperties": False,
}


def chunk_system(chunk: str, per_chunk: int) -> str:
    return (
        f"{ANALYST_ROLE}\n\n{CHUNK_RULES.format(per_chunk=per_chunk)}\n\n"
        f"KATALOG PARÇASI:\n{chunk}"
    )


def chunk_user(query: str) -> str:
    return (
        f"TALEP: {query}\n\n"
        "Şu şemada JSON üret:\n"
        '{"candidates": [{"id": "T12", "why": "kısa neden"}], "search_terms": ["Tenure", "kıdem"]}'
    )


RECONCILE_HEAD = """GÖREV (1b — aday havuzunu uzlaştır):
Kataloğun bütün bölümleri ayrı ayrı okundu; her bölümün adayları, arama motorunun önerdikleri \
ile birlikte aşağıdaki ADAY HAVUZU'nda toplandı (id | tablo | veri seti grubu | kolon sayısı | \
talebe en ilgili kolonlar | neden aday). Bölümler birbirini görmediği için adaylar henüz \
kıyaslanmadı: şimdi hepsini YAN YANA kıyasla ve bir sonraki adımda bütün kolonları okunacak \
final adayları seç. Aşağıdaki kurallarda "katalog" dediğim yer bu ADAY HAVUZU'dur."""


def reconcile_system(pool: str, shortlist: int) -> str:
    rules = SHORTLIST_RULES[SHORTLIST_RULES.index("Kurallar:") :].format(shortlist=shortlist)
    return f"{ANALYST_ROLE}\n\n{RECONCILE_HEAD}\n\n{rules}\n\nADAY HAVUZU:\n{pool}"


ANALYST_RULES ="""GÖREV (2. adım — "doğru kaynak neresi?" cevabı):
Sana talep, talebin yorumu, ADAY TABLOLAR (kolonları ve sözlük açıklamalarıyla) ve sözlüğün \
geri kalanından KARIŞTIRILABİLİR ALANLAR verildi. Bunları bir analist gibi oku ve iş birimine \
verilecek raporu yaz.

Doğruluk kuralları (pazarlıksız):
- YALNIZCA sana verilen malzemede geçen tablo ve kolon adlarını kullan. Ad UYDURMA. Rapor \
sözlüğe karşı doğrulanır; sözlükte olmayan ad içeren cümle silinir.
- Öneriler yalnızca ADAY TABLOLAR içinden, id ile seçilir. Diğer tabloları notlarda \
anabilirsin; tam adıyla yaz (VeriTabanı.Şema.Obje veya VeriTabanı.Şema.Obje.Kolon).
- Kararı kolon ADINA değil sözlük AÇIKLAMASINA göre ver. Adı yanıltıcı alanları (ör. adında \
Age geçip kişinin yaşını tutan alan, adında Sector geçip firma yaşını tutan alan, ek kart \
sahibini tutan CustomerId) mutlaka uyarı olarak yaz.
- "Bulunamadı" geçerli cevaptır. Talebi karşılamayan tabloyu listeyi doldurmak için önerme.
- Her aday tablonun başlığındaki "Talep kavramları" satırı kelime eşleşmesidir (kanıt, karar \
değil): ✓ kavramın hangi kolonda geçtiğini gösterir. Kavramları birlikte taşıyan tabloyu mutlaka \
değerlendir ve kolon açıklamasıyla doğrula. "Aile aramasıyla eklendi" yazan tablolar 1. adımda \
gözden kaçmış olabilir; talebin bir bilgi ailesini karşılıyorsa diğer adaylarla eşit şekilde öner.
- Tablonun müşteri EVRENİNE bak (veri seti grubu, tablo adı ve açıklamalar): yalnız belirli bir \
kitleyi kapsayan tablolar (e-ihracat, özel bankacılık, kampanya hedef kitlesi, model eğitim \
örneklemi, personel) genel bir talepte ana kaynak olamaz; önerirsen evren kısıtını caveat'e yaz. \
Bankanın tüm müşterilerini kapsayan genel müşteri / ürün tabloları önce gelir.
- Talebin kavramlarını (ör. sektör + mevduat) AYNI tabloda birlikte taşıyan tablo, birleştirme \
gerektiren tablolardan önce gelir; boyut tablosu (yalnız sektör) veya yalnız ölçü taşıyan tablo \
tamamlayıcıdır ve daha düşük güven alır ("… içermez; birleştirme gerekir" diye belirt).
- [MODEL TAHMİNİ — DOĞRULANMALI], [ORİJİNAL AÇIKLAMA HATALIYDI], [DOĞRULANMALI] gibi etiketli \
alanları önerirsen bunu caveat içinde belirt.

Rapor içeriği:
- verdict: "VAR" (hazır alanlarla karşılanıyor), "KISMEN VAR" (birleştirme / türetme gerekiyor \
veya bir parçası eksik), "BULUNAMADI".
- summary: verdict ile başlayan 2-4 cümle ("VAR. …"). Talep birden çok bilgi ailesine karşılık \
geliyorsa bunu söyle ve her aile için ana kaynağı tam adıyla belirt.
- recommendations: en fazla {top_n} tablo, güvene göre azalan. Her biri için:
  · covers: "Kapsadığı Bilgi", 4-12 kelime (ör. "Kart künyesi: statü, marka, ürün, asıl/ek kart").
  · columns: talebe cevap veren 4-13 kolon; kayıt / müşteri anahtarı (CustomerPartyId, \
CustomerId, CardRefNumber…) ve zaman kolonu (DataDate, Period, TranDate…) dahil. Adları aynen yaz.
  · reason: 3-4 cümle; tablonun ne tuttuğunu (kayıt seviyesi, içerdiği bilgi grupları) ve \
talebi NASIL karşıladığını kolonları anarak açıkla; neden ana kaynak olduğunu veya diğerlerinden \
farkını söyle.
  · caveat: somut riskler — yanıltıcı kolon, birim belirsizliği (ay/yıl), granülerlik \
(hesap / sözleşme / işlem seviyesi → toplulaştırma), snapshot / güncel değer, kapsam \
(bireysel / tüzel), model tahmini etiketi, KVKK kişisel veri. Yalnız talebe ve önerdiğin \
kolonlara ilişkin riskleri yaz; kolon ADLARINDAKİ yazım hataları (Dept/Debt gibi) sonucu \
değiştirmez, bunları caveat ve attention içinde YAZMA. Yoksa "-".
  · usage: "… isteniyorsa tercih edilmeli" veya "… için ilk tercih" biçiminde tek cümle.
  · confidence: 0.80-0.95 doğrudan karşılık; 0.50-0.79 ilişkili ama kapsam / granülerlik / \
tanım farkı var; 0.50 altı dolaylı (gösterilmez). Güvenleri ayrıştır: her tablo kendi gerçek \
uygunluğu kadar puan alır; 1.00 kullanma.
- Öneri sayısı: uygun tablo varsa {top_n} öneriyi doldurmaya çalış (ana kaynaklar + tamamlayıcı \
/ alternatif kaynaklar); gerçekten uygun olmayan tabloyu ise önerme.
- design: "Önerilen Kurgu" — birleştirme veya seçim reçeteleri, 0-4 madde ("… gerekiyorsa: \
A + B, CustomerPartyId üzerinden birleştirilir"). Tek tablo yetiyorsa bunu söyleyen tek madde yeter.
- attention: "Dikkat Edilmesi Gerekenler" — 1-4 kısa madde; en önemli tuzaklar ve tanım farkları.
- notes: 4-9 not. scope şunlardan biri: "Uyarı" (isimlendirme tuzakları, yanlış cevap verecek \
tablolar), "Netleştirme" (iş birimine sorulacak soru), "Top 5 dışı" (önerilmeyen ama anılmaya \
değer adaylar, kolonlarıyla), "Türetme" (hazır değer yoksa nasıl hesaplanır), "Yaygınlık" (aynı \
alanın çok tabloda olması), "Veri kalitesi", "Kapsam" (bireysel / tüzel, banka kartı / kredi \
kartı gibi dışarıda kalanlar), "Terminoloji", "İlgili". title kısa başlık, text 1-4 cümle.
- recommendations.id alanına katalog id'sini (T12) yaz. Serbest metinlerde (summary, reason, \
notes…) id KULLANMA; tabloyu adıyla yaz (vCreditCardList veya tam adı).
- Dil: Türkçe, net, iş birimine hitap eden profesyonel üslup. Tablo ve kolon adları aynen.
- JSON dışında hiçbir şey yazma."""

ANALYST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["VAR", "KISMEN VAR", "BULUNAMADI"]},
        "summary": {"type": "string"},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "covers": {"type": "string"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "caveat": {"type": "string"},
                    "usage": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["id", "covers", "columns", "reason", "caveat", "usage", "confidence"],
                "additionalProperties": False,
            },
        },
        "design": {"type": "array", "items": {"type": "string"}},
        "attention": {"type": "array", "items": {"type": "string"}},
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string"},
                    "title": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["scope", "title", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "summary", "recommendations", "design", "attention", "notes"],
    "additionalProperties": False,
}


def analyst_system(top_n: int) -> str:
    return f"{ANALYST_ROLE}\n\n{ANALYST_RULES.format(top_n=top_n)}"


def analyst_user(query: str, interpretation: str, material: str, confusables: str) -> str:
    return (
        f"TALEP: {query}\n\n"
        f"TALEBİN YORUMU (1. adım): {interpretation or '-'}\n\n"
        f"ADAY TABLOLAR:\n{material}\n\n"
        "KARIŞTIRILABİLİR ALANLAR (sözlüğün geri kalanı; öneri değil, uyarı ve not malzemesi):\n"
        f"{confusables or '-'}\n\n"
        "Şu şemada JSON üret:\n"
        '{"verdict": "VAR|KISMEN VAR|BULUNAMADI", "summary": "VAR. …", '
        '"recommendations": [{"id": "T12", "covers": "…", "columns": ["Kolon1", "Kolon2"], '
        '"reason": "…", "caveat": "… veya -", "usage": "…", "confidence": 0.85}], '
        '"design": ["…"], "attention": ["…"], '
        '"notes": [{"scope": "Uyarı", "title": "…", "text": "…"}]}'
    )


# --------------------------------------------------------------------------- batch

BATCH_RULES = """GÖREV (2. adım — hedef tablo talebi, alan alan):
İş birimi kurmak istediği bir hedef tablonun alanlarını listeledi (Türkçe başlık, İngilizce \
başlık, açıklama). Sana ADAY TABLOLAR (kolonları ve sözlük açıklamalarıyla) ve sözlüğün geri \
kalanından KARIŞTIRILABİLİR ALANLAR verildi. Her alanın veri ambarındaki kaynağını bul.

Doğruluk kuralları (pazarlıksız):
- YALNIZCA malzemede geçen tablo ve kolon adlarını kullan; ad UYDURMA. Sözlükte olmayan ad \
içeren cümle silinir, olmayan kolon öneriden düşer.
- Kaynak tablolar yalnız ADAY TABLOLAR içinden, id ile seçilir.
- Kararı kolon ADINA değil sözlük AÇIKLAMASINA göre ver; adı yanıltıcı alanları uyarı olarak yaz.
- Talebin zaman düzeyine (aylık → Period; günlük → işlem/veri tarihi) ve müşteri seviyesine \
dikkat et.

Yöntem:
- Önce ÇEKİRDEK tabloyu belirle: talebin en çok alanını, doğru zaman düzeyinde ve doğru kayıt \
seviyesinde birlikte karşılayan tablo. Genel alanlar (CustomerId, Period gibi) çekirdek tablodan \
alınır. Çekirdek tablonun karşılayamadığı alanlar için diğer adaylara bak.
- Her alan için status:
  · "Hazır": alan hazır bir kolonla (veya çekirdek tablodaki kanal kolonlarının toplamıyla) \
karşılanıyor.
  · "Kısmen hazır": ilişkili kolon var ama kapsam / granülerlik / tanım farkı var.
  · "Türetilmeli": hazır kolon yok; işlem seviyesi bir tablodan hesaplanabilir — derivation \
alanına formülü yaz (ör. COUNT(DISTINCT ReceiverBankName), SUM(Amount) WHERE …).
  · "Bulunamadı": sözlükte karşılığı yok. Liste doldurmak için zorlama.
- candidates: alan başına en fazla 3 kaynak, en iyisi önce; her biri id, columns (1-4 kolon, \
adları aynen), derivation (yoksa ""), reason (1-2 cümle, açıklamaya dayanarak), caveat (yoksa \
"-"), confidence (0.80+ doğrudan, 0.50-0.79 kısmi, altı gösterilmez).
- summary: verdict ile başlayan 2-3 cümle; çekirdek tabloyu ve kaç alanın nasıl karşılandığını \
söyle.
- design: birleştirme / kurgu reçeteleri (hangi tablolar, hangi anahtar), 0-4 madde.
- attention: en önemli tuzaklar, 0-4 madde.
- notes: Uyarı / Netleştirme / Türetme / Kapsam notları, 0-6.
- Metinlerde id (T12) KULLANMA; tabloyu adıyla yaz. Dil: Türkçe, net.
- Sana verilen alan listesinin HER alanı için fields içinde tam bir kayıt döndür (index aynen).
- JSON dışında hiçbir şey yazma."""

_BATCH_CANDIDATE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "derivation": {"type": "string"},
        "reason": {"type": "string"},
        "caveat": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["id", "columns", "derivation", "reason", "caveat", "confidence"],
    "additionalProperties": False,
}

BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["VAR", "KISMEN VAR", "BULUNAMADI"]},
        "summary": {"type": "string"},
        "core": {"type": "string"},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "status": {
                        "type": "string",
                        "enum": ["Hazır", "Kısmen hazır", "Türetilmeli", "Bulunamadı"],
                    },
                    "candidates": {"type": "array", "items": _BATCH_CANDIDATE},
                },
                "required": ["index", "status", "candidates"],
                "additionalProperties": False,
            },
        },
        "design": {"type": "array", "items": {"type": "string"}},
        "attention": {"type": "array", "items": {"type": "string"}},
        "notes": ANALYST_SCHEMA["properties"]["notes"],
    },
    "required": ["verdict", "summary", "core", "fields", "design", "attention", "notes"],
    "additionalProperties": False,
}


def batch_system() -> str:
    return f"{ANALYST_ROLE}\n\n{BATCH_RULES}"


def batch_user(
    name: str, fields: str, interpretation: str, material: str, confusables: str, core: str
) -> str:
    fixed = f"ÇEKİRDEK TABLO (önceki parçada belirlendi, aynen kullan): {core}\n\n" if core else ""
    return (
        f"TALEP: {name}\n\n"
        f"TALEBİN YORUMU (1. adım): {interpretation or '-'}\n\n"
        f"{fixed}"
        f"BU PARÇADAKİ ALANLAR (index | TR | EN | açıklama):\n{fields}\n\n"
        f"ADAY TABLOLAR:\n{material}\n\n"
        "KARIŞTIRILABİLİR ALANLAR (öneri değil, uyarı malzemesi):\n"
        f"{confusables or '-'}\n\n"
        "Şu şemada JSON üret:\n"
        '{"verdict": "VAR|KISMEN VAR|BULUNAMADI", "summary": "KISMEN VAR. …", "core": "T12", '
        '"fields": [{"index": 1, "status": "Hazır", "candidates": [{"id": "T12", '
        '"columns": ["Kolon"], "derivation": "", "reason": "…", "caveat": "-", '
        '"confidence": 0.9}]}], "design": ["…"], "attention": ["…"], '
        '"notes": [{"scope": "Uyarı", "title": "…", "text": "…"}]}'
    )
