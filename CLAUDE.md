# CLAUDE.md — Veri Sözlüğü Asistanı (VSA)

Tam spesifikasyon: `docs/HANDOVER.md`. Tasarım sorularında önce orayı oku; bölüm
numaralarıyla (§8, ADR-005 vb.) atıf yap.

## Ne yapar
İş biriminin doğal dildeki veri talebini, veri sözlüğüne (11.158 kolon, 389 obje) karşı
arar ve **tablo seviyesinde**, gerekçeli, güven skorlu öneriler içeren Excel raporu üretir.
LLM açıkken `ask` cevabını **analist akışı** yazar (ADR-029, `llm/analyst.py`): model önce tüm
tablo kataloğundan aday seçer, sonra adayların bütün kolon açıklamalarını okuyup raporu yazar
(öneriler, kurgu, dikkat, notlar). Kural motoru yalnız ipucu ve doğrulayıcıdır (ADR-038). **Tek akış
budur** (ADR-033): toplu arama da bir Excel listesinin her terimini bu akıştan geçirip tek
rapor üretir; hedef tablo (batch) modu, LLM hakem ve LLM sorgu genişletme kaldırıldı. Hedef: kullanıcının
Claude chat'te elle yaptırdığı analizlerle (`out/VSA_Analiz_*.xlsx`, golden q004–q007) aynı kalite.
Kapalı ağda çalışır; hiçbir dış adrese çıkmaz. Modeller kurum içi sunucularda (DGX Spark, ADR-031);
bulut desteği ve model laboratuvarı kaldırıldı.

## Çekirdek kurallar (pazarlıksız)
- **Obje seviyesine toplama** (`scoring/aggregate.py`, §8, ADR-005): arama kolon
  seviyesinde, cevap tablo seviyesinde. Refaktörlerde korunur.
- **Var olmayan alan önerilmez** (`validate.py`, ADR-002): her (obje, kolon) sözlüğe
  karşı doğrulanır; LLM tabloyu yalnızca aday id'siyle seçer. Analist akışında modelin yazdığı
  her metin `MentionChecker` ile taranır; sözlükte olmayan tablo/kolon adı geçen cümle silinir.
