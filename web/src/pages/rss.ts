// Alias for /rss.xml — some feed readers and legacy subscribers expect /rss.
// Re-export the same handler so the feed has a single source of truth.
export { GET } from './rss.xml';
