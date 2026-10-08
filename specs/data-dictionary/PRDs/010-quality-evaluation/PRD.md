# PRD — quality-evaluation

Status: Draft

Version: 0.1.0

Domain: [data-dictionary](../../DOMAIN.md)

## Amaç

Geliştirici, cevap kalitesini etkileyen bir değişiklikten — arama ağırlığı, istem (prompt), ölçülmüş
varsayılan ayar ya da sohbet modeli — önce ve sonra kaliteyi aynı sorularla ölçer ve sonucu önceki
ölçümlerle karşılaştırır. Depodaki küçük **altın set** ve **negatif set** backend'in ölçüm betiğiyle
(`python -m app.scripts.evaluate golden`) ölçülür. Kurum içi **büyük referans set** depo dışında
durur ve aynı betiğin `reference` kipiyle ölçülür. Ölçüm istenirse depodaki **ölçüm geçmişine** bir
satır olarak eklenir; böylece değişikliğin kaliteye etkisi aynı değişiklikte görünür. Taşımadan
sonra kaynak uygulamanın ölçülmüş kalitesinin (alan belgesindeki %89,8 ve %90,0) korunduğu da bu
betikle gösterilir.

## Aktörler ve sonuçlar

- **Geliştirici:** Ölçer, sonucu geçmişe ekler, gerileme görürse değişikliği geri alır. Ölçülebilir
  sonuç: aynı sözlük, ayar, kelime listeleri ve modelle, seri çalışan model sunucusunda iki ölçüm aynı
  metrikleri (ölçü değerlerini) verir; her kalite değişikliğinin önce ve sonra satırı geçmiştedir.
- **Proje sahibi:** Yeni modelin, istemin ya da ağırlığın devreye alınmasına geçmiş satırlarına bakarak
  karar verir.
- **Referans set ve gerçek sözlük sahibi:** Büyük referans seti, onu ölçen betikleri ve gerçek sözlüğü
  depo dışından sağlar (Açık soru 1 ve 3).
- **[question-analysis](../004-question-analysis/PRD.md):** Ölçülen analiz akışının sahibidir. Taşımanın
  kaynakla bayt bayt aynı davrandığını kanıtlayan fark testi (kaynak paketle hedefi aynı girdilerle
  yan yana çalıştırıp çıktıları karşılaştıran test), düzeneği ve girdileri orada tanımlıdır.

## Değişmezler ve sınırlar

Decision 1: Ölçüm uygulamanın kendi analiz akışını çağırır (question-analysis'teki kural motoru ve
analist); ölçüm için ayrı bir motor kopyası yazılmaz. Ölçüm kayıtlı cevap okumaz ve yazmaz, geri
bildirim (oy) ağırlıklandırması uygulamaz, analiz kaydı, toplu arama işi ve telemetri sinyali
üretmez, veritabanına yazmaz. Kaynakta da `vsa eval` bunları kullanmıyordu: kayıtlı cevaplar yalnız
web içindi (ADR-035), oylar yalnız web sunucusunda uygulanıyordu.

Decision 2: Ölçüm yalnız geliştirici makinesindeki yerel yığına (yerel Docker Compose ortamı) karşı
çalışır; sözlüğü, terim sözlüğünü, durak kelimeleri, ayarları ve etkin sohbet modelini yerel
veritabanından okur. Nonprod'a karşı çalışmaz. Gerçek sözlük ve referans set CI'a (değişiklik
gönderilince testleri sunucuda çalıştıran denetim) girmez.

Decision 3: Büyük referans set, onun soruları ve beklenen cevapları, koşum çıktıları ve gerçek sözlük
depoya, test verisine ve uygulama günlüğüne girmez. Depoda yalnız küçük altın set, negatif set ve
yalnız metrik taşıyan ölçüm geçmişi durur.

Decision 4: Kör set (`reference_blind.jsonl`, 50 soru) yalnız son kontrol içindir; ağırlık, istem ya
da ayar seçmek için kullanılmaz. İstem örnekleri ölçüm sorularından türetilmez (kaynak ADR-045).

Decision 5: Ölçüm seri yapılır: model sunucusuna aynı anda tek istek gider (1 işçi). Kaynakta paralel
istekler sonucu koşudan koşuya yaklaşık ±2 puan oynatıyordu; seri koşu aynı sonucu veriyordu.

- Altın set ve negatif set maddeleri silinmez, yalnız eklenir (alan değişmezi, Requirement 2).
- Sınırlar: kural sıralamasının, modele giden istemlerin ve analist cevabının kaynakla bayt bayt
  aynı olduğunu gösteren fark testi [question-analysis](../004-question-analysis/PRD.md) PRD'sinde
  tanımlıdır; bu PRD yalnız ölçüm katmanını kaynakla karşılaştırır (Requirement 16). Ölçülmüş
  varsayılan ayarlar ve arama indeksinin kurulması [search-settings](../009-search-settings/PRD.md),
  model bağlantısı, hata sınıfları ve modele erişim [llm-connection](../003-llm-connection/PRD.md),
  gerçek sözlüğün içe aktarılması [dictionary-management](../001-dictionary-management/PRD.md),
  kelime listeleri [vocabulary-management](../002-vocabulary-management/PRD.md) PRD'lerindedir.

## Mevcut davranış

Kaynak: `~/codes/kt-dwhnavigator` (`76e21a3`). Her maddenin sonundaki **Hedefte** notu bilinçli
değişikliktir.

