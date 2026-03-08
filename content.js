function extractPageContent() {
    
    const textContent = document.body.innerText;

    const images = Array.from(document.images).map(img => img.src);

    return {
        text: textContent,
        images: images
    };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    
    if (request.action === "extractContent") {
        const content = extractPageContent();
        sendResponse(content);
    }
});