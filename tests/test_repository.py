"""Tests for the expanded repository layer — Session and ContextBlock CRUD."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from devmemory.db.repository import (
    create_bulk_context_blocks,
    create_context_block,
    create_session,
    create_user,
    delete_context_block,
    get_context_blocks,
    get_or_create_project,
    get_project_by_id,
    get_session,
    list_sessions,
    update_context_block,
    update_session,
)
from devmemory.models import (
    ContextBlock,
    Session,
    SessionStatus,
)


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
async def user_a(db_session: AsyncSession):
    """Create test user A."""
    return await create_user(db_session, "alice@test.com", "password123", "Alice")


@pytest.fixture
async def user_b(db_session: AsyncSession):
    """Create test user B."""
    return await create_user(db_session, "bob@test.com", "password456", "Bob")


@pytest.fixture
async def project_a(db_session: AsyncSession, user_a):
    """Create a project for user A."""
    project, _ = await get_or_create_project(
        db_session, user_a.id, "alice-webapp", name="Alice's Web App"
    )
    return project


@pytest.fixture
async def project_b(db_session: AsyncSession, user_b):
    """Create a project for user B."""
    project, _ = await get_or_create_project(
        db_session, user_b.id, "bob-api", name="Bob's API"
    )
    return project


@pytest.fixture
async def session_a(db_session: AsyncSession, user_a, project_a):
    """Create a session for user A's project."""
    return await create_session(
        db_session, user_a.id, project_a.id, "Build auth system", "cursor"
    )


# ── Project Operations ─────────────────────────────────────────


class TestGetProjectById:
    """Tests for get_project_by_id."""

    async def test_get_own_project(self, db_session, user_a, project_a):
        result = await get_project_by_id(db_session, project_a.id, user_a.id)
        assert result is not None
        assert result.slug == "alice-webapp"

    async def test_cannot_access_other_users_project(self, db_session, user_a, project_b):
        result = await get_project_by_id(db_session, project_b.id, user_a.id)
        assert result is None

    async def test_nonexistent_project(self, db_session, user_a):
        result = await get_project_by_id(db_session, "nonexistent-id", user_a.id)
        assert result is None


# ── Session Operations ─────────────────────────────────────────


class TestCreateSession:
    """Tests for session creation."""

    async def test_create_session_success(self, db_session, user_a, project_a):
        dev_session = await create_session(
            db_session, user_a.id, project_a.id, "New feature", "claude"
        )
        assert dev_session is not None
        assert dev_session.title == "New feature"
        assert dev_session.tool_source == "claude"
        assert dev_session.status == SessionStatus.ACTIVE.value
        assert dev_session.project_id == project_a.id

    async def test_create_session_strips_whitespace(self, db_session, user_a, project_a):
        dev_session = await create_session(
            db_session, user_a.id, project_a.id, "  Padded Title  ", "  CURSOR  "
        )
        assert dev_session.title == "Padded Title"
        assert dev_session.tool_source == "cursor"

    async def test_create_session_wrong_user_fails(self, db_session, user_b, project_a):
        """User B cannot create sessions in user A's project."""
        result = await create_session(
            db_session, user_b.id, project_a.id, "Hacking", "evil-tool"
        )
        assert result is None


class TestGetSession:
    """Tests for session retrieval with eager loading."""

    async def test_get_session_with_blocks(self, db_session, user_a, session_a):
        # Add a context block first
        block = ContextBlock(
            session_id=session_a.id,
            block_type="goal",
            content="Add JWT auth",
        )
        db_session.add(block)
        await db_session.flush()

        result = await get_session(db_session, session_a.id, user_a.id)
        assert result is not None
        assert result.title == "Build auth system"
        # Context blocks should be eagerly loaded
        assert len(result.context_blocks) == 1
        assert result.context_blocks[0].content == "Add JWT auth"
        # Project should be eagerly loaded
        assert result.project is not None
        assert result.project.slug == "alice-webapp"

    async def test_get_session_wrong_user(self, db_session, user_b, session_a):
        """User B cannot access user A's session."""
        result = await get_session(db_session, session_a.id, user_b.id)
        assert result is None

    async def test_get_nonexistent_session(self, db_session, user_a):
        result = await get_session(db_session, "nonexistent", user_a.id)
        assert result is None


