import pytest

from db import Database
from functions.create_user import create_user
from functions.get_user_context import get_user_context


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "reports.db")
    database.initialize()
    return database


def test_create_user_registers_new_user_id(db):
    result = create_user("new-uuid", relational_db=db)

    assert result == {"user_id": "new-uuid", "created": True}

    context = get_user_context("new-uuid", relational_db=db)
    assert context["user_id"] == "new-uuid"
    assert context["onboarding_done"] is False


def test_create_user_is_idempotent(db):
    first = create_user("dup-uuid", relational_db=db)
    second = create_user("dup-uuid", relational_db=db)

    assert first == {"user_id": "dup-uuid", "created": True}
    assert second == {"user_id": "dup-uuid", "created": False}


def test_create_user_requires_relational_db():
    with pytest.raises(ValueError):
        create_user("some-uuid", relational_db=None)


def test_create_user_rejects_blank_user_id(db):
    with pytest.raises(ValueError):
        create_user("   ", relational_db=db)
