import React, { useState, useEffect, useRef } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { 
  Search, 
  Settings, 
  Info, 
  TrendingUp, 
  User, 
  Building2, 
  HelpCircle, 
  ArrowLeft,
  Loader2,
  Share2
} from 'lucide-react';

interface Node {
  id: string;
  label: string;
  type: string;
  mentions: number;
  sentiment: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

interface Edge {
  source: string;
  target: string;
  weight: number;
  a_to_b?: number;
  b_to_a?: number;
  direction?: 'a_to_b' | 'b_to_a' | 'mutual';
}

const ui = {
  sr: {
    title: 'Interaktivni medijski graf',
    subtitle: 'Vizuelna mreža političkih aktera, institucija i njihovih međusobnih veza u domaćim medijima.',
    searchPlaceholder: 'Pretraži aktera...',
    sidebarTitle: 'Detalji subjekta',
    sidebarPlaceholder: 'Kliknite na bilo koji čvor na mapi da biste istražili njegove veze i sentiment.',
    category: 'Kategorija',
    mentions: 'Ukupno pominjanja',
    sentiment: 'Medijski ton',
    connections: 'Direktne veze',
    loading: 'Učitavanje medijske mreže...',
    noConnections: 'Nisu pronađene jače veze za ovog aktera.',
    minWeightLabel: 'Prag jačine veze',
    searchButton: 'Prikaži mrežu',
    reset: 'Resetuj na globalni prikaz',
    sentimentPositive: 'Pozitivan',
    sentimentNeutral: 'Neutralan',
    sentimentNegative: 'Negativan',
    viewProfile: 'Vidi kompletan profil aktera →'
  },
  mk: {
    title: 'Интерактивен медиумски граф',
    subtitle: 'Визуелна мрежа на политички актери, институции и нивните меѓусебни врски во домашните медиуми.',
    searchPlaceholder: 'Пребарај актер...',
    sidebarTitle: 'Детали за субјектот',
    sidebarPlaceholder: 'Кликнете на кој било јазол на мапата за да ги истражите неговите врски и сентимент.',
    category: 'Kатегорија',
    mentions: 'Вкупно споменувања',
    sentiment: 'Медиумски тон',
    connections: 'Директни врски',
    loading: 'Вчитување на медиумската мрежа...',
    noConnections: 'Не се пронајдени посилни врски за овој актер.',
    minWeightLabel: 'Праг на јачина на врска',
    searchButton: 'Прикажи мрежа',
    reset: 'Ресетирај на глобален приказ',
    sentimentPositive: 'Позитивен',
    sentimentNeutral: 'Неутрален',
    sentimentNegative: 'Негативен',
    viewProfile: 'Види комплетен профил на актерот →'
  }
};

export default function IntelligenceGraph({ lang = 'sr' }: { lang?: 'sr' | 'mk' }) {
  const t = ui[lang] || ui.sr;
  
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeEntity, setActiveEntity] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [minWeight, setMinWeight] = useState(2);
  
  // Group selection & synthesis states
  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [synthesis, setSynthesis] = useState<string | null>(null);
  const [synthesisLoading, setSynthesisLoading] = useState(false);
  const [citations, setCitations] = useState<any[]>([]);
  
