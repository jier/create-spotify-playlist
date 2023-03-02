from fastapi import FastAPI

app= FastAPI()

@app.get('/')
def read_route():
    return "Hello World"

@app.get('/test')
def read_test():
    return "Hello World"