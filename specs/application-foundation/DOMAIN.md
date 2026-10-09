# application-foundation alanı

## Amaç ve sonuçlar

DWH Navigator'ın kimlik, yetki, çalışma ortamı ve dağıtım temeli. Kullanıcılar uygulamanın kendi
yerel hesaplarıyla girer (Active Directory bağlantısı yoktur), rolüne göre yetkilendirilir; uygulama
yerelde Docker Compose ile Windows ve macOS'ta, nonprod'da KT Rancher kümesinde tek chart
(Kubernetes kurulum paketi) ile çalışır.

## Aktörler

- **Kullanıcı:** Yerel hesabıyla giriş yapan `kullanici` veya `yonetici`.
- **Uygulama yöneticisi (süper yönetici):** Hesap açan, rol atayan, parola sıfırlayan ve hesabı
  pasifleştiren yerel hesap.
- **İşletim ekibi:** Azure dağıtım işini, gizli değişkenleri ve küme kaynaklarını yönetir.
- **Geliştirici:** Uygulamayı yerelde Docker Compose ile Windows veya macOS'ta çalıştırır ve dener;
  yerel yığını kodlama ajanının başlat/durdur komutlarıyla yönetir.

## Ortak dil

- **Yerel hesap:** Süper yöneticinin uygulamada açtığı kullanıcı adı ve parola; parola yalnız
  özetiyle saklanır.
- **Rol:** `kullanici` veya `yonetici`. Süper yönetici ayrıca `super_admin` rolündedir.
- **Runtime Secret:** Nonprod'da uygulama sırlarını taşıyan Kubernetes Secret'ı
  (`dwhnavigator-runtime`); `helm/dwhnavigator/deploy-hooks.sh` hazırlar.
- **Ortam:** `local` (geliştirici makinesi, `DWHNAVIGATOR_ENVIRONMENT=development`) veya `nonprod`
  (KT Rancher kümesi, `DWHNAVIGATOR_ENVIRONMENT=staging`). Başka ya da okunamayan değer `nonprod`
  gibi davranır.

## Değişmezler

- Her API isteği, sağlık uçları dışında, geçerli oturum ve uygun rol ister; canlı olay akışları
  (SSE) dahil.
- Parola düz metin olarak saklanmaz, loglanmaz, belirtece girmez; yalnız özeti saklanır.
- Sırlar Git'e, Helm değer dosyasına, komut argümanına ve loga girmez.
- Dağıtım, yayımlanmamış imajla kümeye dokunmaz ve hizmet vermiş release'i silmez.
- Ölçümler ve izler (OpenTelemetry) yalnız PRD'lerin Gözlemlenebilirlik bölümünde adı geçen
  sinyallerdir. Etiket değerleri sabit kümelerdir; kümede olmayan değer `other` olarak yazılır. Soru
  metni, sözlük içeriği, tablo ve kolon adı, model istemi ve yanıtı, adres, parola, belirteç ve
  kullanıcı adı hiçbir iz aralığına, özniteliğe veya ölçüme girmez; hata metni ize yazılmaz.

## Sahip olunan veri

PostgreSQL'de kullanıcı kaydı (kullanıcı adı, görünen ad, rol, parola özeti, son giriş), oturum
yenileme durumu ve hesap değişikliği kaydı.

## Harici sınırlar

- **KT Rancher nonprod kümesi ve Azure dağıtım işi:** `helm/dwhnavigator/deploy.sh` ile.
- **Kurum imaj deposu:** `cr-test.kuveytturk.com.tr/ghcr.io.vc/kt-vibecoding/`.
- **OpenTelemetry toplayıcısı:** Ölçüm ve izler OTLP/gRPC ile yalnız
  `DWHNAVIGATOR_OTEL_EXPORTER_OTLP_ENDPOINT` adresine gider; ayar boşsa hiçbir sinyal dışarı çıkmaz.

## İş yetkinliği yol haritası

[Yol haritası](roadmap.md).
