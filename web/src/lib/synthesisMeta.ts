export type SynthesisMetaLike = {
  copy_purity_ok?: boolean | null;
  copy_purity_score?: number | null;
  copy_purity_reason?: string | null;
  is_provisional?: boolean;
  needs_upgrade?: boolean;
};

const REASON_LABELS: Record<string, { sr: string; mk: string }> = {
  high_latin_share: {
    sr: 'Previše latinice u makedonskom tekstu',
    mk: 'Премногу латиница во македонскиот текст',
  },
  serbian_latin_leaks: {
    sr: 'Srpske latinične reči u makedonskom tekstu',
    mk: 'Српски латинични зборови во македонскиот текст',
  },
  high_cyrillic_share: {
    sr: 'Previše ćirilice u srpskom tekstu',
    mk: 'Премногу кирилица во српскиот текст',
  },
  cyrillic_leaks: {
    sr: 'Ćirilični propusti u srpskom tekstu',
    mk: 'Кирилични протекувања во српскиот текст',
  },
  low_cyrillic: {
    sr: 'Nedovoljno ćirilice za makedonski tekst',
    mk: 'Недоволно кирилица за македонски текст',
  },
  low_latin: {
    sr: 'Nedovoljno latinice za srpski tekst',
    mk: 'Недоволно латиница за српски текст',
  },
};

export function buildCopyPurityNote(
  meta: SynthesisMetaLike | null | undefined,
  lang: 'sr' | 'mk',
): string | null {
  if (!meta || meta.copy_purity_ok !== false) {
    return null;
  }
  const reason = String(meta.copy_purity_reason || '').trim();
  const mapped = REASON_LABELS[reason];
  if (mapped) {
    return mapped[lang];
  }
  return lang === 'mk'
    ? 'Јазичниот квалитет на синтезата се проверува.'
    : 'Jezički kvalitet sinteze se proverava.';
}
