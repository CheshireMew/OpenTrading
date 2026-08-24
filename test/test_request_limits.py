from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.request_limits import RequestBodyLimitMiddleware


def build_test_client(limit: int = 10) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        route_limits={("POST", "/import"): limit},
    )

    @app.post("/import")
    async def import_body(request: Request):
        return {"size": len(await request.body())}

    return TestClient(app)


def build_patch_test_client(limit: int = 10) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        route_limits={("PATCH", "/collection"): limit},
    )

    @app.patch("/collection")
    async def patch_collection(request: Request):
        return {"size": len(await request.body())}

    return TestClient(app)


def build_template_test_client(limit: int = 10) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        route_limits={("PUT", "/portfolios/{portfolio_id}/simulation"): limit},
    )

    @app.put("/portfolios/{portfolio_id}/simulation")
    async def put_simulation(portfolio_id: str, request: Request):
        return {"portfolioId": portfolio_id, "size": len(await request.body())}

    return TestClient(app)


def test_request_body_limit_allows_bounded_body():
    response = build_test_client().post("/import", content=b"0123456789")

    assert response.status_code == 200
    assert response.json() == {"size": 10}


def test_request_body_limit_rejects_oversized_body():
    response = build_test_client().post("/import", content=b"01234567890")

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body exceeds the 10 byte limit"}


def test_request_body_limit_applies_to_patch_routes():
    response = build_patch_test_client().patch("/collection", content=b"01234567890")

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body exceeds the 10 byte limit"}


def test_request_body_limit_matches_parameterized_routes():
    response = build_template_test_client().put(
        "/portfolios/core/simulation",
        content=b"01234567890",
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body exceeds the 10 byte limit"}
