"""Chrome DevTools Protocol client for detecting web page elements.

Connects to Chrome's remote debugging port to enumerate interactive DOM
elements (buttons, links, inputs, etc.) with their bounding rectangles.
This fills the gap where Windows UIAutomation cannot see web content.

Requirements:
    - Chrome launched with --remote-debugging-port=9222
    - websocket-client package
"""

import json
import logging
from typing import List, Optional, Tuple

from ..models.som_element import SoMElement
from ..models.ui_element import BoundingRect

logger = logging.getLogger(__name__)

# JavaScript to find all interactive elements and return bounding rects
_JS_GET_INTERACTIVE_ELEMENTS = """
(() => {
    const selectors = [
        'a[href]',
        'button',
        'input',
        'textarea',
        'select',
        '[role="button"]',
        '[role="link"]',
        '[role="tab"]',
        '[role="menuitem"]',
        '[role="checkbox"]',
        '[role="radio"]',
        '[role="textbox"]',
        '[role="option"]',
        '[onclick]',
        '[tabindex]',
        'summary',
        '[contenteditable="true"]',
    ];
    const seen = new Set();
    const results = [];

    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            if (seen.has(el)) continue;
            seen.add(el);

            const rect = el.getBoundingClientRect();
            // Skip invisible / zero-size elements
            if (rect.width < 4 || rect.height < 4) continue;
            // Skip elements outside viewport
            if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
            if (rect.right < 0 || rect.left > window.innerWidth) continue;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

            // Determine a meaningful name
            let name = el.getAttribute('aria-label')
                || el.getAttribute('title')
                || el.getAttribute('alt')
                || el.getAttribute('placeholder')
                || el.innerText?.trim().substring(0, 80)
                || el.getAttribute('name')
                || el.getAttribute('id')
                || '';

            // Determine element type
            const tag = el.tagName.toLowerCase();
            let elType = 'Button';
            if (tag === 'a') elType = 'Link';
            else if (tag === 'input' || tag === 'textarea') elType = 'Input';
            else if (tag === 'select') elType = 'ComboBox';
            else if (el.getAttribute('role')) elType = el.getAttribute('role');

            results.push({
                name: name,
                type: elType,
                left: Math.round(rect.left),
                top: Math.round(rect.top),
                right: Math.round(rect.right),
                bottom: Math.round(rect.bottom),
                tag: tag,
            });
        }
    }
    return results;
})()
"""


