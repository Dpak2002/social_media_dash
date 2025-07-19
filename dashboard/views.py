from django.shortcuts import render
from django.views.generic import TemplateView
from django.http import JsonResponse
import tweepy
from django.conf import settings
from django.core.cache import cache
import random
import logging



class CustomLoginView(TemplateView):
    template_name = "custom_login.html"




logger = logging.getLogger(__name__)

class DashboardView(TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Cache keys
        data_cache_key = 'dashboard_data_cache'
        lock_cache_key = 'twitter_api_lock'

        # Show old data if we're rate-limited
        if cache.get(lock_cache_key):
            logger.info("Rate limit hit — loading cached data.")
            cached = cache.get(data_cache_key)
            if cached:
                context.update(cached)
                context["notice"] = "Showing cached data due to Twitter API rate limit."
            else:
                context["error"] = "Rate limit hit and no cached data available."
            return context

        cache.set(lock_cache_key, True, timeout=60)

        try:
            client = tweepy.Client(
                bearer_token=settings.TWITTER_BEARER_TOKEN,
                consumer_key=settings.TWITTER_API_KEY,
                consumer_secret=settings.TWITTER_API_SECRET,
                access_token=settings.TWITTER_ACCESS_TOKEN,
                access_token_secret=settings.TWITTER_ACCESS_SECRET,
                wait_on_rate_limit=False
            )

            user_resp = client.get_me(
                user_fields=["id", "username", "name", "profile_image_url", "description", "public_metrics", "created_at"]
            )
            user = user_resp.data

            tweets_resp = client.get_users_tweets(
                user.id,
                max_results=5,
                tweet_fields=["created_at", "attachments"],
                expansions=["attachments.media_keys"],
                media_fields=["url", "preview_image_url", "type"]
            )

            media_map = {}
            if tweets_resp.includes and "media" in tweets_resp.includes:
                for media in tweets_resp.includes["media"]:
                    media_map[media.media_key] = {
                        "type": media.type,
                        "url": getattr(media, "url", None) or getattr(media, "preview_image_url", None)
                    }

            tweets = []
            for tweet in tweets_resp.data or []:
                tweet_data = {
                    "text": tweet.text,
                    "created_at": tweet.created_at,
                    "media": [],
                    "likes": random.randint(10, 100),
                    "comments": random.randint(0, 20)
                }
                if tweet.attachments and "media_keys" in tweet.attachments:
                    tweet_data["media"] = [
                        media_map.get(key)
                        for key in tweet.attachments["media_keys"]
                        if key in media_map
                    ]
                tweets.append(tweet_data)

            # Prepare final context
            dashboard_data = {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "name": user.name,
                    "bio": user.description,
                    "profile_image_url": user.profile_image_url,
                    "followers": user.public_metrics["followers_count"],
                    "following": user.public_metrics["following_count"],
                    "tweet_count": user.public_metrics["tweet_count"],
                    "created_at": user.created_at
                },
                "tweets": tweets
            }

            context.update(dashboard_data)

            # Cache it for 5 minutes
            cache.set(data_cache_key, dashboard_data, timeout=300)

        except tweepy.TooManyRequests:
            logger.warning("Twitter API rate limit hit.")
            cached = cache.get(data_cache_key)
            if cached:
                context.update(cached)
                context["notice"] = "Showing cached data due to rate limiting."
            else:
                context["error"] = "Rate limit hit and no cached data found."

        except Exception as e:
            logger.error("Twitter API error: %s", e)
            cached = cache.get(data_cache_key)
            if cached:
                context.update(cached)
                context["notice"] = "Showing cached data due to error."
            else:
                context["error"] = str(e)

        return context
def twitter_feed(request):
    if cache.get('twitter_api_lock'):
        return JsonResponse({"error": "Rate limit hit. Try again in a minute."}, status=429)
    
    cache.set('twitter_api_lock', True, timeout=60)

    client = tweepy.Client(
        bearer_token=settings.TWITTER_BEARER_TOKEN,
        consumer_key=settings.TWITTER_API_KEY,
        consumer_secret=settings.TWITTER_API_SECRET,
        access_token=settings.TWITTER_ACCESS_TOKEN,
        access_token_secret=settings.TWITTER_ACCESS_SECRET,
        wait_on_rate_limit=True  # Helps with auto wait on 429
    )

    try:
        # Get user info with additional fields
        user_resp = client.get_me(
            user_fields=["id", "username", "name", "profile_image_url", "description", "public_metrics", "created_at"]
        )
        user = user_resp.data

        # Get user tweets (expand media attachments)
        tweets_resp = client.get_users_tweets(
            user.id,
            max_results=5,
            tweet_fields=["created_at", "attachments"],
            expansions=["attachments.media_keys"],
            media_fields=["url", "preview_image_url", "type"]
        )

        tweets = []
        media_map = {}

        # Build media map if media included
        if tweets_resp.includes and "media" in tweets_resp.includes:
            for media in tweets_resp.includes["media"]:
                media_map[media.media_key] = {
                    "type": media.type,
                    "url": getattr(media, "url", None) or getattr(media, "preview_image_url", None)
                }

        for tweet in tweets_resp.data or []:
            tweet_data = {
                "text": tweet.text,
                "created_at": tweet.created_at,
                "media": []
            }
            if tweet.attachments and "media_keys" in tweet.attachments:
                tweet_data["media"] = [media_map.get(key) for key in tweet.attachments["media_keys"] if key in media_map]
            tweets.append(tweet_data)

        # Try getting liked tweets
        try:
            likes_resp = client.get_liked_tweets(
                user.id,
                max_results=5,
                tweet_fields=["created_at"]
            )
            likes = [
                {"text": like.text, "created_at": like.created_at}
                for like in likes_resp.data
            ] if likes_resp.data else []
        except Exception as e:
            likes = f"Could not fetch likes: {str(e)}"

        result = {
            "user": {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "bio": user.description,
                "profile_image_url": user.profile_image_url,
                "followers": user.public_metrics["followers_count"],
                "following": user.public_metrics["following_count"],
                "tweet_count": user.public_metrics["tweet_count"],
                "created_at": user.created_at
            },
            "tweets": tweets,
            "likes": likes,
        }

        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)




class TwitterProfileView(TemplateView):
    template_name = "profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if cache.get('twitter_api_lock'):
            context["error"] = "Rate limit hit. Try again later."
            return context
        
        cache.set('twitter_api_lock', True, timeout=60)

        client = tweepy.Client(
            bearer_token=settings.TWITTER_BEARER_TOKEN,
            consumer_key=settings.TWITTER_API_KEY,
            consumer_secret=settings.TWITTER_API_SECRET,
            access_token=settings.TWITTER_ACCESS_TOKEN,
            access_token_secret=settings.TWITTER_ACCESS_SECRET,
            wait_on_rate_limit=True
        )

        try:
            user_resp = client.get_me(
                user_fields=["id", "username", "name", "profile_image_url", "description", "public_metrics", "created_at"]
            )
            user = user_resp.data

            context["user"] = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "bio": user.description,
                "profile_image_url": user.profile_image_url,
                "followers": user.public_metrics["followers_count"],
                "following": user.public_metrics["following_count"],
                "tweet_count": user.public_metrics["tweet_count"],
                "created_at": user.created_at
            }

        except Exception as e:
            context["error"] = str(e)

        return context
