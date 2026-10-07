# Güvenlik — ön zafiyet taraması ve sertleştirme (2026-10-07)

Şirket ağına entegrasyon taramasından önce yapılan iç denetimin özeti. Taramalar aşağıdaki
komutlarla tekrarlanabilir; her sürümde ve taban imaj güncellendiğinde yeniden çalıştırın.

## Sonuç özeti

| Kapsam | Araç | Sonuç |
|---|---|---|
| Konteyner imajı — işletim sistemi paketleri (Alpine 3.24.2) | Trivy 0.72.0, DB 2026-10-07 | **0** zafiyet |
| Konteyner imajı — Python paketleri | Trivy 0.72.0 | **0** zafiyet |
| Konteyner imajı — gömülü sır (anahtar, parola, token) | Trivy secret | **0** bulgu |
| Dockerfile yapılandırması | Trivy misconfig | **0** bulgu |
| Bağımlılık kilidi (`requirements.lock`, 11 paket) | pip-audit 2.10.1 (PyPI + OSV) | **0** zafiyet |
| Uygulama kaynak kodu (7.4 bin satır) | Bandit 1.9.4 | **0** bulgu (tüm önem seviyeleri) |
| Kaynak kod, Docker dosyaları (46 dosya) | Semgrep (p/python, p/security-audit, p/owasp-top-ten, p/secrets) | **0** bulgu |
| Git geçmişi (54 commit) ve çalışma ağacı | Gitleaks 8.30.1 | **0** sızıntı |
| Çalışan uygulama — pasif DAST | OWASP ZAP baseline (stable) | **0 FAIL**, 65 PASS; 1 bilgi uyarısı (aşağıda) |
| Çalışan uygulama — şablon taraması | Nuclei 3.11.0 (10.532 şablon çalıştı; dos/fuzz/intrusive hariç) | **0** zafiyet; 5 bilgi eşleşmesi (aşağıda) |
| Lint / tip | ruff, mypy --strict | temiz |
| Testler | pytest | 231 test geçti |

