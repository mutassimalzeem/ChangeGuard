"""Test health check endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test basic health check endpoint."""
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_check_db(self, client: AsyncClient):
        """Test database health check endpoint."""
        response = await client.get("/api/v1/health/db")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "unhealthy")
        assert "database" in data

    @pytest.mark.asyncio
    async def test_readiness_check(self, client: AsyncClient):
        """Test readiness check endpoint."""
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ready", "not_ready")
        assert "checks" in data
        assert "database" in data["checks"]