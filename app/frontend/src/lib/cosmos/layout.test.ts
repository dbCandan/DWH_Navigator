import {describe, expect, it} from 'vitest';
import {buildGalaxy, findTable, fnv1a, nearestStar, project, type GalaxyItem} from './layout';

const item = (key: string, group: string, columns = 9): GalaxyItem => {
  const parts = key.split('.');
  return {key, name: parts[parts.length - 1], schema: parts.slice(0, -1).join('.'), group, columns};
};

// Synthetic galaxy: two groups, a group of one, the same name in two schemas.
const ITEMS: GalaxyItem[] = [
  item('DWH.Ornek.vCampaign', 'Kampanya', 4),
  item('DWH.Rapor.vCampaign', 'Kampanya', 16),
  item('DWH.Ornek.vCustomerInfo', 'Müşteri', 25),
  item('DWH.Ornek.vCustomerLimit', 'Müşteri', 1),
  item('DWH.Ornek.vCustomerScore', 'Müşteri', 100),
  item('DWH.Ornek.vİşlemÖzet', 'Diğer', 3),
];

describe('galaxy layout (dictionary-explorer Requirement 4)', () => {
  it('gives the same positions, sizes, depths and tones for the same data', () => {
    const a = buildGalaxy(ITEMS);
    const b = buildGalaxy(ITEMS);
    const shape = (g: ReturnType<typeof buildGalaxy>) =>
      g.stars.map(({key, x, y, z, size, tw, hue}) => ({key, x, y, z, size, tw, hue}));
    expect(shape(a)).toEqual(shape(b));
    expect(a.dust).toEqual(b.dust);
    expect(a.dust).toHaveLength(480);
  });

  it('orders clusters by member count and colours each by the FNV-1a of its name', () => {
    const galaxy = buildGalaxy(ITEMS);
    expect(galaxy.clusters.map((c) => [c.name, c.n])).toEqual([
      ['Müşteri', 3],
      ['Kampanya', 2],
      ['Diğer', 1],
    ]);
    for (const cluster of galaxy.clusters) expect(cluster.hue).toBe(fnv1a(cluster.name) % 360);
    // The largest cluster sits nearest the centre (sunflower spiral).
    const radius = galaxy.clusters.map((c) => Math.hypot(c.x, c.y));
    expect(radius[0]).toBeLessThan(radius[1]);
    expect(radius[1]).toBeLessThan(radius[2]);
  });

  it('sizes a star by the square root of its column count', () => {
    const star = buildGalaxy(ITEMS).byKey.get('DWH.Ornek.vCustomerScore');
    expect(star?.size).toBeCloseTo(0.9 + Math.sqrt(100) * 0.32);
  });

  it('matches the source FNV-1a value for a known text', () => {
    // 32-bit FNV-1a of "a" is 0xe40c292c.
    expect(fnv1a('a')).toBe(0xe40c292c);
  });

  it('places stars in proportion to the window, without fixed pixels', () => {
    const point = {x: 0.5, y: -0.25, z: 1};
    const view = {rot: 0, width: 1000, height: 600, mouseX: 0.5, mouseY: 0.5, camX: 0, camY: 0};
    expect(project(point, view)).toEqual([500 + 0.5 * 1000 * 0.47, 300 - 0.25 * 600 * 0.46]);
    const wide = project(point, {...view, width: 2000});
    expect(wide[0]).toBe(1000 + 0.5 * 2000 * 0.47);
  });
});

describe('star picking (Requirement 6)', () => {
  it('picks the nearest star within 14 pixels and nothing farther', () => {
    const galaxy = buildGalaxy(ITEMS);
    galaxy.stars.forEach((star, i) => {
      star.sx = 100 * i;
      star.sy = 50;
    });
    expect(nearestStar(galaxy.stars, 205, 55)?.key).toBe(galaxy.stars[2].key);
    expect(nearestStar(galaxy.stars, 200, 50 + 13.9)).toBe(galaxy.stars[2]);
    expect(nearestStar(galaxy.stars, 200, 50 + 14)).toBeNull();
  });
});

describe('opening a table by its name (Requirement 9)', () => {
  const stars = buildGalaxy(ITEMS).stars;

  it.each([
    ['the name', 'vCustomerInfo'],
    ['another case', 'VCUSTOMERINFO'],
    ['Schema.name', 'Ornek.vCustomerInfo'],
    ['the full key', 'DWH.Ornek.vCustomerInfo'],
    ['surrounding spaces', '  vcustomerinfo  '],
  ])('finds one table by %s', (_, text) => {
    expect(findTable(stars, text)?.key).toBe('DWH.Ornek.vCustomerInfo');
  });

  it('treats ı and i, İ and i as the same letter', () => {
    expect(findTable(stars, 'VİŞLEMÖZET')?.key).toBe('DWH.Ornek.vİşlemÖzet');
    expect(findTable(stars, 'vışlemözet')?.key).toBe('DWH.Ornek.vİşlemÖzet');
    expect(findTable(stars, 'VCUSTOMERINFO')?.key).toBe('DWH.Ornek.vCustomerInfo');
  });

  it('asks instead when the name is in two schemas, matches nothing or holds a space', () => {
    expect(findTable(stars, 'vCampaign')).toBeNull();
    expect(findTable(stars, 'Rapor.vCampaign')?.key).toBe('DWH.Rapor.vCampaign');
    expect(findTable(stars, 'vNothing')).toBeNull();
    expect(findTable(stars, 'vCustomerInfo nerede')).toBeNull();
    expect(findTable(stars, '')).toBeNull();
  });
});
