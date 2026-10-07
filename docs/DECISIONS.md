# Kararlar (ADR)

ADR-001…036 önceki `docs/` ile birlikte kaldırıldı; özetleri CLAUDE.md'de. Yeni kararlar buraya eklenir.

## ADR-037 — Tek, konsolide veri sözlüğü (2026-10-05)
`DataDictionary-Final.xlsx` ve `ObjectNameList.xlsx` tek dosyada birleştirildi: `data/VeriSozlugu.xlsx`.
- İki sayfa: **Objeler** (ObjectKey, ad, ObjectDescription, Grain, KeyColumns, TimeColumns,
  BusinessDomain, DatasetGroup) ve **Kolonlar** (DatabaseName, SchemaName, ObjectName, ColumnName,
  ColumnDescription, Synonyms, Role, Summary).
- Kolon kümesi yeni sözlükten (daha güncel); tablo açıklamaları ve kaynak metinler eski listeden.
  Yalnız eski listede kalan 24 kolon alınmadı (var olmayan alan önerilmez).
- Kolonlar sayfasındaki tüm açıklamalar **doğrulanmış kabul edilir**: bayrak, süreç notu, kalite sayfası
  ve değişiklik günlüğü tutulmaz. DatasetGroup Objeler'den `DB.Şema.Obje` ile gelir.
- **Role** (Anahtar, Kod, Ad, Zaman, Ölçü, Bayrak, Metin) ve **Summary** (≤70 karakter
  sıkıştırılmış anlam) LLM'e uzun açıklama yerine verilmek için üretildi; sözlüğün "ad + rol + özet"
  hali tam açıklamanın ~1/5'i token tutar.

## ADR-038 — LLM'siz çalışma şartı kalktı (ADR-008'in yerine) (2026-10-05)
Uygulama bir sohbet modeli olmadan cevap üretmez; model ulaşılamazsa ekranda açık bir hata verilir.
Kural motoru (BM25 + kural skoru) yalnız modele ipucu ve doğrulayıcı olarak kalır.

## ADR-039 — Vektör araması kaldırıldı (2026-10-05)
Embedding modeli, vektör indeksi, tablo profil vektörleri ve ilgili yönetim ekranı kaldırıldı.
Gerekçe: ölçülmüş bir kazancı yoktu (golden setteki M3 ölçümü BM25 ile aynı), işletme maliyeti
vardı (her sorguda embedding çağrısı, sözlük/model değişince yeniden kurulum), ve tablo seçimini
artık model yapıyor. Eş anlamlılar ve Summary kelime aramasını besler.

## ADR-040 — Analist akışı: kompakt malzeme (2026-10-05)
- 1. adım katalogu Objeler sayfasından kurulur: `id | tablo | grup | kolon sayısı | içerik |
  Satır: grain | Zaman: kolonlar`. Kolon adları yalnız açıklaması olmayan tablolarda (ya da
  `analyst.catalog_columns: true` ile). Katalog her soruda aynıdır (önek önbelleği).
- 2. adımda kolonlar `Ad [Rol]: özet` biçiminde gider; talebe en ilgili `analyst.detail_columns`
  kolon tam açıklamasıyla.
- Hedef: aynı isabetle daha az okunan token, daha kısa süre. Ölçüm: `data/golden/` altındaki
  67 soruluk set, Fable ve Opus'un bağımsız cevaplarıyla (doğru cevap kabul edilir).

## ADR-041 — Talebin asıl kavramı cevabı belirler (2026-10-06)
Model talebin asıl bilgisini (`core_concept`) ve bunun aday tablolarda olup olmadığını
(`core_found`) yazar. Asıl bilgi yoksa ya da model BULUNAMADI derse, önerdiği yakın tablolar
cevap olmaz: tek bir "İlgili" notuna dönüşür, sonuç BULUNAMADI olur. Gerekçe: negatif sorularda
"KISMEN VAR" ile teselli tablosu önermek kullanıcıyı yanlış yönlendiriyordu.

## ADR-042 — Asıl kavram bir kolonla gösterilmeli (2026-10-06)
Model asıl bilgiyi taşıyan 1-3 kolonu (`core_columns`, "T12.Kolon") adıyla yazar; kod bunları
aday tablolarda doğrular. Geçerli kolon yoksa cevap ADR-041'deki gibi BULUNAMADI olur. Talep bir
varlığın niteliğini istiyorsa (oran, tutar, bakiye, süre) asıl bilgi o niteliktir; varlığın
türü, bayrağı ya da kaydı yetmez. Bilgi birden çok aday tabloya dağılmış ve birleştirilerek elde
ediliyorsa bu BULUNAMADI değil KISMEN VAR'dır (ilk sürüm birleştirme sorularını "tek tabloda yok"
diye BULUNAMADI'ya çeviriyordu; açıklık eklendi). Gerekçe: 294 soruluk ölçümde negatif hataların hepsi (9) bu
kalıptı — varlık var, istenen nitelik yok. Alanı olmayan eski cevaplarda kontrol uygulanmaz.
Ön kontrol (101 soru: akşam hatalı/negatif + 30 doğru koruma sorusu): koruma 30/30, hedef
negatifler 0/9 → 2/9, birleştirme kaybı yok. Tam 294 ölçümü bekliyor.

## ADR-043 — Sırayı asıl kavram belirler (2026-10-07)
Önerilerin sırasını model güveni değil kod verir: modelin gösterdiği asıl kavram kolonlarını
(ADR-042) en çok taşıyan tablo öne geçer; eşitlikte genel tablo, dar kitleli / türetilmiş
tablonun (açıklamasında model girdisi, eğitim verisi, akıllı hedefleme, özel bankacılık
müşterileri, segmentasyon girdisi geçen) önüne geçer; sonra güven. Öne geçen tablo, geçtiği
tablonun güveninden düşük gösterilmez. Kolon gösterilmemişse modelin sırası kalır.
Gerekçe: 294 soruda cevaplanabilir 23 hatanın 17'sinde doğru tablo ilk 3'teydi ama 1.
sırada değildi. Ölçüm (31 soru, seri sunucu): sıralama hatalarının 7/19'u düzeldi, koruma
sorularının 7/8'i korundu.

## ADR-044 — Asıl kavram için ikinci denetim çağrısı: REDDEDİLDİ (2026-10-07)
Denendi: analist cevabından sonra kısa bir çağrı, gösterilen asıl kavram kolonlarının talebin
asıl bilgisini "birebir" taşıyıp taşımadığını sorar; "hayır" → BULUNAMADI. Ölçüm (seri sunucu,
gece ölçümü tabanına göre): negatifler 40/48 → 43/48, ama doğru cevaplanmış 40 koruma sorusundan
3'ü BULUNAMADI'ya döndü (%7,5). Tam sette ~230 doğru cevaba yayılan kayıp, birkaç negatif
kazancını aşar. Uygulanmadı. Negatif hatalar için yol: modelin "nitelik yok" ayrımını daha güçlü
yapan bir model ya da sözlükte kolon düzeyinde daha net açıklamalar.
