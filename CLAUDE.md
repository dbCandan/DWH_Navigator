# CLAUDE.md — Veri Sözlüğü Asistanı (VSA)

Tam spesifikasyon: `docs/HANDOVER.md`. Tasarım sorularında önce orayı oku; bölüm
numaralarıyla (§8, ADR-005 vb.) atıf yap.

## Ne yapar
İş biriminin doğal dildeki veri talebini, veri sözlüğüne (11.158 kolon, 389 obje) karşı
arar ve **tablo seviyesinde**, gerekçeli, güven skorlu öneriler içeren Excel raporu üretir.
Kapalı ağda çalışır; hiçbir dış adrese çıkmaz.

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
ADR-013 (IDF ağırlıklı kapsama + cevap eşiği), ADR-014 (uzun format kırılım), ADR-015 (obje havuzu).

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
```

## Yol haritası durumu
- [x] M1 — LLM'siz çekirdek (normalize, loader, BM25, genişletme, kural skoru, toplama, ask Excel)
      Kabul: golden set recall@5 = 1.00 (3/3). `vsa eval` M2'den önce de çalışıyor.
- [x] M2 — Değerlendirme: `vsa eval` (ask/batch/negatif grupları, kolon isabeti, tuzaklar),
      `--compare` (§13.4), `--save` → `eval/history.jsonl`. Golden set hâlâ küçük (4 ask).
- [ ] M3 — Hibrit arama (dense + reranker)
- [ ] M4 — LLM katmanı
- [ ] M5 — Batch modu
- [ ] M6 — Arayüz — **tasarım kararları tamamen Claude'da**; kullanıcı "beni şaşırt" dedi.
      Seçenek menüsü sunma, iddialı ve özgün bir tasarım yap. Kapalı ağ: runtime'da
      dış CDN/font yok, her şey gömülü.
- [ ] M7 — Geri bildirim döngüsü
