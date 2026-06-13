import os
import requests

# Get environment variables
USER = os.getenv("SPOTIPY_CLIENT_ID")
PASSWORD = os.environ.get("SPOTIPY_CLIENT_SECRET")

GET_USERS_PLAYLIST_ENDPOINT = "https://api.spotify.com/v1/users/{user_id}/playlists?"
GET_PLAYLIST_ENDPOINT = (
    "https://api.spotify.com/v1/users/{user_id}/playlists/{playlist_id}"
)
GET_PLAYLIST_TRACKS_ENDPOINT = (
    "https://api.spotify.com/v1/users/{user_id}/playlists/{playlist_id}/tracks"
)
GET_AUDIO_FEATURES = "https://api.spotify.com/v1/audio-features/{id}"
MAKE_PLAYLIST_ENDPOINT = "https://api.spotify.com/v1/users/{user_id}/playlists"
ADD_TRACK_TO_PLAYLIST_ENDPOINT = (
    "https://api.spotify.com/v1/users/{user_id}/playlists/{playlist_id}/tracks"
)


def get_access_token(client_id, client_secret):
    auth_url = "https://accounts.spotify.com/api/token"
    # message = f"{client_id}:{client_secret}"
    # base64_message = base64.b64encode(message.encode("ascii")).decode("ascii")
    auth_header = {
        "Content-type": "application/x-www-form-urlencoded",
    }
    auth_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    return requests.post(auth_url, headers=auth_header, data=auth_data).json()[
        "access_token"
    ]


access_token = get_access_token(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
)
# print(access_token)
# print(os.getenv("SPOTIPY_USER_ID"))


def get_user_playlist(user_id, access_token, offset=0, limit=20):
    extra_settings = f"?offset={offset}&limit={limit}"
    headers = {"Accept": "application/json", "Authorization": "Bearer " + access_token}
    url = GET_USERS_PLAYLIST_ENDPOINT.format(user_id=user_id) + extra_settings
    return requests.get(url=url, headers=headers).json()
