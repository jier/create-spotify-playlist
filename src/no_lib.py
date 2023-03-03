import os
import requests,json, base64

# Get environment variables
USER = os.getenv('SPOTIPY_CLIENT_ID')
PASSWORD = os.environ.get('SPOTIPY_CLIENT_SECRET')

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
    auth_header = {}
    auth_data = {}
    message = f"{client_id}:{client_secret}"
    base64_message = base64.b64encode(message.encode('ascii')).decode('ascii')
    auth_header['Authorization'] = "Basic " + base64_message
    auth_data['grant_type'] = "client_credentials"
    response = requests.post(auth_url, headers=auth_header, data=auth_data).json()
    return response['access_token']
access_token = get_access_token(
    client_id = os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
)
# print(access_token)
# print(os.getenv("SPOTIPY_USER_ID"))
headers = {"Accept": "application/json", "Authorization": "Bearer " + access_token}
offset=0
limit=1
extra_settings=f"?offset={offset}&limit={limit}"
url = GET_USERS_PLAYLIST_ENDPOINT.format(user_id=os.getenv("SPOTIPY_USER_ID"))+extra_settings
resp = requests.get(url=url, headers=headers)
print(resp.json())


def get_user_playlist(user_id, access_token):
    headers = {"Accept": "application/json", "Authorization": "Bearer " + access_token}
    url = GET_USERS_PLAYLIST_ENDPOINT.format(user_id=user_id)
    return requests.get(url=url, headers=headers).json()