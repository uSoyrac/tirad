"""
YouTube veri toplama — transkript + video başlıkları.
youtube-transcript-api (API key gerekmez) + google-api-python-client (opsiyonel).
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Sabit kanal listesi — settings.yaml'dan override edilir
DEFAULT_CHANNELS = [
    {"id": "UCRvqjQPSeaWn-uEx-w0XLIg", "name": "Michaël van de Poppe", "lang": "en"},
    {"id": "UCTrTXgm2KEHq2La-RNPVuuQ", "name": "Benjamin Cowen", "lang": "en"},
    {"id": "UCqK_GSMbpiV8spgD3ZGloSw", "name": "Coin Bureau", "lang": "en"},
    {"id": "UCbLhGKVY-bJPcawebgtNfbw", "name": "Altcoin Daily", "lang": "en"},
    {"id": "UCJgHxpqfhWEEjYH9cLXqhIQ", "name": "Crypto Banter", "lang": "en"},
]


def get_youtube_client():
    """Google API client — sadece YouTube Data API key varsa kullanılır."""
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        return None
    try:
        from googleapiclient.discovery import build
        return build("youtube", "v3", developerKey=api_key)
    except ImportError:
        logger.warning("google-api-python-client yüklü değil")
        return None
    except Exception as e:
        logger.warning(f"YouTube client oluşturulamadı: {e}")
        return None


def get_channel_recent_videos(channel_id: str, max_results: int = 3) -> list[dict]:
    """YouTube Data API ile kanal son videolarını çeker."""
    client = get_youtube_client()
    if not client:
        logger.debug(f"YouTube API key yok, {channel_id} atlanıyor")
        return []

    try:
        response = client.search().list(
            channelId=channel_id,
            order="date",
            type="video",
            maxResults=max_results,
            part="id,snippet",
        ).execute()

        videos = []
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            videos.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:500],
                "published_at": snippet.get("publishedAt", ""),
                "channel_id": channel_id,
                "channel_title": snippet.get("channelTitle", ""),
            })

        return videos
    except Exception as e:
        logger.warning(f"YouTube video listesi hatası {channel_id}: {e}")
        return []


def get_video_transcript(video_id: str, max_chars: int = 8000) -> Optional[str]:
    """youtube-transcript-api ile transkript çeker (API key gerekmez)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

        # Önce İngilizce, sonra Türkçe, Almanca dene
        for lang_codes in [["en"], ["tr"], ["de"], ["en-US"], None]:
            try:
                if lang_codes:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_codes)
                else:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)

                full_text = " ".join(item["text"] for item in transcript_list)
                return full_text[:max_chars]
            except Exception:
                continue

        return None
    except ImportError:
        logger.warning("youtube-transcript-api yüklü değil")
        return None
    except Exception as e:
        logger.debug(f"Transkript alınamadı {video_id}: {e}")
        return None


def collect_youtube_data(channels: list[dict] = None, max_videos: int = 3,
                          max_chars: int = 8000) -> list[dict]:
    """
    Belirtilen kanallardan son videolar + transkriptleri toplar.
    YouTube API key yoksa transkript API ile devam eder (video listesi için alternatif gerekmez).
    """
    if channels is None:
        channels = DEFAULT_CHANNELS

    results = []

    for channel in channels:
        channel_id = channel.get("id", "")
        channel_name = channel.get("name", channel_id)
        lang = channel.get("lang", "en")

        if not channel_id:
            continue

        # Video listesi al
        videos = get_channel_recent_videos(channel_id, max_videos)

        if not videos:
            logger.info(f"YouTube API yok veya hata — {channel_name} için bilinen video ID'si deneniyor")
            # API olmadan çalışma: sadece kanal adını kaydet (transkript yoksa)
            results.append({
                "channel_id": channel_id,
                "channel_name": channel_name,
                "language": lang,
                "title": f"[{channel_name} — API gerekli]",
                "transcript": "",
                "source": "youtube",
            })
            continue

        for video in videos:
            video_id = video["video_id"]
            transcript = get_video_transcript(video_id, max_chars)

            results.append({
                "channel_id": channel_id,
                "channel_name": channel_name,
                "language": lang,
                "video_id": video_id,
                "title": video["title"],
                "description": video.get("description", ""),
                "transcript": transcript or "",
                "published_at": video.get("published_at", ""),
                "source": "youtube",
            })
            logger.info(
                f"YouTube: {channel_name} — '{video['title'][:60]}' "
                f"({'transkript var' if transcript else 'transkript yok'})"
            )

    return results


def extract_text_from_youtube_data(youtube_data: list[dict]) -> list[str]:
    """YouTube verilerinden analiz için metin listesi çıkarır."""
    texts = []
    for item in youtube_data:
        parts = []
        if item.get("title"):
            parts.append(item["title"])
        if item.get("description"):
            parts.append(item["description"])
        if item.get("transcript"):
            parts.append(item["transcript"][:3000])  # İlk 3000 char
        if parts:
            texts.append(" ".join(parts))
    return texts
