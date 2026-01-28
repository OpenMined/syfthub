#!/usr/bin/env python3
"""Script to ingest existing public endpoints into the RAG vector store.

This script should be run once after deploying the RAG feature to index
all existing public endpoints that don't have a RAG file ID.

Usage:
    python scripts/ingest_existing_endpoints.py [--dry-run] [--batch-size N]

Options:
    --dry-run       Show what would be ingested without actually doing it
    --batch-size N  Number of endpoints to process in each batch (default: 50)
"""

import argparse
import logging
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import Session

from syfthub.core.config import settings
from syfthub.models.endpoint import EndpointModel
from syfthub.services.rag_service import RAGService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def ingest_existing_endpoints(
    dry_run: bool = False,
    batch_size: int = 50,
) -> dict[str, int]:
    """Ingest all existing public endpoints into RAG.

    Args:
        dry_run: If True, only show what would be done without making changes.
        batch_size: Number of endpoints to process in each batch.

    Returns:
        Dictionary with counts: {"total", "ingested", "skipped", "failed"}
    """
    stats = {"total": 0, "ingested": 0, "skipped": 0, "failed": 0}

    # Check if RAG is available
    if not settings.rag_available:
        logger.error(
            "RAG is not available. Please set OPENAI_API_KEY and ensure rag_enabled=True"
        )
        return stats

    # Create database engine and session
    engine = create_engine(settings.database_url)

    # Create RAG service
    rag_service = RAGService()
    if not rag_service.is_available:
        logger.error("RAG service is not available")
        return stats

    logger.info(f"Starting ingestion (dry_run={dry_run}, batch_size={batch_size})")

    with Session(engine) as session:
        # Query for public endpoints without RAG file IDs
        stmt = select(EndpointModel).where(
            and_(
                EndpointModel.visibility == "public",
                EndpointModel.is_active == True,  # noqa: E712
                EndpointModel.rag_file_id.is_(None),
            )
        )

        endpoints = session.execute(stmt).scalars().all()
        stats["total"] = len(endpoints)

        logger.info(f"Found {stats['total']} public endpoints to ingest")

        if dry_run:
            for endpoint in endpoints:
                logger.info(
                    f"[DRY RUN] Would ingest endpoint {endpoint.id}: "
                    f"{endpoint.name} ({endpoint.slug})"
                )
            return stats

        # Process in batches
        for i in range(0, len(endpoints), batch_size):
            batch = endpoints[i : i + batch_size]
            logger.info(
                f"Processing batch {i // batch_size + 1} ({len(batch)} endpoints)"
            )

            for endpoint in batch:
                try:
                    file_id = rag_service.ingest_endpoint(endpoint)
                    if file_id:
                        endpoint.rag_file_id = file_id
                        stats["ingested"] += 1
                        logger.info(
                            f"Ingested endpoint {endpoint.id}: {endpoint.name} "
                            f"(file_id: {file_id})"
                        )
                    else:
                        stats["failed"] += 1
                        logger.warning(
                            f"Failed to ingest endpoint {endpoint.id}: {endpoint.name}"
                        )
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(
                        f"Error ingesting endpoint {endpoint.id}: {e}",
                        exc_info=True,
                    )

            # Commit after each batch
            session.commit()
            logger.info(f"Committed batch {i // batch_size + 1}")

    return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ingest existing public endpoints into RAG vector store"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be ingested without making changes",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of endpoints to process in each batch (default: 50)",
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("RAG Ingestion Script for Existing Endpoints")
    logger.info("=" * 60)

    # Check configuration
    logger.info(f"Database URL: {settings.database_url}")
    logger.info(f"RAG enabled: {settings.rag_enabled}")
    logger.info(f"OpenAI API key configured: {bool(settings.openai_api_key)}")
    logger.info(f"Vector store name: {settings.openai_vector_store_name}")

    if not settings.rag_available:
        logger.error("RAG is not available. Exiting.")
        sys.exit(1)

    # Run ingestion
    stats = ingest_existing_endpoints(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    # Print summary
    logger.info("=" * 60)
    logger.info("Ingestion Summary")
    logger.info("=" * 60)
    logger.info(f"Total endpoints found: {stats['total']}")
    logger.info(f"Successfully ingested: {stats['ingested']}")
    logger.info(f"Skipped: {stats['skipped']}")
    logger.info(f"Failed: {stats['failed']}")

    if stats["failed"] > 0:
        logger.warning(
            f"{stats['failed']} endpoints failed to ingest. Check the logs for details."
        )
        sys.exit(1)

    logger.info("Ingestion completed successfully!")


if __name__ == "__main__":
    main()
