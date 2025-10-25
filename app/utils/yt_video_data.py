import httpx
from datetime import timedelta
import isodate
from pydantic import settings  # Or use pydantic settings for FastAPI

async def get_youtube_video_info(video_id: str):
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    video_duration = None

    API_KEY = getattr(settings, "YOUTUBE_API_KEY", None)
    if not API_KEY:
        return {"video_url": video_url, "video_id": video_id, "video_duration": None}

    url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=contentDetails&key={API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            data = response.json()
        duration_str = data["items"][0]["contentDetails"]["duration"]
        video_duration = format_iso8601_duration(duration_str)
    except (httpx.RequestError, KeyError, IndexError, ValueError):
        video_duration = None

    return {
        "video_url": video_url,
        "video_id": video_id,
        "video_duration": video_duration,
    }


def format_iso8601_duration(duration_str: str) -> str:
    duration = isodate.parse_duration(duration_str)
    if not isinstance(duration, timedelta):
        duration = timedelta(seconds=float(duration.total_seconds()))

    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours} hr")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if seconds > 0 or not parts:  # always show seconds if nothing else
        parts.append(f"{seconds} sec")

    return " ".join(parts)