- **Ölçüm** (`src/vsa/evaluation.py` `evaluate`): İki grup vardır: serbest metin talepleri (`mode: ask`)
  ve negatif set. Sohbet modeli bağlıysa (`Engine.analyst_enabled`) talep maddesinde analistin önerdiği
  tablolar sırasıyla (`analyze(q).objects`), negatif maddede analistin sonucu ölçülür. Model yoksa talep
  maddesinde kural motorunun sıralaması (`rank_objects(q)[0]`, analiste verilecek ipuçları), negatif
  maddede kural cevabı (`rule_answer`; yalnız ölçüm içindir, kullanıcıya gösterilmez, ADR-038) ölçülür.
  `scope.exclude_object_prefix` taşıyan madde, adı o önekle başlayan tabloların çıkarıldığı bir
  sözlükte ölçülür (`restricted_engine`, sürüm `-excl-<önek>`; uygulamada böyle bir süzgeç yoktur,
  ADR-001). `mode: batch` maddeleri atlanır (ADR-033). Model bağlı ama sunucu yanıt vermiyorsa her madde
  "Analiz yapılamadı" ile biter ve kaçırılmış sayılır. **Hedefte:** aynı ölçüm (Requirement 3–5); model
  sunucusu baştan denetlenir (Requirement 4); `mode` alanı taşınmaz (Decision 14).
- **Puanlama** (`_score_item`, `_rank`, `EvalReport`): `KS = (1, 3, 5)`, `COLUMN_WINDOW = 5`,
  `TRAP_WINDOW = 3`; bilinmeyen tuzak kuralı `ValueError`. Altın set dosyasının başındaki açıklama
  `primary_object`'in "MRR ve recall@1 için" olduğunu söyler; kod ise ikisini de `expected_objects`'ten
  hesaplar, `primary_object` yalnız madde satırında "birincil" sırası olarak görünür. **Hedefte:**
  formüller aynı (Requirement 5–6); açıklama koda uydurulur (Requirement 1).
- **Komut** (`src/vsa/cli.py` `cmd_eval`, `_print_items`, `_print_negatives`, `_print_delta`):
  `vsa eval` şu seçenekleri alır: `--golden` (varsayılan `tests/golden_set.yaml`), `--negatives`
  (varsayılan `tests/negative_set.yaml`), `--save`, `--label`, `--settings`. Motor diskteki indeksten
  kurulur. Çıktı madde satırları, recall/MRR/kolon satırı,
  negatif satırları, yanlış cevap oranı ve tuzak sayısıdır. `--save` satırı `eval/history.jsonl`
  dosyasına ekler ve dosyada en az iki satır varsa son iki satırın farkını yazar. **Hedefte:**
  `python -m app.scripts.evaluate golden`, aynı çıktı (Requirement 3, 7–9); `--settings` kalkar,
  ayarlar veritabanındadır.
- **Geçmiş** (`append_history`, `read_history`, `_git_commit`): satır `at` (yerel saat, saat dilimsiz),
  `commit`, `label`, `dictionary_version`, `metrics` taşır. Commit, git süreci çalıştırılmadan `.git`
  klasöründen okunur (`docs/GUVENLIK.md` bulgu 12); `.git` bir dosyaysa (ikinci çalışma kopyası,
  worktree) `-` yazılır. Model adı yalnız etikette geçer. Depodaki `eval/history.jsonl` 26 satırdır
  (2026-09-26 → 2026-10-02): ilk satırlar kaldırılmış batch kipinin `batch.*` metriklerini taşır;
  hepsi 2026-10-05 sözlük birleştirmesinden (ADR-037) önceki `0465cc84a7dd-11158` sözlük sürümüyle
  ölçülmüştür; son satır ADR-053'te silinen `catalog_chunks 5` yolunu ölçer. Birleştirilmiş sözlükle
  ölçülmüş satır yoktur. **Hedefte:** yeni dosya boş başlar (Decision 6); `model` alanı eklenir
  (Decision 7).
- **Setler** (`tests/golden_set.yaml`, `tests/negative_set.yaml`): altın sette 9 madde vardır: 8
  talep (`q001`, `q002`, `q003`, `q001-kapsam` [vPRC* hariç kapsam], `q004`–`q007` [kaynağı
  `chat-analiz-2026-09-26`, analist akışının ölçütü olan elle yapılmış analizler]) ve 1 batch
  maddesi (`b001`, atlanır). "Mevcut maddeler silinmez, yalnızca eklenir." kuralı yalnız açıklama
  satırıdır, denetlenmez. Negatif sette 5 sentetik (test için uydurulmuş) madde vardır
  (`n001`–`n005`). **Hedefte:** Requirement 1–2, Decision 14.
- **Testler:** `tests/test_evaluation.py::test_report_metrics` sabit sonuçlarla metrik aritmetiğini
  doğrular. `tests/test_golden.py::test_m1_acceptance` gerçek sözlükle (`data/VeriSozlugu.xlsx`, git'in
  yok saydığı klasörde; yoksa atlanır) ve modelsiz motorla, `chat-analiz-2026-09-26` dışındaki her talep
  maddesinde beklenen tablonun ilk 5'te olduğunu, tuzak ihlali olmadığını ve negatiflerin hepsinin
  BULUNAMADI olduğunu doğrular. **Hedefte:** Requirement 15.
- **Büyük referans set** (`CLAUDE.md` "Golden set" bölümü; `data/golden/`, git'in yok saydığı
  klasör): iki ayrı modelin (Fable ve Opus) bağımsız cevaplarının uzlaşması; `reference.jsonl`
  (100), `reference_extra.jsonl` (95), `reference_hard.jsonl` (99, zor) ve kod dondurulduktan sonra
  yazılan `reference_blind.jsonl` (50). Ölçüm depo kökünden
  `python data/golden/run_eval.py <full|blind|smoke|ids:…> <etiket> 1` komutuyla (`smoke` 10 soruluk
  hızlı settir, son değer işçi sayısıdır), özet `data/golden/final_report.py` ile alınır. İki betik
  de aynı yok sayılan klasördedir; puanlama kuralı depoda görünmez. Ölçümler ekibin DGX Spark
  sunucusundaki LM Studio'da (model çalıştırma programı; paralel istek kapalı) `gemma-4-31b` ile, 1
  işçiyle, soru başına yaklaşık 45 saniyede alınır. Ölçüm anlatımları: ADR-040 (67 soruluk set),
  ADR-042 (294 soru; 101 soruluk ön kontrol), ADR-043 (31 soru), ADR-044 (40 koruma sorusu;
  değişiklik reddedildi), ADR-045 (160 soru; 294'te dürüst tahmin %89,8, sızıntılı sürüm %90,5; kör
  set %90,0; hızlı set 9/10). **Hedefte:** Requirement 11–13, Açık soru 3.
