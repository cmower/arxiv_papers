import re
import json
import time as _time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser


@dataclass(frozen=True)
class ArxivPaper:
    arxiv_id: str
    title: str
    author: list[str]
    url: str
    abstract: str
    year: int
    month: int
    day: int
    archive: str

    def as_dict(self) -> dict[str, str | list[str] | int]:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "author": self.author,
            "url": self.url,
            "abstract": self.abstract,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "archive": self.archive,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False)


_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

# Tolerant: matches the date at the *start* of the header, ignoring suffix like "(showing ...)"
_H3_DATE_PREFIX_RE = re.compile(
    r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*(\d{1,2})\s*([A-Za-z]{3})\s*(\d{4})\b"
)


def _as_utc_date(d: date | datetime) -> date:
    if isinstance(d, datetime):
        if d.tzinfo is None:
            return d.date()
        return d.astimezone(timezone.utc).date()
    return d


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "arxiv-list-script/1.0 (mailto:you@example.com)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}"


def _parse_posting_date(text: str) -> date | None:
    text = " ".join(text.split())
    m = _H3_DATE_PREFIX_RE.match(text)
    if not m:
        return None
    day = int(m.group(2))
    mon = m.group(3)
    year = int(m.group(4))
    month = _MONTHS.get(mon)
    if not month:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


