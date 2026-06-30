# Milestone R1: Interactive Stance Visualizations - Analysis & Strategy Report

## Summary
This report analyzes the retrieval of `narrative_diversity` and `perspectives` from the cluster payload on the presek details page (`web/src/pages/cluster/[slug].astro`), proposes a concrete design and implementation strategy using modern CSS/layout variables for the interactive widgets, and provides code snippets and configurations to guide the implementer agent.

---

## 1. Observation

Direct observations of code, paths, and payload keys related to `narrative_diversity` and `perspectives`:

### 1.1 Astro Detail Page Retrieval
In `/home/emiloffingen/presek/web/src/pages/cluster/[slug].astro`:
- The cluster details API endpoint is fetched at lines 88–101:
  ```typescript
  try {
      const res = await fetch(`${API_URL}/cluster/${id}?lang=${lang}`);
      if (!res.ok) {
          ...
      } else {
        const payload = await res.json();
        cluster = payload.data;
        pipeline = payload.pipeline && typeof payload.pipeline === 'object' ? payload.pipeline : null;
      }
  ...
  ```
- The `perspectives` array is retrieved at line 156:
  ```typescript
  const perspectives = cluster?.perspectives || [];
  ```
- The `narrative_diversity` object is currently retrieved and formatted only inside `evidenceItems` at lines 464–468:
  ```typescript
  ...(cluster?.pluralism_score != null ? [{
      label: t('cluster.evidence.pluralism_index'),
      value: `${cluster.pluralism_score}%`,
      detail: cluster.narrative_diversity?.verdict
          ? `“${(lang === 'mk' && !isMostlyCyrillic(cluster.narrative_diversity.verdict)
              ? transliterate(cluster.narrative_diversity.verdict)
              : cluster.narrative_diversity.verdict).slice(0, 60)}...”`
          : t('cluster.evidence.perspective_diversity'),
  }] : []),
  ```

### 1.2 TypeScript Interfaces
In `/home/emiloffingen/presek/web/src/types.ts`:
- `ClusterDetail` extends `NewsCluster` (lines 98–144) and has a `perspectives` key:
  ```typescript
  perspectives: ClusterSummary[];
  ```
  Where `ClusterSummary` is defined at lines 37–40:
  ```typescript
  export interface ClusterSummary {
    angle: string;
    content: string;
  }
  ```
- `narrative_diversity` is defined at lines 170–173 of `/home/emiloffingen/presek/web/src/types.ts`:
  ```typescript
  narrative_diversity?: {
    verdict?: string;
  };
  ```

### 1.3 Backend Database & API Route Payload Structure
- Database migrations show that `narrative_diversity` is stored as a `JSONB` column in table `cluster_summaries` (from `/home/emiloffingen/presek/migrations/versions/cc17c5bca747_change_narrative_diversity_to_jsonb.py`):
  ```sql
  ALTER TABLE cluster_summaries ALTER COLUMN narrative_diversity TYPE JSONB USING narrative_diversity::text::jsonb
  ```
- The API route `/cluster/<id>` in `/home/emiloffingen/presek/routes/news.py` retrieves it at line 1430:
  ```python
  narrative_diversity = _parse_maybe_json(s_row.get("narrative_diversity")) if s_row else None
  ```
  And includes it in the cluster payload data under `data.narrative_diversity` at line 1471:
  ```python
  "narrative_diversity": narrative_diversity,
  ```
- The model structure for the analyst assessment in `/home/emiloffingen/presek/nlp/local_analyst.py` shows that `narrative_diversity` is generated via `assess_pluralism(...)` and returns a dict matching the `PluralismResponse` schema at lines 572–574:
  ```json
  {
    "score": 50,
    "verdict": "Standardna pokrivenost",
    "bias_detected": false
  }
  ```

### 1.4 Existing Credibility Analysis Structure
In `/home/emiloffingen/presek/web/src/components/Cluster/CredibilityAnalysis.astro` (lines 101–123):
- Props received from `[slug].astro` include `pluralismScore` (which maps to `cluster.pluralism_score`):
  ```typescript
  const {
      hasFactcheck,
      verificationReport,
      perspectives,
      hasCitationSources,
      showPerspectives = true,
      consensusNote = null,
      lang: propLang,
      pluralismScore,
      toneAnalysis,
  } = Astro.props;
  ```
- Pluralism percent bar is generated statically using inline styles at lines 197–199:
  ```astro
  <div class="signal-bar" aria-hidden="true">
      <div class="signal-bar-fill pluralism" style={`width: ${pluralismPercent}%`}></div>
  </div>
  ```

---

## 2. Logic Chain

Based on these observations, here is the rationale leading to our proposed design:

1. **Information Completeness**:
   - Currently, `types.ts` defines `narrative_diversity` as containing only `{ verdict?: string }`.
   - However, the backend returns `{ score: number, verdict: string, bias_detected: boolean }`.
   - Therefore, the TypeScript `narrative_diversity` interface under `ClusterDetail` (or a global namespace) must be expanded to include all three properties.