- **Bayt bayt karşılaştırma** (ADR-046, ADR-050, ADR-053): 129 soruda (altın set ve referans setler)
  sözlük çıktısı, kural sıralaması, modele giden istemlerin tamamı ve sahte modelle analist cevabı
  değişiklikten önce ve sonra aynıdır. **Hedefte:** taşımanın bayt bayt kanıtı question-analysis'tedir;
  bu PRD ölçüm çıktısını kaynakla karşılaştırır (Requirement 16).

## İşlevsel gereksinimler

Requirement 1: Setler `app/backend/tests/quality/golden_set.yaml` ve
`app/backend/tests/quality/negative_set.yaml` dosyalarındadır; içerikleri kaynaktaki iki dosyadan
alınır (`b001` maddesi ve `mode` alanı taşınmaz, Decision 14). Altın set maddesinin alanları: `id`
(zorunlu, iki dosya boyunca tekil), `query` (zorunlu), `expected_objects` (en az bir `DB.Şema.Obje`;
herhangi biri doğru sayılır), `primary_object` (isteğe bağlı; yalnız madde satırında "birincil"
sırası olarak gösterilir, metriklere girmez), `expected_columns` (`DB.Şema.Obje.Kolon`), `traps`
(`column` ve `rule`: `not_lead` ya da `caveat`), `scope.exclude_object_prefix`, `notes`, `source`.
Negatif madde `id` ve `query` taşır. Bir biçim testi iki dosyayı doğrular; bilinmeyen alan,
bilinmeyen tuzak kuralı, hatalı anahtar biçimi ve tekrarlanan kimlik testi başarısız kılar. Altın
set dosyasının başındaki açıklama `primary_object`'in gerçek kullanımını yazar.

Requirement 2: Bir test, iki setteki bilinen madde kimliklerinin listesini tutar (başlangıçta 8
altın set maddesi ve 5 negatif madde; Decision 14); listedeki bir kimlik dosyalarda yoksa test
başarısız olur. Yeni madde eklenirken kimliği aynı değişiklikte listeye eklenir.

Requirement 3: Altın set şu komutla ölçülür:
`python -m app.scripts.evaluate golden [--golden YOL] [--negatives YOL] [--save] [--label ETİKET]`;
komut varsayılan olarak Requirement 1'deki dosyaları ölçer. Motoru backend'in kurduğu gibi
kurar: sözlüğü, terim sözlüğünü, durak kelimeleri, ayarları (yönetim ekranında değiştirilmiş değerler
dahil) ve etkin sohbet modelini yerel veritabanından okur, arama indeksini search-settings'teki yolla
bellekte kurar ve analizi question-analysis'teki çekirdek akışla yapar; Decision 1'deki yan etkilerin
hiçbiri olmaz. Sözlük yoksa "Sözlük henüz içe aktarılmadı; ölçüm yapılmadı." yazar ve çıkış kodu 2 ile
biter. Set dosyasında biçim hatası varsa hiçbir analiz yapılmadan çıkış kodu 2 ile biter.

Requirement 4: Etkin sohbet modeli varsa, ilk maddeden önce model sunucusunun yanıt verip vermediği
llm-connection'daki denetimle sınanır; yanıt vermiyorsa "Model sunucusu yanıt vermiyor; ölçüm
yapılmadı." yazılır ve çıkış kodu 2'dir. Sunucu yanıt veriyorsa talep maddesinde analistin önerdiği
tablolar sırasıyla, negatif maddede analistin sonucu ölçülür. Etkin model yoksa talep maddesinde kural
sıralaması, negatif maddede kural cevabı ölçülür (kaynaktaki gibi). Standart çıktının ilk iki satırı
ölçülen yapılandırmayı söyler: "Ölçülen: analist (\<model>)" ya da "Ölçülen: kural sıralaması (model
yok)"; ardından "Sözlük: <sürüm> · değiştirilmiş ayar: <anahtarlar | yok>". Bir maddenin analizi
"Analiz yapılamadı" ile biterse madde kaçırılmış sayılır ve çıktıya "Analiz yapılamadı: N madde
(\<kimlikler>)" satırı eklenir. **Yeni davranış:** kaynak modelin durumunu denetlemiyor ve ölçülen
yapılandırmayı yazmıyordu.

