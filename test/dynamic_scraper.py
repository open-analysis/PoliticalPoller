from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# URL = "https://quotes.toscrape.com/js-delayed/"
URL="https://candidates.sos.mn.gov/CandidateFilingResults.aspx?county=0&municipality=0&schooldistrict=0&hospitaldistrict=0&level=1&party=0&federal=True&judicial=True&executive=True&senate=True&representative=True&title=&office=0&candidateid=0"
TIMEOUT_MS = 15_000


@dataclass
class Quote:
    text: str
    author: str
    tags: list[str]


def scrape_quotes(limit: int = 5) -> list[Quote]:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent="python-web-scraping-tutorial/1.0"
            )

            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
                page.wait_for_selector(".quote", timeout=TIMEOUT_MS)

                quote_cards = page.locator(".quote")
                quote_count = min(quote_cards.count(), limit)
                quotes: list[Quote] = []

                for index in range(quote_count):
                    card = quote_cards.nth(index)

                    quotes.append(
                        Quote(
                            text=card.locator(".text").inner_text().strip(),
                            author=card.locator(".author").inner_text().strip(),
                            tags=[
                                tag.strip()
                                for tag in card.locator(".tag").all_inner_texts()
                            ],
                        )
                    )

                return quotes

            finally:
                browser.close()

    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Timed out waiting for quote content.") from exc
    except PlaywrightError as exc:
        raise RuntimeError(f"Playwright failed: {exc}") from exc


def main() -> None:
    quotes = scrape_quotes()

    for quote in quotes:
        print(quote.text)
        print(f"Author: {quote.author}")
        print(f"Tags: {', '.join(quote.tags) if quote.tags else 'none'}")
        print()


if __name__ == "__main__":
    main()