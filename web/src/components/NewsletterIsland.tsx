import MorningEmailSignup from './MorningEmailSignup';
import type { ui } from '../i18n/ui';

export default function NewsletterIsland({ lang = 'mk' }: { lang?: keyof typeof ui }) {
  return <MorningEmailSignup lang={lang} variant="default" />;
}
