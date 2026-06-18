(function presekAudio() {
    function initPresekAudioPlayers() {
        document.querySelectorAll('.presek-audio-player').forEach((wrapper) => {
            if (!(wrapper instanceof HTMLElement) || wrapper.dataset.audioBound === 'true') return;

            const playBtn = wrapper.querySelector('.audio-play-toggle');
            const audio = wrapper.querySelector('.audio-element');
            const progress = wrapper.querySelector('.audio-progress');
            const fill = wrapper.querySelector('.audio-progress-fill');
            const buffer = wrapper.querySelector('.audio-progress-buffer');
            const current = wrapper.querySelector('.audio-current');
            const duration = wrapper.querySelector('.audio-duration');
            const state = wrapper.querySelector('.audio-state');
            const speed = wrapper.querySelector('.audio-speed');
            const skips = wrapper.querySelectorAll('.audio-skip');
            if (!(playBtn instanceof HTMLButtonElement) || !(audio instanceof HTMLAudioElement) || !(progress instanceof HTMLButtonElement) || !(fill instanceof HTMLElement) || !(buffer instanceof HTMLElement) || !(current instanceof HTMLElement) || !(duration instanceof HTMLElement) || !(state instanceof HTMLElement) || !(speed instanceof HTMLButtonElement)) return;

            wrapper.dataset.audioBound = 'true';

            const lang = wrapper.dataset.lang || 'sr';
            const copy = {
                idle: lang === 'mk' ? 'Подготвено за слушање' : 'Spremno za slušanje',
                loading: lang === 'mk' ? 'Подготвувам аудио...' : 'Pripremam audio...',
                playing: lang === 'mk' ? 'Се пушта' : 'Se pušta',
                paused: lang === 'mk' ? 'Паузирано' : 'Pauzirano',
                error: lang === 'mk' ? 'Грешка при вчитување.' : 'Greška pri učitavanju.',
                play: lang === 'mk' ? 'Пушти аудио' : 'Pusti audio',
                pause: lang === 'mk' ? 'Паузирај аудио' : 'Pauziraj audio',
            };

            const speeds = [1, 1.25, 1.5, 2];
            let speedIndex = 0;

            function formatTime(value) {
                if (!Number.isFinite(value) || value < 0) return '0:00';
                const total = Math.floor(value);
                const minutes = Math.floor(total / 60);
                const seconds = String(total % 60).padStart(2, '0');
                return `${minutes}:${seconds}`;
            }

            function setState(next) {
                wrapper.dataset.state = next;
                playBtn.disabled = next === 'loading';
                state.textContent = copy[next] || copy.idle;
                playBtn.setAttribute('aria-label', next === 'playing' ? copy.pause : copy.play);
                playBtn.setAttribute('title', next === 'playing' ? copy.pause : copy.play);
            }

            function updateProgress() {
                const mediaDuration = audio.duration;
                current.textContent = formatTime(audio.currentTime);
                duration.textContent = formatTime(mediaDuration);

                if (Number.isFinite(mediaDuration) && mediaDuration > 0) {
                    fill.style.width = `${Math.min(100, (audio.currentTime / mediaDuration) * 100)}%`;
                    if (audio.buffered.length > 0) {
                        const bufferedEnd = audio.buffered.end(audio.buffered.length - 1);
                        buffer.style.width = `${Math.min(100, (bufferedEnd / mediaDuration) * 100)}%`;
                    }
                }
            }

            function resolveAudioUrl(audioUrl) {
                if (/^https?:\/\//i.test(audioUrl)) return audioUrl;
                return new URL(
                    audioUrl,
                    new URL(wrapper.dataset.apiEndpoint || window.location.href, window.location.href).origin
                ).href;
            }

            async function ensureAudioLoaded() {
                if (audio.currentSrc || audio.getAttribute('src')) return;
                setState('loading');

                const response = await fetch(wrapper.dataset.apiEndpoint);
                if (!response.ok) throw new Error(`Audio request failed: ${response.status}`);
                const data = await response.json();
                if (data.status !== 'success' || !data.audio_url) {
                    throw new Error(data.message || 'Missing audio URL');
                }
                audio.src = resolveAudioUrl(data.audio_url);
                audio.load();
            }

            async function playAudio() {
                try {
                    document.querySelectorAll('.presek-audio-player .audio-element').forEach((otherAudio) => {
                        if (otherAudio !== audio && otherAudio instanceof HTMLAudioElement) otherAudio.pause();
                    });
                    await ensureAudioLoaded();
                    await audio.play();
                    setState('playing');
                } catch (error) {
                    console.error('Failed to play audio:', error);
                    setState('error');
                }
            }

            playBtn.addEventListener('click', async () => {
                if (wrapper.dataset.state === 'loading') return;
                if (audio.paused) {
                    await playAudio();
                } else {
                    audio.pause();
                }
            });

            progress.addEventListener('click', (event) => {
                if (!Number.isFinite(audio.duration) || audio.duration <= 0) return;
                const rect = progress.getBoundingClientRect();
                const pct = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
                audio.currentTime = pct * audio.duration;
                updateProgress();
            });

            skips.forEach((button) => {
                if (!(button instanceof HTMLButtonElement)) return;
                button.addEventListener('click', () => {
                    const delta = Number(button.dataset.skip || 0);
                    audio.currentTime = Math.min(Math.max(audio.currentTime + delta, 0), audio.duration || Infinity);
                    updateProgress();
                });
            });

            speed.addEventListener('click', () => {
                speedIndex = (speedIndex + 1) % speeds.length;
                audio.playbackRate = speeds[speedIndex];
                speed.textContent = `${speeds[speedIndex]}x`;
                speed.title = `${speeds[speedIndex]}x`;
            });

            audio.addEventListener('loadedmetadata', updateProgress);
            audio.addEventListener('progress', updateProgress);
            audio.addEventListener('timeupdate', updateProgress);
            audio.addEventListener('play', () => setState('playing'));
            audio.addEventListener('pause', () => setState(audio.currentTime > 0 && !audio.ended ? 'paused' : 'idle'));
            audio.addEventListener('ended', () => {
                audio.currentTime = 0;
                fill.style.width = '0%';
                setState('idle');
            });
            audio.addEventListener('error', () => setState('error'));

            async function prefetchAudioMetadata() {
                if (audio.currentSrc || audio.getAttribute('src')) {
                    audio.load();
                    return;
                }
                try {
                    await ensureAudioLoaded();
                    updateProgress();
                } catch (error) {
                    console.warn('Failed to prefetch audio metadata:', error);
                }
            }

            if (audio.getAttribute('src')) {
                audio.addEventListener('loadedmetadata', updateProgress, { once: true });
                audio.load();
            } else {
                prefetchAudioMetadata();
            }
            setState('idle');
        });
    }

    document.addEventListener('DOMContentLoaded', initPresekAudioPlayers);
    document.addEventListener('astro:page-load', initPresekAudioPlayers);
})();
