export function initTheme() {
    try {
        const saved = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const isLight = saved ? saved === 'light' : !prefersDark;
        
        document.documentElement.classList.toggle('light', isLight);
        document.body.classList.toggle('light', isLight);
        
        const meta = document.getElementById('themeMeta');
        if (meta) meta.content = isLight ? '#FFFFFF' : '#0A0A0A';
    } catch (e) { console.error("Theme init error", e); }
}

export function setupThemeEvents() {
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const isLight = document.documentElement.classList.toggle('light');
            try {
                localStorage.setItem('theme', isLight ? 'light' : 'dark');
            } catch (e) {}
            // Sync cookie so server-side body class stays consistent on next load
            document.cookie = `theme=${isLight ? 'light' : 'dark'}; path=/; max-age=${60 * 60 * 24 * 365}; SameSite=Lax`;

            // Update theme color meta
            const meta = document.getElementById('themeMeta');
            if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';

            document.body.classList.toggle('light', isLight);

            // Dispatch event for other components (like charts)
            window.dispatchEvent(new Event('themeChanged'));

            // Add a small rotation effect to the button
            themeToggle.style.transform = 'rotate(15deg)';
            setTimeout(() => themeToggle.style.transform = '', 200);
        });
    }

    // Auto System Theme Sync
    const sysTheme = window.matchMedia('(prefers-color-scheme: light)');
    const applySystemTheme = (e) => {
        let hasSavedTheme = false;
        try {
            hasSavedTheme = !!localStorage.getItem('theme');
        } catch (err) {}

        if (!hasSavedTheme) {
            const isLight = e.matches;
            document.documentElement.classList.toggle('light', isLight);
            document.body.classList.toggle('light', isLight);
            const meta = document.getElementById('themeMeta');
            if (meta) meta.content = isLight ? '#F3F5F7' : '#0A0C0E';
        }
    };
    if (sysTheme.addEventListener) sysTheme.addEventListener('change', applySystemTheme);
    else sysTheme.addListener(applySystemTheme); // Legacy support
}