2. **Visual Enhancements & Core Design Tokens**:
   - The user requests custom visual elements (distribution bars, stance gradients) using HSL palettes, glassmorphism, and micro-animations matching the existing design of the site.
   - We observed that `/home/emiloffingen/presek/web/src/styles/global.css` contains strong semantic design tokens:
     - `--presek-mark: #173f7a` (Primary dark blue)
     - `--editorial-positive: #047857` (Emerald green for high agreement/diversity)
     - `--editorial-watch: #92400e` (Amber for medium bias/warnings)
     - `--nyt-red: #a31621` (Deep red for low pluralism/high bias)
     - `--card` and `--background` (Paper cream `#fbfaf5` / dark slate `#08090b`)
   - We should map the dynamic `score` (0–100) to an HSL hue value in CSS:
     - $0\% \to \text{Red (0)}$
     - $50\% \to \text{Amber/Yellow (40)}$
     - $100\% \to \text{Emerald Green/Teal (140)}$
     - Calculation: `calc(var(--score-val) * 1.4)` maps 0–100 to 0 (red) through 140 (teal/green).

3. **Responsive Glassmorphism Bento Grid**:
   - An interactive stance visualization widget should replace or enrich the current static `media-signal-card` and `perspectives-list-card` within `CredibilityAnalysis.astro`.
   - Glassmorphic panels can be constructed using `color-mix` with `var(--card)` and `backdrop-filter: blur(12px)`.

---

## 3. Caveats

- **Network Limits & Static Generation**: Astro performs server-side fetching/rendering. These styles must work regardless of whether the cluster page is server-rendered on demand (SSR) or dynamically pre-generated.
- **Null Handlers**: When a cluster has no diversity assessment yet (e.g. `pluralism_data = null` or "Procena je u toku"), the widgets must fall back gracefully to a loading state or a subtle note rather than crashing the page.
- **Language Support**: All labels inside the custom widgets must support both Serbian (`sr`) and Macedonian (`mk`) using translation utilities `t(...)`.

---

## 4. Conclusion & Strategy

We recommend a concrete strategy for Milestone R1, detailed below in terms of file updates, layout/CSS variables, and component implementation.

### 4.1 Schema Expansion in `web/src/types.ts`
Modify lines 170–173 in `web/src/types.ts` to:
```typescript
  narrative_diversity?: {
    score?: number;
    verdict?: string;
    bias_detected?: boolean;
  };
```

### 4.2 Component Design: Stance Widgets
We recommend introducing a new Astro sub-component or directly updating `/home/emiloffingen/presek/web/src/components/Cluster/CredibilityAnalysis.astro` to render two primary widgets:
1. **`Narrative Diversity Index` Widget**: A gauge/distribution bar utilizing dynamic HSL hues.
2. **`Interactive Stance Perspectives` Widget**: A cards-grid or tabbed layout showing individual angles with subtle animations and indicator lights.

### 4.3 Proposed CSS & Layout Variables
Implement the following CSS system. These variables compute background shades, gradient fills, and border highlights dynamically based on the payload value:

```css
/* Custom variables scoped to the credibility visualization */
.credibility-interactive-scope {
  /* Dynamic values set via HTML style="--score-val: {score}" */
  --score-val: 50; 
  
  /* Dynamic color logic */
  /* Red (0 deg) to Green (120 deg) based on the score */
  --score-hue: calc(var(--score-val) * 1.2); 
  --score-color: hsl(var(--score-hue), 70%, 40%);
  --score-color-bg: hsla(var(--score-hue), 70%, 40%, 0.08);
  --score-color-border: hsla(var(--score-hue), 70%, 40%, 0.25);
  
  /* Glassmorphism primitives */
  --glass-bg: color-mix(in srgb, var(--card) 65%, transparent);
  --glass-backdrop-blur: 16px;
  --glass-border: 1px solid color-mix(in srgb, var(--foreground) 8%, transparent);
  --glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.04);
  
  /* Transitions */
  --transition-bezier: cubic-bezier(0.16, 1, 0.3, 1);
  --transition-fast: 0.2s var(--transition-bezier);
  --transition-normal: 0.4s var(--transition-bezier);
}

/* Stance visual elements styling */
.stance-distribution-bar {
  position: relative;
  height: 12px;
  width: 100%;
  background: color-mix(in srgb, var(--border) 40%, transparent);
  border-radius: 99px;
  overflow: visible;
  margin: 1.5rem 0;
}

.stance-distribution-gradient {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: inherit;
  width: 100%;
  /* Gradient from red (low pluralism) -> yellow -> green (high pluralism) */
  background: linear-gradient(90deg, var(--nyt-red) 0%, var(--editorial-watch) 50%, var(--editorial-positive) 100%);
  opacity: 0.15;
}

.stance-indicator-pin {
  position: absolute;
  top: 50%;
  left: calc(var(--score-val) * 1%);
  transform: translate(-50%, -50%);
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--score-color);
  border: 4px solid var(--card);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
  transition: left var(--transition-normal);
  cursor: pointer;
}

.stance-indicator-pin::after {
  content: '';
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 1px solid var(--score-color-border);
  animation: pulse-glow 2s infinite ease-in-out;
}

@keyframes pulse-glow {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.15); opacity: 0.8; }
}

/* Glassmorphism panel container */
.glass-panel {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-backdrop-blur));
  -webkit-backdrop-filter: blur(var(--glass-backdrop-blur));
  border: var(--glass-border);
  box-shadow: var(--glass-shadow);
  border-radius: var(--radius-md, 8px);
  padding: 1.25rem;
  transition: transform var(--transition-fast), border-color var(--transition-fast);
}

.glass-panel:hover {
  transform: translateY(-2px);
  border-color: var(--score-color-border);
}

/* Perspective Angle styling */
.perspective-card-interactive {
  position: relative;
  overflow: hidden;
  transition: all var(--transition-normal);
}

/* Subtle stance light in corners of perspective cards */
.perspective-card-interactive::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--presek-mark);
}

.perspective-card-interactive.stance-0::before { background: var(--nyt-red); }
.perspective-card-interactive.stance-1::before { background: var(--editorial-watch); }
.perspective-card-interactive.stance-2::before { background: var(--presek-mark); }
.perspective-card-interactive.stance-3::before { background: var(--editorial-positive); }
```

