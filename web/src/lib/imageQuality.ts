import config from '../../config/image_quality.json' with { type: 'json' };

const WEAK_PATTERNS = config.weak_patterns as string[];
const MIN_URL_LENGTH = config.min_url_length as number;
const GENERATED_EXEMPT_PATH = config.generated_exempt_path as string;
const SOURCE_BONUSES = config.source_bonuses as Record<string, number>;

function weakPatternTarget(url: string): string {
  const value = url.toLowerCase().trim();
  if (!value) return value;
  if (value.startsWith('/')) return value;
  try {
    const parsed = new URL(value);
    if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
      return `${parsed.pathname}${parsed.search}`.toLowerCase();
    }
  } catch {
    // fall through
  }
  return value;
}

export function isWeakVisual(url?: string | null): boolean {
  const value = String(url || '').toLowerCase().trim();
  if (!value) return true;
  if (value.includes(GENERATED_EXEMPT_PATH)) return false;
  if (value.length < MIN_URL_LENGTH) return true;
  const target = weakPatternTarget(value);
  return WEAK_PATTERNS.some((token) => target.includes(token));
}

function extractImageDimensions(url: string) {
  let parsed: URL | null = null;
  try {
    parsed = new URL(url, 'https://presek.mk');
  } catch {
    parsed = null;
  }

  const haystack = `${parsed?.pathname || ''} ${parsed?.search || ''} ${url}`.toLowerCase();
  const dimensionMatch = haystack.match(/(^|[^0-9])(\d{2,5})x(\d{2,5})([^0-9]|$)/);
  if (dimensionMatch) {
    return {
      width: Number(dimensionMatch[2]) || 0,
      height: Number(dimensionMatch[3]) || 0,
    };
  }

  return {
    width:
      Number(parsed?.searchParams.get('w')) ||
      Number(parsed?.searchParams.get('width')) ||
      Number(parsed?.searchParams.get('max_width')) ||
      0,
    height:
      Number(parsed?.searchParams.get('h')) ||
      Number(parsed?.searchParams.get('height')) ||
      Number(parsed?.searchParams.get('max_height')) ||
      0,
  };
}

export function scoreImageUrl(url: string, source?: string): number {
  let score = 0;
  const val = url.toLowerCase();
  const { width, height } = extractImageDimensions(url);
  const area = width * height;

  if (isWeakVisual(url)) score -= 12;

  if (val.includes('.avif')) score += 3;
  if (val.includes('.jpg') || val.includes('.jpeg')) score += 2;
  if (val.includes('.webp')) score += 2;
  if (val.includes('.png')) score -= 1;

  if (val.includes('cdn') || val.includes('imgix') || val.includes('cloudinary')) score += 1;

  if (area) score += Math.min(area / 240000, 10);
  if (width >= 1400 || height >= 1400) score += 4;
  else if (width >= 1000 || height >= 1000) score += 2.5;
  else if (width >= 700 || height >= 700) score += 1.25;
  if (width && width < 180) score -= 6;
  if (height && height < 180) score -= 6;

  if (/(thumb|thumbnail|sprite|logo|icon|avatar|favicon|pixel|small)/.test(val)) score -= 7;
  if (/(hero|lead|main|large|full|original)/.test(val)) score += 2;

  if (source) {
    const loweredSource = source.toLowerCase();
    for (const [token, bonus] of Object.entries(SOURCE_BONUSES)) {
      if (loweredSource.includes(token)) {
        score += bonus;
        break;
      }
    }
  }

  return score;
}
