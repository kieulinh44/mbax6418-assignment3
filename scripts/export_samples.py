"""Export exactly three completed, class-generated tracks, never uploads or credentials.

Usage: python scripts/export_samples.py SESSION_ID
Run after generating a three-song jam; review the resulting audio before submission.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    if len(sys.argv) != 2 or not re.fullmatch(r'[0-9a-f]{12}', sys.argv[1]):
        raise SystemExit('Usage: python scripts/export_samples.py SESSION_ID')
    source = ROOT / 'sessions' / sys.argv[1]
    manifest = json.loads((source / 'manifest.json').read_text())
    tracks = manifest['tracks']
    if len(tracks) != 3:
        raise SystemExit('Generate a completed three-song jam first.')
    target = ROOT / 'samples'
    target.mkdir(exist_ok=True)
    exported = []
    for i, track in enumerate(tracks, 1):
        audio = source / f'song_{i}.mp3'
        cover = source / f'cover_{i}.png'
        if not audio.is_file() or not cover.is_file():
            raise SystemExit('Each sample requires actual generated audio and cover art.')
        shutil.copyfile(audio, target / audio.name)
        shutil.copyfile(cover, target / cover.name)
        exported.append({key: track.get(key) for key in
                         ('title', 'artist', 'lyrics', 'blurb', 'meta', 'cover_prompt', 'art_direction')}
                        | {'audio_file': audio.name, 'art_file': cover.name})
    output = {'source_session': sys.argv[1], 'generation': {
        'lyrics': 'Qwen3.6-35B-A3B, class port 9001',
        'audio': 'ACE-Step 1.5 XL Turbo, class port 9007',
        'covers': 'FLUX.2 klein 4B, class port 9006',
        'options': {k: manifest['options'].get(k) for k in
                    ('genre', 'mood', 'theme', 'vocals', 'duration_sec', 'language')}}, 'tracks': exported}
    (target / 'manifest.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    print('Exported three songs and covers to samples/. No session directory or reference audio included.')

if __name__ == '__main__':
    main()
