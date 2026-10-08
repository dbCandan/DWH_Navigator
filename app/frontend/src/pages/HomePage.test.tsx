import {describe, expect, it} from 'vitest';
describe('platform home', () => {
  it('does not ship a generic business resource', () => {
    expect("\u0130\u015f birimlerinin do\u011fal dildeki veri taleplerini veri ambar\u0131 s\u00f6zl\u00fc\u011f\u00fcne kar\u015f\u0131 kurum i\u00e7i LLM ile e\u015fle\u015ftirip tablo seviyesinde, gerek\u00e7eli ve g\u00fcven skorlu \u00f6neriler ve Excel raporu almas\u0131; s\u00f6zl\u00fc\u011f\u00fcn, terim listelerinin ve model ba\u011flant\u0131s\u0131n\u0131n y\u00f6netim ekran\u0131ndan y\u00f6netilmesi; kimlik do\u011frulamal\u0131 ve kurumsal Kubernetes ortam\u0131nda g\u00fcvenli \u00e7al\u0131\u015fma.").not.toMatch(/sample item/i);
  });
});
