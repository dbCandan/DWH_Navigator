# CLAUDE.md — Veri Sözlüğü Asistanı (VSA)

Tam spesifikasyon: `docs/HANDOVER.md`. Tasarım sorularında önce orayı oku; bölüm
numaralarıyla (§8, ADR-005 vb.) atıf yap.

## Ne yapar
İş biriminin doğal dildeki veri talebini, veri sözlüğüne (11.158 kolon, 389 obje) karşı
arar ve **tablo seviyesinde**, gerekçeli, güven skorlu öneriler içeren Excel raporu üretir.
Kapalı ağda çalışacak şekilde tasarlandı; varsayılan ayarlarda hiçbir dış adrese çıkmaz. İstisna:
kullanıcı kararıyla hakem buluta alınabilir (`llm.provider: cloud`, ADR-026) — bu makinede açık.

## Çekirdek kurallar (pazarlıksız)
- **Obje seviyesine toplama** (`scoring/aggregate.py`, §8, ADR-005): arama kolon
  seviyesinde, cevap tablo seviyesinde. Refaktörlerde korunur.
- **Var olmayan alan önerilmez** (`validate.py`, ADR-002): her (obje, kolon) sözlüğe
  karşı doğrulanır; LLM yalnızca `candidate_id` seçer.
- **"Bulunamadı" geçerli cevap** (ADR-006): eşik altı aday gösterilmez, liste doldurulmaz.
- **LLM'siz çalışabilirlik** (ADR-008): kural tabanlı mod her zaman çalışır.
- **Kapsam filtresi koda gömülmez** (ADR-001): kapsam sözlük dosyasıyla yönetilir.
- Sorgu genişletme yalnızca BM25 koluna uygulanır (ADR-004).

## Kodlama standartları
- Python 3.11+, tip ipuçları zorunlu, `ruff` + `mypy --strict` temiz.
- **Hiçbir modülde doğrudan `.lower()` / `.upper()` / `.casefold()` çağrılmaz** —
  `vsa.text.normalize` kullanılır (Türkçe İ/ı sorunu).
- I/O yalnızca `loader.py`, `index/store.py`, `report/`, `cli.py` içinde (+ `Engine.from_*`
  kurucuları); diğer modüller saf fonksiyon.
- Her yeni skorlama kuralı bir testle gelir.
- Kullanıcıya dönük metin (rapor, gerekçe) **Türkçe**; kod, değişken adı, commit **İngilizce**.

## Veri
- Sözlük: `data/DataDictionary-Final.xlsx` (Sheet1 = kolonlar, Sheet2 = kalite bulguları).
- `data/`, `out/` ve tüm `.xlsx` dosyaları gitignore'da — **kurum içi veri, asla commit edilmez**.
  Testler gerçek sözlüğe ihtiyaç duyarsa sözlük yoksa `skip` etmeli.
- Sözlük kolonu `DAtabaseName` yazım hatalı; yükleyici her iki yazımı kabul eder.
- Obje/kolon adlarında baş/son boşluk olabilir → `strip`.

## Yeni kararlar
`docs/DECISIONS.md`: ADR-009 (müşteri no = hesap no), ADR-010 (zaman/granülerlik yalnız obje
skorunda), ADR-011 (uygulanamayan bileşen ağırlıktan çıkar), ADR-012 (kolon skoru tabanı),
ADR-013 (IDF ağırlıklı kapsama + cevap eşiği), ADR-014 (uzun format kırılım), ADR-015 (obje havuzu),
ADR-016/017 (batch: çekirdek tablo, yapısal alanlar, ölçü uyumu, kanal toplamları, terim kapsam notları),
ADR-018..022 (yerel model, hibrit, hakem, ağırlıklar), ADR-023 (Keşfet araması), ADR-024 (Evren arayüzü),
ADR-025 (Model laboratuvarı, `vsa lab`), ADR-026 (bulut modelleri yalnız ölçüm için, NVIDIA),
ADR-027 (tek ekran, tek görünüm: yalnız soru sorma, Evren), ADR-028 (tablo seviyesinde
konu uyumu: tablo BM25 + tablo profil vektörleri; `vsa index --dense` kurar).

## Golden set
`tests/golden_set.yaml` — maddeler silinmez, yalnızca eklenir. Ağırlık değişikliğinden
önce ve sonra `vsa eval` çalıştırılır; regresyon varsa değişiklik geri alınır.

