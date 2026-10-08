# Kurulum — Docker ile (şirket ağı)

DWH Navigator tek bir konteynerdir. Dışarıya yalnız **model sunucusuna** (DGX Spark, OpenAI
uyumlu API) çıkar; başka hiçbir adrese bağlanmaz, dış kaynak (CDN, font, analitik) yüklemez.

| | |
|---|---|
| İmaj | `dwh-navigator:0.1.0` — Alpine 3.24 + Python 3.12, ~119 MB |
| Port | `8765` (HTTP; TLS önündeki ters vekilde) |
| Kullanıcı | `vsa` (uid/gid `10001`), kök değil |
| Yazılabilir alan | yalnız `/app/data` (birim) ve `/tmp` |
| Sağlık kontrolü | `GET /healthz` → `{"ok": true}` |

## 1. İmajı edinmek

**İnternete çıkabilen bir makinede derleyip** şirket ağına taşımak en kolayıdır:

```bash
docker build -t dwh-navigator:0.1.0 .
docker save dwh-navigator:0.1.0 | gzip > dwh-navigator-0.1.0.tar.gz
```

Şirket ağındaki sunucuda:

```bash
docker load -i dwh-navigator-0.1.0.tar.gz
```

Kurum içi bir kayıt defteri (Harbor, Nexus, Artifactory…) varsa `docker tag` + `docker push`
ile oraya da konabilir. Derleme sırasında Docker Hub'dan taban imaj ve PyPI'dan 4 paket
(openpyxl, et-xmlfile, defusedxml, PyYAML) indirilir; sürümleri ve SHA-256 özetleri
`requirements.lock` dosyasında sabittir.

## 2. Veri klasörü

Sunucuda bir klasör hazırlayın:

```
dwh-navigator/
├── compose.yaml          (repodan)
├── .env                  (.env.example'dan kopyalayın)
└── data/                 (boş; uygulama doldurur)
```

Sözlük dosya olarak konmaz; ilk açılıştan sonra yönetim ekranından içe aktarılır (§7).

Konteyner `uid 10001` ile çalışır; Linux'ta klasörün sahibini ayarlayın:

```bash
sudo chown -R 10001:10001 data
```

İlk açılışta `data/` altına şunlar oluşur: `terms.jsonl` (terim
sözlüğü) ve `stopwords.jsonl` (durak kelimeler; ikisi de `/admin` → **Kelimeler**'den
düzenlenir, var olan dosyaya dokunulmaz), `index/` (arama
indeksi), `llm_integrations.yaml` (model bağlantıları, **API anahtarı içerir**), `settings.yaml`
(yalnız yönetim ekranından bir ayar değişince; yoksa ölçülmüş varsayılanlar geçerli), `cache/`
(kayıtlı cevaplar), `logs/` (analiz kayıtları), `feedback.jsonl` (👍/👎), `out/` (Excel raporları).
**Yedeklenecek tek klasör `data/`'dır.**

## 3. Yönetim parolası

Yönetim ekranı (`/admin`: model bağlantısı, ayarlar, analiz kayıtları) parola ister. `.env`:

```
VSA_ADMIN_PASSWORD=uzun-ve-rastgele-bir-parola
```

Parola yoksa yönetim ekranı yalnız konteynerin kendisinden açılır, yani fiilen kapalıdır.
Docker secret kullanılacaksa `VSA_ADMIN_PASSWORD_FILE=/run/secrets/vsa_admin` verilebilir.
Tarayıcı kullanıcı adı da sorar; herhangi bir ad yazılabilir (ör. `admin`). Aynı adresten 5
hatalı denemeden sonra 5 dakika beklenir.

Uygulama klasörü varsayılan olarak `./data`'dır; başka bir yer için `.env`'e
`VSA_DATA_DIR=./baska-klasor` yazılır (geliştirme makinesinde yerel `data/` ile karışmasın diye).

## 4. Başlatma

```bash
docker compose up -d
docker compose logs -f        # "İndeks hazır" ve "VSA arayüzü" satırları
```

`compose.yaml` konteyneri salt-okunur kök dosya sistemiyle, tüm Linux yetkileri düşürülmüş
(`cap_drop: ALL`), `no-new-privileges` ile ve bellek/süreç sınırlarıyla çalıştırır.
Compose yoksa aynısı:

```bash
docker run -d --name dwh-navigator --restart unless-stopped -p 8765:8765 \
  -e VSA_ADMIN_PASSWORD=... -v "$PWD/data:/app/data" \
  --read-only --tmpfs /tmp:size=64m --cap-drop ALL --security-opt no-new-privileges:true \
  dwh-navigator:0.1.0
```

