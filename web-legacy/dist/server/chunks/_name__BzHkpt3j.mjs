import { $ as $$Layout, S as SearchIsland, T as ThemeIsland } from './ThemeIsland_ygngtFwf.mjs';
import { c as createComponent } from './astro-component_CBmWG5JF.mjs';
import 'piccolore';
import { i as renderComponent, r as renderTemplate, m as maybeRenderHead } from './server_CF7VxRY2.mjs';
import { $ as $$NewsCard } from './NewsCard_BJfSuHxC.mjs';
import { jsx, jsxs } from 'react/jsx-runtime';
import { useState, useEffect } from 'react';
import { Loader2, User, Building2, TrendingUp, Link2, ArrowLeft } from 'lucide-react';

function EntityIsland({ name }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const API_URL = "https://presek.live/api";
    fetch(`${API_URL}/intelligence/entity/${encodeURIComponent(name)}`).then((res) => res.json()).then(setData).catch(console.error).finally(() => setLoading(false));
  }, [name]);
  if (loading) return /* @__PURE__ */ jsx("div", { className: "flex flex-col items-center py-12", children: /* @__PURE__ */ jsx(Loader2, { className: "animate-spin text-accent", size: 32 }) });
  if (!data) return null;
  const { profile, related } = data;
  return /* @__PURE__ */ jsxs("div", { className: "space-y-10", children: [
    /* @__PURE__ */ jsxs("header", { className: "border-b-4 border-double border-nyt pb-8", children: [
      /* @__PURE__ */ jsxs("div", { className: "flex items-center gap-4 mb-4", children: [
        /* @__PURE__ */ jsx("div", { className: "p-3 bg-secondary rounded-full", children: profile.type === "PERSON" ? /* @__PURE__ */ jsx(User, { size: 32, className: "text-accent" }) : /* @__PURE__ */ jsx(Building2, { size: 32, className: "text-accent" }) }),
        /* @__PURE__ */ jsxs("div", { children: [
          /* @__PURE__ */ jsx("span", { className: "text-[10px] font-black uppercase tracking-widest text-muted", children: profile.type }),
          /* @__PURE__ */ jsx("h1", { className: "text-4xl md:text-6xl font-serif font-bold text-primary", children: profile.name })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "flex flex-wrap gap-8 mt-6", children: [
        /* @__PURE__ */ jsxs("div", { className: "border-t border-nyt pt-3", children: [
          /* @__PURE__ */ jsx("p", { className: "text-[10px] font-black uppercase text-muted mb-1", children: "Споменувања" }),
          /* @__PURE__ */ jsx("p", { className: "text-2xl font-serif font-bold text-primary", children: profile.total_mentions })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "border-t border-nyt pt-3", children: [
          /* @__PURE__ */ jsx("p", { className: "text-[10px] font-black uppercase text-muted mb-1", children: "Прв пат виден" }),
          /* @__PURE__ */ jsx("p", { className: "text-2xl font-serif font-bold text-primary", children: new Date(profile.first_seen).toLocaleDateString("mk-MK") })
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "border-t border-nyt pt-3", children: [
          /* @__PURE__ */ jsx("p", { className: "text-[10px] font-black uppercase text-muted mb-1", children: "Сентимент" }),
          /* @__PURE__ */ jsxs("p", { className: "text-2xl font-serif font-bold text-accent", children: [
            profile.sentiment_score > 0 ? "+" : "",
            profile.sentiment_score.toFixed(1)
          ] })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "grid grid-cols-1 lg:grid-cols-12 gap-10", children: [
      /* @__PURE__ */ jsxs("div", { className: "lg:col-span-8", children: [
        /* @__PURE__ */ jsxs("h2", { className: "rail-label flex items-center gap-2", children: [
          /* @__PURE__ */ jsx(TrendingUp, { size: 14 }),
          " НАЈНОВИ ВЕСТИ"
        ] }),
        /* @__PURE__ */ jsxs("p", { className: "text-sm text-muted italic mb-8", children: [
          "Сите кластери каде се појавува ",
          profile.name,
          "..."
        ] })
      ] }),
      /* @__PURE__ */ jsx("aside", { className: "lg:col-span-4", children: /* @__PURE__ */ jsxs("div", { className: "rail-widget border-t-2 border-primary pt-4", children: [
        /* @__PURE__ */ jsxs("h3", { className: "rail-label flex items-center gap-2", children: [
          /* @__PURE__ */ jsx(Link2, { size: 14 }),
          " ПОВРЗАНИ ЕНТИТЕТИ"
        ] }),
        /* @__PURE__ */ jsxs("div", { className: "space-y-4", children: [
          related.map((rel) => /* @__PURE__ */ jsxs(
            "a",
            {
              href: `/entity/${encodeURIComponent(rel.related_entity)}`,
              className: "flex justify-between items-center py-2 border-b border-nyt hover:text-accent transition-colors no-underline group",
              children: [
                /* @__PURE__ */ jsx("span", { className: "text-sm font-bold uppercase tracking-tight", children: rel.related_entity }),
                /* @__PURE__ */ jsxs("div", { className: "flex items-center gap-2", children: [
                  /* @__PURE__ */ jsx("div", { className: "h-1 w-12 bg-secondary overflow-hidden", children: /* @__PURE__ */ jsx("div", { className: "h-full bg-accent", style: { width: `${Math.min(rel.weight * 10, 100)}%` } }) }),
                  /* @__PURE__ */ jsx("span", { className: "text-[10px] font-black text-muted", children: rel.weight })
                ] })
              ]
            },
            rel.related_entity
          )),
          related.length === 0 && /* @__PURE__ */ jsx("p", { className: "text-xs text-muted italic", children: "Нема пронајдени врски." })
        ] })
      ] }) })
    ] })
  ] });
}

const $$name = createComponent(async ($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$props, $$slots);
  Astro2.self = $$name;
  const { name } = Astro2.params;
  const decodedName = decodeURIComponent(name || "");
  const API_URL = "https://presek.live/api";
  let clusters = [];
  try {
    const res = await fetch(`${API_URL}/news?entity=${encodeURIComponent(decodedName)}&page_size=10`);
    const data = await res.json();
    clusters = data.clusters || [];
  } catch (e) {
    console.error(e);
  }
  return renderTemplate`${renderComponent($$result, "Layout", $$Layout, { "title": decodedName, "description": `Најнови вести и анализи за ${decodedName} на Пресек.` }, { "default": async ($$result2) => renderTemplate` ${maybeRenderHead()}<header class="site-layout py-6 border-b border-nyt flex items-center justify-between"> <a href="/" class="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-muted hover:text-accent transition"> ${renderComponent($$result2, "ArrowLeft", ArrowLeft, { "size": 14 })} Назад
</a> <a href="/" class="absolute left-1/2 -translate-x-1/2"> <img src="/logo.svg" alt="Presek" class="h-10 grayscale opacity-50"> </a> <div class="flex items-center gap-2"> ${renderComponent($$result2, "SearchIsland", SearchIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/SearchIsland", "client:component-export": "default" })} ${renderComponent($$result2, "ThemeIsland", ThemeIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/ThemeIsland", "client:component-export": "default" })} </div> </header> <main class="site-layout py-12"> ${renderComponent($$result2, "EntityIsland", EntityIsland, { "client:load": true, "name": decodedName, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/EntityIsland", "client:component-export": "default" })} <div class="grid grid-cols-1 lg:grid-cols-12 gap-10 mt-[-30rem] lg:mt-[-25rem]"> <div class="lg:col-span-8"> <div class="news-feed-grid mt-12"> ${clusters.map((cluster) => renderTemplate`${renderComponent($$result2, "NewsCard", $$NewsCard, { "cluster": cluster })}`)} </div> ${clusters.length === 0 && renderTemplate`<div class="bg-secondary p-12 text-center border-t-2 border-nyt"> <p class="text-muted font-bold uppercase tracking-widest text-sm">Нема пронајдени вести за овој ентитет.</p> </div>`} </div> </div> </main> ` })}`;
}, "/home/emiloffingen/presek/web/src/pages/entity/[name].astro", void 0);
const $$file = "/home/emiloffingen/presek/web/src/pages/entity/[name].astro";
const $$url = "/entity/[name]";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  default: $$name,
  file: $$file,
  url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
