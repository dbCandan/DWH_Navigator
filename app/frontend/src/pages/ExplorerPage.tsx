import {lazy, Suspense, useEffect, useLayoutEffect, useRef, useState, type MouseEvent} from 'react';
import {CompassMark} from '@/components/brand/CompassMark';
import {SearchBox} from '@/components/explorer/SearchBox';
import {SessionArea} from '@/components/explorer/SessionArea';
import {useIntl} from '@/contexts/IntlContext';
import {useDocumentTitle} from '@/hooks/useDocumentTitle';
import {useRootClass, useSurface} from '@/hooks/useSurface';
import {SAMPLE_GALAXY} from '@/lib/cosmos/sampleGalaxy';
import '@/components/explorer/explorer.css';

// The map is a separate, lazily loaded part: the shell and the question bar never wait for it
// (dictionary-explorer Requirement 5).
const CosmosMap = lazy(() => import('@/components/explorer/CosmosMap'));

/** Scroll states of the source page: the veil behind the top line and the HUD's retreat. */
function useScrollClasses(): void {
  const [scroll, setScroll] = useState(() => window.scrollY);
  useEffect(() => {
    const onScroll = () => setScroll(window.scrollY);
    window.addEventListener('scroll', onScroll, {passive: true});
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  useRootClass('lifted', scroll > 6);
  useRootClass('scrolled', scroll > 120);
}

/**
 * The main screen (`/`): the "Evren" sky, the top line with the brand, the empty middle slot, the
 * tools (status and the session area) and the landing question bar (dictionary-explorer
 * Requirement 1, 5 and 17). The answer views, the table panel and the status pill come with the
 * capabilities that own them.
 */
export default function ExplorerPage() {
  const {t} = useIntl();
  useSurface('explorer');
  useDocumentTitle(t('explorer.documentTitle'));
  useScrollClasses();
  const [question, setQuestion] = useState('');
  const field = useRef<HTMLTextAreaElement>(null);
  const header = useRef<HTMLElement>(null);
  const hero = useRef<HTMLDivElement>(null);
  const foot = useRef<HTMLElement>(null);

  // Header and footer differ in height; balance them so the landing block sits at the window's
  // centre (index.html centreHero).
  useLayoutEffect(() => {
    const centre = () => {
      if (!header.current || !hero.current || !foot.current) return;
      const d = header.current.getBoundingClientRect().bottom - foot.current.offsetHeight;
      hero.current.style.setProperty('--shift-top', Math.max(0, -d) + 'px');
      hero.current.style.setProperty('--shift-bottom', Math.max(0, d) + 'px');
    };
    centre();
    window.addEventListener('resize', centre);
    return () => window.removeEventListener('resize', centre);
  }, []);

  /** "Yeni başlangıç": back to the landing view without reloading the page. */
  function restart(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    setQuestion('');
    window.scrollTo({top: 0});
    field.current?.focus();
  }

  function ask() {
    if (!question.trim()) field.current?.focus();
  }

  return (
    <>
      <Suspense fallback={null}>
        <CosmosMap galaxy={SAMPLE_GALAXY} />
      </Suspense>
      <header className="top" ref={header}>
        <div className="wrap">
          <a className="brand" href="/" title={t('explorer.brand.restart')} onClick={restart}>
            <CompassMark />
            <div>
              <b>{t('explorer.brand.name')}</b>
              <span>{t('explorer.brand.tagline')}</span>
            </div>
          </a>
          <div className="slot" id="bar-slot" />
          <div className="tools">
            <div className="status" id="status" />
            <SessionArea />
          </div>
        </div>
      </header>

      <main className="wrap">
        <section id="tab-ask">
          <div className="hero" id="hero" ref={hero}>
            <h1>{t('explorer.hero.title')}</h1>
            <SearchBox value={question} onChange={setQuestion} onSubmit={ask} textareaRef={field} />
            <div className="model-warn" id="model-warn" role="status" />
          </div>
          <div id="ask-out" />
        </section>
      </main>
      <footer id="foot" ref={foot} />
    </>
  );
}
