/**
 * content.js — FactGuard AI
 * Extracts article text and image URLs from the active page.
 *
 * Text extraction:
 *   Targets semantic article content (<article>, <main>, <p>) rather than
 *   body.innerText so that navigation menus, footers and sidebars are
 *   excluded. Falls back to all <p> tags, then body text if nothing richer
 *   is found.
 *
 * Image extraction:
 *   Collects <img> src values. Only absolute HTTP(S) URLs are returned.
 *   Small images (width/height < 80px as reported by the DOM) and data URIs
 *   are dropped here to reduce noise before the server filters further.
 */

function extractPageContent() {

    // Text

    let text = "";

    // 1. Prefer <article> element (most news sites use this)
    const articleEl = document.querySelector("article");
    if (articleEl) {
        text = articleEl.innerText.trim();
    }

    // 2. Fall back to <main>
    if (!text) {
        const mainEl = document.querySelector("main");
        if (mainEl) text = mainEl.innerText.trim();
    }

    // 3. Fall back to concatenating all <p> paragraph text
    if (!text) {
        text = Array.from(document.querySelectorAll("p"))
            .map(p => p.innerText.trim())
            .filter(t => t.length > 40)   // skip very short fragments
            .join(" ")
            .trim();
    }

    // 4. Last resort: full body text
    if (!text) {
        text = document.body.innerText.trim();
    }

    // Images 

    const images = Array.from(document.querySelectorAll("img"))
        .filter(img => {
            const src = img.src || "";
            // Only absolute HTTP(S) URLs
            if (!src.startsWith("http://") && !src.startsWith("https://")) return false;
            // Skip data URIs that somehow ended up in src after normalisation
            if (src.startsWith("data:")) return false;
            // Skip tiny images — likely icons, spacers or tracking pixels
            const w = img.naturalWidth  || img.width  || 0;
            const h = img.naturalHeight || img.height || 0;
            if ((w > 0 && w < 80) || (h > 0 && h < 80)) return false;
            return true;
        })
        .map(img => img.src);

    return { text, images };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "extractContent") {
        sendResponse(extractPageContent());
    }
    // Return true to indicate we will call sendResponse asynchronously
    // (not needed here since extractPageContent is synchronous, but good practice)
    return true;
});
