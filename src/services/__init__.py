from src.services.playlistBuilderService import PlaylistBuilderService
from src.services.spotifyService import SpotifyService
from src.settings import settings

spotify = SpotifyService(
    client_id=settings.spotify_client_id,
    client_secret=settings.spotify_client_secret,
    redirect_uri=settings.spotify_redirect_uri,
)
playlist_builder = PlaylistBuilderService(spotify)
