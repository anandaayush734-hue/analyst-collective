import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const caseStudies = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/case-studies' }),
  schema: z.object({
    title: z.string(),
    sector: z.enum(['ev', 'autos', 'industrials', 'aerospace-defence']),
    dealType: z.string(),
    date: z.string(),
    dek: z.string(),
    keyTerms: z.array(z.object({ label: z.string(), value: z.string() })),
    sources: z.array(z.object({ title: z.string(), url: z.string() })),
  }),
});

export const collections = { 'case-studies': caseStudies };
