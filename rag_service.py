import os
import math
import logging
import requests
import json
import datetime
import hashlib
import time
from typing import List, Dict, Any, Tuple, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from dotenv import load_dotenv

# LangChain components
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from openai import OpenAI
from tavily import TavilyClient
import tools as scene_tools
import planning_progress as progress
from search_runtime import run_search_tasks
from tavily_config import (
    get_tavily_include_domains,
    get_tavily_search_kwargs,
    parse_int_env,
    ANIME_SCENE_SITE_QUERIES,
    ANIME_SCENE_TRAVEL_KEYWORDS,
    domain_matches,
)

load_dotenv()

# Version-safe import for RecursiveCharacterTextSplitter
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger("rag_service")
logging.basicConfig(level=logging.INFO)

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_history.json")
PENDING_FILE = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_pending.json")
COLLECTION_NAME = "anime_pilgrimage"
EMBEDDING_CONFIG_VERSION = "1"


def _positive_float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, default))
        return value if math.isfinite(value) and value > 0 else default
    except (TypeError, ValueError):
        return default


def _retrieved_at() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _source_id(url: str) -> str:
    return "src_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url or "")
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _failure_code(exc: BaseException) -> str:
    name = type(exc).__name__.lower()
    if isinstance(exc, (requests.exceptions.Timeout, TimeoutError)) or "timeout" in name:
        return "TOOL_TIMEOUT"
    if isinstance(exc, requests.exceptions.ConnectionError) or "connection" in name:
        return "TOOL_UNAVAILABLE"
    return "TOOL_ERROR"


def _trace_rag_failure(stage: str, exc: BaseException) -> None:
    try:
        import agent_trace
        agent_trace.record_exception(stage, exc, code=_failure_code(exc))
    except Exception:
        pass


def _trace_search_route(provider: str, landmark: str, **details) -> None:
    logger.info("RAG-Service: [%s] 搜索线路 %s: %s", landmark, provider, details)
    label = {"tavily": "Tavily", "baidu": "百度", "bing": "Bing", "ddg": "DuckDuckGo"}.get(provider, provider)
    key = f"search:{provider}:{landmark}"
    if details.get("skipped"):
        progress.activity("retrieve", key, f"{label} · {landmark}", "搜索服务未配置，本次跳过", "skipped")
    elif "trigger" in details:
        summary = "核心资料不足，正在做站点定向补充" if details["trigger"] == "site_supplement" else "正在检索公开资料"
        progress.activity("retrieve", key, f"{label} · {landmark}", summary, "running")
    else:
        added = details.get("new_sources", 0)
        summary = f"新增 {added} 条有效来源，累计 {details.get('total_sources', 0)} 条"
        if details.get("enough"):
            summary += "；资料已足够，跳过后续备用线路"
        progress.activity("retrieve", key, f"{label} · {landmark}", summary, "completed" if added else "warning")
    try:
        import agent_trace
        agent_trace.record_event("retrieve", f"联网检索：{provider}", {"provider": provider, "landmark": landmark, **details})
    except Exception:
        pass


def include_raw_content_enabled(env_name: str, default: str = "1") -> bool:
    return os.getenv(env_name, default).strip().lower() not in {"0", "false", "no", "off"}


def clean_search_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def result_content_with_raw(item: Dict[str, Any], raw_limit: int = 1800) -> str:
    content = clean_search_text(item.get("content", ""))
    raw_content = clean_search_text(item.get("raw_content", ""))
    if raw_content and raw_content != content:
        if len(raw_content) > raw_limit:
            raw_content = raw_content[:raw_limit].rstrip() + "..."
        return f"{content}\n正文摘录: {raw_content}" if content else raw_content
    return content

def log_rag_event(event_type: str, data: dict):
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        history = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        try:
            import agent_trace
            run_id = agent_trace.get_current_run_id()
        except Exception:
            run_id = None
        event = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
            "run_id": run_id,
            **data
        }
        history.insert(0, event)
        history = history[:200]
        
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to log RAG event: {e}")