Requirement 5: Her madde kaynaktaki `_score_item` kuralıyla puanlanır. Talep maddesinde: beklenen
tablolardan ilkinin ölçülen listedeki sırası (1'den; yoksa sırasız); `primary_object`'in sırası; ilk 5
tablo anahtarı; ilk 5 tablonun listelenen kolonları arasında bulunan beklenen kolon sayısı; tuzaklar —
`not_lead`, tuzak kolonu ilk 3 tablodan birinin ilk (lider) kolonuysa; `caveat`, tuzak kolonu ilk 5
tablodan birinde kısıt notu olmadan listelenmişse ihlaldir. Negatif maddede: sonuç, en yakın tablo
(önerilerin ya da yakın adayların ilki) adı ve skoru; sonuç BULUNAMADI değilse yanlış cevaptır.
`scope.exclude_object_prefix` taşıyan madde, adı o önekle başlayan tabloların çıkarıldığı sözlükte
ölçülür; bu sözlüğün sürümü `<sürüm>-excl-<önek>`'tir.

Requirement 6: Metrikler kaynaktaki `EvalReport.as_dict` ile aynı ad ve formüldedir:

- `ask.recall@1`, `ask.recall@3`, `ask.recall@5`: sırası k veya daha iyi olan talep maddelerinin talep
  maddelerine oranı (ilk k öneride doğru tablonun bulunma oranı);
- `ask.mrr`: talep maddelerinde 1/sıra değerlerinin ortalaması, sırasız madde 0 sayılır (doğru tablonun
  ne kadar üstte olduğunun ölçüsü);
- `ask.column_recall`: beklenen kolonu olan maddelerde bulunan beklenen kolonların toplamının beklenen
  kolonların toplamına oranı (hiç yoksa 0);
- `ask.n`: talep maddesi sayısı; `trap_violations`: tuzak ihlali toplamı;
- `negative.false_answer_rate`: yanlış cevap veren negatif maddelerin oranı; `negative.n`: negatif madde
  sayısı.

Değerler 4 ondalığa yuvarlanır. Talep maddesi yoksa `ask.*`, negatif madde yoksa `negative.*` metrikleri
yazılmaz; `trap_violations` her zaman yazılır.

Requirement 7: Standart çıktı (stdout), aynı madde sonuçları için kaynaktaki `vsa eval` çıktısıyla
aynıdır. Satırlar sırasıyla:

- başlık `Serbest metin talepleri`;
- her talep maddesi için
  `  <id>: sıra <n|yok> · birincil <n|-> · kolon <x/y|-> · ilk 3: <ad, ad, ad>`;
  ihlal varsa satırın sonuna ` · TUZAK: <ihlaller>` eklenir;
- özet satırı, örnek
  `recall@1=0.88  recall@3=1.00  recall@5=1.00  MRR=0.917  kolon=0.86  (n=8)`;
- başlık `Negatif set (beklenen: BULUNAMADI)`;
- her negatif madde için `  <id>: <sonuç> (doğru|YANLIŞ) · en yakın <ad> <skor> · <soru>`;
- `Yanlış cevap oranı=0.00`; ihlal varsa `Tuzak ihlali: N`.

Kaynağa göre tek ek, Requirement 4'teki satırlardır. İlerleme (örnek `[3/13] q003 · 47 sn`) standart
hata akışına (stderr) yazılır; böylece standart çıktı kaynakla karşılaştırılabilir kalır. Ölçüm
modeli llm-connection'ın portundan `evaluation` amacıyla çağırır (llm-connection Requirement 18);
çağrı özetleri hiçbir yere kaydedilmez, koşumun sonunda standart hata akışına toplam çağrı sayısı,
giriş ve çıkış token toplamları ve başarısız çağrıların hata sınıfına göre sayıları yazılır.

Requirement 8: `--save`, `app/backend/tests/quality/history.jsonl` dosyasına (yoksa oluşturur) bir
satır ekler. Satır UTF-8 (Türkçe karakterleri doğru saklayan metin kodlaması), tek JSON
(yapılandırılmış metin) nesnesidir; anahtarları sırasıyla `at` (UTC, saat dilimi işaretli ISO 8601
zaman, saniye duyarlılığında; örnek `2026-10-08T11:05:12Z`), `commit` (Requirement 10), `label`,
`model` (ölçülen sohbet modeli; kural sıralamasında boş metin), `dictionary_version` ve
`metrics`'tir (altın sette Requirement 6, referans sette Requirement 13). Başka anahtar yoktur;
soru, madde kimliği ve tablo adı satıra girmez. Ardından "Kaydedildi: \<yol> (\<commit>)" yazılır.
Dosyada aynı türden (altın set ya da aynı referans alt kümesi) önceki bir satır varsa "Önceki kayda
göre fark" başlığı altında, iki satırda da bulunan ve `.n` ile bitmeyen her metrik için
`  <anahtar>: <önce> → <sonra> (<±fark>)` yazılır (3 ondalık, kaynaktaki biçim). Yüksek olması iyi
olan bir metrik düştüyse ya da `trap_violations` veya `negative.false_answer_rate` arttıysa satırın
sonuna ` · GERİLEME` eklenir. **Yeni davranış:** kaynak farkı her zaman bir önceki satırla alıyordu
ve gerilemeyi işaretlemiyordu.

Requirement 9: `--save` için `--label` zorunludur (1–200 karakter); yoksa ölçüm başlamadan çıkış kodu
2'dir. Analizi yapılamayan madde varsa sonuç yazılır ama satır kaydedilmez: "Analiz yapılamayan madde
var; ölçüm kaydedilmedi." ve çıkış kodu 2. Ctrl+C koşumu durdurur, geçmişe satır yazmaz ve çıkış kodu
130'dur. Satır dosyaya ya tam yazılır ya hiç yazılmaz; yarım satır kalmaz.

Requirement 10: `commit`, ölçümün yapıldığı çalışma kopyasının commit'inin (değişikliklerin proje
geçmişindeki kalıcı kaydı) ilk 7 karakteridir ve git süreci çalıştırılmadan `.git` klasöründen
okunur: HEAD (çalışma kopyasının o anki konumu) bir dalı gösteriyorsa dalın ayrı dosyasından ya da
git'in dal kayıtlarını toplu tuttuğu `packed-refs` dosyasından; HEAD doğrudan commit'i gösteriyorsa
ondan; `.git` bir dosyaysa (worktree: aynı projenin ikinci çalışma kopyası) içindeki `gitdir`
yolundan. Okunamazsa `-` yazılır. **Yeni davranış:** kaynak ikinci çalışma kopyasında `-` yazıyordu.

