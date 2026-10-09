import {useEffect} from 'react';

/** The browser tab's title while the calling screen is shown. */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
