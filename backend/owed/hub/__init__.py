"""Local hackathon hub: /timeline, /questions, /architecture, /spec. Reads and writes docs/submission/*.json."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Body
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse

ROOT = Path(__file__).resolve().parents[3]          # repo root
DOCS = ROOT / "docs"
STATIC = Path(__file__).parent / "static"

router = APIRouter()


def _read_json(p: Path):
    return json.loads(p.read_text()) if p.exists() else {}


def _write_json(p: Path, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


@router.get("/hub", include_in_schema=False)
def home():
    return RedirectResponse("/hub/timeline")


for _page in ("timeline", "questions", "architecture", "spec"):
    def _make(page: str):
        def view():
            return FileResponse(STATIC / f"{page}.html")
        view.__name__ = f"page_{page}"
        return view
    router.add_api_route(f"/{_page}", _make(_page), methods=["GET"], include_in_schema=False)
    router.add_api_route(f"/hub/{_page}", _make(_page), methods=["GET"], include_in_schema=False)


@router.get("/hub/api/timeline")
def get_timeline():
    return _read_json(DOCS / "submission" / "timeline.json")


@router.put("/hub/api/timeline")
def put_timeline(data: dict = Body(...)):
    _write_json(DOCS / "submission" / "timeline.json", data)
    return {"ok": True}


@router.get("/hub/api/questions")
def get_questions():
    return _read_json(DOCS / "submission" / "devpost.json")


@router.put("/hub/api/questions")
def put_questions(data: dict = Body(...)):
    _write_json(DOCS / "submission" / "devpost.json", data)
    # also keep a markdown export next to it for pasting into Devpost
    s = data.get("sections", {})
    labels = [("inspiration", "Inspiration"), ("what_it_does", "What it does"), ("how_we_built_it", "How we built it"),
              ("company_challenges", "How it applies to company challenges"), ("challenges", "Challenges we ran into"),
              ("accomplishments", "Accomplishments that we're proud of"), ("what_we_learned", "What we learned"),
              ("whats_next", "What's next for Owed"), ("sentry_bug_writeup", "Sentry: the bug a trace found"),
              ("disclosures", "Disclosures"), ("built_with", "Built with")]
    md = [f"# {data.get('title','Owed')}", "", f"_{data.get('tagline','')}_", ""]
    for k, label in labels:
        if s.get(k):
            md += [f"## {label}", "", s[k], ""]
    (DOCS / "submission" / "devpost.md").write_text("\n".join(md))
    return {"ok": True}


@router.get("/hub/api/doc/{name}", response_class=PlainTextResponse)
def get_doc(name: str):
    allowed = {
        "spec": DOCS / "superpowers" / "specs" / "2026-10-17-owed-design.md",
        "contract": DOCS / "api-contract.md",
        "challenges": DOCS / "reference" / "confirmed-challenges.md",
        "ideas": DOCS / "brainstorm" / "2026-10-17-ideas.md",
    }
    p = allowed.get(name)
    return p.read_text() if p and p.exists() else f"no doc {name}"
