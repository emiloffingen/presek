import { _trackInterest } from './utils.js';

export function _initPersonalization() {
    // Track interest when clicking news clusters - DO NOT prevent default
    document.addEventListener('click', (e) => {
        const clusterLink = e.target.closest('a[href^="/cluster/"]');
        if (clusterLink) {
            const cluster = clusterLink.closest('.news-cluster');
            if (cluster) {
                const catEl = cluster.querySelector('.category');
                if (catEl) {
                    const cat = catEl.textContent.replace('•', '').trim();
                    _trackInterest('topic', cat);
                }
            }
            // Allow normal link navigation - don't preventDefault!
        }
    });
}

export function _initReadingToolkit() {
    const btnInc = document.getElementById('tkInc');
    const btnDec = document.getElementById('tkDec');
    const root = document.documentElement;

    // Load saved size or default
    let currentSize = 1.15;
    try {
        currentSize = parseFloat(localStorage.getItem('presek_reading_size')) || 1.15;
    } catch (e) {}
    root.style.setProperty('--article-text-size', `${currentSize}rem`);

    if (btnInc) {
        btnInc.addEventListener('click', () => {
            if (currentSize < 1.6) {
                currentSize += 0.1;
                update();
            }
        });
    }

    if (btnDec) {
        btnDec.addEventListener('click', () => {
            if (currentSize > 0.9) {
                currentSize -= 0.1;
                update();
            }
        });
    }

    function update() {
        root.style.setProperty('--article-text-size', `${currentSize}rem`);
        try {
            localStorage.setItem('presek_reading_size', currentSize);
        } catch (e) {}
    }

    _initTTS();
}

function _initTTS() {
    const playBtn = document.getElementById('ttsPlayBtn');
    if (!playBtn || !window.speechSynthesis) {
        if (playBtn) playBtn.style.display = 'none';
        return;
    }

    let isPlaying = false;
    let utterance = null;

    playBtn.addEventListener('click', () => {
        if (isPlaying) {
            window.speechSynthesis.cancel();
            isPlaying = false;
            playBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
            return;
        }

        const title = document.querySelector('.nyt-title')?.textContent || '';
        const summaryNodes = document.querySelectorAll('.cluster-summary p');
        let text = title + '. ';
        summaryNodes.forEach(p => text += p.textContent + ' ');

        if (!text.trim()) return;

        utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'mk-MK'; // Macedonian language tag

        utterance.onend = () => {
            isPlaying = false;
            playBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
        };

        window.speechSynthesis.speak(utterance);
        isPlaying = true;
        // Show stop icon
        playBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>';
    });
}
export function _initProgressBar() {
    const bar = document.getElementById('readingProgress');
    if (!bar) return;

    window.addEventListener('scroll', () => {
        const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
        const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
        const scrolled = (winScroll / height) * 100;
        bar.style.width = scrolled + "%";
    }, { passive: true });
}

export function _initPrivacyBanner() {
    const banner = document.getElementById('privacyBanner');
    const accept = document.getElementById('privacyAccept');
    const reject = document.getElementById('privacyReject');

    let consent = null;
    try {
        consent = localStorage.getItem('presek_cookie_consent');
    } catch (e) {}

    if (!consent) {
        setTimeout(() => {
            if (banner) banner.classList.add('active');
        }, 2000);
    }

    if (accept) {
        accept.addEventListener('click', () => {
            try { localStorage.setItem('presek_cookie_consent', 'accepted'); } catch(e) {}
            if (banner) banner.classList.remove('active');
        });
    }
    
    if (reject) {
        reject.addEventListener('click', () => {
            try { localStorage.setItem('presek_cookie_consent', 'rejected'); } catch(e) {}
            if (banner) banner.classList.remove('active');
        });
    }
}
