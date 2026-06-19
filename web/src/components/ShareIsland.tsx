import React, { useState, useEffect } from "react";
import { MessageCircle } from "lucide-react";
import { useClientTranslations } from "../i18n/clientTranslations";
import { cluster } from "../i18n/namespaces/cluster";

const FacebookIcon = ({ size = 16 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
  </svg>
);

const TwitterIcon = ({ size = 16 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 4l11.733 16h4.267l-11.733 -16z" />
    <path d="M4 20l6.768 -6.768" />
    <path d="M20 4l-6.768 6.768" />
  </svg>
);

const RedditIcon = ({ size = 16 }: { size?: number }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <circle cx="12" cy="14" r="7" />
    <circle cx="9" cy="13" r="1" fill="currentColor" />
    <circle cx="15" cy="13" r="1" fill="currentColor" />
    <path d="M9 16c1 1 2.5 1.5 3 1.5s2-.5 3-1.5" />
    <path d="M17.5 7.5l2-2" />
    <circle cx="20" cy="5" r="1.5" />
    <path d="M19 8c1.5 0 3 .5 3 2.5 0 1.5-1 2.5-2 3" />
    <path d="M5 8c-1.5 0-3 .5-3 2.5 0 1.5 1 2.5 2 3" />
    <path d="M12 7V3" />
    <circle cx="12" cy="2" r="1" />
  </svg>
);

interface ShareIslandProps {
  title: string;
  url: string;
  lang?: 'sr' | 'mk';
}

export default function ShareIsland({ title, url, lang = 'sr' }: ShareIslandProps) {
  const t = useClientTranslations(lang, cluster);
  const [currentUrl, setCurrentUrl] = useState(url);

  useEffect(() => {
    if (typeof window !== "undefined") {
      setCurrentUrl(window.location.href);
    }
  }, [url]);

  const shareText = `${title}\n${currentUrl}`;

  const shareOptions = [
    {
      name: "Facebook",
      icon: <FacebookIcon size={20} />,
      url: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(currentUrl)}`,
      hoverClass:
        "hover:text-blue-600 hover:border-blue-600 dark:hover:text-blue-400 dark:hover:border-blue-400",
    },
    {
      name: "WhatsApp",
      icon: <MessageCircle size={20} />,
      url: `https://api.whatsapp.com/send?text=${encodeURIComponent(shareText)}`,
      hoverClass:
        "hover:text-green-600 hover:border-green-600 dark:hover:text-green-400 dark:hover:border-green-400",
    },
    {
      name: "X",
      icon: <TwitterIcon size={20} />,
      url: `https://x.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(currentUrl)}`,
      hoverClass:
        "hover:text-foreground hover:border-foreground dark:hover:text-white dark:hover:border-white",
    },
    {
      name: "Reddit",
      icon: <RedditIcon size={20} />,
      url: `https://www.reddit.com/submit?url=${encodeURIComponent(currentUrl)}&title=${encodeURIComponent(title)}`,
      hoverClass:
        "hover:text-orange-600 hover:border-orange-600 dark:hover:text-orange-400 dark:hover:border-orange-400",
    },
  ];

  return (
    <span className="meta-actions-list flex flex-row items-center gap-2.5">
      {shareOptions.map((option) => (
        <a
          key={option.name}
          href={option.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`meta-action-btn flex items-center justify-center rounded-full border border-border/50 text-muted-foreground bg-background/50 hover:bg-muted/30 transition-all duration-200 ${option.hoverClass}`}
          style={{ width: "38px", height: "38px", minWidth: "38px", minHeight: "38px" }}
          title={option.name}
          aria-label={t('cluster.share_on', { network: option.name })}
        >
          {option.icon}
        </a>
      ))}
    </span>
  );
}
