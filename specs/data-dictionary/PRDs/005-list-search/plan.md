# Plan — list-search

[PRD](PRD.md) belgesinden türetildi (`Status: Accepted`, 1.0.0). Uygulama üç parçadır: kaynaktan
taşınan saf okuma kuralları ve liste raporu (fark testiyle), listelerin kalıcı tabloları ile süreçteki
liste işi (yükleme, terimlerin analiz sırasına tek tek verilmesi, durdurma, sürdürme, yarıda kesilme)
ve uçları, ön yüzdeki liste arayüzü.

## Katmanlar ve dosyalar

| Katman | Dosyalar | Requirement |
|---|---|---|
| Alan | `app/backend/app/domain/term_lists.py` (liste ve terim durumları, ret kodları, `TermListRejected`, 5 liste, terim hata kodu ve güvenli iletisi), `domain/analysis.py` (`ListItem`, `ListResult`) | 3, 7, 16, 18 |
| Okuma | `services/analysis/loader.py` (`parse_term_sheet`, `load_term_list`: ortak güvenli okuyucuyla bellekte, her sayfada 2.001 satır ve 50 sütun) | 1-3, 19, Decision 9, 10 |
| Rapor | `services/analysis/report/excel.py` (`write_list_report`, `_list_summary`, `_list_suggestions`, `_item_state`; bayt döndürür) | 13, Decision 10 |
| Kalıcılık | `domain/models/term_list.py` (`TermList`, `TermListItem`), `infrastructure/repositories/term_list_repository.py` | 4, 6, 15, 16, Veri ve geçiş |
| Göç | `schema/alembic/versions/202610090003_term_lists.py` | Veri ve geçiş |
| Liste işi | `services/term_lists.py` (`TermLists`: yükleme, arka plan görevi, `AnalysisJobs.start(origin=list, list_term=...)`, durdurma, sürdürme, kapanış, açılış ve dakikalık denetim, anlık durum, listeleme, terim cevabı ve raporlar) | 4-16, 18, Decision 2-8, 13, 14 |
| Analiz sırası | `services/analysis/jobs.py` (liste terimi tek soru kuyruk sınırına takılmaz; `present` ile terim cevabına oy uygulaması) | 5, 12 |
| API | `api/term_lists/router.py`, `schemas/term_lists/lists.py` | 2-4, 7-9, 12-15, API sözleşmesi |
| Uygulama | `app/main.py` (süreçteki tek liste yöneticisi; açılış ve dakikalık denetim görevi; kapanışta önce işler, sonra listeler) | 10, 11 |
| Gözlemlenebilirlik | `core/telemetry.py` (altı ölçüm, sabit etiket kümeleri), `app.lists` olayları | Gözlemlenebilirlik |
| Sözleşme | `specs/openapi/dwhnavigator-api.yaml`, `app/frontend/src/types/api.d.ts` | API sözleşmesi |
| Ön yüz | Liste arayüzü, hap, yoklama, `tr.json` | 17 |

## Kararların uygulaması

- Decision 3 ve Requirement 4: Kurumda tek çalışan liste, `term_list` tablosunda yalnız `running`
  satırlarına uygulanan kısmi benzersiz dizindir (`uq_term_list_one_running_per_tenant`). Yükleme
  önce gövdeyi okur (413, 415), sonra çalışan listeye bakar (409, dosya ayrıştırılmadan), sonra
  dosyayı okur (422); aynı anda gelen iki yüklemeden ikincisini dizin 409'a çevirir. İleti, çalışan
  liste isteği yapanınsa ya da başkasınınsa kaynaktaki iki metindir.
- Decision 4 ve Requirement 5: Liste görevi terimi `AnalysisJobs.start` ile analiz sırasına verir
  (`origin=list`, `top=5`, `fresh=false`, liste kimliği, dosya adı ve sıra) ve işin son durumunu
  bekler; sonraki terim ancak o zaman sıraya girer. Liste terimi tek soruların kuyruk sınırına
  takılmaz (question-analysis Requirement 9 c); böylece bir tek soru en çok çalışan terimi bekler.
- Requirement 6 ve Decision 5: Terim bitince cevap tek işlemde yazılır; cevap analiz kaydının tam
  cevabıyla aynı biçimdedir (question-analysis Requirement 18: kayıtlı cevap biçimi, her kolonun
  sözlük satırı içinde), bu yüzden terim ayrıntısı ve raporlar sonraki içe aktarmalardan sonra da
  açılır.
- Requirement 8: Durdurma `stop_requested`'i yazar, görevin durdurma işaretini kurar ve çalışan
  terimin işini `AnalysisJobs.cancel` ile keser (model bağlantısı kapanır); terim sıraya verilirken
  gelen durdurma da işi hemen keser. Uç, listenin görevi bitene kadar en çok 5 saniye bekler.
