import {describe, expect, it} from 'vitest';
import {richTokenizer} from '@/lib/answerText';
import {answer} from '@/test/explorer';

const CATALOG = [
  {key: 'DWH.Kart.vCardLimit1', name: 'vCardLimit1'},
  {key: 'EDWDM.DGM.vUMECustomer', name: 'vUMECustomer'},
  {key: 'A.B.vTwin', name: 'vTwin'},
  {key: 'C.D.vTwin', name: 'vTwin'},
];

describe('the analyst prose as names (question-analysis Requirement 21)', () => {
  it('marks a dictionary table it names but did not suggest; a suggestion stays a suggestion', () => {
    const rich = richTokenizer(answer(), CATALOG);
    const tables = rich('vUMECustomer değil, vCardLimit1 kullanılmalı.').filter((t) => t.kind === 'table');
    expect(tables).toEqual([
      {kind: 'table', key: 'EDWDM.DGM.vUMECustomer', name: 'vUMECustomer', object: null, suggested: false},
      expect.objectContaining({key: 'DWH.Kart.vCardLimit1', suggested: true}),
    ]);
  });

  it('leaves a short name two tables share as text, and reads names without a catalog as before', () => {
    expect(richTokenizer(answer(), CATALOG)('vTwin tablosu').some((t) => t.kind === 'table')).toBe(false);
    expect(richTokenizer(answer())('vUMECustomer tablosu')).toEqual([{kind: 'text', text: 'vUMECustomer tablosu'}]);
  });

  it('drops the quotes around a name the chip already sets apart', () => {
    const tokens = richTokenizer(answer())("doğrudan 'RecordingTime' veya “RecordingDate” kolonları");
    expect(tokens).toEqual([
      {kind: 'text', text: 'doğrudan '},
      {kind: 'column', text: 'RecordingTime'},
      {kind: 'text', text: ' veya '},
      {kind: 'column', text: 'RecordingDate'},
      {kind: 'text', text: ' kolonları'},
    ]);
  });
});
