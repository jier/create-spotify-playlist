import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from my_requests import *
from graph import *
from genetics import *

auth_manager = SpotifyClientCredentials()
# auth_manager.client_id
# auth_manager.client_secret
token = spotipy.util.prompt_for_user_token(
    username="swansoe",
    scope="playlist-modify-public",
    client_id=auth_manager.client_id,
    client_secret=auth_manager.client_secret,
    redirect_uri="http://localhost:8888",
)
sp = spotipy.Spotify(auth=token)
# token = auth_manager.get_access_token(as_dict=False)
# sp = spotipy.Spotify(client_credentials_manager=auth_manager)


playlists = sp.user_playlists(user="swansoe")
dataset = {"name": [], "uri": [], "id": []}
while playlists:
    for i, playlist in enumerate(playlists["items"]):
        dataset["name"].append(playlist["name"])
        dataset["id"].append(playlist["id"])
        dataset["uri"].append(playlist["uri"])
        # print("%4d %s %s" % (i + 1 + playlists['offset'], playlist['id'],  playlist['name']))
    if playlists["next"]:
        playlists = sp.next(playlists)
    else:
        playlists = None

# url_search_results = [getPlaylistTracks(playlistID=id, userID='swansoe', token=token) for id in dataset['id']]
url_search_results = getPlaylistTracks(
    playlistID=dataset["id"][0], userID="swansoe", token=token
)
playlist_data = getAudioFeaturesForList(items=url_search_results["items"], token=token)
print(f"Playlist_data {playlist_data}")
playlist_graph = makeGraph(playlist_data)
print(f"Inital playlist distance: {str(getInitWalkDist(playlist_graph))}")
population = initPopulation(playlistGraph=playlist_graph, numbDNA=20)

for i in range(0, 50):
    population = applyGenetics(population=population, graph=playlist_graph)
    population = sortWalks(population)
    best_walk = population[0]
    # print(f"Best playlist for this population: {str(best_walk[len(best_walk) - 1])}")
# sp.user_playlist_create
makePlaylist(
    playlistIDS=population[0][:-1],
    oldName=dataset["name"][0],
    token=token,
    userID="swansoe",
)
