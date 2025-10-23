from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
import html2text
from urllib.parse import urlparse, parse_qs, unquote


def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Naive web search using DuckDuckGo's HTML results.

    This avoids API keys for the baseline. For production, replace with a proper API.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; BaselineAgent/0.1; +https://example.com)"
    }
    params = {"q": query}
    try:
        resp = requests.get("https://duckduckgo.com/html/", params=params, headers=headers, timeout=10)
        resp.raise_for_status()
    except Exception:
        return []

    # Very rough extraction from HTML results
    results: List[Dict[str, str]] = []
    for part in resp.text.split('<a rel="nofollow" class="result__a" href="')[1:]:
        url = part.split('"', 1)[0]
        # Fix relative URLs from DuckDuckGo
        if url.startswith("//"):
            url = "https:" + url
        rest = part.split('>', 1)[1]
        title = rest.split('<', 1)[0]
        results.append({"title": title, "url": url})
        if len(results) >= max_results:
            break
    return results

def fetch_web_content(url: str, max_chars: int = 5000) -> str:
    """Fetch and extract the main text content from a webpage.

    Args:
        url: The URL to fetch content from
        max_chars: Maximum number of characters to return (default: 5000)

    Returns:
        The extracted text content from the webpage
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse HTML content
        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()

        # Get text content
        # Use html2text for better formatting
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.body_width = 0  # Don't wrap text

        text = h.handle(str(soup))

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        # Truncate if too long
        if len(text) > max_chars:
            text = text[:max_chars] + "...\n[Content truncated]"

        return text

    except requests.exceptions.RequestException as e:
        return f"Error fetching URL: {str(e)}"
    except Exception as e:
        return f"Error processing content: {str(e)}"

def search_and_fetch_content(query: str, max_results: int = 3, content_per_page: int = 3000) -> str:
    """Search the web and fetch actual content from the top results.

    This combines web search with content fetching to provide actual webpage content
    instead of just URLs.

    Args:
        query: The search query
        max_results: Maximum number of search results to fetch content from (default: 3)
        content_per_page: Maximum characters to fetch per webpage (default: 3000)

    Returns:
        Formatted string with search results and their actual content
    """
    # First, search for results
    search_results = web_search(query, max_results)

    if not search_results:
        return f"No search results found for query: '{query}'"

    # Fetch content from each result
    formatted_results = []
    for i, result in enumerate(search_results, 1):
        title = result.get('title', 'No title')
        url = result.get('url', '')
        parsed = urlparse(url)
        url = unquote(parse_qs(parsed.query)["uddg"][0])
        formatted_result = f"\n{'='*80}\nResult {i}: {title}\nURL: {url}\n{'-'*80}\n"

        # Fetch the actual content
        content = fetch_web_content(url, content_per_page)

        # Add the content
        formatted_result += f"Content:\n{content}\n"

        formatted_results.append(formatted_result)

    final_output = f"Search Query: '{query}'\nFound {len(search_results)} results\n"
    final_output += "\n".join(formatted_results)

    return final_output


if __name__ == "__main__":
    # Test the function
    query = "How to cook pasta"
    results = search_and_fetch_content(query, max_results=2)
    print(results)
