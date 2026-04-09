import React, { useState } from 'react';
import { MessageCircle } from 'lucide-react';

interface WhatsAppShareIslandProps {
  title: string;
  url: string;
  shareCardUrl: string;
  filename: string;
}

function openWhatsAppFallback(text: string) {
  const target = `https://wa.me/?text=${encodeURIComponent(text)}`;
  window.open(target, '_blank', 'noopener,noreferrer');
}

export default function WhatsAppShareIsland({
  title,
  url,
  shareCardUrl,
  filename,
}: WhatsAppShareIslandProps) {
  const [isSharing, setIsSharing] = useState(false);

  const handleShare = async () => {
    if (isSharing) return;

    const shareText = `${title}\n${url}`;
    setIsSharing(true);

    try {
      if (typeof navigator !== 'undefined' && typeof navigator.share === 'function') {
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
              return;
            }
          }
        } catch {
          // Fall back to URL-based WhatsApp share below.
        }
      }

      openWhatsAppFallback(shareText);
    } finally {
      setIsSharing(false);
    }
  };

  return (
    <button
      type="button"
      className="cluster-share-link cluster-share-link-whatsapp"
      title="Сподели на WhatsApp"
      onClick={handleShare}
      disabled={isSharing}
    >
      <MessageCircle size={12} />
      {isSharing ? 'Подготвувам...' : 'Сподели на WhatsApp'}
    </button>
  );
}
