"""Cover art via FLUX (9006): a text-to-image prompt per track -> PNG bytes."""
from __future__ import annotations

import random
import threading

from .clients import generate_cover_art


# Shared across genres deliberately: a musical genre is not a color palette.
PALETTES = (
    "burnt orange, petrol teal and warm ivory",
    "forest green, antique gold and charcoal",
    "vermilion, parchment and chocolate brown",
    "cobalt blue, cream and a small rust-red accent",
    "black and white with silver-gray tonal detail",
    "dusty lavender, sage green and chalk white",
    "terracotta, indigo and sand",
    "lemon yellow, ink black and off-white",
    "deep burgundy, pale peach and warm gray",
    "copper, midnight green and bone white",
    "electric magenta, midnight blue and silver",
    "olive, apricot and muted sky blue",
    "luminous jewel tones: emerald, sapphire, amethyst and warm gold highlights",
    "sunlit coral, saffron, turquoise and deep ultramarine shadows",
    "stormy violet and steel gray with radiant orange and pearlescent highlights",
    "lush botanical greens with scarlet, orchid and soft sunlight",
)
MEDIA = (
    "hand-carved linocut print with visible ink texture",
    "analog medium-format photography with natural light and fine film grain",
    "tactile cut-paper collage with layered shadows",
    "expressive oil painting with visible brushwork",
    "an elaborate mixed-object still life photographed in an atmospheric location",
    "charcoal and chalk drawing on textured paper",
    "loose watercolor with translucent washes",
    "layered geometric illustration with intricate pattern and textured imagery",
    "woven textile artwork with visible threads",
    "delicate ink-wash illustration",
    "vintage airbrush illustration with soft gradients",
    "intricate ceramic mosaic artwork with glazed narrative details",
    "cinematic practical-effects photography with atmospheric depth",
    "intricately detailed surrealist digital painting",
    "psychedelic screenprint with ornamental linework and rich overprinting",
    "lush storybook gouache illustration with fine environmental details",
)
# Composition and richness travel together. Independent random choices used to
# combine a story-rich idea with an empty background or single-object layout.
SCENE_PROFILES = {
    "a cinematic establishing scene with a compelling focal point and deep perspective":
        "Layered world-building: foreground story objects, a lived-in middle-distance setting and a distant atmosphere; dramatic motivated light, nuanced shadows and discoveries at several scales.",
    "an immersive surreal world where architecture and organic forms intertwine":
        "Layered impossible spaces, interacting forms and surprising scale changes; intricate surfaces, secondary narrative details and luminous reflected light, unified by one strong visual idea.",
    "an intricate psychedelic image with interlocking narrative motifs":
        "Layered ornamental rhythms, densely illustrated patterns and fine expressive linework across the frame; vary scale and contrast so the focal subject remains legible rather than visual noise.",
    "an expressive environmental portrait with an off-center human or creature subject":
        "Layered personal storytelling through gesture, clothing texture, meaningful surrounding objects and a recognizable setting; intimate directional light and rich background detail without overwhelming the face.",
    "an elaborate still-life tableau with several interacting story-related objects":
        "Layered tactile materials, folds, reflections, small traces of a story and a convincing surrounding location; directional light connects the objects into a narrative rather than a product shot.",
    "an expansive living landscape shaped by weather, geography and the song's story":
        "Layered terrain, vegetation, architecture or signs of human life from foreground to horizon; complex atmospheric light, fine environmental texture and a memorable focal event.",
    "a kinetic action composition with diagonal movement through a distinctive setting":
        "Layered motion, interacting subjects, environmental debris or reflections and dynamic scale; precise focal detail against selective motion blur, with lighting that emphasizes the action.",
    "a layered editorial photomontage merging different story moments into one image":
        "Layered photographic fragments, expressive textures and surprising transitions between scales; several connected narrative clues, sophisticated color grading and coherent light rather than a grid of separate pictures.",
    "a richly illustrated narrative scene with interconnected characters, objects and patterns":
        "Layered visual storytelling, intricate decorative detail, a distinctive environment and small secondary discoveries; a clear hierarchy and thoughtful light keep the illustration readable at album size.",
    "a bold graphic composition with a powerful silhouette and an expressive designed background":
        "A more restrained graphic treatment for contrast: decisive shapes, striking color relationships, textured pattern and a few specific narrative details. Make a finished designed artwork, not a generic icon on blank paper.",
}
COMPOSITIONS = tuple(SCENE_PROFILES)
APPROACHES = (
    "a world built around a symbolic object transformed by the song's central emotion",
    "a human gesture and its surrounding scene conveying the song's story",
    "a natural process such as erosion, growth, tides or changing seasons",
    "an imagined place whose architecture embodies the song's theme",
    "interacting abstract forms and textures translating the song's dynamic journey",
    "a surreal landscape drawn from a concrete image in the lyrics or title",
    "an unexpected encounter between story-related objects, people or environments",
    "a botanical or animal metaphor for the song's emotional journey",
    "a revealing moment within a richly observed environment",
    "a transformation of light and physical space suggesting the song's emotional arc",
)


