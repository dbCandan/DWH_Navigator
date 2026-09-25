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
vsa eval                                    # golden set metrikleri
```

## Durum

Geliştirme aşamasında — M1 (LLM'siz çekirdek).
