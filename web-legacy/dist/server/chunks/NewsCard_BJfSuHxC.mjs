import { c as createComponent } from './astro-component_CBmWG5JF.mjs';
import 'piccolore';
import { m as maybeRenderHead, g as addAttribute, r as renderTemplate } from './server_CF7VxRY2.mjs';
import 'clsx';

const $$NewsCard = createComponent(($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$props, $$slots);
  Astro2.self = $$NewsCard;
  const { cluster, isLead = false } = Astro2.props;
  const main = cluster.articles[0];
  const thumb = cluster.representative_image || cluster.articles.find((a) => a.image_url)?.image_url;
  const thumbSrc = thumb ? `/proxy?url=${encodeURIComponent(thumb)}` : null;
  function getTimeStr(dateStr) {
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString("mk-MK", { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }
  return renderTemplate`${maybeRenderHead()}<article${addAttribute(["news-cluster", { "lead-story": isLead }], "class:list")} data-astro-cid-ibl2wg7k> ${thumbSrc && renderTemplate`<div class="cluster-thumb-wrap" data-astro-cid-ibl2wg7k> <a${addAttribute(`/cluster/${cluster.cluster_id}`, "href")} data-astro-cid-ibl2wg7k> <img${addAttribute(thumbSrc, "src")}${addAttribute(main.title, "alt")} class="cluster-thumb"${addAttribute(isLead ? "eager" : "lazy", "loading")} data-astro-cid-ibl2wg7k> </a> </div>`} <div class="cluster-main" data-astro-cid-ibl2wg7k> <div class="cluster-meta" data-astro-cid-ibl2wg7k> <span class="text-accent" data-astro-cid-ibl2wg7k>${main.source}</span> <span class="dot" data-astro-cid-ibl2wg7k>·</span> <span data-astro-cid-ibl2wg7k>${getTimeStr(main.created_at)}</span> ${cluster.is_breaking && renderTemplate`<span class="breaking-dot" data-astro-cid-ibl2wg7k>● LIVE</span>`} </div> <a${addAttribute(`/cluster/${cluster.cluster_id}`, "href")} class="headline-link" data-astro-cid-ibl2wg7k> <h2${addAttribute(["cluster-headline", isLead ? "text-lead" : "text-standard"], "class:list")} data-astro-cid-ibl2wg7k> ${main.title} </h2> </a> ${main.description && renderTemplate`<p class="cluster-excerpt" data-astro-cid-ibl2wg7k> ${main.description.length > (isLead ? 200 : 120) ? main.description.substring(0, isLead ? 200 : 120) + "..." : main.description} </p>`} ${isLead && cluster.articles.length > 1 && renderTemplate`<div class="lead-sub-headlines" data-astro-cid-ibl2wg7k> ${cluster.articles.slice(1, 4).map((sub) => renderTemplate`<div class="sub-h-item" data-astro-cid-ibl2wg7k> <span class="sub-source" data-astro-cid-ibl2wg7k>${sub.source}:</span> <a${addAttribute(`/cluster/${cluster.cluster_id}`, "href")} class="sub-link" data-astro-cid-ibl2wg7k> ${sub.title} </a> </div>`)} </div>`}  ${cluster.entities && cluster.entities.length > 0 && renderTemplate`<div class="entity-tags" data-astro-cid-ibl2wg7k> ${cluster.entities.slice(0, 3).map((name) => renderTemplate`<a${addAttribute(`/entity/${encodeURIComponent(name)}`, "href")} class="entity-tag" data-astro-cid-ibl2wg7k> ${name} </a>`)} </div>`} <div class="cluster-meta footer-meta" data-astro-cid-ibl2wg7k> <span data-astro-cid-ibl2wg7k>${cluster.articles.length} извори анализирани</span> </div> </div> </article>`;
}, "/home/emiloffingen/presek/web/src/components/NewsCard.astro", void 0);

export { $$NewsCard as $ };
