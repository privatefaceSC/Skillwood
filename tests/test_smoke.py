from sqlalchemy import text


def test_db_session_works(db_session):
    """Фикстура отдаёт рабочую сессию к in-memory SQLite."""
    result = db_session.execute(text("SELECT 1")).scalar()
    assert result == 1
