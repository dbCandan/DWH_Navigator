# Kararlar (ADR)

ADR-001…036 önceki `docs/` ile birlikte kaldırıldı; özetleri CLAUDE.md'de. Yeni kararlar buraya eklenir.

## ADR-037 — Tek, konsolide veri sözlüğü (2026-10-05)
`DataDictionary-Final.xlsx` ve `ObjectNameList.xlsx` tek dosyada birleştirildi: `data/VeriSozlugu.xlsx`.
- İki sayfa: **Objeler** (ObjectKey, ad, ObjectDescription, Grain, KeyColumns, TimeColumns,
  BusinessDomain, DatasetGroup) ve **Kolonlar** (DatabaseName, SchemaName, ObjectName, ColumnName,
  ColumnDescription, Synonyms, Role, Summary).
- Kolon kümesi yeni sözlükten (daha güncel); tablo açıklamaları ve kaynak metinler eski listeden.
  Yalnız eski listede kalan 24 kolon alınmadı (var olmayan alan önerilmez).
- Kolonlar sayfasındaki tüm açıklamalar **doğrulanmış kabul edilir**: bayrak, süreç notu, kalite sayfası
  ve değişiklik günlüğü tutulmaz. DatasetGroup Objeler'den `DB.Şema.Obje` ile gelir.
- **Role** (Anahtar, Kod, Ad, Zaman, Ölçü, Bayrak, Metin) ve **Summary** (≤70 karakter
  sıkıştırılmış anlam) LLM'e uzun açıklama yerine verilmek için üretildi; sözlüğün "ad + rol + özet"
  hali tam açıklamanın ~1/5'i token tutar.

## ADR-038 — LLM'siz çalışma şartı kalktı (ADR-008'in yerine) (2026-10-05)
Uygulama bir sohbet modeli olmadan cevap üretmez; model ulaşılamazsa ekranda açık bir hata verilir.
Kural motoru (BM25 + kural skoru) yalnız modele ipucu ve doğrulayıcı olarak kalır.

## ADR-039 — Vektör araması kaldırıldı (2026-10-05)
Embedding modeli, vektör indeksi, tablo profil vektörleri ve ilgili yönetim ekranı kaldırıldı.
Gerekçe: ölçülmüş bir kazancı yoktu (golden setteki M3 ölçümü BM25 ile aynı), işletme maliyeti
vardı (her sorguda embedding çağrısı, sözlük/model değişince yeniden kurulum), ve tablo seçimini
artık model yapıyor. Eş anlamlılar ve Summary kelime aramasını besler.

## ADR-040 — Analist akışı: kompakt malzeme (2026-10-05)
- 1. adım katalogu Objeler sayfasından kurulur: `id | tablo | grup | kolon sayısı | içerik |
  Satır: grain | Zaman: kolonlar`. Kolon adları yalnız açıklaması olmayan tablolarda (ya da
  `analyst.catalog_columns: true` ile). Katalog her soruda aynıdır (önek önbelleği).
- 2. adımda kolonlar `Ad [Rol]: özet` biçiminde gider; talebe en ilgili `analyst.detail_columns`
  kolon tam açıklamasıyla.
- Hedef: aynı isabetle daha az okunan token, daha kısa süre. Ölçüm: `data/golden/` altındaki
  67 soruluk set, Fable ve Opus'un bağımsız cevaplarıyla (doğru cevap kabul edilir).

## ADR-041 — Talebin asıl kavramı cevabı belirler (2026-10-06)
Model talebin asıl bilgisini (`core_concept`) ve bunun aday tablolarda olup olmadığını
(`core_found`) yazar. Asıl bilgi yoksa ya da model BULUNAMADI derse, önerdiği yakın tablolar
cevap olmaz: tek bir "İlgili" notuna dönüşür, sonuç BULUNAMADI olur. Gerekçe: negatif sorularda
"KISMEN VAR" ile teselli tablosu önermek kullanıcıyı yanlış yönlendiriyordu.

