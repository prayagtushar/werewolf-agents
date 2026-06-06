import random

import pytest

from werewolf.names import NAME_POOL, pick_names


def test_pick_names_returns_distinct_names_of_requested_count():
    names = pick_names(random.Random(0), 9)
    assert len(names) == 9
    assert len(set(names)) == 9
    assert set(names) <= set(NAME_POOL)


def test_pick_names_raises_when_more_than_pool():
    with pytest.raises(ValueError):
        pick_names(random.Random(0), len(NAME_POOL) + 1)
