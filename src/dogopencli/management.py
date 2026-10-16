"""Local management declarations, independent of business domain identities."""

from .helpspec import BizNode

DECLARATIONS = (
    BizNode(
        ("domain",),
        "Inspect and control registered domains offline.",
        handler="cmd_domain_management",
    ),
    *(
        BizNode(("domain", action), summary, handler="cmd_domain_management")
        for action, summary in (
            ("list", "List registered domains and recorded status offline."),
            ("show", "Show one domain and its registered leaves."),
            ("leaves", "List one domain's registered leaves offline."),
            ("enable", "Enable subsequent execution for a registered domain."),
            ("disable", "Disable subsequent execution and preserve caches."),
        )
    ),
    BizNode(
        ("gui",), "Serve domain status and controls on localhost.", handler="cmd_gui"
    ),
)