## ADR-042 — Asıl kavram bir kolonla gösterilmeli (2026-10-06)
Model asıl bilgiyi taşıyan 1-3 kolonu (`core_columns`, "T12.Kolon") adıyla yazar; kod bunları
aday tablolarda doğrular. Geçerli kolon yoksa cevap ADR-041'deki gibi BULUNAMADI olur. Talep bir
varlığın niteliğini istiyorsa (oran, tutar, bakiye, süre) asıl bilgi o niteliktir; varlığın
türü, bayrağı ya da kaydı yetmez. Bilgi birden çok aday tabloya dağılmış ve birleştirilerek elde
ediliyorsa bu BULUNAMADI değil KISMEN VAR'dır (ilk sürüm birleştirme sorularını "tek tabloda yok"
diye BULUNAMADI'ya çeviriyordu; açıklık eklendi). Gerekçe: 294 soruluk ölçümde negatif hataların hepsi (9) bu
kalıptı — varlık var, istenen nitelik yok. Alanı olmayan eski cevaplarda kontrol uygulanmaz.
Ön kontrol (101 soru: akşam hatalı/negatif + 30 doğru koruma sorusu): koruma 30/30, hedef
negatifler 0/9 → 2/9, birleştirme kaybı yok. Tam 294 ölçümü bekliyor.

## ADR-043 — Sırayı asıl kavram belirler (2026-10-07)
Önerilerin sırasını model güveni değil kod verir: modelin gösterdiği asıl kavram kolonlarını
(ADR-042) en çok taşıyan tablo öne geçer; eşitlikte genel tablo, dar kitleli / türetilmiş
tablonun (açıklamasında model girdisi, eğitim verisi, akıllı hedefleme, özel bankacılık
müşterileri, segmentasyon girdisi geçen) önüne geçer; sonra güven. Öne geçen tablo, geçtiği
tablonun güveninden düşük gösterilmez. Kolon gösterilmemişse modelin sırası kalır.
Gerekçe: 294 soruda cevaplanabilir 23 hatanın 17'sinde doğru tablo ilk 3'teydi ama 1.
sırada değildi. Ölçüm (31 soru, seri sunucu): sıralama hatalarının 7/19'u düzeldi, koruma
sorularının 7/8'i korundu.

## ADR-044 — Asıl kavram için ikinci denetim çağrısı: REDDEDİLDİ (2026-10-07)
Denendi: analist cevabından sonra kısa bir çağrı, gösterilen asıl kavram kolonlarının talebin
asıl bilgisini "birebir" taşıyıp taşımadığını sorar; "hayır" → BULUNAMADI. Ölçüm (seri sunucu,
gece ölçümü tabanına göre): negatifler 40/48 → 43/48, ama doğru cevaplanmış 40 koruma sorusundan
3'ü BULUNAMADI'ya döndü (%7,5). Tam sette ~230 doğru cevaba yayılan kayıp, birkaç negatif
kazancını aşar. Uygulanmadı. Negatif hatalar için yol: modelin "nitelik yok" ayrımını daha güçlü
yapan bir model ya da sözlükte kolon düzeyinde daha net açıklamalar.

## ADR-045 — Ölçüm sorularından türeyen prompt örnekleri kaldırıldı; "eksik bilgi" gösterilir (2026-10-07)
ADR-041/042 promptundaki somut örneklerin bir kısmı (hane geliri, ATM arıza kaydı, takipçi sayısı,
rakip banka oranı, ekran bazında süre, onay kaydı ≠ bakiye, aktarılan tutar ≠ karşı kurumdaki
bakiye) ölçüm setindeki hatalı sorulardan türemişti; bu, o sorulardaki skoru şişirebilir. Somut
örnekler kaldırıldı, yalnız genel kural kaldı ("farklı düzey / taraf / nesne aynı bilgi değildir").
Ölçüm (seri, 160 soru, gece sürümüne göre): negatifler 40/48 → 39/48 (z091, z093 ipucu olmadan
yanlış), cevaplanabilir 103 → 102; 294 için dürüst tahmin ~%89,8 (sızıntılı %90,5). Kör set (50,
sızıntısız) %90,0. Ayrıca rapora `missing` alanı eklendi: KISMEN VAR cevabında talebin
karşılanmayan parçaları (≤3) ekranda etiketin yanında ve Excel'de "Eksik Bilgi" olarak gösterilir;
model eksik olanı özetinde yazsa da hızlı okuyan kullanıcı kaçırmasın diye. Hızlı test 9/10.

