#!/usr/bin/env python3
"""
Database Performance Analysis for Presek
Analyzes query patterns and suggests optimizations.
"""

import os
import re
from pathlib import Path
from typing import Dict, List

def analyze_query_patterns() -> Dict[str, List[str]]:
    """Analyze SQL query patterns in the codebase."""
    patterns = {
        'frequent_queries': [],
        'join_queries': [],
        'order_by_queries': [],
        'where_clauses': [],
        'complex_queries': []
    }
    
    # Key directories to analyze
    directories = ['core', 'routes', 'tasks', 'nlp']
    
    for directory in directories:
        if not os.path.exists(directory):
            continue
            
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        content = Path(file_path).read_text()
                        
                        # Find SQL queries
                        sql_matches = re.finditer(
                            r'"""[^"]*SELECT[^"]*"""',
                            content,
                            re.IGNORECASE | re.DOTALL
                        )
                        
                        for match in sql_matches:
                            query = match.group(0)
                            if 'SELECT' in query.upper():
                                patterns['frequent_queries'].append(f"{file_path}: {query[:100]}...")
                                
                                if 'JOIN' in query.upper():
                                    patterns['join_queries'].append(f"{file_path}: {query[:100]}...")
                                if 'ORDER BY' in query.upper():
                                    patterns['order_by_queries'].append(f"{file_path}: {query[:100]}...")
                                if 'WHERE' in query.upper():
                                    patterns['where_clauses'].append(f"{file_path}: {query[:100]}...")
                                
                                # Check for complex queries
                                if len(query) > 200 and (query.count('JOIN') > 1 or query.count('WHERE') > 2):
                                    patterns['complex_queries'].append(f"{file_path}: {query[:150]}...")
                                    
                    except Exception as e:
                        print(f"❌ Error reading {file_path}: {e}")
    
    return patterns

def suggest_indexes() -> List[Dict]:
    """Suggest database indexes based on query patterns."""
    suggestions = [
        {
            "table": "articles",
            "columns": ["created_at"],
            "reason": "Frequently used in ORDER BY and WHERE clauses for recent articles",
            "query_example": "SELECT * FROM articles WHERE created_at > NOW() - INTERVAL '24 hours' ORDER BY created_at DESC"
        },
        {
            "table": "clusters",
            "columns": ["has_synthesis", "homepage_score"],
            "reason": "Used for homepage cluster selection and filtering",
            "query_example": "SELECT * FROM clusters WHERE has_synthesis = TRUE ORDER BY homepage_score DESC"
        },
        {
            "table": "clusters",
            "columns": ["created_at"],
            "reason": "Used for time-based queries and recent cluster retrieval",
            "query_example": "SELECT * FROM clusters WHERE created_at > NOW() - INTERVAL '7 days'"
        },
        {
            "table": "articles",
            "columns": ["cluster_id"],
            "reason": "Used for joining articles with clusters and cluster-based queries",
            "query_example": "SELECT * FROM articles WHERE cluster_id = 'abc123'"
        },
        {
            "table": "clusters",
            "columns": ["lang"],
            "reason": "Used for language-specific queries and filtering",
            "query_example": "SELECT * FROM clusters WHERE lang = 'sr' ORDER BY homepage_score DESC"
        },
        {
            "table": "articles",
            "columns": ["source", "created_at"],
            "reason": "Composite index for source-based recent article queries",
            "query_example": "SELECT * FROM articles WHERE source = 'source1' AND created_at > NOW() - INTERVAL '1 day'"
        }
    ]
    
    return suggestions

def analyze_caching_strategy() -> Dict[str, List[str]]:
    """Analyze current caching strategy and suggest improvements."""
    analysis = {
        'current_cache_usage': [],
        'missing_cache_opportunities': [],
        'recommendations': []
    }
    
    # Check for existing cache usage
    cache_files = [
        'core/cache.py',
        'routes/news.py',
        'routes/home.py',
        'core/api_fast.py'
    ]
    
    for file in cache_files:
        if os.path.exists(file):
            content = Path(file).read_text()
            if '@cached_response' in content or 'cache.get(' in content or 'cache.set(' in content:
                analysis['current_cache_usage'].append(f"✅ {file}: Uses caching")
            else:
                analysis['missing_cache_opportunities'].append(f"⚠️  {file}: No caching detected")
    
    # Common endpoints that could benefit from caching
    analysis['recommendations'] = [
        "Cache homepage data (30-60 seconds)",
        "Cache cluster lists by language (60 seconds)",
        "Cache article details (120 seconds)",
        "Cache trending topics (300 seconds)",
        "Implement cache invalidation on content updates"
    ]
    
    return analysis

