"""
Minimum test suite covering:
  1. Agent creation
  2. Workflow execution (mocked LLM)
  3. Message delivery (persisted to DB)
"""

import asyncio
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from main import app
from models.database import init_db, engine, Base


# ── Fixtures ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    """Initialize in-memory-compatible test DB (uses the configured DB)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── Test 1: Agent CRUD ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_agent(client):
    resp = await client.post("/api/agents/", json={
        "name": "Test Agent",
        "role": "Researcher",
        "system_prompt": "You are a helpful researcher.",
        "model": "gemini-2.5-flash",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Agent"
    assert data["role"] == "Researcher"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_agents(client):
    resp = await client.get("/api/agents/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_agent_not_found(client):
    resp = await client.get(f"/api/agents/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_agent(client):
    # Create first
    create = await client.post("/api/agents/", json={
        "name": "UpdateMe", "role": "Writer",
        "system_prompt": "Write things.", "model": "gemini-2.5-flash",
    })
    agent_id = create.json()["id"]

    resp = await client.put(f"/api/agents/{agent_id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_agent(client):
    create = await client.post("/api/agents/", json={
        "name": "DeleteMe", "role": "Temp",
        "system_prompt": "Temporary.", "model": "gemini-2.5-flash",
    })
    agent_id = create.json()["id"]

    del_resp = await client.delete(f"/api/agents/{agent_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/agents/{agent_id}")
    assert get_resp.status_code == 404


# ── Test 2: Workflow Execution ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_run_no_nodes(client):
    # Create a workflow with no nodes
    wf_resp = await client.post("/api/workflows/", json={
        "name": "Empty WF",
        "definition": {"nodes": [], "edges": []},
    })
    wf_id = wf_resp.json()["id"]

    run_resp = await client.post(f"/api/workflows/{wf_id}/run", json={"input_message": "hello"})
    assert run_resp.status_code == 400
    assert "no nodes" in run_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_workflow_execution_mocked(client):
    """Test full workflow execution with mocked LLM."""
    # 1. Create agent
    agent = (await client.post("/api/agents/", json={
        "name": "MockAgent", "role": "Tester",
        "system_prompt": "Reply with 'MOCK_OK'.", "model": "gemini-2.5-flash",
    })).json()

    # 2. Create workflow
    wf = (await client.post("/api/workflows/", json={
        "name": "Test WF",
        "definition": {
            "nodes": [{"id": "n1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"agent_id": agent["id"], "label": "MockAgent"}}],
            "edges": [],
        },
    })).json()

    # 3. Mock the LLM call
    mock_response = MagicMock()
    mock_response.content = "MOCK_OK"
    mock_response.tool_calls = []
    mock_response.usage_metadata = {"total_tokens": 10}

    with patch("runtime.executor.ChatGoogleGenerativeAI") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)

        run_resp = await client.post(f"/api/workflows/{wf['id']}/run", json={"input_message": "test"})
        assert run_resp.status_code == 200
        run = run_resp.json()
        assert run["status"] in ("pending", "running", "completed")
        assert run["id"] is not None

        # Give background task time to complete
        await asyncio.sleep(0.5)

    # 4. Check run status
    runs_resp = await client.get(f"/api/workflows/{wf['id']}/runs")
    assert runs_resp.status_code == 200


# ── Test 3: Message Delivery ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_messages_persisted_after_run(client):
    """Verify inter-agent messages are stored after execution."""
    # Create agent + workflow
    agent = (await client.post("/api/agents/", json={
        "name": "MsgAgent", "role": "Echo",
        "system_prompt": "Echo back the input.", "model": "gemini-2.5-flash",
    })).json()

    wf = (await client.post("/api/workflows/", json={
        "name": "MsgTest WF",
        "definition": {
            "nodes": [{"id": "n1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"agent_id": agent["id"], "label": "MsgAgent"}}],
            "edges": [],
        },
    })).json()

    mock_response = MagicMock()
    mock_response.content = "Echo: hello world"
    mock_response.tool_calls = []
    mock_response.usage_metadata = {"total_tokens": 5}

    with patch("runtime.executor.ChatGoogleGenerativeAI") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        run = (await client.post(f"/api/workflows/{wf['id']}/run", json={"input_message": "hello world"})).json()

        # Wait for background task
        await asyncio.sleep(1.0)

    # Fetch messages
    msgs_resp = await client.get(f"/api/workflows/runs/{run['id']}/messages")
    assert msgs_resp.status_code == 200
    messages = msgs_resp.json()
    assert len(messages) >= 1  # at least the user input message

    # Check user input message exists
    types = [m["message_type"] for m in messages]
    assert "user_input" in types


# ── Test 4: Monitor Stats ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monitor_stats(client):
    resp = await client.get("/api/monitor/stats")
    assert resp.status_code == 200
    stats = resp.json()
    for key in ["total_agents", "total_workflows", "total_runs", "total_messages", "runs_by_status"]:
        assert key in stats


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