class TestListSessions:
    """Tests for session listing with filters."""

    async def test_list_all_sessions(self, db_session, user_a, project_a):
        await create_session(db_session, user_a.id, project_a.id, "Session 1", "cursor")
        await create_session(db_session, user_a.id, project_a.id, "Session 2", "claude")

        sessions = await list_sessions(db_session, user_a.id)
        assert len(sessions) == 2

    async def test_list_filtered_by_project(self, db_session, user_a, project_a):
        # Create a second project
        project2, _ = await get_or_create_project(db_session, user_a.id, "second-project")
        await create_session(db_session, user_a.id, project_a.id, "In project A", "cursor")
        await create_session(db_session, user_a.id, project2.id, "In project B", "cursor")

        sessions = await list_sessions(db_session, user_a.id, project_id=project_a.id)
        assert len(sessions) == 1
        assert sessions[0].title == "In project A"

    async def test_list_filtered_by_status(self, db_session, user_a, project_a):
        s1 = await create_session(db_session, user_a.id, project_a.id, "Active", "cursor")
        s2 = await create_session(db_session, user_a.id, project_a.id, "Paused", "cursor")
        s2.status = SessionStatus.PAUSED.value
        await db_session.flush()

        active_sessions = await list_sessions(
            db_session, user_a.id, status=SessionStatus.ACTIVE.value
        )
        assert len(active_sessions) == 1
        assert active_sessions[0].title == "Active"

    async def test_list_respects_limit(self, db_session, user_a, project_a):
        for i in range(5):
            await create_session(db_session, user_a.id, project_a.id, f"Session {i}", "cursor")

        sessions = await list_sessions(db_session, user_a.id, limit=3)
        assert len(sessions) == 3

    async def test_list_user_isolation(self, db_session, user_a, user_b, project_a, project_b):
        """Each user only sees their own sessions."""
        await create_session(db_session, user_a.id, project_a.id, "Alice's session", "cursor")
        await create_session(db_session, user_b.id, project_b.id, "Bob's session", "claude")

        alice_sessions = await list_sessions(db_session, user_a.id)
        bob_sessions = await list_sessions(db_session, user_b.id)

        assert len(alice_sessions) == 1
        assert alice_sessions[0].title == "Alice's session"
        assert len(bob_sessions) == 1
        assert bob_sessions[0].title == "Bob's session"


class TestUpdateSession:
    """Tests for session updates."""

    async def test_update_status(self, db_session, user_a, session_a):
        updated = await update_session(
            db_session, session_a.id, user_a.id,
            status=SessionStatus.COMPLETED.value,
        )
        assert updated is not None
        assert updated.status == SessionStatus.COMPLETED.value

    async def test_update_title(self, db_session, user_a, session_a):
        updated = await update_session(
            db_session, session_a.id, user_a.id, title="Renamed session"
        )
        assert updated is not None
        assert updated.title == "Renamed session"

    async def test_update_wrong_user(self, db_session, user_b, session_a):
        result = await update_session(
            db_session, session_a.id, user_b.id,
            status=SessionStatus.ARCHIVED.value,
        )
        assert result is None


# ── Context Block Operations ───────────────────────────────────


class TestCreateContextBlock:
    """Tests for context block creation."""

    async def test_create_block(self, db_session, user_a, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Add JWT authentication",
        )
        assert block is not None
        assert block.block_type == "goal"
        assert block.content == "Add JWT authentication"
        assert block.priority == 5  # default

    async def test_create_block_with_metadata(self, db_session, user_a, session_a):
        meta = json.dumps({"file_path": "auth.py", "language": "python"})
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="code", content="def login():", meta_json=meta, priority=8,
        )
        assert block is not None
        assert block.meta_json == meta
        assert block.priority == 8

    async def test_create_block_wrong_user(self, db_session, user_b, session_a):
        result = await create_context_block(
            db_session, session_a.id, user_b.id,
            block_type="goal", content="Hack!",
        )
        assert result is None


class TestCreateBulkContextBlocks:
    """Tests for bulk context block creation."""

    async def test_bulk_create(self, db_session, user_a, session_a):
        blocks_data = [
            {"block_type": "goal", "content": "Add auth"},
            {"block_type": "decision", "content": "Use JWT", "priority": 8},
            {"block_type": "next_step", "content": "Write tests"},
        ]
        blocks = await create_bulk_context_blocks(
            db_session, session_a.id, user_a.id, blocks_data
        )
        assert blocks is not None
        assert len(blocks) == 3
        assert blocks[0].block_type == "goal"
        assert blocks[1].priority == 8
        assert blocks[2].content == "Write tests"

    async def test_bulk_create_wrong_user(self, db_session, user_b, session_a):
        result = await create_bulk_context_blocks(
            db_session, session_a.id, user_b.id,
            [{"block_type": "goal", "content": "Hack!"}],
        )
        assert result is None


