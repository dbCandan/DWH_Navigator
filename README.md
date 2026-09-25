# DWH Navigator — Veri Sözlüğü Asistanı (VSA)

İş birimlerinin doğal dildeki veri taleplerini ("kart limit doluluk oranı nerede?") veya hedef
tablo tasarımlarını (TR başlık / EN başlık / açıklama) veri ambarı sözlüğüne karşı eşleştirir;
**tablo seviyesinde**, gerekçeli, kısıtlı ve güven skorlu öneriler ile iş birimine
gönderilebilir Excel raporları üretir. Kapalı ağda, yerel modellerle çalışır.

- Spesifikasyon: [docs/HANDOVER.md](docs/HANDOVER.md)
- Geliştirme kararları: [docs/DECISIONS.md](docs/DECISIONS.md)

## Hızlı başlangıç (Windows, LM Studio kurulu)

`baslat.bat` dosyasına çift tıklayın: LM Studio sunucusunu açar, modelleri yükler ve
arayüzü tarayıcıda açar (http://127.0.0.1:8765).

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy config\settings.example.yaml config\settings.yaml
```

Veri sözlüğünü `data/` altına koyun (bu klasör repoya girmez). Yerel model sunucusu için
`config/settings.yaml`:

```yaml
llm:
  enabled: true
  endpoint: http://localhost:1234/v1     # LM Studio / vLLM / llama.cpp / Ollama
  model: qwen/qwen3.5-9b                  # LLM hakem
  embedding_model: text-embedding-bge-m3  # anlamsal arama
dense:
  enabled: true
```

LLM ayarlanmazsa uygulama kural tabanlı modda çalışmaya devam eder (ADR-008).

## Kullanım

```bash
vsa index                   # sözlükten BM25 indeksi
vsa index --dense           # + vektör indeksi (BGE-M3; CPU'da ~45 dk, kaldığı yerden devam eder)
vsa serve --open            # web arayüzü
vsa ask "kredi kartı limit doluluk oranı"   # terminalden tek soru + Excel
vsa batch -i data/talep.xlsx                # hedef tablo talebi + Excel
vsa eval --save --label "..."               # golden set metrikleri, geçmişe kayıt
vsa eval --compare                          # genişletme konfigürasyonları (§13.4)
vsa feedback                                # arayüz geri bildirimleri → golden set adayları
```

## Mimari (özet)

```
talep → Türkçe normalizasyon → kavramlar + genişletme (terim sözlüğü, sözlük eş anlamlıları)
      → BM25 (alan ağırlıklı) + BGE-M3 vektör araması (hibrit)
      → kolon kural skoru → obje seviyesine toplama (kapsama, zaman, granülerlik)
      → LLM hakem (yalnız aday kimliği seçer) → sözlük doğrulaması → rapor / arayüz
```

Batch modu: alan başına arama → çekirdek tablo (alan skorları × zaman uyumu) → yapısal
alanlar çekirdekten → durum etiketi (Hazır / Kısmen hazır / Türetilmeli / Bulunamadı) ve
türetme ipucu (`COUNT(DISTINCT …)`, kanal kolonları toplamı).

## Durum

| Kilometre taşı | Durum |
|---|---|
| M1 LLM'siz çekirdek | ✓ |
| M2 Değerlendirme | ✓ `vsa eval`, geçmiş `eval/history.jsonl` |
| M3 Hibrit arama | ✓ BGE-M3 + BM25 |
| M4 LLM katmanı | ✓ hakem (soru modu) |
| M5 Batch modu | ✓ |
| M6 Arayüz | ✓ yerel web arayüzü |
| M7 Geri bildirim | başlangıç: 👍/👎 → golden set adayları |

## Geliştirme

```bash
pytest            # LM Studio gerekmez; gerçek sözlük yoksa ilgili testler atlanır
ruff check src tests
mypy src
```
