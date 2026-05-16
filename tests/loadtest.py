"""
Load testing scenarios for Presek API using Locust.

This file defines various user behaviors and test scenarios for
performance testing the Presek application.
"""

from locust import HttpUser, task, between, events
import random


class PresekUser(HttpUser):
    """Base user class with common behavior."""
    
    wait_time = between(1, 5)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Generate a random user ID for this user
        self.user_id = f"user_{random.randint(1, 10000)}"


class NewsConsumer(PresekUser):
    """User that primarily consumes news content."""
    
    @task(3)
    def get_recent_news(self):
        """Get recent news articles."""
        with self.client.get("/api/news/recent", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get recent news: {response.status_code}")
            else:
                response.success()

    @task(2)
    def get_news_by_category(self):
        """Get news by category."""
        categories = ["politics", "sports", "technology", "business"]
        category = random.choice(categories)
        
        with self.client.get(f"/api/news/category/{category}", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get news by category: {response.status_code}")
            else:
                response.success()

    @task(1)
    def search_news(self):
        """Search for news articles."""
        search_terms = ["elections", "economy", "sports", "technology", "health"]
        query = random.choice(search_terms)
        
        with self.client.get(f"/api/news/search?q={query}", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to search news: {response.status_code}")
            else:
                response.success()


class ClusterExplorer(PresekUser):
    """User that explores news clusters."""
    
    @task(2)
    def get_clusters(self):
        """Get news clusters."""
        with self.client.get("/api/news/clusters", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get clusters: {response.status_code}")
            else:
                response.success()

    @task(1)
    def get_cluster_details(self):
        """Get details for a specific cluster."""
        # In a real test, we'd use actual cluster IDs from the API
        cluster_id = f"cluster_{random.randint(1, 100)}"
        
        with self.client.get(f"/api/news/cluster/{cluster_id}", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get cluster details: {response.status_code}")
            else:
                response.success()


class IntelligenceUser(PresekUser):
    """User that uses intelligence features."""
    
    @task(1)
    def get_trending_topics(self):
        """Get trending topics."""
        with self.client.get("/api/intelligence/trending", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get trending topics: {response.status_code}")
            else:
                response.success()

    @task(1)
    def get_ai_analysis(self):
        """Get AI analysis for a topic."""
        topics = ["politics", "economy", "sports", "technology"]
        topic = random.choice(topics)
        
        with self.client.get(f"/api/intelligence/analysis/{topic}", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get AI analysis: {response.status_code}")
            else:
                response.success()


class AdminUser(HttpUser):
    """Admin user that accesses admin endpoints."""
    
    wait_time = between(2, 10)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # In a real test, we'd use a valid admin token
        # For load testing, we'll use a dummy token
        self.admin_token = "dummy_admin_token_for_load_testing"
        self.headers["Authorization"] = f"Bearer {self.admin_token}"

    @task(1)
    def get_admin_dashboard(self):
        """Get admin dashboard."""
        with self.client.get("/admin/dashboard", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get admin dashboard: {response.status_code}")
            else:
                response.success()


class MixedBehaviorUser(PresekUser):
    """User with mixed behavior patterns."""
    
    @task(4)
    def browse_news(self):
        """Browse recent news."""
        with self.client.get("/api/news/recent", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to browse news: {response.status_code}")
            else:
                response.success()

    @task(2)
    def search_and_explore(self):
        """Search for news and explore clusters."""
        # Search
        search_terms = ["elections", "economy", "sports", "technology"]
        query = random.choice(search_terms)
        
        with self.client.get(f"/api/news/search?q={query}", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to search: {response.status_code}")
            else:
                response.success()
        
        # Explore clusters
        with self.client.get("/api/news/clusters", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get clusters: {response.status_code}")
            else:
                response.success()

    @task(1)
    def get_intelligence(self):
        """Get intelligence analysis."""
        with self.client.get("/api/intelligence/trending", headers=self.headers, catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Failed to get intelligence: {response.status_code}")
            else:
                response.success()


def on_test_start(environment):
    """Callback when test starts."""
    print(f"Starting load test with {environment.runner.user_count} users...")


def on_test_stop(environment):
    """Callback when test stops."""
    print(f"Load test completed. Total requests: {environment.runner.stats.total.num_requests}")
    print(f"Failure ratio: {environment.runner.stats.total.fail_ratio:.2%}")


# Event hooks
events.test_start.add_listener(on_test_start)
events.test_stop.add_listener(on_test_stop)
