# Milestone R1: Interactive Stance Visualizations — Analysis and Implementation Report

This report provides a concrete implementation strategy for **Milestone R1: Interactive Stance Visualizations** on the Presek platform. It documents how the payload data (`perspectives`, `narrative_diversity`, `stance_vectors`) is retrieved, details the styling and design parameters for the new widgets, and provides code blueprints for the implementation.

---

## 1. Current Payload Retrieval & Analysis

### A. Location & Scope
- **File**: `web/src/pages/cluster/[slug].astro`
- **Data Source**: FastAPI endpoint `/cluster/{id}?lang={lang}` (defined in `routes/news.py`).
- **Astro Frontmatter Retrieval** (lines 88–101):
  ```javascript
  const res = await fetch(`${API_URL}/cluster/${id}?lang=${lang}`);
  const payload = await res.json();
  cluster = payload.data;
  ```

### B. Payload Structure Inspection
By investigating `web/src/types.ts` and `nlp/local_analyst.py`, the exact structures for the relevant keys in the cluster payload were determined:

1. **`perspectives`**:
   - **Type**: `ClusterSummary[]` (where `ClusterSummary` has `angle` and `content`).
   - **Structure**:
     ```json
     [
       { "angle": "različiti akcenti", "content": "RTS naglašava ekonomski stabilizacioni plan..." },
       { "angle": "reakcije i odgovori", "content": "Danas prenosi kritiku opozicionih lidera..." }
     ]
     ```
   - **Current extraction**: Extracted at line 156 as `const perspectives = cluster?.perspectives || [];`.

2. **`narrative_diversity`**:
   - **Type**: Represented by the `PluralismResponse` schema from `nlp/local_analyst.py`.
   - **Structure**:
     ```json
     {
       "score": 75,
       "verdict": "Visok pluralizam sa raznovrsnim izvorima i suprotstavljenim stavovima.",
       "bias_detected": false
     }
     ```
   - **Current extraction**: Not extracted to a dedicated frontmatter variable. It is only accessed deeply inside `evidenceItems` (line 464) as `cluster.narrative_diversity?.verdict`.

3. **`stance_vectors`** (Implicitly needed for interactive stance layout):
   - **Type**: `Record<string, number>` mapping source names to average sentiment scores (ranging from `-1.0` (critical/negative) to `1.0` (supportive/positive)).
   - **Current extraction**: Not extracted in Astro page, but returned by API as `cluster.stance_vectors`.

---

## 2. Interactive Widget Design

We recommend building an interactive React component (island) `InteractiveStanceWidget.tsx` and rendering it with client-side interactivity (`client:visible`). This widget will integrate:
1. **A Circular Gauge / Score Dial**: Visualizing the `narrative_diversity.score` and indicating if bias is detected.
2. **A Stance Distribution Spectrum**: A horizontal gradient bar representing the stance spectrum from negative/critical tone (`-1.0`) to positive/supportive tone (`1.0`), mapping each source's stance from `stance_vectors` onto this line.
3. **Perspective Nuance Cards**: Clickable cards representing each perspective angle. Clicking or hovering over a card highlights the sources that contribute to that perspective.

### A. Layout Structure & Glassmorphism Styling
The widgets will follow the Presek premium aesthetic, incorporating glassmorphism (`backdrop-filter`) and the signature copper theme accent (`--presek-mark`).

### B. CSS Variables & Theme Specification
Add the following CSS variables to `web/src/styles/cluster-page.css` or `web/src/styles/presek-identity.css` to govern the visual presentation:

