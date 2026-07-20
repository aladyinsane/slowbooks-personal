from __future__ import annotations

import pytest

from slowbooks import db


@pytest.fixture
def conn():
    """A fresh in-memory book with the default chart and starter rules."""
    connection = db.connect(":memory:")
    db.initialize(connection)
    yield connection
    connection.close()
