// Alias for /rss.xml — some feed readers expect /feed.xml. Re-export the same
// handler so there is a single source of truth for the feed.
export { GET } from './rss.xml';
