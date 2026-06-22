import os
from typing import List, Optional
from urllib.parse import urlparse


DEFAULT_TAVILY_INCLUDE_DOMAINS = [
    "anitabi.cn",
    "bgm.tv",
    "bangumi.tv",
    "animetourism88.com",
    "anime-tourism.jp",
    "seichimap.jp",
    "ja.wikipedia.org",
    "zh.wikipedia.org",
    "japan-guide.com",
]

DEFAULT_TAVILY_EXCLUDE_DOMAINS = [
    "github.com",
    "huggingface.co",
    "kaggle.com",
    "medium.com",
    "csdn.net",
    "jianshu.com",
]


def _parse_domain_list(value: str) -> List[str]:
    if not value:
        return []

    domains = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue

        parsed = urlparse(item if "://" in item else f"https://{item}")
        domain = (parsed.netloc or parsed.path).strip().lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if domain:
            domains.append(domain)

    return list(dict.fromkeys(domains))


def get_tavily_search_kwargs(
    *,
    search_depth: str = "basic",
    include_answer: bool = False,
    max_results: Optional[int] = None,
) -> dict:
    """Build Tavily search kwargs with centralized domain allow/deny lists."""
    include_domains = _parse_domain_list(
        os.getenv("TAVILY_INCLUDE_DOMAINS", ",".join(DEFAULT_TAVILY_INCLUDE_DOMAINS))
    )
    exclude_domains = _parse_domain_list(
        os.getenv("TAVILY_EXCLUDE_DOMAINS", ",".join(DEFAULT_TAVILY_EXCLUDE_DOMAINS))
    )

    kwargs = {
        "search_depth": search_depth,
        "include_answer": include_answer,
    }
    if max_results is not None:
        kwargs["max_results"] = max_results
    if include_domains:
        kwargs["include_domains"] = include_domains
    if exclude_domains:
        kwargs["exclude_domains"] = exclude_domains

    return kwargs


def get_tavily_include_domains() -> List[str]:
    return _parse_domain_list(
        os.getenv("TAVILY_INCLUDE_DOMAINS", ",".join(DEFAULT_TAVILY_INCLUDE_DOMAINS))
    )
