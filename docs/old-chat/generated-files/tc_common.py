"""Shared helper for test-case definitions."""

CASES = []

def T(module, sub, title, pre, steps, data, expected, pri="P1", typ="Functional", notes=""):
    """Register one test case.
    module: module name (also decides the ID prefix)
    steps: list of strings (numbered automatically)
    """
    if isinstance(steps, (list, tuple)):
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    CASES.append(dict(module=module, sub=sub, title=title, pre=pre, steps=steps,
                      data=data, expected=expected, pri=pri, typ=typ, notes=notes))

PREFIX = {
    "Agents List": "AGL",
    "Agent Profile": "AGP",
    "Agent Identity": "AGI",
    "Skills Tab": "SKL",
    "Asset Upload": "UPL",
    "Generation Lifecycle": "GEN",
    "Generation Quality - Actions": "GQA",
    "Generation Quality - Aggregation": "GQX",
    "Generation Quality - Docs & Instructions": "GQD",
    "Select Existing redflow": "SEL",
    "Editor & Syntax": "EDT",
    "Versions & Drafts": "VER",
    "Execution Parameters": "PAR",
    "Execution Control": "EXE",
    "Agent Runtime - Element Targeting": "RTE",
    "Agent Runtime - Page & App Conditions": "RTP",
    "Agent Runtime - Data & Outcome": "RTD",
    "Aggregation Execution & Output": "AGR",
    "Results Review": "RES",
    "Publish": "PUB",
    "API Trigger": "API",
    "Agent Settings": "SET",
    "Certified Agents": "CRT",
    "Security": "SEC",
    "Performance & Reliability": "PRF",
}
