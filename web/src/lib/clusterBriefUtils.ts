export function parseBriefItem(item: string, lang: string) {
  const clean = item.trim();
  const match = clean.match(/^([A-Za-z\u0400-\u04FF\s\-]{3,20}):\s*(.*)$/);
  if (match) {
    const prefix = match[1].trim();
    const content = match[2].trim();

    let badgeText = prefix;
    let badgeClass = 'bg-muted text-muted-foreground';

    const lowerPrefix = prefix.toLowerCase();
    if (
      lowerPrefix.includes('настан') ||
      lowerPrefix.includes('фокус') ||
      lowerPrefix.includes('развој') ||
      lowerPrefix.includes('nadan') ||
      lowerPrefix.includes('događaj') ||
      lowerPrefix.includes('fokus') ||
      lowerPrefix.includes('razvoj')
    ) {
      badgeText = lang === 'sr' ? 'Fokus' : 'Фокус';
      badgeClass = 'bg-nyt-accent/15 text-nyt-accent border border-nyt-accent/25';
    } else if (
      lowerPrefix.includes('детали') ||
      lowerPrefix.includes('детал') ||
      lowerPrefix.includes('detalji') ||
      lowerPrefix.includes('detalj')
    ) {
      badgeText = lang === 'sr' ? 'Detalji' : 'Детали';
      badgeClass = 'cluster-brief-badge-detail';
    } else if (
      lowerPrefix.includes('медиум') ||
      lowerPrefix.includes('покриеност') ||
      lowerPrefix.includes('medij') ||
      lowerPrefix.includes('pokrivenost') ||
      lowerPrefix.includes('izvori') ||
      lowerPrefix.includes('извори')
    ) {
      badgeText = lang === 'sr' ? 'Izvori' : 'Извори';
      badgeClass = 'cluster-brief-badge-positive';
    } else if (
      lowerPrefix.includes('отворено') ||
      lowerPrefix.includes('нејасно') ||
      lowerPrefix.includes('otvoreno') ||
      lowerPrefix.includes('nejasno')
    ) {
      badgeText = lang === 'sr' ? 'Otvoreno' : 'Отворено';
      badgeClass = 'cluster-brief-badge-watch';
    }

    return { hasBadge: true, badgeText, badgeClass, content };
  }
  return { hasBadge: false, badgeText: '', badgeClass: '', content: clean };
}

export function highlightFactText(text: string) {
  let html = text;
  const moneyRegex =
    /(\d+[\beta\s\.]*(?:евра|evra|денари|denara|динара|dinara|EUR|€)|половина милион евра|polovina milion evra|пола милион евра|pola miliona evra)/gi;
  html = html.replace(moneyRegex, '<strong class="text-nyt-accent font-black">$1</strong>');

  const locationRegex =
    /(ГП\s+Табановце|Табановце|Tabanovce|Германија|Germanija|Албанија|Albanija)/gi;
  html = html.replace(locationRegex, '<strong class="text-foreground font-semibold">$1</strong>');

  return html;
}
