# DWH Navigator — Veri Sözlüğü Asistanı (VSA)

İş birimlerinin doğal dildeki veri taleplerini ("kart limit doluluk oranı nerede?") veya hedef
tablo tasarımlarını (TR başlık / EN başlık / açıklama) veri ambarı sözlüğüne karşı eşleştirir;
**tablo seviyesinde**, gerekçeli, kısıtlı ve güven skorlu öneriler ile iş birimine
gönderilebilir Excel raporları üretir. Kapalı ağda, yerel modellerle çalışır.

- Spesifikasyon: [docs/HANDOVER.md](docs/HANDOVER.md)
- Geliştirme kararları: [docs/DECISIONS.md](docs/DECISIONS.md)

## Hızlı başlangıç (Windows)

`baslat.bat` dosyasına çift tıklayın: eski sunucuyu durdurur, indeks yoksa kurar ve arayüzü
tarayıcıda açar (http://127.0.0.1:8765). Modeller bu makinede değil, DGX Spark sunucularında
çalışır; bağlantıyı http://127.0.0.1:8765/admin → Ayarlar → Yapay zekâ ekranından ekleyin
(OpenAI uyumlu adres, API anahtarı, sohbet ve embedding modeli; test, envanter, aktif/pasif).

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy config\settings.example.yaml config\settings.yaml
```

Veri sözlüğünü `data/` altına koyun (bu klasör repoya girmez). Model bağlantıları yönetim
ekranında tutulur (`config/llm_integrations.yaml`, API anahtarı içerir, repoya girmez).
Ekran kullanılmadan komut satırından çalışılacaksa `config/settings.yaml` → `llm:` bölümü de
yeterlidir (bkz. `settings.example.yaml`).

Aktif model yoksa uygulama kural tabanlı modda çalışmaya devam eder (ADR-008).

## Kullanım

```bash
vsa index                   # sözlükten BM25 indeksi
vsa index --dense           # + vektör indeksi (BGE-M3; CPU'da ~45 dk, kaldığı yerden devam eder)
vsa serve --open            # web arayüzü
vsa ask "kredi kartı limit doluluk oranı"   # terminalden tek soru + Excel
vsa ask -i terimler.xlsx                    # terim listesi (ilk sütun): her terim ayrı, tek rapor
vsa eval --save --label "..."               # golden set metrikleri, geçmişe kayıt
vsa feedback                                # arayüz geri bildirimleri → golden set adayları
```

## Mimari (özet)

Tek akış (ADR-033):

```
talep → kural motoru: Türkçe normalizasyon, kavramlar, genişletme, BM25 + vektör araması,
        kolon skoru, tablo seviyesine toplama (ipucu ve yedek)
      → analist (sohbet modeli bağlıysa): katalogdan aday seçimi → adayların kolonlarını
        okuyup raporu yazma (ADR-029)
      → sözlük doğrulaması → rapor / arayüz
```

Model yoksa ya da hata verirse kural motorunun cevabı döner (ADR-008). Toplu arama aynı
akışı bir Excel listesinin her terimi için sırayla çalıştırır ve tek rapor üretir.

## Durum

| Kilometre taşı | Durum |
|---|---|
| M1 LLM'siz çekirdek | ✓ |
| M2 Değerlendirme | ✓ `vsa eval`, geçmiş `eval/history.jsonl` |
| M3 Hibrit arama | ✓ BGE-M3 + BM25 |
| M4/M8 LLM katmanı | ✓ analist akışı |
| M5 Toplu arama | ✓ Excel listesi → tek rapor |
| M6 Arayüz | ✓ yerel web arayüzü |
| M7 Geri bildirim | başlangıç: 👍/👎 → golden set adayları |

## Geliştirme

```bash
pytest            # model sunucusu gerekmez; gerçek sözlük yoksa ilgili testler atlanır
ruff check src tests
mypy src
```
