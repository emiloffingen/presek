import React, { useEffect, useState } from 'react';
import { shouldShowTinyAdzInlinedAds } from '../lib/tinyadz';

interface Props {
  lang?: 'sr' | 'mk';
  className?: string;
}

/** React slot mirror of TinyAdzRailAd - uses the same ta-ad-container hook. */
export default function TinyAdzRailSlot({ lang = 'sr', className = '' }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setVisible(shouldShowTinyAdzInlinedAds(lang, window.location.hostname));
  }, [lang]);

  if (!visible) return null;

  return (
    <div
      ta-ad-container=""
      className={`tinyadz-inlined tinyadz-rail-shell page-rail-ad ${className}`.trim()}
      aria-label={lang === 'sr' ? 'Oglas' : 'Реклама'}
    />
  );
}
