"""Cover art via FLUX (9006): a text-to-image prompt per track -> PNG bytes."""
from __future__ import annotations

from .clients import generate_cover_art


def cover_for(track: dict, size: str = "1024x1024") -> bytes:
    """Render the album cover for a composed track."""
    prompt = (track.get("cover_prompt") or track.get("caption")
              or "abstract album cover art, vibrant colors, no text")
    return generate_cover_art(prompt, size=size)