- Requirement 9: Sürdürme, cevabı olmayan (durdurulmuş, yarıda kesilmiş, hatalı) terimleri dosya
  sırasıyla yeniden sorar; "Analiz yapılamadı" cevabı cevaptır. Bir koşu içinde hatalı terim yeniden
  denenmez (kaynaktaki tek geçiş).
- Requirement 7 ve 9: Geçen süre `elapsed_before_ms` (önceki dilimler) ile süren dilimin
  `run_started_at`'ten bu yana geçen süresidir; duraklama sayılmaz.
- Requirement 10 ve Decision 2: Kapanışta önce analiz işleri `interrupted` olur, liste görevi bunu
  görüp listeyi `interrupted` yazar (sebep `shutdown`); açılışta bu süreç başlamadan önce başlamış
  `running` listeler, çalışırken de görevi bu süreçte olmayan `running` listeler her dakika
  `interrupted` olur (sebep `startup`, `check`). Ölmüş bir sürecin son diliminin sonu listenin son
  yazıldığı andır. Hiçbir liste kendiliğinden sürdürülmez.
- Requirement 12: Terim ayrıntısı saklanan cevaptan Requirement 7 biçimine çevrilir ve
  question-analysis'in `present` noktasından (answer-feedback oyları) geçer; terim raporu aynı
  cevaptan `write_ask_report` ile üretilir.
- Requirement 13 ve Decision 10: Liste raporu kaynağın `write_list_report`'udur; yarıda kesilen
  liste durdurulmuş liste gibi yazılır; "Üretim" ve dosya adındaki zaman İstanbul saatidir;
  "Kaynak sözlük" `dictionary.jsonl` ve listenin başladığı andaki sürümdür.
- Requirement 16 ve Decision 14: Yeni liste aynı işlemde yazılırken sahibin en yeni 5 listesi
  dışındakiler terimleriyle kalıcı silinir; analiz kayıtları kalır.
- Requirement 18: Beklenmeyen hatada terim `term_analysis_failed` koduyla ve kaynaktaki güvenli
  Türkçe iletiyle kalır; istisna metni hiçbir yere yazılmaz, günlükte yalnız hata sınıfı vardır.

## Doğrulama

- Backend: `scripts/quality-gate.sh all`.
- Fark testi: `tests/parity/test_term_lists_parity.py` (okuma ve liste raporu; kaynak anlık
  görüntüsü `term_lists.json`), yeniden kurma `python -m tests.parity.harness --verify-snapshot`.
- Sözleşme: `scripts/export-openapi.sh --check`, `scripts/generate-types.sh --check`.

## İzlenebilirlik

| Requirement | Test |
|---|---|
| 1-3 | `tests/unit/analysis/test_term_lists.py`, `tests/parity/test_term_lists_parity.py`, `tests/integration/test_term_lists_api.py` (`test_term_list_rejects_bad_files`) |
| 4 | `tests/integration/test_term_list_runs.py` (`test_only_one_list_runs_in_the_tenant`), `tests/integration/test_term_lists_api.py` (`test_a_list_is_its_owners_alone`, `test_two_uploads_at_once_start_one_list`) |
| 5, 6 | `tests/integration/test_term_list_runs.py` (`test_terms_go_one_at_a_time_in_file_order_and_are_kept_at_once`), `tests/integration/test_term_lists_api.py` (`test_a_question_waits_for_one_term_at_most`, `test_a_saved_answer_is_given_again_and_marked`, `test_answers_and_reports_outlive_a_dictionary_import`) |
| 7-9 | `tests/integration/test_term_list_runs.py`, `tests/integration/test_term_lists_api.py` (`test_stop_and_resume_over_http`) |
| 10 | `tests/integration/test_term_list_runs.py` (`test_a_closing_process_interrupts_the_list`, `test_a_list_left_running_is_interrupted_at_start_and_by_the_check`) |
| 12, 14 | `tests/integration/test_term_lists_api.py` |
| 13 | `tests/parity/test_term_lists_parity.py`, `tests/integration/test_term_lists_api.py` |
| 15, 16 | `tests/integration/test_term_lists_api.py` (`test_the_newest_five_lists_of_a_person_are_kept`) |
| 18 | `tests/integration/test_term_list_runs.py` (`test_unavailable_answers_are_kept_and_failed_terms_asked_again`) |
| Veri ve geçiş | `tests/integration/test_list_and_vote_data_model.py` |
| Gözlemlenebilirlik | `tests/integration/test_telemetry_signals.py`, `tests/integration/test_term_lists_api.py` (`test_logs_and_metrics_carry_no_term_or_file_name`) |
| 17 | Ön yüz testleri (açık görev) |
