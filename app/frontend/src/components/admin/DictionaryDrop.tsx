import {useEffect, useRef, useState} from 'react';
import {useIntl} from '@/contexts/IntlContext';
import {useDictionaryImport} from '@/hooks/useAdminActions';

const carriesFiles = (event: DragEvent) => [...(event.dataTransfer?.types ?? [])].includes('Files');

/**
 * Dropping an Excel file anywhere on the admin screen but Kelimeler imports it as the dictionary;
 * while it is dragged, the "Sözlüğü içe aktarmak için Excel dosyasını bırakın" area covers the
 * page (dictionary-management Requirement 15). The hidden `#file` input serves "Excel'den içe
 * aktar…" on the Sözlük page and in the command palette.
 */
export function DictionaryDrop({onWordsPage}: {onWordsPage: boolean}) {
  const {t} = useIntl();
  const importWorkbook = useDictionaryImport();
  const [shown, setShown] = useState(false);
  const depth = useRef(0);
  const latest = useRef({importWorkbook, onWordsPage});
  useEffect(() => {
    latest.current = {importWorkbook, onWordsPage};
  });

  useEffect(() => {
    const enter = (event: DragEvent) => {
      if (latest.current.onWordsPage || !carriesFiles(event)) return;
      depth.current += 1;
      setShown(true);
    };
    const leave = () => {
      depth.current = Math.max(0, depth.current - 1);
      if (!depth.current) setShown(false);
    };
    const over = (event: DragEvent) => {
      if (!latest.current.onWordsPage && carriesFiles(event)) event.preventDefault();
    };
    const drop = (event: DragEvent) => {
      const file = event.dataTransfer?.files[0];
      if (!file || latest.current.onWordsPage) return;
      event.preventDefault();
      depth.current = 0;
      setShown(false);
      void latest.current.importWorkbook(file);
    };
    window.addEventListener('dragenter', enter);
    window.addEventListener('dragleave', leave);
    window.addEventListener('dragover', over);
    window.addEventListener('drop', drop);
    return () => {
      window.removeEventListener('dragenter', enter);
      window.removeEventListener('dragleave', leave);
      window.removeEventListener('dragover', over);
      window.removeEventListener('drop', drop);
    };
  }, []);

  return (
    <>
      <div className="dropzone" id="dropzone" hidden={!shown}>
        {t('dictionary.drop')}
      </div>
      <input
        type="file"
        id="file"
        accept=".xlsx"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) void importWorkbook(file);
        }}
      />
    </>
  );
}
