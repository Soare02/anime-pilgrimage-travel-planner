import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import List, Optional
from agent import agent
from rag_service import rag_service

app = FastAPI(title="Anime Pilgrimage Travel Planner Agent Server")

# 启用 CORS 跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Landmark(BaseModel):
    id: str
    name: str
    originalName: Optional[str] = None
    bangumiName: Optional[str] = None
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
        # 1. 提取地标信息并利用 RAG 进行增量并发联网检索及入库
        landmarks_data = []
        for lm in req.landmarks:
            landmarks_data.append({
                "id": lm.id,
                "name": lm.name,
                "bangumiName": lm.bangumiName or "未知"
            })
        
        # 触发增量联网与切片入库
        ingest_result = rag_service.ingest_landmarks(landmarks_data)
        pending_count = ingest_result.get("pending_count", 0) if ingest_result else 0

        # 2. 构建检索查询词并获取 RAG 召回内容
        unique_bangumis = list(set([lm.bangumiName for lm in req.landmarks if lm.bangumiName and lm.bangumiName != "未知"]))
        landmark_names = [lm.name for lm in req.landmarks if lm.name]
        rag_query = " ".join(unique_bangumis + landmark_names)
        
        # 召回与重排最优上下文
        rag_context = rag_service.query_rag_context(rag_query)

        # 3. 格式化地标数据，拼装为 Agent 能够理解的文本 prompt
        landmark_lines = []
        for i, lm in enumerate(req.landmarks):
            parts = [f"{i + 1}. 地点名称：{lm.name or lm.originalName or '未知'}"]
            parts.append(f"   作品名称：{lm.bangumiName or '未知'}")
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

        # 注入 RAG 上下文
        if rag_context:
            data_text = (
                "## 检索到的巡礼背景与攻略知识 (RAG Context)\n"
                f"{rag_context}\n\n"
                "--------------------------------------------------\n"
                "## 用户规划任务请求\n"
                f"{data_text}"
            )

        # 4. 定义流式生成器函数
        # 使用同步生成器配合同步 endpoint，FastAPI 会自动在独立的线程池中迭代它，避免阻塞主事件循环
        def event_generator():
            stream_result = agent.stream(
                {"messages": [{"role": "user", "content": data_text}]},
                config={"recursion_limit": 15},
                stream_mode="messages"
            )
            for chunk, metadata in stream_result:
                if chunk.content:
                    yield chunk.content

        response = StreamingResponse(event_generator(), media_type="text/plain")
        response.headers["X-RAG-Pending-Count"] = str(pending_count)
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=f"获取 RAG 地标缓存失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"RAG 检索与精排测试失败: {str(e)}")

@app.post("/api/rag/clear")
def clear_rag_database_endpoint():
    try:
        rag_service.clear_database()
        return {"status": "success", "message": "RAG 向量数据库已清空且重置完成"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空 RAG 数据库失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"获取 RAG 历史日志失败: {str(e)}")

@app.post("/api/rag/logs/clear")
def clear_rag_logs_endpoint():
    try:
        log_file = os.path.join(os.path.dirname(__file__), "chroma_db", "rag_history.json")
        if os.path.exists(log_file):
            os.remove(log_file)
        return {"status": "success", "message": "RAG 历史日志已清空"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清空 RAG 历史日志失败: {str(e)}")

@app.get("/api/rag/pending")
def get_pending_endpoint():
    """获取待审核暂存队列"""
    try:
        return rag_service.get_pending_list()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取待审核队列失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"审批操作失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"拒绝操作失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"删除地标数据失败: {str(e)}")

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
        raise HTTPException(status_code=500, detail=f"获取地标切片失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