### 4.4 Astro HTML Layout Strategy for `CredibilityAnalysis.astro`

Update the render block under `/web/src/components/Cluster/CredibilityAnalysis.astro` to include the interactive panel (incorporating `cluster.narrative_diversity` payload properties):

```astro
<!-- Wrapper setting dynamic scope variables -->
<div 
  class="credibility-interactive-scope" 
  style={`--score-val: ${pluralismScore || 50};`}
>
  <div class="analysis-bento-grid">
    
    <!-- Left Column: Diversity Gauge & Metric -->
    <div class="glass-panel media-signal-card">
      <div class="signal-header">
        <h5 class="signal-label">{t('cluster.credibility.signal_discourse')}</h5>
        <p class="signal-summary">{signalSummary}</p>
      </div>

      <div class="signal-metrics">
        <div class="signal-metric">
          <div class="signal-metric-head">
            <span>{t('cluster.credibility.pluralism_sources')}</span>
            <strong style="color: var(--score-color);">{pluralismScore || 50}%</strong>
          </div>
          
          <!-- Interactive Gauge/Distribution bar -->
          <div class="stance-distribution-bar" aria-valuenow={pluralismScore} aria-valuemin="0" aria-valuemax="100">
            <div class="stance-distribution-gradient"></div>
            <div class="stance-indicator-pin" title={`Index: ${pluralismScore}%`}></div>
          </div>
          
          {verificationReport?.bias_detected && (
            <div class="bias-warning-pill text-xs py-1 px-2.5 rounded bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-400 font-bold border border-red-200/50 mt-2 flex items-center gap-1.5 animate-pulse">
              <TriangleAlert size={12} />
              <span>{t('cluster.credibility.bias_detected_warning') || 'Uočena jednostranost u izveštavanju'}</span>
            </div>
          )}
        </div>
      </div>
    </div>

    <!-- Right Column: Stance Perspectives Grid -->
    <div class="glass-panel perspectives-list-card">
      <h4 class="perspectives-label">{t('cluster.factcheck.diversity')}</h4>
      <div class="perspective-grid-v2">
        {displayPerspectives.map((p: any, idx: number) => (
          <div class={`glass-panel perspective-card-interactive stance-${idx % 4}`}>
            <h5 class="angle-title" set:html={renderSynthesisHtml(p.angle)}></h5>
            <p class="angle-content text-sm" set:html={renderSynthesisHtml(p.content)}></p>
          </div>
        ))}
      </div>
    </div>

  </div>
</div>
```

---

## 5. Verification Method

To independently verify this implementation:

1. **Verify Backend payload delivery**:
   - Inspect backend output from a shell using `curl`:
     ```bash
     curl -s "http://localhost:8000/cluster/<id>?lang=sr" | jq '.data.narrative_diversity'
     ```
   - Ensure the JSON keys returned match:
     ```json
     {
       "score": 85,
       "verdict": "Visok nivo pluralizma...",
       "bias_detected": false
     }
     ```

2. **Verify Frontend UI integration**:
   - Start the Astro web server in development mode:
     ```bash
     npm run dev
     ```
   - Navigate to `/cluster/<slug>` using a web browser.
   - Inspect the Pluralism metric block under the main column.
   - Verify that:
     - The pin pointer aligns precisely along the gradient bar matching the percentage value.
     - Hovering over/interacting with perspective cards triggers smooth CSS animations (translateY/shadow transitions).
     - Color hues adapt automatically according to the cluster's diversity score (low score turns the pin/headers red, high score emerald green).