def generate_sql_index_script() -> str:
    """Generate SQL script for recommended indexes."""
    suggestions = suggest_indexes()
    
    script = "-- Presek Database Performance Optimization Script\n"
    script += "-- Recommended indexes for performance improvement\n\n"
    
    for i, suggestion in enumerate(suggestions, 1):
        script += f"-- #{i}. {suggestion['reason']}\n"
        script += f"CREATE INDEX IF NOT EXISTS idx_{suggestion['table']}_{'_'.join(suggestion['columns'])} \n"
        script += f"    ON {suggestion['table']} ({', '.join(suggestion['columns'])});\n\n"
    
    script += "-- Verify indexes\n"
    script += "\nSELECT indexname, indexdef FROM pg_indexes \n"
    script += "WHERE tablename IN ('articles', 'clusters') \n"
    script += "ORDER BY tablename, indexname;\n"
    
    return script

def main():
    print("🔍 Presek Database Performance Analysis")
    print("=" * 50)
    
    # Analyze query patterns
    print("\n📊 Analyzing query patterns...")
    patterns = analyze_query_patterns()
    
    print(f"   Found {len(patterns['frequent_queries'])} frequent queries")
    print(f"   Found {len(patterns['join_queries'])} JOIN queries")
    print(f"   Found {len(patterns['order_by_queries'])} ORDER BY queries")
    print(f"   Found {len(patterns['complex_queries'])} complex queries")
    
    # Suggest indexes
    print("\n🎯 Generating index recommendations...")
    suggestions = suggest_indexes()
    print(f"   {len(suggestions)} index recommendations generated")
    
    # Analyze caching
    print("\n🧊 Analyzing caching strategy...")
    cache_analysis = analyze_caching_strategy()
    print(f"   Current cache usage: {len(cache_analysis['current_cache_usage'])} files")
    print(f"   Missing opportunities: {len(cache_analysis['missing_cache_opportunities'])} files")
    
    # Generate SQL script
    print("\n📋 Generating SQL optimization script...")
    sql_script = generate_sql_index_script()
    Path("scripts/optimize_database.sql").write_text(sql_script)
    print("   ✅ Written scripts/optimize_database.sql")
    
    # Generate performance report
    print("\n📄 Generating performance report...")
    
    report = "# Database Performance Optimization Report\n\n"
    report += "## Query Pattern Analysis\n\n"
    report += f"- **Frequent Queries:** {len(patterns['frequent_queries'])}\n"
    report += f"- **JOIN Queries:** {len(patterns['join_queries'])}\n"
    report += f"- **ORDER BY Queries:** {len(patterns['order_by_queries'])}\n"
    report += f"- **Complex Queries:** {len(patterns['complex_queries'])}\n\n"
    
    report += "## Recommended Indexes\n\n"
    for i, suggestion in enumerate(suggestions, 1):
        report += f"### {i}. {suggestion['table']} ({', '.join(suggestion['columns'])})\n\n"
        report += f"**Reason:** {suggestion['reason']}\n\n"
        report += f"**Example Query:**\n```sql\n{suggestion['query_example']}\n```\n\n"
        report += f"**SQL:**\n```sql\nCREATE INDEX idx_{suggestion['table']}_{'_'.join(suggestion['columns'])} \n    ON {suggestion['table']} ({', '.join(suggestion['columns'])});\n```\n\n"
    
    report += "## Caching Strategy Analysis\n\n"
    report += "### Current Cache Usage\n\n"
    for item in cache_analysis['current_cache_usage']:
        report += f"- {item}\n"
    
    if cache_analysis['missing_cache_opportunities']:
        report += "\n### Missing Cache Opportunities\n\n"
        for item in cache_analysis['missing_cache_opportunities']:
            report += f"- {item}\n"
    
    report += "\n### Caching Recommendations\n\n"
    for i, rec in enumerate(cache_analysis['recommendations'], 1):
        report += f"{i}. {rec}\n"
    
    report += "\n## Implementation Steps\n\n"
    report += "1. **Apply database indexes:**\n```bash\npsql -f scripts/optimize_database.sql\n```\n\n"
    report += "2. **Implement caching for key endpoints:**\n```python\n@router.get(\"/home\")\n@cached_response(timeout=60)\nasync def get_home(...):\n    # ... existing code\n```\n\n"
    report += "3. **Monitor performance:**\n```bash\n# Before and after comparison\nEXPLAIN ANALYZE SELECT * FROM clusters WHERE has_synthesis = TRUE ORDER BY homepage_score DESC;\n```\n\n"
    report += "4. **Test thoroughly:**\n```bash\npython -m pytest tests/test_api.py tests/test_performance.py\n```\n"
    
    Path("DATABASE_PERFORMANCE_REPORT.md").write_text(report)
    print("   ✅ Written DATABASE_PERFORMANCE_REPORT.md")
    
    print("\n🎉 Database performance analysis complete!")
    print("   📋 Report: DATABASE_PERFORMANCE_REPORT.md")
    print("   📄 SQL Script: scripts/optimize_database.sql")
    print("\n💡 Recommended next steps:")
    print("   1. Review DATABASE_PERFORMANCE_REPORT.md")
    print("   2. Apply indexes: psql -f scripts/optimize_database.sql")
    print("   3. Implement caching recommendations")
    print("   4. Test performance improvements")

if __name__ == "__main__":
    main()