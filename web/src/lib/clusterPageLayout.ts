export type SiteLang = 'sr' | 'mk';

export type SynthesisFreshness = {
  is_stale?: boolean;
  reasons?: string[];
};

export type ClusterLayoutInput = {
  hasGeneratedNarrative: boolean;
  synthesisFreshness?: SynthesisFreshness | null;
  hasFactcheck: boolean;
  conflictsCount: number;
  pluralismScore?: number | null;
  uniqueSourcesCount: number;
  leadVisualIsWeak?: boolean;
};

export function shouldShowExecutiveSummary(
  input: ClusterLayoutInput & { hasBriefItems?: boolean; hasKeyFacts?: boolean },
): boolean {
  if (!input.hasBriefItems && !input.hasKeyFacts) return false;
  if (!input.hasGeneratedNarrative) return true;
  if (input.synthesisFreshness?.is_stale) return true;
  if (input.synthesisFreshness?.reasons?.includes('missing_synthesis')) return true;
  return false;
}

export function shouldShowHeroVisual(input: ClusterLayoutInput): boolean {
  return !input.leadVisualIsWeak;
}

export function shouldShowPerspectives(input: ClusterLayoutInput): boolean {
  if (input.conflictsCount > 0) return true;
  const pluralism = input.pluralismScore;
  if (pluralism != null && pluralism >= 55) return true;
  return false;
}

export function shouldShowConsensusNote(input: ClusterLayoutInput): boolean {
  if (!input.hasGeneratedNarrative) return false;
  if (input.hasFactcheck) return false;
  if (input.conflictsCount > 0) return false;
  if (shouldShowPerspectives(input)) return false;
  if (input.uniqueSourcesCount < 2) return false;

  const pluralism = input.pluralismScore;
  if (pluralism != null) return pluralism < 55;
  return true;
}

export function shouldShowCredibilitySection(input: ClusterLayoutInput): boolean {
  return input.hasFactcheck || shouldShowPerspectives(input) || shouldShowConsensusNote(input);
}

export function getConsensusNote(lang: SiteLang): string {
  return lang === 'sr'
    ? 'Izvori prenose istu ili vrlo sličnu informaciju. Razlike su u dubini, naslovu i izboru detalja — ne u samoj činjenici događaja.'
    : 'Изворите пренесуваат иста или многу слична информација. Разликите се во длабочина, наслов и избор на детали — не во самата чиненица на настанот.';
}

export function resolveHasCitationSources(citationSources: unknown): boolean {
  return Array.isArray(citationSources) && citationSources.length > 0;
}
