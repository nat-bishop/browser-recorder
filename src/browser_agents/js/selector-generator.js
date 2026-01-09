/**
 * Codegen-style selector generator for browser automation.
 *
 * This file is used by:
 * 1. Playwright recorder (injected via add_init_script)
 * 2. Chrome extension content script (bundled directly)
 *
 * Selector Priority (same as Playwright Codegen):
 * 1. role + accessible name - "button named 'Submit'" (most resilient)
 * 2. label - "input labeled 'Email'" (form fields)
 * 3. placeholder - "input with placeholder 'Enter email'"
 * 4. text - "link containing 'Sign In'"
 * 5. testid - data-testid="login-btn"
 * 6. css - Last resort fallback
 */

// =============================================================================
// Main selector generation
// =============================================================================

/**
 * Generate multiple selector candidates for an element.
 * Returns selectors ordered by resilience (best first).
 *
 * @param {Element} element - The DOM element to generate selectors for
 * @returns {Array<{strategy: string, value: string, confidence: string, role?: string, name?: string}>}
 */
function generateSelectors(element) {
    const selectors = [];

    // Priority 1: Role + accessible name (most resilient)
    const role = getImplicitRole(element);
    const accessibleName = getAccessibleName(element);
    if (role && accessibleName && accessibleName.length < 100) {
        selectors.push({
            strategy: "role",
            role: role,
            name: accessibleName,
            value: `role=${role}[name="${escapeSelector(accessibleName)}"]`,
            confidence: "high"
        });
    }

    // Priority 2: Label (for form fields)
    const label = findAssociatedLabel(element);
    if (label && label.length < 100) {
        selectors.push({
            strategy: "label",
            value: label,
            confidence: "high"
        });
    }

    // Priority 3: Placeholder
    const placeholder = element.placeholder;
    if (placeholder && placeholder.length < 100) {
        selectors.push({
            strategy: "placeholder",
            value: placeholder,
            confidence: "medium"
        });
    }

    // Priority 4: Text content (clickables only)
    const text = getVisibleText(element);
    if (text && text.length < 50 && isClickable(element)) {
        selectors.push({
            strategy: "text",
            value: text,
            confidence: "medium"
        });
    }

    // Priority 5: Test ID
    const testId = getTestId(element);
    if (testId) {
        selectors.push({
            strategy: "testid",
            value: testId,
            confidence: "high"
        });
    }

    // Priority 6: CSS (smart fallback - avoid brittle selectors)
    const css = generateSmartCSS(element);
    if (css) {
        selectors.push({
            strategy: "css",
            value: css,
            confidence: "low"
        });
    }

    return selectors;
}

// =============================================================================
// ARIA role detection
// =============================================================================

/**
 * Get the ARIA role for an element (explicit or implicit).
 *
 * @param {Element} element
 * @returns {string|null}
 */
function getImplicitRole(element) {
    // Explicit role takes precedence
    const explicitRole = element.getAttribute("role");
    if (explicitRole) return explicitRole;

    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type")?.toLowerCase();

    // Implicit role mapping based on HTML spec
    const implicitRoles = {
        "button": "button",
        "a": "link",
        "input:text": "textbox",
        "input:email": "textbox",
        "input:password": "textbox",
        "input:tel": "textbox",
        "input:url": "textbox",
        "input:search": "searchbox",
        "input:number": "spinbutton",
        "input:checkbox": "checkbox",
        "input:radio": "radio",
        "input:range": "slider",
        "select": "combobox",
        "textarea": "textbox",
        "img": "img",
        "nav": "navigation",
        "main": "main",
        "header": "banner",
        "footer": "contentinfo",
        "aside": "complementary",
        "article": "article",
        "section": "region",
        "form": "form",
        "table": "table",
        "ul": "list",
        "ol": "list",
        "li": "listitem"
    };

    // Try type-specific first, then tag-only
    const typeKey = type ? `${tag}:${type}` : null;
    return implicitRoles[typeKey] || implicitRoles[tag] || null;
}

// =============================================================================
// Accessible name computation
// =============================================================================

/**
 * Get the accessible name for an element following ARIA spec.
 *
 * @param {Element} element
 * @returns {string|null}
 */
