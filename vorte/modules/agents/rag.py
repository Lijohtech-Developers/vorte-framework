"""
RAG (Retrieval Augmented Generation) Agent
==========================================
Provides a RAG agent that retrieves relevant context from a vectorstore
before generating responses. Supports pgvector, embedding model configuration,
and source model management for retrieval.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from vorte.modules.agents.agent import Agent, AgentConfig, AgentResponse, AgentRole
from vorte.modules.agents.memory import ConversationMemory, MemoryConfig


class RetrievalMode(str, Enum):
    """Modes for document retrieval."""
    SIMILARITY = "similarity"
    MMR = "mmr"
    SIMILARITY_SCORE_THRESHOLD = "similarity_score_threshold"


@dataclass
class VectorStoreConfig:
    """
    Configuration for the vectorstore backend.

    Attributes:
        provider: The vectorstore provider (e.g., 'pgvector', 'pinecone',
            'chromadb', 'weaviate', 'qdrant').
        connection_string: Connection URL or configuration string.
        collection_name: The collection/index name to use.
        embedding_dimension: Dimension of the embedding vectors.
        api_key: API key for cloud vectorstore providers.
        ssl: Whether to use SSL for connections.
    """
    provider: str = "pgvector"
    connection_string: str = ""
    collection_name: str = "documents"
    embedding_dimension: int = 1536
    api_key: str = ""
    ssl: bool = True
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingConfig:
    """
    Configuration for the embedding model.

    Attributes:
        model: The embedding model name (e.g., 'text-embedding-3-small').
        provider: The embedding provider (e.g., 'openai', 'cohere', 'huggingface').
        dimensions: Output dimensions (None = use model default).
        api_key: API key for the embedding provider.
    """
    model: str = "text-embedding-3-small"
    provider: str = "openai"
    dimensions: Optional[int] = None
    api_key: str = ""


@dataclass
class RAGConfig:
    """
    Configuration for the RAG agent.

    Attributes:
        vectorstore: Configuration for the vectorstore backend.
        embedding: Configuration for the embedding model.
        top_k: Number of documents to retrieve per query.
        retrieval_mode: Retrieval strategy to use.
        score_threshold: Minimum similarity score for retrieval (when using
            SIMILARITY_SCORE_THRESHOLD mode).
        include_sources: Whether to include source information in responses.
        max_context_tokens: Maximum tokens of retrieved context to include.
        rerank: Whether to rerank retrieved documents.
        rerank_model: Model to use for reranking.
        source_models: Additional source models for retrieval.
    """
    vectorstore: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    top_k: int = 5
    retrieval_mode: RetrievalMode = RetrievalMode.SIMILARITY
    score_threshold: float = 0.7
    include_sources: bool = True
    max_context_tokens: int = 4096
    rerank: bool = False
    rerank_model: Optional[str] = None
    source_models: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RetrievedDocument:
    """
    A document retrieved from the vectorstore.

    Attributes:
        content: The document text content.
        metadata: Document metadata (source, title, etc.).
        score: Similarity score (0.0 to 1.0).
        id: Document ID in the vectorstore.
    """
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    id: Optional[str] = None

    def to_context(self, include_metadata: bool = True) -> str:
        """Format the document as context text."""
        parts = [self.content]
        if include_metadata and self.metadata:
            source = self.metadata.get("source", self.metadata.get("title", ""))
            if source:
                parts.append(f"\n[Source: {source}]")
        return "\n".join(parts)


class RAGAgent(Agent):
    """
    Retrieval Augmented Generation Agent.

    Extends the base Agent with a retrieval step that queries a vectorstore
    for relevant documents before generating a response. The retrieved context
    is injected into the prompt to ground the model's output in factual data.

    Usage:
        rag_agent = RAGAgent(
            name="knowledge_assistant",
            model="gpt-4o",
            vectorstore=VectorStoreConfig(
                provider="pgvector",
                connection_string="postgresql+asyncpg://localhost/mydb",
                collection_name="docs",
            ),
            embedding=EmbeddingConfig(model="text-embedding-3-small"),
            top_k=5,
        )

        response = await rag_agent.run("What is the refund policy?")
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[Sequence] = None,
        memory_config: Optional[MemoryConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # RAG-specific
        vectorstore: Optional[VectorStoreConfig] = None,
        embedding: Optional[EmbeddingConfig] = None,
        top_k: int = 5,
        retrieval_mode: RetrievalMode = RetrievalMode.SIMILARITY,
        score_threshold: float = 0.7,
        include_sources: bool = True,
        max_context_tokens: int = 4096,
        rerank: bool = False,
        rag_config: Optional[RAGConfig] = None,
        # Base agent config
        config: Optional[AgentConfig] = None,
    ) -> None:
        # Build RAG config
        if rag_config:
            self._rag_config = rag_config
        else:
            self._rag_config = RAGConfig(
                vectorstore=vectorstore or VectorStoreConfig(),
                embedding=embedding or EmbeddingConfig(),
                top_k=top_k,
                retrieval_mode=retrieval_mode,
                score_threshold=score_threshold,
                include_sources=include_sources,
                max_context_tokens=max_context_tokens,
                rerank=rerank,
            )

        # Build system prompt with RAG instructions
        rag_system_prompt = system_prompt or self._build_rag_system_prompt()

        # Initialize the base Agent
        super().__init__(
            name=name or "rag_agent",
            model=model,
            system_prompt=rag_system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            memory_config=memory_config,
            metadata=metadata,
            role=AgentRole.RAG,
            config=config,
        )

        # RAG state
        self._last_retrieved_docs: List[RetrievedDocument] = []

    @property
    def rag_config(self) -> RAGConfig:
        """Get the RAG configuration."""
        return self._rag_config

    @property
    def last_retrieved_docs(self) -> List[RetrievedDocument]:
        """Get the documents retrieved in the last run."""
        return list(self._last_retrieved_docs)

    async def run(
        self,
        message: str,
        *,
        tools_enabled: bool = True,
        memory_enabled: bool = True,
        retrieval_enabled: bool = True,
        **kwargs: Any,
    ) -> AgentResponse:
        """
        Run the RAG agent with a message.

        Performs retrieval from the vectorstore, injects the retrieved
        context into the prompt, and generates a grounded response.

        Args:
            message: The user message to process.
            tools_enabled: Whether to allow tool calls.
            memory_enabled: Whether to use conversation memory.
            retrieval_enabled: Whether to perform retrieval (can be disabled
                for general conversation without RAG).
            **kwargs: Additional overrides.

        Returns:
            An AgentResponse with the grounded result.
        """
        if retrieval_enabled:
            # Step 1: Retrieve relevant documents
            retrieved = await self._retrieve(message)
            self._last_retrieved_docs = retrieved

            # Step 2: Build context-augmented message
            augmented_message = self._build_augmented_message(message, retrieved)
        else:
            augmented_message = message
            self._last_retrieved_docs = []

        # Step 3: Run the base agent with the augmented message
        response = await super().run(
            augmented_message,
            tools_enabled=tools_enabled,
            memory_enabled=memory_enabled,
            **kwargs,
        )

        # Attach retrieval metadata to the response
        if self._last_retrieved_docs:
            response.metadata["retrieved_documents"] = len(self._last_retrieved_docs)
            response.metadata["sources"] = [
                doc.metadata.get("source", doc.metadata.get("title", ""))
                for doc in self._last_retrieved_docs
                if doc.metadata
            ]

        return response

    # ---- Retrieval ----

    async def _retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve relevant documents from the vectorstore.

        Args:
            query: The query to search for.

        Returns:
            List of RetrievedDocument instances sorted by relevance.
        """
        try:
            return await self._query_vectorstore(query)
        except Exception as e:
            # If vectorstore is not available, return empty
            if self._rag_config.vectorstore.connection_string:
                # Only log if a connection string was configured
                print(f"RAG retrieval error: {e}")
            return []

    async def _query_vectorstore(self, query: str) -> List[RetrievedDocument]:
        """
        Query the vectorstore for relevant documents.

        In production, this would connect to the actual vectorstore
        (pgvector, Pinecone, ChromaDB, etc.) and perform a similarity search.

        For now, returns an empty list (placeholder).
        """
        # Placeholder: In production, implement actual vectorstore querying:
        #
        # if self._rag_config.vectorstore.provider == "pgvector":
        #     return await self._query_pgvector(query)
        # elif self._rag_config.vectorstore.provider == "pinecone":
        #     return await self._query_pinecone(query)
        # etc.

        return []

    async def _embed(self, text: str) -> List[float]:
        """
        Generate embeddings for a text.

        Args:
            text: The text to embed.

        Returns:
            List of float embedding values.
        """
        # Placeholder: In production, call the embedding API
        # embedding = await openai.embeddings.create(
        #     model=self._rag_config.embedding.model,
        #     input=text,
        # )
        # return embedding.data[0].embedding
        return []

    # ---- Source Model Management ----

    def add_source_model(
        self,
        name: str,
        model_type: str,
        config: Dict[str, Any],
    ) -> None:
        """
        Add a source model for retrieval.

        A source model defines a data source (e.g., database table, API,
        file system) that can be queried during retrieval.

        Args:
            name: Source model name.
            model_type: Type of source ('database', 'api', 'file', 'web').
            config: Configuration for the source model.
        """
        self._rag_config.source_models.append({
            "name": name,
            "type": model_type,
            "config": config,
        })

    def remove_source_model(self, name: str) -> None:
        """
        Remove a source model by name.

        Args:
            name: Source model name to remove.
        """
        self._rag_config.source_models = [
            m for m in self._rag_config.source_models
            if m["name"] != name
        ]

    def get_source_models(self) -> List[Dict[str, Any]]:
        """Get all registered source models."""
        return list(self._rag_config.source_models)

    # ---- Internal Helpers ----

    def _build_rag_system_prompt(self) -> str:
        """Build the default RAG system prompt."""
        source_instruction = ""
        if self._rag_config.include_sources:
            source_instruction = (
                "Always cite the sources of your information when possible. "
                "Format citations as [Source: name]."
            )

        return (
            "You are a knowledgeable assistant that answers questions based on "
            "the provided context. Always ground your responses in the retrieved "
            "documents. If the context does not contain relevant information, "
            "say so honestly rather than making up information.\n\n"
            f"{source_instruction}\n\n"
            "You will receive context from the document retrieval system below "
            "the user's message. Use this context to provide accurate, "
            "well-sourced answers."
        )

    def _build_augmented_message(
        self,
        message: str,
        documents: List[RetrievedDocument],
    ) -> str:
        """
        Build a message augmented with retrieved document context.

        Args:
            message: The original user message.
            documents: The retrieved documents.

        Returns:
            The augmented message with context injected.
        """
        if not documents:
            return message

        # Build context block
        context_parts = []
        total_chars = 0
        max_chars = self._rag_config.max_context_tokens * 4  # Approximate

        for i, doc in enumerate(documents):
            doc_text = doc.to_context(include_metadata=self._rag_config.include_sources)
            if total_chars + len(doc_text) > max_chars:
                break
            context_parts.append(f"[Document {i + 1}]\n{doc_text}")
            total_chars += len(doc_text)

        context_block = "\n\n".join(context_parts)

        return (
            f"{message}\n\n"
            f"---\n"
            f"Retrieved Context:\n{context_block}\n"
            f"---\n"
            f"Please answer the question using the above context."
        )

    async def index_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Index documents into the vectorstore.

        Args:
            documents: List of dicts with 'content' and optional 'metadata' keys.

        Returns:
            A summary dict of the indexing operation.
        """
        indexed = 0
        errors = []

        for doc in documents:
            try:
                content = doc.get("content", "")
                metadata = doc.get("metadata", {})

                # Generate embedding
                embedding = await self._embed(content)

                # In production, store in vectorstore:
                # await self._store_in_vectorstore(content, metadata, embedding)

                indexed += 1
            except Exception as e:
                errors.append(f"Error indexing document: {e}")

        return {
            "indexed": indexed,
            "total": len(documents),
            "errors": errors,
        }

    def __repr__(self) -> str:
        return (
            f"RAGAgent(name={self.name!r}, model={self.model!r}, "
            f"vectorstore={self._rag_config.vectorstore.provider!r}, "
            f"top_k={self._rag_config.top_k})"
        )
