# Tarayıcı kanıtı

Kalıcı tarayıcı paketi varsayılan `http://localhost:8080` olmak üzere `APP_E2E_BASE` üzerinde çalışır.
Süreç kaynaklı `super-admin` kimlik bilgilerini (`APP_E2E_SUPER_ADMIN_USER`, `APP_E2E_SUPER_ADMIN_PASS`)
kullanır ve depoya işlemez. Başlangıç parolasıyla açılmış hesap ilk girişte yeni parola ister; bu
durumda yeni parola `APP_E2E_SUPER_ADMIN_NEW_PASS` ile verilir ve sonraki koşumlar onu
`APP_E2E_SUPER_ADMIN_PASS` olarak kullanır. Temel senaryo; korumalı yönlendirme, gerçek formla oturum
açma, belirtecin yalnız bellekte tutulması ve yenileme çerezinin HttpOnly olması, kiracı uygulaması,
veritabanı destekli `/auth/me`, başka kökenden yenileme reddi, yeniden yüklemede yenileme çereziyle
kurtarma ve oturum alanından çıkışın oturumu sunucuda kapatmasını kanıtlar. İstemciden bağımsız
Node.js/Playwright kodudur; eklenti kurmaz veya ikinci MCP sunucusu açmaz. Tarayıcı çalıştırılabilir
dosyaları kontrollü çevrimdışı paketten gelmeli ve
`PLAYWRIGHT_BROWSERS_PATH` ile seçilmelidir.

Paketi depo kökünden çalıştırın:

~~~sh
export KT_SCAFFOLD_OFFLINE_BUNDLE=/approved/bundles/<platform-matrix>
export KT_SCAFFOLD_OFFLINE_BUNDLE_SHA256=<bank-admission-sha256-of-SHA256SUMS>
scripts/e2e.sh auth
~~~

Varsayılan kip çevrimdışıdır. Yardımcı önce `SHA256SUMS` dosyasını bankanın bant dışı yapıt kabul
kaydındaki özete bağlar; listedeki her dosyayı doğrular, paketin platform uyumluluğunu denetler, npm
çevrimdışı kipiyle paket önbelleğinden kurar, Playwright'ın kabul edilmiş ağaç içindeki
çalıştırılabilir Chromium dosyasını çözümlediğini doğrular ve ancak sonra paketi başlatır. Kayıt deposuna
veya tarayıcı indirmesine geri dönüş yoktur. Yük ile paket içi bildirimi birlikte yeniden yazmak
güven oluşturmaz. Bankaya bağlı geliştirme ortamı açıkça `KT_SCAFFOLD_E2E_MODE=private-index`
seçebilir; bu kip ayrıca `KT_SCAFFOLD_NPM_REGISTRY` ve önceden hazırlanmış
`PLAYWRIGHT_BROWSERS_PATH` ister, genel npm kayıt depolarını reddeder.

Hata durumunda her paket kısa ad içeren `test-results/*-failure.png` yazar; bu yok sayılan yerel
kanıttır. Kök kalite kapısı bütün `e2e/*/run-all.mjs` çalıştırıcılarını keşfeder; üretilen alan paketleri
tarayıcı kanıt seviyesinin sessizce dışında kalamaz.
