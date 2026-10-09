import {useLayoutEffect} from 'react';

/** The two looks of the application: the main screen and the admin (and account) screens. */
export type Surface = 'explorer' | 'admin';

/**
 * Mark <html> with the screen's surface so its stylesheet and token values apply
 * (globals.css). Set before paint, so a screen never shows the other's look.
 */
export function useSurface(surface: Surface): void {
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.surface = surface;
    return () => {
      if (root.dataset.surface === surface) delete root.dataset.surface;
    };
  }, [surface]);
}

/** Toggle a state class on <html>, as the source pages did (docked, busy, lifted, ...). */
export function useRootClass(name: string, on: boolean): void {
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.classList.toggle(name, on);
    return () => root.classList.remove(name);
  }, [name, on]);
}