class TestGetContextBlocks:
    """Tests for context block retrieval."""

    async def test_get_all_blocks(self, db_session, user_a, session_a):
        for btype in ["goal", "decision", "code"]:
            await create_context_block(
                db_session, session_a.id, user_a.id,
                block_type=btype, content=f"Content for {btype}",
            )

        blocks = await get_context_blocks(db_session, session_a.id, user_a.id)
        assert blocks is not None
        assert len(blocks) == 3

    async def test_filter_by_type(self, db_session, user_a, session_a):
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Goal 1",
        )
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="decision", content="Decision 1",
        )
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Goal 2",
        )

        goals = await get_context_blocks(
            db_session, session_a.id, user_a.id, block_type="goal"
        )
        assert goals is not None
        assert len(goals) == 2
        assert all(b.block_type == "goal" for b in goals)

    async def test_ordered_by_priority_desc(self, db_session, user_a, session_a):
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Low priority", priority=2,
        )
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="High priority", priority=9,
        )

        blocks = await get_context_blocks(db_session, session_a.id, user_a.id)
        assert blocks is not None
        assert blocks[0].content == "High priority"
        assert blocks[1].content == "Low priority"

    async def test_respects_limit(self, db_session, user_a, session_a):
        for i in range(5):
            await create_context_block(
                db_session, session_a.id, user_a.id,
                block_type="goal", content=f"Block {i}",
            )

        blocks = await get_context_blocks(
            db_session, session_a.id, user_a.id, limit=3
        )
        assert blocks is not None
        assert len(blocks) == 3

    async def test_wrong_user_returns_none(self, db_session, user_b, session_a):
        result = await get_context_blocks(db_session, session_a.id, user_b.id)
        assert result is None


class TestUpdateContextBlock:
    """Tests for context block updates."""

    async def test_update_content(self, db_session, user_a, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Original",
        )
        updated = await update_context_block(
            db_session, block.id, user_a.id, content="Updated content"
        )
        assert updated is not None
        assert updated.content == "Updated content"

    async def test_update_priority(self, db_session, user_a, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Test", priority=3,
        )
        updated = await update_context_block(
            db_session, block.id, user_a.id, priority=10
        )
        assert updated is not None
        assert updated.priority == 10

    async def test_update_wrong_user(self, db_session, user_a, user_b, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Alice's block",
        )
        result = await update_context_block(
            db_session, block.id, user_b.id, content="Hacked!"
        )
        assert result is None

    async def test_update_nonexistent_block(self, db_session, user_a):
        result = await update_context_block(
            db_session, "nonexistent-id", user_a.id, content="Nothing"
        )
        assert result is None


class TestDeleteContextBlock:
    """Tests for context block deletion."""

    async def test_delete_block(self, db_session, user_a, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="To be deleted",
        )
        success = await delete_context_block(db_session, block.id, user_a.id)
        assert success is True

        # Verify it's gone
        result = await db_session.execute(
            select(ContextBlock).where(ContextBlock.id == block.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_delete_wrong_user(self, db_session, user_a, user_b, session_a):
        block = await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Protected",
        )
        success = await delete_context_block(db_session, block.id, user_b.id)
        assert success is False

    async def test_delete_nonexistent(self, db_session, user_a):
        success = await delete_context_block(db_session, "nonexistent", user_a.id)
        assert success is False


# ── Cascade Delete ─────────────────────────────────────────────


class TestCascadeDeletes:
    """Tests for cascade delete behavior."""

    async def test_delete_session_cascades_blocks(self, db_session, user_a, session_a):
        """Deleting a session should delete all its context blocks."""
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="goal", content="Block 1",
        )
        await create_context_block(
            db_session, session_a.id, user_a.id,
            block_type="code", content="Block 2",
        )

        # Reload the session with relationships so ORM cascade can track children
        loaded_session = await get_session(db_session, session_a.id, user_a.id)
        assert loaded_session is not None

        # Delete the session — ORM cascade should delete blocks
        await db_session.delete(loaded_session)
        await db_session.flush()

        # Blocks should be gone
        result = await db_session.execute(
            select(ContextBlock).where(ContextBlock.session_id == session_a.id)
        )
        assert list(result.scalars().all()) == []

    async def test_delete_project_cascades_sessions(self, db_session, user_a, project_a):
        """Deleting a project should cascade to sessions and blocks."""
        s = await create_session(
            db_session, user_a.id, project_a.id, "Temp session", "cursor"
        )
        await create_context_block(
            db_session, s.id, user_a.id,
            block_type="goal", content="Cascade test",
        )

        # Delete the project
        await db_session.delete(project_a)
        await db_session.flush()

        # Sessions and blocks should be gone
        sessions = await db_session.execute(
            select(Session).where(Session.project_id == project_a.id)
        )
        assert list(sessions.scalars().all()) == []
