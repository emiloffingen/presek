import React, { useState, useRef, useEffect } from 'react';
import {
  MessageCircle,
  Share2,
  Link2,
  Check,
  Send
} from 'lucide-react';

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

const InstagramIcon = ({ size = 14 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5" /><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" /><line x1="17.5" y1="6.5" x2="17.51" y2="6.5" />
  </svg>
);

interface ShareIslandProps {
  title: string;
  url: string;
  shareCardUrl: string;
  filename: string;
}

export default function ShareIsland({
  title,
  url,
  shareCardUrl,
  filename,
}: ShareIslandProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [copied, setCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const shareText = `${title}\n${url}`;

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleMainShare = async () => {
    if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
      setIsSharing(true);
      try {
        const response = await fetch(shareCardUrl);
        if (response.ok) {
          const blob = await response.blob();
          const file = new File([blob], filename, { type: 'image/png' });
          if (typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })) {
            await navigator.share({
              title,
              text: shareText,
              files: [file],
            });
            setIsSharing(false);
            return;
          }
        }
        // Fallback if no file sharing support
        await navigator.share({
          title,
          text: shareText,
        });
      } catch (err) {
        console.error('Error sharing:', err);
        setIsOpen(!isOpen);
      } finally {
        setIsSharing(false);
      }
    } else {
      setIsOpen(!isOpen);
    }
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(`${title}\n${url}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  const shareOptions = [
    {
      name: 'WhatsApp',
      icon: <MessageCircle size={14} />,
      url: `https://wa.me/?text=${encodeURIComponent(shareText)}`,
      color: 'hover:bg-green-50 hover:text-green-700'
    },
    {
      name: 'Facebook',
      icon: <Facebook size={14} />,
      url: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(url)}`,
      color: 'hover:bg-blue-50 hover:text-blue-700'
    },
    {
      name: 'Twitter / X',
      icon: <Twitter size={14} />,
      url: `https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}`,
      color: 'hover:bg-gray-50 hover:text-black'
    },
    {
      name: 'Reddit',
      icon: <Send size={14} />, // Using Send as a fallback for Reddit
      url: `https://www.reddit.com/submit?url=${encodeURIComponent(url)}&title=${encodeURIComponent(title)}`,
      color: 'hover:bg-orange-50 hover:text-orange-700'
    },
    {
        name: 'Instagram',
        icon: <Instagram size={14} />,
        url: `https://www.instagram.com/`, // Link to IG as no direct share web URL
        color: 'hover:bg-pink-50 hover:text-pink-700'
    }
  ];

  return (
    <div className="relative inline-block" ref={menuRef}>
      <button
        type="button"
        className="cluster-share-link"
        title="Сподели"
        onClick={handleMainShare}
        disabled={isSharing}
      >
        <Share2 size={12} />
        {isSharing ? 'Подготвувам...' : 'Сподели'}
      </button>

      {isOpen && (
        <div className="absolute left-0 bottom-full mb-2 w-48 bg-white border border-gray-200 shadow-xl z-50 overflow-hidden py-1 transform transition-all">
          <div className="px-3 py-2 border-bottom text-[0.6rem] font-black text-gray-400 uppercase tracking-widest">
            Сподели вест
          </div>
          
          {shareOptions.map((option) => (
            <a
              key={option.name}
              href={option.url}
              target="_blank"
              rel="noopener noreferrer"
              className={`flex items-center gap-3 px-3 py-2 text-[0.7rem] font-bold text-gray-700 transition-colors ${option.color}`}
              onClick={() => setIsOpen(false)}
            >
              <span className="opacity-70">{option.icon}</span>
              {option.name}
            </a>
          ))}

          <button
            type="button"
            className="w-full flex items-center gap-3 px-3 py-2 text-[0.7rem] font-bold text-gray-700 hover:bg-gray-50 transition-colors border-t border-gray-100 mt-1"
            onClick={copyToClipboard}
          >
            <span className="opacity-70">{copied ? <Check size={14} className="text-green-600" /> : <Link2 size={14} />}</span>
            {copied ? 'Копирано!' : 'Копирај линк'}
          </button>
        </div>
      )}
    </div>
  );
}
