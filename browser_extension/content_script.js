// yt-rag Watch History Recorder - Content Script
// Simplified: No message passing, no background worker
// Just listen to YouTube's navigation event and POST directly

const RECEIVER_URL = "http://localhost:8765/record_video";

// Get video ID from URL
function getVideoIdFromUrl(url) {
  const params = new URLSearchParams(url.split("?")[1]);
  return params.get("v");
}

// Get video title from page
function getVideoTitle() {
  // Try multiple selectors for the video title
  const selectors = [
    "h1.title yt-formatted-string",
    "h1 yt-formatted-string",
    "h2 yt-formatted-string",
    "yt-formatted-string.title",
  ];

  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element && element.textContent.trim()) {
      return element.textContent.trim();
    }
  }

  return "Unknown Title";
}

// Record video to server
function recordVideo(videoId, title, url) {
  if (!videoId) return;

  const videoData = {
    video_id: videoId,
    title: title || "Unknown Title",
    url: url,
    watch_date: new Date().toISOString(),
  };

  console.log("[yt-rag] Recording video:", videoData);

  fetch(RECEIVER_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(videoData),
  })
    .then((response) => {
      if (response.ok) {
        return response.json();
      }
      throw new Error(`HTTP ${response.status}`);
    })
    .then((result) => {
      console.log("[yt-rag] Recorded:", result.message);
    })
    .catch((error) => {
      console.log("[yt-rag] Could not record:", error.message);
    });
}

// Listen to YouTube's navigation event
window.addEventListener("yt-navigate-finish", () => {
  console.log("[yt-rag] YouTube navigation detected");

  const videoId = getVideoIdFromUrl(window.location.href);
  if (videoId) {
    const title = getVideoTitle();
    const url = window.location.href.split("&")[0]; // Remove extra params
    recordVideo(videoId, title, url);
  }
});

console.log("[yt-rag] Extension loaded - listening for YouTube navigation");
