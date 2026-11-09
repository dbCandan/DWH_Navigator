import type {AnalysisAnswer, AnswerColumn, AnswerObject} from '@/types/analysis';
import type {VoteRecorded} from '@/types/feedback';

/**
 * The welcome tour's sample: one question and the answer the real answer view draws for it. It is
 * written by hand, never read from the dictionary, and nothing the visitor does with it leaves the
 * browser.
 */
export const TOUR_QUESTION = 'Şube bazında aylık ortalama mevduat bakiyesine ihtiyacım var';

const columnOf =
  (object: string) =>
  (column: string, description: string, role: '' | 'eşleşme' | 'yapısal' = '', extra: Partial<AnswerColumn> = {}): AnswerColumn => ({
    key: `${object}.${column}`,
    column,
    object,
    description,
    synonyms: [],
    group: null,
    role,
    signals: [],
    caveats: [],
    ...extra,
  });

const BALANCE = 'DWH.Mevduat.vDepositDailyBalance';
const BRANCH = 'DWH.Ortak.vBranch';
const ACCOUNT = 'DWH.Mevduat.vDepositAccount';

const balance = columnOf(BALANCE);
const branch = columnOf(BRANCH);
const account = columnOf(ACCOUNT);

type SampleField =
  | 'rank' | 'key' | 'schema' | 'name' | 'groups' | 'score' | 'level' | 'covered' | 'missing'
  | 'dimension' | 'reason' | 'caveat' | 'usage' | 'covers' | 'columns';
type SampleObject = Pick<AnswerObject, SampleField> & Pick<Partial<AnswerObject>, 'votes'>;

const object = (o: SampleObject): AnswerObject => ({
  database: 'DWH',
  components: {best_column: 0.8, coverage: 0.7, time: 1, granularity: 1, topic: 0.8},
  llm: o.score,
  long_format: [],
  ...o,
});

