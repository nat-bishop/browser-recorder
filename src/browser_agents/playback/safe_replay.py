"""Safe replay mode for blocking state-changing requests.

Intercepts network requests during playback and blocks/mocks
state-changing HTTP methods (POST, PUT, PATCH, DELETE) to
prevent unintended side effects.

No network recording needed - intercepts during playback only.
"""

from enum import Enum

from playwright.async_api import Page, Route


class SafeReplayMode(str, Enum):
    """Network interception modes for safe replay."""

    LIVE = "live"  # No interception, real requests
    WARN = "warn"  # Log state-changing requests but allow
    BLOCK = "block"  # Block state-changing requests
    MOCK = "mock"  # Mock state-changing requests with fake success


class SafeReplayController:
    """Controls network during replay using HTTP method heuristics.

    No network recording needed - intercepts during playback based
    on HTTP method:
    - GET, HEAD, OPTIONS: Always allowed (read-only)
    - POST, PUT, PATCH, DELETE: Controlled by mode

    Usage:
        controller = SafeReplayController(page, SafeReplayMode.BLOCK)
        await controller.setup()
        # ... run replay ...
        report = controller.get_report()
    """

    def __init__(self, page: Page, mode: SafeReplayMode) -> None:
        """Initialize the controller.

        Args:
            page: Playwright page to intercept.
            mode: Interception mode.
        """
        self.page = page
        self.mode = mode
        self.blocked_requests: list[dict] = []
        self.allowed_requests: list[dict] = []
        self._is_setup = False

    async def setup(self) -> None:
        """Configure network interception based on mode."""
        if self.mode == SafeReplayMode.LIVE:
            # No interception needed
            return

        if self._is_setup:
            return

        await self.page.route("**/*", self._handle_route)
        self._is_setup = True

    async def teardown(self) -> None:
        """Remove network interception."""
        if not self._is_setup:
            return

        await self.page.unroute("**/*", self._handle_route)
        self._is_setup = False

    async def _handle_route(self, route: Route) -> None:
        """Handle intercepted requests."""
        request = route.request
        method = request.method.upper()
        url = request.url

        # Safe methods - always allow
        if method in ("GET", "HEAD", "OPTIONS"):
            self.allowed_requests.append({"method": method, "url": url})
            await route.continue_()
            return

        # State-changing methods (POST, PUT, PATCH, DELETE)
        request_info = {
            "method": method,
            "url": url,
            "post_data": request.post_data[:500] if request.post_data else None,
        }
        self.blocked_requests.append(request_info)

        if self.mode == SafeReplayMode.WARN:
            print(f"[WARN] State-changing request: {method} {url}")
            await route.continue_()

        elif self.mode == SafeReplayMode.BLOCK:
            print(f"[BLOCKED] {method} {url}")
            await route.abort("blockedbyclient")

        elif self.mode == SafeReplayMode.MOCK:
            print(f"[MOCKED] {method} {url}")
            # Return fake success response
            await route.fulfill(
                status=200,
                content_type="application/json",
                body='{"success": true, "mocked": true}',
            )

    def get_report(self) -> dict:
        """Generate report of intercepted requests.

        Returns:
            Dict with mode, counts, and blocked request details.
        """
        return {
            "mode": self.mode.value,
            "allowed_count": len(self.allowed_requests),
            "blocked_count": len(self.blocked_requests),
            "blocked_requests": self.blocked_requests,
        }

    def reset_stats(self) -> None:
        """Reset request statistics."""
        self.blocked_requests = []
        self.allowed_requests = []
