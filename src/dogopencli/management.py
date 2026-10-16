"""Local management declarations, independent of business domain identities."""

from .helpspec import NO_EFFECTS, BizNode

GUI_DECLARATION = BizNode(
    ("gui",),
    "Serve domain status and controls on localhost.",
    handler="cmd_gui",
    effects={**NO_EFFECTS, "mutates": True, "network": True},
    constraints=(
        "Serves HTTP only on localhost; never contacts production systems.",
        "Domain toggles write local execution settings; no production mutation, "
        "login or business query execution is available.",
    ),
)

DECLARATIONS = (
    BizNode(
        ("domain",),
        "Inspect and control registered domains offline.",
        handler="cmd_domain_management",
    ),
    *(
        BizNode(
            ("domain", action),
            summary,
            handler="cmd_domain_management",
            effects={**NO_EFFECTS, "mutates": action in {"enable", "disable"}},
            constraints=(
                "Changes local execution settings only; never mutates production "
                "business configuration.",
            )
            if action in {"enable", "disable"}
            else (),
        )
        for action, summary in (
            ("list", "List registered domains and recorded status offline."),
            ("show", "Show one domain and its registered leaves."),
            ("leaves", "List one domain's registered leaves offline."),
            ("enable", "Enable subsequent execution for a registered domain."),
            ("disable", "Disable subsequent execution and preserve caches."),
        )
    ),
    GUI_DECLARATION,
)
