# Presek - Macedonian News Aggregation Frontend

A modern, production-ready React + TypeScript frontend for Presek, a Macedonian news aggregation platform with AI-powered synthesis.

## 🎯 Features

- **News Feed**: Browse curated news clusters with semantic grouping
- **Smart Filtering**: Filter by geographic region and topic categories
- **AI Synthesis**: Read AI-generated summaries and multiple perspectives on news stories
- **Interactive Q&A**: Ask questions about specific clusters powered by AI
- **Real-time Stats**: View platform statistics, trending keywords, and news velocity
- **Daily Briefing**: Get a comprehensive daily news briefing
- **Image Optimization**: Automatic image proxying, resizing, and WebP conversion
- **Rate Limiting**: Built-in rate limit handling and error recovery
- **Responsive Design**: Fully responsive with Tailwind CSS
- **Server-Sent Events**: Real-time updates for new articles (when backend supports)

## 🏗️ Tech Stack

- **React 18.3** - UI framework
- **TypeScript 5.5** - Type safety
- **Vite 5.4** - Fast build tooling
- **React Router 6.26** - Client-side routing
- **Zustand 4.5** - State management
- **Axios 1.7** - HTTP client with interceptors
- **Tailwind CSS 3.4** - Utility-first styling
- **PostCSS & Autoprefixer** - CSS processing

## 🚀 Getting Started

### Prerequisites
- Node.js 16+ and npm 8+
- Backend API running on `http://localhost:5000`

### Installation

```bash
# Install dependencies
npm install

# Create environment file (optional, defaults are provided)
cp .env.example .env.local
```

### Development

```bash
# Start dev server with hot reload
npm run dev
```

The app will be available at `http://localhost:5173` with automatic proxy to the backend API.

### Production Build

```bash
# Build for production
npm run build

# Preview production build locally
npm run preview
```

Build output is in `static/dist/` for integration with the Flask backend.

## 📁 Project Structure

```
src/
├── api/              # API client with type-safe methods
│   └── client.ts     # Axios instance with interceptors
├── components/       # Reusable React components
│   ├── ArticleCard.tsx
│   ├── ClusterCard.tsx
│   └── TrendingSidebar.tsx
├── pages/            # Page components (routed)
│   ├── HomePage.tsx
│   ├── ClusterDetailPage.tsx
│   ├── StatsPage.tsx
│   └── BriefingPage.tsx
├── store/            # Zustand state stores
│   └── useNewsStore.ts
├── hooks/            # Custom React hooks
│   └── useSSE.ts     # Server-Sent Events hook
├── types/            # TypeScript interfaces
│   └── index.ts      # All API response types
├── App.tsx           # Root component with routing
├── main.tsx          # React DOM entry point
└── index.css         # Tailwind styles
```

## 🔌 API Integration

### Client Methods

```typescript
import { apiClient } from '@/api/client';

// Fetch news with filters
const news = await apiClient.getNews({
  country: '🇲🇰',
  category: 'Македонија',
  topic: 'Политика',
  page: 0,
  page_size: 20,
  sort: 'recent'
});

// Get cluster details with synthesis
const detail = await apiClient.getClusterDetail('cluster-id-123');

// Get trending keywords
const trending = await apiClient.getTrending();

// Stats and analytics
const stats = await apiClient.getFullStats();

// Ask AI about a cluster
const answer = await apiClient.chatCluster('cluster-id', 'Your question?');

// Other endpoints
await apiClient.getStats();
await apiClient.getPulse();
await apiClient.getWeather();
await apiClient.getBriefing();
await apiClient.getHealth();
```

### Image Optimization

```typescript
// Automatically optimizes images to WebP, adds LQIP, resizes
const url = apiClient.getImageUrl(originalUrl, width);
```

## 🎨 Styling

