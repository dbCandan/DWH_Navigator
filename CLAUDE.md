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
- I/O yalnızca `loader.py`, `report/`, `cli.py` içinde; diğer modüller saf fonksiyon.
- Her yeni skorlama kuralı bir testle gelir.
- Kullanıcıya dönük metin (rapor, gerekçe) **Türkçe**; kod, değişken adı, commit **İngilizce**.

## Veri
- Sözlük: `data/DataDictionary-Final.xlsx` (Sheet1 = kolonlar, Sheet2 = kalite bulguları).
- `data/`, `out/` ve tüm `.xlsx` dosyaları gitignore'da — **kurum içi veri, asla commit edilmez**.
  Testler gerçek sözlüğe ihtiyaç duyarsa sözlük yoksa `skip` etmeli.
- Sözlük kolonu `DAtabaseName` yazım hatalı; yükleyici her iki yazımı kabul eder.
- Obje/kolon adlarında baş/son boşluk olabilir → `strip`.

## Golden set
`tests/golden_set.yaml` — maddeler silinmez, yalnızca eklenir. Ağırlık değişikliğinden
önce ve sonra `vsa eval` çalıştırılır; regresyon varsa değişiklik geri alınır.

## Komutlar
```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
vsa index
vsa ask "kredi kartı limit doluluk oranı"
```

## Yol haritası durumu
- [ ] M1 — LLM'siz çekirdek (normalize, loader, BM25, genişletme, kural skoru, toplama, ask Excel)
- [ ] M2 — Değerlendirme (recall@k, MRR)
- [ ] M3 — Hibrit arama (dense + reranker)
- [ ] M4 — LLM katmanı
- [ ] M5 — Batch modu
- [ ] M6 — Arayüz
- [ ] M7 — Geri bildirim döngüsü
