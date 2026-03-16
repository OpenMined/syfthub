"""Feedback endpoint — proxies user feedback to Linear as issues."""

import logging
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from syfthub.auth.db_dependencies import get_current_active_user
from syfthub.core.config import settings
from syfthub.schemas.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

LINEAR_API_URL = "https://api.linear.app/graphql"


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    success: bool
    message: str
    ticket_id: Optional[str] = Field(
        None, description="Linear issue identifier (e.g. OME-123)"
    )


async def _upload_to_linear(
    filename: str, content: bytes, content_type: str
) -> Optional[str]:
    """Upload a file to Linear and return the asset URL."""
    assert settings.linear_api_key is not None
    api_key: str = settings.linear_api_key
    query = """
    mutation($contentType: String!, $filename: String!, $size: Int!) {
        fileUpload(contentType: $contentType, filename: $filename, size: $size) {
            success
            uploadFile {
                uploadUrl
                assetUrl
                headers { key value }
            }
        }
    }
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            LINEAR_API_URL,
            json={
                "query": query,
                "variables": {
                    "contentType": content_type,
                    "filename": filename,
                    "size": len(content),
                },
            },
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        data = resp.json()

    upload_data = data.get("data", {}).get("fileUpload", {})
    if not upload_data.get("success"):
        logger.warning("Linear file upload request failed: %s", data)
        return None

    upload_file = upload_data["uploadFile"]
    headers = {
        "Content-Type": content_type,
        "Cache-Control": "public, max-age=31536000",
    }
    for h in upload_file.get("headers", []):
        headers[h["key"]] = h["value"]

    async with httpx.AsyncClient() as client:
        await client.put(
            upload_file["uploadUrl"], content=content, headers=headers, timeout=30.0
        )

    asset_url: str = upload_file["assetUrl"]
    return asset_url


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    current_user: Annotated[User, Depends(get_current_active_user)],
    category: str = Form(default="feedback"),
    description: str = Form(...),
    page_url: Optional[str] = Form(default=None),
    app_version: Optional[str] = Form(default=None),
    browser_info: Optional[str] = Form(default=None),
    screenshot: Optional[UploadFile] = File(default=None),
) -> FeedbackResponse:
    """Submit feedback or bug report — creates a Linear issue.

    Uses the authenticated user's email as the reporter.
    """
    if not settings.linear_api_key or not settings.linear_team_id:
        logger.warning("Linear API key or team ID not configured")
        return FeedbackResponse(
            success=False,
            message="Feedback service is not configured.",
            ticket_id=None,
        )

    linear_api_key: str = settings.linear_api_key
    linear_team_id: str = settings.linear_team_id

    category_labels = {"bug": "Bug", "feedback": "Feedback", "idea": "Feature Request"}
    label = category_labels.get(category, "Feedback")
    title = f"[Syft Space] [{label}] {description[:100]}"

    # Build markdown body
    lines = [
        "## Feedback Details",
        f"- Reporter: {current_user.email}",
    ]
    if app_version:
        lines.append(f"- App version: `{app_version}`")
    if page_url:
        lines.append(f"- Page: `{page_url}`")
    if browser_info:
        lines.append(f"- Browser: `{browser_info}`")
    lines.extend(["", "### Description", description])
    body = "\n".join(lines)

    # Upload screenshot if provided
    screenshot_asset_url = None
    if screenshot:
        try:
            content = await screenshot.read()
            screenshot_asset_url = await _upload_to_linear(
                screenshot.filename or "screenshot.png",
                content,
                screenshot.content_type or "image/png",
            )
        except Exception as e:
            logger.warning("Failed to upload screenshot to Linear: %s", e)

    # Create Linear issue
    create_mutation = """
    mutation($input: IssueCreateInput!) {
        issueCreate(input: $input) {
            success
            issue { id identifier }
        }
    }
    """
    variables = {
        "input": {
            "teamId": linear_team_id,
            "title": title,
            "description": body,
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                LINEAR_API_URL,
                json={"query": create_mutation, "variables": variables},
                headers={
                    "Authorization": linear_api_key,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        logger.error("Linear API request failed: %s", e)
        return FeedbackResponse(
            success=False,
            message="Failed to submit feedback. Please try again.",
            ticket_id=None,
        )

    if "errors" in data:
        logger.error("Linear API error: %s", data["errors"])
        return FeedbackResponse(
            success=False, message="Failed to create feedback ticket.", ticket_id=None
        )

    issue_data = data.get("data", {}).get("issueCreate", {})
    if not issue_data.get("success"):
        return FeedbackResponse(
            success=False, message="Failed to create feedback ticket.", ticket_id=None
        )

    issue = issue_data["issue"]
    issue_id = issue["id"]
    identifier = issue["identifier"]

    # Attach screenshot if uploaded
    if screenshot_asset_url:
        attach_mutation = """
        mutation($input: AttachmentCreateInput!) {
            attachmentCreate(input: $input) { success }
        }
        """
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    LINEAR_API_URL,
                    json={
                        "query": attach_mutation,
                        "variables": {
                            "input": {
                                "issueId": issue_id,
                                "url": screenshot_asset_url,
                                "title": "Screenshot",
                                "subtitle": "Auto-captured screenshot",
                            }
                        },
                    },
                    headers={
                        "Authorization": linear_api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=30.0,
                )
        except Exception as e:
            logger.warning("Failed to attach screenshot: %s", e)

    logger.info("Created Linear issue %s for user %s", identifier, current_user.email)
    return FeedbackResponse(
        success=True,
        message="Bug report submitted successfully",
        ticket_id=identifier,
    )
