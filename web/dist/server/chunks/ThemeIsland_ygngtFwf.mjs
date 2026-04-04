import { c as createComponent } from './astro-component_CBmWG5JF.mjs';
import 'piccolore';
import { r as renderTemplate, j as renderSlot, k as renderHead, g as addAttribute } from './server_CF7VxRY2.mjs';
import 'clsx';
import { jsxs, Fragment, jsx } from 'react/jsx-runtime';
import { useState, useRef, useEffect } from 'react';
import { Search, X, Moon, Sun } from 'lucide-react';

var __freeze = Object.freeze;
var __defProp = Object.defineProperty;
var __template = (cooked, raw) => __freeze(__defProp(cooked, "raw", { value: __freeze(cooked.slice()) }));
var _a;
const $$Layout = createComponent(($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$props, $$slots);
  Astro2.self = $$Layout;
  const { title, description = "Presek - Македонска агрегација на вести со ЈИ синтеза" } = Astro2.props;
  return renderTemplate(_a || (_a = __template(['<html lang="mk"> <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0"><link rel="icon" type="image/svg+xml" href="/logo.svg"><meta name="generator"', '><meta name="description"', '><!-- Google Fonts: Lora (Headlines) + Inter (Reading & UI) --><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400..700;1,400..700&family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet"><title>', " | Пресек</title><script>\n			// Immediate theme sync to prevent flicker\n			const getTheme = () => {\n				if (typeof localStorage !== 'undefined' && localStorage.getItem('theme')) {\n					return localStorage.getItem('theme');\n				}\n				return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';\n			};\n			const theme = getTheme();\n			if (theme === 'dark') {\n				document.documentElement.classList.add('dark');\n			} else {\n				document.documentElement.classList.remove('dark');\n			}\n		<\/script>", '</head> <body class="bg-primary text-primary antialiased transition-colors duration-300"> ', "</body></html>"])), addAttribute(Astro2.generator, "content"), addAttribute(description, "content"), title, renderHead(), renderSlot($$result, $$slots["default"]));
}, "/home/emiloffingen/presek/web/src/layouts/Layout.astro", void 0);

function SearchIsland() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef(null);
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen(true);
      }
      if (e.key === "Escape") setIsOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);
  const handleSearch = (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    window.location.href = `/?q=${encodeURIComponent(query.trim())}`;
  };
  return /* @__PURE__ */ jsxs(Fragment, { children: [
    /* @__PURE__ */ jsxs(
      "button",
      {
        onClick: () => setIsOpen(true),
        className: "p-2 hover:bg-secondary rounded-full transition-colors group flex items-center gap-2",
        "aria-label": "Пребарај",
        children: [
          /* @__PURE__ */ jsx(Search, { size: 18, className: "text-muted group-hover:text-primary" }),
          /* @__PURE__ */ jsx("span", { className: "hidden lg:inline text-[10px] font-black text-muted uppercase tracking-widest border border-color px-1.5 py-0.5 rounded", children: "Ctrl K" })
        ]
      }
    ),
    isOpen && /* @__PURE__ */ jsx("div", { className: "fixed inset-0 z-[100] bg-primary/95 backdrop-blur-md flex flex-col items-center pt-24 px-4 transition-all duration-300", children: /* @__PURE__ */ jsxs("div", { className: "w-full max-w-2xl relative", children: [
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: () => setIsOpen(false),
          className: "absolute -top-12 right-0 p-2 text-muted hover:text-primary transition-colors",
          children: /* @__PURE__ */ jsx(X, { size: 24 })
        }
      ),
      /* @__PURE__ */ jsxs("form", { onSubmit: handleSearch, className: "relative", children: [
        /* @__PURE__ */ jsx(Search, { className: "absolute left-0 top-1/2 -translate-y-1/2 text-muted", size: 28 }),
        /* @__PURE__ */ jsx(
          "input",
          {
            ref: inputRef,
            type: "text",
            value: query,
            onChange: (e) => setQuery(e.target.value),
            placeholder: "Што ве интересира денес?",
            className: "w-full bg-transparent border-b-2 border-color focus:border-accent py-4 pl-12 pr-4 text-2xl md:text-4xl font-serif font-bold text-primary outline-none transition-colors"
          }
        ),
        /* @__PURE__ */ jsxs("div", { className: "mt-4 flex items-center gap-2 text-muted", children: [
          /* @__PURE__ */ jsx("span", { className: "text-[10px] font-black uppercase tracking-widest bg-secondary px-2 py-1 rounded", children: "Semantic Search" }),
          /* @__PURE__ */ jsx("span", { className: "text-xs italic", children: "Пишувајте на природен јазик за попаметни резултати" })
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "mt-12", children: [
        /* @__PURE__ */ jsx("h3", { className: "rail-label text-muted", children: "Чести пребарувања" }),
        /* @__PURE__ */ jsx("div", { className: "flex flex-wrap gap-2 mt-4", children: ["Избори", "Економија", "Технологија", "Вештачка Интелигенција"].map((tag) => /* @__PURE__ */ jsx(
          "button",
          {
            onClick: () => {
              setQuery(tag);
              window.location.href = `/?q=${encodeURIComponent(tag)}`;
            },
            className: "px-4 py-2 bg-secondary hover:bg-accent hover:text-white transition-all rounded-sm text-xs font-bold uppercase tracking-wider",
            children: tag
          },
          tag
        )) })
      ] })
    ] }) })
  ] });
}

function ThemeIsland() {
  const [theme, setTheme] = useState(() => {
    if (typeof localStorage !== "undefined" && localStorage.getItem("theme")) {
      return localStorage.getItem("theme");
    }
    return "dark";
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("theme", theme);
    const meta = document.getElementById("themeMeta");
    if (meta) meta.setAttribute("content", theme === "dark" ? "#0f1117" : "#FFFFFF");
  }, [theme]);
  return /* @__PURE__ */ jsx(
    "button",
    {
      onClick: () => setTheme(theme === "light" ? "dark" : "light"),
      className: "p-2 hover:bg-secondary rounded-full transition-colors group",
      "aria-label": "Промени тема",
      children: theme === "light" ? /* @__PURE__ */ jsx(Moon, { size: 18, className: "text-muted group-hover:text-primary" }) : /* @__PURE__ */ jsx(Sun, { size: 18, className: "text-muted group-hover:text-primary" })
    }
  );
}

export { $$Layout as $, SearchIsland as S, ThemeIsland as T };
