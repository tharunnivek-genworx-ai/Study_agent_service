# Chunk 1 | pages 1–10

## # 1. FastAPI – Introduction

### Overview of FastAPI

* FastAPI is a modern Python web framework for building APIs efficiently.
* It leverages Python's type hints feature, introduced in Python 3.6, for high performance.
* FastAPI is based on the Starlette and Pydantic libraries, making it one of the fastest web frameworks in Python, comparable to NodeJS and Go.

### Key Features of FastAPI

* High performance
* Fast development speed
* Reduced human-induced errors in code
* Easy to learn
* Production-ready
* Fully compatible with OpenAPI and JSON schema standards

### History of FastAPI

* Developed by Sebastian Ramirez in December 2018
* Current version: 0.68.0

## # 2. FastAPI – Environment Setup

### Installing FastAPI

* Use pip installer to install FastAPI in a virtual environment.
* Run the following command:
```bash
pip3 install fastapi
```
* This will also install the required Starlette and Pydantic libraries.

### Installing Uvicorn

* FastAPI doesn't come with a built-in server application.
* Use pip installer to install the Uvicorn ASGI server.
* Run the following command:
```bash
pip3 install uvicorn
```
* This will also install the required dependencies, including asgiref, click, h11, and typing-extensions.

## # 2. FastAPI – Hello World

### Creating a FastAPI App

* Declare the application object of the FastAPI class.
* Create a path operation by binding a view function to a URL and the corresponding HTTP method.
* For example:
```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```
* Save the code as main.py.

### Running the FastAPI App

* Use the Uvicorn server to run the FastAPI app.
* Run the following command:
```bash
uvicorn main:app --reload
```
* This will start the Uvicorn server and listen for client requests.

## # 3. FastAPI – OpenAPI

### Automatic Documentation

* FastAPI generates a schema using OpenAPI specifications.
* The specification determines how to define API paths, path parameters, etc.
* The API schema defined by the OpenAPI standard decides how the data is sent.

### Using Swagger UI

* Click the "try it out" button and then the "Execute" button.
* A screenshot of the FastAPI Swagger UI will be displayed, showing the executed request details.

### Using ReDoc

* Enter http://localhost:8000/redoc as the URL in the browser's address bar.
* A screenshot of the FastAPI ReDoc interface will be displayed, showing the API documentation layout and response example.

## # 4. FastAPI – Uvicorn

### Overview of Uvicorn

* Uvicorn is an ASGI server that implements the ASGI standards.
* It is lightning-fast and supports HTTP/2 and WebSockets.
* Uvicorn uses the uvloop and httptools libraries.

### Installing Uvicorn

* Use pip installer to install Uvicorn with minimal dependencies.
* Run the following command:
```bash
pip3 install uvicorn
```
* This will also install the required dependencies, including cython-based dependencies and additional libraries.

### Running Uvicorn

* Use the Uvicorn server to run the FastAPI app.
* Run the following command:
```bash
uvicorn main:app -reload
```
* This will start the Uvicorn server and listen for client requests.

### Command-Line Options

* Use the following command-line options to customize the Uvicorn server:
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000 --uds /tmp/uvicorn.sock --fd 3
```
* These options enable auto-reload, bind the server to a specific host and port, and use a UNIX domain socket.

### Launching Uvicorn Programmatically

* Use the uvicorn.run() method to launch the Uvicorn server programmatically.
* For example:
```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
```