function getAccessibleName(element) {
    // 1. aria-label
    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim();

    // 2. aria-labelledby (can contain multiple space-separated IDs)
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy) {
        const ids = labelledBy.split(/\s+/);
        const texts = ids
            .map(id => document.getElementById(id)?.textContent?.trim())
            .filter(Boolean);
        if (texts.length > 0) return texts.join(" ");
    }

    // 3. For buttons/links: use text content
    const tag = element.tagName.toLowerCase();
    if (["button", "a"].includes(tag)) {
        const text = getVisibleText(element);
        if (text && text.length < 50) return text;
    }

    // 4. For inputs: use associated label or placeholder
    if (tag === "input" || tag === "textarea" || tag === "select") {
        const label = findAssociatedLabel(element);
        if (label) return label;
        if (element.placeholder) return element.placeholder;
    }

    // 5. title attribute
    const title = element.getAttribute("title");
    if (title) return title.trim();

    // 6. For images: alt text
    if (tag === "img") {
        const alt = element.getAttribute("alt");
        if (alt) return alt.trim();
    }

    return null;
}

/**
 * Find the associated label for a form element.
 *
 * @param {Element} element
 * @returns {string|null}
 */
function findAssociatedLabel(element) {
    // 1. Explicit label via 'for' attribute
    const id = element.id;
    if (id) {
        const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
        if (label) {
            const text = label.textContent?.trim();
            if (text) return text;
        }
    }

    // 2. Parent label element
    const parentLabel = element.closest("label");
    if (parentLabel) {
        // Get text excluding the input itself
        const clone = parentLabel.cloneNode(true);
        const inputs = clone.querySelectorAll("input, select, textarea");
        inputs.forEach(input => input.remove());
        const text = clone.textContent?.trim();
        if (text) return text;
    }

    // 3. aria-label/aria-labelledby handled in getAccessibleName
    return null;
}

// =============================================================================
// Test ID detection
// =============================================================================

/**
 * Get test ID from element (various common conventions).
 *
 * @param {Element} element
 * @returns {string|null}
 */
function getTestId(element) {
    // Check common test ID attributes
    const testIdAttrs = [
        "data-testid",
        "data-test-id",
        "data-test",
        "data-cy",           // Cypress
        "data-automation-id" // Common enterprise pattern
    ];

    for (const attr of testIdAttrs) {
        const value = element.getAttribute(attr);
        if (value) return value;
    }

    return null;
}

// =============================================================================
// CSS selector generation
// =============================================================================

/**
 * Generate a smart CSS selector (avoiding brittle patterns).
 *
 * @param {Element} element
 * @returns {string|null}
 */
function generateSmartCSS(element) {
    const parts = [];

    // Tag name
    const tag = element.tagName.toLowerCase();
    parts.push(tag);

    // ID (if stable-looking)
    const id = element.id;
    if (id && isStableId(id)) {
        return `#${CSS.escape(id)}`;
    }

    // Stable attributes for form elements
    if (tag === "input" || tag === "textarea" || tag === "select") {
        const name = element.getAttribute("name");
        if (name) {
            return `${tag}[name="${CSS.escape(name)}"]`;
        }
        const type = element.getAttribute("type");
        if (type) {
            parts.push(`[type="${type}"]`);
        }
    }

    // href for links (first part of path)
    if (tag === "a") {
        const href = element.getAttribute("href");
        if (href && !href.startsWith("javascript:") && !href.startsWith("#")) {
            try {
                const url = new URL(href, window.location.origin);
                const path = url.pathname;
                if (path && path !== "/") {
                    // Use just the last path segment
                    const lastSegment = path.split("/").filter(Boolean).pop();
                    if (lastSegment) {
                        return `a[href*="${CSS.escape(lastSegment)}"]`;
                    }
                }
            } catch (e) {
                // Invalid URL, skip href-based selector
            }
        }
    }

    // Classes (limit to 2 stable-looking classes)
    const classes = Array.from(element.classList)
        .filter(isStableClass)
        .slice(0, 2);
    if (classes.length > 0) {
        parts.push(...classes.map(c => `.${CSS.escape(c)}`));
    }

    // If we have at least tag + something, return it
    if (parts.length > 1) {
        return parts.join("");
    }

    // Last resort: tag with nth-of-type if there are siblings
    const parent = element.parentElement;
    if (parent) {
        const siblings = Array.from(parent.children).filter(
            c => c.tagName === element.tagName
        );
        if (siblings.length > 1) {
            const index = siblings.indexOf(element) + 1;
            return `${tag}:nth-of-type(${index})`;
        }
    }

    return tag;
}

