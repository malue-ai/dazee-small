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
  3. Session lifecycle: browser starts on first call, persists within session
  4. Separation of concerns: browser tool for web, peekaboo for native desktop apps
"""

import asyncio
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from core.tool.types import ToolContext
from tools.base import BaseTool

logger = logging.getLogger(__name__)

# Max characters for text snapshot (prevents context bloat on huge pages)
MAX_SNAPSHOT_CHARS = 8000

# Default action timeout (ms)
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

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return """Automate browser interactions: navigate, read page content, click, type.

Actions:
- navigate: Open a URL. Returns page title.
- snapshot: Get page content as text with interactive element refs [e1], [e2]...
  Use this FIRST to understand the page before acting.
- click: Click an element by ref (e.g. ref="e3"). Run snapshot first to get refs.
- type: Type text into an input field by ref. Use clear=true to replace existing text.
- select: Select a dropdown option by ref + option text.
- screenshot: Capture page image (only when snapshot is insufficient).
- tabs: List open tabs or switch to a tab by id.
- close: Close browser.

Workflow: navigate → snapshot → identify ref → click/type/select → snapshot to verify.
Use snapshot (text) instead of screenshot (image) whenever possible."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate", "snapshot", "click", "type",
                        "select", "screenshot", "tabs", "close",
                        "scroll", "hover", "drag", "fill",
                    ],
                    "description": "Browser action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (navigate action)",
                },
                "ref": {
                    "type": "string",
                    "description": "Element ref from snapshot, e.g. 'e3' (click/type/select/hover/fill)",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (type action), option to select (select action), or text to fill (fill action)",
                },
                "clear": {
                    "type": "boolean",
                    "description": "Clear existing text before typing (type action, default false)",
                },
                "tab_id": {
                    "type": "string",
                    "description": "Tab ID to switch to (tabs action)",
                },
                "scroll_x": {
                    "type": "number",
                    "description": "Horizontal scroll pixels (scroll action, default 0)",
                },
                "scroll_y": {
                    "type": "number",
                    "description": "Vertical scroll pixels (scroll action, positive=down negative=up, default 300)",
                },
                "source_ref": {
                    "type": "string",
                    "description": "Source element ref for drag action",
                },
                "target_ref": {
                    "type": "string",
                    "description": "Target element ref for drag action",
                },
            },
            "required": ["action"],
        }

    # ==================== Lifecycle ====================

    # Browser detection order:
    #   1. Google Chrome  (channel="chrome")   — most users have it
    #   2. Microsoft Edge (channel="msedge")   — pre-installed on Windows
    #   3. Bundled Chromium (no channel)       — fallback, requires download
    #
    # Safari/WebKit: Playwright's WebKit is a custom build, not real Safari.
    # We skip it — Chrome/Edge cover 95%+ of users on both macOS and Windows.

    _BROWSER_CANDIDATES = [
        {"channel": "chrome", "label": "Google Chrome"},
        {"channel": "msedge", "label": "Microsoft Edge"},
        {"channel": None, "label": "Chromium (bundled)"},
    ]

    async def _detect_browser(self) -> Optional[Dict[str, Any]]:
        """
        Detect the best available browser.

        Tries Chrome → Edge → bundled Chromium, returns the first that launches.
        Result is cached for the process lifetime.
        """
        if hasattr(self, "_detected_browser") and self._detected_browser:
            return self._detected_browser

        from playwright.async_api import async_playwright

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

    async def _auto_install_chromium(self) -> bool:
        """
        Auto-install bundled Chromium as last resort.

        Returns True on success.
        """
        try:
            # Use subprocess.run in thread-pool for Windows compatibility
            # (asyncio.create_subprocess_exec may raise NotImplementedError
            #  on Windows SelectorEventLoop)
            try:
                proc = await asyncio.create_subprocess_exec(
                    "playwright", "install", "chromium",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
                rc, err_text = proc.returncode, stderr.decode()[:500]
            except NotImplementedError:
                import subprocess as _sp

                def _run():
                    return _sp.run(
                        ["playwright", "install", "chromium"],
                        capture_output=True, timeout=180,
                    )

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, _run)
                rc, err_text = result.returncode, result.stderr.decode()[:500]

            if rc == 0:
                logger.info("Chromium auto-installed successfully")
                return True
            logger.warning(
                f"Chromium auto-install failed (rc={rc}): {err_text}"
            )
            return False
        except FileNotFoundError:
            logger.warning("playwright CLI not found in PATH")
            return False
        except asyncio.TimeoutError:
            logger.warning("Chromium auto-install timed out (180s)")
            return False
        except Exception as e:
            logger.warning(f"Chromium auto-install error: {e}")
            return False

    async def _ensure_browser(self) -> None:
        """
        Start browser if not running. Thread-safe via lock.

        Detection order: Chrome → Edge → bundled Chromium → auto-install Chromium.
        Zero extra download if user has Chrome or Edge installed.
        """
        if self._browser and self._browser.is_connected():
            return

        async with self._launch_lock:
            # Double-check after acquiring lock
            if self._browser and self._browser.is_connected():
                return

            # 1. Check playwright package
            try:
                import playwright  # noqa: F401
            except ImportError:
                raise RuntimeError(
                    "playwright package not installed. "
                    "Run: pip install playwright"
                )

            # 2. Detect available browser (Chrome → Edge → Chromium)
            candidate = await self._detect_browser()

            if not candidate:
                # 3. No browser found — try auto-install Chromium
                logger.info(
                    "No Chrome/Edge/Chromium found. "
                    "Attempting Chromium auto-install..."
                )
                if await self._auto_install_chromium():
                    candidate = {"channel": None, "label": "Chromium (bundled)"}
                else:
                    raise RuntimeError(
                        "No compatible browser found (Chrome, Edge, or Chromium). "
                        "Please install Google Chrome, or run: "
                        "playwright install chromium"
                    )

            # 4. Launch the detected browser
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()

                launch_args: Dict[str, Any] = {
                    "headless": False,  # Visible browser for desktop agent
                    "args": [
                        "--no-first-run",
                        "--no-default-browser-check",
                        "--disable-infobars",
                    ],
                }
                if candidate.get("channel"):
                    launch_args["channel"] = candidate["channel"]

                self._browser = await self._playwright.chromium.launch(**launch_args)
                self._context = await self._browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    locale="zh-CN",
                )
                logger.info(
                    f"Browser started: {candidate['label']} (headless=False)"
                )
            except Exception as e:
                logger.error(f"Browser launch failed: {e}", exc_info=True)
                raise

    async def _get_active_page(self):
        """Get the currently active page, creating one if needed."""
        await self._ensure_browser()

        if self._active_tab and self._active_tab in self._pages:
            page = self._pages[self._active_tab]
            if not page.is_closed():
                return page

        # Create new tab
        page = await self._context.new_page()
        tab_id = f"tab_{len(self._pages) + 1}"
        self._pages[tab_id] = page
        self._active_tab = tab_id
        return page

    async def _cleanup(self) -> None:
        """Close browser and release resources."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
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
            await locator.click(timeout=DEFAULT_TIMEOUT_MS)
            # Brief wait for UI reaction
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
            fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="browser_")
            os.close(fd)

            await page.screenshot(path=tmp_path, full_page=False)
            return {
                "success": True,
                "path": tmp_path,
                "hint": "Screenshot saved. Prefer snapshot (text) for most tasks.",
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
        page = await self._get_page()
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
        page = await self._get_page()
        ref = params.get("ref")
        if not ref:
            return {"success": False, "error": "ref is required for hover"}
        locator = self._resolve_ref(page, ref)
        await locator.hover(timeout=DEFAULT_TIMEOUT_MS)
        return {"success": True, "hovered": ref}

    async def _drag(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Drag an element to another element."""
        page = await self._get_page()
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
        page = await self._get_page()
        ref = params.get("ref")
        text = params.get("text", "")
        if not ref:
            return {"success": False, "error": "ref is required for fill"}
        locator = self._resolve_ref(page, ref)
        await locator.fill(text, timeout=DEFAULT_TIMEOUT_MS)
        return {"success": True, "filled": ref, "text": text}

    # ==================== Main Dispatch ====================

    async def execute(
        self, params: Dict[str, Any], context: Optional[ToolContext] = None
    ) -> Any:
        action = params.get("action", "")

        dispatch = {
            "navigate": self._navigate,
            "snapshot": self._snapshot,
            "click": self._click,
            "type": self._type,
            "select": self._select,
            "screenshot": self._screenshot,
            "tabs": self._tabs,
            "close": self._close,
            "scroll": self._scroll,
            "hover": self._hover,
            "drag": self._drag,
            "fill": self._fill,
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
                    "install_command": "pip install playwright && playwright install chromium",
                }
            return {"success": False, "error": err_msg}
        except Exception as e:
            logger.error(f"browser.{action} failed: {e}", exc_info=True)
            return {"success": False, "error": f"browser.{action} error: {e}"}
