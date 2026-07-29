// yt-rag Watch History Recorder - Content Script

const DEBUG = false;
const log = (...args) => DEBUG && console.log("[yt-rag]", ...args);

// Get video ID from URL
function getVideoIdFromUrl(url) {
  const params = new URLSearchParams(url.split("?")[1]);
  return params.get("v");
}

// Get video title from page (with retry for async loading)
async function getVideoTitle() {
  const selectors = [
    "h1.title yt-formatted-string",
    "h1 yt-formatted-string",
    "h2 yt-formatted-string",
    "yt-formatted-string.title",
  ];

  log("Starting title extraction...");

  // Retry up to 5 times, 300ms apart
  for (let attempt = 0; attempt < 5; attempt++) {
    for (const selector of selectors) {
      const element = document.querySelector(selector);
      if (element) {
        const title = element.textContent.trim();
        // Skip empty or "Home" titles
        if (title && title !== "Home") {
          log(`Title found on attempt ${attempt + 1}: "${title}"`);
          return title;
        }
      }
    }

    // Wait 300ms before next attempt
    if (attempt < 4) {
      log(`Title not found on attempt ${attempt + 1}, retrying...`);
      await new Promise(resolve => setTimeout(resolve, 300));
    }
  }

  log("Title extraction failed, using default");
  return "Unknown Title";
}

// Record video to server (via background worker)
function recordVideo(videoId, title, url, watchDate) {
  log("Recording video:", { video_id: videoId, title, url, watch_date: watchDate });
  chrome.runtime.sendMessage({
    type: "RECORD_VIDEO",
    data: { video_id: videoId, title, url, watch_date: watchDate }
  });
  log("Message sent to background worker");
}

// Listen to YouTube's navigation event
window.addEventListener("yt-navigate-finish", async () => {
  log("YouTube navigation detected");

  const videoId = getVideoIdFromUrl(window.location.href);
  log("Video ID extracted:", videoId);

  if (videoId) {
    log("Valid video ID found, starting title extraction...");
    const title = await getVideoTitle();
    const url = window.location.href.split("&")[0]; // Remove extra params
    const watchDate = new Date().toISOString();
    log("About to call recordVideo with:", { videoId, title, url, watchDate });
    recordVideo(videoId, title, url, watchDate);
  } else {
    log("No video ID found in URL, skipping");
  }
});

log("Extension loaded - listening for YouTube navigation");