  // Physics simulation state
  const [simNodes, setSimNodes] = useState<Node[]>([]);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null);

  // Fetch graph data
  const fetchGraphData = (entityName?: string) => {
    setLoading(true);
    const API_URL = apiBaseUrl();
    let url = `${API_URL}/intelligence/network-graph?min_weight=${minWeight}&limit=60`;
    if (entityName) {
      url += `&entity=${encodeURIComponent(entityName)}`;
    }
    
    fetch(url)
      .then((res) => res.json())
      .then((resData) => {
        if (resData.status === 'success') {
          setNodes(resData.nodes || []);
          setEdges(resData.edges || []);
          if (entityName) {
            const centerNode = resData.nodes.find((n: Node) => n.id.toLowerCase() === entityName.toLowerCase());
            if (centerNode) setSelectedNode(centerNode);
          }
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchGraphData(activeEntity || undefined);
  }, [activeEntity, minWeight]);

  // Run customized Verlet force integration simulation loop
  useEffect(() => {
    if (nodes.length === 0) {
      setSimNodes([]);
      return;
    }

    // Initialize positions randomly centered around svg (width 700, height 500)
    let simulationNodes: Node[] = nodes.map(node => {
      const existing = simNodes.find(n => n.id === node.id);
      if (existing && existing.x !== undefined) {
        return { ...node, x: existing.x, y: existing.y, vx: 0, vy: 0 };
      }
      return {
        ...node,
        x: 350 + (Math.random() - 0.5) * 200,
        y: 250 + (Math.random() - 0.5) * 200,
        vx: 0,
        vy: 0
      };
    });

    let running = true;
    const ticksPerFrame = 2; // Extra steps for stiffer constraint solving

    const tick = () => {
      if (!running) return;

      for (let step = 0; step < ticksPerFrame; step++) {
        // 1. Repulsion between all node pairs
        for (let i = 0; i < simulationNodes.length; i++) {
          for (let j = i + 1; j < simulationNodes.length; j++) {
            const n1 = simulationNodes[i];
            const n2 = simulationNodes[j];
            const dx = n2.x! - n1.x!;
            const dy = n2.y! - n1.y!;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            
            // Adjust repulsion distance based on popularity
            const minDist = 80 + Math.sqrt(n1.mentions) * 3 + Math.sqrt(n2.mentions) * 3;
            if (dist < minDist) {
              const force = (minDist - dist) * 0.04;
              const fx = (dx / dist) * force;
              const fy = (dy / dist) * force;
              
              if (n1.id !== draggedNodeId) {
                n1.vx! -= fx;
                n1.vy! -= fy;
              }
              if (n2.id !== draggedNodeId) {
                n2.vx! += fx;
                n2.vy! += fy;
              }
            }
          }
        }

        // 2. Attraction along relationship links (edges)
        for (const edge of edges) {
          const sourceNode = simulationNodes.find(n => n.id === edge.source);
          const targetNode = simulationNodes.find(n => n.id === edge.target);
          if (sourceNode && targetNode) {
            const dx = targetNode.x! - sourceNode.x!;
            const dy = targetNode.y! - sourceNode.y!;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            
            // Stiffer link spring force for heavy relationships
            const targetDist = 90 - Math.min(edge.weight * 3, 30);
            const force = (dist - targetDist) * 0.02;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;

            if (sourceNode.id !== draggedNodeId) {
              sourceNode.vx! += fx;
              sourceNode.vy! += fy;
            }
            if (targetNode.id !== draggedNodeId) {
              targetNode.vx! -= fx;
              targetNode.vy! -= fy;
            }
          }
        }

        // 3. Central gravity pulling nodes back to the center of viewbox
        for (const node of simulationNodes) {
          if (node.id === draggedNodeId) continue;
          
          const dx = 350 - node.x!;
          const dy = 250 - node.y!;
          node.vx! += dx * 0.005;
          node.vy! += dy * 0.005;

          // Apply friction damping
          node.x! += node.vx!;
          node.y! += node.vy!;
          node.vx! *= 0.8;
          node.vy! *= 0.8;

          // Confined boundaries
          node.x = Math.max(40, Math.min(660, node.x!));
          node.y = Math.max(40, Math.min(460, node.y!));
        }
      }

      setSimNodes([...simulationNodes]);
      requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
    return () => { running = false; };
  }, [nodes, edges, draggedNodeId]);

  // SVG Mouse handlers for drag operations
  const handleNodeMouseDown = (nodeId: string, e: React.MouseEvent) => {
    e.preventDefault();
    setDraggedNodeId(nodeId);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!draggedNodeId || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 700;
    const y = ((e.clientY - rect.top) / rect.height) * 500;
    
    setSimNodes(prev => prev.map(node => {
      if (node.id === draggedNodeId) {
        return { ...node, x, y, vx: 0, vy: 0 };
      }
      return node;
    }));
  };

  const handleMouseUpOrLeave = () => {
    setDraggedNodeId(null);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setActiveEntity(searchQuery.trim());
    }
  };

  const resetToGlobal = () => {
    setSearchQuery('');
    setActiveEntity(null);
    setSelectedNode(null);
    setSelectedNodes([]);
    setSynthesis(null);
    setCitations([]);
  };

  const handleNodeClick = (node: Node, e: React.MouseEvent) => {
    if (e.shiftKey) {
      setSelectedNodes(prev => {
        if (prev.includes(node.id)) {
          const next = prev.filter(id => id !== node.id);
          if (next.length === 0) setSelectedNode(null);
          else {
            const lastId = next[next.length - 1];
            const found = simNodes.find(n => n.id === lastId);
            if (found) setSelectedNode(found);
          }
          return next;
        } else {
          setSelectedNode(node);
          return [...prev, node.id];
        }
      });
    } else {
      setSelectedNode(node);
      setSelectedNodes([node.id]);
    }
  };

  const generateGroupSynthesis = () => {
    if (selectedNodes.length === 0) return;
    setSynthesisLoading(true);
    setSynthesis(null);
    setCitations([]);
    
    const API_URL = apiBaseUrl();
    fetch(`${API_URL}/intelligence/synthesize-nodes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        entities: selectedNodes,
        lang: lang
      })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'success') {
          setSynthesis(data.synthesis);
          setCitations(data.citations || []);
        } else {
          setSynthesis(data.message || 'Greška.');
        }
      })
      .catch(err => {
        console.error(err);
        setSynthesis('Greška prilikom povezivanja sa serverom.');
      })
      .finally(() => {
        setSynthesisLoading(false);
      });
  };

  // Helper for computing node styles
  const getNodeColor = (sentiment: number) => {
    if (sentiment > 0.15) return 'rgb(34, 197, 94)'; // Positive green
    if (sentiment < -0.15) return 'rgb(239, 68, 68)'; // Negative red
    return 'rgb(245, 158, 11)'; // Neutral gold
  };

  const getNodeRadius = (nodeType: string, mentions: number) => {
    const base = nodeType === 'ORG' ? 14 : 10;
    return base + Math.min(Math.sqrt(mentions) * 2, 22);
  };

  return (
    <div className="flex flex-col gap-6 md:gap-8 max-w-7xl mx-auto px-4 md:px-6">
      {/* Title Header */}
      <div className="border-b border-nyt-border pb-4 md:pb-6">
        <span className="nyt-section-label tracking-wide uppercase text-xs text-nyt-accent font-black block mb-2">
          {lang === 'sr' ? 'PRESEK INTEGRITY GRAPH' : 'ПРЕСЕК INTEGRITY GRAPH'}
        </span>
        <h1 className="font-serif text-3xl md:text-5xl font-black text-nyt-text tracking-tight mb-2">
          {t.title}
        </h1>
        <p className="text-muted-foreground font-serif italic text-sm md:text-base leading-relaxed max-w-3xl">
          {t.subtitle}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar Controls and Lookup Inspector */}
        <div className="lg:col-span-1 flex flex-col gap-5">
          {/* Controls box */}
          <div className="p-5 bg-card border border-nyt-border rounded-none shadow-sm flex flex-col gap-4">
            <h3 className="font-serif font-black text-lg text-nyt-text flex items-center gap-2 pb-2 border-b border-nyt-border">
              <Settings size={18} className="text-nyt-accent" />
              {lang === 'sr' ? 'Pretraga i filteri' : 'Пребарување и филтри'}
            </h3>
            
            {/* Search form */}
            <form onSubmit={handleSearchSubmit} className="relative">
              <input
                type="text"
                placeholder={t.searchPlaceholder}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-nyt-border rounded-none text-sm bg-background text-nyt-text focus:outline-none focus:border-nyt-accent"
              />
              <Search className="absolute left-3 top-2.5 text-muted-foreground" size={16} />
              {searchQuery && (
                <button
                  type="submit"
                  className="absolute right-2 top-1.5 px-3 py-1 bg-nyt-accent text-white text-xs font-black hover:bg-black uppercase tracking-wider"
                >
                  {t.searchButton}
                </button>
              )}
            </form>

            {/* Range threshold slider */}
            <div className="flex flex-col gap-2 mt-2">
              <div className="flex justify-between text-xs font-black uppercase text-muted-foreground">
                <span>{t.minWeightLabel}</span>
                <span className="text-nyt-accent font-black">{minWeight}</span>
              </div>
              <input
                type="range"
                min="1"
                max="8"
                value={minWeight}
                onChange={(e) => setMinWeight(parseInt(e.target.value))}
                className="accent-nyt-accent cursor-pointer h-1.5 bg-nyt-border w-full rounded-none"
              />
            </div>

            {activeEntity && (
              <button
                onClick={resetToGlobal}
                className="w-full mt-2 border border-nyt-accent text-nyt-accent font-black py-2 text-xs hover:bg-nyt-accent hover:text-white transition-colors duration-150 uppercase tracking-wider flex items-center justify-center gap-2"
              >
                <ArrowLeft size={14} />
                {t.reset}
              </button>
            )}
          </div>

          {/* Details Sidebar panel */}
          <div className="p-5 bg-card border border-nyt-border rounded-none shadow-sm flex flex-col gap-4 flex-grow">
            <h3 className="font-serif font-black text-lg text-nyt-text flex items-center gap-2 pb-2 border-b border-nyt-border">
              <Info size={18} className="text-nyt-accent" />
              {t.sidebarTitle}
            </h3>

            {selectedNodes.length > 1 ? (
              <div className="flex flex-col gap-4 animate-fade-in">
                <div>
                  <span className="text-[10px] uppercase tracking-wider font-black text-muted-foreground bg-nyt-border px-2 py-0.5 rounded-none block w-max mb-1">
                    {lang === 'sr' ? 'GRUPNA SELEKCIJA' : 'ГРУПНА СЕЛЕКЦИЈА'}
                  </span>
                  <h4 className="font-serif font-black text-xl text-nyt-text">
                    {lang === 'sr' ? 'Analiza aktera' : 'Анализа на актери'}
                  </h4>
                  <div className="flex flex-wrap gap-1.5 mt-2 max-h-24 overflow-y-auto border border-nyt-border p-2 bg-background/50">
                    {selectedNodes.map(name => (
                      <span 
                        key={name}
                        onClick={() => {
                          const found = nodes.find(n => n.id === name);
                          if (found) setSelectedNode(found);
                        }}
                        className="cursor-pointer text-xs font-serif font-bold text-nyt-text hover:text-nyt-accent border border-nyt-border px-2 py-0.5 bg-card flex items-center gap-1.5 hover:border-nyt-accent"
                      >
                        <span className="w-1.5 h-1.5 rounded-full bg-nyt-accent"></span>
                        {name}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="border-t border-nyt-border pt-4">
                  {!synthesis && !synthesisLoading && (
                    <button
                      onClick={generateGroupSynthesis}
                      className="w-full bg-black text-white hover:bg-nyt-accent font-black py-3 text-xs uppercase tracking-wider transition-colors duration-150 flex items-center justify-center gap-2 border border-black hover:border-nyt-accent"
                    >
                      <TrendingUp size={16} />
                      {lang === 'sr' ? 'Generiši analizu grupe' : 'Генерирај анализа на група'}
                    </button>
                  )}

                  {synthesisLoading && (
                    <div className="flex flex-col items-center justify-center py-8 text-center text-muted-foreground">
                      <Loader2 className="animate-spin text-nyt-accent mb-3" size={24} />
                      <p className="font-serif italic text-xs">
                        {lang === 'sr' ? 'Lokalni AI analitičar sastavlja izveštaj...' : 'Локалниот АИ аналитичар го составува извештајот...'}
                      </p>
                    </div>
                  )}

                  {synthesis && (
                    <div className="flex flex-col gap-4 animate-fade-in">
                      <div className="p-4 bg-card border-l-2 border-nyt-accent font-serif text-sm leading-relaxed text-nyt-text italic bg-background/30 max-h-72 overflow-y-auto scrollbar-thin">
                        <p className="whitespace-pre-line">{synthesis}</p>
                      </div>

                      {citations.length > 0 && (
                        <div className="flex flex-col gap-2 border-t border-nyt-border pt-3">
                          <span className="text-muted-foreground uppercase font-black text-[9px]">
                            {lang === 'sr' ? 'Korišćeni izvori' : 'Користени извори'}
                          </span>
                          <div className="grid grid-cols-1 gap-1.5 max-h-36 overflow-y-auto pr-1">
                            {citations.map(cite => (
                              <a
                                key={cite.id}
                                href={cite.link}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[11px] py-1.5 px-2 hover:bg-nyt-border cursor-pointer transition-colors duration-150 border border-nyt-border flex justify-between items-center"
                              >
                                <span className="font-serif font-bold text-nyt-text hover:text-nyt-accent truncate max-w-[80%]">
                                  [{cite.id}] {cite.title}
                                </span>
                                <span className="font-mono text-[9px] uppercase tracking-wider bg-nyt-border px-1.5 py-0.5 text-muted-foreground font-black">
                                  {cite.source}
                                </span>
                              </a>
                            ))}
                          </div>
                        </div>
                      )}

                      <button
                        onClick={() => { setSynthesis(null); setCitations([]); }}
                        className="w-full mt-2 border border-nyt-border text-muted-foreground font-black py-2 text-xs hover:bg-nyt-border transition-colors duration-150 uppercase tracking-wider"
                      >
                        {lang === 'sr' ? 'Nova analiza' : 'Нова анализа'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ) : selectedNode ? (
              <div className="flex flex-col gap-4 animate-fade-in">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="p-1.5 bg-nyt-border rounded-full text-nyt-accent">
                      {selectedNode.type === 'PERSON' ? <User size={16} /> : <Building2 size={16} />}
                    </span>
                    <span className="text-[10px] uppercase tracking-wider font-black text-muted-foreground bg-nyt-border px-2 py-0.5 rounded-none">
                      {selectedNode.type}
                    </span>
                  </div>
                  <h4 className="font-serif font-black text-xl text-nyt-text">{selectedNode.id}</h4>
                </div>

                <div className="grid grid-cols-2 gap-4 py-3 border-y border-nyt-border text-xs">
                  <div className="flex flex-col gap-1 border-r border-nyt-border pr-2">
                    <span className="text-muted-foreground uppercase font-black text-[9px]">{t.mentions}</span>
                    <strong className="text-lg text-nyt-text font-black">{selectedNode.mentions}</strong>
                  </div>
                  <div className="flex flex-col gap-1 pl-2">
                    <span className="text-muted-foreground uppercase font-black text-[9px]">{t.sentiment}</span>
                    <strong 
                      className={`text-lg font-black ${
                        selectedNode.sentiment > 0.15 ? 'text-green-600' : selectedNode.sentiment < -0.15 ? 'text-red-500' : 'text-amber-500'
                      }`}
                    >
                      {selectedNode.sentiment > 0.15 
                        ? t.sentimentPositive 
                        : selectedNode.sentiment < -0.15 
                          ? t.sentimentNegative 
                          : t.sentimentNeutral}
                      <span className="text-[10px] font-mono font-medium block text-muted-foreground">
                        ({selectedNode.sentiment > 0 ? '+' : ''}{selectedNode.sentiment.toFixed(2)})
                      </span>
                    </strong>
                  </div>
                </div>

                {/* Direct connections in this visible sub-graph */}
                <div className="flex flex-col gap-2">
                  <span className="text-muted-foreground uppercase font-black text-[9px]">{t.connections}</span>
                  <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
                    {edges
                      .filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id)
                      .map((edge, idx) => {
                        const isSource = edge.source === selectedNode.id;
                        const partnerName = isSource ? edge.target : edge.source;
                        
                        // Calculate percentage of direction
                        const total = (edge.a_to_b || 0) + (edge.b_to_a || 0) || edge.weight || 1;
                        const directionCount = isSource 
                          ? (edge.direction === 'b_to_a' ? edge.b_to_a : edge.a_to_b)
                          : (edge.direction === 'b_to_a' ? edge.a_to_b : edge.b_to_a);
                        
                        const ratio = Math.round(((directionCount || 0) / total) * 100);
                        
                        // Determine representation arrow
                        let relationArrow = '↔';
                        if (edge.direction && edge.direction !== 'mutual') {
                          relationArrow = edge.source === selectedNode.id ? '→' : '←';
                        }

                        return (
                          <div 
                            key={idx}
                            onClick={() => {
                              const found = nodes.find(n => n.id === partnerName);
                              if (found) setSelectedNode(found);
                            }}
                            className="flex flex-col gap-0.5 py-2 px-2 hover:bg-nyt-border cursor-pointer transition-colors duration-150 border-b border-nyt-border"
                          >
                            <div className="flex justify-between items-center text-xs">
                              <span className="font-serif font-bold text-nyt-text hover:text-nyt-accent">
                                {relationArrow} {partnerName}
                              </span>
                              <span className="font-mono text-nyt-accent font-black">w: {edge.weight}</span>
                            </div>
                            {edge.direction && edge.direction !== 'mutual' && (
                              <div className="text-[10px] text-muted-foreground font-mono">
                                {relationArrow === '→' 
                                  ? (lang === 'sr' ? `${selectedNode.id} utiče sa ${ratio}%` : `${selectedNode.id} влијае со ${ratio}%`)
                                  : (lang === 'sr' ? `${partnerName} utiče sa ${ratio}%` : `${partnerName} влијае со ${ratio}%`)}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    {edges.filter(edge => edge.source === selectedNode.id || edge.target === selectedNode.id).length === 0 && (
                      <p className="text-xs text-muted-foreground italic">{t.noConnections}</p>
                    )}
                  </div>
                </div>

                <a 
                  href={`${lang === 'sr' ? '/subjekt' : '/mk/subjekt'}/${encodeURIComponent(selectedNode.id)}`}
                  className="w-full mt-3 text-center bg-black text-white hover:bg-nyt-accent font-black py-2.5 text-xs uppercase tracking-wider transition-colors duration-150"
                >
                  {t.viewProfile}
                </a>
              </div>
            ) : (
              <div className="flex-grow flex flex-col justify-center items-center text-center p-6 text-muted-foreground">
                <HelpCircle size={36} className="text-nyt-border mb-3 animate-pulse" />
                <p className="text-xs font-serif leading-relaxed italic">{t.sidebarPlaceholder}</p>
              </div>
            )}
          </div>
        </div>

        {/* Visual Graph Viewbox Area */}
        <div className="lg:col-span-3 bg-card border border-nyt-border shadow-sm relative min-h-[500px] flex items-center justify-center select-none overflow-hidden">
          {loading && (
            <div className="absolute inset-0 bg-background/70 backdrop-blur-xs flex flex-col items-center justify-center z-20 animate-fade-in">
              <Loader2 className="animate-spin text-nyt-accent mb-3" size={36} />
              <p className="font-serif italic text-sm text-nyt-text">{t.loading}</p>
            </div>
          )}

          {simNodes.length === 0 && !loading ? (
            <div className="text-center p-8 z-10 flex flex-col items-center">
              <TrendingUp size={44} className="text-nyt-border mb-3" />
              <p className="font-serif italic text-muted-foreground">{lang === 'sr' ? 'Nema podataka u ovoj mreži.' : 'Нема податоци во оваа мрежа.'}</p>
            </div>
          ) : (
            <svg
              ref={svgRef}
              viewBox="0 0 700 500"
              className="w-full h-full cursor-grab active:cursor-grabbing z-10"
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUpOrLeave}
              onMouseLeave={handleMouseUpOrLeave}
            >
              {/* Grid Background */}
              <defs>
                <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                  <path d="M 30 0 L 0 0 0 30" fill="none" stroke="rgba(0, 0, 0, 0.03)" strokeWidth="1" />
                </pattern>
                {/* Arrow markers for edges */}
                <marker id="influence-arrow" viewBox="0 -5 10 10" refX="0" refY="0" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M0,-4L8,0L0,4" fill="rgba(0, 0, 0, 0.2)" />
                </marker>
                <marker id="influence-arrow-active" viewBox="0 -5 10 10" refX="0" refY="0" markerWidth="5" markerHeight="5" orient="auto">
                  <path d="M0,-4L8,0L0,4" fill="rgb(217, 119, 6)" />
                </marker>
              </defs>
              <style>{`
                @keyframes flow-forward {
                  to {
                    stroke-dashoffset: -20;
                  }
                }
                .flow-active {
                  stroke-dasharray: 6, 4;
                  animation: flow-forward 1.5s linear infinite;
                }
                .flow-active-highlight {
                  stroke-dasharray: 6, 4;
                  animation: flow-forward 0.9s linear infinite;
                }
              `}</style>
              <rect width="700" height="500" fill="url(#grid)" />

              {/* Edge Connections */}
              <g>
                {edges.map((edge, idx) => {
                  const sourceNode = simNodes.find(n => n.id === edge.source);
                  const targetNode = simNodes.find(n => n.id === edge.target);
                  if (!sourceNode || !targetNode) return null;
                  
                  const isHighlighted = selectedNode && (selectedNode.id === edge.source || selectedNode.id === edge.target);
                  
                  // Compute vector offset to place arrow head perfectly on target node boundary
                  const dx = targetNode.x! - sourceNode.x!;
                  const dy = targetNode.y! - sourceNode.y!;
                  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                  
                  const targetRadius = getNodeRadius(targetNode.type, targetNode.mentions);
                  const x2 = targetNode.x! - (dx / dist) * (targetRadius + 5);
                  const y2 = targetNode.y! - (dy / dist) * (targetRadius + 5);
                  
                  // Determine flow class
                  const isDirected = edge.direction && edge.direction !== 'mutual';
                  const flowClass = isDirected 
                    ? (isHighlighted ? 'flow-active-highlight' : 'flow-active') 
                    : '';

                  return (
                    <line
                      key={idx}
                      x1={sourceNode.x}
                      y1={sourceNode.y}
                      x2={x2}
                      y2={y2}
                      stroke={isHighlighted ? 'rgb(217, 119, 6)' : 'rgba(0, 0, 0, 0.08)'}
                      strokeWidth={isHighlighted ? Math.max(edge.weight / 1.5, 2.5) : Math.max(edge.weight / 2, 1.2)}
                      markerEnd={isDirected ? `url(#${isHighlighted ? 'influence-arrow-active' : 'influence-arrow'})` : undefined}
                      className={`transition-all duration-150 ${flowClass}`}
                    />
                  );
                })}
              </g>

              {/* Graph Nodes */}
              <g>
                {simNodes.map((node) => {
                  const radius = getNodeRadius(node.type, node.mentions);
                  const color = getNodeColor(node.sentiment);
                  const isSelected = selectedNode && selectedNode.id === node.id;
                  
                  return (
                    <g 
                      key={node.id} 
                      transform={`translate(${node.x},${node.y})`}
                      className="cursor-pointer group"
                      onMouseDown={(e) => handleNodeMouseDown(node.id, e)}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleNodeClick(node, e);
                      }}
                    >
                      {/* Selection shadow glow */}
                      {selectedNodes.includes(node.id) && (
                        <circle
                          r={radius + 8}
                          fill="rgba(217, 119, 6, 0.04)"
                          stroke="rgb(217, 119, 6)"
                          strokeWidth={isSelected ? "2.5" : "1.5"}
                          strokeDasharray={isSelected ? "none" : "3,3"}
                          className="animate-pulse"
                        />
                      )}
                      
                      {/* Core node shape */}
                      {node.type === 'ORG' ? (
                        <rect
                          x={-radius}
                          y={-radius}
                          width={radius * 2}
                          height={radius * 2}
                          rx="4"
                          fill={color}
                          stroke="#ffffff"
                          strokeWidth={isSelected ? '3' : '2'}
                          style={{ filter: 'drop-shadow(0px 2px 4px rgba(0, 0, 0, 0.12))' }}
                          className="transition-all duration-150 group-hover:scale-110"
                        />
                      ) : (
                        <circle
                          r={radius}
                          fill={color}
                          stroke="#ffffff"
                          strokeWidth={isSelected ? '3' : '2'}
                          style={{ filter: 'drop-shadow(0px 2px 4px rgba(0, 0, 0, 0.12))' }}
                          className="transition-all duration-150 group-hover:scale-110"
                        />
                      )}
                      
                      {/* Popularity indicator overlay */}
                      {node.type === 'ORG' ? (
                        <rect
                          x={-(radius - 4)}
                          y={-(radius - 4)}
                          width={(radius - 4) * 2}
                          height={(radius - 4) * 2}
                          rx="2"
                          fill="rgba(255, 255, 255, 0.25)"
                        />
                      ) : (
                        <circle
                          r={radius - 4}
                          fill="rgba(255, 255, 255, 0.25)"
                        />
                      )}

                      {/* Text tags */}
                      <text
                        y={radius + 14}
                        textAnchor="middle"
                        className={`font-serif text-[10px] select-none pointer-events-none transition-all duration-150 ${
                          isSelected 
                            ? 'font-black fill-nyt-accent scale-105' 
                            : 'font-bold fill-nyt-text group-hover:fill-nyt-accent'
                        }`}
                      >
                        {node.id}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>
          )}

          {/* Map stats badge */}
          <div className="absolute bottom-4 right-4 bg-background/90 border border-nyt-border px-3 py-1.5 text-[10px] font-black uppercase text-muted-foreground select-none z-10">
            {lang === 'sr' ? 'Aktivni čvorovi: ' : 'Активни јазли: '}
            <span className="text-nyt-text">{nodes.length}</span>
            <span className="mx-2 text-nyt-border">|</span>
            {lang === 'sr' ? 'Veze: ' : 'Врски: '}
            <span className="text-nyt-text">{edges.length}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