```css
/* Custom variables for Interactive Stance Widgets */
:root {
  --stance-hue: 24; /* Presek signature copper hue (#c45c26) */
  --stance-sat: 67%;
  
  /* Glassmorphism panel variables */
  --stance-glass-bg: hsla(var(--stance-hue), 12%, 98%, 0.65);
  --stance-glass-border: hsla(var(--stance-hue), 10%, 20%, 0.08);
  --stance-glass-shadow: 0 8px 32px 0 rgba(196, 92, 38, 0.06);

  /* Spectrum Gradient Colors (Critical/Neutral/Objective) */
  --stance-grad-left: hsl(350, 75%, 48%);   /* Red (Critical/Sensational) */
  --stance-grad-center: hsl(24, 70%, 50%);  /* Copper (Neutral/Balanced) */
  --stance-grad-right: hsl(150, 65%, 40%);  /* Green (Objective/Supportive) */

  /* Interactive states */
  --stance-transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  --stance-marker-hover: scale(1.2);
}

.dark {
  /* Glassmorphism panel dark variables */
  --stance-glass-bg: hsla(var(--stance-hue), 8%, 10%, 0.7);
  --stance-glass-border: hsla(var(--stance-hue), 12%, 80%, 0.12);
  --stance-glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.35);

  /* Spectrum Gradient Colors (Dark Mode) */
  --stance-grad-left: hsl(350, 75%, 55%);
  --stance-grad-center: hsl(24, 70%, 60%);
  --stance-grad-right: hsl(150, 65%, 48%);
}
```

---

## 3. Implementation Blueprints

### A. TypeScript Interface Updates (`web/src/types.ts`)
Update `ClusterDetail` (around line 170) to properly type all narrative and stance fields:
```typescript
export interface ClusterDetail extends NewsCluster {
  // ... existing fields ...
  perspectives: ClusterSummary[];
  narrative_diversity?: {
    score?: number;
    verdict?: string;
    bias_detected?: boolean;
  };
  stance_vectors?: Record<string, number>;
  editorial_divergence?: number;
}
```

### B. Astro Frontmatter Update (`web/src/pages/cluster/[slug].astro`)
Extract the required variables from the cluster payload and import the interactive component:
```astro
---
// ... existing imports ...
import InteractiveStanceWidget from '../../components/Cluster/InteractiveStanceWidget.tsx';

// ... existing code ...
const perspectives = cluster?.perspectives || [];
const narrativeDiversity = cluster?.narrative_diversity || null;
const stanceVectors = cluster?.stance_vectors || {};
const editorialDivergence = cluster?.editorial_divergence || 0;
// ...
---
```

Locate the rendering place inside the main column (around line 709–722) and place the widget:
```astro
{showCredibilitySection && (
  <ClusterAnalysisSection t={translate}>
    <!-- Custom Interactive Stance Widget -->
    {narrativeDiversity && (
      <InteractiveStanceWidget
        client:visible
        lang={lang}
        narrativeDiversity={narrativeDiversity}
        perspectives={perspectives}
        stanceVectors={stanceVectors}
        editorialDivergence={editorialDivergence}
        articles={cluster.articles}
      />
    )}

    <!-- Existing analysis components (fallback or complementary) -->
    <CredibilityAnalysis
      hasFactcheck={hasFactcheck}
      verificationReport={verificationReport}
      perspectives={perspectives}
      hasCitationSources={hasCitationSources}
      showPerspectives={showPerspectivesBlock}
      consensusNote={consensusNote}
      pluralismScore={cluster?.pluralism_score}
      toneAnalysis={sentimentData?.tone_analysis}
    />
  </ClusterAnalysisSection>
)}
```

