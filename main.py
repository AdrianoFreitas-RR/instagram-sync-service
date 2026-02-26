from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from instagrapi import Client
from instagrapi.exceptions import ClientThrottledError, ClientLoginRequired

cl = Client()
cl.delay_range = [1, 3]  # delay natural entre requests para evitar 429

@app.post("/sync", response_model=SyncResponse)
async def sync_instagram(request: SyncRequest):
    username = request.username.strip().lstrip('@')
    try:
        user_id = cl.user_id_from_username(username)
        user_info = cl.user_info(user_id)

        profile_dict = {
            "username": user_info.username,
            "full_name": user_info.full_name or "",
            "bio": user_info.biography or "",
            "avatar_url": user_info.profile_pic_url,
            "follower_count": user_info.follower_count,
            "following_count": user_info.following_count,
            "is_verified": user_info.is_verified,
            "external_id": str(user_info.pk),
            "raw_json": user_info.dict()
        }

        posts_list = []
        medias = cl.user_medias(user_id, amount=10)  # limite baixo para teste

        for media in medias:
            post_dict = {
                "external_post_id": media.pk,
                "created_time": media.taken_at.isoformat() if media.taken_at else None,
                "text": media.caption_text or "",
                "post_type": media.product_type.lower() if hasattr(media, 'product_type') and media.product_type else "image",
                "likes_count": media.like_count,
                "comments_count": media.comment_count,
                "views_count": media.view_count if hasattr(media, 'view_count') else None,
                "hashtags": [h.name for h in media.caption_hashtags] if media.caption_hashtags else [],
                "mentions": [m.user.username for m in media.usertags] if media.usertags else [],
                "media_urls": [{"type": "video" if media.media_type == 2 else ("album" if media.media_type == 8 else "image"), "url": str(media.thumbnail_url or media.resources[0].thumbnail_url if hasattr(media, 'resources') and media.resources else media.thumbnail_url)}],
                "raw_json": media.dict()
            }
            posts_list.append(post_dict)

        logger.info(f"Sync complete: {len(posts_list)} posts fetched for @{username} via Instagrapi")
        return {"profile": profile_dict, "posts": posts_list}

    except ClientThrottledError:
        logger.error("429 Throttled - Instagram rate limit")
        raise HTTPException(status_code=429, detail="Rate limit hit - try again later")
    except Exception as e:
        logger.error(f"Instagrapi error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
