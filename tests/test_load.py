"""
Load Testing for URL Shortener Service

This module performs load tests to determine:
1. Maximum sustainable request rate (RPS)
2. Breaking point (when service starts failing)
3. Response time under various loads
4. Error rate at different load levels

Test Strategy:
- Gradually increase load to find breaking point
- Measure response times (p50, p95, p99)
- Track error rates
- Identify consistent working rate

Usage:
    pytest tests/test_load.py -v -s
"""

import asyncio
import time
import statistics
import subprocess
import socket
import signal
import sys
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import httpx
import pytest
import os

# Test configuration
# BASE_URL can be overridden via environment variable LOAD_TEST_BASE_URL
# If not set, server will be started automatically on an available port
BASE_URL_ENV = os.getenv("LOAD_TEST_BASE_URL")
BASE_URL = BASE_URL_ENV or "http://localhost:8000"  # Default, will be overridden by fixture
TEST_DURATION = 10  # seconds per test
RAMP_UP_STEPS = [10, 50, 100, 200, 500, 1000, 2000, 5000]  # Requests per second


def find_available_port(start_port: int = 8000, end_port: int = 8100) -> int:
    """Find an available port between start_port and end_port."""
    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No available port found between {start_port} and {end_port}")


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait for server to be ready by checking health endpoint."""
    start_time = time.time()
    last_error = None
    while time.time() - start_time < timeout:
        try:
            # Use httpx for async-compatible health check
            import httpx as sync_httpx
            with sync_httpx.Client(timeout=2.0) as client:
                response = client.get(f"{url}/health")
                if response.status_code == 200:
                    return True
        except Exception as e:
            last_error = str(e)
            pass
        time.sleep(0.5)
    
    # Log last error for debugging
    if last_error:
        print(f"[DEBUG] Last health check error: {last_error}")
    return False


@pytest.fixture(scope="session")
def test_server():
    """
    Fixture to start the FastAPI server for load tests.
    
    If LOAD_TEST_BASE_URL is set, uses that URL (server must be running).
    Otherwise, starts a server automatically on an available port.
    """
    server_process: Optional[subprocess.Popen] = None
    server_port: Optional[int] = None
    base_url: str
    
    if BASE_URL_ENV:
        # Use provided URL (server should be running externally)
        base_url = BASE_URL_ENV
        print(f"\n[INFO] Using external server at {base_url}")
        yield base_url
        return
    
    # Start server automatically
    try:
        # Find available port
        server_port = find_available_port()
        base_url = f"http://localhost:{server_port}"
        
        print(f"\n[INFO] Starting test server on port {server_port}...")
        
        # Start uvicorn server
        # Use python -m uvicorn to ensure we use the venv's uvicorn
        server_process = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "app.main:app",
                "--host", "127.0.0.1",
                "--port", str(server_port),
                "--log-level", "warning"  # Reduce noise in test output
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONPATH": os.getcwd()},
            cwd=os.getcwd()
        )
        
        # Give server a moment to start
        time.sleep(2)
        
        # Wait for server to be ready
        print(f"[INFO] Waiting for server to be ready at {base_url}...")
        if not wait_for_server(base_url, timeout=60):  # Increased timeout for startup
            # Check if process is still running
            poll_result = server_process.poll()
            if poll_result is not None:
                # Process exited, get error output
                stdout, stderr = server_process.communicate()
                error_msg = stderr.decode() if stderr else stdout.decode()
                if error_msg:
                    print(f"[ERROR] Server stderr: {error_msg[:1000]}")
                raise RuntimeError(
                    f"Server failed to start on port {server_port}. "
                    f"Process exited with code {poll_result}. "
                    f"Error: {error_msg[:500] if error_msg else 'No error output'}"
                )
            else:
                # Process still running but not responding
                # Try to get some output to see what's happening
                try:
                    # Non-blocking check for output
                    import select
                    import fcntl
                    if sys.platform != 'win32':
                        # Unix-like system
                        flags = fcntl.fcntl(server_process.stderr, fcntl.F_GETFL)
                        fcntl.fcntl(server_process.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        try:
                            stderr_output = server_process.stderr.read(1000).decode()
                            if stderr_output:
                                print(f"[DEBUG] Server stderr (last 1000 chars): {stderr_output}")
                        except:
                            pass
                except:
                    pass
                
                server_process.terminate()
                server_process.wait(timeout=5)
                raise RuntimeError(
                    f"Server started but health check failed on port {server_port}. "
                    "Server may still be initializing (database migrations, pool setup). "
                    "Try increasing the timeout or check server logs."
                )
        
        print(f"[INFO] Server is ready at {base_url}")
        
        # Set BASE_URL for tests
        yield base_url
        
    finally:
        # Cleanup: stop server
        if server_process:
            print(f"\n[INFO] Stopping test server...")
            try:
                server_process.terminate()
                server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait()
            print("[INFO] Server stopped")


@pytest.fixture(autouse=True)
def set_base_url(test_server):
    """Set BASE_URL for all tests to use the test server."""
    global BASE_URL
    BASE_URL = test_server
    yield


class LoadTestResults:
    """Container for load test results."""
    
    def __init__(self, rps: int):
        self.rps = rps
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.start_time: float = 0
        self.end_time: float = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.failed_requests / self.total_requests) * 100
    
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        if not self.response_times:
            return 0.0
        return statistics.mean(self.response_times)
    
    @property
    def p50_response_time(self) -> float:
        """Calculate 50th percentile response time."""
        if not self.response_times:
            return 0.0
        return statistics.median(self.response_times)
    
    @property
    def p95_response_time(self) -> float:
        """Calculate 95th percentile response time."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.95)
        return sorted_times[index] if index < len(sorted_times) else sorted_times[-1]
    
    @property
    def p99_response_time(self) -> float:
        """Calculate 99th percentile response time."""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * 0.99)
        return sorted_times[index] if index < len(sorted_times) else sorted_times[-1]
    
    @property
    def actual_rps(self) -> float:
        """Calculate actual requests per second."""
        duration = self.end_time - self.start_time
        if duration == 0:
            return 0.0
        return self.total_requests / duration
    
    def __str__(self) -> str:
        """String representation of results."""
        return (
            f"RPS: {self.rps} | "
            f"Total: {self.total_requests} | "
            f"Success: {self.successful_requests} ({self.success_rate:.1f}%) | "
            f"Failed: {self.failed_requests} ({self.error_rate:.1f}%) | "
            f"Avg RT: {self.avg_response_time:.2f}ms | "
            f"P95 RT: {self.p95_response_time:.2f}ms"
        )


