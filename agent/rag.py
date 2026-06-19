import os
from pathlib import Path
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv

load_dotenv()

RAG_DOCUMENT_PATH = Path(__file__).parent.parent / "documents" / "rag-document.md"
CHROMA_DB_PATH = Path(__file__).parent.parent / "chroma_db"
CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)


class RAG:
    def __init__(
        self,
        rag_document_path: Path = RAG_DOCUMENT_PATH,
        chroma_db_path: Path = CHROMA_DB_PATH,
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        separators=None,
    ):
        self.rag_document_path = rag_document_path
        self.persist_directory = str(chroma_db_path)

        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", " ", ""],
        )

        self._vector_db = None
        self._retrievers = {}

    def load_and_split_documents(self):
        if not self.rag_document_path.exists():
            raise FileNotFoundError(f"RAG document not found at {self.rag_document_path}")
        loader = TextLoader(str(self.rag_document_path), encoding="utf-8")
        documents = loader.load()
        return self.text_splitter.split_documents(documents)

    def create_or_load_vector_db(self):
        if self._vector_db is not None:
            return self._vector_db

        if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
            print("Loading existing vector database...")
            self._vector_db = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings,
                collection_name="rag_documents",
            )
        else:
            print("Creating new vector database...")
            chunks = self.load_and_split_documents()
            print(f"Split document into {len(chunks)} chunks")
            self._vector_db = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.persist_directory,
                collection_name="rag_documents",
            )
            self._vector_db.persist()
            print(f"Vector database created at {self.persist_directory}")

        return self._vector_db

    def get_retriever(self, k=3):
        if k not in self._retrievers:
            vector_db = self.create_or_load_vector_db()
            self._retrievers[k] = vector_db.as_retriever(
                search_type="similarity",
                search_kwargs={"k": k},
            )
        return self._retrievers[k]

    def retrieve_context(self, query: str, k: int = 3):
        return self.get_retriever(k=k).invoke(query)

    def format_retrieved_documents(self, docs):
        if not docs:
            return "No relevant information found in the knowledge base."
        formatted = "Retrieved Context:\n" + "=" * 50 + "\n"
        for i, doc in enumerate(docs, 1):
            formatted += f"\n[Document {i}]\n{doc.page_content}\n"
        formatted += "\n" + "=" * 50 + "\n"
        return formatted

    def get_rag_context(self, query: str, k: int = 3) -> str:
        docs = self.retrieve_context(query, k=k)
        return self.format_retrieved_documents(docs)


# Single shared instance — initialized once, reused across calls
rag = RAG()

# Eagerly initialize the vector DB at startup so embeddings
# are created/loaded before the first request comes in
rag.create_or_load_vector_db()


@tool
def get_rag_context(query: str, k: int = 3) -> str:
    """Retrieve relevant knowledge base context for a query about learning portal,
    program information, policies, documentation, URLs, or academy information."""
    return rag.get_rag_context(query, k=k)