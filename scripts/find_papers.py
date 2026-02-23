from pathlib import Path

from arxiv_papers.list_papers import list_papers
from arxiv_papers.filter_papers import filter_papers
from arxiv_papers.openai_client import setup_client


def main() -> None:

    preferences = Path(__file__).parent / "preferences.txt"
    client = setup_client()

    papers = list_papers(days=2)
    print("Found", len(papers), "papers. Filtering...")

    filtered = filter_papers(papers, preferences, client, batch_size=15)
    print(f"{len(filtered)} papers matched preferences:\n")

    for fp in filtered:
        print(f'** TODO [#C] Read "{fp.paper.title}"')
        print(f"Authors: {', '.join(fp.paper.author)}")
        print(f"URL: {fp.paper.url}")
        print("Importance:", fp.importance)
        print(f"Why?\n{fp.explanation}")


if __name__ == "__main__":
    main()
