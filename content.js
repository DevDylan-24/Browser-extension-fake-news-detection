function extractPageContent() {

    let paragraphs = Array.from(document.querySelectorAll("p"))
        .map(p => p.innerText)
        .join(" ");

    let images = Array.from(document.querySelectorAll("img"))
        .map(img => img.src);

    return {
        text: paragraphs,
        images: images
    };
}

// function extractPageContent() {

//     let paragraphs = Array.from(document.querySelectorAll("p"))
//         .map(p => p.innerText.trim())
//         .filter(p => p.length > 20)
//         .join(" ");

//     let images = Array.from(document.querySelectorAll("img"))
//         .map(img => img.src)
//         .filter(src => src.startsWith("http"));

//     return {
//         text: paragraphs,
//         images: images
//     };
// }

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    
    if (request.action === "extractContent") {
        const content = extractPageContent();
        sendResponse(content);
    }
});