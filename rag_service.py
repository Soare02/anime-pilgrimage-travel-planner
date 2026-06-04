import os
import math
import logging
import requests
import json
import datetime
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# LangChain components
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_community.vectorstores import Chroma
from openai import OpenAI
from tavily import TavilyClient

# Version-safe import for RecursiveCharacterTextSplitter
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger("rag_service")
logging.basicConfig(level=logging.INFO)

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_history.json")
PENDING_FILE = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_pending.json")

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
        
        event = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
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
    自适应向量提取器：
    优先尝试连接本地 LM Studio 兼容 OpenAI 的端点；
    如果失败，则平滑切换到 Chroma 内建的本地 CPU ONNXMiniLM 嵌入函数，避免系统崩溃。
    """
    def __init__(self, model: str = "text-embedding-qwen3-embedding-0.6b", base_url: str = None):
        self.model = model
        self.base_url = base_url or os.getenv("EMBEDDING_BASE_URL", "http://localhost:1234/v1")
        self.client = OpenAI(base_url=self.base_url, api_key="lm-studio")
        self._local_embedding_fn = None

    def _get_local_embedding_fn(self):
        if self._local_embedding_fn is None:
            try:
                import chromadb.utils.embedding_functions as ef
                # 默认本地 CPU 极速嵌入模型 (onnx-mini-lm)
                self._local_embedding_fn = ef.ONNXMiniLM_L6_V2()
                logger.info("RAG-Embeddings: 已成功加载 Chroma 本地 ONNX MiniLM 嵌入函数作为备用")
            except Exception as e:
                logger.warning(f"RAG-Embeddings: 无法加载 ONNX MiniLM, 尝试 fallback 到 HuggingFaceEmbeddings: {e}")
                try:
                    from langchain_community.embeddings import HuggingFaceEmbeddings
                    self._local_embedding_fn = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
                except Exception as ex:
                    logger.error(f"RAG-Embeddings: 所有本地 CPU 备用嵌入全部加载失败！ {ex}")
                    raise ex
        return self._local_embedding_fn

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        try:
            # 尝试连接 LM Studio
            response = self.client.embeddings.create(input=texts, model=self.model, timeout=5)
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.warning(f"RAG-Embeddings: 无法调用 LM Studio 嵌入 API ({e})，正在切换到本地 CPU 极速嵌入...")
            fn = self._get_local_embedding_fn()
            if hasattr(fn, "__call__"):
                # chromadb 的 ONNX 嵌入函数接收 List[str] 并返回 List[List[float]] 列表
                return fn(texts)
            return fn.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        try:
            response = self.client.embeddings.create(input=text, model=self.model, timeout=5)
            return response.data[0].embedding
        except Exception as e:
            logger.warning(f"RAG-Embeddings: 无法调用 LM Studio 嵌入 API ({e})，正在切换到本地 CPU 极速嵌入...")
            fn = self._get_local_embedding_fn()
            if hasattr(fn, "__call__"):
                return fn([text])[0]
            return fn.embed_query(text)


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
        self.db = Chroma(
            collection_name="anime_pilgrimage",
            embedding_function=self.embeddings,
            persist_directory=self.db_dir
        )
        self.reranker = LMStudioReranker()
        
        # 初始化 Tavily 客户端
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily_client = TavilyClient(api_key=tavily_key) if tavily_key else None
        if not self.tavily_client:
            logger.warning("RAG-Service: 未配置 TAVILY_API_KEY，联网预检索功能将无法正常抓取网页。")

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

    def add_to_pending(self, landmark_id: str, name: str, bangumi: str, raw_text: str, chunks: List[str], sources: List[str]):
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
            "sources": sources
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

        documents_to_add = []
        for i, chunk in enumerate(chunks_to_write):
            doc = Document(
                page_content=chunk,
                metadata={
                    "landmark_id": target["landmark_id"],
                    "landmark_name": target["landmark_name"],
                    "bangumi": target.get("bangumi", "未知"),
                    "chunk_id": i,
                    "source": "tavily_search"
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

    def _search_single_landmark(self, name: str, bangumi: str) -> str:
        """
        联网搜索单个地标的长效攻略、圣地巡礼剧情以及交通状况，自动规避天气等易变词汇。
        包含智能防噪与内容过滤机制，拒绝 Git Diff 页面、不相关技术博客及 SEO 垃圾网页。
        """
        if not self.tavily_client:
            return ""
        
        # 严格限制在“长效背景知识”领域，规避瞬时信息
        if bangumi and bangumi != "未知":
            query = f"动漫《{bangumi}》 圣地巡礼 {name} 还原 剧情 交通 攻略"
        else:
            query = f"圣地巡礼 {name} 经典拍摄角度 交通 旅游攻略"
            
        try:
            logger.info(f"RAG-Service: 正在对地标 [{name}] 进行长效背景知识检索... 查询词: {query}")
            response = self.tavily_client.search(query=query, search_depth="basic", max_results=5)
            
            contents = []
            for item in response.get("results", []):
                title = item.get("title", "")
                url = item.get("url", "")
                content = item.get("content", "")
                
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
                    
                # 3. 过滤 SEO 垃圾广告或与动漫/地标/旅游完全不相关的噪音网页
                # 必须包含地标/动漫名之一，或者包含基本的旅游/圣地巡礼关键词
                keywords = [name.lower()]
                if bangumi and bangumi != "未知":
                    keywords.append(bangumi.lower())
                
                travel_keywords = ["巡礼", "圣地", "动漫", "打卡", "交通", "攻略", "站", "拍摄", "anime", "pilgrimage", "scene", "station", "route"]
                
                has_core_kw = any(kw in content_lower or kw in title.lower() for kw in keywords)
                has_travel_kw = any(tkw in content_lower or tkw in title.lower() for tkw in travel_keywords)
                
                if not has_core_kw and not has_travel_kw:
                    logger.info(f"RAG-Service: 已过滤不具备动漫/地标/旅游相关性的垃圾网页: {url}")
                    continue
                
                contents.append(f"【来源网页: {title} ({url})】\n{content}\n")
                
            return "\n".join(contents)
        except Exception as e:
            logger.error(f"RAG-Service: 地标 [{name}] 检索失败，细节: {e}")
            return ""

    def ingest_landmarks(self, landmarks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        并发检索缺失的地标信息，递归切片并暂存至待审核队列（不直接写入 ChromaDB）。
        返回暂存状态信息，供前端展示审核提示。
        """
        # 1. 过滤出在数据库中没有缓存记录、且不在待审核队列中的地标
        to_search = []
        for lm in landmarks:
            lm_id = lm.get("id")
            lm_name = lm.get("name")
            bangumi = lm.get("bangumiName")
            
            if not lm_id or not lm_name:
                continue
                
            if self.is_landmark_indexed(lm_id):
                logger.info(f"RAG-Service: 地标 [{lm_name}] (ID: {lm_id}) 已经有本地缓存记录，跳过联网检索。")
            elif self.is_landmark_pending(lm_id):
                logger.info(f"RAG-Service: 地标 [{lm_name}] (ID: {lm_id}) 已在待审核队列中，跳过联网检索。")
            else:
                to_search.append((lm_id, lm_name, bangumi))
                
        if not to_search:
            logger.info("RAG-Service: 所有地标均已缓存或待审核，无需进行额外联网检索。")
            return {"pending_count": 0, "pending_landmarks": []}

        # 2. 并发对需要抓取的地标进行联网检索
        results_to_stage = []
        with ThreadPoolExecutor(max_workers=min(len(to_search), 5)) as executor:
            future_to_lm = {
                executor.submit(self._search_single_landmark, name, bangumi): (lm_id, name, bangumi)
                for lm_id, name, bangumi in to_search
            }
            
            for future in as_completed(future_to_lm):
                lm_id, name, bangumi = future_to_lm[future]
                try:
                    raw_text = future.result()
                    if raw_text.strip():
                        results_to_stage.append((lm_id, name, bangumi, raw_text))
                except Exception as exc:
                    logger.error(f"RAG-Service: 并发检索地标 [{name}] 线程跑飞: {exc}")

        # 3. 递归切片并暂存至待审核队列（不直接写入 ChromaDB）
        if not results_to_stage:
            logger.warning("RAG-Service: 未获取到有效的联网检索内容，本次不进行暂存。")
            return {"pending_count": 0, "pending_landmarks": []}
            
        splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=60)
        pending_landmarks = []
        
        for lm_id, name, bangumi, text in results_to_stage:
            chunks = splitter.split_text(text)
            logger.info(f"RAG-Service: 地标 [{name}] 联网文本提取完毕，递归切割为 {len(chunks)} 个文本块，已加入待审核队列。")
            
            # 提取来源 URL
            sources = []
            for line in text.split("\n"):
                if line.startswith("【来源网页:") and "(" in line and ")" in line:
                    url_start = line.rfind("(")
                    url_end = line.rfind(")")
                    if url_start < url_end:
                        sources.append(line[url_start+1:url_end])
            
            self.add_to_pending(lm_id, name, bangumi or "未知", text, chunks, sources)
            pending_landmarks.append({"id": lm_id, "name": name, "chunks_count": len(chunks)})

        return {"pending_count": len(pending_landmarks), "pending_landmarks": pending_landmarks}

    def query_rag_context(self, query: str, k: int = 6) -> str:
        """
        向量检索 (Recall K=6) -> 重排评分 (Rerank) -> 过滤保留 Top 3。
        输出格式化好的 Context 字符串供大模型规划路线。
        """
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
                collection_name="anime_pilgrimage",
                embedding_function=self.embeddings,
                persist_directory=self.db_dir
            )
            logger.info("RAG-Service: Chroma 向量数据库已成功清空并且重新初始化。")
            return True
        except Exception as e:
            logger.error(f"RAG-Service: 清空数据库失败: {e}")
            raise e

# 单例模式
rag_service = RAGService()