class _ArxivAbsParser(HTMLParser):
    """Parse https://arxiv.org/abs/<id> and extract the abstract text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_abstract_block = False
        self._in_descriptor = False
        self._started = False
        self._parts: list[str] = []

    def abstract(self) -> str:
        return " ".join(" ".join(self._parts).split()).strip()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = dict(attrs)

        if tag == "blockquote":
            cls = (attrs_dict.get("class") or "").strip()
            # arXiv uses: class="abstract mathjax"
            if "abstract" in cls.split() or "abstract" in cls:
                self._in_abstract_block = True
                self._in_descriptor = False
                self._started = False
                self._parts.clear()
            return

        if self._in_abstract_block and tag == "span":
            cls = (attrs_dict.get("class") or "").strip()
            if "descriptor" in cls.split() or "descriptor" in cls:
                self._in_descriptor = True
            return

    def handle_endtag(self, tag: str):
        if self._in_abstract_block and tag == "span" and self._in_descriptor:
            self._in_descriptor = False
            self._started = True
            return

        if tag == "blockquote" and self._in_abstract_block:
            self._in_abstract_block = False
            return

    def handle_data(self, data: str):
        if not self._in_abstract_block:
            return
        if self._in_descriptor:
            # skip "Abstract:" label
            return
        if not self._started:
            return

        txt = " ".join(data.split())
        if not txt:
            return

        # Be defensive about occasional UI words
        if txt.lower() in {"less", "more"}:
            return

        self._parts.append(txt)


def _fetch_abstract_from_abs(arxiv_id: str) -> str:
    html = _fetch(_abs_url(arxiv_id))
    p = _ArxivAbsParser()
    p.feed(html)
    return p.abstract()


class _ArxivRecentParser(HTMLParser):
    """
    Parses https://arxiv.org/list/<archive>/recent pages, keeping entries in the
    most recent `days` posting-day buckets.

    NOTE: We intentionally do NOT rely on abstracts from this page.
    """

    def __init__(self, days: int, archive: str):
        super().__init__(convert_charrefs=True)
        self.days = max(1, days)
        self.archive = archive

        self._current_day: date | None = None
        self._days_seen: list[date] = []

        self._in_h3 = False
        self._h3_text_parts: list[str] = []

        self._in_dt = False
        self._pending_id: str | None = None

        self._in_dd = False

        self._in_title_div = False
        self._title_parts: list[str] = []
        self._title: str = ""

        self._in_authors_div = False
        self._in_author_a = False
        self._author_parts: list[str] = []
        self._authors: list[str] = []

        self._entries: list[tuple[date, str, str, list[str]]] = []
        # entries are tuples: (posting_day, arxiv_id, title, authors)

        self._seen_ids: set[str] = set()

    def entries(self) -> list[tuple[date, str, str, list[str]]]:
        return self._entries

    def _day_is_active(self) -> bool:
        return (
            self._current_day is not None
            and self._current_day in self._days_seen[: self.days]
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attrs_dict = dict(attrs)

        if tag == "h3":
            self._in_h3 = True
            self._h3_text_parts.clear()
            return

        if tag == "dt":
            self._in_dt = True
            self._pending_id = None
            return

        if tag == "a" and self._in_dt:
            href = (attrs_dict.get("href") or "").strip()
            if self._pending_id is None:
                if href.startswith("/abs/"):
                    self._pending_id = href[len("/abs/") :]
                elif href.startswith("https://arxiv.org/abs/"):
                    self._pending_id = href[len("https://arxiv.org/abs/") :]
            return

        if tag == "dd":
            self._in_dd = True
            self._title_parts.clear()
            self._title = ""
            self._authors = []
            return

        if tag == "div" and self._in_dd:
            cls = attrs_dict.get("class") or ""
            if "list-title" in cls:
                self._in_title_div = True
                self._title_parts.clear()
            elif "list-authors" in cls:
                self._in_authors_div = True
                self._authors = []
            return

        if tag == "a" and self._in_authors_div:
            self._in_author_a = True
            self._author_parts.clear()
            return

    def handle_endtag(self, tag: str):
        if tag == "h3" and self._in_h3:
            self._in_h3 = False
            d = _parse_posting_date("".join(self._h3_text_parts))
            if d is not None:
                if d not in self._days_seen:
                    self._days_seen.append(d)  # appears newest-first
                self._current_day = d
            return

        if tag == "dt":
            self._in_dt = False
            return

        if tag == "div" and self._in_title_div:
            self._in_title_div = False
            title = " ".join("".join(self._title_parts).split())
            if title.lower().startswith("title:"):
                title = title[6:].strip()
            self._title = title
            return

        if tag == "a" and self._in_author_a:
            self._in_author_a = False
            name = " ".join("".join(self._author_parts).split())
            if name:
                self._authors.append(name)
            return

        if tag == "div" and self._in_authors_div:
            self._in_authors_div = False
            return

        if tag == "dd" and self._in_dd:
            self._in_dd = False

            if not self._day_is_active():
                return
            if self._pending_id is None:
                return
            if self._pending_id in self._seen_ids:
                return
            if self._current_day is None:
                return

            self._seen_ids.add(self._pending_id)
            self._entries.append(
                (self._current_day, self._pending_id, self._title, self._authors)
            )
            return

    def handle_data(self, data: str):
        if self._in_h3:
            self._h3_text_parts.append(data)
            return
        if self._in_title_div:
            self._title_parts.append(data)
            return
        if self._in_author_a:
            self._author_parts.append(data)
            return


def list_papers(
    since: date | datetime | None = None,
    archive: str = "cs.RO",
    days: int = 1,
    show: int = 2000,
    per_paper_delay_s: float = 0.2,
) -> list[ArxivPaper]:
    """
    Returns papers in the most recent `days` posting-day buckets from:
      https://arxiv.org/list/<archive>/recent

    Optional `since` filters by posting date (UTC date if datetime given).

    per_paper_delay_s adds a small delay between /abs fetches to be polite.
    """
    since_date = _as_utc_date(since) if since is not None else None

    url = "https://arxiv.org/list/{}/recent?{}".format(
        urllib.parse.quote(archive),
        urllib.parse.urlencode({"skip": 0, "show": show}),
    )
    page = _fetch(url)

    parser = _ArxivRecentParser(days=days, archive=archive)
    parser.feed(page)

    out: list[ArxivPaper] = []
    for posting_day, arxiv_id, title, authors in parser.entries():
        if since_date is not None and posting_day < since_date:
            continue

        abstract = ""

        try:
            abstract = _fetch_abstract_from_abs(arxiv_id)
        except Exception:
            abstract = ""

        if per_paper_delay_s > 0:
            _time.sleep(per_paper_delay_s)

        p = ArxivPaper(
            arxiv_id=arxiv_id,
            title=title or "",
            author=authors,
            url=_abs_url(arxiv_id),
            abstract=abstract,
            year=posting_day.year,
            month=posting_day.month,
            day=posting_day.day,
            archive=archive,
        )
        out.append(p)

    return out


if __name__ == "__main__":
    archive = "cs.RO"
    papers = list_papers(archive=archive, days=1)
    print(
        f"Found {len(papers)} {archive} papers in the most recent posting day bucket."
    )
    for i, p in enumerate(papers, start=1):
        print("-" * 80)
        print(f"{i}. {p.title} ({p.year}-{p.month:02d}-{p.day:02d})")
        print(f"    {p.url}")
        print(f"    Authors: {', '.join(p.author)}")
        print(f"    Abstract: {p.abstract}")
