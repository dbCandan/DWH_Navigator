# Plan — dictionary-sync

PRD: [PRD.md](PRD.md). Bu dosya uygulamanın tek sözleşmesidir; PRD ile çelişirse aşağıdaki kararlar geçerlidir.

## Proje sahibi kararları

- Kaynağa **doğrudan SQL** ile bağlanılır (PRD Decision 2'nin HTTP yolu yerine). Motor SQL Server'dır.
- Okunan tablolar yalnız `EDWUTIL.OPR.DatasetDefinition` ve `EDWUTIL.OPR.DatasetDefinitionDetail`.
- Yerelde kurumsal yönetişim kuralları uygulanmaz; değerlendirme kurum ağına girerken yapılır.
- Uygulama SQL Server'a tam yetkili kullanıcıyla bağlanır (yerelde `sa`).
- Kişisel veri (KVKK) işareti üründen kaldırıldı. Sözlük metinlerindeki işaret cümleleri ve Summary'deki
  `· KVKK` eki güncellemede temizlenir; kavram olarak KVKK'dan söz eden iş metinlerine dokunulmaz.
- Navigator'daki sözlük kaynaktan daha kalitelidir ve kaynak insan girişidir: dolu metin kaynakla ezilmez,
  saklı yordam kolonunda kaynaktaki yakın yazım Navigator'daki yazıma çevrilir.
- `DWHNAVIGATOR_DICTIONARY_IGNORED_DATABASES` içindeki veritabanı (yerelde `ERPDM`) okunmaz; kayıtları
  sözlükte değişmeden kalır ve silinmiş sayılmaz.
- Zamanlayıcı yok. Yönetici alan düzeltme ekranı (PRD Open Question 2) bu işin kapsamında değil.

## Kaynak eşlemesi

`DatasetDefinition`: `DatabaseName`, `SchemaName`, `ObjectName`, `Description` okunur.
`DatasetDefinitionDetail`: `DatabaseName`, `SchemaName`, `ObjectName`, `ColumnName`, `ColumnDescription`,
`DatasetGroup` okunur.

- `BusinessOwner`, `BusinessTeam`, `Analyst`, `Developer`, `UATResponsible` kişi veya ekip bilgisidir:
  **SELECT edilmez**, saklanmaz, modele gitmez.
- `TranDate` ve `CreateDate` her yüklemede değişebilir: okunmaz, özete girmez.
- Tablo düzeyi `DatasetGroup`, kolon satırlarındaki en sık dolu değerdir; model üretmez.
- Metinler kırpılır; NULL boş metindir. Anahtar `DB.Şema.Obje`, büyük/küçük harf duyarsız eşleşir.
- Yalnız kolon satırı olan tablo da sözlüğe girer; kolonsuz tablo uyarı olur ve atlanır.

## Varlık teyidi

Sözlük satırları, adlandırdıkları veritabanında gerçekten var mı diye teyit edilir. `DatabaseName` değerleri
(bugün `EDWDM`, `EDWBridge`, `ERPDM`) aynı sunucudaki veritabanlarıdır. Yalnız katalog okunur
(`sys.objects` tip `V`/`P`, `sys.schemas`, `sys.columns`); iş verisine dokunulmaz.

Sözlük, ambarın sunduğu nesneleri kapsar: `EDWDM` görünümleri ve `EDWBridge` saklı yordamları. Tablolar
sunulmaz; aynı adlı tablo bir görünümün veya yordamın varlık kanıtı sayılmaz.
Saklı yordamın kolon listesi katalogda yoktur: yordamda nesne teyit edilir, kolonları kaynaktaki hâliyle alınır.

- Hedef veritabanında olmayan nesne eşitleme kapsamı dışındadır: yeni sürüme girmez, modele gitmez.
- Nesnesi olan ama hedefte bulunmayan kolon da dışarıda kalır. Teyitli kolonu kalmayan nesne dışarıda kalır.
- Hedefte olup sözlükte olmayan nesne veya kolon eklenmez; kapsamı sözlük belirler.
- Dışarıda kalanlar raporda `table_excluded` ve `column_excluded` olarak görünür. Etkin sözlükte olup dışarıda
  kalan kayıt ayrıca `table_removed` veya `column_removed` olur ve silme güvenlik sınırına sayılır.
- **Güvenlik:** Adlandırılan veritabanı sunucuda yoksa, çevrimiçi değilse, okunamıyorsa veya kataloğu hiç nesne
  döndürmüyorsa (yetki eksikliğinde SQL Server nesneleri sessizce gizler) iş `failed` kapanır, kod
  `dictionary_target_unavailable` olur. Erişim sorunu hiçbir zaman "nesne yok" sayılmaz.
- Veritabanı adı kaynak veridir: önce `sys.databases` ile doğrulanır, sorguya yalnız `QUOTENAME` ile girer.

## Üçlü kontrol

Navigator, `EDWUTIL` ve hedef katalog birlikte karşılaştırılır. Katalog varlığın, Navigator metnin otoritesidir.

| Navigator | `EDWUTIL` | Katalog | Sonuç |
|---|---|---|---|
| Var | Var | Var | Metin korunur, ad katalogdan gelir |
| Yok | Var | Var | Yeni kayıt |
| Var | Yok | Var | Korunur (`table_kept`, `column_kept`) |
| Var | Var veya yok | Yok | Silinir |
| Yok | Var | Yok | Dışarıda kalır (`table_excluded`, `column_excluded`) |

Saklı yordamda kolonun yokluğu kanıtlanamaz: Navigator'daki kolon kalır. Elle onaylanan ad eşleşmeleri
`DWHNAVIGATOR_DICTIONARY_OBJECT_ALIASES` içinde `kaynak=katalog` biçiminde, noktalı virgülle ayrılır.

## Yazım düzeltme

Sözlük elle tutulduğu için adlarda insan hatası olabilir. Doğru ad her zaman hedef veritabanı kataloğundaki addır;
düzeltme yalnız Navigator'ın sözlüğünde olur, `EDWUTIL`'e hiçbir şey yazılmaz. Eşleştirme sırası:

1. **Birebir:** Katalogla aynı olan ada asla dokunulmaz ve bu ad başka bir kayda aday olamaz.
2. **Normal biçim:** Boşluklar (NBSP ve görünmez karakterler dahil, ad içindekiler de), baştaki ve sondaki noktalama
   (`. , ; : ' " `` ` ``) atılır, büyük/küçük harf yok sayılır. Veritabanı, şema, nesne ve kolon adlarına uygulanır.
3. **Tek harf hatası:** Yalnız nesne ve kolon adlarında, en az 6 karakterli adlarda, aynı veritabanı ve şema (kolonda
   aynı nesne) içinde: bir fazla karakter, bir eksik karakter, yan yana iki harfin yer değiştirmesi veya bir harfin
   yanlış yazılması. Rakam içeren değişiklik düzeltme sayılmaz (`Risk1` ile `Risk2` farklı kolonlardır). İlk
   karakter değişikliği de sayılmaz: baştaki `v` görünümü gösterir, `vCard` ile `Card` iki ayrı nesnedir.

- **Yanlış şema:** Nesne kendi şemasında yoksa ama aynı ad (2. adıma göre) aynı veritabanında tek bir başka
  şemada varsa ve o nesneyi başka kayıt kullanmıyorsa yalnız şema düzeltilir, ad hiç değişmez.
- Aday **tek** olmalı ve o katalog adını birebir kullanan başka bir sözlük kaydı bulunmamalıdır. Değilse kayıt
  düzeltilmez, `table_excluded` veya `column_excluded` olur.
- Düzeltilen kayıt sözlüğe katalogdaki adla girer; rapor `table_corrected` veya `column_corrected` satırında eski ve
  yeni yazımı gösterir. Etkin sürümde hatalı adla duran kaydın değerleri yeni ada taşınır, silinmiş sayılmaz.
- Veritabanı adı 3. adıma girmez: 2. adımda da eşleşmezse `dictionary_target_unavailable` kuralı geçerlidir.

## Birleştirme

| Alan | Kural |
|---|---|
| Ad alanları | Kaynaktaki yazım geçerli |
| `ObjectDescription`, `ColumnDescription`, `DatasetGroup` | Önceki boşsa kaynak, o da boşsa model (grup hariç). Önceki `kaynak` kökenliyse ve kaynak dolu ve farklıysa kaynak geçerli. Önceki başka kökenliyse korunur |
| `Grain`, `KeyColumns`, `TimeColumns`, `BusinessDomain`, `Synonyms`, `Role`, `Summary` | Dolu değer korunur, boşsa model |

Köken `kaynak`, `model` veya `onceki`dir ve kaydın `props.origins` alanında durur. Tablonun kaynak özeti
`props.source_digest`, modeli bekleyen tablo `props.model_pending` alanında durur. Özeti olmayan eski tablo,
kolon kümesi aynıysa değişmemiş sayılır. Model yalnız yeni, özeti değişmiş veya `model_pending` tablolara gider.

## API sözleşmesi

Bütün yollar mevcut sözlük router'ının önekinin altındadır (`<sözlük>`), yalnız `yonetici` erişir.

| Yöntem ve yol | Gövde | Yanıt |
|---|---|---|
| `GET <sözlük>/source` | | `Source` |
| `PUT <sözlük>/source` | `SourceInput` | `Source` |
| `POST <sözlük>/source/test` | `SourceInput` | `SourceTest` |
| `POST <sözlük>/sync` | | 202 `RunSummary` |
| `GET <sözlük>/sync/runs?page&page_size` | | `{items: RunSummary[], total, page, page_size}` |
| `GET <sözlük>/sync/runs/{id}` | | `RunDetail` |
| `GET <sözlük>/sync/runs/{id}/changes?kind&search&page&page_size` | | `{items: Change[], total, page, page_size}` |
| `POST <sözlük>/sync/runs/{id}/approve` | | `RunDetail` |
| `POST <sözlük>/sync/runs/{id}/reject` | | `RunDetail` |
| `POST <sözlük>/sync/runs/{id}/suggestions/apply` | `{suggestion_ids: string[]}` | `RunDetail` |
| `GET <sözlük>/versions` | | `{items: Version[]}` |
| `POST <sözlük>/versions/{id}/restore` | | 202 `RunSummary` |

```text
Source      {configured: bool, host, port: int, database, username, has_password: bool, encrypt: bool,
             updated_at: datetime|null}
SourceInput {host, port: int, database, username, password?: string, encrypt: bool}
            password yoksa kayıtlı parola korunur; parola hiçbir yanıtta dönmez.
SourceTest  {ok: bool, message: string, table_count: int, column_count: int, last_change_at: datetime|null,
             missing_databases: string[]}
RunSummary  {public_id, kind: "guncelleme"|"geri_donus",
             status: "running"|"completed"|"no_change"|"pending_approval"|"rejected"|"failed"|"interrupted",
             phase: "reading"|"comparing"|"filling"|"indexing"|"done", progress_done: int, progress_total: int,
             started_at, finished_at: datetime|null, started_by: {public_id, display_name}|null,
             previous_version: string, new_version: string, model: string, counts: Counts,
             error_code: string, error_message: string}
Counts      {tables_added, tables_removed, tables_changed, tables_excluded, tables_corrected, columns_added,
             columns_removed, columns_changed, columns_excluded, columns_corrected, fields_filled, fields_empty,
             model_calls, model_failures, warnings: int}
RunDetail   RunSummary + {warnings: string[], suggestions: Suggestion[]}
Suggestion  {public_id, kind: "term"|"stopword", value, equivalents: string[], note,
             status: "pending"|"applied"}
Change      {kind: "table_added"|"table_removed"|"table_changed"|"table_excluded"|"table_corrected"|"column_added"|
             "column_removed"|"column_changed"|"column_excluded"|"column_corrected", table_key, column_name, field, old_value, new_value, origin: "kaynak"|"model"|"onceki"|""}
Version     {public_id, version, status: "active"|"previous"|"pending", channel, imported_at,
             imported_by: {public_id, display_name}|null, object_count, column_count,
             run_public_id: string|null, expires_at: datetime|null, can_restore: bool}
```

Hata kodları: `dictionary_sync_in_progress` (409), `dictionary_source_not_configured` (409),
`dictionary_source_unavailable` (502), `dictionary_source_invalid` (502),
`dictionary_target_unavailable` (502), `dictionary_version_expired` (410), `dictionary_run_not_pending` (409),
`settings_encryption_unavailable` (409, parola şifreleme anahtarı olmadan saklanmaz).

## Kaynak bağlantı noktası

`app/domain/dictionary_source.py` şu tipleri tanımlar; uyarlayıcı
`app/infrastructure/dictionary_source/sqlserver.py` içindedir.

```python
@dataclass(frozen=True, slots=True)
class SourceConnection: host: str; port: int; database: str; username: str; password: str; encrypt: bool
@dataclass(frozen=True, slots=True)
class SourceTable: database: str; schema: str; name: str; description: str
@dataclass(frozen=True, slots=True)
class SourceColumn: database: str; schema: str; table: str; name: str; description: str; group: str
@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    tables: tuple[SourceTable, ...]            # yalnız teyitli nesneler
    columns: tuple[SourceColumn, ...]          # yalnız teyitli kolonlar
    skipped: int                               # bozuk veya yinelenen satırlar
    excluded_tables: tuple[str, ...]           # hedefte olmayan DB.Şema.Obje anahtarları
    excluded_columns: tuple[tuple[str, str], ...]  # (tablo anahtarı, kolon adı)
    corrected_tables: tuple[tuple[str, str], ...]  # (kaynaktaki anahtar, katalogdaki anahtar)
    corrected_columns: tuple[tuple[str, str, str], ...]  # (katalogdaki tablo anahtarı, kaynaktaki ad, katalogdaki ad)
@dataclass(frozen=True, slots=True)
class SourceProbe:
    table_count: int; column_count: int; last_change_at: datetime | None
    missing_databases: tuple[str, ...]         # sözlüğün adlandırdığı, ulaşılamayan veritabanları
class SourceUnavailable(Exception): ...   # ağ, oturum açma, zaman aşımı; metin taşımaz, .code alanı sabit sınıftır
class SourceInvalid(Exception): ...       # tablo veya kolon yok, sınır aşıldı
class TargetUnavailable(Exception): ...   # hedef veritabanı yok, okunamıyor veya kataloğu boş; .databases adları taşır
class DictionarySourcePort(Protocol):
    async def probe(self, connection: SourceConnection) -> SourceProbe: ...
    async def read(self, connection: SourceConnection) -> SourceSnapshot: ...
```

## Dosya sahipliği

Paralel çalışanlar yalnız kendi dosyalarına yazar.

- **Çekirdek:** `schema/alembic`, `app/domain/models/dictionary*.py`, `app/domain/dictionary.py`,
  `dictionary_repository.py`, `app/services/dictionary_sync*`, `app/api/dictionary_sync/`, `app/schemas/dictionary/sync.py`,
  `app/main.py`, `app/api/router.py`.
- **Kaynak uyarlayıcısı:** `app/domain/dictionary_source.py`, `app/infrastructure/dictionary_source/`, bağımlılık
  dosyaları, `app/infra/` yerel ağ ayarları.
- **Excel kaldırma:** `app/api/dictionary/router.py`, `dictionary_service.py`, `dictionary_import.py`,
  `app/scripts/dictionary.py`, `app/core/telemetry.py`, `app/backend/tests/`, `e2e/`.
- **Ön yüz:** `app/frontend/`.