export const TOUR_ANSWER: AnalysisAnswer = {
  query: TOUR_QUESTION,
  verdict: 'KISMEN VAR',
  summary:
    'KISMEN VAR — Günlük mevduat bakiyeleri vDepositDailyBalance tablosunda şube kırılımıyla tutulur. Aylık ortalama hazır bir kolon değildir; günlük bakiyelerin ay içindeki ortalaması alınmalıdır.',
  interpretation: 'Her şube için, her ayın günlük mevduat bakiyelerinin ortalaması isteniyor.',
  concepts: ['ölçü:mevduat bakiyesi', 'kırılım:şube', 'zaman:aylık'],
  expansion: ['vadeli mevduat', 'vadesiz mevduat', 'hesap bakiyesi'],
  missing: ['aylık ortalama'],
  objects: [
    object({
      rank: 1,
      key: BALANCE,
      schema: 'Mevduat',
      name: 'vDepositDailyBalance',
      groups: ['Mevduat'],
      score: 0.86,
      level: 'Yüksek',
      covered: ['mevduat bakiyesi', 'şube', 'günlük'],
      missing: ['aylık ortalama'],
      dimension: 'Şube',
      reason:
        'BalanceAmountTRY kolonu her hesabın gün sonu bakiyesini TL karşılığıyla, BranchCode kolonu hesabın şubesini verir; tablo her gün güncellenir.',
      caveat: ['Döviz hesaplarında BalanceAmount kendi para birimindedir; toplamada BalanceAmountTRY kullanın.'],
      usage: 'BranchCode ve ay bazında gruplayıp BalanceAmountTRY ortalamasını alın.',
      covers: 'günlük bakiye, şube',
      votes: {up: 3, down: 0, reasons: [], status: 'approved', support: 3},
      columns: [
        balance('BalanceAmountTRY', 'Hesabın gün sonu bakiyesinin TL karşılığı', 'eşleşme', {
          synonyms: ['mevduat bakiyesi', 'TL bakiye'],
          signals: ['ad eşleşmesi', 'açıklama eşleşmesi'],
        }),
        balance('BranchCode', 'Hesabın bağlı olduğu şubenin kodu', 'yapısal', {synonyms: ['şube kodu']}),
        balance('BalanceDate', 'Bakiyenin ait olduğu gün', 'yapısal'),
        balance('AccountNumber', 'Mevduat hesabının numarası', 'yapısal'),
        balance('BalanceAmount', 'Gün sonu bakiyesi, hesabın kendi para biriminde'),
        balance('CurrencyCode', 'Hesabın para birimi (TRY, USD, EUR…)'),
        balance('ProductType', 'Vadeli, vadesiz ya da katılım hesabı'),
      ],
    }),
    object({
      rank: 2,
      key: BRANCH,
      schema: 'Ortak',
      name: 'vBranch',
      groups: ['Ortak'],
      score: 0.63,
      level: 'Orta',
      covered: ['şube'],
      missing: ['mevduat bakiyesi'],
      dimension: 'Şube',
      reason: 'Şube kodunu şube adı, bölge ve il bilgisiyle eşler; bakiye tutmaz, sonucu adlandırmak için gerekir.',
      caveat: [],
      usage: 'BranchCode üzerinden vDepositDailyBalance ile birleştirin.',
      covers: 'şube adı ve bölgesi',
      columns: [
        branch('BranchCode', 'Şube kodu', 'yapısal'),
        branch('BranchName', 'Şubenin adı', 'eşleşme', {synonyms: ['şube adı']}),
        branch('RegionName', 'Şubenin bağlı olduğu bölge'),
        branch('CityName', 'Şubenin bulunduğu il'),
      ],
    }),
  ],
  near: [
    object({
      rank: 3,
      key: ACCOUNT,
      schema: 'Mevduat',
      name: 'vDepositAccount',
      groups: ['Mevduat'],
      score: 0.41,
      level: 'Düşük',
      covered: ['mevduat'],
      missing: ['bakiye', 'aylık ortalama'],
      dimension: 'Hesap',
      reason: 'Hesabın açılış, vade ve şube bilgisini tutar; günlük bakiye geçmişi yoktur.',
      caveat: [],
      usage: '',
      covers: 'hesap bilgileri',
      columns: [
        account('AccountNumber', 'Mevduat hesabının numarası', 'yapısal'),
        account('OpenDate', 'Hesabın açılış tarihi'),
        account('MaturityDate', 'Vadeli hesapta vade sonu'),
      ],
    }),
  ],
  design: [
    'vDepositDailyBalance tablosunu istenen dönemle BalanceDate üzerinden süzün.',
    'BranchCode ve ay (BalanceDate’in yıl-ay kısmı) bazında gruplayıp BalanceAmountTRY ortalamasını alın.',
    'Şube adı ve bölgesi için sonucu BranchCode üzerinden vBranch ile birleştirin.',
  ],
  attention: [
    'Kapanan hesapların kapanıştan sonraki günlerde satırı yoktur; ortalamayı ayın gün sayısına değil satır sayısına bölün.',
    'Döviz hesaplarında BalanceAmount değil BalanceAmountTRY kullanın.',
  ],
  notes: [
    {
      scope: 'Netleştirme',
      title: 'Ortalama türü',
      text: 'Ay sonu bakiyesi mi yoksa günlük bakiyelerin ortalaması mı istendiği talep sahibiyle netleştirilmeli.',
    },
  ],
  method: ['Analist talebi üç kavrama ayırdı ve altı aday tabloyu okudu.'],
  elapsed_ms: 21400,
  dictionary_version: 'örnek',
  llm_model: 'örnek/analist',
  analyst: true,
  fallback: '',
  reused: null,
};

/** What the tour answers a vote with: the vote stays in the page, it is never sent. */
export function tourVoteRecorded(): Promise<VoteRecorded> {
  return Promise.resolve({answer_rejected: false, forgotten: 0, votes: null});
}

/** The steps the tour shows while the sample "analysis" runs, as the real analysis reports them. */
export const TOUR_PROGRESS = ['understand', 'search', 'score', 'write'] as const;

/** The tour's pace in milliseconds: a character typed, a progress step. Tests make it instant. */
export const tourPace = {typeMs: 28, stageMs: 750};