Requirement 11: Referans kipi şu komutla çalışır:
`python -m app.scripts.evaluate reference --dir <klasör> --set <küme> --label <etiket>`
ve isteğe bağlı `--workers N`, `--final-check`, `--save`. Klasör kaynaktaki dört dosyayı aynı adlarla
taşır. Küme şunlardan biridir: `full` ilk üç dosya (294 soru), `blind` kör set (50 soru), `smoke`
kaynaktaki 10 soruluk hızlı set (tanımı kaynak koşturucudan alınır), `ids:<kimlik,…>` virgülle
verilen kimlikler. Bilinmeyen kimlik ya da eksik dosya çıkış kodu 2 verir. `--dir` çözümlenmiş
yoluyla depo çalışma kopyasının içindeyse (Windows'ta büyük/küçük harf ayrımı gözetilmeden) "Referans
set klasörü depo dışında olmalı." yazılır ve çıkış kodu 2'dir. `blind`, `--final-check` olmadan
çalışmaz: "Kör set yalnız son kontrol içindir; --final-check ile çalıştırın." ve çıkış kodu 2.

Requirement 12: Referans kipi her soruyu Requirement 3–4'teki akışla ölçer; etkin model yoksa ya da
sunucu yanıt vermiyorsa çıkış kodu 2'dir. İşçi sayısı varsayılan 1'dir; 1'den büyük değer yalnız
`--save` olmadan kabul edilir. Puanlama kuralı ve dosya alanları kaynak koşturucununkidir
(`run_eval.py`, `final_report.py`; Açık soru 3). Kaynaktaki ADR-042…045 anlatımı, cevaplanabilir
soruda birinci önerinin referansın kabul ettiği tablolardan biri olmasının, negatif soruda
BULUNAMADI'nın doğru sayıldığını düşündürür; kesin kural koşturucu kodundadır. Soru başına sonuç
(kimlik, sonuç, ilk tablolar, doğru/yanlış, süre) `--dir` altında zaman damgalı bir dosyaya yazılır;
depoya hiçbir şey yazılmaz. Terminale her soru için yalnız kimlik, doğru/yanlış ve süre yazılır,
soru metni yazılmaz. Sonda doğru/toplam ve yüzde; cevaplanabilir ve negatif sorular ayrı ayrı; dosya
başına sonuç yazılır.

Requirement 13: Referans kipinde `--save` yalnız `full`, `blind` ve `smoke` için çalışır (`ids:` ile
çıkış kodu 2). Satırın `metrics` alanı `reference.<küme>.n`, `reference.<küme>.correct`,
`reference.<küme>.accuracy` (4 ondalık) ve koşturucu negatif soruları ayırıyorsa
`reference.<küme>.negative.n`, `reference.<küme>.negative.correct` taşır. Fark, aynı kümenin önceki
satırıyla alınır (Requirement 8).

Requirement 14: `scripts/quality-eval.sh` sarmalayıcısı (`golden …` ya da `reference …` bağımsız
değişkenleriyle) ölçümü yerel yığının backend ayarları, veritabanı ve ağıyla çalıştırır; böylece
ölçüm uygulamanın eriştiği model sunucusuna aynı yoldan erişir. Bağımsız değişkenleri, çıktıyı ve
çıkış kodunu olduğu gibi geçirir; referans kipinde `--dir` klasörünü ölçüme açar. Geçmiş dosyası ve
`.git` bilgisi geliştiricinin çalışma kopyasından okunur ve yazılır. Windows ve macOS'ta yerel
yığının diğer betikleriyle aynı yoldan çalışır. Yerel yığın çalışmıyorsa "Yerel yığın çalışmıyor;
önce yığını başlatın." yazar ve çıkış kodu 2'dir.

Requirement 15: Kaynaktaki iki test taşınır. Metrik aritmetiği testi (`test_report_metrics`) aynı
sabit sonuçlarla aynı değerleri doğrular. Kabul testi, depo dışındaki gerçek sözlük Excel'inin yolu
`DWHNAVIGATOR_PARITY_DICTIONARY` ortam değişkeniyle verilince (question-analysis'in fark testiyle
aynı değişken) dosyayı dictionary-management'ın içe aktarma ayrıştırıcısıyla okur, motoru modelsiz
kurar ve `source: chat-analiz-2026-09-26` dışındaki her talep maddesinde beklenen tablolardan
birinin ilk 5'te olduğunu, tuzak ihlali olmadığını ve negatif maddelerin hepsinin BULUNAMADI
olduğunu doğrular. Değişken verilmezse test atlanır (CI'da her zaman atlanır).

Requirement 16: Ölçüm çıktısı kaynakla aynıdır: aynı sözlük, ayar ve kelime listeleriyle hedefin
`golden` standart çıktısı (Requirement 4'teki ek satırlar dışında) ve metrikleri, kaynaktaki
`76e21a3` sürümünün `vsa eval` çıktısıyla aynıdır. Karşılaştırma iki yerde yapılır:
question-analysis'te tanımlanan fark düzeneğinin sentetik sözlüğünde, kural sıralaması kipinde ve
sahte modelle analist kipinde (otomatik); gerçek sözlükte kural sıralaması kipinde (yerel). Kural
sıralamasının, istemlerin ve analist cevabının bayt bayt aynılığı bu gereksinimin değil,
question-analysis'te tanımlanan fark testinin konusudur.

## API sözleşmesi

Bu PRD API ucu (sunucunun istek kabul ettiği adres) eklemez; sözleşmesi komut satırıdır. Kullanıcı
hatasında çıkış kodu 2'dir (kaynaktaki gibi), Ctrl+C'de 130.

| Komut | Bağımsız değişkenler | Başarı | Çıkış kodu 2 |
|---|---|---|---|
| `python -m app.scripts.evaluate golden` | `--golden`, `--negatives` (varsayılan Requirement 1 dosyaları), `--save`, `--label` | 0; Requirement 7 çıktısı; `--save` ile geçmiş satırı | sözlük yok; model sunucusu yanıt vermiyor; set dosyasında biçim hatası; etiketsiz `--save`; analizi yapılamayan madde varken `--save` |
| `python -m app.scripts.evaluate reference` | `--dir`, `--set`, `--label`, `--workers` (varsayılan 1), `--final-check`, `--save` | 0; Requirement 12 özeti; sonuç dosyası referans klasöründe; `--save` ile geçmiş satırı | klasör depo içinde ya da dosya eksik; bilinmeyen kimlik; `blind` için `--final-check` yok; model yok ya da yanıt vermiyor; `ids:` ya da `--workers` > 1 ile `--save`; etiketsiz `--save` |
| `scripts/quality-eval.sh golden …` ve `… reference …` | yukarıdakilerle aynı | aynı | ek olarak yerel yığın çalışmıyor |

## Güvenlik ve yetkilendirme

- Betik bir geliştirici aracıdır: yerel yığında backend'in veritabanı bağlantısıyla çalışır, API ve rol
  denetiminden geçmez, veritabanına yazmaz. Nonprod'da çalıştırılmaz; modül backend paketinin parçası
  olduğu için imajda bulunur ama imajda set dosyaları yoktur ve kök dosya sistemi salt okunurdur.
- Model API anahtarı yalnız llm-connection'ın yoluyla bellekte çözülür; çıktıya, geçmişe ve dosyaya
  yazılmaz. Model isteği yalnız llm-connection'ın izin verdiği kurum içi adrese gider.
- Referans klasörünün depo dışında olması betikte denetlenir (Requirement 11); soru başına sonuçlar o
  klasörde kalır; terminale referans soruların metni yazılmaz. Bir test, geçmiş satırlarının yalnız
  Requirement 8'deki anahtarları taşıdığını doğrular.
- Gerçek sözlük Excel'i depo dışında tutulur ve depoya eklenmez; kabul testi onu yalnız verilen yoldan
  okur.
- Betik telemetri (OpenTelemetry) sağlayıcısını başlatmaz; ortamda gönderim adresi tanımlı olsa da ölçüm
  sinyali dışarı çıkmaz.

## Veri ve geçiş

- Veritabanı değişikliği yoktur; betik yalnız okur.
- Kaynaktaki `tests/golden_set.yaml` ve `tests/negative_set.yaml` Requirement 1'deki yere taşınır
  (`b001` taşınmaz, Decision 14).
- Kaynaktaki `eval/history.jsonl` taşınmaz; kaynak deponun `76e21a3` sürümünde başvuru olarak kalır.
  Hedefteki geçmiş, taşıma sonrası ilk ölçümlerle başlar (Acceptance 4–6, Decision 6).
- Büyük referans set ve gerçek sözlük geliştirici makinesinde depo dışında durur; nasıl sağlanacağı
  Açık soru 1 ve 3'tedir.

## Gözlemlenebilirlik

Bu PRD günlük olayı, ölçüm ya da iz (OpenTelemetry sinyali) tanımlamaz; `dwhnavigator_` önekli sinyal
eklemez. Betiğin tek çıktısı standart çıktı, standart hata akışı, geçmiş satırı ve referans klasöründeki
sonuç dosyasıdır.

## Dağıtım etkisi

- Nonprod'a etkisi yoktur: yeni ortam ayarı, sır, chart nesnesi ya da ağ çıkışı eklenmez.
- `scripts/quality-eval.sh` yalnız yerel yığında çalışır. Ölçüm, yerel yığının model sunucusuna
  erişebilmesini gerektirir; bu erişim
  [kubernetes-delivery](../../../application-foundation/PRDs/002-kubernetes-delivery/PRD.md)
  Requirement 17'deki isteğe bağlı yerel çıkış kapısıyla (`app/infra/.env`'de
  `COMPOSE_PROFILES=local-egress`) açılır; adres kuralları [llm-connection](../003-llm-connection/PRD.md)
  PRD'sindedir.
- CI (değişiklik gönderilince sunucuda çalışan otomatik denetim), gerçek veri gerektirmeyen testleri
  (Acceptance 1–3) kalite kapısında çalıştırır; gerçek sözlük
  ya da model isteyen testler atlanır.

## Test stratejisi

- **Birim:** Requirement 1 biçim testi ve Requirement 2 kimlik listesi testi; sahte sıralı listelerle
  puanlama (sıra, birincil sıra, kolon bulma, iki tuzak kuralı, bilinmeyen kural); kapsam öneki
  sözlüğü ve sürüm eki; metrik formülleri ve yuvarlama; standart çıktının kaynaktan üretilmiş sabit
  metinle karşılaştırılması; geçmiş satırının anahtarları ve sırası; aynı türden önceki satırın seçimi
  ve GERİLEME işareti; `.git` okuma (dal, `packed-refs`, doğrudan commit, worktree dosyası, okunamayan
  durum); koruma kuralları (depo içi klasör, `--final-check`'siz kör set, etiketsiz kayıt, `ids:` ve
  çok işçiyle kayıt); sentetik referans dosyalarıyla puanlama ve özet.
- **Gerçek PostgreSQL ve sahte model sunucusuyla:** sentetik sözlüğü yüklenmiş veritabanında iki kipte
  uçtan uca ölçüm; sunucu yanıt vermezken çıkış kodu 2; ölçüm boyunca analiz kaydı, kayıtlı cevap ve
  toplu arama işi oluşmaması, veritabanı satır sayılarının değişmemesi, sahte telemetri alıcısının
  sinyal almaması; analizi yapılamayan maddeyle kaydın reddi; Ctrl+C'de yarım satır kalmaması.
- **Kaynakla fark:** question-analysis'te tanımlanan düzenekte kaynak paket `76e21a3` ile yan yana,
  sentetik sözlükte iki kipte aynı standart çıktı ve metrikler (Requirement 16).
- **Yalnız yerel:** gerçek sözlükle kabul testi (Requirement 15) ve Acceptance 4–6'daki ölçümler.

## Vektör ve gömme sözleşmesi (uygulanabilirse)

- Sağlayıcı / dağıtım sınırı: Uygulanamaz
- Model kimliği ve değişmez sürüm: Uygulanamaz
- Boyut ve normalleştirme: Uygulanamaz
- Uzaklık metriği ve indeks stratejisi: Uygulanamaz
- Getirim kalitesi/duyarlılık ve gecikme eşikleri: Uygulanamaz
- Kaynak sınıflandırması, en aza indirme ve saklama: Uygulanamaz
- Yeniden gömme, geçiş ve geri alma: Uygulanamaz

## Kabul kriterleri

- [ ] Acceptance 1: L1 — Otomatik testlerden geçti: birim testleri Requirement 1, 2, 5–11 ve 13'ü
  sentetik (test için uydurulmuş) verilerle doğrular; metrik aritmetiği testi kaynaktaki değerleri
  verir (Requirement 15).
- [ ] Acceptance 2: L1 — Otomatik testlerden geçti: gerçek PostgreSQL ve sahte model sunucusuyla
  Requirement 3, 4, 9 ve 12 doğrulanır; ölçüm boyunca veritabanına yazılmadığı, analiz kaydı ve kayıtlı
  cevap oluşmadığı ve telemetri sinyali çıkmadığı gösterilir (Decision 1).
- [ ] Acceptance 3: L1 — Otomatik testlerden geçti: question-analysis'te tanımlanan fark düzeneğinde
  kaynak paket `76e21a3` ile yan yana, sentetik sözlükte kural sıralaması ve sahte modelli analist
  kiplerinde standart çıktı ve metrikler aynıdır (Requirement 16).
- [ ] Acceptance 4: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da (geliştirici
  makinesindeki Docker ortamı) gerçek sözlük içe aktarılmış, etkin model yokken
  `scripts/quality-eval.sh golden` kural sıralamasını ölçer; standart çıktısı ve metrikleri aynı
  sözlükle çalıştırılan kaynak `vsa eval` (`76e21a3`) ile aynıdır; `DWHNAVIGATOR_PARITY_DICTIONARY`
  verilerek çalıştırılan kabul testi geçer (Requirement 14–16).
- [ ] Acceptance 5: L2 — Gerçek istemci/ortamda doğrulandı: yerel Compose'da gerçek sözlük ve
  kaynağın ölçüm modeliyle (Açık soru 2) ve kaynaktan taşınan koşturucuyla (Açık soru 3), seri
  çalışmada `golden --save --label "taşıma tabanı"` iki kez aynı metrikleri verir;
  `reference --set smoke` ve `reference --set blind --final-check --save` çalışır ve kör set sonucu
  kaynaktaki ölçümle aynıdır (50 soruda 45 doğru, %90,0); koşumdan sonra çalışma kopyasında yalnız
  `history.jsonl` değişmiştir, referans çıktıları depo dışındadır (Requirement 8, 11–13, Decision
  3).
- [ ] Acceptance 6: L2 — Gerçek istemci/ortamda doğrulandı — nonprod modeli: nonprod'da
  etkinleştirilecek sohbet modeli kullanıcılara açılmadan önce yerelde aynı gerçek sözlükle altın
  set ve kör setle ölçülür; sonuçlar model adıyla geçmişe yazılır ve proje sahibine sunulur (alan
  değişmezi: model değişikliği önce ölçülür).

## Kararlar

- Decision 6: Ölçüm geçmişi depoda, `app/backend/tests/quality/history.jsonl` dosyasında tutulur ve
  boş başlar; kaynağın geçmişi kopyalanmaz. Gerekçe: geçmiş yalnız metrik taşır, kurum içi veri
  değildir; ölçüldüğü değişiklikle aynı commit'te (proje geçmişindeki aynı kayıtta) durması
  incelemede önce/sonra farkını gösterir. Kaynak satırları başka deponun commit'lerini, kaldırılmış
  batch kipinin metriklerini, birleştirmeden önceki sözlük sürümünü ve silinmiş bir kod yolunu
  ölçer; hedefin ölçümüyle karşılaştırılamaz. Dosya setlerle aynı klasördedir; ölçümün girdisi ve
  kaydı bir arada durur.
- Decision 7: Geçmiş satırına `model` alanı eklenir, `at` UTC olarak saat dilimi işaretiyle yazılır
  (alan değişmezi: zamanlar UTC saklanır), referans ölçümleri
  aynı dosyaya `reference.<küme>.*` metrikleriyle girer. Gerekçe: model değişikliği ölçümün ana
  sebeplerinden biridir ve kaynakta yalnız serbest etikette geçiyordu; kural sıralaması ile analist
  ölçümü (model boş/dolu) karışmaz. Referans sonuçları da önce/sonra karşılaştırmasının parçasıdır.
- Decision 8: Geçmişin güvenilirliği için etiket zorunludur; analizi yapılamayan maddesi olan koşum,
  çok işçili koşum ve `ids:` alt kümesi kaydedilmez; fark aynı türden önceki satırla alınır ve gerileme
  işaretlenir. Gerekçe: zaman aşımına uğrayan birkaç madde ya da paralel çalışma, değişiklikten
  bağımsız bir düşüş gibi görünür; kaynakta tek dosyada farklı türlerin ardışık satırları anlamsız fark
  üretirdi. Geri alma kararı geliştiricinindir; işaret yalnız dikkat çeker.
- Decision 9: Ölçüm, yerel yığının backend ayarları, veritabanı ve ağıyla çalışır. Gerekçe: yerel
  veritabanı makineye açık değildir; ölçüm, uygulamanın kullandığı model sunucusuna aynı yoldan
  erişmelidir. Nonprod'da kök dosya sistemi salt okunurdur ve kurum içi referans verisini kümeye taşımak
  gereksizdir.
- Decision 10: Referans klasörünün depo dışında olması betikte zorunludur; soru başına sonuçlar o
  klasöre yazılır, terminale soru metni yazılmaz. Gerekçe: kurum içi soruların yanlışlıkla depoya ya da
  ekran kaydına girmesi önlenir.
- Decision 11: Model sunucusu ölçümden önce denetlenir ve ölçülen yapılandırma çıktının başında yazılır.
  Gerekçe: kaynakta yanıt vermeyen sunucu her maddeyi kaçırılmış gösteriyor, bu da gerçek bir gerileme
  gibi okunabiliyordu.
- Decision 12: Setler `app/backend/tests/quality/` altındadır. Gerekçe: ölçüm betiği ve kabul testi
  backend'in parçasıdır; yerel yığının backend'i bu klasörü görür, çalışma imajı görmez.
- Decision 13: Kaynakla karşılaştırma bu PRD'de ölçüm çıktısı düzeyindedir; bayt düzeyindeki fark
  testi question-analysis'te tanımlıdır. Gerekçe: aynı kanıt iki PRD'de tekrarlanmaz; ölçüm katmanının
  taşınması (puanlama, metrik, çıktı, geçmiş) ayrıca doğrulanmalıdır.
- Decision 14: Kaldırılmış batch kipine ait `b001` maddesi ve `mode` alanı hedef sete alınmaz; madde
  kaynak deponun `76e21a3` sürümünde kalır. "Maddeler silinmez, yalnız eklenir" kuralı (alan
  değişmezi) hedef setteki ölçülebilir maddeler için geçerlidir. Gerekçe: madde ADR-033'ten beri
  ölçülmüyor; hedefe almak, ölçüm betiğinde kaldırılmış bir kipi tanıyıp atlayan kod bırakmak demektir.

## Açık sorular

1. **Gerçek sözlük kimden ve nasıl alınacak?** Ölçüm ve kabul testi gerçek sözlüğü (kaynakta
   `data/VeriSozlugu.xlsx`, yaklaşık 11 bin kolon) gerektirir; dosya kurum içi veridir, depoda ve
   sunucudaki otomatik testlerde (CI) yoktur. Öneri: dosyayı kaynak uygulamanın geliştiricisi Git
   dışındaki kurum içi güvenli bir kanalla versin; geliştirici makinesinde depo dışındaki bir
   klasörde dursun, yerel yığına Sözlük sayfasından içe aktarılsın ve içe aktarılan sözlüğün sürümü
   taşıma tabanının geçmiş satırında yazsın.
2. **Ölçüm hangi model sunucusu ve modelle yapılacak, geliştirici makinesi ona nasıl erişecek?**
   Kaynağın %89,8 ve %90,0 sonuçları ekibin DGX Spark sunucusundaki LM Studio'da (model çalıştırma
   programı) `gemma-4-31b` ile seri çalışmayla alındı; nonprod ise kurum içi RunAI (model çalıştırma
   hizmeti) ucunu
   (`https://runai.gpudtx.kuveytturk.com.tr/inference/qwen36-35b-a3b-fp8/v1`) kullanıyor ve bu model
   kaynakta hiç ölçülmedi. Öneri: taşıma tabanı kaynağın ölçüm ortamıyla (DGX LM Studio,
   `gemma-4-31b`, paralel istek kapalı) alınıp kaynakla karşılaştırılsın (Acceptance 5); nonprod
   modeli kullanıcılara açılmadan önce aynı setlerle ayrıca ölçülsün (Acceptance 6). DGX'e erişim
   bilgisi ve ağ izni ile RunAI ucunun istekleri sırayla mı paralel mi işlediği ekipten öğrenilsin;
   bilinmiyorsa RunAI ölçümü iki kez alınıp sonuçların aynı olduğu doğrulansın.
3. **Büyük referans set ve onu ölçen betikler kimden, nasıl alınacak; koşturucu kodu depoya taşınsın
   mı?** `run_eval.py` ve `final_report.py` kaynakta git'in yok saydığı veri klasöründe durduğu için
   puanlama kuralı depoda görünmüyor; hedefte koşturucu kaynaktaki `vsa` paketini değil yeni backend'i
   çağırmak zorunda. Öneri: dört referans dosyası kaynak geliştiriciden Git dışındaki kurum içi güvenli
   bir kanalla alınıp depo dışında tutulsun; iki betiğin kodu (veri olmadan) Requirement 11–13'teki
   `reference` kipine taşınsın ve sentetik referans dosyalarıyla CI'da test edilsin; betikler
   alınamazsa puanlama kuralı yeniden yazılıp proje sahibinin onayına sunulsun.
4. **Önce/sonra ölçümü otomatik denetlensin mi?** Alan değişmezi ağırlık, istem ve model
   değişikliğinin önce ve sonra ölçülmesini istiyor; gerçek sözlük ve model sunucudaki otomatik
   denetimde (CI) olmadığı için ölçüm yalnız geliştiricinin elinde. Öneri: kalite kapısı, çekirdek
   motorun, istemlerin ya da ölçülmüş varsayılan ayarların dosyaları değişen bir değişiklikte
   `history.jsonl`'e en az bir yeni satır eklenmesini istesin, eklenmemişse başarısız olsun. Yönetim
   ekranından yapılan model değişikliği bu denetimin dışında kalır; onun için Acceptance 6'daki
   kural geçerlidir.

## Teslim akışı

Belirtim → Plan → Görevler → Uygulama ([Plan](plan.md), [Görevler](tasks.md)).

## Riskler

- **Ölçüm geliştiriciye bağlı:** Gerçek sözlük ve model sunucudaki otomatik denetimde (CI)
  olmadığından ölçüm atlanırsa gerileme fark
  edilmeden geçebilir (Açık soru 4).
- **Ölçülmemiş nonprod modeli:** Nonprod'daki model kaynakta hiç ölçülmedi; kalite %89,8'in altında
  kalabilir (Acceptance 6).
- **Koşturucu kodu yok:** Kaynak betikler alınamaz ve puanlama kuralı yeniden yazılırsa hedefin
  sonuçları kaynağın %89,8 ve %90,0'ıyla doğrudan karşılaştırılamaz.
- **Süre:** Seri ölçüm uzundur; soru başına yaklaşık 45 saniyeyle 294 soru yaklaşık 3,7 saat, kör set
  yaklaşık 40 dakika, hızlı set yaklaşık 8 dakika, küçük altın set (13 madde) yaklaşık 10 dakika sürer.
- **Paylaşılan model sunucusu:** Ölçüm sırasında aynı sunucuyu kullanan kullanıcılar yavaşlar; istekleri
  paralel işleyen bir sunucu sonucu koşudan koşuya oynatabilir.
- **Küçük set zayıf:** Altın sette 8 talep maddesi vardır; recall@1 (birinci öneride doğru tablo
  oranı) her maddede 0,125 oynar. Kalite
  kararları büyük setle verilmelidir.
- **Bayatlayan beklentiler:** Altın setin beklenen tabloları belirli bir sözlük sürümüne göre yazıldı;
  sözlük değişince beklentiler eskiyebilir ve maddeler silinemediği için düzeltme ayrı karar ister.
- **Geçmiş dosyasında çakışma:** İki dal aynı dosyanın sonuna satır eklerse birleştirmede çakışma olur;
  iki satır da zaman sırasıyla korunarak çözülür.
- **Dağınık kurum verisi:** Gerçek sözlük ve referans set geliştirici makinelerinde depo dışında durur;
  bu kopyaların erişim denetimi depo dışındadır.