- **"Bulunamadı" geçerli cevap** (ADR-006): eşik altı aday gösterilmez, liste doldurulmaz.
- **Cevabı yalnız analist yazar** (ADR-038, ADR-008'in yerine): model yoksa/ulaşılamıyorsa/çalışamazsa
  sonuç "Analiz yapılamadı" + sebep; kural cevabı kullanıcıya gösterilmez (`Engine.rule_answer`
  yalnız ölçüm ve testler için).
- **Kapsam filtresi koda gömülmez** (ADR-001): kapsam sözlük dosyasıyla yönetilir.
- Sorgu genişletme yalnızca BM25 koluna uygulanır (ADR-004).

## Kodlama standartları
- Python 3.11+, tip ipuçları zorunlu, `ruff` + `mypy --strict` temiz.
- **Hiçbir modülde doğrudan `.lower()` / `.upper()` / `.casefold()` çağrılmaz** —
  `vsa.text.normalize` kullanılır (Türkçe İ/ı sorunu).
- I/O yalnızca `loader.py`, `index/store.py`, `report/`, `cli.py` içinde (+ `Engine.from_*`
  kurucuları); diğer modüller saf fonksiyon.
- Her yeni skorlama kuralı bir testle gelir.
- Kullanıcıya dönük metin (rapor, gerekçe) **Türkçe**; kod, değişken adı, commit **İngilizce**.

## Veri
- Sözlük: `data/VeriSozlugu.xlsx` — tek kaynak (2026-10-05'te DataDictionary-Final + ObjectNameList
  birleştirildi, eskiler kaldırıldı). Yalnız iki sayfa: `Objeler` (ObjectKey, ad, ObjectDescription,
  Grain, KeyColumns, TimeColumns, BusinessDomain, DatasetGroup) ve `Kolonlar`
  (DatabaseName, SchemaName, ObjectName, ColumnName, ColumnDescription, Synonyms, Role, Summary;
  KVKK bayrağı açıklamadan türetilir; DatasetGroup Objeler'den `DB.Şema.Obje` ile gelir).
  Role ∈ {Anahtar, Kod, Ad, Zaman, Ölçü, Bayrak, Metin}; Summary ≤70 karakter sıkıştırılmış anlam
  ("Cari hesap bakiyesi · TL · son 12 ay ortalama"), LLM'e uzun açıklama yerine verilmek için. Kalite sayfası yok (`quality_sheet` boş); yükleyici isteğe bağlı olarak hâlâ okuyabilir.
- `vsa catalog` → `data/VeriSozlugu.objeler.jsonl` (Objeler sayfasından LLM tablo kataloğu).
  Sözlük değişince `vsa index` ve `vsa catalog`.
- `data/`, `out/` ve tüm `.xlsx` dosyaları gitignore'da — **kurum içi veri, asla commit edilmez**.
  Testler gerçek sözlüğe ihtiyaç duyarsa sözlük yoksa `skip` etmeli.
- Eski kaynakta kolon `DAtabaseName` yazım hatalıydı; yükleyici her iki yazımı kabul eder.
- Obje/kolon adları kırpılmış (ambarda 55 kolonun adında sonda boşluk var; SQL'de dikkat). Yükleyici yine `strip` eder.

## Yeni kararlar
`docs/DECISIONS.md`: ADR-009 (müşteri no = hesap no), ADR-010 (zaman/granülerlik yalnız obje
skorunda), ADR-011 (uygulanamayan bileşen ağırlıktan çıkar), ADR-012 (kolon skoru tabanı),
ADR-013 (IDF ağırlıklı kapsama + cevap eşiği), ADR-014 (uzun format kırılım), ADR-015 (obje havuzu),
ADR-016/017 (batch modu — ADR-033 ile kaldırıldı), ADR-018/019 (yerel model, hibrit arama — vektör araması 2026-10-05'te kaldırıldı),
ADR-020..022 (web, hakem ve ağırlıkları — hakem ADR-033 ile kaldırıldı), ADR-023 (Keşfet araması), ADR-024 (Evren arayüzü),
ADR-025/026 (model laboratuvarı ve bulut modelleri — ADR-031 ile kaldırıldı),
ADR-027 (tek ekran, tek görünüm: yalnız soru sorma, Evren), ADR-028 (tablo seviyesinde
konu uyumu: tablo BM25), ADR-029 (analist
akışı: LLM katalogdan aday seçer, adayların kolonlarını okuyup raporu yazar; kurallar doğrular), ADR-030 (`/admin`: ayarlar + analiz izleri, bağlantısız ve korumasız), ADR-031 (modeller kurum içinde; lab ve bulut kaldırıldı), ADR-032 (LLM entegrasyonları ekranı: sunucu + sohbet rolü, test, envanter, aktif/pasif; sade üç sayfalık ayarlar), ADR-033 (tek akış: tek soru + onu kullanan Excel listesi; batch, hakem, LLM genişletme, `--compare` kaldırıldı). ADR-034 (cevabı kim yazdı her yerde yazılır; ölü sunucu beklenmez; kural cevabı artık gösterilmez, ADR-038). ADR-035 (önceki cevaplar: analist cevabı `data/cache/answers.jsonl`'de saklanır; aynı soru ya da terim sözlüğüne göre aynı kavram kümesi → kayıtlı cevap; sözlük/model/ayar parmak izi değişince geçersiz; yalnız web, `vsa ask`/`eval` etkilenmez). ADR-036 (geri bildirim cevabı şekillendirir: tablo ve cevap 👍/👎 + gerekçe; kişi başı son oy, aynı soru 1,0 / aynı anlam 0,6, 180 gün yarılanma; ≈2 kişi 👎 → tablo önerilerden çıkar ama görünür kalır, güven ±%15, doğrulanan yakın aday eklenir; cevap 👎 çoğunluğu kayıtlı cevabı siler; yalnız ekranda, Excel değişmez; `feedback.assess/apply`). ADR-037..040 `docs/DECISIONS.md`'de: tek konsolide sözlük, analist
tek yol, vektör kaldırıldı, kompakt analist malzemesi (Objeler kataloğu + `Ad [Rol]: özet`).

## Golden set
`tests/golden_set.yaml` — maddeler silinmez, yalnızca eklenir. Ağırlık değişikliğinden
önce ve sonra `vsa eval` çalıştırılır; regresyon varsa değişiklik geri alınır.
Büyük referans set (kurum içi veri, `data/golden/`, gitignore'da): 100 soru, Fable ve Opus'un
bağımsız cevaplarının uzlaşması (`merge_oracles.py` → `reference.jsonl`, `reference_golden.yaml`,
`reference_negative.yaml`). Ölçüm: `vsa eval --golden data/golden/reference_golden.yaml
--negatives data/golden/reference_negative.yaml` (model açıkken analist akışını ölçer).

## Sözlükte dokümanda olmayan ayrıntılar
- Yükleyici baştaki `[...]` bayraklarını hâlâ tanır (`MODEL TAHMİNİ` ×0.85, diğerleri not), ama
  güncel sözlükte bayrak yoktur. Metin ortasındaki `[...]` formül olabilir, bayrak değildir.
- `vCampaign` iki şemada (CFM, CMP) var → obje anahtarı her zaman `DB.Şema.Obje`.
- Tekrar kolon yok (yükleme 0 uyarı, 0 bayrak).
- Kolonlar sayfasındaki tüm açıklamalar doğrulanmış kabul edilir (2026-10-05 kararı): baştaki
  `[...]` bayrak ve süreç notu ("kaynakta hatalıydı", "doğrulanmalı" vb.) yoktur, eklenmez.
  Sözlükte süreç/tarihçe sayfası tutulmaz.

## Komutlar
Sanal ortam `.venv/` (Windows: `.venv\Scripts\python`).
```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy src
vsa index
vsa ask "kredi kartı limit doluluk oranı"
vsa ask -i terimler.xlsx               # ilk sütundaki her terim ayrı aranır, tek rapor
vsa eval --save --label "ne değişti"   # ağırlık değişikliğinden önce/sonra
```
Stopword veya terim sözlüğü değişirse `vsa index` yeniden çalıştırılmalı (BM25 indekse gömülü).

## Yol haritası durumu
- [x] M1 — LLM'siz çekirdek (normalize, loader, BM25, genişletme, kural skoru, toplama, ask Excel)
      Kabul: golden set recall@5 = 1.00 (3/3). `vsa eval` M2'den önce de çalışıyor.
- [x] M2 — Değerlendirme: `vsa eval` (ask + negatif grupları, kolon isabeti, tuzaklar),
      `--save` → `eval/history.jsonl`. Golden set küçük (8 ask); `mode: batch` maddesi (b001)
      dosyada kalır ama atlanır (ADR-033).
- [-] M3 — Hibrit arama: vektör araması kaldırıldı (2026-10-05); arama yalnız BM25.
      Eski `settings.yaml` / `llm_integrations.yaml` içindeki `dense:` ve embedding alanları yok sayılır.
- [x] M4 — LLM katmanı: hakem ve LLM sorgu genişletme yerini analist akışına (M8) bıraktı,
      ADR-033 ile kaldırıldı. `reasoning_effort: none` ve seed korunuyor.
- [x] M5 — Toplu arama (ADR-033): tek sütunlu Excel listesi, her terim tek soru akışından,
      tek birleşik rapor (Özet · Öneriler · Alan Detayları · Notlar, terim sütunlu). Arayüzde
      arka plan işi (ilerleme, durdurma, ara rapor), CLI'da `vsa ask -i`. Eski hedef tablo modu
      (ADR-016/017) kaldırıldı.
- [x] M6 — Arayüz: `vsa serve` / `baslat.bat` → http://127.0.0.1:8765. Tek ekran (soru sorma),
      tek görünüm: Evren (galaksi, ADR-024/027). Arama çubuğunda Excel'den toplu arama. Stdlib sunucu +
      `src/vsa/web/static/index.html` (tek dosya, dış kaynak yok). Ayarlar ve analiz izleri yalnız `/admin`
      (`admin.html`, ADR-030/032: Yapay zekâ · Arama ve cevap · Veri ve bakım); uygulamadan bağlantı yok. **Tasarım kararları
      Claude'da** (kullanıcı "beni şaşırt" dedi); seçenek menüsü sunma.
- [~] M7 — Geri bildirim: 👍/👎 → `data/feedback.jsonl` → `vsa feedback` golden adayları.
      Oylar sonraki cevaplara yansır (ADR-036); arayüzde "Bir bakışta" panosu ve kapsama matrisi.
      Eş anlamlı zenginleştirme akışı henüz yok.
- [x] M8 — Analist akışı (ADR-029): `ask` cevabını LLM yazar (katalog → aday → kolon okuma →
      rapor), kurallar ipucu/doğrulayıcı/yedek. Excel ve arayüz chat analizlerinin biçiminde
      (Kapsadığı Bilgi, Önerilen Kurgu, Dikkat, Uyarı/Netleştirme/Top 5 dışı notları).
      Soru başına ~2-4 dk bulutta ölçüldü (katalog ~70k token); üretimde DGX Spark + vLLM önek önbelleği.
      `vsa eval` model açıkken analist cevabını ölçer. Aile araması + kavram kanıtı (v2).
      Sıradaki: deterministik skor, yapılandırılmış ayrıştırma (METODOLOJI_KARSILASTIRMASI.md).

## Model ortamı
Modeller ekibin DGX Spark sunucularında, OpenAI uyumlu API ile (ADR-031); bu makinede model
çalıştırılmaz, `baslat.bat` LM Studio açmaz. Bağlantı `/admin` → Ayarlar → Yapay zekâ ekranından
(ADR-032): entegrasyonlar `config/llm_integrations.yaml` (repoda yok, API anahtarı içerir). Dosya
yoksa `config/settings.yaml` → `llm:` geçerli. Analist okuma ayarları (aday sayısı, `detail_columns`,
`catalog_chunks`, `catalog_columns`) `/admin` → Arama ve cevap → Analist'te. Model
değişikliğinden önce ve sonra `vsa eval --save`.
