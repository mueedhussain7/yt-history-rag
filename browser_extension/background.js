// yt-rag Background Service Worker

const DEBUG = false;
const log = (...args) => DEBUG && console.log("[yt-rag]", ...args);

chrome.runtime.onMessage.addListener((message) => {
  log("Message received in background:", message);
  if (message.type === "RECORD_VIDEO") {
    fetch("http://localhost:8765/record_video", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(message.data)
    })
      .then(() => log("Recorded successfully"))
      .catch((err) => console.error("[yt-rag] Could not record:", err));
  }
});

log("Background worker loaded");
