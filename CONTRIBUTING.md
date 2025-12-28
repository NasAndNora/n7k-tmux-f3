# Contributing

Not accepting contributions at this time.

This project is in early development. Once stable, contribution guidelines will be added.

## Testing

```bash
# All tests (isolated env via tox)
uvx --with tox-uv tox -e py312

# Snapshot tests only
uvx --with tox-uv tox -e snapshots

# Specific test
uvx --with tox-uv tox -e py312 -- tests/test_foo.py -x
```

Why tox? Isolates env vars → no API keys leak in snapshot_report.html.
