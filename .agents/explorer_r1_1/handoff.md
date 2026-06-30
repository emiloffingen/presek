# Handoff Report: Milestone R1 Investigation

## 1. Observation
- **Astro Cluster Detail Page**:
  - Path: `/home/emiloffingen/presek/web/src/pages/cluster/[slug].astro`
  - In lines 98-100:
    ```typescript
    const payload = await res.json();
    cluster = payload.data;
    ```
  - In line 156:
    ```typescript
    const perspectives = cluster?.perspectives || [];
    ```
  - In lines 464-468:
    ```typescript
    detail: cluster.narrative_diversity?.verdict
        ? `“${(lang === 'mk' && !isMostlyCyrillic(cluster.narrative_diversity.verdict)
            ? transliterate(cluster.narrative_diversity.verdict)
            : cluster.narrative_diversity.verdict).slice(0, 60)}...”`
        : t('cluster.evidence.perspective_diversity'),
    ```
- **Backend Schema & API Responses**:
  - In `nlp/local_analyst.py` (lines 67-70):
    ```python
    class PluralismResponse(BaseModel):
        score: int = Field(..., ge=0, le=100, description="Pluralism score from 0 to 100")
        verdict: str = Field(..., description="A short sentence explaining the score")
        bias_detected: bool = Field(..., description="Whether bias was detected")
    ```
  - In `routes/news.py` (lines 1464, 1471):
    ```python
    "perspectives": perspectives,
    ...
    "narrative_diversity": narrative_diversity,
    ```
- **Design System Variables**:
  - In `web/src/styles/global.css` (lines 330-331):
    ```css
    --glass-blur: blur(16px);
    --glass-opacity: 0.88;
    ```

## 2. Logic Chain
1. The backend API `/api/cluster/{id}` serves a data payload containing both `narrative_diversity` and `perspectives`.
2. This is fetched in the Astro page component (`[slug].astro`) frontmatter and mapped to the `cluster` variable.
3. Therefore, frontend components (such as a new or modified `<CredibilityAnalysis>` widget) can immediately consume `cluster.perspectives` (array of `{angle: string, content: string}`) and `cluster.narrative_diversity` (object of `{score: number, verdict: string, bias_detected: boolean}`).
4. By passing the dynamic numeric score to HTML attributes as inline CSS variables (e.g. `style="--stance-score: X"`), we can use CSS `calc()` to dynamically shift HSL color values and position markers without relying on heavy client-side Javascript.
5. Using standard `--glass-blur` and custom HSL stance properties guarantees consistent light and dark mode styling with smooth transitions.

## 3. Caveats
- Since this is a read-only investigation, we did not run the dev server or inspect the actual visual rendering in the browser.
- We assume that the backend database and API always return a valid `narrative_diversity` schema matching `PluralismResponse` structure. If either `score` or `verdict` is absent, the widget must degrade gracefully.

## 4. Conclusion
Milestone R1 can be implemented directly by creating/integrating a new visual section in `web/src/pages/cluster/[slug].astro` that exposes the dynamic distribution bar (based on `--stance-score`) and the stance spectrum of perspective cards (utilizing the designed HSL colors and glassmorphic card overlays).

## 5. Verification Method
- **Frontend Build Verification**: Run `npm run build` in the `web` folder to verify there are no compilation or Astro type errors.
- **Frontend Test Suite**: Run `npm run test` and `npm run test:e2e` in the `web` folder.
- **Backend Test Suite**: Run `pytest` from the root directory to confirm all backend tests pass.
- **Invalidation Condition**: If `cluster.narrative_diversity` is returned as a plain float or is missing key fields like `score`, the widget will render with default/fallback values.
