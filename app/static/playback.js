"use strict";

function seekTime(clientX, left, width, duration) {
  if (!Number.isFinite(width) || width <= 0 || !Number.isFinite(duration) || duration <= 0) {
    return null;
  }
  const ratio = Math.min(1, Math.max(0, (clientX - left) / width));
  return ratio * duration;
}

const playbackApi = { seekTime };
if (typeof window !== "undefined") window.AIJPlayback = playbackApi;
if (typeof module !== "undefined") module.exports = playbackApi;
