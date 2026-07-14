"""Tests for SQLAlchemy models — creation, relationships, and enums."""

from __future__ import annotations

from devmemory.models import (
    ApiKey,
    Base,
    BlockType,
    ContextBlock,
    Project,
    Session,
    SessionStatus,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    User,
)


class TestUserModel:
    """Tests for the User model."""

    async def test_create_user(self, db_session):
        """Create a user and verify fields persist."""
        user = User(
            email="test@devmemory.io",
            password_hash="hashed_password_here",
            display_name="Test User",
        )
        db_session.add(user)
        await db_session.flush()

        assert user.id is not None
        assert len(user.id) == 36  # UUID format
        assert user.email == "test@devmemory.io"
        assert user.display_name == "Test User"
        assert user.is_active is True
        assert user.created_at is not None
        assert user.updated_at is not None

    async def test_user_repr(self, db_session):
        """User repr shows email."""
        user = User(
            email="repr@test.com",
            password_hash="hash",
            display_name="Repr",
        )
        assert "repr@test.com" in repr(user)


class TestApiKeyModel:
    """Tests for the ApiKey model."""

    async def test_create_api_key(self, db_session):
        """Create an API key linked to a user."""
        user = User(
            email="apikey@test.com",
            password_hash="hash",
            display_name="API Key User",
        )
        db_session.add(user)
        await db_session.flush()

        key = ApiKey(
            user_id=user.id,
            key_hash="bcrypt_hash_of_the_key",
            name="cursor-home",
            prefix="dm_key_a1b2",
        )
        db_session.add(key)
        await db_session.flush()

        assert key.id is not None
        assert key.user_id == user.id
        assert key.name == "cursor-home"
        assert key.prefix == "dm_key_a1b2"
        assert key.revoked is False
        assert key.last_used_at is None

    async def test_api_key_repr(self, db_session):
        """ApiKey repr shows prefix and name."""
        key = ApiKey(
            user_id="fake-id",
            key_hash="hash",
            name="test-key",
            prefix="dm_key_xxxx",
        )
        assert "dm_key_xxxx" in repr(key)
        assert "test-key" in repr(key)


class TestSubscriptionModel:
    """Tests for the Subscription model."""

    async def test_create_free_subscription(self, db_session):
        """New subscriptions default to free tier."""
        user = User(
            email="sub@test.com",
            password_hash="hash",
            display_name="Sub User",
        )
        db_session.add(user)
        await db_session.flush()

        sub = Subscription(user_id=user.id)
        db_session.add(sub)
        await db_session.flush()

        assert sub.tier == SubscriptionTier.FREE.value
        assert sub.status == SubscriptionStatus.ACTIVE.value
        assert sub.is_active is True
        assert sub.tier_enum == SubscriptionTier.FREE
        assert sub.last_tx_hash is None
        assert sub.last_invoice_id is None

    async def test_subscription_tiers(self):
        """All expected tiers exist."""
        assert SubscriptionTier.FREE.value == "free"
        assert SubscriptionTier.PRO.value == "pro"
        assert SubscriptionTier.TEAM.value == "team"


class TestProjectModel:
    """Tests for the Project model."""

    async def test_create_project(self, db_session):
        """Create a project with git remote URL."""
        user = User(
            email="project@test.com",
            password_hash="hash",
            display_name="Project User",
        )
        db_session.add(user)
        await db_session.flush()

        project = Project(
            user_id=user.id,
            slug="yuguda999-devmemory",
            name="DevMemory",
            remote_url="git@github.com:Yuguda999/devmemory.git",
            description="Universal Dev Memory",
        )
        db_session.add(project)
        await db_session.flush()

        assert project.id is not None
        assert project.slug == "yuguda999-devmemory"
        assert project.remote_url == "git@github.com:Yuguda999/devmemory.git"


class TestSessionModel:
    """Tests for the Session model."""

    async def test_create_session(self, db_session):
        """Create a dev session within a project."""
        user = User(
            email="session@test.com",
            password_hash="hash",
            display_name="Session User",
        )
        db_session.add(user)
        await db_session.flush()

        project = Project(
            user_id=user.id,
            slug="test-project",
            name="Test Project",
        )
        db_session.add(project)
        await db_session.flush()

        session = Session(
            project_id=project.id,
            title="Fix authentication",
            tool_source="cursor",
        )
        db_session.add(session)
        await db_session.flush()

        assert session.id is not None
        assert session.title == "Fix authentication"
        assert session.tool_source == "cursor"
        assert session.status == SessionStatus.ACTIVE.value
        assert session.status_enum == SessionStatus.ACTIVE

    async def test_session_statuses(self):
        """All expected session statuses exist."""
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.ARCHIVED.value == "archived"


