from http import client
import os
from fastapi import Depends, FastAPI
from .services.spotifyService import SpotifyService

app = FastAPI()

# Temporary credentials retrieval
client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
spotify = SpotifyService(client_id=client_id, client_secret=client_secret)


@app.get("/")
def read_route():
    return "Hello World"


@app.get("/test_auth")
def test_auth():
    # TODO: remove this endpoint. This should be done behind the scenes
    result = spotify.auth()
    return result


@app.get("/users/{user_id}/playlists")
def get_user_playlists(user_id: str):
    #
    playlists = spotify.get_user_playlists(user_id)
    return playlists
