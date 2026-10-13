import sectors from './data/sectors.json';

export type Item = { headline: string; summary: string; whyItMatters: string; source: string; url: string };
export type Brief = {
  date: string;
  lead: { headline: string; dek: string };
  keyNumbers: { label: string; value: string; note?: string }[];
  ticker: { tag: string; text: string }[];
  sectors: Record<string, Item[]>;
  regulatory?: Item[];
};

const modules = import.meta.glob('./data/briefs/*.json', { eager: true }) as Record<string, { default: Brief }>;
export const briefs: Brief[] = Object.values(modules).map((m) => m.default).sort((a, b) => b.date.localeCompare(a.date));
export const latest = briefs[0];
export { sectors };

export function fmtDate(iso: string, opts: Intl.DateTimeFormatOptions = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) {
  return new Date(iso + 'T00:00:00+05:30').toLocaleDateString('en-GB', { timeZone: 'Asia/Kolkata', ...opts });
}
export const sectorName = (slug: string) => sectors.find((s) => s.slug === slug)?.name ?? (slug === 'general' ? 'General / Deal terms' : slug);
