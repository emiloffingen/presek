"""
db_monitoring.py - Database connection pool monitoring and management

Provides:
- Connection pool monitoring
- Automatic pool resizing
- Health checks and alerts
- Performance metrics
"""

import time
import logging
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

from core.database import db_manager as db
from core.logging_config import get_logger

log = get_logger("presek.db_monitoring")

@dataclass
class ConnectionPoolStats:
    """Connection pool statistics."""
    current_connections: int
    max_connections: int
    idle_connections: int
    waiting_requests: int
    utilization: float
    queue_size: int
    
    def is_healthy(self) -> bool:
        """Check if pool is in a healthy state."""
        return (self.utilization < 0.9 and 
                self.waiting_requests < 5 and
                self.queue_size < 10)
    
    def is_critical(self) -> bool:
        """Check if pool is in critical state."""
        return (self.utilization > 0.95 or 
                self.waiting_requests > 10 or
                self.queue_size > 20)

class DatabaseMonitor:
    """Database connection pool monitor."""
    
    def __init__(self):
        self.last_check_time = 0
        self.check_interval = 60  # seconds
        self.warning_threshold = 0.8  # 80% utilization
        self.critical_threshold = 0.95  # 95% utilization
        
    def get_pool_stats(self) -> Optional[ConnectionPoolStats]:
        """Get current connection pool statistics."""
        try:
            # Get pool statistics from the database connection
            stats = db.get_pool_stats()
            if not stats:
                return None
            
            # Handle different psycopg_pool versions and attribute names
            current = stats.get('current', 0)
            max_connections = stats.get('max', 1)
            idle = stats.get('idle', 0)
            waiting = stats.get('waiting', 0)
            queue_size = stats.get('queue_size', 0)
            
            # Fallback for different attribute names
            if current == 0 and 'current_connections' in stats:
                current = stats['current_connections']
            if max_connections == 1 and 'max_connections' in stats:
                max_connections = stats['max_connections']
            if idle == 0 and 'idle_connections' in stats:
                idle = stats['idle_connections']
            if waiting == 0 and 'waiting_requests' in stats:
                waiting = stats['waiting_requests']
            if queue_size == 0 and 'queue_size' in stats:
                queue_size = stats['queue_size']
            
            utilization = current / max_connections if max_connections > 0 else 0.0
            
            return ConnectionPoolStats(
                current_connections=current,
                max_connections=max_connections,
                idle_connections=idle,
                waiting_requests=waiting,
                utilization=utilization,
                queue_size=queue_size
            )
            
        except Exception as e:
            log.error(f"Failed to get pool stats: {e}")
            return None
    
    def check_pool_health(self) -> Dict[str, Any]:
        """Check connection pool health and return status."""
        stats = self.get_pool_stats()
        if not stats:
            return {
                'healthy': False,
                'error': 'Unable to retrieve pool statistics',
                'stats': None
            }
        
        health_status = 'healthy'
        if stats.is_critical():
            health_status = 'critical'
        elif not stats.is_healthy():
            health_status = 'warning'
        
        return {
            'healthy': stats.is_healthy(),
            'status': health_status,
            'stats': {
                'current_connections': stats.current_connections,
                'max_connections': stats.max_connections,
                'idle_connections': stats.idle_connections,
                'waiting_requests': stats.waiting_requests,
                'utilization': round(stats.utilization, 3),
                'queue_size': stats.queue_size
            }
        }
    
    def should_resize_pool(self) -> bool:
        """Determine if pool should be resized based on current load."""
        stats = self.get_pool_stats()
        if not stats:
            return False
        
        # Resize if utilization is consistently high
        return (stats.utilization > self.warning_threshold and
                stats.waiting_requests > 0)
    
    def resize_pool(self, increment: int = 5) -> bool:
        """Resize the connection pool."""
        try:
            current_stats = self.get_pool_stats()
            if not current_stats:
                return False
            
            new_max = current_stats.max_connections + increment
            max_limit = int(os.environ.get('DB_POOL_MAX', '50'))
            
            if new_max > max_limit:
                log.warning(f"Cannot resize pool: would exceed maximum limit of {max_limit}")
                return False
            
            # Resize the pool
            db.resize_pool(new_max)
            log.info(f"Resized connection pool from {current_stats.max_connections} to {new_max}")
            return True
            
        except Exception as e:
            log.error(f"Failed to resize connection pool: {e}")
            return False
    
    def monitor_connection_pool(self):
        """Monitor connection pool and take action if needed."""
        now = time.time()
        if now - self.last_check_time < self.check_interval:
            return
        
        self.last_check_time = now
        
        try:
            health = self.check_pool_health()
            
            if health['status'] == 'critical':
                log.critical(f"Database connection pool in critical state: {health['stats']}")
                # Try to resize if needed
                if self.should_resize_pool():
                    self.resize_pool()
            
            elif health['status'] == 'warning':
                log.warning(f"Database connection pool in warning state: {health['stats']}")
            
            # Log healthy state periodically
            elif now % 300 < 10:  # Every ~5 minutes
                log.info(f"Database connection pool healthy: {health['stats']}")
                
        except Exception as e:
            log.error(f"Database monitoring error: {e}")

