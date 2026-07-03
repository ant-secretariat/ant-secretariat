import logging
from typing import List, Optional
from interfaces import BaseEmbeddingModel, BaseVectorDB
from schemas import VectorChunk

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Placeholder (API 키 올 때까지 임시 사용)
# ──────────────────────────────────────────────

class PlaceholderEmbeddingModel(BaseEmbeddingModel):
    def embed(self, text: str) -> List[float]:
        logger.debug("PlaceholderEmbeddingModel: API 키 대기 중")
        return []

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]

    def get_dimension(self) -> int:
        return 0


class PlaceholderVectorDB(BaseVectorDB):
    def upsert(self, chunk: VectorChunk, vector: List[float]) -> str:
        return ""

    def upsert_batch(self, chunks: List[VectorChunk], vectors: List[List[float]]) -> List[str]:
        return ["" for _ in chunks]

    def search(self, query_vector: List[float], top_k: int = 5, filter: Optional[dict] = None) -> List[dict]:
        logger.warning("PlaceholderVectorDB: 검색 불가")
        return []

    def delete(self, chunk_id: str) -> bool:
        return False


# ──────────────────────────────────────────────
# Upstage 임베딩 모델 (API 키 오면 사용)
# ──────────────────────────────────────────────

class UpstageEmbeddingModel(BaseEmbeddingModel):
    MODEL_NAME = "solar-embedding-1-large-passage"

    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            from openai import OpenAI
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.upstage.ai/v1"
            )
            logger.info("UpstageEmbeddingModel 초기화 완료")
        except ImportError:
            raise ImportError("openai 패키지 미설치. pip install openai 실행")

    def embed(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.MODEL_NAME,
            input=text
        )
        return response.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]

    def get_dimension(self) -> int:
        return 4096


# ──────────────────────────────────────────────
# Pinecone Vector DB
# ──────────────────────────────────────────────

class PineconeVectorDB(BaseVectorDB):

    NAMESPACE_MAP = {
        "report":        "report_chunks",
        "news":          "news_chunks",
        "disclosure":    "disclosure_chunks",
        "macro_summary": "macro_summary_chunks",
    }

    def __init__(self, api_key: str, index_name: str):
        try:
            from pinecone import Pinecone
        except ImportError:
            raise ImportError("pinecone 패키지 미설치. pip install pinecone 실행")

        self.pc = Pinecone(api_key=api_key)
        self.index = self.pc.Index(index_name)
        logger.info(f"PineconeVectorDB 초기화 완료: {index_name}")

    def _get_namespace(self, document_type: str) -> str:
        return self.NAMESPACE_MAP.get(document_type, "report_chunks")

    def upsert(self, chunk: VectorChunk, vector: List[float]) -> str:
        if not vector:
            return ""
        try:
            namespace = self._get_namespace(chunk.metadata.document_type)
            self.index.upsert(
                vectors=[{
                    "id": chunk.id,
                    "values": vector,
                    "metadata": {
                        "chunk_id":      chunk.metadata.chunk_id,
                        "ticker":        chunk.metadata.ticker,
                        "company":       chunk.metadata.company,
                        "date":          chunk.metadata.date,
                        "source":        chunk.metadata.source,
                        "document_type": chunk.metadata.document_type,
                        "report_type":   chunk.metadata.report_type or "",
                        "title":         chunk.metadata.title,
                        "author_org":    chunk.metadata.author_org or "",
                        "page_start":    chunk.metadata.page_start or 0,
                        "page_end":      chunk.metadata.page_end or 0,
                        "url":           chunk.metadata.url,
                        "content":       chunk.content,
                    }
                }],
                namespace=namespace,
            )
            return chunk.id
        except Exception as e:
            logger.error(f"Pinecone upsert 실패: {chunk.id} | {e}")
            return ""

    def upsert_batch(self, chunks: List[VectorChunk], vectors: List[List[float]]) -> List[str]:
        valid = [(c, v) for c, v in zip(chunks, vectors) if v]
        if not valid:
            return ["" for _ in chunks]

        from collections import defaultdict
        groups = defaultdict(list)
        for chunk, vector in valid:
            groups[chunk.metadata.document_type].append((chunk, vector))

        results = {c.id: "" for c in chunks}

        for doc_type, items in groups.items():
            try:
                namespace = self._get_namespace(doc_type)
                self.index.upsert(
                    vectors=[{
                        "id": c.id,
                        "values": v,
                        "metadata": {
                            "chunk_id":      c.metadata.chunk_id,
                            "ticker":        c.metadata.ticker,
                            "company":       c.metadata.company,
                            "date":          c.metadata.date,
                            "source":        c.metadata.source,
                            "document_type": c.metadata.document_type,
                            "report_type":   c.metadata.report_type or "",
                            "title":         c.metadata.title,
                            "author_org":    c.metadata.author_org or "",
                            "page_start":    c.metadata.page_start or 0,
                            "page_end":      c.metadata.page_end or 0,
                            "url":           c.metadata.url,
                            "content":       c.content,
                        }
                    } for c, v in items],
                    namespace=namespace,
                )
                for c, _ in items:
                    results[c.id] = c.id
            except Exception as e:
                logger.error(f"Pinecone upsert_batch 실패: {doc_type} | {e}")

        return [results[c.id] for c in chunks]

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> List[dict]:
        if not query_vector:
            return []

        doc_type = (filter or {}).get("document_type")
        namespaces = (
            [self._get_namespace(doc_type)] if doc_type
            else list(self.NAMESPACE_MAP.values())
        )

        pinecone_filter = {}
        if filter:
            for k, v in filter.items():
                if k == "document_type":
                    continue
                elif k == "date_from":
                    pinecone_filter.setdefault("date", {})["$gte"] = v
                elif k == "date_to":
                    pinecone_filter.setdefault("date", {})["$lte"] = v
                else:
                    pinecone_filter[k] = {"$eq": v}

        results = []
        for namespace in namespaces:
            try:
                res = self.index.query(
                    vector=query_vector,
                    top_k=top_k,
                    namespace=namespace,
                    filter=pinecone_filter if pinecone_filter else None,
                    include_metadata=True,
                )
                for match in res.matches:
                    meta = match.metadata or {}
                    results.append({
                        "id":       match.id,
                        "content":  meta.pop("content", ""),
                        "score":    match.score,
                        "metadata": meta,
                    })
            except Exception as e:
                logger.error(f"Pinecone search 실패: {namespace} | {e}")

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def delete(self, chunk_id: str) -> bool:
        namespace_map = {
            "news_":        "news_chunks",
            "disclosure_":  "disclosure_chunks",
            "macro_":       "macro_summary_chunks",
        }
        namespace = "report_chunks"
        for prefix, ns in namespace_map.items():
            if chunk_id.startswith(prefix):
                namespace = ns
                break
        try:
            self.index.delete(ids=[chunk_id], namespace=namespace)
            return True
        except Exception as e:
            logger.error(f"Pinecone delete 실패: {chunk_id} | {e}")
            return False