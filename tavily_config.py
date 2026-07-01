import os
from typing import List, Optional
from urllib.parse import urlparse


DEFAULT_TAVILY_INCLUDE_DOMAINS: list = []

DEFAULT_TAVILY_EXCLUDE_DOMAINS = [
    "github.com",
    "huggingface.co",
    "kaggle.com",
    "csdn.net",
    "stackoverflow.com",
    "npmjs.com",
    "pypi.org",
    "docker.com",
    "aws.amazon.com",
    "azure.microsoft.com",
]


# --- 动漫圣地巡礼搜索共享常量（tools.py 与 rag_service.py 共用，避免重复维护漂移） ---

# 站点定向 query：(展示标签, site: 过滤串)
ANIME_SCENE_SITE_QUERIES = [
    ("Bilibili专栏", "site:bilibili.com/read"),
    ("知乎", "site:zhihu.com"),
    ("巴哈姆特", "site:forum.gamer.com.tw"),
    ("Anitabi", "site:anitabi.cn"),
    ("日文博客(Ameblo)", "site:ameblo.jp"),
    ("日文博客(Livedoor)", "site:livedoor.jp"),
]

# 优质来源域名（用于相关性加分）
ANIME_SCENE_VALUE_DOMAINS = (
    "anitabi.cn",
    "bilibili.com",
    "zhihu.com",
    "gamer.com.tw",
    "ameblo.jp",
    "livedoor.jp",
    "hatena.ne.jp",
    "seichimap.jp",
    "anime-tourism.jp",
    "animetourism88.com",
    "note.com",
    "medium.com",
)

# 巡礼/交通/拍照关键词（用于相关性加分与 RAG 结果过滤）
ANIME_SCENE_TRAVEL_KEYWORDS = (
    "圣地巡礼", "聖地巡礼", "巡礼", "舞台探訪", "舞台", "取景地", "打卡",
    "攻略", "交通", "路线", "路線", "拍照", "机位", "撮影", "アクセス",
    "anime pilgrimage", "location", "scene", "route", "guide",
)


def parse_int_env(name: str, default: int, *, min_value: int = 1, max_value: Optional[int] = None) -> int:
    """安全解析整型环境变量：空串/非数字/None 时回退到 default，并夹取到 [min_value, max_value]。"""
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        value = default
    value = max(min_value, value)
    if max_value is not None:
        value = min(value, max_value)
    return value


def domain_matches(domain: str, value_domain: str) -> bool:
    """严格域名匹配：要求域名本身或以 '.' + value_domain 结尾，避免 notbilibili.com 匹配 bilibili.com。"""
    if not domain or not value_domain:
        return False
    return domain == value_domain or domain.endswith("." + value_domain)


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
