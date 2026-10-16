"""Latest-created bank selection through CLI, fake CDP and real temporary SQLite."""

pytest_plugins = ["test_liquidity_cli_sit"]

ROOT = ["liquidity", "reference", "blacklist", "bank"]
FIELD = "bankFilterConfigQuery"


def bank(identity, created, **values):
    return {"bankId": identity, "gmtCreate": created, "status": "INVALID", **values}