### C. Proposed Widget Component (`web/src/components/Cluster/InteractiveStanceWidget.tsx`)
Create this new component to process and render the stances:
```tsx
import React, { useState } from 'react';

interface Props {
  lang: string;
  narrativeDiversity: {
    score?: number;
    verdict?: string;
    bias_detected?: boolean;
  };
  perspectives: Array<{ angle: string; content: string }>;
  stanceVectors: Record<string, number>;
  editorialDivergence: number;
  articles: Array<{ id: number; title: string; source: string; link: string }>;
}

export default function InteractiveStanceWidget({
  lang,
  narrativeDiversity,
  perspectives,
  stanceVectors,
  editorialDivergence,
  articles,
}: Props) {
  const [hoveredSource, setHoveredSource] = useState<string | null>(null);

  // Helper to map stance sentiment [-1.0, 1.0] to visual percentage [0%, 100%]
  const getPositionPercent = (score: number) => {
    return Math.max(0, Math.min(100, ((score + 1) / 2) * 100));
  };

  return (
    <div className="stance-widget-container p-6 mb-8 border rounded-lg backdrop-blur-[var(--glass-blur)] bg-[var(--stance-glass-bg)] border-[var(--stance-glass-border)] shadow-[var(--stance-glass-shadow)] transition-[var(--stance-transition)]">
      {/* Title & Diversity Index Dial */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h3 className="font-serif text-lg font-black tracking-tight text-foreground">
            {lang === 'sr' ? 'Medijski Pluralizam i Perspektive' : 'Медиумски Плурализам и Перспективи'}
          </h3>
          <p className="text-xs text-muted-foreground mt-1">{narrativeDiversity.verdict}</p>
        </div>
        
        <div className="flex items-center gap-3 bg-secondary/10 px-3 py-1.5 rounded-full border border-border/30">
          <span className="text-[10px] font-black uppercase tracking-wider text-muted-foreground">
            {lang === 'sr' ? 'Indeks Divergencije:' : 'Индекс на Дивергенција:'}
          </span>
          <span className="font-serif font-black text-sm text-presek-mark">{editorialDivergence}</span>
        </div>
      </div>

      {/* Stance Distribution Spectrum */}
      <div className="spectrum-wrapper py-6 relative">
        <div 
          className="h-2 rounded-full w-full relative" 
          style={{ background: 'linear-gradient(90deg, var(--stance-grad-left) 0%, var(--stance-grad-center) 50%, var(--stance-grad-right) 100%)' }}
        >
          {/* Render Source Markers */}
          {Object.entries(stanceVectors).map(([sourceName, score]) => {
            const leftOffset = getPositionPercent(score);
            const isHovered = hoveredSource === sourceName;
            return (
              <button
                key={sourceName}
                className={`absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-background cursor-pointer shadow-md transition-all z-20 ${
                  isHovered ? 'scale-125 border-presek-mark bg-presek-mark' : 'bg-foreground'
                }`}
                style={{ left: `${leftOffset}%` }}
                onMouseEnter={() => setHoveredSource(sourceName)}
                onMouseLeave={() => setHoveredSource(null)}
                aria-label={`Source: ${sourceName}, Score: ${score}`}
              />
            );
          })}
        </div>

        {/* Labels below gradient */}
        <div className="flex justify-between text-[10px] font-bold text-muted-foreground uppercase tracking-wider mt-3">
          <span>{lang === 'sr' ? 'Kritički/Skeptično' : 'Критички/Скептично'}</span>
          <span>{lang === 'sr' ? 'Neutralno' : 'Неутрално'}</span>
          <span>{lang === 'sr' ? 'Objektivno/Podrška' : 'Објективно/Поддршка'}</span>
        </div>

        {/* Dynamic Tooltip */}
        {hoveredSource && (
          <div className="absolute top-12 left-1/2 -translate-x-1/2 bg-card border border-border p-3 shadow-lg max-w-xs z-30 pointer-events-none transition-opacity duration-200">
            <h4 className="font-bold text-xs text-presek-mark uppercase tracking-wider mb-1">{hoveredSource}</h4>
            <p className="text-[11px] text-muted-foreground">
              Stance: {stanceVectors[hoveredSource]}
            </p>
            {articles.filter(a => a.source === hoveredSource).map(art => (
              <p key={art.id} className="text-[10px] text-foreground mt-1 line-clamp-1 italic">
                "{art.title}"
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Bias Alert Warning if detected */}
      {narrativeDiversity.bias_detected && (
        <div className="mt-4 p-3 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded flex items-center gap-2">
          <span className="font-black">⚠</span>
          <span>{lang === 'sr' ? 'Detektovan je disbalans ili pristrasnost u pokrivenosti.' : 'Детектиран е дисбаланс или пристрасност во покривањето.'}</span>
        </div>
      )}
    </div>
  );
}
```

---

## 4. Recommendations for Implementation Sequence

1. **Schema and Validation Verification**: Validate that downstream payloads in all cluster detail responses contain valid `stance_vectors` and `narrative_diversity` dicts before making UI adjustments.
2. **Component Integration**: Create the `InteractiveStanceWidget.tsx` React component as described above. Ensure client-side interactivity works.
3. **Astro Updates**: Edit `/web/src/pages/cluster/[slug].astro` to pull the variables and wire them into the page section inside `<ClusterAnalysisSection>`.
4. **Style Sheet Verification**: Add the CSS variables and classes to `web/src/styles/cluster-page.css` and verify performance of `backdrop-filter` backdrop blur across core browsers.
