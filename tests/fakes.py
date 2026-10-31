"""Fakes shared by pipeline and agent tests: an SEC transport and a structured-output LLM."""
import hashlib
import json
import re

from backend.llm.client import LLMResult, normalise
from backend.pipeline import prompts
from backend.sources.sec import SecClient

CIK = "0000999999"


def _flow(val, year):
    return {"val": val, "start": f"{year - 1}-10-01", "end": f"{year}-09-30", "filed": f"{year}-11-01", "form": "10-K", "accn": f"0000999999-{year % 100}-000001"}


def _instant(val, year):
    return {"val": val, "end": f"{year}-09-30", "filed": f"{year}-11-01", "form": "10-K", "accn": f"0000999999-{year % 100}-000001"}


COMPANY_FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [_flow(100e9, 2022), _flow(110e9, 2023), _flow(121e9, 2024)]}},
            "GrossProfit": {"units": {"USD": [_flow(40e9, 2022), _flow(45e9, 2023), _flow(50e9, 2024)]}},
            "OperatingIncomeLoss": {"units": {"USD": [_flow(20e9, 2022), _flow(24e9, 2023), _flow(30.25e9, 2024)]}},
            "NetIncomeLoss": {"units": {"USD": [_flow(15e9, 2022), _flow(18e9, 2023), _flow(22e9, 2024)]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_flow(25e9, 2024)]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [_flow(5e9, 2024)]}},
            "StockholdersEquity": {"units": {"USD": [_instant(60e9, 2023), _instant(70e9, 2024)]}},
        }
    }
}

FILING_HTML = (
    "<html><body><p>Item 1. Business</p><p>Item 1A. Risk Factors</p><p>Item 7. Management's Discussion and Analysis</p>"
    "<p>Item 1. Business</p>"
    + "<p>Widgetco designs industrial widgets and sells them to manufacturers in over forty countries.</p>" * 12
    + "<p>Item 1A. Risk Factors</p>"
    + "<p>A shortage of specialty steel could interrupt widget production and reduce margins.</p>" * 12
    + "<p>Item 7. Management's Discussion and Analysis of Financial Condition</p>"
    + "<p>Net sales grew due to strong demand for premium widgets in Europe.</p>" * 12
    + "<p>Item 8. Financial Statements</p></body></html>"
)

RESPONSES = {
    "https://www.sec.gov/files/company_tickers.json": {"0": {"cik_str": 999999, "ticker": "WDGT", "title": "Widgetco"}},
    f"https://data.sec.gov/submissions/CIK{CIK}.json": {
        "name": "Widgetco Inc.", "sic": "3560", "sicDescription": "General Industrial Machinery", "fiscalYearEnd": "0930",
        "exchanges": ["NYSE"],
        "filings": {"recent": {
            "form": ["10-K"], "accessionNumber": ["0000999999-24-000001"], "filingDate": ["2024-11-01"],
            "reportDate": ["2024-09-30"], "primaryDocument": ["wdgt-10k.htm"], "primaryDocDescription": ["10-K"],
        }},
    },
    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json": COMPANY_FACTS,
}


class FakeSec(SecClient):
    def __init__(self, tmp_path, responses=RESPONSES):
        super().__init__("FinResearch tests test@example.com", tmp_path)
        self.responses = responses

    def fetch(self, url, *, max_age_seconds):
        if url.endswith("wdgt-10k.htm"):
            return FILING_HTML.encode()
        if url in self.responses:
            return json.dumps(self.responses[url]).encode()
        return None


class FakeLLM:
    """Follows the prompt contract: quotes verbatim from excerpts, cites metric ids, never invents numbers."""

    fast_model = "fake-fast"
    strong_model = "fake-strong"

    def embed(self, texts, *, task):
        vectors = []
        for text in texts:
            digest = hashlib.sha256(" ".join(sorted(set(text.lower().split()))).encode()).digest()
            vectors.append(normalise([digest[i % 32] - 128.0 for i in range(768)]))
        return vectors

    def generate_json(self, *, prompt, schema, system, strong=False, temperature=0.2):
        if schema is prompts.ResearchPlan:
            value = schema(sub_questions=["What are the main risks?", "How is profitability trending?"])
        elif schema is prompts.ClaimDraft:
            # Quote a substantive sentence, as the prompt asks; headings aren't evidence.
            blocks = re.findall(r"\[(E\d+)\] \([^)]*\)\n(.*?)(?=\n\n\[E|\Z)", prompt, re.S)
            excerpts = {
                eid: next(line for line in text.splitlines() if len(line.split()) >= 6 and not line.lower().startswith("item"))
                for eid, text in blocks
                if any(len(line.split()) >= 6 and not line.lower().startswith("item") for line in text.splitlines())
            }
            metrics = dict(re.findall(r"(M\d+): Operating margin FY2024 = ([\d.]+%)", prompt))
            first_id, first_text = next(iter(excerpts.items()))
            metric_id, shown = next(iter(metrics.items()))
            value = schema(claims=[
                prompts.DraftClaim(section="business", claim_type="fact", text="Widgetco sells widgets globally.",
                                   evidence=[prompts.EvidenceRef(excerpt_id=first_id, quote=first_text)], importance=3),
                prompts.DraftClaim(section="profitability", claim_type="calculation",
                                   text=f"Operating margin was {shown} in FY2024.", metric_refs=[metric_id], importance=3),
                prompts.DraftClaim(section="profitability", claim_type="calculation",
                                   text="Operating margin was 99.0% in FY2024.", metric_refs=[metric_id], importance=1),
                prompts.DraftClaim(section="risks", claim_type="fact", text="Steel shortages are a risk.",
                                   evidence=[prompts.EvidenceRef(excerpt_id=first_id, quote="this sentence is not in the filing at all")],
                                   importance=2),
            ])
        elif schema is prompts.Judgements:
            value = schema(judgements=[prompts.Judgement(claim_id=cid, verdict="supported", note="Quote matches.")
                                       for cid in re.findall(r"^(C\d+) ", prompt, re.MULTILINE)])
        elif schema is prompts.ReportDraft:
            value = schema(
                headline="Widgetco: growing, profitable, steel-exposed",
                direct_answer="Revenue and margins have grown steadily.",
                executive_summary="Widgetco grew revenue with expanding margins.",
                key_points=[prompts.KeyPoint(text="Margins expanded.", claim_ids=["C1", "C2"])],
                investment_thesis="Premium demand supports margins.",
                scenarios=[prompts.Scenario(name=n, summary=n, assumptions=[prompts.Assumption(driver="growth", assumption="10%", basis="M1")]) for n in ("bull", "base", "bear")],
                risks=[prompts.Risk(title="Steel", description="Input shortages", severity="high", claim_ids=["C1"])],
                open_questions=["How concentrated are customers?"],
            )
        else:
            raise AssertionError(schema)
        return LLMResult(value=value, model=self.strong_model if strong else self.fast_model, input_tokens=100, output_tokens=50)


def ingest(make_job, tmp_path, ticker="WDGT"):
    """Run the deterministic stages (resolve → index) for a new job and return its id."""
    from backend.pipeline.research import Services, research_stages
    from backend.worker.main import Worker

    job = make_job(ticker=ticker)
    services = Services(sec_factory=lambda: FakeSec(tmp_path), llm_factory=FakeLLM)
    Worker(stages_factory=lambda: research_stages(services)[:5], retry_base_seconds=0).run_once()
    return job