class TestContextBlockModel:
    """Tests for the ContextBlock model."""

    async def test_create_context_block(self, db_session):
        """Create a typed context block."""
        user = User(
            email="context@test.com",
            password_hash="hash",
            display_name="Context User",
        )
        db_session.add(user)
        await db_session.flush()

        project = Project(
            user_id=user.id,
            slug="ctx-project",
            name="Context Project",
        )
        db_session.add(project)
        await db_session.flush()

        session = Session(
            project_id=project.id,
            title="Build context engine",
            tool_source="claude",
        )
        db_session.add(session)
        await db_session.flush()

        block = ContextBlock(
            session_id=session.id,
            block_type=BlockType.GOAL.value,
            content="Implement JWT authentication for FastAPI endpoints",
            priority=8,
        )
        db_session.add(block)
        await db_session.flush()

        assert block.id is not None
        assert block.block_type == "goal"
        assert block.block_type_enum == BlockType.GOAL
        assert block.content == "Implement JWT authentication for FastAPI endpoints"
        assert block.priority == 8
        assert block.created_at is not None

    async def test_context_block_metadata(self, db_session):
        """Metadata JSON serialization works."""
        user = User(
            email="meta@test.com",
            password_hash="hash",
            display_name="Meta User",
        )
        db_session.add(user)
        await db_session.flush()

        project = Project(
            user_id=user.id,
            slug="meta-project",
            name="Meta Project",
        )
        db_session.add(project)
        await db_session.flush()

        session = Session(
            project_id=project.id,
            title="Metadata test",
            tool_source="windsurf",
        )
        db_session.add(session)
        await db_session.flush()

        block = ContextBlock(
            session_id=session.id,
            block_type=BlockType.CODE.value,
            content="def create_token(data): ...",
        )
        block.extra_metadata = {
            "file_path": "auth.py",
            "language": "python",
            "line_range": [10, 25],
        }
        db_session.add(block)
        await db_session.flush()

        assert block.extra_metadata == {
            "file_path": "auth.py",
            "language": "python",
            "line_range": [10, 25],
        }
        assert block.meta_json is not None

    async def test_context_block_empty_metadata(self, db_session):
        """Empty metadata returns empty dict."""
        user = User(
            email="empty@test.com",
            password_hash="hash",
            display_name="Empty",
        )
        db_session.add(user)
        await db_session.flush()

        project = Project(user_id=user.id, slug="empty-proj", name="Empty")
        db_session.add(project)
        await db_session.flush()

        session = Session(project_id=project.id, title="Empty test", tool_source="gemini")
        db_session.add(session)
        await db_session.flush()

        block = ContextBlock(
            session_id=session.id,
            block_type=BlockType.DECISION.value,
            content="Use bcrypt for password hashing",
        )
        db_session.add(block)
        await db_session.flush()

        assert block.extra_metadata == {}

    async def test_all_block_types_valid(self):
        """All expected block types exist."""
        expected = {
            "goal",
            "decision",
            "code",
            "file_ref",
            "error",
            "insight",
            "next_step",
            "dependency",
            "blocker",
            "task",
            "note",
        }
        actual = {bt.value for bt in BlockType}
        assert actual == expected

    async def test_context_block_default_priority(self, db_session):
        """Default priority is 5."""
        user = User(email="pri@test.com", password_hash="h", display_name="Pri")
        db_session.add(user)
        await db_session.flush()

        project = Project(user_id=user.id, slug="pri-proj", name="Pri")
        db_session.add(project)
        await db_session.flush()

        session = Session(project_id=project.id, title="Pri test", tool_source="cursor")
        db_session.add(session)
        await db_session.flush()

        block = ContextBlock(
            session_id=session.id,
            block_type=BlockType.INSIGHT.value,
            content="Default priority test",
        )
        db_session.add(block)
        await db_session.flush()

        assert block.priority == 5


class TestModelEnums:
    """Verify all enums have correct values."""

    async def test_subscription_tier_values(self):
        assert list(SubscriptionTier) == [
            SubscriptionTier.FREE,
            SubscriptionTier.PRO,
            SubscriptionTier.TEAM,
        ]

    async def test_session_status_values(self):
        assert list(SessionStatus) == [
            SessionStatus.ACTIVE,
            SessionStatus.PAUSED,
            SessionStatus.COMPLETED,
            SessionStatus.ARCHIVED,
        ]

    async def test_block_type_values(self):
        assert len(BlockType) == 11


class TestTableRegistry:
    """Verify all expected tables are registered in metadata."""

    async def test_all_tables_registered(self):
        expected_tables = {
            "users",
            "api_keys",
            "subscriptions",
            "projects",
            "sessions",
            "context_blocks",
            "tool_connections",
            "email_tokens",
            "invoices",
        }
        actual_tables = set(Base.metadata.tables.keys())
        assert expected_tables == actual_tables
