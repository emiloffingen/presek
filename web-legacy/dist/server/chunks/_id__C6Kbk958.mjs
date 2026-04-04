import { $ as $$Layout, S as SearchIsland, T as ThemeIsland } from './ThemeIsland_ygngtFwf.mjs';
import { c as createComponent } from './astro-component_CBmWG5JF.mjs';
import 'piccolore';
import { i as renderComponent, r as renderTemplate, m as maybeRenderHead, g as addAttribute } from './server_CF7VxRY2.mjs';
import { ArrowLeft, Clock, Sparkles, Newspaper, MessageCircle, Link2 } from 'lucide-react';

const $$id = createComponent(async ($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$props, $$slots);
  Astro2.self = $$id;
  const { id } = Astro2.params;
  const API_URL = "https://presek.live/api";
  let cluster = null;
  let error = null;
  try {
    const res = await fetch(`${API_URL}/cluster/${id}`);
    if (!res.ok) throw new Error("Cluster not found");
    const data = await res.json();
    cluster = data.data;
  } catch (e) {
    console.error(e);
    error = "Кластерот не е пронајден.";
  }
  if (error) {
    return Astro2.redirect("/404");
  }
  const article = cluster.articles[0];
  return renderTemplate`${renderComponent($$result, "Layout", $$Layout, { "title": article.title, "description": cluster.synthesis?.substring(0, 160), "data-astro-cid-5zpa4vfw": true }, { "default": async ($$result2) => renderTemplate` ${maybeRenderHead()}<header class="site-layout py-6 border-b border-nyt flex items-center justify-between" data-astro-cid-5zpa4vfw> <a href="/" class="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-muted hover:text-accent transition" data-astro-cid-5zpa4vfw> ${renderComponent($$result2, "ArrowLeft", ArrowLeft, { "size": 14, "data-astro-cid-5zpa4vfw": true })} Назад
</a> <a href="/" class="absolute left-1/2 -translate-x-1/2" data-astro-cid-5zpa4vfw> <img src="/logo.svg" alt="Presek" class="h-10 grayscale opacity-50" data-astro-cid-5zpa4vfw> </a> <div class="flex items-center gap-2" data-astro-cid-5zpa4vfw> ${renderComponent($$result2, "SearchIsland", SearchIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/SearchIsland", "client:component-export": "default", "data-astro-cid-5zpa4vfw": true })} ${renderComponent($$result2, "ThemeIsland", ThemeIsland, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/home/emiloffingen/presek/web/src/components/ThemeIsland", "client:component-export": "default", "data-astro-cid-5zpa4vfw": true })} </div> </header> <main class="site-layout py-12" data-astro-cid-5zpa4vfw> <article class="max-w-4xl mx-auto" data-astro-cid-5zpa4vfw> <header class="mb-12 border-b-2 border-primary pb-10" data-astro-cid-5zpa4vfw> <div class="flex flex-wrap gap-2 mb-6" data-astro-cid-5zpa4vfw> ${(cluster.is_breaking || cluster.articles.length > 5) && renderTemplate`<span class="text-[10px] font-black uppercase tracking-widest text-accent border border-accent px-2 py-0.5" data-astro-cid-5zpa4vfw>BREAKING</span>`} ${cluster.has_synthesis && renderTemplate`<span class="text-[10px] font-black uppercase tracking-widest text-white bg-accent px-2 py-0.5" data-astro-cid-5zpa4vfw>СИНТЕЗА</span>`} </div> <h1 class="text-4xl md:text-6xl font-serif font-bold leading-tight text-primary mb-6" data-astro-cid-5zpa4vfw> ${article.title} </h1> <div class="flex items-center gap-4 text-xs font-bold uppercase text-muted" data-astro-cid-5zpa4vfw> <span class="flex items-center gap-1" data-astro-cid-5zpa4vfw>${renderComponent($$result2, "Clock", Clock, { "size": 12, "data-astro-cid-5zpa4vfw": true })} ${new Date(article.created_at).toLocaleTimeString("mk-MK", { hour: "2-digit", minute: "2-digit" })}</span> <span data-astro-cid-5zpa4vfw>·</span> <span data-astro-cid-5zpa4vfw>${cluster.total_reading_time || 1} мин читање</span> <span data-astro-cid-5zpa4vfw>·</span> <span data-astro-cid-5zpa4vfw>${cluster.articles.length} извори</span> </div> </header> <div class="grid grid-cols-1 lg:grid-cols-12 gap-12" data-astro-cid-5zpa4vfw> <!-- Content Column --> <div class="lg:col-span-8" data-astro-cid-5zpa4vfw> ${cluster.has_synthesis && cluster.synthesis && renderTemplate`<section class="mb-16" data-astro-cid-5zpa4vfw> <h2 class="rail-label mb-8 flex items-center gap-2" data-astro-cid-5zpa4vfw>${renderComponent($$result2, "Sparkles", Sparkles, { "size": 14, "data-astro-cid-5zpa4vfw": true })} АИ РЕЗИМЕ</h2> <div class="prose-nyt italic border-l-4 border-accent pl-8 py-2 text-secondary text-xl leading-relaxed" data-astro-cid-5zpa4vfw> ${cluster.synthesis} </div> ${cluster.perspectives && cluster.perspectives.length > 0 && renderTemplate`<div class="mt-12 space-y-8" data-astro-cid-5zpa4vfw> <p class="section-heading text-xs font-black uppercase tracking-tighter text-muted" data-astro-cid-5zpa4vfw>РАЗЛИЧНИ ПЕРСПЕКТИВИ</p> ${cluster.perspectives.map((p) => renderTemplate`<div class="bg-secondary p-6 border-t border-nyt" data-astro-cid-5zpa4vfw> <p class="font-bold text-sm mb-3 uppercase tracking-tight text-primary" data-astro-cid-5zpa4vfw>${p.angle}</p> <p class="text-base text-secondary leading-relaxed" data-astro-cid-5zpa4vfw>${p.content}</p> </div>`)} </div>`} </section>`} <section data-astro-cid-5zpa4vfw> <h2 class="rail-label mb-8 flex items-center gap-2" data-astro-cid-5zpa4vfw>${renderComponent($$result2, "Newspaper", Newspaper, { "size": 14, "data-astro-cid-5zpa4vfw": true })} СИТЕ ИЗВОРИ</h2> <div class="grid grid-cols-1 md:grid-cols-2 gap-8" data-astro-cid-5zpa4vfw> ${cluster.articles.map((art) => renderTemplate`<div class="border-b border-nyt pb-6" data-astro-cid-5zpa4vfw> <div class="flex justify-between items-start gap-3 mb-3" data-astro-cid-5zpa4vfw> <span class="text-[10px] font-black uppercase text-accent" data-astro-cid-5zpa4vfw>${art.source}</span> <span class="text-[10px] text-muted" data-astro-cid-5zpa4vfw> ${new Date(art.created_at).toLocaleTimeString("mk-MK", { hour: "2-digit", minute: "2-digit" })} </span> </div> <a${addAttribute(art.link, "href")} target="_blank" rel="noopener noreferrer" class="font-serif font-bold text-lg text-primary no-underline hover:text-accent transition-colors block leading-snug" data-astro-cid-5zpa4vfw> ${art.title} </a> </div>`)} </div> </section> </div> <!-- Sidebar Column --> <aside class="lg:col-span-4 space-y-12" data-astro-cid-5zpa4vfw> <div class="rail-widget border-t-2 border-primary pt-4" data-astro-cid-5zpa4vfw> <h3 class="rail-label flex items-center gap-2" data-astro-cid-5zpa4vfw>${renderComponent($$result2, "MessageCircle", MessageCircle, { "size": 14, "data-astro-cid-5zpa4vfw": true })} ПРАШАЈ АИ</h3> <div class="bg-secondary p-6 text-center" data-astro-cid-5zpa4vfw> <p class="text-xs text-muted mb-4 italic" data-astro-cid-5zpa4vfw>Интерактивниот АИ чет доаѓа наскоро во Presek 6.0</p> <button disabled class="w-full bg-primary/10 border border-nyt py-3 text-[10px] font-black uppercase tracking-widest opacity-50" data-astro-cid-5zpa4vfw>
Наскоро
</button> </div> </div> ${cluster.related && cluster.related.length > 0 && renderTemplate`<div class="rail-widget border-t-2 border-primary pt-4" data-astro-cid-5zpa4vfw> <h3 class="rail-label flex items-center gap-2" data-astro-cid-5zpa4vfw>${renderComponent($$result2, "Link2", Link2, { "size": 14, "data-astro-cid-5zpa4vfw": true })} ПОВРЗАНИ ТЕМИ</h3> <div class="space-y-8" data-astro-cid-5zpa4vfw> ${cluster.related.map((rel) => renderTemplate`<a${addAttribute(`/cluster/${rel.cluster_id}`, "href")} class="group block no-underline" data-astro-cid-5zpa4vfw> <p class="font-serif font-bold text-base text-primary group-hover:text-accent transition-colors leading-snug mb-2" data-astro-cid-5zpa4vfw> ${rel.title} </p> <div class="flex flex-wrap gap-2" data-astro-cid-5zpa4vfw> ${(rel.tags || []).slice(0, 3).map((tag) => renderTemplate`<span class="text-[9px] font-bold uppercase text-muted" data-astro-cid-5zpa4vfw>#${tag}</span>`)} </div> </a>`)} </div> </div>`} </aside> </div> </article> </main> ` })}`;
}, "/home/emiloffingen/presek/web/src/pages/cluster/[id].astro", void 0);
const $$file = "/home/emiloffingen/presek/web/src/pages/cluster/[id].astro";
const $$url = "/cluster/[id]";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
	__proto__: null,
	default: $$id,
	file: $$file,
	url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