## Sözlükte dokümanda olmayan ayrıntılar
- Baştaki `[...]` bayrakları: `MODEL TAHMİNİ` (240, ×0.85), `ORİJİNAL AÇIKLAMA HATALIYDI`
  (88, not), ve `BU OBJEDE FARKLI ANLAMDA — DOĞRULANMALI` gibi diğerleri (~50,
  `NEEDS_VERIFICATION`, not). Metin ortasındaki `[...]` formül olabilir, bayrak değildir.
- `vCampaign` iki şemada (CFM, CMP) var → obje anahtarı her zaman `DB.Şema.Obje`.
- Sheet2'de db/şema yok; bulgular (Obje, Kolon) ile eşlenir. 22 tekrar kolon var.

## Komutlar
Sanal ortam `.venv/` (Windows: `.venv\Scripts\python`).
```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
vsa index
vsa ask "kredi kartı limit doluluk oranı"
vsa batch -i data/QuestionList-1.xlsx
vsa eval --save --label "ne değişti"   # ağırlık değişikliğinden önce/sonra
```
Stopword veya terim sözlüğü değişirse `vsa index` yeniden çalıştırılmalı (BM25 indekse gömülü).

## Yol haritası durumu
- [x] M1 — LLM'siz çekirdek (normalize, loader, BM25, genişletme, kural skoru, toplama, ask Excel)
      Kabul: golden set recall@5 = 1.00 (3/3). `vsa eval` M2'den önce de çalışıyor.
- [x] M2 — Değerlendirme: `vsa eval` (ask/batch/negatif grupları, kolon isabeti, tuzaklar),
      `--compare` (§13.4), `--save` → `eval/history.jsonl`. Golden set hâlâ küçük (4 ask).
- [x] M3 — Hibrit arama: BGE-M3 (LM Studio) + BM25, `vsa index --dense` (~45 dk CPU, devam
      edebilir). Reranker yok (LM Studio cross-encoder sunmuyor). ADR-019.
- [x] M4 — LLM hakem: başta qwen/qwen3.5-9b (yerel); şimdi gemma-4-31b bulutta (ADR-025/026), `reasoning_effort: none`,
      final = 0.75 kural + 0.25 LLM (ADR-021/022). Opsiyonel LLM sorgu genişletme (kapalı).
      Batch modunda hakem yok (süre).
- [x] M5 — Batch modu: `vsa batch -i talep.xlsx` (TR/EN/açıklama). Çekirdek tablo, yapısal
      alanlar, türetme ipuçları (ADR-016/017). Ek A.3: recall@3 0.90, durum doğruluğu 0.90.
      QuestionList-2 (günlük) ve A.3 dışı alanlar için doğrulanmış cevap yok.
- [x] M6 — Arayüz: `vsa serve` / `baslat.bat` → http://127.0.0.1:8765. Tek ekran (soru sorma),
      tek görünüm: Evren (galaksi, ADR-024/027). Toplu talep yalnız `vsa batch`. Stdlib sunucu +
      `src/vsa/web/static/index.html` (tek dosya, dış kaynak yok). **Tasarım kararları
      Claude'da** (kullanıcı "beni şaşırt" dedi); seçenek menüsü sunma.
- [~] M7 — Geri bildirim: 👍/👎 → `data/feedback.jsonl` → `vsa feedback` golden adayları.
      Eş anlamlı zenginleştirme akışı henüz yok.

## Bu makinenin model ortamı
LM Studio (http://127.0.0.1:1234; `localhost` Windows'ta IPv6 yüzünden ~2 sn yavaş, ADR-023), runtime `llama.cpp-win-x86_64-vulkan-avx2@2.46.0`.
Modeller: `text-embedding-bge-m3` (vektör, yerel). Hakem: `google/gemma-4-31b-it` NVIDIA API
kataloğu üzerinden (`llm.provider: cloud`, seed 42; ADR-026) — her soru dışarı gider; yerel yedek
`google/gemma-4-12b` (laboratuvarın en iyi yerel sonucu). Model seçimi: `vsa lab` / Ayarlar → Model laboratuvarı. Yerel ayar
`config/settings.yaml` (repoda yok). Model karşılaştırma: `eval/bench_llm.py`.
