export interface ResearchQAItem {
  id: 'conflict' | 'facts' | 'reactions';
  question: string;
  answer: string;
}

interface Perspective {
  angle?: string;
  content?: string;
}

interface BuildResearchQAInput {
  lang: 'sr' | 'mk';
  questions: [string, string, string];
  keyFacts?: string[];
  perspectives?: Perspective[];
  synthesisBullets?: string[];
  generatedArticle?: string | null;
  emptyAnswer: string;
}

function cleanText(value: unknown): string {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function joinBullets(items: string[], limit = 4): string {
  const cleaned = items.map(cleanText).filter((item) => item.length > 12);
  if (!cleaned.length) return '';
  return cleaned.slice(0, limit).map((item) => `• ${item}`).join('\n');
}

function perspectiveAnswer(
  perspectives: Perspective[],
  matcher: RegExp,
  fallbackMatcher?: RegExp,
): string {
  const ranked = perspectives
    .map((item) => ({
      angle: cleanText(item.angle),
      content: cleanText(item.content),
    }))
    .filter((item) => item.content.length > 20);

  const primary = ranked.find((item) => matcher.test(item.angle) || matcher.test(item.content));
  if (primary) {
    return primary.angle ? `${primary.angle}: ${primary.content}` : primary.content;
  }

  if (fallbackMatcher) {
    const secondary = ranked.find((item) => fallbackMatcher.test(item.angle) || fallbackMatcher.test(item.content));
    if (secondary) {
      return secondary.angle ? `${secondary.angle}: ${secondary.content}` : secondary.content;
    }
  }

  const first = ranked[0];
  return first ? (first.angle ? `${first.angle}: ${first.content}` : first.content) : '';
}

function articleLead(text: string): string {
  const cleaned = cleanText(text);
  if (!cleaned) return '';
  const sentence = cleaned.split(/(?<=[.!?])\s+/).find((part) => part.length > 40);
  return sentence || cleaned.slice(0, 280);
}

export function buildResearchQA({
  lang,
  questions,
  keyFacts = [],
  perspectives = [],
  synthesisBullets = [],
  generatedArticle = '',
  emptyAnswer,
}: BuildResearchQAInput): ResearchQAItem[] {
  const conflictMatchers =
    lang === 'sr'
      ? /konflikt|razlik|spor|kontroverz|neslag/i
      : /конфликт|разлик|спор|контровер|несоглас/i;
  const reactionMatchers =
    lang === 'sr'
      ? /reakci|stav|izjav|komentar|odgovor/i
      : /реакци|став|изјав|коментар|одговор/i;

  const factsAnswer =
    joinBullets(keyFacts) ||
    joinBullets(synthesisBullets.filter((line) => /\d/.test(line))) ||
    joinBullets(synthesisBullets);

  const conflictAnswer =
    perspectiveAnswer(perspectives, conflictMatchers, /ugao|агол|angle/i) ||
    articleLead(generatedArticle || '') ||
    joinBullets(synthesisBullets, 2);

  const reactionsAnswer =
    perspectiveAnswer(perspectives, reactionMatchers) ||
    joinBullets(
      perspectives.map((item) => cleanText(item.content)).filter(Boolean),
      3,
    );

  const answers = [conflictAnswer, factsAnswer, reactionsAnswer];
  const ids: ResearchQAItem['id'][] = ['conflict', 'facts', 'reactions'];

  return questions.map((question, index) => ({
    id: ids[index],
    question,
    answer: answers[index] || emptyAnswer,
  }));
}
