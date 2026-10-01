"""Every shipped contract has committed sampled evidence, not invented types."""

from dogopencli.catalog import NODES
from dogopencli.plugins.liquidity.fields import SAMPLED_FIELDS, VARIANT_SAMPLED_FIELDS
from dogopencli.plugins.liquidity.leaves import DETAIL_LEAVES, LIST_LEAVES
from dogopencli.plugins.liquidity.reading import description


def test_all_shipped_descriptions_have_field_evidence():
    names = set()
    for leaf in LIST_LEAVES.values():
        for variant in leaf.variants:
            names.add(variant.name)
            assert SAMPLED_FIELDS[variant.name]
        node = NODES[("liquidity", *leaf.path, "list")]
        assert description(node)["data_schema"]["properties"]
    for leaf in DETAIL_LEAVES.values():
        names.add(leaf.spec.name)
        assert SAMPLED_FIELDS[leaf.spec.name]
        node = NODES[("liquidity", *leaf.spec.path, leaf.spec.action)]
        assert description(node)["data_schema"]["properties"]
    assert set(SAMPLED_FIELDS) == names


def test_return_variants_keep_separate_sampled_fields():
    fields = VARIANT_SAMPLED_FIELDS["liquidity.investment.returns.list"]
    assert "investmentNo" in fields["/accrualBaseList.json"]
    assert "transactionId" in fields["/cashBaseList.json"]
    assert "settlementDate" in fields["/cashBaseList.json"]
    node = NODES[("liquidity", "investment", "returns", "list")]
    variants = description(node)["read_guide"]["variants"]
    cash = next(item for item in variants if item["selectors"]["basis"] == "cash")
    assert cash["selectors"] == {"basis": "cash"}
    assert "transactionId" in cash["data_schema"]["properties"]
    assert "investmentNo" not in cash["data_schema"]["properties"]
