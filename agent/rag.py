import os
from pathlib import Path
from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from dotenv import load_dotenv

load_dotenv()

# Path to the RAG document
RAG_DOCUMENT_PATH = Path(__file__).parent.parent / "documents" / "rag-document.md"

# Chroma persistent storage directory
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
        self.chroma_db_path = chroma_db_path
        self.persist_directory = str(self.chroma_db_path)

        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators or ["\n\n", "\n", " ", ""],
        )

        self._vector_db = None
        self._retrievers = {}

    def load_and_split_documents(self):
        """Load the RAG document and split it into chunks."""
        if not self.rag_document_path.exists():
            raise FileNotFoundError(f"RAG document not found at {self.rag_document_path}")

        loader = TextLoader(str(self.rag_document_path), encoding="utf-8")
        documents = loader.load()
        return self.text_splitter.split_documents(documents)

    def create_or_load_vector_db(self):
        """Create or load the Chroma vector database."""
        if self._vector_db is not None:
            return self._vector_db

        if os.path.exists(self.persist_directory) and len(os.listdir(self.persist_directory)) > 0:
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
            print(f"Vector database created and persisted at {self.persist_directory}")

        return self._vector_db

    def get_retriever(self, k=3):
        """Get or create a retriever for the given K value."""
        if k in self._retrievers:
            return self._retrievers[k]

        vector_db = self.create_or_load_vector_db()
        retriever = vector_db.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k},
        )
        self._retrievers[k] = retriever
        return retriever

    def retrieve_context(self, query, k=3):
        """Retrieve relevant documents from the vector DB based on a query."""
        retriever = self.get_retriever(k=k)
        return retriever.invoke(query)

    def format_retrieved_documents(self, docs):
        """Format retrieved documents for use in the LLM prompt."""
        if not docs:
            return "No relevant information found in the knowledge base."

        formatted = "Retrieved Context:\n" + "=" * 50 + "\n"
        for i, doc in enumerate(docs, 1):
            formatted += f"\n[Document {i}]\n{doc.page_content}\n"
        formatted += "\n" + "=" * 50 + "\n"
        return formatted

    def get_rag_context(self, query: str, k: int = 3):
        """Retrieve relevant knowledge base context for a query."""
        docs = self.retrieve_context(query, k=k)
        return self.format_retrieved_documents(docs)


rag = RAG()


@tool
def get_rag_context(query: str, k: int = 3):
    """Retrieve relevant knowledge base context for a query."""
    return rag.get_rag_context(query, k=k)


def load_and_split_documents():
    """Load the RAG document and split it into chunks."""
    if not RAG_DOCUMENT_PATH.exists():
        raise FileNotFoundError(f"RAG document not found at {RAG_DOCUMENT_PATH}")
    
    # Load the document
    loader = TextLoader(str(RAG_DOCUMENT_PATH), encoding="utf-8")
    documents = loader.load()
    
    # Split into chunks
    chunks = text_splitter.split_documents(documents)
    
    return chunks


def create_or_load_vector_db():
    """
    Create or load the Chroma vector database.
    If the DB already exists, it loads from disk (reuses embeddings).
    If not, it creates a new one from the RAG document.
    """
    
    # Check if vector DB already exists
    if os.path.exists(persist_directory) and len(os.listdir(persist_directory)) > 0:
        print("Loading existing vector database...")
        vector_db = Chroma(
            persist_directory=persist_directory,
            embedding_function=embeddings,
            collection_name="rag_documents"
        )
    else:
        print("Creating new vector database...")
        # Load and split documents
        chunks = load_and_split_documents()
        print(f"Split document into {len(chunks)} chunks")
        
        # Create vector DB from chunks
        vector_db = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=persist_directory,
            collection_name="rag_documents"
        )
        
        # Persist the database
        vector_db.persist()
        print(f"Vector database created and persisted at {persist_directory}")
    
    return vector_db


def get_retriever(k=3):
    """
    Get a retriever connected to the vector database.
    
    Args:
        k: Number of documents to retrieve (default: 3)
    
    Returns:
        A retriever object that can be used in chains
    """
    vector_db = create_or_load_vector_db()
    retriever = vector_db.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k}
    )
    return retriever


def retrieve_context(query, k=3):
    """
    Retrieve relevant documents from the vector DB based on a query.
    
    Args:
        query: The query string
        k: Number of documents to retrieve
    
    Returns:
        A list of retrieved documents with content and metadata
    """
    retriever = get_retriever(k=k)
    docs = retriever.invoke(query)
    return docs


def format_retrieved_documents(docs):
    """
    Format retrieved documents for use in the LLM prompt.
    
    Args:
        docs: List of retrieved documents
    
    Returns:
        A formatted string containing the document content
    """
    if not docs:
        return "No relevant information found in the knowledge base."
    
    formatted = "Retrieved Context:\n" + "=" * 50 + "\n"
    for i, doc in enumerate(docs, 1):
        formatted += f"\n[Document {i}]\n{doc.page_content}\n"
    formatted += "\n" + "=" * 50 + "\n"
    return formatted

@tool
def get_rag_context(query: str, k: int = 3):
    """Retrieve relevant knowledge base context for a query."""
    docs = retrieve_context(query, k=k)
    return format_retrieved_documents(docs)