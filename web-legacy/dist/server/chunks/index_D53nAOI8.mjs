import { $ as $$Layout, S as SearchIsland, T as ThemeIsland } from './ThemeIsland_ygngtFwf.mjs';
import { c as createComponent } from './astro-component_CBmWG5JF.mjs';
import 'piccolore';
import { i as renderComponent, r as renderTemplate, m as maybeRenderHead, g as addAttribute } from './server_CF7VxRY2.mjs';
import { $ as $$NewsCard } from './NewsCard_BJfSuHxC.mjs';
import { Menu, TrendingUp, BarChart3 } from 'lucide-react';

const $$Index = createComponent(async ($$result, $$props, $$slots) => {
  const API_URL = "https://presek.live/api";
  let clusters = [];
  let trending = [];
  let topEntities = [];
  let error = null;
  try {
    const [newsRes, trendRes, entityRes] = await Promise.all([
      fetch(`${API_URL}/news?page_size=25`),
      fetch(`${API_URL}/trending`),
      fetch(`${API_URL}/intelligence/top-entities?limit=10`)
      // We'll add this endpoint
    ]);
    const newsData = await newsRes.json();
    clusters = newsData.clusters || [];
    trending = await trendRes.json();
    topEntities = await entityRes.json();
  } catch (e) {
    console.error("Fetch error:", e);
    error = "Грешка при вчитување на вестите.";
  }
  const currentDate = (/* @__PURE__ */ new Date()).toLocaleDateString("mk-MK", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric"
  });
  return renderTemplate`${renderComponent($$result, "Layout", $$Layout, { "title": "Главни Вести", "data-astro-cid-j7pv25f6": true }, { "default": async ($$result2) => renderTemplate`  ${maybeRenderHead()}<div class="utility-bar border-b border-nyt py-2 bg-primary" data-astro-cid-j7pv25f6> <div class="site-layout flex items-center justify-between" data-astro-cid-j7pv25f6> <div class="flex flex-col" data-astro-cid-j7pv25f6> <span class="font-black text-[0.65rem] uppercase tracking-wider text-primary" data-astro-cid-j7pv25f6>${currentDate}</span> <span class="text-[0.6rem] text-muted uppercase tracking-wider" data-astro-cid-j7pv25f6>Скопје, Македонија</span> </div> <div class="hidden md:flex gap-6 items-center" data-astro-cid-j7pv25f6> <a href="/briefing" class="font-black text-[0.65rem] uppercase tracking-wider text-primary hover:text-accent transition" data-astro-cid-j7pv25f6>Дневен Брифинг</a> <a href="/stats" class="font-black text-[0.65rem] uppercase tracking-wider text-primary hover:text-accent transition" data-astro-cid-j7pv25f6>Статистика</a> </div> </div> </div>  <header class="site-layout py-8 border-b-4 border-double border-nyt mb-8" data-astro-cid-j7pv25f6> <div class="text-center relative" data-astro-cid-j7pv25f6> <button class="md:hidden absolute left-0 top-1/2 -translate-y-1/2 p-2" data-astro-cid-j7pv25f6> ${renderComponent($$result2, "Menu", Menu, { "size": 20, "data-astro-cid-j7pv25f6": true })} </button> <a href="/" class="inline-block" data-astro-cid-j7pv25f6> <img src="/logo.svg" alt="Presek" class="h-16 md:h-20" data-astro-cid-j7pv25f6> </a> <div class="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-2" data-astro-cid-j7pv25f6> ${renderComponent($$result2, "SearchIsland", SearchIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/SearchIsland", "client:component-export": "default", "data-astro-cid-j7pv25f6": true })} ${renderComponent($$result2, "ThemeIsland", ThemeIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/ThemeIsland", "client:component-export": "default", "data-astro-cid-j7pv25f6": true })} </div> </div> <nav class="hidden md:block mt-6" data-astro-cid-j7pv25f6> <div class="flex justify-center border-y border-nyt py-3 gap-8" data-astro-cid-j7pv25f6> ${["Македонија", "Балкан", "Европа", "Свет", "Економија", "Спорт", "Технологија"].map((cat) => renderTemplate`<a${addAttribute(`/?category=${cat}`, "href")} class="text-xs font-black uppercase tracking-widest text-muted hover:text-primary transition no-underline" data-astro-cid-j7pv25f6> ${cat} </a>`)} </div> </nav> <!-- Entities in Focus --> <div class="mt-6 flex flex-wrap justify-center items-center gap-4" data-astro-cid-j7pv25f6> <span class="text-[9px] font-black uppercase tracking-tighter text-muted" data-astro-cid-j7pv25f6>Личности во фокус:</span> ${topEntities.map((ent) => renderTemplate`<a${addAttribute(`/entity/${encodeURIComponent(ent.name)}`, "href")} class="text-[10px] font-bold text-primary hover:text-accent no-underline border-b border-color transition-colors" data-astro-cid-j7pv25f6> ${ent.name} </a>`)} </div> </header> <main class="site-layout" data-astro-cid-j7pv25f6> <div class="grid grid-cols-1 lg:grid-cols-12 gap-10" data-astro-cid-j7pv25f6> <!-- Main Feed (9 cols) --> <div class="lg:col-span-9" data-astro-cid-j7pv25f6> ${error && renderTemplate`<div class="bg-secondary p-8 text-center border-t-2 border-accent mb-8" data-astro-cid-j7pv25f6> <p class="text-accent font-bold uppercase tracking-widest" data-astro-cid-j7pv25f6>${error}</p> </div>`} <div class="news-feed-grid" data-astro-cid-j7pv25f6> ${clusters.map((cluster, idx) => renderTemplate`${renderComponent($$result2, "NewsCard", $$NewsCard, { "cluster": cluster, "isLead": idx === 0, "data-astro-cid-j7pv25f6": true })}`)} </div> </div> <!-- Sidebar (3 cols) --> <aside class="lg:col-span-3 space-y-10" data-astro-cid-j7pv25f6> <section class="border-t-2 border-primary pt-4" data-astro-cid-j7pv25f6> <h3 class="rail-label flex items-center gap-2" data-astro-cid-j7pv25f6> ${renderComponent($$result2, "TrendingUp", TrendingUp, { "size": 14, "data-astro-cid-j7pv25f6": true })} ПОПУЛАРНО
