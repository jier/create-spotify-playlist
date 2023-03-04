import os, requests, base64, json


class SpotifyService:
    _CLIENT_ID: str
    _CLIENT_SECRET: str
    _TOKEN: str

    _AUTH_URL: str = "https://accounts.spotify.com/api/token"
    # The base url has the API version fixed here. Maybe put it as a variable?
    _BASE_URL: str = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._CLIENT_ID = client_id
        self._CLIENT_SECRET = client_secret
        self.auth()

    def _header(self) -> dict:
        """Header to be used in regular requests. NOT FOR AUTH"""
        return {
            "Authorization": f"Bearer {self._TOKEN}",
            "Content-type": "application/",
        }

    def auth(self) -> bool:
        # The header containing the client and secret seems to not be working O_O
        header = {
            "Content-type": "application/x-www-form-urlencoded",
        }
        form = {
            "grant_type": "client_credentials",
            "client_id": self._CLIENT_ID,
            "client_secret": self._CLIENT_SECRET,
        }

        result_bytes = requests.post(self._AUTH_URL, headers=header, data=form)
        if result_bytes.status_code == 200:
            result = json.loads(result_bytes.content.decode("utf-8"))
            self._TOKEN = result["access_token"]
            return True
        return False

    def get_user_playlists(self, user_id: str):
        url = f"{self._BASE_URL}/users/{user_id}/playlists"
        result_bytes = requests.get(url, headers=self._header())
        result = json.loads(result_bytes.content.decode("utf-8"))
        return result