## 5. Model bağlantısı

`http://<sunucu>:8765/admin` → **Yapay zekâ → Yeni entegrasyon**:
API adresi (ör. `http://dgx-spark:8000/v1`), gerekiyorsa API anahtarı, sohbet modeli.
**Test et** ile doğrulayıp **aktif** yapın; değişiklik anında geçerli olur.
Model bağlı değilken uygulama açılır ama soru cevaplamaz ("Analiz yapılamadı" + sebep).

Ekran kullanılmayacaksa aynı bilgiler `data/settings.yaml` → `llm:` bölümüne yazılıp konteyner
yeniden başlatılabilir (`data/llm_integrations.yaml` varsa o geçerlidir).

## 6. TLS ve ters vekil

Uygulama düz HTTP konuşur; şirket içinde TLS'i önündeki vekil (nginx, F5, Traefik…) sağlar.
Uzun analizler için okuma zaman aşımını yükseltin (bir soru birkaç dakika sürebilir):

```nginx
location / {
    proxy_pass         http://127.0.0.1:8765;
    proxy_set_header   Host $host;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 900s;
    client_max_body_size 20m;
    add_header Strict-Transport-Security "max-age=31536000" always;
}
```

Konteyner portunu yalnız vekile açın (ör. `ports: ["127.0.0.1:8765:8765"]`).

## 7. Sözlük

Uygulamanın tek sözlüğü `data/dictionary.jsonl`'dir (ADR-050). Excel yalnız aktarım içindir;
uygulama hiçbir Excel dosyasını sözlük olarak okumaz.

- **İlk kurulum:** konteyner sözlüksüz açılır; sorular "Sözlük henüz içe aktarılmadı" der.
  `/admin` → **Sözlük** → "Excel'den içe aktar…" ile şablondaki (Objeler · Kolonlar) Excel'i
  yükleyin; indeks kurulur (~10 sn) ve sözlük hemen kullanılır.
- **Güncelleme:** yeni Excel'i aynı yoldan içe aktarın; mevcut sözlüğün yerini alır, önceki sürüm
  `dictionary.jsonl.bak` olarak saklanır.
- **Dışa aktarma:** "Excel olarak dışa aktar" sözlüğü aynı şablonla verir (düzeltip geri yüklemek
  için); "Boş şablon" yeni bir sözlük için başlangıçtır.

Aynı işlemler komut satırından (dosya `data/` altında olmalı):

```bash
docker compose exec vsa vsa dictionary import data/VeriSozlugu.xlsx
docker compose exec vsa vsa dictionary export data/sozluk_yedek.xlsx
docker compose restart        # komut satırından içe aktarınca: çalışan arayüz yeni sözlüğü okusun
```

Yönetim ekranından içe aktarılan sözlük hemen geçerli olur; komut satırından içe aktarılan ise
konteyner yeniden başlatılınca.

İçe aktarıldıktan sonra Excel dosyasına gerek yoktur; silinebilir.

## 8. Komut satırı (isteğe bağlı)

```bash
docker compose exec vsa vsa ask "kredi kartı limit doluluk oranı"
docker compose exec vsa vsa ask -i data/terimler.xlsx   # rapor: data/out/
docker compose exec vsa vsa index
```

## 9. Güncelleme ve geri dönüş

Yeni sürümün imajını yükleyin, `compose.yaml`'daki etiketi değiştirin, `docker compose up -d`.
`data/` olduğu gibi kalır. Geri dönmek için eski etikete dönün.
Taban imajı yamalamak için Dockerfile'daki `PYTHON_IMAGE` özetini yenileyin
(`docker pull python:3.12-alpine` → `docker image inspect --format '{{index .RepoDigests 0}}'`),
imajı yeniden derleyip `docs/GUVENLIK.md`'deki taramaları tekrarlayın.

## 10. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| Sorular "Sözlük henüz içe aktarılmadı" diyor | `/admin` → Sözlük'ten şablondaki Excel'i içe aktarın; birim (`data/`) doğru bağlı mı? |
| "Permission denied" (data/) | Klasör sahibi `10001` değil: `chown -R 10001:10001 data` |
| `/admin` 403 | `VSA_ADMIN_PASSWORD` tanımlı değil |
| `/admin` 401 | Parola yanlış (tarayıcıyı kapatıp yeniden deneyin) |
| Cevap yerine "Analiz yapılamadı" | Model bağlantısı yok/ulaşılamıyor: Yönetim → Yapay zekâ → Test et |
| Analiz yarıda kesiliyor | Vekilin okuma zaman aşımı kısa (`proxy_read_timeout`) |
