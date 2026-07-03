from abc import ABC, abstractmethod
from typing import List, Optional
from processing.schemas import VectorChunk, ReportChunkRecord


class BaseEmbeddingModel(ABC):
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        pass


class BaseVectorDB(ABC):
    @abstractmethod
    def upsert(self, chunk: VectorChunk, vector: List[float]) -> str:
        pass

    @abstractmethod
    def upsert_batch(self, chunks: List[VectorChunk], vectors: List[List[float]]) -> List[str]:
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter: Optional[dict] = None,
    ) -> List[dict]:
        pass

    @abstractmethod
    def delete(self, chunk_id: str) -> bool:
        pass


class BaseRelationalDB(ABC):

    @abstractmethod
    def insert_report_chunk_record(self, record: ReportChunkRecord) -> bool:
        pass

    @abstractmethod
    def update_chunk_vector_id(self, chunk_id: str, vector_id: str) -> bool:
        pass

    @abstractmethod
    def update_chunk_embedding_status(self, chunk_id: str, status: str) -> bool:
        pass

    @abstractmethod
    def get_chunk_by_id(self, chunk_id: str) -> Optional[ReportChunkRecord]:
        pass

    @abstractmethod
    def chunk_exists(self, chunk_id: str) -> bool:
        pass

    @abstractmethod
    def get_chunks_by_report_id(self, report_id: str) -> List[ReportChunkRecord]:
        pass


    @abstractmethod
    def get_reports_to_process(self) -> list:
        pass
