import requests


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
            "Accept": "application/json",
        }

    def auth(self) -> bool:
        auth_header = {
            "Content-type": "application/x-www-form-urlencoded",
        }

        auth_form = {
            "grant_type": "client_credentials",
            "client_id": self._CLIENT_ID,
            "client_secret": self._CLIENT_SECRET,
        }

        response = requests.post(self._AUTH_URL, headers=auth_header, data=auth_form)

        if response.status_code == 200:
            self._TOKEN = response.json()["access_token"]
            return True
        return False

    def get_user_playlists(
        self, user_id: str, offset: int = 0, limit: int = 10
    ) -> dict:
        extra_settings = f"?offset={offset}&limit={limit}"
        url = f"{self._BASE_URL}/users/{user_id}/playlists" + extra_settings

        return requests.get(url=url, headers=self._header()).json()

    def _get_next_cursor(self, url: str) -> dict:
        return requests.post(url=url).json()