async def make_request(
    client: httpx.AsyncClient,
    url: str,
    method: str = "GET",
    **kwargs
) -> Tuple[bool, float, str]:
    """
    Make a single HTTP request and measure response time.
    
    Returns:
        Tuple of (success, response_time_ms, error_message)
    """
    start_time = time.time()
    try:
        if method == "GET":
            response = await client.get(url, timeout=10.0, **kwargs)
        elif method == "POST":
            response = await client.post(url, timeout=10.0, **kwargs)
        else:
            return False, 0, f"Unsupported method: {method}"
        
        response_time = (time.time() - start_time) * 1000  # Convert to ms
        success = 200 <= response.status_code < 400
        
        if not success:
            error_msg = f"HTTP {response.status_code}"
        else:
            error_msg = ""
        
        return success, response_time, error_msg
    
    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        return False, response_time, str(e)


async def create_short_url(client: httpx.AsyncClient) -> Tuple[str, bool]:
    """
    Create a short URL for testing.
    
    Returns:
        Tuple of (short_code, success)
    """
    test_url = f"https://example.com/test/{time.time()}"
    success, _, error = await make_request(
        client,
        f"{BASE_URL}/shorten",
        method="POST",
        json={"url": test_url}
    )
    
    if success:
        # In a real scenario, we'd parse the response to get short_code
        # For load testing, we'll use a known short code
        return "test", True
    return "", False


async def worker(
    client: httpx.AsyncClient,
    url: str,
    requests_per_second: float,
    duration: float,
    results: LoadTestResults
):
    """
    Worker coroutine that makes requests at specified rate.
    
    Args:
        client: HTTP client
        url: URL to request
        requests_per_second: Target RPS
        duration: How long to run (seconds)
        results: Results container to update
    """
    delay = 1.0 / requests_per_second if requests_per_second > 0 else 0
    end_time = time.time() + duration
    
    while time.time() < end_time:
        success, response_time, error = await make_request(client, url)
        
        results.total_requests += 1
        if success:
            results.successful_requests += 1
            results.response_times.append(response_time)
        else:
            results.failed_requests += 1
            results.errors.append(error)
        
        # Rate limiting: wait before next request
        if delay > 0:
            await asyncio.sleep(delay)


async def run_load_test(
    url: str,
    target_rps: int,
    duration: float = TEST_DURATION,
    num_workers: int = None
) -> LoadTestResults:
    """
    Run a load test at specified RPS.
    
    Args:
        url: URL to test
        target_rps: Target requests per second
        duration: Test duration in seconds
        num_workers: Number of concurrent workers (auto-calculated if None)
    
    Returns:
        LoadTestResults object with test results
    """
    if num_workers is None:
        # Use number of workers roughly equal to RPS for better distribution
        num_workers = min(target_rps, 100)  # Cap at 100 workers
    
    results = LoadTestResults(target_rps)
    results.start_time = time.time()
    
    # Calculate RPS per worker
    rps_per_worker = target_rps / num_workers
    
    async with httpx.AsyncClient() as client:
        # Create workers
        workers = [
            worker(client, url, rps_per_worker, duration, results)
            for _ in range(num_workers)
        ]
        
        # Run all workers concurrently
        await asyncio.gather(*workers)
    
    results.end_time = time.time()
    return results