/**
 * Check if an ID looks stable (not auto-generated).
 *
 * @param {string} id
 * @returns {boolean}
 */
function isStableId(id) {
    // Skip IDs that look auto-generated
    const autoGenPatterns = [
        /^[a-z]{1,2}\d{4,}$/i,         // e.g., "e12345", "ab123456"
        /^_/,                            // Starting with underscore
        /^\d/,                           // Starting with digit
        /^ember\d+$/i,                   // Ember.js
        /^react-/i,                      // React
        /^ng-/i,                         // Angular
        /^:r\w+:$/,                      // React 18 useId
        /^[0-9a-f]{8,}$/i,               // Long hex strings (UUIDs, hashes)
        /__/                              // Double underscore (often generated)
    ];

    return !autoGenPatterns.some(pattern => pattern.test(id));
}

/**
 * Check if a class looks stable (not utility or auto-generated).
 *
 * @param {string} className
 * @returns {boolean}
 */
function isStableClass(className) {
    // Skip Tailwind-style utility classes
    if (/^(p|m|w|h|text|bg|border|flex|grid|gap|rounded|shadow)-/.test(className)) {
        return false;
    }

    // Skip auto-generated patterns
    const autoGenPatterns = [
        /^_/,                // Underscore prefix
        /^\d/,               // Starting with digit
        /^[a-z]{1,2}\d{3,}$/i, // e.g., "c123", "ab1234"
        /^css-/i,            // Emotion/styled-components
        /^sc-/i,             // styled-components
        /^MuiPaper/i         // Material-UI (keep more specific MUI classes)
    ];

    return !autoGenPatterns.some(pattern => pattern.test(className));
}

// =============================================================================
// Utility functions
// =============================================================================

/**
 * Get visible text content from an element.
 *
 * @param {Element} element
 * @returns {string|null}
 */
function getVisibleText(element) {
    // For buttons with just text, get innerText
    const text = element.innerText?.trim();
    if (text && text.length > 0 && !text.includes("\n")) {
        return text;
    }
    return null;
}

/**
 * Check if an element is clickable (button, link, etc).
 *
 * @param {Element} element
 * @returns {boolean}
 */
function isClickable(element) {
    const tag = element.tagName.toLowerCase();
    const role = element.getAttribute("role");

    const clickableTags = ["a", "button"];
    const clickableRoles = ["button", "link", "menuitem", "tab", "option"];

    return (
        clickableTags.includes(tag) ||
        clickableRoles.includes(role) ||
        element.onclick !== null ||
        element.hasAttribute("onclick") ||
        getComputedStyle(element).cursor === "pointer"
    );
}

/**
 * Escape special characters for selector strings.
 *
 * @param {string} str
 * @returns {string}
 */
function escapeSelector(str) {
    return str.replace(/["\\]/g, "\\$&");
}

/**
 * Get the element type for LLM context.
 *
 * @param {Element} element
 * @returns {string}
 */
function getElementType(element) {
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type")?.toLowerCase();
    const role = element.getAttribute("role");

    if (tag === "button" || role === "button") return "button";
    if (tag === "a" || role === "link") return "link";
    if (tag === "select" || role === "combobox") return "select";
    if (tag === "textarea") return "textarea";

    if (tag === "input") {
        if (type === "checkbox") return "checkbox";
        if (type === "radio") return "radio";
        return "input";
    }

    return "generic";
}

// Export for use in both Playwright and Chrome extension contexts
if (typeof module !== "undefined" && module.exports) {
    module.exports = {
        generateSelectors,
        getImplicitRole,
        getAccessibleName,
        findAssociatedLabel,
        getTestId,
        generateSmartCSS,
        getElementType,
        isClickable
    };
}
