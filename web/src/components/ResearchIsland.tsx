import React from 'react';
import { BrainCircuit, ExternalLink } from 'lucide-react';

interface ResearchIslandProps {
  clusterId: string;
  initialHeadline: string;
}

export default function ResearchIsland({ clusterId, initialHeadline }: ResearchIslandProps) {
  // The complex deep-dive query for Google AI
  const promptTemplate = "Клучни факти, бројки и статистики, анализа, ставови и реакции на засегнатите страни, што е потврдено, а што не, прашања и одговори на тема: ";
  const fullQuery = `${promptTemplate}${initialHeadline}`;
  
  // udm=14 triggers the AI/Research mode (SGE) on Google
  const googleSearchUrl = `https://www.google.mk/search?q=${encodeURIComponent(fullQuery)}&udm=14`;

  return (
    <div className="ai-research-container mt-12 mb-16">
        <a 
          href={googleSearchUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="w-full group block relative overflow-hidden rounded-xl border border-border bg-secondary/20 p-8 text-left transition-all hover:bg-secondary/40 hover:border-nyt-accent/30 no-underline"
        >
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-start gap-5">
              <div className="p-4 bg-nyt-accent/10 rounded-2xl text-nyt-accent group-hover:scale-110 transition-transform duration-300">
                <BrainCircuit size={32} strokeWidth={1.5} />
              </div>
              <div>
                <h3 className="font-serif font-black text-xl md:text-2xl text-foreground mb-2 flex items-center gap-2">
                  Сакате подлабока анализа?
                </h3>
                <p className="text-muted-foreground text-sm max-w-lg leading-relaxed">
                  Истражете ја оваа тема со помош на Google AI. Добијте клучни факти, ставови и детални статистики директно од најголемиот светски пребарувач.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 font-black uppercase text-[10px] tracking-widest text-nyt-accent bg-background px-4 py-3 rounded-full border border-nyt-accent/20 group-hover:bg-nyt-accent group-hover:text-white transition-colors">
              Прашај го AI Истражувачот <ExternalLink size={12} className="ml-1" />
            </div>
          </div>
          
          {/* Subtle background glow */}
          <div className="absolute -right-20 -bottom-20 w-64 h-64 bg-nyt-accent/5 rounded-full blur-3xl opacity-0 group-hover:opacity-100 transition-opacity"></div>
        </a>
    </div>
  );
}
