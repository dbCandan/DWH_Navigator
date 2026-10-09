# Kalite bildirimi

| Yüzey | Senaryo | Kanıt |
|---|---|---|
| Platform kimlik doğrulaması | auth/01-super-admin-login.mjs | Korumalı yönlendirme, gerçek formla oturum açma ve gerektiğinde ilk girişte yeni parola, belirtecin yalnız bellekte tutulması ve HttpOnly yenileme çerezi, kiracı ret/kabulü, veritabanı destekli `/auth/me`, başka kökenden yenileme reddi, yeniden yüklemede çerezle geri gelme, oturum alanından sunucuda kapanan çıkış |
| Soru analizi (question-analysis) | question/01-ask-and-answer.mjs | Bağlı sohbet modeliyle soru sorma, "Durdur" ve Esc ile durdurma, "Bir bakışta" ile cevap, Excel raporunun oturum belirteci başlıkta giderek indirilmesi (adreste belirteç yok), aynı soruda "Önceki cevap" ve "Yeniden analiz et" ile yeni analiz |

Alan satırları yalnız kabul edilmiş PRD'ler tarafından eklenir.
