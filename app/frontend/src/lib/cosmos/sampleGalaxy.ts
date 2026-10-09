import type {GalaxyItem} from './layout';
import sample from './sampleGalaxy.json';

/**
 * A fixed, synthetic galaxy (no real dictionary) that draws the map until the galaxy endpoint
 * (dictionary-explorer Requirement 3, `GET /explorer/galaxy`) is wired in; it has the endpoint's
 * shape: name-ordered tables with their group and column count.
 */
export const SAMPLE_GALAXY: readonly GalaxyItem[] = sample.items;