## ADR-046 — MVP temizliği: eski bayraklar, açıklama içi eş anlamlılar ve pandas kaldırıldı (2026-10-07)
Sözlük ADR-037'den beri doğrulanmış kabul edildiği için baştaki `[...]` bayrakları
(`MODEL TAHMİNİ`, `DÜZELTİLDİ`, `DOĞRULANMALI`), bunların uyarı/kalite notları ve arayüzdeki
"Uyarılı" filtresi kaldırıldı; açıklama metni olduğu gibi kalır. Eş anlamlılar yalnız `Synonyms`
kolonundan, veri seti grubu yalnız `Objeler` sayfasından okunur (açıklama içindeki
"Eş anlamlılar:" bölümü ve satır başına DatasetGroup okunmaz). Gerçek sözlükte bunların hiçbiri
yoktu. Yükleyici pandas yerine openpyxl'i doğrudan kullanır (pandas + numpy + dateutil + tzdata
çıktı; çalışma bağımlılığı 11 pakete indi). Yalnız kural cevabında görünen netleştirme soruları
(`config/clarifications.yaml`) ve tablo birleştirme notu, kullanılmayan fonksiyonlar, bulut
API'lerinden kalan yeniden deneme kodu ve vektör aramasından kalan indeks dosyaları silindi.
Doğrulama: 129 soruda (altın set + referans setlerinden) sözlük çıktısı, kural sıralaması,
modele giden promptların tamamı ve (sahte modelle) analist cevabı değişiklikten önce ve sonra
**bayt bayt aynı**; yalnız kullanıcıya gösterilmeyen kural cevabının netleştirme notları düştü.
Eski indeks ve kayıtlı cevaplar okunmaya devam eder (emekli alanlar yok sayılır).

## ADR-047 — Yönetim ekranı korunur, istekler denetlenir (ADR-030'un "korumasız" kısmının yerine) (2026-10-07)
Şirket ağına çıkış için: `/admin` ve `/api/admin`, `/api/settings`, `/api/reindex`, `/api/llm`
yolları `VSA_ADMIN_PASSWORD` (ya da `VSA_ADMIN_PASSWORD_FILE`) ile HTTP Basic ister; parola
yoksa yalnız sunucunun kendisinden açılır (loopback, vekilsiz, `Host` loopback). Tüm POST'lar
`Sec-Fetch-Site`/`Origin` ile siteler arası isteğe karşı denetlenir; her yanıt CSP (sayfa betiği
SHA-256 özetiyle), `X-Frame-Options` vb. taşır; Excel'e yazılan metin formül olamaz; yüklenen
listeler `defusedxml` ve satır/sütun sınırıyla okunur. Uygulamadan yönetim ekranına bağlantı
yine yoktur. Ayrıntı ve tarama sonuçları: `docs/GUVENLIK.md`.

## ADR-048 — Dağıtım: Alpine tabanlı Docker imajı (2026-10-07)
Üretim kurulumu tek konteynerdir (`Dockerfile`, `compose.yaml`, `docs/KURULUM.md`). Taban
`python:3.12-alpine` (özetle sabit): aynı uygulama Debian slim tabanında 165 yamasız OS zafiyeti
(44 HIGH) verirken Alpine'de 0; imaj 119 MB. Paketler `requirements.lock` ile sürüm + hash
sabit, pip çalışma imajında yok, kullanıcı uid 10001, kök dosya sistemi salt-okunur, tüm veri
`/app/data` biriminde. `serve --auto-index` indeks yoksa ya da sözlük değiştiyse açılışta kurar.
Windows yerel geliştirme (`baslat.bat`, `scripts/`) repoda kalır, imaja girmez.
