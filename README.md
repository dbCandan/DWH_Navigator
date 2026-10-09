# DWH Navigator — Veri Sözlüğü Asistanı (VSA)

İş birimlerinin doğal dildeki veri taleplerini ("kart limit doluluk oranı nerede?") veri ambarı
sözlüğüne (11 bin kolon, 390 tablo) karşı eşleştirir; **tablo seviyesinde**, gerekçeli ve güven
skorlu öneriler ile iş birimine gönderilebilir Excel raporları üretir. Kapalı ağda çalışır;
cevabı kurum içi sunucudaki sohbet modeli (DGX Spark, OpenAI uyumlu API) yazar.

- **Kurulum (Docker, şirket ağı):** [docs/KURULUM.md](docs/KURULUM.md)
- **Güvenlik ve zafiyet taraması:** [docs/GUVENLIK.md](docs/GUVENLIK.md)
- **Kararlar:** [docs/DECISIONS.md](docs/DECISIONS.md)

## Hızlı başlangıç (Docker)

```bash
docker build -t dwh-navigator:0.1.0 .
cp .env.example .env            # VSA_ADMIN_PASSWORD'ü doldurun
docker compose up -d            # http://<sunucu>:8765 · yönetim: /admin
```

Sonra `/admin` → **Sözlük** → "Excel'den içe aktar…" ile şablondaki sözlüğü yükleyin ve
Yapay zekâ sayfasından model bağlantısını ekleyin (adres, anahtar, model; test; aktif).

## Nasıl çalışır

```
talep → kural motoru: Türkçe normalizasyon, terim sözlüğü, BM25 araması, tablo seviyesine
        toplama — modele ipucu ve doğrulayıcı (ADR-038)
      → analist (sohbet modeli): 1. tüm tablo kataloğundan aday seçer
                                 2. adayların kolonlarını okuyup raporu yazar (ADR-029)
      → sözlük doğrulaması: var olmayan tablo/kolon geçen cümle silinir (ADR-002)
      → arayüz / Excel raporu
```

Model yoksa ya da ulaşılamıyorsa cevap "Analiz yapılamadı" + sebeptir; kural motorunun kendi
sıralaması kullanıcıya gösterilmez. Toplu arama aynı akışı bir Excel listesinin her terimi için
çalıştırır ve tek rapor üretir. Aynı soru (ya da aynı anlam) tekrar gelirse kayıtlı cevap
verilir (ADR-035); 👍/👎 sonraki cevapları şekillendirir (ADR-036).

## Geliştirme (Windows, yerel)

```bash
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\vsa serve --open      # ya da baslat.bat; indeks yoksa önce kurulur
```

```bash
pytest                 # model sunucusu gerekmez; gerçek sözlük yoksa ilgili testler atlanır
ruff check src tests
mypy src
vsa eval --save --label "ne değişti"   # ağırlık / model değişikliğinden önce ve sonra
```

Komutlar: `vsa serve`, `vsa index`, `vsa ask "…"`, `vsa ask -i liste.xlsx`, `vsa eval`,
`vsa dictionary import|export`. Ayar dosyası gerekmez: varsayılanlar ölçülen ayarlardır;
yönetim ekranında değiştirilen ayar `data/settings.yaml`'a yazılır.

Çalışma bağımlılıkları dört pakettir: openpyxl (+ et-xmlfile), defusedxml, PyYAML.

Uygulamanın tek sözlüğü `data/dictionary.jsonl`'dir. Excel yalnız aktarım içindir: şablondaki
Excel yönetim ekranının **Sözlük** sekmesinden (ya da `vsa dictionary import`) içe aktarılınca
sözlüğün yerini alır; sözlük aynı şablonla dışa aktarılır (ADR-049, ADR-050).

Uygulamanın okuduğu ve yazdığı her şey `data/` klasöründedir (ADR-052): sözlük, terim sözlüğü
(`terms.jsonl`), durak kelimeler (`stopwords.jsonl`), ayarlar, model bağlantıları, indeks,
kayıtlar. Terim sözlüğü ve durak kelimeler yönetim ekranının **Kelimeler** sayfasından
düzenlenir. `data/` repoya girmez (kurum içi veri ve API anahtarları); yalnız `terms.jsonl` ve
`stopwords.jsonl` repodadır. `out/`, `*.xlsx` ve `.env` de repoya girmez.
