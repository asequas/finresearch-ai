from decimal import Decimal
from types import SimpleNamespace

from backend.pipeline.research import _resolve_basis

CLAIMS = {"C1": SimpleNamespace(id="claim-a", position=0), "C5": SimpleNamespace(id="claim-b", position=7)}
METRICS = {"M3": SimpleNamespace(label="Operating margin", period="FY2026", value=Decimal("0.468"), unit="ratio")}


def test_scenario_basis_handles_become_readable_references():
    resolved = _resolve_basis({"driver": "d", "assumption": "a", "basis": "Anchored to C5 and M3"}, CLAIMS, METRICS)

    assert resolved["basis"] == "Anchored to claim 8 and Operating margin FY2026 (46.8%)"
    assert resolved["claim_ids"] == ["claim-b"]


def test_unknown_handles_are_left_alone():
    assert _resolve_basis({"basis": "C9"}, CLAIMS, METRICS) == {"basis": "C9", "claim_ids": []}
