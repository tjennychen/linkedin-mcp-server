"""
LinkedIn connection request tool.

Sends a connection request to a LinkedIn profile using the
authenticated browser session with anti-detection infrastructure.
"""

import logging
from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from linkedin_mcp_server.drivers.browser import (
    ensure_authenticated,
    get_or_create_browser,
)
from linkedin_mcp_server.error_handler import handle_tool_error

logger = logging.getLogger(__name__)


def register_connection_tools(mcp: FastMCP) -> None:
    """Register all connection-related tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Send Connection Request",
            readOnlyHint=False,
            destructiveHint=False,
            openWorldHint=True,
        )
    )
    async def send_connection_request(
        profile_url: str,
        ctx: Context,
        note: str = "",
    ) -> dict[str, Any]:
        """
        Send a LinkedIn connection request to a person.

        Args:
            profile_url: Full LinkedIn profile URL (e.g., "https://www.linkedin.com/in/williamhgates")
            ctx: FastMCP context for progress reporting
            note: Optional personalized note to include with the connection request (max 300 chars).
                  Leave empty to send without a note.

        Returns:
            Dict with success status, profile URL, and any error details.
        """
        try:
            await ensure_authenticated()

            logger.info(
                "Sending connection request to: %s (note=%s)",
                profile_url,
                "yes" if note else "no",
            )

            browser = await get_or_create_browser()
            page = browser.page

            await ctx.report_progress(
                progress=10, total=100, message="Navigating to profile"
            )

            await page.goto(profile_url, wait_until="domcontentloaded")

            await ctx.report_progress(
                progress=30, total=100, message="Looking for Connect button"
            )

            # Try the main Connect button (visible on profile)
            connect_btn = await page.query_selector(
                'button[aria-label*="Connect"]'
            )

            # If not found directly, it may be inside a "More" dropdown
            if not connect_btn:
                more_btn = await page.query_selector(
                    'button[aria-label*="More actions"]'
                )
                if more_btn:
                    await more_btn.click()
                    await page.wait_for_timeout(800)
                    connect_btn = await page.query_selector(
                        '[aria-label*="Connect"]'
                    )

            if not connect_btn:
                return {
                    "success": False,
                    "profile": profile_url,
                    "error": (
                        "Connect button not found. The person may already be a "
                        "connection, a pending request exists, or this profile "
                        "does not allow connection requests."
                    ),
                }

            await connect_btn.click()

            await ctx.report_progress(
                progress=55, total=100, message="Handling connection modal"
            )

            # Wait for the modal to appear
            await page.wait_for_timeout(1000)

            if note:
                # Truncate note to LinkedIn's 300-character limit
                note = note[:300]

                add_note_btn = await page.query_selector(
                    'button:has-text("Add a note")'
                )
                if add_note_btn:
                    await add_note_btn.click()
                    await page.wait_for_timeout(600)

                    message_area = await page.query_selector(
                        'textarea[name="message"]'
                    )
                    if message_area:
                        await message_area.fill(note)
                    else:
                        logger.warning(
                            "Message textarea not found; sending without note"
                        )
                else:
                    logger.warning(
                        "'Add a note' button not found; sending without note"
                    )

            await ctx.report_progress(
                progress=80, total=100, message="Sending connection request"
            )

            # Click Send / Done
            send_btn = await page.query_selector(
                'button:has-text("Send"), button:has-text("Send now")'
            )
            if not send_btn:
                # Fallback: look for the primary action button in the modal
                send_btn = await page.query_selector(
                    '[data-control-name="send_invite"]'
                )

            if not send_btn:
                return {
                    "success": False,
                    "profile": profile_url,
                    "error": "Send button not found after opening connection modal.",
                }

            await send_btn.click()

            await ctx.report_progress(
                progress=100, total=100, message="Connection request sent"
            )

            logger.info("Connection request sent to: %s", profile_url)

            return {
                "success": True,
                "profile": profile_url,
                "note_included": bool(note),
            }

        except Exception as e:
            return handle_tool_error(e, "send_connection_request")
