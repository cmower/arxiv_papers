import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from openai import OpenAI

from arxiv_papers.list_papers import ArxivPaper


class Importance(Enum):
    DEFINITELY_READ = "DEFINITELY_READ"  # critical to your work / directly aligned
    GOOD_TO_READ = "GOOD_TO_READ"  # useful but not urgent (surveys, adjacent methods)
    INTEREST = "INTEREST"  # personally interesting / tangential
    SKIM = "SKIM"  # not a priority, but worth a quick look


@dataclass(frozen=True)
class FilteredArxivPaper:
    paper: ArxivPaper
    importance: Importance
    explanation: str


def _chunked(items: list[Any], n: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def _paper_brief(p: ArxivPaper) -> dict[str, Any]:
    return {
        "arxiv_id": p.arxiv_id,
        "title": p.title,
        "authors": p.author,
        "abstract": p.abstract,
    }


def filter_papers(
    papers: list[ArxivPaper],
    preferences: Path,
    client: OpenAI,
    *,
    model: str = "gpt-5.2",
    batch_size: int | None = None,
    request_delay_s: float = 0.25,
) -> list[FilteredArxivPaper]:
    prefs_text = preferences.read_text(encoding="utf-8")

    response_format = {
        "type": "json_schema",
        "name": "arxiv_paper_filter_subset",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "selected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "arxiv_id": {"type": "string"},
                            "importance": {
                                "type": "string",
                                "enum": list(Importance._value2member_map_.keys()),
                            },
                            "explanation": {"type": "string"},
                        },
                        "required": ["arxiv_id", "importance", "explanation"],
                    },
                }
            },
            "required": ["selected"],
        },
    }

    by_id: dict[str, ArxivPaper] = {p.arxiv_id: p for p in papers}
    out: list[FilteredArxivPaper] = []

    instructions_path = Path(__file__).parent / "filter_instructions.txt"
    instructions = instructions_path.read_text(encoding="utf-8")

    if batch_size is None:
        batches: Iterable[list[ArxivPaper]] = [papers]
    else:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive or None")
        batches = _chunked(papers, batch_size)

    for batch in batches:
        payload = [_paper_brief(p) for p in batch]
        user_input = (
            "USER PREFERENCES:\n"
            f"{prefs_text}\n\n"
            "PAPERS (JSON):\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
        )

        resp = client.responses.create(
            model=model,
            instructions=instructions,
            input=user_input,
            text={"format": response_format},
        )

        data = json.loads(resp.output_text)

        for item in data["selected"]:
            pid = item["arxiv_id"]
            paper = by_id.get(pid)
            if paper is None:
                continue  # defensive

            out.append(
                FilteredArxivPaper(
                    paper=paper,
                    importance=Importance(item["importance"]),
                    explanation=item["explanation"].strip(),
                )
            )

        if request_delay_s > 0:
            time.sleep(request_delay_s)

    return out