Nuclei'nin 5 eşleşmesi bilgi düzeyindedir: teknoloji tespitleri (`addEventListener`, `/healthz`),
dosya yükleme formunun varlığı (Excel listesi; sınırları bulgu 5'te), eksik
`Strict-Transport-Security` (TLS ve HSTS ters vekilde verilir, §Kalan riskler 1) ve
`X-Permitted-Cross-Domain-Policies` (eklendi: `none`).

ZAP'ın tek kalan uyarısı "Non-Storable Content" (Bilgi): her yanıt bilerek `Cache-Control:
no-store` taşır — cevaplar ve raporlar tarayıcıda/vekilde önbelleğe alınmasın diye.

Karşılaştırma: aynı uygulama Debian 13 (`python:3.12-slim-trixie`) tabanında 165 OS zafiyeti
(44 HIGH, hiçbirinin yaması yok) veriyordu; Alpine'e geçilerek sıfırlandı ve imaj 212 MB'tan
119 MB'a indi.

## Bileşen envanteri (SBOM özeti)

Çalışma imajında yalnız şunlar vardır: Alpine taban (musl, busybox, ~38 apk paketi), CPython
3.12.15 ve aşağıdaki Python paketleri. pip/setuptools imajdan çıkarılmıştır.

| Paket | Sürüm | Neden |
|---|---|---|
| openpyxl | 3.1.5 | Excel okuma/yazma |
| et-xmlfile | 2.0.0 | openpyxl bağımlılığı |
| defusedxml | 0.7.1 | yüklenen Excel'lerin XML'i güvenli ayrıştırılır |
| PyYAML | 6.0.3 | ayar dosyaları (yalnız `safe_load`) |
| typer, annotated-doc, shellingham | 0.27.3, 0.0.5, 1.5.4 | komut satırı |
| rich, markdown-it-py, mdurl, Pygments | 15.0.0, 4.2.0, 0.1.2, 2.21.0 | terminal çıktısı |

Web sunucusu ve model istemcisi Python standart kütüphanesidir (`http.server`, `urllib`);
web arayüzü tek HTML dosyasıdır, dış kaynak (CDN, font, analitik) yüklemez.
Tam SBOM: `trivy image --format cyclonedx --output sbom.json dwh-navigator:0.1.0`.

## Bu denetimde kapatılan bulgular

| # | Bulgu | Önem | Düzeltme |
|---|---|---|---|
| 1 | Yönetim ekranı ve API'leri (model bağlantısı/API anahtarı, ayarlar, kayıt silme) kimlik doğrulamasız ve ağa açıktı | Yüksek | `VSA_ADMIN_PASSWORD` ile HTTP Basic; parola yoksa yalnız sunucunun kendisinden (loopback, vekilsiz, `Host` doğrulamalı — DNS rebinding'e karşı). 5 hatalı denemede 5 dk kilit, sabit zamanlı karşılaştırma (`vsa/web/security.py`) |
| 2 | Siteler arası istek sahteciliği (CSRF): başka bir sitenin sayfası ayar kaydedebilir, model adresini değiştirebilirdi | Yüksek | Tüm POST'larda `Sec-Fetch-Site` / `Origin` denetimi |
| 3 | Model bağlantı testinin sunucu tarafı istek yapması (SSRF yüzeyi) | Orta | Yalnız yönetim parolasıyla erişilebilir (bulgu 1) |
| 4 | Excel formül enjeksiyonu: "=" ile başlayan soru/model metni raporda formül olarak yazılıyordu (CWE-1236) | Orta | Tüm hücreler metin olarak yazılır (`report/excel.py::_text`) |
| 5 | Yüklenen Excel'de XML saldırıları (billion laughs) ve sıkıştırma bombası | Orta | `defusedxml`; liste dosyasında en fazla 2000 satır × 50 sütun okunur, 20 MB yükleme sınırı |
| 6 | Güvenlik başlıkları eksikti | Orta | Katı CSP: yalnız sayfanın kendi betik ve stil blokları (SHA-256 özetiyle), `'unsafe-inline'` yok — eleman stilleri CSSOM ile verilir; `frame-ancestors 'none'`. Ayrıca `X-Frame-Options`, `nosniff`, `Referrer-Policy`, COOP/COEP/CORP, `Permissions-Policy`; Python'un kendi hata sayfaları da aynı başlıklarla |
| 7 | Hata yanıtlarında istisna metni dönüyordu (bilgi sızıntısı) | Düşük | 500'lerde genel mesaj; ayrıntı yalnız sunucu kaydında |
| 8 | `Server` başlığında Python sürümü | Düşük | Yalnız `VSA` |
| 9 | Geçersiz/negatif `Content-Length`, parçalı gövde, JSON dizisi gövde | Düşük | 400/411/413 ile reddedilir |
| 10 | Yavaş istemci (slowloris) | Düşük | İstek okuma zaman aşımı 120 sn |
| 11 | Çok uzun soru metni (modele dev bağlam) | Düşük | En fazla 4000 karakter |
| 12 | `git` alt süreci (değerlendirme geçmişi) | Bilgi | Kaldırıldı; commit `.git` klasöründen okunur |
| 13 | Sayfa kaynağında SQL'e benzeyen yorum kelimeleri (ZAP "Suspicious Comments") | Bilgi | Yorumlar yeniden yazıldı |

## Konteyner sertleştirmesi

- Kök olmayan kullanıcı (`10001:10001`), kabuk girişi yok (`/sbin/nologin`).
- Salt-okunur kök dosya sistemi; yazılabilir yalnız `/app/data` ve `/tmp` (tmpfs).
- `cap_drop: ALL`, `no-new-privileges`, bellek (2 GB) ve süreç (256) sınırı.
- Taban imaj özetle (digest), Python paketleri sürüm + SHA-256 ile sabit (`--require-hashes`,
  yalnız wheel). pip ve setuptools çalışma imajında yok.
- İmaja yalnız uygulama kodu ve iki yapılandırma dosyası girer (`.dockerignore` beyaz liste):
  sözlük, kurum içi veri, API anahtarları, testler, Windows betikleri (`baslat.bat`) girmez.
- `HEALTHCHECK` `/healthz` ile (modele çağrı yapmaz).

## Kalan riskler ve öneriler

1. **TLS**: uygulama HTTP konuşur; şirket vekili TLS sonlandırmalı, konteyner portu yalnız
   vekile açılmalı (`docs/KURULUM.md` §6). HSTS vekilde verilir.
2. **Son kullanıcı kimliği**: soru sorma ekranı kimlik sormaz (kapalı ağ, ekip aracı). Erişim
   kısıtlanacaksa vekilde SSO/AD kimlik doğrulaması önerilir; kayıtlarda kullanıcı olarak
   istemci adresi tutulur.
3. **Ağ çıkışı**: konteynerin dışarıya tek ihtiyacı model sunucusudur. Güvenlik duvarında
   yalnız DGX Spark adres/portuna çıkış izni verilmesi önerilir.
4. **Model sunucusu**: OpenAI uyumlu uç nokta HTTP ise API anahtarı ağda açık gider; mümkünse
   HTTPS ya da ayrılmış VLAN kullanılmalı.
5. **Veri birimi**: `data/llm_integrations.yaml` API anahtarı, `data/logs/` soru metinleri ve
   istemci adresleri içerir; birim yalnız uygulama kullanıcısına açık olmalı, yedekler
   şifrelenmeli.
6. **Kişisel veri**: sözlükte KVKK işaretli kolonlar gösterilir ama hiçbir müşteri verisi
   işlenmez; uygulama yalnız sözlük metinleriyle çalışır.
7. **Taban imaj takibi**: Alpine/CPython yamaları için imaj aylık ya da kritik bir CVE'de
   yeniden derlenip taranmalı.

## Taramaları tekrarlamak

```bash
docker build -t dwh-navigator:0.1.0 .
docker save dwh-navigator:0.1.0 -o image.tar
docker run --rm -v "$PWD:/scan" aquasec/trivy image --input /scan/image.tar \
  --scanners vuln,secret,misconfig --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL
docker run --rm -v "$PWD:/src" aquasec/trivy config /src
pip install pip-audit bandit
pip-audit -r requirements.lock --require-hashes --disable-pip
bandit -r src
docker run --rm -v "$PWD:/src" -w /src semgrep/semgrep semgrep scan --metrics=off \
  --config p/python --config p/security-audit --config p/owasp-top-ten --config p/secrets src
docker run --rm -v "$PWD:/repo" ghcr.io/gitleaks/gitleaks:v8.30.1 git /repo --redact
```

Dinamik tarama (uygulama ayrı bir Docker ağında, parolalı):

```bash
docker network create vsa-scan
docker run -d --name vsa-scan-app --network vsa-scan -e VSA_ADMIN_PASSWORD=... \
  -v "$PWD/data:/app/data" dwh-navigator:0.1.0
docker run --rm --network vsa-scan -v "$PWD:/zap/wrk:rw" zaproxy/zap-stable \
  zap-baseline.py -t http://vsa-scan-app:8765 -r zap.html
docker run --rm --network vsa-scan projectdiscovery/nuclei -u http://vsa-scan-app:8765 \
  -etags dos,fuzz,intrusive
```

Bağımlılık kilidini yenilemek (Linux konteynerinde, hash'lerle):

```bash
docker run --rm -v "$PWD:/w" -w /w python:3.12-alpine sh -c \
  "pip install pip-tools && pip-compile --generate-hashes --strip-extras --allow-unsafe \
   --no-emit-index-url --output-file=requirements.lock pyproject.toml"
```
