# Contributing

Start with [docs/first-connector.md](docs/first-connector.md). [docs/protocol.md](docs/protocol.md)
is the contract, copied from Luminary at the SDK commit every connector here pins.

## A new connector

Open an issue first, naming the source and quoting what its terms say about automated download
and use as model input. A source whose terms forbid either is not accepted, nor a connector that
gets past a bot defence. Then a pull request with:

- the connector in its own folder, Apache-2.0, on the shared SDK pin;
- a README quoting the source's terms, with the link;
- tests that serve a local copy of the source, pass the conformance kit against a table of
  contents written from the real source, and record the bundle (`tests/test_golden.py`).

## A change to a connector

- A change meant to alter a bundle regenerates its golden (`GOLDEN_UPDATE=1 uv run pytest`) and
  says why in the pull request. Any other change leaves every golden passing.
- Moving to a newer SDK moves every connector at once: one commit in every `pyproject.toml` and
  `docs/protocol.md` copied from that commit's `docs/connectors.md`. `scripts/check_contract.py`
  fails CI otherwise.

## Checks

Each connector's suite runs on Linux, macOS and Windows (`.github/workflows/test.yml`):

```
cd <connector> && uv run --locked pytest -q
python scripts/check_contract.py
```

Sign off your commits (`git commit -s`).
