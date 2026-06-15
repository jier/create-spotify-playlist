from ..settings import settings
from .playlistBuilderService import PlaylistBuilderService
from .spotifyService import SpotifyService

spotify = SpotifyService(
    client_id=settings.spotify_client_id,
    client_secret=settings.spotify_client_secret,
    redirect_uri=settings.spotify_redirect_uri,
)
playlist_builder = PlaylistBuilderService(spotify)
