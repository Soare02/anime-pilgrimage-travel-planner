import os
import traceback
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional
from agent import agent
from rag_service import rag_service
import agent_trace

app = FastAPI(title="Anime Pilgrimage Travel Planner Agent Server")

# P2: 限制 CORS 为前端确切来源（Vite 代理）/ P3: localhost 个人工具无需额外鉴权
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Landmark(BaseModel):
    id: str
    name: str
    originalName: Optional[str] = None
    bangumiName: Optional[str] = None
    bangumiOriginalName: Optional[str] = None
    ep: Optional[str] = None
    s: Optional[float] = None
    geo: Optional[List[float]] = None
    image: Optional[str] = None

    @field_validator('ep', mode='before')
    @classmethod
    def coerce_ep(cls, v):
        return str(v) if v is not None else None

class PlanRequest(BaseModel):
    days: int
    landmarks: List[Landmark]

class ApproveRequest(BaseModel):
    id: str
    chunks: Optional[List[str]] = None

class RejectRequest(BaseModel):
    id: str


def format_timestamp(seconds: float) -> str:
    if seconds is None:
        return ""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

@app.post("/api/agent/plan")
def plan_route_endpoint(req: PlanRequest):
    try:
        # 1. 提取地标信息，准备 RAG 查询与必要的联网补全
        landmarks_data = []
        for lm in req.landmarks:
            landmarks_data.append({
                "id": lm.id,
                "name": lm.name,
                "originalName": lm.originalName or "",
                "bangumiName": lm.bangumiName or "未知",
                "bangumiOriginalName": lm.bangumiOriginalName or "",
                "geo": lm.geo or None
            })

        # 2. 逐地标查询已审核入库的 RAG 内容，再聚合去重
        rag_result = rag_service.query_landmarks_context(landmarks_data)
        rag_context = rag_result.get("context", "") if rag_result else ""
        missing_landmarks = rag_result.get("missing_landmarks", landmarks_data) if rag_result else landmarks_data

        # 3. 仅对 RAG 未命中的地标做 Tavily 联网补全：本次生成临时使用，同时进入 RAG 审核区
        ingest_result = rag_service.ingest_landmarks(missing_landmarks)
        pending_count = ingest_result.get("pending_count", 0) if ingest_result else 0
        tavily_context = ingest_result.get("search_context", "") if ingest_result else ""

        # 4. 格式化地标数据，拼装为 Agent 能够理解的文本 prompt
        landmark_lines = []
        for i, lm in enumerate(req.landmarks):
            parts = [f"{i + 1}. 地点名称：{lm.name or lm.originalName or '未知'}"]
            parts.append(f"   作品名称：{lm.bangumiName or '未知'}")
            if lm.originalName and lm.originalName != lm.name:
                parts.append(f"   日文地点名：{lm.originalName}")
            if lm.bangumiOriginalName and lm.bangumiOriginalName != lm.bangumiName:
                parts.append(f"   日文作品名：{lm.bangumiOriginalName}")
            if lm.ep:
                parts.append(f"   出现集数：EP{lm.ep}")
            if lm.s is not None:
                parts.append(f"   时间戳：{format_timestamp(lm.s)}")
            if lm.geo:
                parts.append(f"   坐标：{lm.geo[0]}, {lm.geo[1]}")
            if lm.image:
                parts.append(f"   截图URL：{lm.image}")
            landmark_lines.append("\n".join(parts))
        
        data_text = f"巡礼天数：{req.days}天\n\n需要访问的地标（共{len(req.landmarks)}个）：\n" + "\n\n".join(landmark_lines)

        # 注入已审核 RAG 上下文与本次 Tavily 补充上下文
        context_sections = []
        if rag_context:
            context_sections.append("### 已审核 RAG 内容\n" + rag_context)
        if tavily_context:
            context_sections.append("### 本次联网检索补充内容（待审核入库）\n" + tavily_context)

        if context_sections:
            data_text = (
                "## 检索到的巡礼背景与攻略知识 (RAG Context)\n"
                + "\n\n".join(context_sections)
                + "\n\n"
                "--------------------------------------------------\n"
                "## 用户规划任务请求\n"
                f"{data_text}"
            )

        # 5. 定义流式生成器函数
        # 使用同步生成器配合同步 endpoint，FastAPI 会自动在独立的线程池中迭代它，避免阻塞主事件循环
        # 在生成器内部启动 / 结束 trace —— 因为 agent.invoke 在 worker 线程里执行，
        # 需要把 run_id 通过 ContextVar 暴露给 agent.py 里的所有 traced 调用。
        run_id = agent_trace.start_run(
            days=req.days,
            landmark_names=[lm.name for lm in req.landmarks],
        )

        def event_generator():
            ended = False
            try:
                # 把 run_id 重新 attach 到这个生成器迭代线程（FastAPI 在线程池里跑同步生成器）
                agent_trace.attach_run(run_id)
                stream_result = agent.stream(
                    {"messages": [{"role": "user", "content": data_text}]},
                    config={"recursion_limit": 15},
                    stream_mode="messages"
                )
                for chunk, metadata in stream_result:
                    if chunk.content:
                        yield chunk.content
                agent_trace.end_run(status="success")
                ended = True
            except Exception as e:
                print(f"[plan_route_endpoint] pipeline exception: {traceback.format_exc()}")
                agent_trace.attach_run(run_id)
                agent_trace.end_run(status="error", error=str(e))
                ended = True
                yield f"\n__ERROR__:{str(e)}\n"
            finally:
                # 客户端断开 / GeneratorExit 时也强制结束 trace（避免一直停在 running 状态）
                if not ended:
                    agent_trace.attach_run(run_id)
                    agent_trace.end_run(status="aborted", error="generator closed before finish")

        response = StreamingResponse(event_generator(), media_type="text/plain")
        response.headers["X-RAG-Pending-Count"] = str(pending_count)
        response.headers["X-Agent-Run-Id"] = run_id
        return response

    except Exception as e:
        print(f'[plan_route_endpoint] {traceback.format_exc()}')
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/rag/landmarks")
def get_rag_landmarks_endpoint():
    try:
        if not rag_service.db:
            return []
        
        # 获取 Chroma 库中所有文本的分块和元数据
        results = rag_service.db.get(include=["metadatas"])
        
        # 统计每个地标入库的分块数量
        landmarks_dict = {}
        for meta in results.get("metadatas", []):
            if not meta:
                continue
            lm_id = meta.get("landmark_id")
            if not lm_id:
                continue
            if lm_id not in landmarks_dict:
                landmarks_dict[lm_id] = {
                    "id": lm_id,
                    "name": meta.get("landmark_name", "未知地标"),
                    "bangumi": meta.get("bangumi", "未知作品"),
                    "chunks_count": 0
                }
            landmarks_dict[lm_id]["chunks_count"] += 1
            
        return list(landmarks_dict.values())
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/rag/query")
def query_rag_test_endpoint(query: str):
    try:
        if not query.strip():
            return []
            
        # 向量相似度检索 (Recall)
        raw_docs = rag_service.db.similarity_search(query, k=6)
        if not raw_docs:
            return []
            
        # 大模型精排 (Rerank)
        scored_docs = rag_service.reranker.rerank_with_scores(query, raw_docs)
        
        # 组装展示数据
        results = []
        for idx, (original_idx, score, doc) in enumerate(scored_docs):
            results.append({
                "rank": idx + 1,
                "score": score,
                "landmark_name": doc.metadata.get("landmark_name", "未知地标"),
                "bangumi": doc.metadata.get("bangumi", "未知作品"),
                "chunk_id": doc.metadata.get("chunk_id", 0),
                "content": doc.page_content,
                "source": doc.metadata.get("source", "未知来源")
            })
        return results
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.post("/api/rag/clear")
def clear_rag_database_endpoint():
    try:
        rag_service.clear_database()
        return {"status": "success", "message": "RAG 向量数据库已清空且重置完成"}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/rag/logs")
