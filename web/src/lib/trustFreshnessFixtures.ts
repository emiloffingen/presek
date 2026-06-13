import type { StoryFreshnessInput } from '../utils/storyFreshness';

export type TrustChipFixture = {
  id: string;
  label: string;
  props: {
    sourcesCount: number;
    pluralismScore?: number | null;
    isStale?: boolean;
    hasVerification?: boolean;
    quietFreshness?: boolean;
    isPendingSynthesis?: boolean;
    showExplainer?: boolean;
  };
};

export type FreshnessFixture = {
  id: string;
  label: string;
  input: StoryFreshnessInput & {
    pipelineBusy?: boolean;
    missingSynthesis?: boolean;
  };
};

const minutesAgo = (mins: number) => new Date(Date.now() - mins * 60 * 1000).toISOString();

export const trustChipFixtures: TrustChipFixture[] = [
  {
    id: 'early-single',
    label: 'Single source (early)',
    props: { sourcesCount: 1 },
  },
  {
    id: 'pending-synthesis',
    label: 'Pending synthesis',
    props: {
      sourcesCount: 3,
      isPendingSynthesis: true,
      quietFreshness: true,
      showExplainer: true,
    },
  },
  {
    id: 'consensus',
    label: 'Consensus',
    props: { sourcesCount: 5, pluralismScore: 8 },
  },
  {
    id: 'plural',
    label: 'Pluralism',
    props: { sourcesCount: 4, pluralismScore: 62 },
  },
  {
    id: 'verified',
    label: 'Verified + fact-check',
    props: { sourcesCount: 6, pluralismScore: 12, hasVerification: true },
  },
  {
    id: 'stale-refresh',
    label: 'Stale refresh',
    props: { sourcesCount: 4, pluralismScore: 18, isStale: true, showExplainer: true },
  },
];

export const freshnessFixtures: FreshnessFixture[] = [
  {
    id: 'fresh',
    label: 'Fresh synthesis',
    input: { lang: 'sr', synthesisUpdatedAt: minutesAgo(8), isStale: false },
  },
  {
    id: 'aging',
    label: 'Aging synthesis',
    input: { lang: 'sr', synthesisUpdatedAt: minutesAgo(95), isStale: false },
  },
  {
    id: 'pending',
    label: 'Pending synthesis',
    input: { lang: 'sr', missingSynthesis: true, isStale: true },
  },
  {
    id: 'stale-updating',
    label: 'Stale refresh',
    input: { lang: 'sr', synthesisUpdatedAt: minutesAgo(30), isStale: true },
  },
  {
    id: 'stale-new-reports',
    label: 'Stale with new reports',
    input: {
      lang: 'sr',
      synthesisUpdatedAt: minutesAgo(45),
      isStale: true,
      newArticleCount: 3,
    },
  },
  {
    id: 'pipeline-busy',
    label: 'Pipeline busy',
    input: {
      lang: 'sr',
      synthesisUpdatedAt: minutesAgo(12),
      isStale: false,
      pipelineBusy: true,
    },
  },
];
