"""Tests for vorte.modules.database.planner — N1Detector and @select_related."""
import pytest
from vorte.modules.database.planner import (
    N1Detector,
    select_related,
    QueryPlanner,
)


# ---------------------------------------------------------------------------
# N1Detector
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_n1_detector_no_warning_under_threshold():
    async with N1Detector(threshold=5) as detector:
        for _ in range(3):
            detector.record("SELECT * FROM users")
    # No warning raised for 3 < 5


@pytest.mark.asyncio
async def test_n1_detector_counts_queries():
    async with N1Detector(threshold=100) as detector:
        detector.record("SELECT 1")
        detector.record("SELECT 2")
        detector.record()  # empty sql
        assert detector.query_count == 3


@pytest.mark.asyncio
async def test_n1_detector_stores_sql_strings():
    async with N1Detector(threshold=100) as detector:
        detector.record("SELECT * FROM posts")
        assert "SELECT * FROM posts" in detector.queries


@pytest.mark.asyncio
async def test_n1_detector_raises_when_configured():
    with pytest.raises(RuntimeError, match="N\\+1 query warning"):
        async with N1Detector(threshold=2, raise_on_exceed=True) as detector:
            for _ in range(5):
                detector.record()


@pytest.mark.asyncio
async def test_n1_detector_resets_between_contexts():
    async with N1Detector(threshold=100) as detector:
        detector.record()
        detector.record()
        count_first = detector.query_count

    async with N1Detector(threshold=100) as detector2:
        assert detector2.query_count == 0


# ---------------------------------------------------------------------------
# @select_related
# ---------------------------------------------------------------------------

def test_select_related_attaches_metadata():
    @select_related("posts", "profile")
    async def list_users():
        pass

    assert getattr(list_users, "_vorte_select_related", False) is True
    assert "posts" in list_users._vorte_relations
    assert "profile" in list_users._vorte_relations


def test_select_related_stacks():
    @select_related("posts")
    @select_related("profile")
    async def list_users():
        pass

    assert "posts" in list_users._vorte_relations
    assert "profile" in list_users._vorte_relations


@pytest.mark.asyncio
async def test_select_related_handler_still_callable():
    @select_related("comments")
    async def get_posts():
        return [{"id": 1}]

    result = await get_posts()
    assert result == [{"id": 1}]


# ---------------------------------------------------------------------------
# QueryPlanner
# ---------------------------------------------------------------------------

def test_query_planner_get_relations():
    @select_related("tags", "author")
    async def handler():
        pass

    planner = QueryPlanner()
    relations = planner.get_relations(handler)
    assert "tags" in relations
    assert "author" in relations


def test_query_planner_has_select_related():
    @select_related("comments")
    async def decorated_handler():
        pass

    async def plain_handler():
        pass

    planner = QueryPlanner()
    assert planner.has_select_related(decorated_handler) is True
    assert planner.has_select_related(plain_handler) is False


def test_query_planner_apply_without_sqlalchemy():
    """apply() should return the statement unchanged when SQLAlchemy not available."""
    planner = QueryPlanner()
    sentinel = object()
    result = planner.apply(sentinel, object, ("nonexistent_rel",))
    # Without a real SQLAlchemy model the attr lookup returns None and we fall through
    assert result is sentinel


def test_query_planner_stats_tracking():
    planner = QueryPlanner()
    assert planner.stats == {}
    planner.reset_stats()
    assert planner.stats == {}
