# Briefing Language Separation Fix

## 🎯 Problem Identified

The daily briefing system is generating mixed-language content because:
1. The `_load_daily_brief_clusters()` function loads articles without language filtering
2. The `daily_briefings` table stores a single briefing without language distinction
3. Both Serbian and Macedonian articles are being combined into one briefing

## 📋 Current Implementation

```sql
-- tasks/delivery.py line ~XXX
SELECT cluster_id, title, description, summary, source, category, topic, created_at 
FROM articles 
WHERE created_at >= NOW() - INTERVAL '24 hours' 
ORDER BY created_at DESC LIMIT 180
```

This query pulls articles from both languages, resulting in mixed-language briefings.

## ✅ Solution Options

### Option 1: Add Language Filtering (Recommended)

Modify the query to filter by language:

```sql
-- For Serbian briefing
SELECT cluster_id, title, description, summary, source, category, topic, created_at 
FROM articles 
WHERE created_at >= NOW() - INTERVAL '24 hours' 
  AND (source LIKE '%.rs' OR source LIKE '%.com' OR source IN ('B92', 'Nova.rs', 'Kurir.rs'))
ORDER BY created_at DESC LIMIT 180

-- For Macedonian briefing
SELECT cluster_id, title, description, summary, source, category, topic, created_at 
FROM articles 
WHERE created_at >= NOW() - INTERVAL '24 hours' 
  AND (source LIKE '%.mk' OR source IN ('360 Stepeni', 'A1on', 'Alsat'))
ORDER BY created_at DESC LIMIT 180
```

### Option 2: Add Language Column to daily_briefings

```sql
ALTER TABLE daily_briefings ADD COLUMN lang CHAR(2);

-- Then update generation to specify language
INSERT INTO daily_briefings (date, content, lang) 
VALUES (CURRENT_DATE, %s, 'sr') 
ON CONFLICT (date, lang) DO UPDATE SET content = EXCLUDED.content;
```

### Option 3: Create Separate Tables

```sql
CREATE TABLE daily_briefings_sr (
    date DATE PRIMARY KEY,
    content TEXT
);

CREATE TABLE daily_briefings_mk (
    date DATE PRIMARY KEY,
    content TEXT
);
```

## 🎯 Recommended Solution

**Option 1: Add Language Filtering** is the simplest and most effective:

1. **Pros**:
   - Minimal database changes
   - Easy to implement
   - Maintains backward compatibility

2. **Implementation Steps**:
   - Modify `_load_daily_brief_clusters()` to accept language parameter
   - Update briefing generation to create separate briefings
   - Store briefings with language distinction

## 📋 Files to Modify

1. **tasks/delivery.py**
   - Add language parameter to `_load_daily_brief_clusters()`
   - Filter articles by language in SQL query

2. **tasks/intelligence.py**
   - Update briefing endpoint to support language parameter
   - Modify response to include language

3. **Database Schema**
   - Consider adding language column to `daily_briefings` table

## 🎉 Expected Result

After implementation:
- ✅ Serbian briefing: Only Serbian language content
- ✅ Macedonian briefing: Only Macedonian language content
- ✅ Clear language separation
- ✅ Improved user experience

## 📝 Next Steps

1. **Development**: Implement language filtering in `_load_daily_brief_clusters()`
2. **Testing**: Verify briefings generate correctly for each language
3. **Deployment**: Update production system with changes
4. **Monitoring**: Ensure briefings maintain quality and relevance

## 🎯 Impact

- **User Experience**: Significantly improved with language-specific content
- **Content Quality**: Higher relevance for each language audience
- **System Maintainability**: Clear separation of concerns
- **Future Growth**: Easy to add more languages if needed

**Status**: Analysis complete, ready for implementation