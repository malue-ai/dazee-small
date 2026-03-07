# -*- coding: utf-8 -*-
"""
Browser automation tool — Playwright-driven, text-snapshot-first.

Architecture:
  1. snapshot (primary) → accessibility tree as text + ref IDs (~50ms)
  2. screenshot (optional) → pixel capture, only when explicitly needed
  3. act (click/type/select) → ref-based semantic targeting, not coordinates

Design principles:
  1. Text-first: snapshot returns pure text, zero image tokens in context
  2. Ref-based targeting: elements addressed by [e1] refs, resolved via role+name
  3. Persistent session: browser profile saved to disk, login state persists across sessions
  4. Separation of concerns: browser tool for web, peekaboo for native desktop apps
"""

import asyncio
import logging
import os
import platform
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_CHARS = 8000

DEFAULT_TIMEOUT_MS = 8000

# Roles that are interactive / actionable (worth assigning a ref)
INTERACTIVE_ROLES = {
    "button", "link", "textbox", "combobox", "checkbox",
    "radio", "tab", "menuitem", "option", "searchbox",
    "spinbutton", "slider", "switch", "textarea", "search",
}

# Regex to parse one line of Playwright's aria_snapshot() output:
#   "- button "Submit":" or "- link "Docs":" or "  - combobox "Search":"
_ARIA_LINE_RE = re.compile(
    r'^(\s*)-\s+'           # indent + dash
    r'(\w+)'                # role (button, link, ...)
    r'(?:\s+"([^"]*)")?'   # optional name in quotes
    r'(.*)$'                # rest (annotations like [level=1])
)


