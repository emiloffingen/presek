"""
Locust load test for Presek API

Run with: locust -f tests/loadtest.py --headless -u 100 -r 10 --run-time 1m
"""

from locust import HttpUser, task, between
import random


class PresekUser(HttpUser):
    """Simulates a user browsing and interacting with Presek API."""

    wait_time = between(0.5, 2.5)

    def on_start(self):
        """Called when a user starts before any tasks are scheduled."""
        self.host = self.host or "http://localhost:8000"

    @task(3)
    def health_check(self):
        """Check API health - lightweight endpoint."""
        self.client.get("/api/health")

    @task(5)
    def get_feed(self):
        """Fetch the main news feed."""
        self.client.get("/api/feed?limit=20")

    @task(4)
    def search_articles(self):
        """Search for articles with various queries."""
        queries = [
            "Srbija",
            "Скопје",
            "Политика",
            "Економија",
            "Спорт",
            "Култура",
            "Здравство",
            "Образование",
        ]
        query = random.choice(queries)
        self.client.get(f"/api/search?q={query}&limit=10")

    @task(3)
    def get_clusters(self):
        """Fetch clusters of related articles."""
        self.client.get("/api/clusters?limit=10")

    @task(2)
    def get_article(self):
        """Fetch a specific article by ID."""
        # In a real test, we'd use actual article IDs from the feed
        article_ids = list(range(1, 100))
        article_id = random.choice(article_ids)
        self.client.get(f"/api/news/{article_id}")

    @task(1)
    def get_stats(self):
        """Fetch statistics."""
        self.client.get("/api/stats/sources")

    @task(1)
    def get_version(self):
        """Get version info."""
        self.client.get("/api/version")


class HeavyUser(HttpUser):
    """Simulates a power user with more intensive operations."""

    wait_time = between(1, 3)

    @task(2)
    def intelligence_endpoints(self):
        """Test AI intelligence endpoints."""
        self.client.get("/api/intelligence/synthesis?cluster_id=1")

    @task(1)
    def profile_endpoints(self):
        """Test profile-related endpoints."""
        self.client.get("/api/profile/preferences")


class AdminUser(HttpUser):
    """Simulates admin operations."""

    wait_time = between(2, 5)

    @task(1)
    def admin_stats(self):
        """Admin statistics."""
        self.client.get("/api/admin/stats")
