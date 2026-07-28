from .base import HistoryProvider
from .takeout_provider import GoogleTakeoutProvider
from .browser_extension_provider import BrowserExtensionProvider

# YouTube API provider uses google-auth which may have platform issues
# Import it lazily when actually needed
def __getattr__(name):
    if name == "YouTubeAPIProvider":
        from .youtube_api_provider import YouTubeAPIProvider
        return YouTubeAPIProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "HistoryProvider",
    "YouTubeAPIProvider",
    "GoogleTakeoutProvider",
    "BrowserExtensionProvider",
]
