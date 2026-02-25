from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import instaloader
from datetime import datetime
import time
import logging

app = FastAPI(title="Instagram Sync Service via Instaloader")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SyncRequest(BaseModel):
    username: str
    user_id: str  # do Supabase auth, só para log/identificação

class SyncResponse(BaseModel):
    profile: dict
    posts: list[dict]

import random

L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_comments=False,
    save_metadata=False,
    quiet=True
)

proxies_list = [
    {'http': 'http://proxylab:U7tS9j2Q@us.proxylab.com:8000', 'https': 'http://proxylab:U7tS9j2Q@us.proxylab.com:8000'},
    {'http': 'http://proxylab:U7tS9j2Q@uk.proxylab.com:8000', 'https': 'http://proxylab:U7tS9j2Q@uk.proxylab.com:8000'},
    {'http': 'http://proxylab:U7tS9j2Q@de.proxylab.com:8000', 'https': 'http://proxylab:U7tS9j2Q@de.proxylab.com:8000'},
]

@app.post("/sync", response_model=SyncResponse)
async def sync_instagram(request: SyncRequest):
    username = request.username.strip().lstrip('@')
    try:
        selected_proxy = random.choice(proxies_list)
        L.context.proxy = selected_proxy
        logger.info(f"Using proxy: {selected_proxy}")
        logger.info(f"Syncing public profile: {username} for user {request.user_id}")

        profile = instaloader.Profile.from_username(L.context, username)

        # Profile data (mapeado como Data365)
        profile_dict = {
            "username": profile.username,
            "full_name": profile.full_name or "",
            "bio": profile.biography or "",
            "avatar_url": profile.profile_pic_url,
            "follower_count": profile.followers,
            "following_count": profile.followees,
            "is_verified": profile.is_verified,
            "external_id": str(profile.userid),
            "raw_json": profile.__dict__  # ou profile.to_dict() se disponível
        }

        posts_list = []
        post_count = 0
        max_posts = 10  # limite para evitar blocks; aumente com cuidado

        for post in profile.get_posts():
            if post_count >= max_posts:
                break

            post_dict = {
                "external_post_id": post.shortcode,
                "created_time": post.date_utc.isoformat() if post.date_utc else None,
                "text": post.caption or "",
                "post_type": post.typename.lower(),
                "likes_count": post.likes,
                "comments_count": post.comments,
                "views_count": post.video_view_count if hasattr(post, 'video_view_count') else None,
                "hashtags": list(post.caption_hashtags) if post.caption_hashtags else [],
                "mentions": list(post.tagged_users) if post.tagged_users else [],
                "media_urls": [
                    {"type": "video" if node.is_video else "image", "url": node.url}
                    for node in post.get_sidecar_nodes()
                ] or [{"type": "video" if post.is_video else "image", "url": post.url}],
                "raw_json": post.__dict__
            }
            posts_list.append(post_dict)
            post_count += 1

            # Sleep anti-rate-limit
            time.sleep(1.5 + post_count * 0.1)  # aumenta devagar

        logger.info(f"Sync complete: {len(posts_list)} posts fetched for {username}")
        return {"profile": profile_dict, "posts": posts_list}

    except instaloader.exceptions.ProfileNotExistsException:
        raise HTTPException(status_code=404, detail=f"Profile @{username} not found or private")
    except instaloader.exceptions.ConnectionException as e:
        logger.error(f"Instagram rate limit or block: {e}")
        raise HTTPException(status_code=429, detail="Rate limit hit - try again later or use proxy")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
