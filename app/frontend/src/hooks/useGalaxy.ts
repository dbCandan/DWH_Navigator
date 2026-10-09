import {useEffect, useRef, useState} from 'react';
import type {GalaxyItem} from '@/lib/cosmos/layout';
import {ExplorerService} from '@/services/explorer';
import type {ServiceStatus} from '@/types/analysis';

/**
 * The map's data (dictionary-explorer Requirement 3, 16, 19): read with the first status answer,
 * read again when the status names another dictionary version, and, while the index is not
 * ready (503) or the read failed, tried again at the next status poll. Without data the page
 * works without the map.
 */
export function useGalaxy(status: ServiceStatus | null): readonly GalaxyItem[] | null {
  const [galaxy, setGalaxy] = useState<readonly GalaxyItem[] | null>(null);
  const loadedFor = useRef<string | null>(null);
  const loading = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (status === null || loading.current || loadedFor.current === status.dictionary_version) return;
    const version = status.dictionary_version;
    loading.current = true;
    ExplorerService.galaxy()
      .then(
        (answer) => {
          if (!mounted.current) return;
          loadedFor.current = version;
          setGalaxy(answer.items);
        },
        () => undefined, // the next status poll tries again
      )
      .finally(() => {
        loading.current = false;
      });
  }, [status]);

  return galaxy;
}
