"""Reliable Playwright-based MCP server for browser automation.

Fixes the CDP connection issues in browser_use.mcp by managing
Playwright browser sessions directly.
"""

import asyncio
import base64
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING, stream=sys.stderr, force=True)
logger = logging.getLogger("playwright_mcp")

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    print("playwright not installed. Install with: pip install playwright && playwright install chromium", file=sys.stderr)
    sys.exit(1)

try:
    import mcp.server.stdio
    import mcp.types as types
    from mcp.server import NotificationOptions, Server
    from mcp.server.models import InitializationOptions

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("MCP SDK not installed. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)


class PlaywrightMCPServer:
    def __init__(self):
        self.server = Server("playwright-browser")
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._tabs: dict[str, Page] = {}
        self._current_tab_id: str | None = None
        self._setup_handlers()

    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="browser_navigate",
                    description="Navigate to a URL in the browser",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "The URL to navigate to"},
                            "new_tab": {"type": "boolean", "description": "Whether to open in a new tab", "default": False},
                        },
                        "required": ["url"],
                    },
                ),
                types.Tool(
                    name="browser_click",
                    description="Click an element by index or at specific viewport coordinates",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "The index of the element to click (from browser_get_state)"},
                            "coordinate_x": {"type": "integer", "description": "X coordinate in pixels"},
                            "coordinate_y": {"type": "integer", "description": "Y coordinate in pixels"},
                        },
                    },
                ),
                types.Tool(
                    name="browser_type",
                    description="Type text into an input field. Clears existing text by default.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer", "description": "The index of the input element (from browser_get_state)"},
                            "text": {"type": "string", "description": "The text to type"},
                        },
                        "required": ["index", "text"],
                    },
                ),
                types.Tool(
                    name="browser_get_state",
                    description="Get the current state of the page including all interactive elements",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "include_screenshot": {
                                "type": "boolean",
                                "description": "Whether to include a screenshot of the current page",
                                "default": False,
                            }
                        },
                    },
                ),
                types.Tool(
                    name="browser_get_html",
                    description="Get the raw HTML of the current page or a specific element by CSS selector",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "Optional CSS selector to get HTML of a specific element",
                            },
                        },
                    },
                ),
                types.Tool(
                    name="browser_screenshot",
                    description="Take a screenshot of the current page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "full_page": {
                                "type": "boolean",
                                "description": "Whether to capture the full scrollable page",
                                "default": False,
                            },
                        },
                    },
                ),
                types.Tool(
                    name="browser_scroll",
                    description="Scroll the page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "direction": {
                                "type": "string",
                                "enum": ["up", "down"],
                                "description": "Direction to scroll",
                                "default": "down",
                            }
                        },
                    },
                ),
                types.Tool(
                    name="browser_go_back",
                    description="Go back to the previous page",
                    inputSchema={"type": "object", "properties": {}},
                ),
                types.Tool(
                    name="browser_list_tabs",
                    description="List all open tabs",
                    inputSchema={"type": "object", "properties": {}},
                ),
                types.Tool(
                    name="browser_switch_tab",
                    description="Switch to a different tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tab_id": {"type": "string", "description": "4 Character Tab ID of the tab to switch to"}
                        },
                        "required": ["tab_id"],
                    },
                ),
                types.Tool(
                    name="browser_close_tab",
                    description="Close a tab",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tab_id": {"type": "string", "description": "4 Character Tab ID of the tab to close"}
                        },
                        "required": ["tab_id"],
                    },
                ),
                types.Tool(
                    name="browser_list_sessions",
                    description="List all active browser sessions",
                    inputSchema={"type": "object", "properties": {}},
                ),
                types.Tool(
                    name="browser_close_all",
                    description="Close all active browser sessions and clean up resources",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> list[types.TextContent | types.ImageContent]:
            try:
                return await self._execute_tool(name, arguments or {})
            except Exception as e:
                logger.error(f"Tool execution failed: {e}", exc_info=True)
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def _ensure_browser(self):
        if self._page is not None:
            return
        self._playwright = await async_playwright().start()
        channel = os.environ.get("PLAYWRIGHT_BROWSER", "msedge")
        executable_path = os.environ.get("PLAYWRIGHT_BROWSER_BINARY", None)
        headless = os.environ.get("PLAYWRIGHT_HEADLESS", "0") != "1"

        launch_options = {"headless": headless, "channel": channel}
        if executable_path:
            del launch_options["channel"]
            launch_options["executable_path"] = executable_path

        self._browser = await self._playwright.chromium.launch(**launch_options)
        self._context = await self._browser.new_context(no_viewport=True)
        self._page = await self._context.new_page()
        self._current_tab_id = id(self._page)
        self._tabs[self._current_tab_id] = self._page

    async def _get_page(self, tab_id: str | None = None) -> Page:
        await self._ensure_browser()
        if tab_id is None:
            return self._page
        if tab_id in self._tabs:
            return self._tabs[tab_id]
        for tid, page in self._tabs.items():
            if str(tid)[-4:] == tab_id:
                return page
        raise ValueError(f"Tab {tab_id} not found")

    async def _get_interactive_elements(self, page: Page) -> list[dict]:
        elements = await page.evaluate("""
            () => {
                const interactives = document.querySelectorAll(
                    'a, button, input, select, textarea, [role="button"], [role="link"], ' +
                    '[role="checkbox"], [role="radio"], [tabindex]:not([tabindex="-1"])'
                );
                const results = [];
                let index = 0;
                for (const el of interactives) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        const tag = el.tagName.toLowerCase();
                        const text = (el.textContent || '').trim().substring(0, 100);
                        const placeholder = el.getAttribute('placeholder') || '';
                        const href = el.getAttribute('href') || '';
                        const type = el.getAttribute('type') || '';
                        results.push({
                            index,
                            tag,
                            text,
                            placeholder,
                            href,
                            type,
                            rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}
                        });
                        index++;
                    }
                }
                return results;
            }
        """)
        return elements

    async def _execute_tool(self, name: str, args: dict) -> list[types.TextContent | types.ImageContent]:
        if name == "browser_list_sessions":
            return [types.TextContent(type="text", text=json.dumps({"active": self._page is not None}, indent=2))]

        if name == "browser_close_all":
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            self._page = None
            self._browser = None
            self._playwright = None
            self._tabs = {}
            return [types.TextContent(type="text", text="All sessions closed")]

        await self._ensure_browser()

        if name == "browser_navigate":
            url = args["url"]
            new_tab = args.get("new_tab", False)
            if new_tab:
                self._page = await self._context.new_page()
                self._current_tab_id = id(self._page)
                self._tabs[self._current_tab_id] = self._page
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            return [types.TextContent(type="text", text=f"Navigated to: {url}")]

        elif name == "browser_click":
            page = self._page
            index = args.get("index")
            coord_x = args.get("coordinate_x")
            coord_y = args.get("coordinate_y")

            if coord_x is not None and coord_y is not None:
                await page.mouse.click(coord_x, coord_y)
                return [types.TextContent(type="text", text=f"Clicked at coordinates ({coord_x}, {coord_y})")]

            if index is not None:
                elements = await self._get_interactive_elements(page)
                if index < 0 or index >= len(elements):
                    return [types.TextContent(type="text", text=f"Error: Element with index {index} not found")]
                el = elements[index]
                await page.mouse.click(el["rect"]["x"] + el["rect"]["width"] / 2, el["rect"]["y"] + el["rect"]["height"] / 2)
                return [types.TextContent(type="text", text=f"Clicked element {index}")]

            return [types.TextContent(type="text", text="Error: Provide either index or both coordinate_x and coordinate_y")]

        elif name == "browser_type":
            page = self._page
            index = args.get("index")
            text = args.get("text", "")

            elements = await self._get_interactive_elements(page)
            if index < 0 or index >= len(elements):
                return [types.TextContent(type="text", text=f"Error: Element with index {index} not found")]

            el = elements[index]
            await page.mouse.click(el["rect"]["x"] + el["rect"]["width"] / 2, el["rect"]["y"] + el["rect"]["height"] / 2)
            await page.keyboard.press("Control+a")
            await page.keyboard.type(text)
            return [types.TextContent(type="text", text=f"Typed '{text}' into element {index}")]

        elif name == "browser_get_state":
            page = self._page
            include_screenshot = args.get("include_screenshot", False)

            url = page.url
            title = await page.title()
            viewport = await page.evaluate("({width: window.innerWidth, height: window.innerHeight})")
            page_dim = await page.evaluate("({width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight})")
            scroll = await page.evaluate("({x: window.scrollX, y: window.scrollY})")
            elements = await self._get_interactive_elements(page)

            tabs_info = []
            for tid, p in self._tabs.items():
                try:
                    tabs_info.append({"url": p.url, "title": await p.title()})
                except Exception:
                    tabs_info.append({"url": "unknown", "title": "unknown"})

            result = {
                "url": url,
                "title": title,
                "tabs": tabs_info,
                "viewport": {"width": viewport["width"], "height": viewport["height"]},
                "page": {"width": page_dim["width"], "height": page_dim["height"]},
                "scroll": {"x": scroll["x"], "y": scroll["y"]},
                "interactive_elements": elements,
            }

            content: list[types.TextContent | types.ImageContent] = [types.TextContent(type="text", text=json.dumps(result, indent=2))]
            if include_screenshot:
                screenshot_bytes = await page.screenshot(full_page=False)
                b64 = base64.b64encode(screenshot_bytes).decode()
                content.append(types.ImageContent(type="image", data=b64, mimeType="image/png"))
            return content

        elif name == "browser_get_html":
            page = self._page
            selector = args.get("selector")
            if selector:
                html = await page.evaluate(f"""
                    (() => {{ const el = document.querySelector({json.dumps(selector)}); return el ? el.outerHTML : null; }})()
                """)
                if html is None:
                    return [types.TextContent(type="text", text=f"No element found for selector: {selector}")]
                return [types.TextContent(type="text", text=html)]
            html = await page.content()
            return [types.TextContent(type="text", text=html)]

        elif name == "browser_screenshot":
            page = self._page
            full_page = args.get("full_page", False)
            screenshot_bytes = await page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode()
            meta = json.dumps({"size_bytes": len(screenshot_bytes), "viewport": {"width": await page.evaluate("window.innerWidth"), "height": await page.evaluate("window.innerHeight")}})
            return [types.TextContent(type="text", text=meta), types.ImageContent(type="image", data=b64, mimeType="image/png")]

        elif name == "browser_scroll":
            page = self._page
            direction = args.get("direction", "down")
            amount = 500 if direction == "down" else -500
            await page.evaluate(f"window.scrollBy(0, {amount})")
            return [types.TextContent(type="text", text=f"Scrolled {direction}")]

        elif name == "browser_go_back":
            await self._page.go_back()
            return [types.TextContent(type="text", text="Navigated back")]

        elif name == "browser_list_tabs":
            tabs = []
            for tid, p in self._tabs.items():
                try:
                    tabs.append({"tab_id": str(tid)[-4:], "url": p.url, "title": await p.title()})
                except Exception:
                    pass
            return [types.TextContent(type="text", text=json.dumps(tabs, indent=2))]

        elif name == "browser_switch_tab":
            tab_id = args["tab_id"]
            for tid, p in self._tabs.items():
                if str(tid)[-4:] == tab_id:
                    self._page = p
                    self._current_tab_id = tid
                    await p.bring_to_front()
                    return [types.TextContent(type="text", text=f"Switched to tab {tab_id}: {p.url}")]
            return [types.TextContent(type="text", text=f"Tab {tab_id} not found")]

        elif name == "browser_close_tab":
            tab_id = args["tab_id"]
            for tid, p in list(self._tabs.items()):
                if str(tid)[-4:] == tab_id:
                    await p.close()
                    del self._tabs[tid]
                    if self._current_tab_id == tid:
                        remaining = list(self._tabs.values())
                        if remaining:
                            self._page = remaining[0]
                            self._current_tab_id = id(remaining[0])
                        else:
                            self._page = await self._context.new_page()
                            self._current_tab_id = id(self._page)
                            self._tabs[self._current_tab_id] = self._page
                    return [types.TextContent(type="text", text=f"Closed tab {tab_id}")]
            return [types.TextContent(type="text", text=f"Tab {tab_id} not found")]

        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    if not MCP_AVAILABLE:
        print("MCP SDK is required. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = PlaywrightMCPServer()

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="playwright-browser",
                server_version="1.0.0",
                capabilities=server.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())