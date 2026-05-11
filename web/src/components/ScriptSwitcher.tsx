import React, { useState, useEffect } from 'react';

const ScriptSwitcher = () => {
    const [script, setScript] = useState('latin');

    useEffect(() => {
        const saved = localStorage.getItem('presek_script') || 'latin';
        setScript(saved);
        applyScript(saved);
    }, []);

    const toggleScript = () => {
        const next = script === 'latin' ? 'cyrillic' : 'latin';
        setScript(next);
        localStorage.setItem('presek_script', next);
        applyScript(next);
    };

    const applyScript = (mode) => {
        // Implementation logic for script switching
        // This would typically iterate over document elements or toggle a global class
        document.body.className = document.body.className.replace('script-cyrillic', '').replace('script-latin', '');
        document.body.classList.add(`script-${mode}`);
    };

    return (
        <button 
            onClick={toggleScript}
            className="flex items-center gap-1.5 px-2 py-1 bg-secondary rounded text-[9px] font-black uppercase tracking-widest hover:bg-nyt-accent hover:text-white transition-all"
        >
            {script === 'latin' ? 'LAT' : 'ЋIR'}
        </button>
    );
};

export default ScriptSwitcher;
