import asyncio
import os
import sys
import time

# Ensure project root in path
sys.path.append(os.getcwd())

# Ensure we configure the read replica env vars for the benchmark
os.environ["USE_READ_REPLICA"] = "True"
if "DATABASE_READ_REPLICA_URL" not in os.environ:
    # Use the primary connection as the replica connection if not set
    os.environ["DATABASE_READ_REPLICA_URL"] = os.environ.get(
        "DATABASE_URL", "postgresql://presek:CHANGE_ME@localhost/presek"
    )

from core.database import async_db


async def simulate_read_request(req_id):
    """Simulate a read request (SELECT query) which should route to replica."""
    start = time.time()
    # Trigger a read query. Auto-detection should route this to the replica!
    await async_db.execute("SELECT count(*) FROM articles LIMIT 1")
    duration = time.time() - start
    return "read", duration


async def simulate_write_request(req_id):
    """Simulate a write request (INSERT or UPDATE query) which should route to primary."""
    start = time.time()
    # Trigger a write query. Auto-detection should NOT route this to the replica!
    await async_db.execute(
        "INSERT INTO failed_tasks (task_name, error_message) VALUES (%s, %s)",
        (f"bench-{req_id}", "Benchmark test write"),
        fetch=False,
    )
    duration = time.time() - start
    return "write", duration


async def run_benchmark(concurrency=20, total_requests=100):
    print("Starting High-Load Replica Routing Simulation Benchmark...")
    print(f"Parameters: Concurrency={concurrency}, Total Requests={total_requests}")

    # 1. Warm up connection pools
    await async_db._ensure_pool()

    if getattr(async_db, "_read_pool", None) is None:
        print("❌ Error: Async read replica pool is not initialized! Check configurations.")
        return

    print("✅ Async read replica pool initialized successfully.")

    # Counters for query routing verification
    replica_routed = 0
    primary_routed = 0

    # Spy/Patch pool connection methods to count routing hits
    orig_read_connection = async_db._read_pool.connection
    orig_primary_connection = async_db._pool.connection

    # Define spied context managers
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def spied_read_connection():
        nonlocal replica_routed
        replica_routed += 1
        async with orig_read_connection() as conn:
            yield conn

    @asynccontextmanager
    async def spied_primary_connection():
        nonlocal primary_routed
        primary_routed += 1
        async with orig_primary_connection() as conn:
            yield conn

    async_db._read_pool.connection = spied_read_connection
    async_db._pool.connection = spied_primary_connection

    # 2. Build list of concurrent requests (80% reads, 20% writes)
    tasks = []
    for i in range(total_requests):
        if i % 5 == 0:
            tasks.append(simulate_write_request(i))
        else:
            tasks.append(simulate_read_request(i))

    # Run requests concurrently in batches to respect concurrency limit
    start_time = time.time()
    sem = asyncio.Semaphore(concurrency)

    async def worker(task):
        async with sem:
            return await task

    results = await asyncio.gather(*(worker(t) for t in tasks))
    total_duration = time.time() - start_time

    # 3. Print Benchmark Results
    read_times = [r[1] for r in results if r[0] == "read"]
    write_times = [r[1] for r in results if r[0] == "write"]

    qps = total_requests / total_duration

    print("\n================ BENCHMARK RESULTS ================")
    print(f"Total Completed Requests: {total_requests}")
    print(f"Benchmark Concurrency: {concurrency}")
    print(f"Total Time Taken: {total_duration:.4f} seconds")
    print(f"Throughput (QPS): {qps:.2f} queries/sec")
    print(f"Average Read Query Latency: {sum(read_times) / len(read_times):.4f}s")
    print(f"Average Write Query Latency: {sum(write_times) / len(write_times):.4f}s")
    print("---------------------------------------------------")
    print(f"Total Queries routed to Read Replica pool: {replica_routed} (Expected: {len(read_times)})")
    print(f"Total Queries routed to Primary Write pool: {primary_routed} (Expected: {len(write_times)})")
    print("===================================================\n")

    # Restore original connections to stop spying
    async_db._read_pool.connection = orig_read_connection
    async_db._pool.connection = orig_primary_connection

    assert replica_routed == len(read_times), f"Expected {len(read_times)} replica routes, got {replica_routed}"
    assert primary_routed == len(write_times), f"Expected {len(write_times)} primary routes, got {primary_routed}"

    # Cleanup benchmark write entries
    print("Cleaning up benchmark entries...")
    await async_db.execute("DELETE FROM failed_tasks WHERE task_name LIKE 'bench-%'", fetch=False)

    print("🎉 Load simulation and query routing validation successful!")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
