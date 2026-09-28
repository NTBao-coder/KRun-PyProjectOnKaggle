"""Small deterministic batch calculation."""


def squares(count: int) -> list[int]:
    """Return squares for the first count integers."""
    return [value * value for value in range(count)]
