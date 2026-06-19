#!/usr/bin/env python3
"""
Test script to validate RAG setup.
Initializes vector DB, splits documents, and tests retrieval.
"""

from dotenv import load_dotenv
import sys

load_dotenv()

print("=" * 60)
print("Testing RAG Setup")
print("=" * 60)

try:
    print("\n[1/4] Importing RAG modules...")
    from utils.rag import (
        RAG,
        RAG_DOCUMENT_PATH,
    )
    print("✓ RAG modules imported successfully")
    
    print(f"\n[2/4] Checking RAG document path...")
    print(f"   Path: {RAG_DOCUMENT_PATH}")
    if RAG_DOCUMENT_PATH.exists():
        print(f"   ✓ Document found ({RAG_DOCUMENT_PATH.stat().st_size} bytes)")
    else:
        print(f"   ✗ Document not found!")
        sys.exit(1)
    
    print("\n[3/4] Initializing vector database...")
    rag = RAG()
    vector_db = rag.create_or_load_vector_db()
    print("✓ Vector database initialized")
    
    print("\n[4/4] Testing retrieval with sample queries...")
    test_queries = [
        "What is My Journey?",
        "How do course exams work?",
        "Tell me about exam schedule",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n   Query {i}: '{query}'")
        docs = rag.retrieve_context(query, k=2)
        formatted = rag.format_retrieved_documents(docs)
        print(f"   Retrieved {len(docs)} documents")
        print(f"   Preview: {formatted[:200]}...")
    
    print("\n" + "=" * 60)
    print("✓ All RAG tests passed!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ Error during testing: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
