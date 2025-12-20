"""Visual demo mode for reviewing recordings.

Provides visual cursor indicator and smooth mouse movement for
demonstrating recorded browser interactions.
"""

from playwright.async_api import Page

# Arrow cursor SVG (black with white outline for visibility on any background)
CURSOR_SVG = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M5 3L19 12L12 13L9 20L5 3Z" fill="black" stroke="white" stroke-width="1.5" stroke-linejoin="round"/>
</svg>"""

# JavaScript to inject visual cursor
CURSOR_SCRIPT = (
    """
(() => {
    if (window.__demoCursor) return;

    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = `"""
    + CURSOR_SVG.replace("\n", "").replace("  ", "")
    + """`;
    cursor.style.cssText = `
        position: fixed;
        left: 0;
        top: 0;
        pointer-events: none;
        z-index: 999999;
        filter: drop-shadow(1px 1px 2px rgba(0,0,0,0.4));
        transition: transform 0.08s ease-out;
    `;
    document.body.appendChild(cursor);

    window.__demoCursor = cursor;
    window.__moveCursor = (x, y) => {
        cursor.style.left = x + 'px';
        cursor.style.top = y + 'px';
    };
    window.__clickEffect = () => {
        cursor.style.transform = 'scale(0.85)';
        setTimeout(() => {
            cursor.style.transform = 'scale(1)';
        }, 100);
    };
})();
"""
)


async def setup_demo_cursor(page: Page) -> None:
    """Inject visual cursor indicator into the page.

    The cursor is an SVG arrow that follows mouse movements
    and animates on clicks.
    """
    # Add to init script for page reloads
    await page.add_init_script(CURSOR_SCRIPT)
    # Also run immediately for current page
    try:
        await page.evaluate(CURSOR_SCRIPT)
    except Exception:
        # CSP may block - that's OK, init script handles navigations
        pass


async def move_cursor(page: Page, x: float, y: float) -> None:
    """Update the visual cursor position."""
    try:
        await page.evaluate(f"window.__moveCursor && window.__moveCursor({x}, {y})")
    except Exception:
        pass  # Page may have navigated


async def click_effect(page: Page) -> None:
    """Trigger the click animation on the visual cursor."""
    try:
        await page.evaluate("window.__clickEffect && window.__clickEffect()")
    except Exception:
        pass


async def move_cursor_smoothly(
    page: Page, target_x: float, target_y: float, steps: int = 20
) -> None:
    """Move cursor smoothly from current position to target.

    Uses Playwright's built-in mouse.move with steps for interpolation,
    and updates the visual cursor to match.

    Args:
        page: Playwright page
        target_x: Target X coordinate
        target_y: Target Y coordinate
        steps: Number of interpolation steps (higher = smoother but slower)
    """
    # Move actual mouse with interpolation first
    await page.mouse.move(target_x, target_y, steps=steps)
    # Then update visual cursor to match final position
    await move_cursor(page, target_x, target_y)
