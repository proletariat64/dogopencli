"""Daily market benchmarks through the public CLI, fake CDP and real SQLite."""

pytest_plugins = ["test_liquidity_cli_sit"]

FIELDS = (
    "id",
    "effectiveDate",
    "strategyBenchmarkType",
    "currency",
    "colorType",
    "value",
)
OPTIONS = ["--from-date", "20261001", "--to-date", "20261004"]


def benchmark(index=0, **overrides):
    return {
        "id": "",
        "effectiveDate": "20261002",
        "strategyBenchmarkType": (
            "passiveInterestBenchmark" if index < 9 else "tenorStrategyBenchmark"
        ),
        "currency": ("USD", "EUR", "HKD")[index % 3],
        "colorType": ("RED", "YELLOW", "GREEN")[(index // 3) % 3],
        "value": "2.0012300",
        **overrides,
    }


def command(*extra, refresh=False, options=None):
    return (
        (
            ["refresh", "liquidity", "investment", "benchmark-values"]
            if refresh
            else ["liquidity", "investment", "benchmark-values", "list"]
        )
        + (OPTIONS if options is None else options)
        + list(extra)
    )


def page(rows, total):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": total}},
    }


def listing(rows):
    def answer(body, index):
        return page(rows[body["rowStart"] : body["rowStart"] + 10], len(rows))

    return answer


def ordered(rows):
    return sorted(rows, key=lambda row: tuple(row[field] for field in FIELDS[1:5]))
