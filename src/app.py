from fastapi import FastAPI

app= FastAPI()

@app.get('/')
def read_route():
    return "Hello World"

@app.get('/playlists')
def get_playlists():
    return "Hello World"