class ArtDirector:
    """Thread-safe shuffle bags: exhaust each dimension before reusing it.

    Bags are per genre, shared by all sessions, including single-song requests.
    Each genre gets a freshly shuffled mix of the same broad visual vocabulary,
    not its own fixed aesthetic. State is intentionally process-local; a restart
    starts a new random order rather than always repeating the first style.
    """

    def __init__(self, rng: random.Random | None = None):
        self._rng = rng if rng is not None else random.SystemRandom()
        self._lock = threading.Lock()
        self._bags: dict[tuple[str, str], list[str]] = {}
        self._last: dict[tuple[str, str], str] = {}

    def choose(self, genre: str = "") -> dict[str, str]:
        genre = str(genre).strip().casefold()
        pools = {"palette": PALETTES, "medium": MEDIA,
                 "composition": COMPOSITIONS, "approach": APPROACHES}
        direction = {}
        with self._lock:
            for dimension, pool in pools.items():
                key = (genre, dimension)
                bag = self._bags.setdefault(key, [])
                if not bag:
                    bag.extend(pool)
                    self._rng.shuffle(bag)
                    # Avoid an immediate repeat across a shuffle boundary.
                    if bag[-1] == self._last.get(key):
                        bag[-1], bag[0] = bag[0], bag[-1]
                value = bag.pop()
                self._last[key] = value
                direction[dimension] = value
        direction["richness"] = SCENE_PROFILES[direction["composition"]]
        return direction


director = ArtDirector()


def cover_for(track: dict, size: str = "1024x1024") -> bytes:
    """Render the album cover for a composed track."""
    direction = track.get("art_direction")
    if not isinstance(direction, dict) or not all(
            direction.get(key) for key in ("palette", "medium", "composition", "approach")):
        direction = director.choose(track.get("genres", ""))
        track["art_direction"] = direction
    elif not direction.get("richness"):
        # Upgrade an older spec only if explicitly rendered again. Existing
        # image files are untouched; keep its palette/medium, but pair a new
        # composition with its matching detail treatment.
        profile = director.choose(track.get("genres", ""))
        direction = {**direction, "composition": profile["composition"],
                     "richness": profile["richness"]}
        track["art_direction"] = direction
    brief = "; ".join(f"{key}: {value}" for key, value in direction.items())
    scene = track.get("cover_prompt") or track.get("caption") or "an original symbolic scene"
    prompt = (
        f"Original square full-bleed album artwork. Assigned visual direction: {brief}. "
        f"Song title for inspiration only (do not write it): {track.get('title', 'Untitled')}. "
        f"Song-specific scene: {scene}. "
        "Follow the composition and its matched richness as one coherent visual brief. "
        "Use the palette as a color family with nuanced shades, textured surfaces and "
        "motivated light, rather than flat fills. Keep a strong focal hierarchy and "
        "make the surrounding scene and secondary details specific to this song. "
        "Interpret the story, not stock music-genre iconography. No text, letters, typography, "
        "logos, watermarks or album mockup borders."
    )
    return generate_cover_art(prompt, size=size)
