#!/usr/bin/env python3
"""Generate an AllotMint overview video with narration."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

try:
    from gtts import gTTS
    from moviepy.editor import AudioFileClip, ImageClip
except ImportError:  # pragma: no cover - installation hint
    print("Missing dependencies. Install with: pip install gTTS moviepy")
    raise SystemExit(1)

SCRIPT = (
    """Welcome to AllotMint — a FastAPI backend powering a smart investment "
    "dashboard built for families.\n\n"
    "This project combines REST APIs for portfolios and instruments, a trading "
    "agent engine, and a fundamental screener — all working together to give "
    "private investors professional-grade insights.\n\n"
    "So what’s the current status? The good news — no merge conflicts. But, "
    "there are a few things missing. We need scenario testing support. Our "
    "instrument metadata still lacks sector and region fields. And in the UI, "
    "performance, transactions, screener and trading tabs are currently "
    "disabled.\n\n"
    "Now, here are two big enhancements we’re working on:\n\n"
    "First — a scenario tester. This lets users simulate a price shock and "
    "instantly see the impact across their portfolio. We’ll add a backend "
    "function called apply_price_shock, expose it via an API, and build a new UI "
    "tab for it.\n\n"
    "Second — we’re adding sector and region metadata to every instrument. This "
    "means upgrading utilities and rebuilding the scraped data files so "
    "investors can segment and analyse holdings more meaningfully.\n\n"
    "Finally, how do we help users actually pick and monitor stocks? AllotMint "
    "will bring in four tools: fundamental screeners with advanced filters, "
    "technical indicators, news and sector context, and intelligent portfolio "
    "alerts.\n\n"
    "Next steps? Developers — focus on wiring the scenario tester and enriching "
    "metadata. Investors — tag your assets and start preparing your watchlist.\n\n"
    "AllotMint is evolving from dashboard… to decision support system. Thanks "
    "for watching."""
)


def main() -> None:
    script_path = Path(__file__).resolve()
    image_path = script_path.with_name("presenter.png")
    if not image_path.exists():
        print("presenter.png not found in scripts directory.")
        raise SystemExit(1)

    with NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        gTTS(SCRIPT, lang="en", tld="co.uk").save(tmp.name)
        audio_path = Path(tmp.name)

    audio_clip = AudioFileClip(str(audio_path))
    image_clip = ImageClip(str(image_path)).set_duration(audio_clip.duration)
    video_clip = image_clip.set_audio(audio_clip).resize((1280, 720))
    output_path = script_path.with_name("allotmint_video.mp4")
    video_clip.write_videofile(str(output_path), fps=24)

    audio_clip.close()
    video_clip.close()
    audio_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
