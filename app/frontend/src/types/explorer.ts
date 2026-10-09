import type {components} from './api';

type Schemas = components['schemas'];

/** The map's data, the table search and the table file (data-dictionary/PRDs/007-dictionary-explorer). */
export type Galaxy = Schemas['Galaxy'];
export type GalaxyTable = Schemas['GalaxyTable'];
export type TableSearchResult = Schemas['TableSearchResult'];
export type FoundTable = Schemas['FoundTable'];
export type TableDetail = Schemas['TableDetail'];
export type TableColumn = Schemas['TableColumn'];
