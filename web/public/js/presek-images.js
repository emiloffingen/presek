(function presekImages() {
  const handleImageLoad = (img) => {
    img.classList.add('is-loaded');
    const imageWrap = img.closest('.image-wrap');
    if (imageWrap) {
      imageWrap.setAttribute('data-image-state', 'ready');
    }
    const leadFrame = img.closest('.lead-media-frame');
    if (leadFrame) {
      leadFrame.classList.add('media-ready');
    }
  };

  const emergencyFallbackUrl = () => {
    const pageLang = document.documentElement.lang === 'mk' ? 'mk' : 'sr';
    const cat = pageLang === 'mk' ? 'вести' : 'vesti';
    const proxyBase = document.documentElement.dataset.proxyBase || '';
    return `${proxyBase}/proxy?cat=${encodeURIComponent(cat)}&lang=${pageLang}&w=720`;
  };

  const getSourceInitials = (source) => {
    const cleaned = source.trim();
    if (!cleaned) return 'P';
    const words = cleaned.split(/[\s|·\-–—/]+/).filter(Boolean);
    if (words.length >= 2) {
      return words.slice(0, 2).map((word) => word[0] || '').join('').toUpperCase();
    }
    return cleaned.slice(0, 2).toUpperCase();
  };

  const renderEditorialImageFallback = (imageWrap) => {
    if (imageWrap.querySelector('.topic-fallback-card--editorial')) return;
    const source = imageWrap.getAttribute('data-fallback-source') || '';
    const category = imageWrap.getAttribute('data-fallback-category') || '';
    const label = imageWrap.getAttribute('data-fallback-label') || category || 'Presek';
    const tint = imageWrap.getAttribute('data-fallback-tint') || '#c45c26';
    const initials = getSourceInitials(source);
    imageWrap.classList.add('image-wrap-fallback');
    imageWrap.setAttribute('data-image-state', 'fallback');
    imageWrap.style.setProperty('--placeholder-bg', tint);
    const link = imageWrap.querySelector('a');
    if (!link) return;

    link.replaceChildren();
    const card = document.createElement('div');
    card.className = 'article-image-placeholder topic-fallback-card topic-fallback-card--editorial topic-fallback-card--compact';

    const mark = document.createElement('span');
    mark.className = 'article-image-placeholder-mark';
    mark.setAttribute('aria-hidden', 'true');
    mark.textContent = initials;

    const labelEl = document.createElement('p');
    labelEl.className = 'article-image-placeholder-label';
    labelEl.textContent = label;

    const sourceEl = document.createElement('p');
    sourceEl.className = 'article-image-placeholder-source';
    sourceEl.textContent = source;

    card.append(mark, labelEl, sourceEl);
    link.appendChild(card);
  };

  const handleImageError = (img) => {
    const markArticleImageFailed = () => {
      const imageWrap = img.closest('.image-wrap');
      if (imageWrap && imageWrap.hasAttribute('data-fallback-source')) {
        renderEditorialImageFallback(imageWrap);
        return;
      }
      if (imageWrap) {
        imageWrap.setAttribute('data-image-state', 'failed');
      }
      const article = img.closest('.nyt-article');
      if (article) {
        article.classList.add('image-failed');
      }
    };

    if (img.classList.contains('article-image') && !img.classList.contains('article-image-fallback')) {
      img.removeAttribute('srcset');
      const fallbackUrl = img.getAttribute('data-fallback-url') || emergencyFallbackUrl();
      img.src = fallbackUrl;
      img.classList.add('is-loaded', 'article-image-fallback');
      const imageWrap = img.closest('.image-wrap');
      if (imageWrap) {
        imageWrap.classList.add('image-wrap-fallback');
        imageWrap.setAttribute('data-image-state', 'fallback');
      }
      return;
    }
    if (img.classList.contains('article-image') && img.classList.contains('article-image-fallback')) {
      if (img.dataset.emergencyTried === '1') {
        const imageWrap = img.closest('.image-wrap');
        if (imageWrap) {
          renderEditorialImageFallback(imageWrap);
        } else {
          markArticleImageFailed();
        }
        return;
      }
      img.dataset.emergencyTried = '1';
      img.src = emergencyFallbackUrl();
      return;
    }
    if (img.classList.contains('lead-media-image') && !img.classList.contains('lead-media-fallback-image')) {
      img.removeAttribute('srcset');
      const fallbackUrl = img.getAttribute('data-fallback-url') || emergencyFallbackUrl();
      img.src = fallbackUrl;
      img.classList.add('is-loaded', 'lead-media-fallback-image');
      const parent = img.parentElement;
      if (parent) {
        parent.classList.add('media-ready', 'lead-media-frame-proxy-fallback');
      }
      return;
    }
    if (img.classList.contains('lead-media-image') && img.classList.contains('lead-media-fallback-image')) {
      const parent = img.parentElement;
      if (parent) {
        parent.classList.add('media-ready', 'media-failed');
      }
      return;
    }
    if (img.classList.contains('hero-main-image') && !img.classList.contains('article-image-fallback')) {
      img.removeAttribute('srcset');
      const fallbackUrl = img.getAttribute('data-fallback-url') || emergencyFallbackUrl();
      img.src = fallbackUrl;
      img.classList.add('is-loaded', 'article-image-fallback');
      const card = img.closest('.hero-visual-card');
      if (card) {
        card.classList.add('is-weak', 'is-proxy-fallback');
      }
    }
  };

  document.addEventListener('load', (event) => {
    const target = event.target;
    if (target && target.tagName === 'IMG') {
      handleImageLoad(target);
    }
  }, true);

  document.addEventListener('error', (event) => {
    const target = event.target;
    if (target && target.tagName === 'IMG') {
      handleImageError(target);
    }
  }, true);

  const checkAllImages = () => {
    document.querySelectorAll('img').forEach((img) => {
      if (img.complete) {
        if (img.naturalWidth === 0) {
          handleImageError(img);
        } else {
          handleImageLoad(img);
        }
      }
    });
  };

  checkAllImages();
  document.addEventListener('astro:page-load', checkAllImages);
})();
