"""Entry point: ``python -m matricula_mcp`` / the ``matricula-mcp`` script."""

from __future__ import annotations

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
