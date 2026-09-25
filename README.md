# Veri Sözlüğü Asistanı (VSA) — DWH Navigator

İş birimlerinin doğal dildeki veri taleplerini veri ambarı sözlüğüne karşı eşleştirip
gerekçeli, güven skorlu tablo/alan önerileri içeren Excel raporu üreten komut satırı aracı.

Proje spesifikasyonu: [docs/HANDOVER.md](docs/HANDOVER.md)

## Kurulum

```bash
pip install -e ".[dev]"
copy config\settings.example.yaml config\settings.yaml
```

Veri sözlüğünü `data/` altına koyun (bu klasör repoya girmez).

## Kullanım

```bash
vsa index                                   # sözlükten indeks kurar
vsa ask "kredi kartı limit doluluk oranı"   # tekil soru, Excel üretir
vsa batch -i data/talep.xlsx                # hedef tablo talebi (TR/EN/açıklama), Excel üretir
vsa eval                                    # golden set metrikleri (--compare, --save)
```

## Durum

M1 (LLM'siz çekirdek), M2 (değerlendirme) ve M5 (batch modu) tamamlandı. M3 (hibrit arama)
ve M4 (LLM) donanım/model kararlarını bekliyor (HANDOVER §19).

Kararlar: [docs/DECISIONS.md](docs/DECISIONS.md)