# Global monitor instance
_db_monitor = DatabaseMonitor()

def get_db_monitor() -> DatabaseMonitor:
    """Get the global database monitor instance."""
    return _db_monitor

def get_current_pool_stats() -> Optional[ConnectionPoolStats]:
    """Get current connection pool statistics."""
    return _db_monitor.get_pool_stats()

def check_db_pool_health() -> Dict[str, Any]:
    """Check database pool health."""
    return _db_monitor.check_pool_health()

def monitor_db_connections():
    """Monitor database connections (to be called periodically)."""
    _db_monitor.monitor_connection_pool()

# Database performance monitoring
class QueryPerformanceMonitor:
    """Monitor database query performance."""
    
    def __init__(self):
        self.slow_query_threshold = 1.0  # seconds
        self.query_history = []
        self.max_history = 1000
    
    def record_query(self, query: str, execution_time: float):
        """Record a query execution."""
        if execution_time > self.slow_query_threshold:
            log.warning(f"Slow query ({execution_time:.3f}s): {query[:200]}")
        
        self.query_history.append({
            'query': query,
            'time': execution_time,
            'timestamp': time.time()
        })
        
        # Keep history size manageable
        if len(self.query_history) > self.max_history:
            self.query_history = self.query_history[-self.max_history:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get query performance statistics."""
        if not self.query_history:
            return {'average_time': 0, 'slow_queries': 0, 'total_queries': 0}
        
        total_time = sum(q['time'] for q in self.query_history)
        slow_queries = sum(1 for q in self.query_history if q['time'] > self.slow_query_threshold)
        
        return {
            'average_time': total_time / len(self.query_history),
            'slow_queries': slow_queries,
            'total_queries': len(self.query_history),
            'slow_query_percentage': slow_queries / len(self.query_history) * 100
        }

# Global query performance monitor
_query_monitor = QueryPerformanceMonitor()

def get_query_monitor() -> QueryPerformanceMonitor:
    """Get the global query performance monitor."""
    return _query_monitor

def record_db_query(query: str, execution_time: float):
    """Record a database query execution."""
    _query_monitor.record_query(query, execution_time)

def get_query_performance_stats() -> Dict[str, Any]:
    """Get query performance statistics."""
    return _query_monitor.get_performance_stats()

# Database health check endpoint
def get_database_health() -> Dict[str, Any]:
    """Get comprehensive database health information."""
    pool_health = check_db_pool_health()
    query_stats = get_query_performance_stats()
    
    return {
        'pool_health': pool_health,
        'query_performance': query_stats,
        'overall_healthy': pool_health.get('healthy', False)
    }

# Initialize monitoring system
def init_db_monitoring():
    """Initialize database monitoring system."""
    log.info("Database monitoring system initialized")
    
    # Add periodic monitoring
    import threading
    import time
    
    def monitoring_loop():
        while True:
            try:
                monitor_db_connections()
                time.sleep(60)  # Check every minute
            except Exception as e:
                log.error(f"Database monitoring loop error: {e}")
                time.sleep(10)
    
    # Start monitoring thread
    monitoring_thread = threading.Thread(
        target=monitoring_loop,
        daemon=True,
        name="db-monitoring"
    )
    monitoring_thread.start()

# Auto-initialize
init_db_monitoring()

# Database connection pool management utilities

def get_connection_pool_utilization() -> float:
    """Get current connection pool utilization percentage."""
    stats = get_current_pool_stats()
    if stats:
        return stats.utilization
    return 0.0

def is_pool_under_stress() -> bool:
    """Check if connection pool is under stress."""
    stats = get_current_pool_stats()
    if not stats:
        return False
    return stats.utilization > 0.85 or stats.waiting_requests > 3

def get_pool_stress_level() -> str:
    """Get connection pool stress level."""
    stats = get_current_pool_stats()
    if not stats:
        return "unknown"
    
    if stats.is_critical():
        return "critical"
    elif not stats.is_healthy():
        return "warning"
    else:
        return "normal"