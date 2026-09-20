from __future__ import annotations

from lgh.schema.frontier import ReviewRequest, ReviewResponse


class StubReviewer:
    """Deterministic reviewer for tests. Unavailable by default."""

    def __init__(self, response: ReviewResponse | None = None, unavailable: bool = True) -> None:
        self.response = response
        self.unavailable = unavailable
        self.calls: list[ReviewRequest] = []

    def review(self, request: ReviewRequest) -> ReviewResponse:
        self.calls.append(request)
        if self.unavailable or self.response is None:
            raise FrontierUnavailable("stub reviewer unavailable")
        return self.response


class FrontierUnavailable(Exception):
    pass
