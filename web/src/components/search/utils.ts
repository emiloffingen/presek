import { proxyUrl } from '../../lib/apiBase';

export function proxiedImage(url: string, width: number): string {
  return proxyUrl(`/proxy?url=${encodeURIComponent(url)}&w=${width}`);
}