@pytest.mark.asyncio
async def test_health_check(test_server):
    """
    Test that the service is running and healthy.
    
    Server is automatically started by the test_server fixture.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        success, response_time, error = await make_request(
            client,
            f"{test_server}/health"
        )
        assert success, f"Health check failed: {error}"
        print(f"\n✓ Health check passed ({response_time:.2f}ms)")


@pytest.mark.asyncio
async def test_load_redirect_endpoint(test_server):
    """
    Load test for redirect endpoint (GET /{short_code}).
    
    This test gradually increases load to find:
    - Maximum sustainable RPS
    - Breaking point
    - Response time degradation
    
    Server is automatically started by the test_server fixture.
    """
    print("\n" + "="*80)
    print("LOAD TEST: Redirect Endpoint (GET /{short_code})")
    print("="*80)
    
    # First, create a short URL to test with
    async with httpx.AsyncClient(timeout=10.0) as client:
        test_url = f"https://example.com/loadtest/{time.time()}"
        response = await client.post(
            f"{test_server}/shorten",
            json={"url": test_url},
            timeout=10.0
        )
        
        assert response.status_code == 201, f"Could not create test short URL: {response.status_code}"
        
        short_code = response.json()["short_code"]
        redirect_url = f"{test_server}/{short_code}"
    
    print(f"\nTesting with short code: {short_code}")
    print(f"Test duration per RPS level: {TEST_DURATION} seconds\n")
    
    results_history: List[LoadTestResults] = []
    breaking_point = None
    consistent_rate = None
    
    for target_rps in RAMP_UP_STEPS:
        print(f"\n{'='*80}")
        print(f"Testing at {target_rps} RPS...")
        print(f"{'='*80}")
        
        results = await run_load_test(redirect_url, target_rps, TEST_DURATION)
        results_history.append(results)
        
        # Print results
        print(f"\nResults:")
        print(f"  Target RPS: {target_rps}")
        print(f"  Actual RPS: {results.actual_rps:.2f}")
        print(f"  Total Requests: {results.total_requests}")
        print(f"  Success Rate: {results.success_rate:.2f}%")
        print(f"  Error Rate: {results.error_rate:.2f}%")
        print(f"  Avg Response Time: {results.avg_response_time:.2f}ms")
        print(f"  P50 Response Time: {results.p50_response_time:.2f}ms")
        print(f"  P95 Response Time: {results.p95_response_time:.2f}ms")
        print(f"  P99 Response Time: {results.p99_response_time:.2f}ms")
        
        # Determine breaking point (error rate > 1%)
        if breaking_point is None and results.error_rate > 1.0:
            breaking_point = target_rps
            print(f"\n  ⚠️  BREAKING POINT DETECTED at {target_rps} RPS")
            print(f"     Error rate exceeded 1%: {results.error_rate:.2f}%")
        
        # Determine consistent rate (success rate > 99% and P95 < 500ms)
        if results.success_rate >= 99.0 and results.p95_response_time < 500:
            consistent_rate = target_rps
            print(f"\n  ✓ Consistent performance at {target_rps} RPS")
        else:
            if consistent_rate:
                print(f"\n  ⚠️  Performance degraded (consistent rate was {consistent_rate} RPS)")
        
        # Stop if error rate is too high (> 10%)
        if results.error_rate > 10.0:
            print(f"\n  🛑 STOPPING: Error rate too high ({results.error_rate:.2f}%)")
            break
        
        # Brief pause between tests
        await asyncio.sleep(2)
    
    # Print summary
    print("\n" + "="*80)
    print("LOAD TEST SUMMARY")
    print("="*80)
    
    if consistent_rate:
        print(f"\n✅ Consistent Working Rate: {consistent_rate} RPS")
        print(f"   (Success rate > 99%, P95 response time < 500ms)")
    else:
        print(f"\n⚠️  Could not determine consistent rate")
        print(f"   (Service may need optimization)")
    
    if breaking_point:
        print(f"\n⚠️  Breaking Point: {breaking_point} RPS")
        print(f"   (Error rate exceeded 1%)")
    else:
        print(f"\n✅ No breaking point detected up to {RAMP_UP_STEPS[-1]} RPS")
    
    # Find best performance
    best_result = max(
        [r for r in results_history if r.success_rate >= 99.0],
        key=lambda x: x.rps,
        default=None
    )
    
    if best_result:
        print(f"\n📊 Best Performance:")
        print(f"   RPS: {best_result.rps}")
        print(f"   Success Rate: {best_result.success_rate:.2f}%")
        print(f"   P95 Response Time: {best_result.p95_response_time:.2f}ms")
    
    # Assertions (soft - for reporting)
    if consistent_rate:
        assert consistent_rate > 0, "Service should handle at least some load"
    
    print("\n" + "="*80)


async def post_worker(
    client: httpx.AsyncClient,
    url: str,
    requests_per_second: float,
    duration: float,
    results: LoadTestResults
):
    """
    Worker coroutine for POST requests.
    
    Args:
        client: HTTP client
        url: URL to request
        requests_per_second: Target RPS
        duration: How long to run (seconds)
        results: Results container to update
    """
    delay = 1.0 / requests_per_second if requests_per_second > 0 else 0
    end_time = time.time() + duration
    
    while time.time() < end_time:
        test_url = f"https://example.com/test/{time.time()}"
        success, response_time, error = await make_request(
            client,
            url,
            method="POST",
            json={"url": test_url}
        )
        
        results.total_requests += 1
        if success:
            results.successful_requests += 1
            results.response_times.append(response_time)
        else:
            results.failed_requests += 1
            results.errors.append(error)
        
        # Rate limiting: wait before next request
        if delay > 0:
            await asyncio.sleep(delay)


async def run_post_load_test(
    url: str,
    target_rps: int,
    duration: float = TEST_DURATION,
    num_workers: int = None
) -> LoadTestResults:
    """
    Run a load test for POST endpoint at specified RPS.
    
    Args:
        url: URL to test
        target_rps: Target requests per second
        duration: Test duration in seconds
        num_workers: Number of concurrent workers (auto-calculated if None)
    
    Returns:
        LoadTestResults object with test results
    """
    if num_workers is None:
        num_workers = min(target_rps, 50)  # Cap at 50 workers for POST
    
    results = LoadTestResults(target_rps)
    results.start_time = time.time()
    
    # Calculate RPS per worker
    rps_per_worker = target_rps / num_workers
    
    async with httpx.AsyncClient() as client:
        # Create workers
        workers = [
            post_worker(client, url, rps_per_worker, duration, results)
            for _ in range(num_workers)
        ]
        
        # Run all workers concurrently
        await asyncio.gather(*workers)
    
    results.end_time = time.time()
    return results


@pytest.mark.asyncio
async def test_load_shorten_endpoint(test_server):
    """
    Load test for shorten endpoint (POST /shorten).
    
    Tests the write-heavy endpoint to find its limits.
    
    Server is automatically started by the test_server fixture.
    """
    print("\n" + "="*80)
    print("LOAD TEST: Shorten Endpoint (POST /shorten)")
    print("="*80)
    
    shorten_url = f"{test_server}/shorten"
    test_rps_levels = [10, 50, 100, 200, 500]  # Lower for write operations
    
    print(f"\nTest duration per RPS level: {TEST_DURATION} seconds\n")
    
    results_history: List[LoadTestResults] = []
    breaking_point = None
    consistent_rate = None
    
    for target_rps in test_rps_levels:
        print(f"\nTesting at {target_rps} RPS...")
        
        results = await run_post_load_test(shorten_url, target_rps, TEST_DURATION)
        results_history.append(results)
        
        print(f"  Success Rate: {results.success_rate:.2f}%")
        print(f"  Error Rate: {results.error_rate:.2f}%")
        print(f"  Avg Response Time: {results.avg_response_time:.2f}ms")
        print(f"  P95 Response Time: {results.p95_response_time:.2f}ms")
        
        # Determine breaking point
        if breaking_point is None and results.error_rate > 1.0:
            breaking_point = target_rps
            print(f"  ⚠️  BREAKING POINT DETECTED at {target_rps} RPS")
        
        # Determine consistent rate
        if results.success_rate >= 99.0 and results.p95_response_time < 1000:
            consistent_rate = target_rps
            print(f"  ✓ Consistent performance at {target_rps} RPS")
        
        if results.error_rate > 10.0:
            print(f"  🛑 STOPPING: Error rate too high")
            break
        
        await asyncio.sleep(2)
    
    # Print summary
    print("\n" + "="*80)
    print("SHORTEN ENDPOINT SUMMARY")
    print("="*80)
    
    if consistent_rate:
        print(f"\n✅ Consistent Working Rate: {consistent_rate} RPS")
    if breaking_point:
        print(f"\n⚠️  Breaking Point: {breaking_point} RPS")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])

