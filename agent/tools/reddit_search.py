from typing import List, Dict, Optional
import requests
import time


def search_reddit(query: str, subreddit: Optional[str] = None, max_results: int = 5, sort: str = "relevance") -> str:
    """Search Reddit posts using the Reddit JSON API (no authentication required).

    Args:
        query: The search query
        subreddit: Optional subreddit to search within (e.g., "python", "programming")
        max_results: Maximum number of results to return (default: 5)
        sort: Sort method - "relevance", "hot", "top", "new", "comments" (default: "relevance")

    Returns:
        Formatted string with Reddit search results including titles, scores, and content
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AgentMemory/1.0)"
        }

        # Build the search URL
        if subreddit:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
        else:
            url = "https://www.reddit.com/search.json"

        params = {
            "q": query,
            "limit": max_results,
            "sort": sort,
            "restrict_sr": "true" if subreddit else "false",
            "raw_json": 1
        }

        # Make the request
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Extract posts
        posts = data.get("data", {}).get("children", [])

        if not posts:
            return f"No Reddit results found for query: '{query}'"

        # Format results
        formatted_results = []
        for i, post in enumerate(posts[:max_results], 1):
            post_data = post.get("data", {})

            title = post_data.get("title", "No title")
            author = post_data.get("author", "Unknown")
            subreddit_name = post_data.get("subreddit", "")
            score = post_data.get("score", 0)
            num_comments = post_data.get("num_comments", 0)
            url = f"https://www.reddit.com{post_data.get('permalink', '')}"
            selftext = post_data.get("selftext", "")

            result = f"{i}. [{subreddit_name}] {title}\n"
            result += f"   Author: u/{author} | Score: {score} | Comments: {num_comments}\n"
            result += f"   URL: {url}\n"

            if selftext:
                # Truncate long posts
                if len(selftext) > 300:
                    selftext = selftext[:300] + "..."
                result += f"   Content: {selftext}\n"

            formatted_results.append(result)

        return "\n".join(formatted_results)

    except requests.exceptions.RequestException as e:
        return f"Error searching Reddit: {str(e)}"
    except Exception as e:
        return f"Error processing Reddit results: {str(e)}"


if __name__ == "__main__":
    # Test the function
    print("Test 1: General search")
    results = search_reddit("python programming", max_results=3)
    print(results)
    print("\n" + "="*80 + "\n")

    print("Test 2: Subreddit-specific search")
    results = search_reddit("best practices", subreddit="python", max_results=3)
    print(results)
