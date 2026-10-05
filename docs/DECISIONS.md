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