Uses **Tailwind CSS** for all styling. Key utilities:
- Color scheme: Blue for primary (600), gray for neutral
- Responsive grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`
- Custom animations: `animate-spin`, `animate-pulse`
- Dark mode: Supported via Tailwind (toggle in config)

### Custom CSS

Global styles in `src/index.css`:
- Utility functions: `line-clamp-2`, `line-clamp-3`
- Prose styling for text content
- Tailwind directives

## 📊 State Management (Zustand)

### News Store

```typescript
const {
  clusters,         // NewsCluster[]
  isLoading,        // boolean
  error,            // string | null
  page,             // number
  pageSize,         // number
  hasMore,          // boolean
  totalClusters,    // number
  setClusters,      // (clusters) => void
  addClusters,      // (clusters) => void
  setLoading,       // (loading) => void
  setError,         // (error) => void
  setPage,          // (page) => void
  setPageSize,      // (size) => void
  setHasMore,       // (hasMore) => void
  setTotalClusters, // (total) => void
  reset,            // () => void
} = useNewsStore();
```

### UI Store

```typescript
const {
  sidebarOpen,      // boolean
  selectedCategory, // string
  selectedTopic,    // string
  searchQuery,      // string
  stats,            // FullStats | null
  setSidebarOpen,   // (open) => void
  setSelectedCategory,
  setSelectedTopic,
  setSearchQuery,
  setStats,
} = useUIStore();
```

## 🌐 Environment Variables

```env
VITE_API_URL=http://localhost:5000  # Backend API URL for development
```

In production, the build bundles everything and proxies through the Flask backend.

## 🧪 Type Safety

All API responses are fully typed. Key types:

```typescript
interface Article { ... }
interface NewsCluster { ... }
interface ClusterDetail extends NewsCluster { ... }
interface TrendingWord { ... }
interface Stats { ... }
interface FullStats extends Stats { ... }
interface Weather { ... }
interface HealthResponse { ... }
interface BriefingResponse { ... }
interface ChatResponse { ... }
```

## 🔄 Real-Time Updates

Hook for Server-Sent Events:

```typescript
const { disconnect } = useSSE('/api/live', (update) => {
  console.log('New articles:', update.new_articles);
});

// Manual disconnect
disconnect();
```

## ⚡ Performance Optimizations

- **Code splitting**: Automatic via Vite
- **Image optimization**: WebP format, LQIP, width-based resizing
- **Caching**: Client-side memoization of cluster details
- **Lazy loading**: Images with intersection observer
- **Bundle size**: ~230KB gzipped (React + Router + Axios included)
- **CSS**: Tailwind purges unused styles (~16KB gzipped)

## 🐛 Error Handling

- **Rate limiting**: Automatic backoff detection (429 status)
- **Network errors**: Graceful error messages
- **Stale data**: Cluster data is immutable after synthesis
- **Navigation**: 404 routes redirect to home

## 📱 Browser Support

- Chrome/Edge 88+
- Firefox 78+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

## 🔐 Security

- No authentication stored client-side (API is public)
- CSRF protection: Flask backend handles
- SSRF protection: Image proxy validates URLs
- XSS prevention: React auto-escapes, Tailwind for CSS safety

## 🚢 Deployment

### Development
```bash
npm run dev
```
Server runs on `http://localhost:5173` with hot reload.

### Production
```bash
npm run build
```
Output: `static/dist/index.html` + assets

Flask backend serves this from `/static/dist/`:
```python
app.use_static_files('/static/dist/index.html', ...)
```

## 📝 Available Routes

- `/` - Home page (news feed)
- `/cluster/:clusterId` - Cluster detail page with synthesis
- `/stats` - Statistics dashboard
- `/briefing` - Daily briefing
- `*` - 404 redirect to home

## 🔧 Development Tips

1. **Hot Reload**: Changes to files automatically refresh in browser
2. **TypeScript**: All code is type-checked before build
3. **Linting**: Run `npm run build` to check for errors
4. **Debugging**: Use React DevTools browser extension
5. **Network**: Open DevTools → Network tab to inspect API calls

## 📦 Build Size Analysis

Run Vite's built-in analyzer:
```bash
npm run build  # Already shows gzipped sizes
```

Main bundle: 229KB (gzip: 74KB)
CSS: 16.5KB (gzip: 3.8KB)
Total: ~78KB gzipped

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/new-feature`
3. Commit changes: `git commit -m 'Add new feature'`
4. Push to branch: `git push origin feature/new-feature`
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

---

**Built with ❤️ for Macedonian news enthusiasts**