class CDPClient:
    """Chrome DevTools Protocol client for element detection.

    Connects to Chrome's remote debugging port and uses JavaScript
    evaluation to find interactive DOM elements.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9222):
        self.host = host
        self.port = port
        self._ws = None
        self._msg_id = 0
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Chrome debug port is reachable."""
        if self._available is not None:
            return self._available

        try:
            import urllib.request
            url = f"http://{self.host}:{self.port}/json/version"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                logger.info(f"CDP: Connected to {data.get('Browser', 'Chrome')}")
                self._available = True
                return True
        except Exception as e:
            logger.debug(f"CDP: Chrome debug port not available: {e}")
            self._available = False
            return False

    def _get_ws_url(self) -> Optional[str]:
        """Get WebSocket URL for the first browser page."""
        try:
            import urllib.request
            url = f"http://{self.host}:{self.port}/json"
            with urllib.request.urlopen(url, timeout=3) as resp:
                pages = json.loads(resp.read())

            # Find the first "page" type target
            for page in pages:
                if page.get("type") == "page" and "webSocketDebuggerUrl" in page:
                    return page["webSocketDebuggerUrl"]

            # Fallback: first target with a WebSocket URL
            for page in pages:
                if "webSocketDebuggerUrl" in page:
                    return page["webSocketDebuggerUrl"]

            logger.warning("CDP: No debuggable pages found")
            return None
        except Exception as e:
            logger.error(f"CDP: Failed to get page list: {e}")
            return None

    def _connect(self) -> bool:
        """Establish WebSocket connection to Chrome."""
        if self._ws is not None:
            return True

        ws_url = self._get_ws_url()
        if not ws_url:
            return False

        try:
            import websocket
            self._ws = websocket.create_connection(ws_url, timeout=5)
            logger.info(f"CDP: WebSocket connected to {ws_url}")
            return True
        except Exception as e:
            logger.error(f"CDP: WebSocket connection failed: {e}")
            self._ws = None
            return False

    def _send(self, method: str, params: dict = None) -> Optional[dict]:
        """Send a CDP command and wait for the response."""
        if not self._connect():
            return None

        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method}
        if params:
            msg["params"] = params

        try:
            self._ws.send(json.dumps(msg))
            # Read responses until we get the one matching our ID
            for _ in range(50):  # safety limit
                raw = self._ws.recv()
                resp = json.loads(raw)
                if resp.get("id") == self._msg_id:
                    if "error" in resp:
                        logger.warning(f"CDP error: {resp['error']}")
                        return None
                    return resp.get("result", {})
            logger.warning("CDP: Response timeout")
            return None
        except Exception as e:
            logger.error(f"CDP send/recv failed: {e}")
            self._ws = None
            return None

    def get_window_offset(self) -> Tuple[int, int]:
        """Get Chrome window position offset for coordinate translation.

        DOM element coordinates are relative to the viewport. We need
        to add the window position + browser chrome offset to get
        screen-absolute coordinates.

        Returns:
            (offset_x, offset_y) to add to DOM coordinates
        """
        # Get window bounds
        result = self._send("Browser.getWindowBounds", {"windowId": 0})
        if not result:
            # Fallback: try to get bounds via Browser.getWindowForTarget
            target_result = self._send("Browser.getWindowForTarget")
            if target_result:
                result = target_result.get("bounds", {})

        # Get the layout metrics to determine the viewport offset
        metrics = self._send("Page.getLayoutMetrics")

        win_x, win_y = 0, 0
        if result and "bounds" in result:
            bounds = result["bounds"]
            win_x = bounds.get("left", 0)
            win_y = bounds.get("top", 0)
        elif result:
            win_x = result.get("left", 0)
            win_y = result.get("top", 0)

        # Estimate browser chrome height (address bar + tabs)
        # Typical Chrome chrome height is ~85px at 100% DPI
        # We can get a more accurate value from cssVisualViewport
        chrome_offset_y = 0
        if metrics and "cssVisualViewport" in metrics:
            viewport = metrics["cssVisualViewport"]
            # The visual viewport pageY tells us the scroll position
            # pageTop is the offset of the viewport from the page top
            chrome_offset_y = int(viewport.get("clientHeight", 0))
            # This isn't the chrome height; we need a different approach

        # Use a reasonable default for Chrome chrome height
        # TODO: compute precisely from window bounds vs viewport
        chrome_offset_y = 85

        return win_x, win_y + chrome_offset_y

    def get_interactive_elements(self) -> List[SoMElement]:
        """Detect interactive elements on the current Chrome page.

        Returns:
            List of SoMElement with screen-absolute bounding rectangles
        """
        if not self.is_available():
            return []

        if not self._connect():
            return []

        # Execute JavaScript to find elements
        result = self._send("Runtime.evaluate", {
            "expression": _JS_GET_INTERACTIVE_ELEMENTS,
            "returnByValue": True,
        })

        if not result or "result" not in result:
            logger.warning("CDP: JS evaluation returned no result")
            return []

        js_result = result["result"]
        if js_result.get("type") != "object" or "value" not in js_result:
            logger.warning(f"CDP: Unexpected JS result type: {js_result.get('type')}")
            return []

        raw_elements = js_result["value"]
        if not isinstance(raw_elements, list):
            logger.warning("CDP: JS result is not a list")
            return []

        # Get window offset for coordinate translation
        offset_x, offset_y = self.get_window_offset()

        elements = []
        for raw in raw_elements:
            name = raw.get("name", "")
            el_type = raw.get("type", "Button")

            # Translate viewport-relative coords to screen-absolute
            left = raw.get("left", 0) + offset_x
            top = raw.get("top", 0) + offset_y
            right = raw.get("right", 0) + offset_x
            bottom = raw.get("bottom", 0) + offset_y

            elements.append(SoMElement(
                mark_id=0,
                name=name,
                element_type=el_type,
                bounding_rect=BoundingRect(
                    left=int(left),
                    top=int(top),
                    right=int(right),
                    bottom=int(bottom),
                ),
                source="cdp",
                is_enabled=True,
                is_visible=True,
            ))

        logger.info(f"CDP: Detected {len(elements)} interactive elements")
        return elements

    def close(self):
        """Close the WebSocket connection."""
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._available = None
