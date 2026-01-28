import asyncio
import uuid

# To run this example, you need to have the following environment variables set:
# export SYFTHUB_URL="http://localhost:8080"
# export SYFTHUB_USERNAME="your-syfthub-username"
# export SYFTHUB_PASSWORD="your-syfthub-password"
# export SPACE_URL="http://localhost:8001" # The public URL of this running space

from syfthub_api.app import SyftAPI
from syfthub_api.schemas import Document, Message

# Initialize the SyftAI Space application
app = SyftAPI()

# In-memory data store for the example
DUMMY_PAPERS = {
    "paper-1": "Attention is All You Need. The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
    "paper-2": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. We introduce a new language representation model called BERT...",
}


@app.datasource(
    slug="scientific-papers",
    name="Scientific Papers",
    description="A collection of important scientific papers.",
)
async def search_papers(query: str) -> list[Document]:
    """
    A simple data source that performs a keyword search on in-memory documents.
    """
    print(f"Received query for papers: {query}")
    results = []
    for doc_id, content in DUMMY_PAPERS.items():
        if query.lower() in content.lower():
            results.append(
                Document(
                    document_id=doc_id,
                    content=content,
                    metadata={"source": "dummy_db"},
                    similarity_score=0.9,  # Dummy score
                )
            )
    return results


@app.model(
    slug="echo-model",
    name="Echo Model",
    description="A simple model that echoes the last user message.",
)
async def echo_model(messages: list[Message]) -> str:
    """
    A simple model that returns the content of the last user message.
    """
    print(f"Received messages for echo model: {messages}")
    last_user_message = ""
    for msg in reversed(messages):
        if msg.role == "user":
            last_user_message = msg.content
            break
    return f"Echo: {last_user_message}"


async def main() -> None:
    """
    Main function to run the SyftAI Space.
    The server will run on the host and port specified here.
    This host and port must be reachable at the `SPACE_URL`.
    """
    # The SDK will automatically use environment variables for configuration.
    # Uvicorn will be started on 0.0.0.0:8001
    await app.run(host="0.0.0.0", port=8001)


if __name__ == "__main__":
    asyncio.run(main())