def _parse_aria_snapshot(
    aria_text: str,
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Parse Playwright's aria_snapshot() text, assign ref IDs to interactive elements.

    Input format (from Playwright):
        - heading "Example Domain" [level=1]
        - paragraph: ...
        - search:
          - combobox "Search"
          - button "Go"
        - link "About"

    Output format:
        [e1] search:
          [e2] combobox: Search
          [e3] button: Go
        [e4] link: About
        heading: Example Domain
        paragraph: ...

    Returns:
        (formatted_text, ref_map) where ref_map is {"e1": {"role": "button", "name": "Go"}}
    """
    refs: Dict[str, Dict[str, str]] = {}
    output_lines: List[str] = []
    counter = 1

    for line in aria_text.splitlines():
        # Skip empty lines and metadata lines (like /url:)
        stripped = line.strip()
        if not stripped or stripped.startswith("/url:") or stripped.startswith("- /url:"):
            continue

        m = _ARIA_LINE_RE.match(line)
        if not m:
            # Non-role lines (plain text content, annotations)
            # Include as-is for context
            if stripped.startswith("- text:"):
                text_content = stripped[7:].strip()
                if text_content and len(text_content) > 3:
                    output_lines.append(f"  text: {text_content[:150]}")
            elif not stripped.startswith("-"):
                # Continuation text
                if len(stripped) > 3 and not stripped.startswith("- img"):
                    output_lines.append(f"  {stripped[:150]}")
            continue

        indent = m.group(1)
        role = m.group(2).lower()
        name = m.group(3) or ""
        _rest = m.group(4)

        # Calculate depth from indent (2 spaces per level)
        depth = len(indent) // 2
        out_indent = "  " * depth

        if role in INTERACTIVE_ROLES:
            ref_id = f"e{counter}"
            counter += 1
            refs[ref_id] = {"role": role, "name": name}
            if name:
                output_lines.append(f"{out_indent}[{ref_id}] {role}: {name}")
            else:
                output_lines.append(f"{out_indent}[{ref_id}] {role}")
        elif name:
            # Non-interactive with name (heading, paragraph, etc.)
            display = name[:120] + "..." if len(name) > 120 else name
            output_lines.append(f"{out_indent}{role}: {display}")

    formatted = "\n".join(output_lines)
    return formatted, refs


def _build_snapshot_text(
    page_title: str,
    page_url: str,
    aria_text: str,
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """
    Build the final text snapshot from aria_snapshot() output.

    Returns:
        (snapshot_text, ref_map)
    """
    elements_text, refs = _parse_aria_snapshot(aria_text)

    sections = [
        f"Page: {page_title}",
        f"URL: {page_url}",
        "",
    ]

    if refs:
        sections.append(f"Interactive elements ({len(refs)}):")

    if elements_text:
        sections.append(elements_text)
    else:
        sections.append("(No interactive elements found)")

    snapshot = "\n".join(sections)

    # Truncate if too large
    if len(snapshot) > MAX_SNAPSHOT_CHARS:
        snapshot = snapshot[:MAX_SNAPSHOT_CHARS] + "\n\n[...TRUNCATED — page too large]"

    return snapshot, refs


class BrowserTool(BaseTool):
    """
    Browser automation via Playwright.

    Text-snapshot-first design: snapshot returns pure text with ref IDs,
    screenshot is optional. Refs resolve to semantic locators (role+name),
    not pixel coordinates.
    """

    execution_timeout = 120  # Browser ops may be slow (page loads, etc.)

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: Dict[str, Any] = {}  # tab_id → page
        self._active_tab: Optional[str] = None
        self._ref_cache: Dict[str, Dict[str, Any]] = {}
        self._launch_lock = asyncio.Lock()
        self._listened_pages: set = set()
        self._dialog_history: List[Dict[str, str]] = []
        self._next_dialog_action: Optional[Dict[str, Any]] = None
        self._console_messages: List[Dict[str, str]] = []
        self._network_log: List[Dict[str, Any]] = []
        self._pending_file_chooser: Any = None

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return """Automate browser: navigate, read, click, type, and more. Login persists across sessions.

Actions:
- navigate: Open a URL. go_back / go_forward: history navigation.
- snapshot: Page as text with refs [e1],[e2]... Use FIRST before acting.
- click: Click ref. double_click=true for double-click.
- type: Type text by ref. submit=true to press Enter. clear=true to replace.
- fill: Clear and fill text (reliable for forms).
- select: Select dropdown option by ref + text.
- press_key: Press key (Enter, Escape, Tab, ArrowDown, Control+a...).
- hover: Hover ref (triggers menus/tooltips). drag: Drag source_ref to target_ref.
- scroll: scroll_y=500 (down), -300 (up). Supports ref for element scroll.
- handle_dialog: Pre-set accept/dismiss for next alert/confirm/prompt.
- upload_file: Upload files via ref (clicks input) or after clicking input manually.
- wait_for: Wait for text/text_gone/time (seconds).
- evaluate: Run JavaScript on the page and return result.
- screenshot: Capture image (only when text insufficient). pdf_save: Save as PDF.
- console: Browser console messages. network: Network requests with status codes.
- resize: Resize viewport (width, height).
- tabs: List/switch tabs. new_tab: Open new tab. close: Close browser.

Workflow: navigate → snapshot → identify ref → act → snapshot to verify.
Prefer snapshot (text) over screenshot (image)."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate", "go_back", "go_forward",
                        "snapshot", "click", "type", "fill",
                        "select", "press_key", "hover", "drag", "scroll",
                        "handle_dialog", "upload_file", "wait_for",
                        "evaluate", "screenshot", "pdf_save",
                        "console", "network", "resize",
                        "tabs", "new_tab", "close",
                    ],
                    "description": "Browser action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL (navigate/new_tab)",
                },
                "ref": {
                    "type": "string",
                    "description": "Element ref from snapshot, e.g. 'e3'",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type/fill/select, or text to wait for (wait_for)",
                },
                "clear": {
                    "type": "boolean",
                    "description": "Clear before typing (type, default false)",
                },
                "submit": {
                    "type": "boolean",
                    "description": "Press Enter after typing (type, default false)",
                },
                "double_click": {
                    "type": "boolean",
                    "description": "Double-click (click, default false)",
                },
                "key": {
                    "type": "string",
                    "description": "Key to press (press_key), e.g. 'Enter', 'Escape', 'Control+a'",
                },
                "accept": {
                    "type": "boolean",
                    "description": "Accept or dismiss dialog (handle_dialog, default true)",
                },
                "prompt_text": {
                    "type": "string",
                    "description": "Text for prompt dialog (handle_dialog)",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to upload (upload_file)",
                },
                "text_gone": {
                    "type": "string",
                    "description": "Text to wait for disappearance (wait_for)",
                },
                "time": {
                    "type": "number",
                    "description": "Seconds to wait (wait_for)",
                },
                "expression": {
                    "type": "string",
                    "description": "JavaScript to evaluate (evaluate)",
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (pdf_save/screenshot)",
                },
                "width": {
                    "type": "number",
                    "description": "Viewport width (resize, default 1280)",
                },
                "height": {
                    "type": "number",
                    "description": "Viewport height (resize, default 900)",
                },
                "tab_id": {
                    "type": "string",
                    "description": "Tab ID to switch to (tabs)",
                },
                "scroll_x": {
                    "type": "number",
                    "description": "Horizontal scroll pixels (scroll)",
                },
                "scroll_y": {
                    "type": "number",
                    "description": "Vertical scroll pixels (scroll, positive=down)",
                },
                "source_ref": {
                    "type": "string",
                    "description": "Source element ref (drag)",
                },
                "target_ref": {
                    "type": "string",
                    "description": "Target element ref (drag)",
                },
            },
            "required": ["action"],
        }

    # ==================== Lifecycle ====================

    # Browser detection: Chrome → Edge.
    # macOS/Linux users almost always have Chrome; Windows ships with Edge.
    # No auto-download of Chromium — users should install Chrome or Edge.

    _BROWSER_CANDIDATES = [
        {"channel": "chrome", "label": "Google Chrome"},
        {"channel": "msedge", "label": "Microsoft Edge"},
    ]

    async def _detect_browser(self) -> Optional[Dict[str, Any]]:
        """
        Detect the best available browser (Chrome or Edge).

        Result is cached for the process lifetime.
        """
        if hasattr(self, "_detected_browser") and self._detected_browser:
            return self._detected_browser

        from playwright.async_api import async_playwright  # type: ignore[import-untyped]

        pw = await async_playwright().start()
        try:
            for candidate in self._BROWSER_CANDIDATES:
                channel = candidate["channel"]
                label = candidate["label"]
                try:
                    launch_args: Dict[str, Any] = {"headless": True}
                    if channel:
                        launch_args["channel"] = channel
                    browser = await pw.chromium.launch(**launch_args)
                    await browser.close()
                    logger.info(f"Detected browser: {label}")
                    self._detected_browser = candidate
                    return candidate
                except Exception:
                    logger.debug(f"Browser not available: {label}")
                    continue
            return None
        finally:
            await pw.stop()

    def _get_profile_dir(self) -> str:
        """
        Get persistent browser profile directory.

        Cookies, localStorage, and login sessions are preserved across sessions
        so users only need to log in once per site.
        """
        data_dir = os.environ.get("ZENFLUX_DATA_DIR")
        if data_dir:
            base = Path(data_dir)
        elif platform.system() == "Darwin":
            base = Path.home() / "Library" / "Application Support" / "com.zenflux.agent"
        elif platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", "")) / "com.zenflux.agent"
        else:
            base = Path.home() / ".local" / "share" / "com.zenflux.agent"

        profile_dir = base / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return str(profile_dir)

    def _is_alive(self) -> bool:
        """Check if the browser context is still usable."""
        if not self._context:
            return False
        # persistent context: check via pages (no .is_connected on context)
        # normal browser: check via browser.is_connected()
        if self._browser and hasattr(self._browser, "is_connected"):
            return self._browser.is_connected()
        try:
            return len(self._context.pages) >= 0  # throws if closed
        except Exception:
            return False

    async def _ensure_browser(self) -> None:
        """
        Start browser if not running. Thread-safe via lock.

        Uses launch_persistent_context with a dedicated profile directory
        so that cookies/login sessions persist across agent sessions.
        Detection order: Chrome → Edge.

        Raises RuntimeError if playwright is missing or no browser is found.
        """
        if self._is_alive():
            return

        async with self._launch_lock:
            if self._is_alive():
                return

            try:
                import playwright  # noqa: F401  # type: ignore[import-untyped]
            except ImportError:
                raise RuntimeError(
                    "playwright package not installed. "
                    "Run: pip install playwright"
                )

            candidate = await self._detect_browser()

            if not candidate:
                raise RuntimeError(
                    "No browser found. Please install Google Chrome: "
                    "https://www.google.com/chrome/"
                )

            try:
                from playwright.async_api import async_playwright  # type: ignore[import-untyped]

                self._playwright = await async_playwright().start()

                profile_dir = self._get_profile_dir()
                launch_args: Dict[str, Any] = {
                    "headless": False,
                    "args": [
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-infobars",
                    ],
                    "viewport": {"width": 1280, "height": 900},
                    "locale": "zh-CN",
                }
                if candidate.get("channel"):
                    launch_args["channel"] = candidate["channel"]

                self._context = await self._playwright.chromium.launch_persistent_context(
                    profile_dir, **launch_args
                )
                # persistent context: .browser may be None, store it only if available
                self._browser = self._context.browser
                logger.info(
                    f"Browser started: {candidate['label']} "
                    f"(persistent profile: {profile_dir})"
                )
            except Exception as e:
                logger.error(f"Browser launch failed: {e}", exc_info=True)
                raise

    def _setup_page_listeners(self, page) -> None:
        """Attach dialog/console/network/filechooser listeners to a page."""
        page_id = id(page)
        if page_id in self._listened_pages:
            return
        self._listened_pages.add(page_id)

        async def _on_dialog(dialog):
            info = {"type": dialog.type, "message": dialog.message[:200]}
            if dialog.default_value:
                info["default_value"] = dialog.default_value
            self._dialog_history.append(info)
            if len(self._dialog_history) > 20:
                self._dialog_history = self._dialog_history[-20:]
            if self._next_dialog_action:
                action = self._next_dialog_action
                self._next_dialog_action = None
                if action["accept"]:
                    await dialog.accept(action.get("prompt_text", ""))
                else:
                    await dialog.dismiss()
            else:
                await dialog.dismiss()

        def _on_console(msg):
            try:
                text = msg.text
            except Exception:
                text = "(unreadable)"
            self._console_messages.append({"type": msg.type, "text": text[:500]})
            if len(self._console_messages) > 200:
                self._console_messages = self._console_messages[-200:]

        def _on_response(response):
            self._network_log.append({
                "method": response.request.method,
                "url": response.url[:200],
                "status": response.status,
                "resource_type": response.request.resource_type,
            })
            if len(self._network_log) > 500:
                self._network_log = self._network_log[-500:]

        def _on_filechooser(file_chooser):
            self._pending_file_chooser = file_chooser

        page.on("dialog", _on_dialog)
        page.on("console", _on_console)
        page.on("response", _on_response)
        page.on("filechooser", _on_filechooser)

    async def _get_active_page(self):
        """Get the currently active page, creating one if needed."""
        await self._ensure_browser()

        if self._active_tab and self._active_tab in self._pages:
            page = self._pages[self._active_tab]
            if not page.is_closed():
                self._setup_page_listeners(page)
                return page

        if not self._context:
            raise RuntimeError("Browser context not initialized")

        existing = self._context.pages
        if existing and not self._pages:
            page = existing[-1]
            tab_id = "tab_1"
            self._pages[tab_id] = page
            self._active_tab = tab_id
            self._setup_page_listeners(page)
            return page

        page = await self._context.new_page()
        tab_id = f"tab_{len(self._pages) + 1}"
        self._pages[tab_id] = page
        self._active_tab = tab_id
        self._setup_page_listeners(page)
        return page

    async def _cleanup(self) -> None:
        """Close browser and release resources."""
        try:
            # persistent context: closing context is sufficient (no separate browser)
            # normal browser: close context first, then browser
            if self._context:
                await self._context.close()
            if self._browser and self._browser != self._context:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Browser cleanup error: {e}")
        finally:
            self._playwright = None
            self._browser = None
            self._context = None
            self._pages.clear()
            self._active_tab = None
            self._ref_cache.clear()
            self._listened_pages.clear()
            self._dialog_history.clear()
            self._next_dialog_action = None
            self._console_messages.clear()
            self._network_log.clear()
            self._pending_file_chooser = None

    # ==================== Ref Resolution ====================

    def _resolve_ref(self, page, ref: str):
        """
        Resolve a ref ID (e.g. "e3") to a Playwright locator.

        Uses role+name from the cached accessibility snapshot.
        Falls back to aria-ref locator.
        """
        ref = ref.strip().lower()
        if not ref.startswith("e"):
            ref = f"e{ref}"

        info = self._ref_cache.get(ref)
        if not info:
            raise ValueError(
                f"Unknown ref '{ref}'. Run snapshot first to get current refs."
            )

        role = info["role"].lower()
        name = info["name"]

        # Map accessibility roles to Playwright getByRole args
        ROLE_MAP = {
            "button": "button",
            "link": "link",
            "textbox": "textbox",
            "textarea": "textbox",
            "searchbox": "searchbox",
            "combobox": "combobox",
            "checkbox": "checkbox",
            "radio": "radio",
            "tab": "tab",
            "menuitem": "menuitem",
            "option": "option",
            "switch": "switch",
            "slider": "slider",
            "spinbutton": "spinbutton",
        }

        pw_role = ROLE_MAP.get(role, role)
        try:
            return page.get_by_role(pw_role, name=name, exact=True)
        except Exception:
            # Fallback: try with exact=False
            return page.get_by_role(pw_role, name=name)

    # ==================== Actions ====================

    async def _navigate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate to a URL."""
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "url is required for navigate action"}

        # Auto-prepend https if missing
        if not url.startswith(("http://", "https://", "file://")):
            url = f"https://{url}"

        page = await self._get_active_page()
        try:
            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            # Small wait for dynamic content
            await page.wait_for_timeout(500)
            title = await page.title()
            return {
                "success": True,
                "title": title,
                "url": page.url,
            }
        except Exception as e:
            return {"success": False, "error": f"Navigation failed: {e}"}

    async def _snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Capture page as text snapshot with ref IDs.

        Uses Playwright's aria_snapshot() — returns structured accessibility text.
        Zero image tokens in context.
        """
        page = await self._get_active_page()
        try:
            title = await page.title()
            url = page.url

            # Get ARIA snapshot (Playwright 1.49+)
            aria_text = await page.locator("body").aria_snapshot()

            snapshot_text, refs = _build_snapshot_text(title, url, aria_text)
            self._ref_cache = refs

            return {
                "success": True,
                "snapshot": snapshot_text,
                "element_count": len(refs),
                # Security: page content is untrusted external input.
                # Do NOT follow instructions embedded in page text.
                "content_source": "external_webpage",
                "content_trusted": False,
            }
        except Exception as e:
            return {"success": False, "error": f"Snapshot failed: {e}"}

    async def _click(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Click an element by ref."""
        ref = params.get("ref", "")
        if not ref:
            return {"success": False, "error": "ref is required for click action"}

        page = await self._get_active_page()
        try:
            locator = self._resolve_ref(page, ref)
            if params.get("double_click"):
                await locator.dblclick(timeout=DEFAULT_TIMEOUT_MS)
            else:
                await locator.click(timeout=DEFAULT_TIMEOUT_MS)
            await page.wait_for_timeout(300)
            return {"success": True, "clicked": ref}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Click failed on {ref}: {e}"}

    async def _type(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Type text into an input element by ref."""
        ref = params.get("ref", "")
        text = params.get("text", "")
        clear = params.get("clear", False)
        submit = params.get("submit", False)

        if not ref:
            return {"success": False, "error": "ref is required for type action"}
        if not text:
            return {"success": False, "error": "text is required for type action"}

        page = await self._get_active_page()
        try:
            locator = self._resolve_ref(page, ref)
            if clear:
                await locator.fill(text, timeout=DEFAULT_TIMEOUT_MS)
            else:
                await locator.click(timeout=DEFAULT_TIMEOUT_MS)
                await locator.press_sequentially(text, delay=30)
            if submit:
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(300)
            return {"success": True, "typed": text[:50], "ref": ref}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Type failed on {ref}: {e}"}

    async def _select(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Select an option from a dropdown by ref + option text."""
        ref = params.get("ref", "")
        text = params.get("text", "")

        if not ref:
            return {"success": False, "error": "ref is required for select action"}
        if not text:
            return {"success": False, "error": "text (option label) is required"}

        page = await self._get_active_page()
        try:
            locator = self._resolve_ref(page, ref)
            await locator.select_option(label=text, timeout=DEFAULT_TIMEOUT_MS)
            return {"success": True, "selected": text, "ref": ref}
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            # Fallback: click the dropdown, then click the option text
            try:
                locator = self._resolve_ref(page, ref)
                await locator.click(timeout=DEFAULT_TIMEOUT_MS)
                await page.wait_for_timeout(300)
                await page.get_by_text(text, exact=True).click(
                    timeout=DEFAULT_TIMEOUT_MS
                )
                return {"success": True, "selected": text, "ref": ref}
            except Exception as e2:
                return {
                    "success": False,
                    "error": f"Select failed on {ref}: {e}. Fallback also failed: {e2}",
                }

    async def _screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Capture page screenshot (use only when text snapshot is insufficient).

        Returns file path, not image data — keeps context lean.
        """
        page = await self._get_active_page()
        try:
            out_path = params.get("filename")
            if not out_path:
                fd, out_path = tempfile.mkstemp(suffix=".png", prefix="browser_")
                os.close(fd)

            await page.screenshot(path=out_path, full_page=False)
            return {
                "success": True,
                "path": out_path,
                "hint": "Screenshot saved. Prefer snapshot (text) for most tasks.",
                "content_source": "external_webpage",
                "content_trusted": False,
            }
        except Exception as e:
            return {"success": False, "error": f"Screenshot failed: {e}"}

    async def _tabs(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List open tabs or switch to a specific tab."""
        tab_id = params.get("tab_id", "")

        if tab_id:
            # Switch to specified tab
            if tab_id not in self._pages:
                return {
                    "success": False,
                    "error": f"Tab '{tab_id}' not found. Available: {list(self._pages.keys())}",
                }
            page = self._pages[tab_id]
            if page.is_closed():
                del self._pages[tab_id]
                return {"success": False, "error": f"Tab '{tab_id}' is closed"}
            self._active_tab = tab_id
            await page.bring_to_front()
            title = await page.title()
            return {"success": True, "active_tab": tab_id, "title": title}

        # List all tabs
        tab_list = []
        for tid, page in list(self._pages.items()):
            if page.is_closed():
                del self._pages[tid]
                continue
            try:
                title = await page.title()
            except Exception:
                title = "(error)"
            tab_list.append({
                "id": tid,
                "title": title,
                "url": page.url,
                "active": tid == self._active_tab,
            })

        return {"success": True, "tabs": tab_list, "count": len(tab_list)}

    async def _close(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Close browser and release all resources."""
        await self._cleanup()
        return {"success": True, "message": "Browser closed"}

    # ==================== Extended Actions ====================

    async def _scroll(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Scroll the page or a specific element."""
        page = await self._get_active_page()
        ref = params.get("ref")
        scroll_x = params.get("scroll_x", 0)
        scroll_y = params.get("scroll_y", 300)

        if ref:
            locator = self._resolve_ref(page, ref)
            await locator.scroll_into_view_if_needed(timeout=DEFAULT_TIMEOUT_MS)
            bbox = await locator.bounding_box()
            if bbox:
                # Move mouse to element center before scrolling
                cx = bbox["x"] + bbox["width"] / 2
                cy = bbox["y"] + bbox["height"] / 2
                await page.mouse.move(cx, cy)

        await page.mouse.wheel(scroll_x, scroll_y)
        await page.wait_for_timeout(300)
        return {"success": True, "scrolled": {"x": scroll_x, "y": scroll_y}, "ref": ref}

    async def _hover(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Hover over an element (triggers dropdowns, tooltips, etc.)."""
        page = await self._get_active_page()
        ref = params.get("ref")
        if not ref:
            return {"success": False, "error": "ref is required for hover"}
        locator = self._resolve_ref(page, ref)
        await locator.hover(timeout=DEFAULT_TIMEOUT_MS)
        return {"success": True, "hovered": ref}

    async def _drag(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Drag an element to another element."""
        page = await self._get_active_page()
        source_ref = params.get("source_ref")
        target_ref = params.get("target_ref")
        if not source_ref or not target_ref:
            return {"success": False, "error": "source_ref and target_ref are required for drag"}
        source = self._resolve_ref(page, source_ref)
        target = self._resolve_ref(page, target_ref)
        await source.drag_to(target, timeout=DEFAULT_TIMEOUT_MS)
        return {"success": True, "dragged": source_ref, "to": target_ref}

    async def _fill(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Clear field and fill with text (more reliable than type for forms)."""
        page = await self._get_active_page()
        ref = params.get("ref")
        text = params.get("text", "")
        if not ref:
            return {"success": False, "error": "ref is required for fill"}
        locator = self._resolve_ref(page, ref)
        await locator.fill(text, timeout=DEFAULT_TIMEOUT_MS)
        return {"success": True, "filled": ref, "text": text}

    # ==================== Advanced Actions ====================

    async def _press_key(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Press a keyboard key or key combination."""
        key = params.get("key", "")
        if not key:
            return {
                "success": False,
                "error": "key is required, e.g. 'Enter', 'Escape', 'Control+a'",
            }
        page = await self._get_active_page()
        try:
            await page.keyboard.press(key)
            return {"success": True, "pressed": key}
        except Exception as e:
            return {"success": False, "error": f"Press key failed: {e}"}

    async def _handle_dialog(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Pre-set handler for the next browser dialog (alert/confirm/prompt).

        Dialogs are auto-dismissed by default. Call this BEFORE the action
        that triggers the dialog to control accept/dismiss behavior.
        """
        accept = params.get("accept", True)
        prompt_text = params.get("prompt_text", "")
        self._next_dialog_action = {"accept": accept, "prompt_text": prompt_text}
        return {
            "success": True,
            "handler_set": "accept" if accept else "dismiss",
            "recent_dialogs": self._dialog_history[-3:],
        }

    async def _upload_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Upload files to a file input element.

        Two patterns supported:
          1. Provide ref → clicks the file input and uploads in one step.
          2. Click a file input first, then call upload_file with just paths.
        """
        paths = params.get("paths", [])
        ref = params.get("ref")
        page = await self._get_active_page()

        try:
            if self._pending_file_chooser:
                fc = self._pending_file_chooser
                self._pending_file_chooser = None
                await fc.set_files(paths if paths else [])
                names = [os.path.basename(p) for p in paths]
                return {"success": True, "uploaded": names}

            if ref:
                locator = self._resolve_ref(page, ref)
                async with page.expect_file_chooser(
                    timeout=DEFAULT_TIMEOUT_MS
                ) as fc_info:
                    await locator.click(timeout=DEFAULT_TIMEOUT_MS)
                fc = await fc_info.value
                await fc.set_files(paths if paths else [])
                names = [os.path.basename(p) for p in paths]
                return {"success": True, "uploaded": names}

            return {
                "success": False,
                "error": (
                    "No file chooser pending. Provide ref to click a file input, "
                    "or click it first then call upload_file."
                ),
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"File upload failed: {e}"}

    async def _wait_for(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Wait for text to appear/disappear, or a specified time."""
        text = params.get("text")
        text_gone = params.get("text_gone")
        time_s = params.get("time")
        page = await self._get_active_page()

        try:
            if time_s is not None:
                ms = int(float(time_s) * 1000)
                await page.wait_for_timeout(ms)
                return {"success": True, "waited_seconds": time_s}
            if text:
                await page.get_by_text(text).wait_for(
                    state="visible", timeout=30000
                )
                return {"success": True, "text_found": text}
            if text_gone:
                await page.get_by_text(text_gone).wait_for(
                    state="hidden", timeout=30000
                )
                return {"success": True, "text_gone": text_gone}
            return {
                "success": False,
                "error": "Provide text, text_gone, or time",
            }
        except Exception as e:
            return {"success": False, "error": f"Wait failed: {e}"}

    async def _go_back(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate back in browser history."""
        page = await self._get_active_page()
        try:
            await page.go_back(timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)
            return {
                "success": True,
                "title": await page.title(),
                "url": page.url,
            }
        except Exception as e:
            return {"success": False, "error": f"Go back failed: {e}"}

    async def _go_forward(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Navigate forward in browser history."""
        page = await self._get_active_page()
        try:
            await page.go_forward(timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)
            return {
                "success": True,
                "title": await page.title(),
                "url": page.url,
            }
        except Exception as e:
            return {"success": False, "error": f"Go forward failed: {e}"}

    async def _console(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return collected browser console messages."""
        recent = self._console_messages[-50:]
        return {
            "success": True,
            "messages": recent,
            "total": len(self._console_messages),
        }

    async def _network(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return collected network requests (excludes static resources)."""
        static_types = {"image", "font", "media", "stylesheet"}
        filtered = [
            r for r in self._network_log
            if r.get("resource_type") not in static_types
        ]
        recent = filtered[-50:]
        return {
            "success": True,
            "requests": recent,
            "total": len(filtered),
        }

    async def _pdf_save(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Save the current page as PDF."""
        page = await self._get_active_page()
        out_path = params.get("filename")
        try:
            if not out_path:
                fd, out_path = tempfile.mkstemp(suffix=".pdf", prefix="browser_")
                os.close(fd)
            await page.pdf(path=out_path)
            return {"success": True, "path": out_path}
        except Exception as e:
            return {
                "success": False,
                "error": f"PDF save failed: {e}. PDF requires headless mode (Chrome).",
            }

    async def _resize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resize the browser viewport."""
        width = int(params.get("width", 1280))
        height = int(params.get("height", 900))
        page = await self._get_active_page()
        try:
            await page.set_viewport_size({"width": width, "height": height})
            return {"success": True, "viewport": {"width": width, "height": height}}
        except Exception as e:
            return {"success": False, "error": f"Resize failed: {e}"}

    async def _evaluate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute JavaScript on the page and return the result."""
        expression = params.get("expression", "")
        if not expression:
            return {"success": False, "error": "expression is required"}
        page = await self._get_active_page()
        try:
            result = await page.evaluate(expression)
            result_str = str(result)
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "\n[...TRUNCATED]"
            return {"success": True, "result": result_str}
        except Exception as e:
            return {"success": False, "error": f"Evaluate failed: {e}"}

    async def _new_tab(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Open a new browser tab, optionally navigating to a URL."""
        url = params.get("url", "about:blank")
        if url != "about:blank" and not url.startswith(
            ("http://", "https://", "file://")
        ):
            url = f"https://{url}"
        try:
            await self._ensure_browser()
            if not self._context:
                return {"success": False, "error": "Browser context not available"}
            page = await self._context.new_page()
            tab_id = f"tab_{len(self._pages) + 1}"
            self._pages[tab_id] = page
            self._active_tab = tab_id
            self._setup_page_listeners(page)
            if url != "about:blank":
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            title = await page.title()
            return {
                "success": True,
                "tab_id": tab_id,
                "title": title,
                "url": page.url,
            }
        except Exception as e:
            return {"success": False, "error": f"New tab failed: {e}"}

    # ==================== Main Dispatch ====================

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Any:
        action = params.get("action", "")

        dispatch = {
            "navigate": self._navigate,
            "go_back": self._go_back,
            "go_forward": self._go_forward,
            "snapshot": self._snapshot,
            "click": self._click,
            "type": self._type,
            "fill": self._fill,
            "select": self._select,
            "press_key": self._press_key,
            "hover": self._hover,
            "drag": self._drag,
            "scroll": self._scroll,
            "handle_dialog": self._handle_dialog,
            "upload_file": self._upload_file,
            "wait_for": self._wait_for,
            "evaluate": self._evaluate,
            "screenshot": self._screenshot,
            "pdf_save": self._pdf_save,
            "console": self._console,
            "network": self._network,
            "resize": self._resize,
            "tabs": self._tabs,
            "new_tab": self._new_tab,
            "close": self._close,
        }

        handler = dispatch.get(action)
        if not handler:
            return {
                "success": False,
                "error": f"Unknown action '{action}'. Available: {list(dispatch.keys())}",
            }

        try:
            return await handler(params)
        except RuntimeError as e:
            # Installation / setup errors — return friendly message
            err_msg = str(e)
            if "not installed" in err_msg or "not downloaded" in err_msg:
                return {
                    "success": False,
                    "error": err_msg,
                    "needs_install": True,
                    "install_command": "pip install playwright",
                }
            return {"success": False, "error": err_msg}
        except Exception as e:
            logger.error(f"browser.{action} failed: {e}", exc_info=True)
            return {"success": False, "error": f"browser.{action} error: {e}"}
