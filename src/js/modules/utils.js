export function _esc(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = String(str);
    return d.innerHTML;
}

export function _relativeTime(dateStr) {
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return '';
        const now = new Date();
        const diff = (now - d) / 1000;
        if (diff < 60) return 'сега';
        if (diff < 3600) return `${Math.floor(diff / 60)}м`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}ч`;
        return d.toLocaleDateString('mk-MK', { day: 'numeric', month: 'short' });
    } catch (e) { return ''; }
}

export function _updateMacedonianDate() {
    const el = document.getElementById('currentDate');
    if (!el) return;
    const now = new Date();
    const options = { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' };
    try {
        let dateStr = now.toLocaleDateString('mk-MK', options);
        // Capitalize every word
        dateStr = dateStr.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
        el.textContent = dateStr;
    } catch (e) { 
        console.error("Date formatting error", e);
        el.textContent = now.toDateString(); 
    }
}

export function _trackInterest(type, value) {
    const key = `presek_interests_${type}`;
    let data = {};
    try {
        data = JSON.parse(localStorage.getItem(key) || '{}');
    } catch(e) {}
    data[value] = (data[value] || 0) + 1;
    try {
        localStorage.setItem(key, JSON.stringify(data));
    } catch(e) {}
}

export function _getTopInterests(type) {
    const key = `presek_interests_${type}`;
    try {
        const data = JSON.parse(localStorage.getItem(key) || '{}');
        return Object.entries(data)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 3)
            .map(e => e[0])
            .join(',');
    } catch(e) { return ''; }
}

export function _saveSearchToHistory(query) {
    if (!query) return;
    try {
        let history = JSON.parse(localStorage.getItem('presek_search_history') || '[]');
        history = history.filter(h => h.toLowerCase() !== query.toLowerCase());
        history.unshift(query);
        history = history.slice(0, 5);
        localStorage.setItem('presek_search_history', JSON.stringify(history));
        _renderSearchHistory();
    } catch (e) {}
}

export function _renderSearchHistory() {
    const container = document.getElementById('searchHistory');
    const section = document.getElementById('searchHistorySection');
    if (!container || !section) return;

    try {
        const history = JSON.parse(localStorage.getItem('presek_search_history') || '[]');
        if (history.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        container.innerHTML = history.map(h => `
            <div class="suggestion-item history-item" data-search="${encodeURIComponent(h)}">
                <span style="opacity: 0.5; margin-right: 6px;">⏳</span> ${_esc(h)}
            </div>
        `).join('');

        container.querySelectorAll('.history-item').forEach(el => {
            el.addEventListener('click', () => {
                const query = decodeURIComponent(el.dataset.search);
                if (window.app) window.app.setSearch(query);
                const searchOverlay = document.getElementById('searchOverlay');
                if (searchOverlay) searchOverlay.classList.remove('active');
            });
        });
    } catch (e) {
        section.style.display = 'none';
    }
}

export function updateClock() {
    const el = document.getElementById('live-clock');
    if (!el) return;
    el.textContent = new Date().toLocaleTimeString('mk-MK', { hour: '2-digit', minute: '2-digit' });
}

export function showToast(msg) {
    const toast = document.getElementById('newsToast');
    const toastMsg = document.getElementById('toastMsg');
    if (!toast) return;
    
    if (toastMsg) toastMsg.textContent = msg.toUpperCase();
    toast.classList.add('active');
    
    // Auto-hide after 10 seconds
    setTimeout(() => toast.classList.remove('active'), 10000);
}

export function isFollowing(type, value) {
    try {
        const data = JSON.parse(localStorage.getItem(`presek_follow_${type}`) || '[]');
        return data.includes(value);
    } catch(e) { return false; }
}

export function toggleFollow(type, value) {
    try {
        const key = `presek_follow_${type}`;
        let data = JSON.parse(localStorage.getItem(key) || '[]');
        const idx = data.indexOf(value);
        if (idx === -1) data.push(value);
        else data.splice(idx, 1);
        localStorage.setItem(key, JSON.stringify(data));
    } catch(e) {}
}

export function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