def get_rag_logs_endpoint():
    try:
        import json
        log_file = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_history.json")
        if not os.path.exists(log_file):
            return []
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.post("/api/rag/logs/clear")
def clear_rag_logs_endpoint():
    try:
        log_file = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_history.json")
        if os.path.exists(log_file):
            os.remove(log_file)
        return {"status": "success", "message": "RAG 历史日志已清空"}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/rag/pending")
def get_pending_endpoint():
    """获取待审核暂存队列"""
    try:
        return rag_service.get_pending_list()
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.post("/api/rag/pending/approve")
def approve_pending_endpoint(req: ApproveRequest):
    """审批通过暂存记录并写入 ChromaDB"""
    try:
        success = rag_service.approve_pending(req.id, req.chunks)
        if success:
            return {"status": "success", "message": "已批准并写入向量数据库"}
        else:
            raise HTTPException(status_code=404, detail="未找到对应的待审核记录")
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.post("/api/rag/pending/reject")
def reject_pending_endpoint(req: RejectRequest):
    """拒绝暂存记录"""
    try:
        success = rag_service.reject_pending(req.id)
        if success:
            return {"status": "success", "message": "已拒绝并删除暂存记录"}
        else:
            raise HTTPException(status_code=404, detail="未找到对应的待审核记录")
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.delete("/api/rag/landmarks/{landmark_id}")
def delete_landmark_endpoint(landmark_id: str):
    """从向量库中删除指定地标的所有知识数据"""
    try:
        success = rag_service.delete_landmark_chunks(landmark_id)
        if success:
            return {"status": "success", "message": f"已从向量库中删除地标 {landmark_id} 的所有数据"}
        else:
            raise HTTPException(status_code=404, detail=f"向量库中未找到地标 {landmark_id} 的数据")
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/rag/landmark/{landmark_id}/chunks")
def get_landmark_chunks_endpoint(landmark_id: str):
    """获取指定地标在向量数据库中的所有切片详情"""
    try:
        results = rag_service.db.get(
            where={"landmark_id": landmark_id},
            include=["documents", "metadatas"]
        )
        chunks = []
        for i, doc_id in enumerate(results.get("ids", [])):
            chunks.append({
                "id": doc_id,
                "content": results["documents"][i] if results.get("documents") else "",
                "metadata": results["metadatas"][i] if results.get("metadatas") else {}
            })
        return chunks
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

# ---------------- Agent 调试追踪相关端点 ----------------

@app.get("/api/agent/traces")
def list_agent_traces_endpoint():
    """列出最近的 agent 运行（摘要，不含 steps）"""
    try:
        return agent_trace.list_traces()
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.get("/api/agent/trace/{run_id}")
def get_agent_trace_endpoint(run_id: str):
    """获取指定 run 的完整 trace（包含所有 LLM/工具步骤）"""
    try:
        trace = agent_trace.get_trace(run_id)
        if not trace:
            raise HTTPException(status_code=404, detail=f"未找到 run_id={run_id} 的追踪记录")
        return trace
    except HTTPException:
        raise
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

@app.post("/api/agent/traces/clear")
def clear_agent_traces_endpoint():
    """清空所有 agent 追踪记录"""
    try:
        agent_trace.clear_traces()
        return {"status": "success", "message": "Agent 追踪记录已清空"}
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail='服务器内部错误')

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
