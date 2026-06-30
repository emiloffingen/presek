# Synthesis Report: Milestone R1 - Interactive Stance Visualizations

## Consensus
- **Target Page**: `web/src/pages/cluster/[slug].astro` retrieves the cluster details via `${API_URL}/cluster/${id}?lang=${lang}` (Cited: Explorer 1, 2, 3).
- **Narrative Diversity Schema**: The `narrative_diversity` payload contains `score` (int), `verdict` (string), and `bias_detected` (boolean) keys. Currently, only `verdict` is typed in `web/src/types.ts` (Cited: Explorer 1, 2, 3).
- **Perspectives Schema**: The `perspectives` payload contains an array of objects, each containing `angle` and `content` keys (Cited: Explorer 1, 2, 3).
- **Styling Direction**: Use vanilla CSS HSL variables and glassmorphism styling (`backdrop-filter`) aligned with Presek theme tokens (`--presek-mark`, `--nyt-red`, `--editorial-watch`, `--editorial-positive`) (Cited: Explorer 1, 2, 3).

## Resolved Conflicts / Design Approaches
- **Astro Component vs. React Island**:
  - Explorer 3 proposed a React component (`InteractiveStanceWidget.tsx`) to handle source hover tooltips and interactive state for `stance_vectors`.
  - Explorer 1 and 2 proposed an Astro-only component (`StanceVisuals.astro` or editing `CredibilityAnalysis.astro`) with vanilla CSS.
  - *Resolution*: Integrating the enhancements directly into the existing `CredibilityAnalysis.astro` component using vanilla CSS HSL styling, glassmorphic cards, and micro-animations is highly preferred. It maintains Presek's clean server-side rendering architecture, avoids adding React overhead, and keeps styling scoped.

## Gaps / Additional Payload Fields
- **Stance Vectors**: Explorer 3 identified `stance_vectors` and `editorial_divergence` returned by the API. While not explicitly mandated by the core requirements, including a visual spectrum of these stances adds massive value to the "Interactive Stance Visualizations" prompt.

## Recommended Implementation Plan
1. **Types Update**: Update `web/src/types.ts` to fully type `narrative_diversity` with `score` and `bias_detected` fields.
2. **Component Enhancements**: Update `web/src/components/Cluster/CredibilityAnalysis.astro` to:
   - Accept the expanded `narrative_diversity` object.
   - Render a custom stance distribution progress bar with a dynamic HSL pointer position calculated from the score.
   - Display perspective cards using glassmorphic panels and CSS transitions.
   - Show a warning banner if `bias_detected` is true.
3. **CSS Updates**: Add custom class definitions for glassmorphic elements and keyframe pulse animations to `web/src/styles/global.css` or scoped styles.