</h3> <div class="flex flex-wrap gap-2" data-astro-cid-j7pv25f6> ${trending.slice(0, 15).map((item) => renderTemplate`<a${addAttribute(`/?q=${item.word}`, "href")} class="pill-lite" data-astro-cid-j7pv25f6> ${item.word} ${item.trend === "↑" && "↑"} </a>`)} </div> </section> <section class="border-t-2 border-primary pt-4" data-astro-cid-j7pv25f6> <h3 class="rail-label flex items-center gap-2" data-astro-cid-j7pv25f6> ${renderComponent($$result2, "BarChart3", BarChart3, { "size": 14, "data-astro-cid-j7pv25f6": true })} МЕДИУМСКИ ПУЛС
</h3> <div class="bg-secondary p-4 rounded-sm" data-astro-cid-j7pv25f6> <p class="text-[10px] font-bold text-muted uppercase mb-1" data-astro-cid-j7pv25f6>ПОСЛЕДНИ 24 ЧАСА</p> <p class="text-2xl font-serif font-bold text-primary" data-astro-cid-j7pv25f6>--</p> <p class="text-[10px] font-bold text-muted uppercase" data-astro-cid-j7pv25f6>ОБЈАВЕНИ СТАТИИ</p> </div> </section> </aside> </div> </main> <footer class="site-layout mt-20 py-10 border-t border-nyt text-center" data-astro-cid-j7pv25f6> <img src="/logo.svg" alt="Presek" class="h-10 opacity-30 mx-auto mb-4 grayscale" data-astro-cid-j7pv25f6> <p class="text-[10px] font-bold text-muted uppercase tracking-widest" data-astro-cid-j7pv25f6>
© 2026 ПРЕСЕК - ИНТЕЛИГЕНТНА АГРЕГАЦИЈА НА ВЕСТИ
</p> </footer> ` })}`;
}, "/home/emiloffingen/presek/web/src/pages/index.astro", void 0);
const $$file = "/home/emiloffingen/presek/web/src/pages/index.astro";
const $$url = "";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
	__proto__: null,
	default: $$Index,
	file: $$file,
	url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
