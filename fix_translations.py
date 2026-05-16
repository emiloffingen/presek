import re

with open('web/src/components/SearchIsland.tsx', 'r') as f:
    content = f.read()

replacements = [
    (
        r'<p className="text-\[9px\] font-black uppercase tracking-widest text-muted-foreground mb-4">MEDIUMSKI PRISUSTVO</p>',
        r'<p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-4">{lang === \'sr\' ? \'MEDIJSKO PRISUSTVO\' : \'МЕДИУМСКО ПРИСУСТВО\'}</p>'
    ),
    (
        r'<p className="text-xs font-bold">\{selectedItem\.data\.total_mentions\} spomenuvanja vo arhivata</p>',
        r'<p className="text-xs font-bold">{selectedItem.data.total_mentions} {lang === \'sr\' ? \'pominjanja u arhivi\' : \'споменувања во архивата\'}</p>'
    ),
    (
        r'<p className="font-serif font-black text-lg text-emerald-600">POZITIVEN</p>',
        r'<p className="font-serif font-black text-lg text-emerald-600">{lang === \'sr\' ? \'POZITIVAN\' : \'ПОЗИТИВЕН\'}</p>'
    ),
    (
        r'VIDI SITE vesti <ExternalLink size=\{16\} />',
        r'{lang === \'sr\' ? \'VIDI SVE VESTI\' : \'ВИДИ СИТЕ ВЕСТИ\'} <ExternalLink size={16} />'
    ),
    (
        r'IZVRSI AKCIJA\s*</button>',
        r'{lang === \'sr\' ? \'IZVRŠI AKCIJU\' : \'ИЗВРШИ АКЦИЈА\'}\n                    </button>'
    ),
    (
        r'<p className="font-serif font-black text-xl mb-1">Pregled</p>',
        r'<p className="font-serif font-black text-xl mb-1">{lang === \'sr\' ? \'Pregled\' : \'Преглед\'}</p>'
    ),
    (
        r'<p className="text-\[10px\] font-black uppercase tracking-widest">Izberete stavka za detali</p>',
        r'<p className="text-[10px] font-black uppercase tracking-widest">{lang === \'sr\' ? \'Izaberite stavku za detalje\' : \'Изберете ставка за детали\'}</p>'
    ),
    (
        r'<span className="flex items-center gap-2"><kbd className="px-1\.5 py-0\.5 bg-background border border-border rounded">ENTER</kbd> IZBERI</span>',
        r'<span className="flex items-center gap-2"><kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ENTER</kbd> {lang === \'sr\' ? \'IZABERI\' : \'ИЗБЕРИ\'}</span>'
    ),
    (
        r'<kbd className="px-1\.5 py-0\.5 bg-background border border-border rounded">↓</kbd> NAVIGACIJA</span>',
        r'<kbd className="px-1.5 py-0.5 bg-background border border-border rounded">↓</kbd> {lang === \'sr\' ? \'NAVIGACIJA\' : \'НАВИГАЦИЈА\'}</span>'
    ),
    (
        r'<kbd className="px-1\.5 py-0\.5 bg-background border border-border rounded">ESC</kbd> ZATVORI</span>',
        r'<kbd className="px-1.5 py-0.5 bg-background border border-border rounded">ESC</kbd> {lang === \'sr\' ? \'ZATVORI\' : \'ЗАТВОРИ\'}</span>'
    ),
    (
        r'<span className="flex items-center gap-1\.5"><Globe size=\{12\} /> GLOBALNA PRETRAGA</span>',
        r'<span className="flex items-center gap-1.5"><Globe size={12} /> {lang === \'sr\' ? \'GLOBALNA PRETRAGA\' : \'ГЛОБАЛНО ПРЕБАРУВАЊЕ\'}</span>'
    ),
    (
        r'<span className="flex items-center gap-1\.5"><Sparkles size=\{12\} /> AI ASISTENCIJA</span>',
        r'<span className="flex items-center gap-1.5"><Sparkles size={12} /> AI {lang === \'sr\' ? \'ASISTENCIJA\' : \'АСИСТЕНЦИЈА\'}</span>'
    ),
    (
        r'<p className="text-\[9px\] font-black uppercase tracking-widest text-muted-foreground mb-1">izvori</p>',
        r'<p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">{lang === \'sr\' ? \'izvori\' : \'извори\'}</p>'
    ),
    (
        r'<p className="text-\[9px\] font-black uppercase tracking-widest text-muted-foreground mb-1">SKOR</p>',
        r'<p className="text-[9px] font-black uppercase tracking-widest text-muted-foreground mb-1">{lang === \'sr\' ? \'SKOR\' : \'СКОР\'}</p>'
    )
]

for old, new in replacements:
    content = re.sub(old, new, content)

with open('web/src/components/SearchIsland.tsx', 'w') as f:
    f.write(content)
