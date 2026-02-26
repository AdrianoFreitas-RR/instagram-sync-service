from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from instagrapi import Client
from instagrapi.exceptions import ClientThrottledError, ClientLoginRequired
import logging

app = FastAPI(title="Instagram Sync Service via Instagrapi")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncRequest(BaseModel):
    username: str
    user_id: str  # do Supabase auth, só para log/identificação


class SyncResponse(BaseModel):
    profile: dict
    posts: list[dict]


cl = Client()
cl.delay_range = [1, 3]  # delay natural entre requests para evitar 429


@app.get("/")
async def health():
    return {"status": "ok", "service": "instagram-sync"}


@app.post("/sync", response_model=SyncResponse)
async def sync_instagram(request: SyncRequest):
    username = request.username.strip().lstrip("@")
    try:
        logger.info(f"Iniciando sync de @{username} for user {request.user_id}")

        user_id_ig = cl.user_id_from_username(username)
        user_info = cl.user_info(user_id_ig)

        profile_dict = {
            "username": user_info.username,
            "full_name": user_info.full_name or "",
            "bio": user_info.biography or "",
            "avatar_url": str(user_info.profile_pic_url) if user_info.profile_pic_url else None,
            "follower_count": user_info.follower_count,
            "following_count": user_info.following_count,
            "is_verified": user_info.is_verified,
            "external_id": str(user_info.pk),
            "raw_json": user_info.model_dump(mode="json"),
        }

        posts_list = []
        medias = cl.user_medias(user_id_ig, amount=10)  # limite baixo para teste

        for media in medias:
            try:
                thumb_url = None
                if media.thumbnail_url:
                    thumb_url = str(media.thumbnail_url)
                elif hasattr(media, "resources") and media.resources:
                    thumb_url = str(media.resources[0].thumbnail_url)

                post_dict = {
                    "external_post_id": str(media.pk),
                    "created_time": media.taken_at.isoformat() if media.taken_at else None,
                    "text": media.caption_text or "",
                    "post_type": (
                        media.product_type.lower()
                        if hasattr(media, "product_type") and media.product_type
                        else ("video" if media.media_type == 2 else ("album" if media.media_type == 8 else "image"))
                    ),
                    "likes_count": media.like_count or 0,
                    "comments_count": media.comment_count or 0,
                    "views_count": getattr(media, "view_count", None),
                    "hashtags": [h.name for h in media.caption_hashtags] if media.caption_hashtags else [],
                    "mentions": [m.user.username for m in media.usertags] if media.usertags else [],
                    "media_urls": [
                        {
                            "type": "video" if media.media_type == 2 else ("album" if media.media_type == 8 else "image"),
                            "url": thumb_url,
                        }
                    ],
                    "raw_json": media.model_dump(mode="json"),
                }
                posts_list.append(post_dict)
            except Exception as post_err:
                logger.warning(f"Error parsing post {media.pk}: {post_err}")
                continue

        logger.info(f"Sync complete: {len(posts_list)} posts fetched for @{username} via Instagrapi")
        return {"profile": profile_dict, "posts": posts_list}

    except ClientThrottledError:
        logger.error("429 Throttled - Instagram rate limit")
        raise HTTPException(status_code=429, detail="Rate limit hit - try again later")
    except Exception as e:
        logger.error(f"Instagrapi error for @{username}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