class FallbackEmbeddings(Embeddings):
    """
    固定模型的向量提取器。服务异常时抛出异常，绝不把另一个模型的向量混入集合。
    """
    def __init__(self, model: str = None, base_url: str = None, dimension: int = None):
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-qwen3-embedding-0.6b")
        self.base_url = (base_url or os.getenv("EMBEDDING_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.dimension = dimension or parse_int_env("EMBEDDING_DIMENSION", 1024)
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=os.getenv("EMBEDDING_API_KEY", "lm-studio"),
            timeout=_positive_float_env("EMBEDDING_TIMEOUT_SECONDS", 5.0),
            max_retries=1,
        )

    def _check_vectors(self, vectors: List[List[float]]) -> List[List[float]]:
        if not vectors or any(len(vector) != self.dimension for vector in vectors):
            raise ValueError(f"embedding dimension mismatch: expected {self.dimension}")
        return vectors

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        response = self.client.embeddings.create(input=texts, model=self.model)
        vectors = [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
        if len(vectors) != len(texts):
            raise ValueError("embedding response count mismatch")
        return self._check_vectors(vectors)

    def embed_query(self, text: str) -> List[float]:
        response = self.client.embeddings.create(input=text, model=self.model)
        return self._check_vectors([response.data[0].embedding])[0]


class LMStudioReranker:
    """
    大模型 Logits 概率预测精排器：
    利用本地托管的 qwen3-reranker-0.6b 模型，直接通过对 output_text 产生的首 Token 概率做 logits 计算。
    若服务不可用则自动降级，保留向量库原始距离排序。
    """
    def __init__(self, model: str = "qwen3-reranker-0.6b", base_url: str = None, top_n: int = 3):
        self.model = model
        self.base_url = (base_url or os.getenv("RERANK_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.top_n = top_n
        self.failure_cooldown_seconds = parse_int_env("RERANK_FAILURE_COOLDOWN_SECONDS", 60)
        self.unavailable_until = 0.0

    def _score_single(self, query: str, doc_content: str) -> float:
        url = f"{self.base_url}/responses"
        input_data = [
            {"role": "system", "content": "你是一个文档相关性判定助手。你必须只回答 'yes' 或 'no'，不要输出任何解释或前缀。"},
            {"role": "user", "content": f"用户问题：{query}\n参考文档：{doc_content}\n该文档是否相关，能回答该问题吗？请仅回答 'yes' 或 'no'。是否相关:"}
        ]
        payload = {
            "model": self.model,
            "input": input_data,
            "include": ["message.output_text.logprobs"],
            "top_logprobs": 20,
            "temperature": 0.0,
            "max_tokens": 10
        }
        try:
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code != 200:
                return -1.0
            
            resp_data = resp.json()
            logprobs = None
            full_text = ""
            for out_item in resp_data.get("output", []):
                if out_item.get("type") == "message":
                    for content_item in out_item.get("content", []):
                        if content_item.get("type") == "output_text" and "logprobs" in content_item:
                            logprobs = content_item["logprobs"]
                            full_text = content_item.get("text", "")
                            break

            if not logprobs:
                return 10.0 if "yes" in full_text.lower() else 0.0

            yes_tokens = {"yes", "Yes", "YES"}
            no_tokens = {"no", "No", "NO"}

            for token_info in logprobs:
                token_str = token_info.get("token", "").strip()
                if token_str.lower() in {"yes", "no"}:
                    top_logprobs = token_info.get("top_logprobs", [])
                    yes_lp, no_lp = -99.0, -99.0
                    for tl in top_logprobs:
                        tl_token = tl.get("token", "").strip()
                        tl_val = float(tl.get("logprob", -99.0))
                        if tl_token in yes_tokens:
                            yes_lp = max(yes_lp, tl_val)
                        elif tl_token in no_tokens:
                            no_lp = max(no_lp, tl_val)
                            
                    if yes_lp > -99.0 or no_lp > -99.0:
                        p_yes = math.exp(yes_lp) if yes_lp > -99.0 else 0.0
                        p_no = math.exp(no_lp) if no_lp > -99.0 else 0.0
                        if p_yes + p_no > 0:
                            return round((p_yes / (p_yes + p_no)) * 10.0, 2)
                    return 10.0 if token_str.lower() == "yes" else 0.0
            return 10.0 if "yes" in full_text.lower() else 0.0
        except Exception as e:
            logger.debug(f"Reranker: 连续相关性打分异常，细节: {e}")
            return -1.0

    def rerank_with_scores(self, query: str, documents: List[Document]) -> List[Tuple[int, float, Document]]:
        if not documents:
            return []

        if self.unavailable_until > time.time():
            return [(i, -1.0, doc) for i, doc in enumerate(documents)]
        
        scored = []
        has_error = False
        for i, doc in enumerate(documents):
            score = self._score_single(query, doc.page_content)
            if score < 0.0:  # 接口异常自动降级
                has_error = True
                logger.warning("Reranker: 本地精排接口调用失败，自动降级为向量默认相似度排序。")
                break
            scored.append((i, score, doc))
        
        if has_error:
            # 降级模式：直接返回原顺序，分数设为 -1.0
            self.unavailable_until = time.time() + self.failure_cooldown_seconds
            return [(i, -1.0, doc) for i, doc in enumerate(documents)]
        
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored


class RAGService:
    """
    RAG 服务管理器：
    负责并发联网搜索、切片入库、Chroma 向量检索、LMStudioReranker 重排的完整流水线。
    """
    def __init__(self):
        self.db_dir = os.path.join(os.path.dirname(__file__), "chroma_db")
        os.makedirs(self.db_dir, exist_ok=True)
        
        self.embeddings = FallbackEmbeddings()
        self.embedding_config = {
            "embedding_config_version": os.getenv("EMBEDDING_CONFIG_VERSION", EMBEDDING_CONFIG_VERSION),
            "embedding_model": self.embeddings.model,
            "embedding_base_url": self.embeddings.base_url,
            "embedding_dimension": self.embeddings.dimension,
        }
        self.db = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=self.db_dir,
            collection_metadata=self.embedding_config,
        )
        self.vector_enabled = self._embedding_binding_verified()
        self.reranker = LMStudioReranker()
        
        # 初始化 Tavily 客户端
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily_client = TavilyClient(
            api_key=tavily_key,
            timeout=max(1, int(_positive_float_env("TAVILY_TIMEOUT_SECONDS", 10.0))),
        ) if tavily_key else None
        if not self.tavily_client:
            logger.warning("RAG-Service: 未配置 TAVILY_API_KEY，联网预检索将尝试直接搜索兜底。")

    def _embedding_binding_verified(self) -> bool:
        metadata = getattr(self.db._collection, "metadata", None) or {}
        verified = all(metadata.get(key) == value for key, value in self.embedding_config.items())
        if not verified:
            logger.warning(
                "RAG-Service: 向量集合 embedding 配置缺失或不匹配；暂停向量查询和写入。"
                "旧资料仍可按地标 ID 读取；请管理员核实模型配置后建立独立版本索引。"
            )
        return verified

    def is_landmark_indexed(self, landmark_id: str) -> bool:
        """
        判断地标是否已经在向量数据库中建立过索引，避免重复检索抓取。
        """
        try:
            # where 过滤：Chroma 允许根据 metadata 属性进行过滤
            results = self.db.get(where={"landmark_id": landmark_id})
            return len(results.get("ids", [])) > 0
        except Exception as e:
            logger.error(f"RAG-Service: 检查地标索引状态出错: {e}")
            return False

    def _read_pending(self) -> List[Dict]:
        """读取待审核暂存队列"""
        try:
            if os.path.exists(PENDING_FILE):
                with open(PENDING_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"RAG-Service: 读取待审核队列失败: {e}")
        return []

    def _write_pending(self, data: List[Dict]):
        """写入待审核暂存队列"""
        try:
            os.makedirs(os.path.dirname(PENDING_FILE), exist_ok=True)
            with open(PENDING_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"RAG-Service: 写入待审核队列失败: {e}")

    def get_pending_list(self) -> List[Dict]:
        """获取所有待审核的地标暂存记录"""
        return self._read_pending()

    def add_to_pending(
        self, landmark_id: str, name: str, bangumi: str, raw_text: str,
        chunks: List[str], sources: List[str],
        chunk_metadata: List[Dict[str, Any]] = None,
        source_records: List[Dict[str, Any]] = None,
    ):
        """将新搜索到的地标切片加入待审核暂存队列"""
        import uuid
        pending = self._read_pending()
        entry = {
            "id": f"pending_{uuid.uuid4().hex[:12]}",
            "landmark_id": landmark_id,
            "landmark_name": name,
            "bangumi": bangumi or "未知",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "raw_text_preview": raw_text[:1500] + "..." if len(raw_text) > 1500 else raw_text,
            "chunks": chunks,
            "sources": sources,
            "source_records": source_records or [],
            "chunk_metadata": chunk_metadata or [],
        }
        pending.append(entry)
        self._write_pending(pending)
        logger.info(f"RAG-Service: 地标 [{name}] 的 {len(chunks)} 个切片已暂存至待审核队列。")
        log_rag_event("pending", {
            "landmark_id": landmark_id,
            "landmark_name": name,
            "bangumi": bangumi,
            "chunks_count": len(chunks)
        })

    def approve_pending(self, pending_id: str, edited_chunks: List[str] = None) -> bool:
        """审批通过暂存记录，将编辑后的切片写入 ChromaDB"""
        pending = self._read_pending()
        target = None
        for item in pending:
            if item["id"] == pending_id:
                target = item
                break
        if not target:
            logger.warning(f"RAG-Service: 未找到待审核记录: {pending_id}")
            return False

        chunks_to_write = edited_chunks if edited_chunks else target["chunks"]
        if not chunks_to_write:
            logger.warning(f"RAG-Service: 审批记录 {pending_id} 无有效切片，跳过写入。")
            # 仍然从队列中移除
            pending = [p for p in pending if p["id"] != pending_id]
            self._write_pending(pending)
            return True

        if not self.vector_enabled:
            logger.error("RAG-Service: embedding 配置未核实，审批记录保留在待审核队列，未写入向量库。")
            return False

        documents_to_add = []
        stored_metadata = target.get("chunk_metadata") or []
        for i, chunk in enumerate(chunks_to_write):
            source_meta = stored_metadata[i] if i < len(stored_metadata) and len(chunks_to_write) == len(stored_metadata) else {}
            doc = Document(
                page_content=chunk,
                metadata={
                    "landmark_id": target["landmark_id"],
                    "landmark_name": target["landmark_name"],
                    "bangumi": target.get("bangumi", "未知"),
                    "chunk_id": i,
                    "source": "tavily_search",
                    "source_id": source_meta.get("source_id", ""),
                    "url": source_meta.get("url", ""),
                    "title": source_meta.get("title", ""),
                    "retrieved_at": source_meta.get("retrieved_at", ""),
                    "review_status": "approved" if source_meta.get("url") else "missing",
                }
            )
            documents_to_add.append(doc)

        try:
            self.db.add_documents(documents_to_add)
            logger.info(f"RAG-Service: 审批通过，已将 [{target['landmark_name']}] 的 {len(documents_to_add)} 个切片写入 ChromaDB。")
            log_rag_event("ingest", {
                "landmarks_count": 1,
                "total_chunks_added": len(documents_to_add),
                "details": [{
                    "landmark_id": target["landmark_id"],
                    "landmark_name": target["landmark_name"],
                    "bangumi": target.get("bangumi", "未知"),
                    "chunks_count": len(chunks_to_write),
                    "chunks": chunks_to_write
                }]
            })
        except Exception as e:
            logger.error(f"RAG-Service: 审批写入 ChromaDB 失败: {e}")
            return False

        # 从暂存队列移除
        pending = [p for p in pending if p["id"] != pending_id]
        self._write_pending(pending)
        return True

    def reject_pending(self, pending_id: str) -> bool:
        """拒绝暂存记录，直接从队列中删除"""
        pending = self._read_pending()
        new_pending = [p for p in pending if p["id"] != pending_id]
        if len(new_pending) == len(pending):
            logger.warning(f"RAG-Service: 未找到待审核记录: {pending_id}")
            return False
        self._write_pending(new_pending)
        logger.info(f"RAG-Service: 已拒绝并删除待审核记录: {pending_id}")
        log_rag_event("reject", {"pending_id": pending_id})
        return True

    def delete_landmark_chunks(self, landmark_id: str) -> bool:
        """从 ChromaDB 中彻底删除指定地标的所有已存切片"""
        try:
            results = self.db.get(where={"landmark_id": landmark_id})
            ids_to_delete = results.get("ids", [])
            if not ids_to_delete:
                logger.info(f"RAG-Service: 地标 {landmark_id} 在数据库中不存在数据。")
                return False
            self.db._collection.delete(ids=ids_to_delete)
            logger.info(f"RAG-Service: 已从 ChromaDB 中删除地标 {landmark_id} 的 {len(ids_to_delete)} 个切片。")
            log_rag_event("delete", {
                "landmark_id": landmark_id,
                "chunks_deleted": len(ids_to_delete)
            })
            return True
        except Exception as e:
            logger.error(f"RAG-Service: 删除地标 {landmark_id} 的切片失败: {e}")
            return False

    def is_landmark_pending(self, landmark_id: str) -> bool:
        """检查某个地标是否已经在待审核队列中"""
        pending = self._read_pending()
        return any(p["landmark_id"] == landmark_id for p in pending)

    def _clean_text_value(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _is_unknown_value(self, value: Any) -> bool:
        text = self._clean_text_value(value)
        return not text or text.lower() in {"unknown", "none", "null"} or text in {"未知", "鏈煡"}

    def _landmark_names(self, landmark: Dict[str, Any]) -> List[str]:
        names = []
        for key in ("name", "originalName"):
            value = self._clean_text_value(landmark.get(key))
            if value and value not in names:
                names.append(value)
        return names

    def _bangumi_names(self, landmark: Dict[str, Any]) -> List[str]:
        names = []
        for key in ("bangumiName", "bangumiOriginalName"):
            value = self._clean_text_value(landmark.get(key))
            if not self._is_unknown_value(value) and value not in names:
                names.append(value)
        return names

    def _build_landmark_rag_query(self, landmark: Dict[str, Any]) -> str:
        parts = []
        parts.extend(self._bangumi_names(landmark))
        parts.extend(self._landmark_names(landmark))
        geo = landmark.get("geo")
        if isinstance(geo, (list, tuple)) and len(geo) >= 2:
            parts.append(f"{geo[0]}, {geo[1]}")
        elif geo:
            parts.append(str(geo))
        parts.extend(["圣地巡礼", "聖地巡礼", "舞台", "交通", "攻略", "拍照机位"])
        return " ".join([p for p in parts if p])

    def _contains_any(self, haystack: str, needles: List[str]) -> bool:
        haystack = haystack.lower()
        return any(needle.lower() in haystack for needle in needles if needle)

    def _is_doc_relevant_to_landmark(self, landmark: Dict[str, Any], doc: Document, score: float = -1.0) -> bool:
        meta = doc.metadata or {}
        landmark_id = self._clean_text_value(landmark.get("id"))
        stored_landmark_id = self._clean_text_value(meta.get("landmark_id"))
        if landmark_id and stored_landmark_id and stored_landmark_id != landmark_id:
            return False
        if landmark_id and stored_landmark_id == landmark_id:
            return True

        landmark_names = self._landmark_names(landmark)
        meta_landmark = self._clean_text_value(meta.get("landmark_name"))

        if meta_landmark and any(
            meta_landmark.lower() in name.lower() or name.lower() in meta_landmark.lower()
            for name in landmark_names
        ):
            return True

        content = doc.page_content or ""
        if self._contains_any(content, landmark_names):
            return True

        return False

    def _doc_dedup_key(self, doc: Document) -> str:
        meta = doc.metadata or {}
        landmark_id = self._clean_text_value(meta.get("landmark_id"))
        chunk_id = self._clean_text_value(meta.get("chunk_id"))
        if landmark_id and chunk_id:
            return f"{landmark_id}:{meta.get('source_id', '')}:{chunk_id}"
        digest = hashlib.sha1((doc.page_content or "").encode("utf-8")).hexdigest()
        return f"content:{digest}"

    def _source_from_doc(self, doc: Document, point_id: str) -> Dict[str, Any]:
        meta = doc.metadata or {}
        url = str(meta.get("url") or "").strip()
        if not _is_http_url(url):
            url = ""
        source_id = str(meta.get("source_id") or "").strip() if url else ""
        if not source_id:
            source_id = _source_id(url) if url else "missing_" + hashlib.sha256(
                f"{point_id}:{doc.page_content}".encode("utf-8")
            ).hexdigest()[:20]
        return {
            "source_id": source_id,
            "url": url,
            "title": str(meta.get("title") or ("来源缺失" if not url else "网页资料")),
            "retrieved_at": str(meta.get("retrieved_at") or ""),
            "review_status": str(meta.get("review_status") or "unreviewed") if url else "missing",
            "point_ids": [point_id] if point_id else [],
        }

    @staticmethod
    def _merge_source_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = {}
        for source in records:
            source_id = source["source_id"]
            if source_id not in merged:
                merged[source_id] = dict(source)
                merged[source_id]["point_ids"] = list(source.get("point_ids") or [])
            else:
                for point_id in source.get("point_ids") or []:
                    if point_id not in merged[source_id]["point_ids"]:
                        merged[source_id]["point_ids"].append(point_id)
        return list(merged.values())

    def _get_indexed_landmark_docs(self, landmark_id: str, limit: int) -> List[Document]:
        if not landmark_id:
            return []
        try:
            results = self.db.get(
                where={"landmark_id": landmark_id},
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.error(f"RAG-Service: direct landmark lookup failed for [{landmark_id}]: {e}")
            raise

        docs = []
        documents = results.get("documents", []) or []
        metadatas = results.get("metadatas", []) or []
        for content, meta in zip(documents, metadatas):
            if content:
                docs.append(Document(page_content=content, metadata=meta or {}))
            if len(docs) >= limit:
                break
        return docs

    def _format_landmark_context(self, grouped_docs: List[Dict[str, Any]]) -> str:
        blocks = []
        for item in grouped_docs:
            landmark = item["landmark"]
            docs = item["docs"]
            name = self._clean_text_value(landmark.get("name")) or self._clean_text_value(landmark.get("originalName")) or "未知"
            bangumi_names = self._bangumi_names(landmark)
            bangumi = bangumi_names[0] if bangumi_names else "未知"
            doc_blocks = []
            for doc_item in docs:
                doc = doc_item["doc"]
                score = doc_item["score"]
                meta = doc.metadata or {}
                ref_name = meta.get("landmark_name") or name
                ref_bangumi = meta.get("bangumi") or bangumi
                source = meta.get("source") or "RAG"
                source_id = self._source_from_doc(doc, self._clean_text_value(landmark.get("id")))["source_id"]
                score_text = "vector" if score < 0 else f"{score}"
                doc_blocks.append(
                    f"【参考地标: {ref_name} (涉及作品:《{ref_bangumi}》, 来源: {source}, 来源ID: {source_id}, 评分: {score_text})】\n"
                    f"{(doc.page_content or '').strip()}"
                )
            blocks.append(f"### {name} / {bangumi}\n" + "\n\n".join(doc_blocks))
        return "\n\n".join(blocks)

    def query_landmarks_context(
        self,
        landmarks: List[Dict[str, Any]],
        per_landmark_k: int = 4,
        per_landmark_limit: int = 2,
        global_limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Run independent RAG recall for each landmark, then reduce duplicated chunks.
        Returns formatted approved context plus per-landmark hit/miss lists.
        """
        missing_landmarks = []
        candidate_groups = []
        recall_details = []
        failures = []

        for landmark in landmarks:
            name = self._clean_text_value(landmark.get("name")) or self._clean_text_value(landmark.get("originalName"))
            query = self._build_landmark_rag_query(landmark)
            if not query:
                missing_landmarks.append(landmark)
                continue

            try:
                direct_docs = self._get_indexed_landmark_docs(
                    self._clean_text_value(landmark.get("id")), per_landmark_k,
                )
            except Exception as e:
                direct_docs = []
                failures.append({"landmark_id": landmark.get("id"), "stage": "id_recall", "code": _failure_code(e), "message": str(e)})
                _trace_rag_failure("rag_id_recall", e)
            vector_docs = []
            if self.vector_enabled:
                try:
                    vector_docs = self.db.similarity_search(query, k=per_landmark_k)
                except Exception as e:
                    logger.warning("RAG-Service: vector recall failed for [%s]; ID hits preserved: %s", name, e)
                    failures.append({"landmark_id": landmark.get("id"), "stage": "vector_recall", "code": _failure_code(e), "message": str(e)})
                    _trace_rag_failure("rag_vector_recall", e)
            else:
                failures.append({"landmark_id": landmark.get("id"), "stage": "vector_recall", "code": "EMBEDDING_CONFIG_UNVERIFIED", "message": "向量配置未核实，已跳过向量查询"})
            raw_docs = []
            raw_seen_keys = set()
            for doc in direct_docs + vector_docs:
                dedup_key = self._doc_dedup_key(doc)
                if dedup_key in raw_seen_keys:
                    continue
                raw_docs.append(doc)
                raw_seen_keys.add(dedup_key)

            if not raw_docs:
                missing_landmarks.append(landmark)
                recall_details.append({
                    "landmark_id": landmark.get("id"),
                    "landmark_name": name,
                    "query": query,
                    "recalled_count": 0,
                    "selected_count": 0,
                })
                continue

            try:
                scored_docs = self.reranker.rerank_with_scores(query, raw_docs)
            except Exception as e:
                logger.warning("RAG-Service: rerank failed for [%s]; original recall order preserved: %s", name, e)
                failures.append({"landmark_id": landmark.get("id"), "stage": "rerank", "code": _failure_code(e), "message": str(e)})
                _trace_rag_failure("rag_rerank", e)
                scored_docs = [(index, -1.0, doc) for index, doc in enumerate(raw_docs)]
            candidates = []
            local_seen_keys = set()
            relevant_count = 0
            for _, score, doc in scored_docs:
                if not self._is_doc_relevant_to_landmark(landmark, doc, score):
                    continue
                relevant_count += 1
                dedup_key = self._doc_dedup_key(doc)
                if dedup_key in local_seen_keys:
                    continue
                candidates.append({"score": score, "doc": doc, "dedup_key": dedup_key})
                local_seen_keys.add(dedup_key)
                if len(candidates) >= per_landmark_limit:
                    break

            if candidates:
                candidate_groups.append({
                    "landmark": landmark,
                    "name": name,
                    "docs": [],
                    "candidates": candidates,
                    "relevant_count": relevant_count,
                })
            else:
                missing_landmarks.append(landmark)

            recall_details.append({
                "landmark_id": landmark.get("id"),
                "landmark_name": name,
                "query": query,
                "recalled_count": len(raw_docs),
                "candidate_count": len(candidates),
                "relevant_count": relevant_count,
            })

        seen_doc_keys = set()
        total_selected = 0

        # First pass: guarantee every hit landmark has at least one injected chunk.
        for group in candidate_groups:
            for candidate in group["candidates"]:
                dedup_key = candidate["dedup_key"]
                if dedup_key in seen_doc_keys:
                    continue
                group["docs"].append({"score": candidate["score"], "doc": candidate["doc"]})
                seen_doc_keys.add(dedup_key)
                total_selected += 1
                break

        # Extra passes: add second/third chunks only while staying within the global budget.
        for desired_count in range(2, per_landmark_limit + 1):
            if total_selected >= global_limit:
                break
            for group in candidate_groups:
                if total_selected >= global_limit:
                    break
                if len(group["docs"]) >= desired_count:
                    continue
                for candidate in group["candidates"]:
                    dedup_key = candidate["dedup_key"]
                    if dedup_key in seen_doc_keys:
                        continue
                    group["docs"].append({"score": candidate["score"], "doc": candidate["doc"]})
                    seen_doc_keys.add(dedup_key)
                    total_selected += 1
                    break

        grouped_docs = []
        hit_landmarks = []
        for group in candidate_groups:
            if not group["docs"]:
                missing_landmarks.append(group["landmark"])
                continue
            grouped_docs.append({"landmark": group["landmark"], "docs": group["docs"]})
            hit_landmarks.append({
                "id": group["landmark"].get("id"),
                "name": group["name"],
                "chunks_count": len(group["docs"]),
                "relevant_count": group["relevant_count"],
            })

        detail_by_id = {
            item.get("landmark_id"): item
            for item in recall_details
            if item.get("landmark_id")
        }
        for group in candidate_groups:
            detail = detail_by_id.get(group["landmark"].get("id"))
            if detail is not None:
                detail["selected_count"] = len(group["docs"])

        context = self._format_landmark_context(grouped_docs)
        source_records = []
        landmark_context = {}
        for group in grouped_docs:
            point_id = self._clean_text_value(group["landmark"].get("id"))
            chunks = []
            for selected in group["docs"]:
                doc = selected["doc"]
                source = self._source_from_doc(doc, point_id)
                source_records.append(source)
                chunks.append({
                    "text": doc.page_content,
                    "source_id": source["source_id"],
                    "review_status": source["review_status"],
                })
            landmark_context[point_id] = {
                "context": self._format_landmark_context([group]),
                "chunks": chunks,
                "source_ids": list(dict.fromkeys(item["source_id"] for item in chunks)),
            }
        sources = self._merge_source_records(source_records)
        log_rag_event("multi_recall", {
            "landmarks_count": len(landmarks),
            "hit_count": len(hit_landmarks),
            "missing_count": len(missing_landmarks),
            "selected_chunks_count": total_selected,
            "details": recall_details,
            "final_context": context,
            "failures": failures,
        })
        logger.info(
            "RAG-Service: multi-route recall complete. hits=%s missing=%s selected_chunks=%s",
            len(hit_landmarks),
            len(missing_landmarks),
            total_selected,
        )
        return {
            "context": context,
            "hit_landmarks": hit_landmarks,
            "missing_landmarks": missing_landmarks,
            "sources": sources,
            "landmark_context": landmark_context,
            "failures": failures,
            "status": "failed" if failures and not hit_landmarks else ("partial" if failures or missing_landmarks else "success"),
        }

    def _search_single_landmark(
        self,
        name: str,
        bangumi: str,
        original_name: str = "",
        bangumi_original_name: str = "",
        should_cancel: Optional[Callable[[], bool]] = None,
        deadline: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        联网搜索单个地标的长效攻略、圣地巡礼剧情以及交通状况，自动规避天气等易变词汇。
        包含智能防噪与内容过滤机制，拒绝 Git Diff 页面、不相关技术博客及 SEO 垃圾网页。
        """
        is_cancelled = lambda: bool(should_cancel and should_cancel())
        if is_cancelled():
            return {"text": "", "pages": [], "failures": [{"code": "RUN_CANCELLED", "message": "检索已取消"}]}
        web_deadline = min(deadline if deadline is not None else float("inf"), time.monotonic() + _positive_float_env("RAG_WEB_TIMEOUT_SECONDS", 30))
        tavily_deadline = min(web_deadline, time.monotonic() + _positive_float_env("RAG_TAVILY_PHASE_TIMEOUT_SECONDS", 12))
        stopped = lambda: is_cancelled() or time.monotonic() >= web_deadline
        tavily_stopped = lambda: is_cancelled() or time.monotonic() >= tavily_deadline
        
        # 严格限制在“长效背景知识”领域，规避瞬时信息；核心 query 先跑，站点 query 仅在召回不足时补充。
        core_queries = []
        site_queries = []
        # 仅当提供了真实的日文原名时才构造日文 query，避免把中文名塞进日文模板生成伪日文 query。
        has_jp_name = bool(original_name) or bool(bangumi_original_name)
        jp_name = original_name or name
        jp_bangumi = bangumi_original_name or bangumi
        if bangumi and bangumi != "未知":
            core_queries.extend([
                ("中文精确", f"动漫《{bangumi}》 圣地巡礼 {name} 还原 剧情 交通 攻略"),
                ("中文宽松", f"{bangumi} {name} 圣地巡礼 攻略 交通 拍照机位"),
                ("地点优先", f"{name} {bangumi} 巡礼 舞台 取景地 打卡"),
                ("英文", f"{bangumi} {name} anime pilgrimage scene location guide"),
            ])
            if has_jp_name:
                if jp_bangumi and jp_bangumi != "未知":
                    core_queries.append(("日文", f"アニメ『{jp_bangumi}』 聖地巡礼 {jp_name} 舞台探訪 場面 アクセス"))
                else:
                    core_queries.append(("日文", f"聖地巡礼 {jp_name} 舞台 写真スポット 交通 攻略"))
        else:
            core_queries.extend([
                ("中文", f"圣地巡礼 {name} 经典拍摄角度 交通 旅游攻略"),
            ])
            if has_jp_name:
                core_queries.append(("日文", f"{jp_name} 聖地巡礼 舞台探訪 写真スポット アクセス"))

        if bangumi and bangumi != "未知":
            site_base = f"{bangumi} {name} 圣地巡礼 攻略"
            jp_site_base = f"{jp_bangumi or bangumi} {jp_name} 聖地巡礼 舞台探訪"
            for label, site_filter in ANIME_SCENE_SITE_QUERIES:
                if "ameblo.jp" in site_filter or "livedoor.jp" in site_filter:
                    if has_jp_name:
                        site_queries.append((label, f"{site_filter} {jp_site_base}"))
                else:
                    site_queries.append((label, f"{site_filter} {site_base}"))

        def dedupe_queries(queries):
            seen_queries = set()
            deduped_queries = []
            for label, query in queries:
                key = " ".join(query.split()).lower()
                if not key or key in seen_queries:
                    continue
                seen_queries.add(key)
                deduped_queries.append((label, query))
            return deduped_queries

        core_queries = dedupe_queries(core_queries)
        site_queries = dedupe_queries(site_queries)
        # 站点 fallback 使用独立预算 RAG_TAVILY_SITE_QUERIES，避免被核心 query 预算挤占导致只剩 1 条。
        max_queries = parse_int_env("RAG_TAVILY_MAX_QUERIES", 8)
        core_limit = parse_int_env("RAG_TAVILY_CORE_QUERIES", 4, max_value=max_queries)
        site_limit = parse_int_env("RAG_TAVILY_SITE_QUERIES", 3)
        min_results = parse_int_env("RAG_TAVILY_MIN_RESULTS", 3)
        search_depth = os.getenv("RAG_TAVILY_SEARCH_DEPTH", "basic")
        queries = core_queries[:core_limit]

        search_failures = []
        routes = []

        def search_with_retry(query: str) -> Dict[str, Any]:
            attempts = min(parse_int_env("TAVILY_MAX_RETRIES", 1, min_value=0), 2) + 1
            for attempt in range(attempts):
                if tavily_stopped():
                    return {}
                try:
                    return self.tavily_client.search(
                        query=query,
                        **get_tavily_search_kwargs(
                            search_depth=search_depth,
                            max_results=5,
                            include_raw_content=include_raw_content_enabled("RAG_TAVILY_INCLUDE_RAW_CONTENT", "1"),
                        ),
                    )
                except Exception as exc:
                    transient = "timeout" in type(exc).__name__.lower() or "connection" in type(exc).__name__.lower()
                    if not transient or attempt + 1 >= attempts:
                        raise
                    time.sleep(0.2 * (attempt + 1))
            return {}

        def run_tavily_queries(query_batch: List[Tuple[str, str]]) -> List[Tuple[str, Dict[str, Any]]]:
            if not query_batch or tavily_stopped():
                return []

            responses = []
            tasks = [(label, search_with_retry, (query,)) for label, query in query_batch]
            completed = 0
            for label, response, error in run_search_tasks(tasks, tavily_stopped):
                completed += 1
                if error is None and (not isinstance(response, dict) or not isinstance(response.get("results"), list)):
                    error = ValueError("Tavily 未返回有效的 results 数组")
                if error:
                    logger.warning(f"RAG-Service: {label}检索失败 [{name}]: {error}")
                    search_failures.append({"code": _failure_code(error), "message": str(error), "stage": f"tavily/{label}"})
                    _trace_rag_failure("rag_web_search", error)
                else:
                    responses.append((f"Tavily/{label}", response))
            if completed < len(tasks) and not is_cancelled():
                search_failures.append({"code": "TOOL_TIMEOUT", "message": "Tavily 阶段时间预算已到，尝试备用搜索", "stage": "tavily"})
            return responses

        contents = []
        pages = []
        seen_urls = set()
        domain_policy = get_tavily_search_kwargs()

        def append_useful_results(responses: List[Tuple[str, Dict[str, Any]]]) -> None:
            for label, response in responses:
                for item in response.get("results", []):
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "")
                    url = scene_tools.normalize_search_url(item.get("url", ""))
                    content = result_content_with_raw(item)

                    if not url or not content.strip() or url in seen_urls:
                        continue
                    domain = (urlparse(url).hostname or "").lower()
                    allowed = domain_policy.get("include_domains", [])
                    denied = domain_policy.get("exclude_domains", [])
                    if allowed and not any(domain_matches(domain, value) for value in allowed):
                        continue
                    if any(domain_matches(domain, value) for value in denied):
                        continue

                    # 1. 过滤明显的文件/代码提交页面噪声（如 Hugging Face, GitHub Commits/Diffs 等）
                    url_lower = url.lower()
                    blacklist_patterns = [
                        ".diff", ".patch", ".csv", ".xlsx", ".json", ".xml", ".txt",
                        "/commit/", "/raw/", "/blob/", "huggingface.co/datasets", "github.com/commits"
                    ]
                    if any(pat in url_lower for pat in blacklist_patterns):
                        logger.info(f"RAG-Service: 已跳过匹配黑名单 URL 的噪点网页: {url}")
                        continue
                    
                    # 2. 过滤网页内容是 Git Diff 或代码结构的内容
                    content_lower = content.lower()
                    if "diff --git" in content_lower or "index " in content_lower or "+++ b/" in content_lower:
                        logger.info(f"RAG-Service: 已跳过内容包含 Git Diff 的噪点网页: {url}")
                        continue
                        
                    # 3. 过滤 SEO 垃圾广告或与动漫/地标/旅游完全不相关的噪音网页。
                    # 已知作品时，不能只凭通用地点名放行，否则京都站/新宿站等常见地标会混入普通页面。
                    keywords = [kw.lower() for kw in (name, original_name) if kw]
                    if bangumi and bangumi != "未知":
                        keywords.append(bangumi.lower())
                    if bangumi_original_name and bangumi_original_name != "未知":
                        keywords.append(bangumi_original_name.lower())

                    # 复用 tools.py 的共享旅游关键词，保证两条检索路径过滤口径一致。
                    travel_keywords = [kw.lower() for kw in ANIME_SCENE_TRAVEL_KEYWORDS]

                    title_lower = title.lower()
                    name_keywords = [kw.lower() for kw in (name, original_name) if kw]
                    bangumi_keywords = [
                        kw.lower()
                        for kw in (bangumi, bangumi_original_name)
                        if kw and kw != "未知"
                    ]
                    has_name_kw = any(kw in content_lower or kw in title_lower for kw in name_keywords)
                    has_bangumi_kw = any(kw in content_lower or kw in title_lower for kw in bangumi_keywords)
                    has_core_kw = any(kw in content_lower or kw in title_lower for kw in keywords)
                    has_travel_kw = any(tkw in content_lower or tkw in title_lower for tkw in travel_keywords)

                    if bangumi and bangumi != "未知":
                        is_useful = (
                            (has_name_kw and has_travel_kw)
                            or (has_name_kw and has_bangumi_kw)
                            or (has_bangumi_kw and has_travel_kw)
                        )
                    else:
                        is_useful = has_core_kw or has_travel_kw

                    if not is_useful:
                        missing = []
                        if not has_name_kw:
                            missing.append("地点名")
                        if not has_bangumi_kw:
                            missing.append("作品名")
                        if not has_travel_kw:
                            missing.append("旅游关键词")
                        logger.info(
                            f"RAG-Service: 已过滤不具备动漫/地标/旅游相关性的垃圾网页: {url} "
                            f"(缺失: {'/'.join(missing)})"
                        )
                        continue

                    clean_url = url if _is_http_url(url) else ""
                    seen_urls.add(url)
                    pages.append({"title": title, "url": clean_url, "content": content, "retrieved_at": _retrieved_at()})
                    contents.append(f"【{label}来源网页: {title} ({clean_url or '来源缺失'})】\n{content}\n")

        try:
            include_domains = get_tavily_include_domains()
            logger.info(
                "RAG-Service: 正在对地标 [%s] 进行长效背景知识检索... 查询词: %s；白名单站点: %s",
                name,
                " | ".join([f"{label}: {query}" for label, query in queries]),
                ", ".join(include_domains) if include_domains else "未限制",
            )
            responses = []
            if self.tavily_client and not tavily_stopped():
                routes.append("tavily")
                _trace_search_route("tavily", name, trigger="primary")
                responses = run_tavily_queries(queries)
                append_useful_results(responses)
            elif not self.tavily_client:
                search_failures.append({"code": "TOOL_UNCONFIGURED", "message": "TAVILY_API_KEY 未配置，尝试直接搜索兜底", "stage": "tavily"})
                _trace_search_route("tavily", name, skipped=True)

            if responses and not tavily_stopped() and len(contents) < min_results and site_queries:
                fallback_queries = site_queries[:min(site_limit, max(0, max_queries - len(queries)))]
                logger.info(
                    "RAG-Service: 地标 [%s] 核心检索仅命中 %s 条，追加站点定向检索: %s",
                    name,
                    len(contents),
                    " | ".join([f"{label}: {query}" for label, query in fallback_queries]),
                )
                _trace_search_route("tavily", name, trigger="site_supplement", existing_sources=len(pages))
                append_useful_results(run_tavily_queries(fallback_queries))

            if "tavily" in routes:
                _trace_search_route("tavily", name, new_sources=len(pages), total_sources=len(pages), enough=len(pages) >= min_results)

            direct_enabled = os.getenv("RAG_ENABLE_DIRECT_FALLBACK", "1").strip().lower() not in {"0", "false", "no", "off"}
            if direct_enabled and len(pages) < min_results and not stopped():
                engine_names = list(dict.fromkeys(
                    value.strip().lower() for value in os.getenv("RAG_DIRECT_SEARCH_ENGINES", "baidu,bing,ddg").split(",")
                    if value.strip().lower() in {"baidu", "bing", "ddg"}
                )) or ["baidu", "bing", "ddg"]
                # Reserve a Japanese query when real Japanese aliases are available.
                pool = core_queries[:1] + [entry for entry in core_queries if entry[0] == "日文"] + core_queries[1:]
                direct_queries = dedupe_queries(pool)[:parse_int_env("RAG_DIRECT_MAX_QUERIES", 2, max_value=4)]
                terms = list(dict.fromkeys(filter(None, [name, original_name, bangumi, bangumi_original_name])))
                for index, engine in enumerate(engine_names):
                    if stopped() or len(pages) >= min_results:
                        break
                    routes.append(engine)
                    trigger = "supplement" if pages else "fallback"
                    _trace_search_route(engine, name, trigger=trigger, existing_sources=len(pages))
                    # Leave a share of the remaining budget for each later engine.
                    remaining = web_deadline - time.monotonic()
                    engine_deadline = time.monotonic() + remaining / (len(engine_names) - index)
                    engine_stopped = lambda stop_at=engine_deadline: stopped() or time.monotonic() >= stop_at
                    before = len(pages)
                    try:
                        results, query_errors = scene_tools.search_scene_pages(
                            direct_queries, terms, engine, should_cancel=engine_stopped,
                            exclude_urls=set(seen_urls),
                            max_pages=parse_int_env("RAG_DIRECT_MAX_PAGES", 2, max_value=5),
                        )
                        append_useful_results([(engine, {"results": results})])
                        for label, message in query_errors:
                            code = next((code for code in ("TOOL_TIMEOUT", "TOOL_UNAVAILABLE") if code in str(message)), "TOOL_ERROR")
                            search_failures.append({"code": code, "message": str(message), "stage": f"{engine}/{label}"})
                        if engine_stopped() and not is_cancelled():
                            search_failures.append({"code": "TOOL_TIMEOUT", "message": f"{engine} 搜索时间预算已到", "stage": engine})
                    except Exception as exc:
                        search_failures.append({"code": _failure_code(exc), "message": str(exc), "stage": engine})
                        _trace_rag_failure(f"rag_web_search/{engine}", exc)
                    _trace_search_route(engine, name, new_sources=len(pages) - before, total_sources=len(pages), enough=len(pages) >= min_results)

            if is_cancelled():
                return {"text": "", "pages": [], "failures": search_failures + [{"code": "RUN_CANCELLED", "message": "检索已取消"}]}
            if time.monotonic() >= web_deadline:
                search_failures.append({"code": "TOOL_TIMEOUT", "message": "联网检索总时间预算已到，保留已取得的资料", "stage": "web_search"})
            return {"text": "\n".join(contents), "pages": pages, "failures": search_failures, "routes": routes}
        except Exception as e:
            logger.error(f"RAG-Service: 地标 [{name}] 检索失败，细节: {e}")
            return {"text": "", "pages": [], "failures": search_failures + [{"code": "TOOL_ERROR", "message": str(e)}]}

    def ingest_landmarks(
        self, landmarks: List[Dict[str, Any]],
        should_cancel: Optional[Callable[[], bool]] = None,
        deadline: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        并发检索缺失的地标信息，递归切片并暂存至待审核队列（不直接写入 ChromaDB）。
        返回暂存状态信息和本次新检索文本，供前端展示审核提示，并供当前生成链路临时使用。
        """
        is_cancelled = lambda: bool(should_cancel and should_cancel())
        web_deadline = min(deadline if deadline is not None else float("inf"), time.monotonic() + _positive_float_env("RAG_WEB_TIMEOUT_SECONDS", 30))
        stopped = lambda: is_cancelled() or time.monotonic() >= web_deadline
        empty_result = {"pending_count": 0, "pending_landmarks": [], "search_context": "", "sources": [], "landmark_context": {}}
        if is_cancelled():
            return {**empty_result, "failures": [{"code": "RUN_CANCELLED", "message": "联网补充已取消"}], "status": "cancelled"}

        # 1. 过滤出在数据库中没有缓存记录、且不在待审核队列中的地标
        to_search = []
        for lm in landmarks:
            if is_cancelled():
                return {**empty_result, "failures": [{"code": "RUN_CANCELLED", "message": "联网补充已取消"}], "status": "cancelled"}
            lm_id = lm.get("id")
            lm_name = lm.get("name")
            original_name = lm.get("originalName") or ""
            bangumi = lm.get("bangumiName")
            bangumi_original_name = lm.get("bangumiOriginalName") or ""
            
            if not lm_id or not lm_name:
                continue
                
            if self.is_landmark_indexed(lm_id):
                logger.info(f"RAG-Service: 地标 [{lm_name}] (ID: {lm_id}) 已经有本地缓存记录，跳过联网检索。")
            elif self.is_landmark_pending(lm_id):
                logger.info(f"RAG-Service: 地标 [{lm_name}] (ID: {lm_id}) 已在待审核队列中，跳过联网检索。")
            else:
                to_search.append((lm_id, lm_name, bangumi, original_name, bangumi_original_name))
                
        if not to_search:
            logger.info("RAG-Service: 所有地标均已缓存或待审核，无需进行额外联网检索。")
            return {"pending_count": 0, "pending_landmarks": [], "search_context": "", "sources": [], "landmark_context": {}, "failures": [], "status": "success"}

        # 2. 并发对需要抓取的地标进行联网检索
        results_to_stage = []
        failures = []
        try:
            import agent_trace
            run_id = agent_trace.get_current_run_id()
        except Exception:
            agent_trace = None
            run_id = None

        def search_with_trace(name, bangumi, original_name, bangumi_original_name, point_id):
            if agent_trace and run_id:
                agent_trace.attach_run(run_id)
            if is_cancelled():
                return {"text": "", "pages": [], "failures": [{"code": "RUN_CANCELLED", "message": "检索已取消"}]}
            # Leave a little time to collect the terminal partial result before the batch deadline.
            with progress.point_scope(point_id):
                return self._search_single_landmark(name, bangumi, original_name, bangumi_original_name, should_cancel, web_deadline - 0.2)

        ingest_workers = parse_int_env("RAG_INGEST_MAX_WORKERS", 3)
        tasks = [
            ((lm_id, name, bangumi), search_with_trace, (name, bangumi, original_name, bangumi_original_name, lm_id))
            for lm_id, name, bangumi, original_name, bangumi_original_name in to_search
        ]
        for (lm_id, name, bangumi), search_result, error in run_search_tasks(tasks, stopped, max_workers=ingest_workers):
            if error:
                logger.error(f"RAG-Service: 并发检索地标 [{name}] 线程跑飞: {error}")
                failures.append({"landmark_id": lm_id, "code": _failure_code(error), "message": str(error)})
                continue
            if isinstance(search_result, str):
                raw_text, pages = search_result, []
            else:
                raw_text = search_result.get("text", "")
                pages = search_result.get("pages", [])
                failures.extend({**item, "landmark_id": lm_id} for item in search_result.get("failures", []))
            if raw_text.strip():
                results_to_stage.append((lm_id, name, bangumi, raw_text, pages))
        if time.monotonic() >= web_deadline and not is_cancelled():
            failures.append({"code": "TOOL_TIMEOUT", "message": "批量联网检索时间预算已到，保留已完成的资料"})

        # 3. 递归切片并暂存至待审核队列（不直接写入 ChromaDB）
        if not results_to_stage:
            logger.warning("RAG-Service: 未获取到有效的联网检索内容，本次不进行暂存。")
            if is_cancelled():
                failures.append({"code": "RUN_CANCELLED", "message": "联网补充已取消"})
                return {**empty_result, "failures": failures, "status": "cancelled"}
            return {"pending_count": 0, "pending_landmarks": [], "search_context": "", "sources": [], "landmark_context": {}, "failures": failures, "status": "failed" if failures else "partial"}
            
        splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=60)
        pending_landmarks = []
        all_source_records = []
        landmark_context = {}
        staged_context_blocks = []
        
        for lm_id, name, bangumi, text, pages in results_to_stage:
            if is_cancelled():
                failures.append({"code": "RUN_CANCELLED", "message": "联网补充已取消"})
                break
            if not pages:
                # 兼容旧的纯文本搜索返回值；出处无法可靠恢复时明确标注缺失。
                pages = [{"title": "来源缺失", "url": "", "content": text, "retrieved_at": ""}]
            chunks = []
            chunk_metadata = []
            source_records = []
            for page in pages:
                content = str(page.get("content") or "").strip()
                if not content:
                    continue
                url = str(page.get("url") or "").strip()
                if not _is_http_url(url):
                    url = ""
                title = str(page.get("title") or ("网页资料" if url else "来源缺失"))
                source_id = _source_id(url) if url else "missing_" + hashlib.sha256(
                    f"{lm_id}:{title}:{content}".encode("utf-8")
                ).hexdigest()[:20]
                status = "unreviewed" if url else "missing"
                source = {
                    "source_id": source_id, "url": url, "title": title,
                    "retrieved_at": str(page.get("retrieved_at") or ""),
                    "review_status": status, "point_ids": [lm_id],
                }
                source_records.append(source)
                for chunk in splitter.split_text(content):
                    chunks.append(chunk)
                    chunk_metadata.append({key: source[key] for key in ("source_id", "url", "title", "retrieved_at", "review_status")})
            logger.info(f"RAG-Service: 地标 [{name}] 联网文本提取完毕，递归切割为 {len(chunks)} 个文本块，已加入待审核队列。")
            if not chunks:
                continue
            if is_cancelled():
                failures.append({"code": "RUN_CANCELLED", "message": "联网补充已取消"})
                break
            self.add_to_pending(
                lm_id, name, bangumi or "未知", text, chunks,
                [source["url"] for source in source_records if source["url"]],
                chunk_metadata=chunk_metadata,
                source_records=source_records,
            )
            progress.activity("retrieve", f"sources:{lm_id}", f"整理来源 · {name}",
                              f"已保留 {len(source_records)} 条参考来源，新增资料已标记为待审核")
            pending_landmarks.append({"id": lm_id, "name": name, "chunks_count": len(chunks)})
            staged_context_blocks.append(f"### {name} / {bangumi or '未知'}\n{text}")
            all_source_records.extend(source_records)
            landmark_context[lm_id] = {
                "context": f"### {name} / {bangumi or '未知'}\n{text}",
                "chunks": [
                    {"text": chunk, "source_id": meta["source_id"], "review_status": meta["review_status"]}
                    for chunk, meta in zip(chunks, chunk_metadata)
                ],
                "source_ids": list(dict.fromkeys(meta["source_id"] for meta in chunk_metadata)),
            }
            
        search_context = "\n\n".join(staged_context_blocks)
        return {
            "pending_count": len(pending_landmarks),
            "pending_landmarks": pending_landmarks,
            "search_context": search_context,
            "sources": self._merge_source_records(all_source_records),
            "landmark_context": landmark_context,
            "failures": failures,
            "status": "cancelled" if any(item.get("code") == "RUN_CANCELLED" for item in failures)
            else ("partial" if failures or len(pending_landmarks) < len(to_search) else "success"),
        }

    def query_rag_context(self, query: str, k: int = 6) -> str:
        """
        向量检索 (Recall K=6) -> 重排评分 (Rerank) -> 过滤保留 Top 3。
        输出格式化好的 Context 字符串供大模型规划路线。
        """
        if not self.vector_enabled:
            logger.warning("RAG-Service: embedding 配置未核实，跳过全局向量检索；可改用按地标 ID 查询。")
            return ""
        try:
            # 1. 向量相似度粗回 Top K
            raw_docs = self.db.similarity_search(query, k=k)
            if not raw_docs:
                logger.info("RAG-Service: Chroma 向量检索未召回任何相关背景文档。")
                log_rag_event("recall", {
                    "query": query,
                    "recalled_count": 0,
                    "reranked_top_3": [],
                    "final_context": ""
                })
                return ""
            
            logger.info(f"RAG-Service: Chroma 向量库粗回完成，召回 {len(raw_docs)} 条候选背景文档。")

            # 2. 借助大模型 Logits 概率精排过滤
            scored_docs = self.reranker.rerank_with_scores(query, raw_docs)
            
            # 3. 提取排名前 3 的最优上下文 (分数为 -1.0 表示精排被降级，但原先的相似度序依然有效)
            top_n = scored_docs[:3]
            
            context_blocks = []
            reranked_top_3_details = []
            logger.info("RAG-Service: RAG 召回与重排结果如下：")
            for idx, (original_idx, score, doc) in enumerate(top_n):
                name = doc.metadata.get("landmark_name", "未知")
                bgm = doc.metadata.get("bangumi", "未知")
                logger.info(f"  [Top {idx+1}] 地标: {name} | 评分: {score} | 原属作品: {bgm}")
                
                context_block = (
                    f"【参考地标: {name} (涉及作品:《{bgm}》)】\n"
                    f"{doc.page_content.strip()}"
                )
                context_blocks.append(context_block)
                
                reranked_top_3_details.append({
                    "rank": idx + 1,
                    "score": score,
                    "landmark_name": name,
                    "bangumi": bgm,
                    "content": doc.page_content,
                    "source": doc.metadata.get("source", "未知")
                })
                
            final_context = "\n\n".join(context_blocks)
            
            log_rag_event("recall", {
                "query": query,
                "recalled_count": len(raw_docs),
                "reranked_top_3": reranked_top_3_details,
                "final_context": final_context
            })
            
            return final_context
        except Exception as e:
            logger.error(f"RAG-Service: 执行 RAG 查询/精排出错: {e}")
            log_rag_event("recall", {
                "query": query,
                "error": str(e)
            })
            return ""
    def clear_database(self) -> bool:
        """
        清空向量数据库中的 collection，并重新初始化它。
        """
        try:
            self.db.delete_collection()
            self.db = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=self.embeddings,
                persist_directory=self.db_dir,
                collection_metadata=self.embedding_config,
            )
            self.vector_enabled = self._embedding_binding_verified()
            logger.info("RAG-Service: Chroma 向量数据库已成功清空并且重新初始化。")
            return True
        except Exception as e:
            logger.error(f"RAG-Service: 清空数据库失败: {e}")
            raise e

# 单例模式
rag_service = RAGService()
