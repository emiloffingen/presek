import React from 'react';
import { MessageCircle } from 'lucide-react';

const FacebookIcon = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
  </svg>
);

const TwitterIcon = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 4l11.733 16h4.267l-11.733 -16z" /><path d="M4 20l6.768 -6.768" /><path d="M20 4l-6.768 6.768" />
  </svg>
);

const RedditIcon = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="14" r="7" /><circle cx="9" cy="13" r="1" fill="currentColor" /><circle cx="15" cy="13" r="1" fill="currentColor" /><path d="M9 16c1 1 2.5 1.5 3 1.5s2-.5 3-1.5" /><path d="M17.5 7.5l2-2" /><circle cx="20" cy="5" r="1.5" /><path d="M19 8c1.5 0 3 .5 3 2.5 0 1.5-1 2.5-2 3" /><path d="M5 8c-1.5 0-3 .5-3 2.5 0 1.5 1 2.5 2 3" /><path d="M12 7V3" /><circle cx="12" cy="2" r="1" />
  </svg>
);

interface ShareIslandProps {
  title: string;
  url: string;
}

export default function ShareIsland({
  title,
  url,
}: ShareIslandProps) {
  const shareText = `${title}\n${url}`;

  const shareOptions = [
    {
      name: 'Facebook',
      icon: <FacebookIcon size={14} />,
      url: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
      hoverClass: 'share-icon-facebook',
    },
    {
      name: 'WhatsApp',
      icon: <MessageCircle size={14} />,
      url: `https://wa.me/?text=${encodeURIComponent(shareText)}`,
      hoverClass: 'share-icon-whatsapp',
    },
    {
      name: 'Twitter / X',
      icon: <TwitterIcon size={14} />,
      url: `https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}`,
      hoverClass: 'share-icon-twitter',
    },
    {
      name: 'Reddit',
      icon: <RedditIcon size={14} />,
      url: `https://www.reddit.com/submit?url=${encodeURIComponent(url)}&title=${encodeURIComponent(title)}`,
      hoverClass: 'share-icon-reddit',
    },
  ];

  return (
    <span className="share-icons flex flex-row items-center gap-[var(--grid-gap)]">
      {shareOptions.map((option) => (
        <a
          key={option.name}
          href={option.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`share-icon ${option.hoverClass}`}
          title={option.name}
          aria-label={`Spodeli na ${option.name}`}
        >
          {option.icon}
        </a>
      ))}
    </span>
  );
}
