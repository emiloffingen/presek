"""
queue_monitoring.py - Celery task queue depth monitoring and management

Provides:
- Real-time queue depth monitoring
- Alerting for queue backlogs
- Automatic scaling recommendations
- Historical queue metrics
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from core.celery_app import celery_app
from core.logging_config import get_logger

log = get_logger("presek.queue_monitoring")


@dataclass
class QueueStats:
    """Statistics for a single Celery queue."""

    name: str
    active: int
    scheduled: int
    reserved: int
    total: int

    def is_backlogged(self, threshold: int = 50) -> bool:
        """Check if queue is backlogged."""
        return self.total > threshold

    def is_critical(self, threshold: int = 200) -> bool:
        """Check if queue is in critical state."""
        return self.total > threshold


class QueueMonitor:
    """Celery queue monitor."""

    def __init__(self):
        self.last_check_time = 0
        self.check_interval = 30  # seconds
        self.warning_threshold = 50  # tasks
        self.critical_threshold = 200  # tasks
        self.queue_history = []
        self.max_history = 100

    def get_queue_stats(self) -> List[QueueStats]:
        """Get current queue statistics."""
        try:
            inspector = celery_app.control.inspect()

            # Get active tasks
            active_tasks = inspector.active() or {}

            # Get scheduled tasks
            scheduled_tasks = inspector.scheduled() or {}

            # Get reserved tasks
            reserved_tasks = inspector.reserved() or {}

            # Get registered queues
            queues = inspector.active_queues() or {}

            # Aggregate stats by queue
            queue_stats = {}

            for worker, worker_queues in queues.items():
                for queue_info in worker_queues:
                    queue_name = queue_info.get("name", "unknown")

                    if queue_name not in queue_stats:
                        queue_stats[queue_name] = {
                            "active": 0,
                            "scheduled": 0,
                            "reserved": 0,
                        }

            # Count active tasks by queue
            for worker, tasks in active_tasks.items():
                for task in tasks:
                    queue_name = task.get("delivery_info", {}).get(
                        "routing_key", "unknown"
                    )
                    if queue_name in queue_stats:
                        queue_stats[queue_name]["active"] += 1

            # Count scheduled tasks by queue
            for worker, tasks in scheduled_tasks.items():
                for task in tasks:
                    queue_name = (
                        task.get("request", {})
                        .get("delivery_info", {})
                        .get("routing_key", "unknown")
                    )
                    if queue_name in queue_stats:
                        queue_stats[queue_name]["scheduled"] += 1

            # Count reserved tasks by queue
            for worker, tasks in reserved_tasks.items():
                for task in tasks:
                    queue_name = task.get("delivery_info", {}).get(
                        "routing_key", "unknown"
                    )
                    if queue_name in queue_stats:
                        queue_stats[queue_name]["reserved"] += 1

            # Convert to QueueStats objects
            result = []
            for queue_name, stats in queue_stats.items():
                result.append(
                    QueueStats(
                        name=queue_name,
                        active=stats["active"],
                        scheduled=stats["scheduled"],
                        reserved=stats["reserved"],
                        total=stats["active"] + stats["scheduled"] + stats["reserved"],
                    )
                )

            return result

        except Exception as e:
            log.error(f"Failed to get queue stats: {e}")
            return []

    def get_total_queue_depth(self) -> int:
        """Get total number of tasks across all queues."""
        stats = self.get_queue_stats()
        return sum(queue.total for queue in stats)

    def check_queue_health(self) -> Dict[str, Any]:
        """Check overall queue health."""
        stats = self.get_queue_stats()
        total_depth = self.get_total_queue_depth()

        critical_queues = [
            q.name for q in stats if q.is_critical(self.critical_threshold)
        ]
        backlogged_queues = [
            q.name for q in stats if q.is_backlogged(self.warning_threshold)
        ]

        health_status = "healthy"
        if critical_queues:
            health_status = "critical"
        elif backlogged_queues:
            health_status = "warning"

        return {
            "status": health_status,
            "total_depth": total_depth,
            "queues": [
                {
                    "name": q.name,
                    "active": q.active,
                    "scheduled": q.scheduled,
                    "reserved": q.reserved,
                    "total": q.total,
                    "is_backlogged": q.is_backlogged(self.warning_threshold),
                    "is_critical": q.is_critical(self.critical_threshold),
                }
                for q in stats
            ],
            "critical_queues": critical_queues,
            "backlogged_queues": backlogged_queues,
            "healthy": health_status == "healthy",
        }

    def should_scale_workers(self) -> bool:
        """Determine if workers should be scaled based on queue depth."""
        health = self.check_queue_health()
        return health["status"] in ["warning", "critical"]

    def get_scaling_recommendation(self) -> Dict[str, Any]:
        """Get worker scaling recommendation."""
        health = self.check_queue_health()

        if health["status"] == "healthy":
            return {"action": "none", "reason": "Queues are healthy"}

        # Simple scaling recommendation
        current_workers = self._get_worker_count()
        recommended_workers = current_workers

        if health["status"] == "critical":
            # Add 2 workers for critical state
            recommended_workers = current_workers + 2
        elif health["status"] == "warning":
            # Add 1 worker for warning state
            recommended_workers = current_workers + 1

        return {
            "action": "scale_up",
            "current_workers": current_workers,
            "recommended_workers": recommended_workers,
            "reason": f"Queue depth {health['total_depth']} exceeds threshold",
        }

    def _get_worker_count(self) -> int:
        """Get current number of active workers."""
        try:
            inspector = celery_app.control.inspect()
            stats = inspector.stats() or {}
            return len(stats)
        except Exception as e:
            log.warning(f"Failed to get worker count: {e}")
            return 1  # Default to 1 worker

    def monitor_queues(self):
        """Monitor queues and log status."""
        now = time.time()
        if now - self.last_check_time < self.check_interval:
            return

        self.last_check_time = now

        try:
            health = self.check_queue_health()

            # Record in history
            self.queue_history.append(
                {
                    "timestamp": now,
                    "status": health["status"],
                    "total_depth": health["total_depth"],
                }
            )

            # Keep history size manageable
            if len(self.queue_history) > self.max_history:
                self.queue_history = self.queue_history[-self.max_history :]

            # Log based on status
            if health["status"] == "critical":
                log.critical(
                    f"Celery queues in critical state: {health['total_depth']} tasks queued"
                )
            elif health["status"] == "warning":
                log.warning(
                    f"Celery queues backlogged: {health['total_depth']} tasks queued"
                )
            elif now % 300 < 10:  # Every ~5 minutes
                log.info(f"Celery queues healthy: {health['total_depth']} tasks queued")

        except Exception as e:
            log.error(f"Queue monitoring error: {e}")


# Global queue monitor instance
_queue_monitor = QueueMonitor()


def get_queue_monitor() -> QueueMonitor:
    """Get the global queue monitor instance."""
    return _queue_monitor


def get_current_queue_stats() -> List[QueueStats]:
    """Get current queue statistics."""
    return _queue_monitor.get_queue_stats()


def check_queue_health() -> Dict[str, Any]:
    """Check queue health."""
    return _queue_monitor.check_queue_health()


def get_total_queue_depth() -> int:
    """Get total queue depth."""
    return _queue_monitor.get_total_queue_depth()


def get_scaling_recommendation() -> Dict[str, Any]:
    """Get worker scaling recommendation."""
    return _queue_monitor.get_scaling_recommendation()


def monitor_queues():
    """Monitor queues (to be called periodically)."""
    _queue_monitor.monitor_queues()


# Queue performance monitoring
class QueuePerformanceMonitor:
    """Monitor queue performance metrics."""

    def __init__(self):
        self.task_history = []
        self.max_history = 1000
        self.slow_task_threshold = 5.0  # seconds

    def record_task_execution(self, task_name: str, queue: str, execution_time: float):
        """Record a task execution."""
        if execution_time > self.slow_task_threshold:
            log.warning(
                f"Slow task ({execution_time:.3f}s): {task_name} on queue {queue}"
            )

        self.task_history.append(
            {
                "task_name": task_name,
                "queue": queue,
                "execution_time": execution_time,
                "timestamp": time.time(),
            }
        )

        # Keep history size manageable
        if len(self.task_history) > self.max_history:
            self.task_history = self.task_history[-self.max_history :]

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        if not self.task_history:
            return {
                "average_time": 0,
                "slow_tasks": 0,
                "total_tasks": 0,
                "slow_task_percentage": 0,
            }

        total_time = sum(t["execution_time"] for t in self.task_history)
        slow_tasks = sum(
            1
            for t in self.task_history
            if t["execution_time"] > self.slow_task_threshold
        )

        return {
            "average_time": total_time / len(self.task_history),
            "slow_tasks": slow_tasks,
            "total_tasks": len(self.task_history),
            "slow_task_percentage": slow_tasks / len(self.task_history) * 100,
        }


# Global queue performance monitor
_queue_perf_monitor = QueuePerformanceMonitor()


def get_queue_perf_monitor() -> QueuePerformanceMonitor:
    """Get the global queue performance monitor."""
    return _queue_perf_monitor


def record_task_execution(task_name: str, queue: str, execution_time: float):
    """Record a task execution."""
    _queue_perf_monitor.record_task_execution(task_name, queue, execution_time)


def get_queue_performance_stats() -> Dict[str, Any]:
    """Get queue performance statistics."""
    return _queue_perf_monitor.get_performance_stats()


# Queue health endpoint
def get_queue_health() -> Dict[str, Any]:
    """Get comprehensive queue health information."""
    queue_health = check_queue_health()
    perf_stats = get_queue_performance_stats()

    return {
        "queue_health": queue_health,
        "performance": perf_stats,
        "overall_healthy": queue_health.get("healthy", False),
    }


# Task queue monitoring for specific queues
def get_queue_depth_by_name(queue_name: str) -> int:
    """Get depth of a specific queue."""
    stats = get_current_queue_stats()
    for queue in stats:
        if queue.name == queue_name:
            return queue.total
    return 0


def is_queue_backlogged(queue_name: str, threshold: int = 50) -> bool:
    """Check if a specific queue is backlogged."""
    depth = get_queue_depth_by_name(queue_name)
    return depth > threshold


# Initialize queue monitoring system
def init_queue_monitoring():
    """Initialize queue monitoring system."""
    log.info("Queue monitoring system initialized")

    # Add periodic monitoring
    import threading

    def monitoring_loop():
        while True:
            try:
                monitor_queues()
                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                log.error(f"Queue monitoring loop error: {e}")
                time.sleep(10)

    # Start monitoring thread
    monitoring_thread = threading.Thread(
        target=monitoring_loop, daemon=True, name="queue-monitoring"
    )
    monitoring_thread.start()


# Auto-initialize
init_queue_monitoring()


# Queue monitoring utilities for admin interface
def get_queue_monitoring_summary() -> Dict[str, Any]:
    """Get a summary of queue monitoring status."""
    health = check_queue_health()

    return {
        "status": health["status"],
        "total_depth": health["total_depth"],
        "critical_queues": health["critical_queues"],
        "backlogged_queues": health["backlogged_queues"],
        "worker_count": _queue_monitor._get_worker_count(),
        "scaling_recommendation": get_scaling_recommendation(),
    }


# Alerting system for queue monitoring
def check_queue_alerts() -> List[Dict[str, Any]]:
    """Check for queue alerts that need attention."""
    alerts = []
    health = check_queue_health()

    if health["status"] == "critical":
        alerts.append(
            {
                "level": "critical",
                "message": f"Celery queues in critical state: {health['total_depth']} tasks queued",
                "queues": health["critical_queues"],
                "timestamp": time.time(),
            }
        )

    if health["status"] == "warning":
        alerts.append(
            {
                "level": "warning",
                "message": f"Celery queues backlogged: {health['total_depth']} tasks queued",
                "queues": health["backlogged_queues"],
                "timestamp": time.time(),
            }
        )

    return alerts
