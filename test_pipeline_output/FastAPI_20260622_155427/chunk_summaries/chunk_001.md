# Chunk 1 | pages 1–10

## # 1. FastAPI – Introduction

### Overview of FastAPI

FastAPI is a modern Python web framework that is efficient in building APIs. It is based on Python's type hints feature, which was added in Python 3.6 onwards. FastAPI is one of the fastest web frameworks in Python, with performance comparable to NodeJS and Go.

### Key Features of FastAPI

* High performance
* Significant speed for development
* Reduced human-induced errors in the code
* Easy to learn
* Completely production-ready
* Fully compatible with well-known standards of APIs, namely OpenAPI and JSON schema

### History of FastAPI

FastAPI was developed by Sebastian Ramirez in December 2018. The current version of FastAPI is 0.68.0.

## FastAPI – Environment Setup

### Installing FastAPI

To install FastAPI, use the pip installer in a virtual environment:
```bash
pip3 install fastapi
```
This will also install the required dependencies, Starlette and Pydantic.

## Installing Uvicorn using PIP

### Installing Uvicorn

FastAPI does not come with a built-in server application. To run a FastAPI app, you need an ASGI server called Uvicorn. Install Uvicorn using pip:
```bash
pip3 install uvicorn
```
This will also install Uvicorn's dependencies, asgiref, click, h11, and typing-extensions.

## # 2. FastAPI – Hello World

### Creating a FastAPI App

The first step in creating a FastAPI app is to declare the application object of the FastAPI class:
```python
from fastapi import FastAPI

app = FastAPI()
```
This app object is the main point of interaction between the application and the client browser. The Uvicorn server uses this object to listen to client requests.

### Creating Path Operations

The next step is to create path operations. A path operation is a URL that, when visited by the client, invokes a mapped URL to one of the HTTP methods, an associated function is to be executed. We need to bind a view function to a URL and the corresponding HTTP method. For example, the index() function corresponds to the ‘/’ path with the ‘get’ operation:
```python
@app.get("/")
async def root():
    return {"message": "Hello World"}
```
The function returns a JSON response, but it can also return dict, list, str, int, etc. It can also return Pydantic models.

## # 3. FastAPI – OpenAPI

### Automatic Documentation

FastAPI generates a schema using OpenAPI specifications. The specification determines how to define API paths, path parameters, etc. The API schema defined by the OpenAPI standard decides how the data is sent using JSON Schema.

### Viewing OpenAPI Documentation

Visit http://127.0.0.1:8000/openapi.json from your browser to view the OpenAPI documentation. A neatly formatted JSON response will be displayed:
```json
{
  "openapi": "3.0.2",
  "info": {
    "title": "FastAPI",
    "version": "0.1.0"
  },
  "paths": {
    "/": {
      "get": {
        "summary": "Index",
        "operationId": "index__get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        }
      }
    }
  }
}
```
FastAPI also supports another automatic documentation method provided by Redoc.

## # 4. FastAPI – Uvicorn

### Uvicorn Server

Unlike the Flask framework, FastAPI does not contain any built-in development server. Hence, we need Uvicorn. It implements ASGI standards and is lightning-fast. ASGI stands for Asynchronous Server Gateway Interface.

### Installing Uvicorn

Install Uvicorn using pip:
```bash
pip3 install uvicorn(standard)
```
This will install Uvicorn with minimal dependencies. However, standard installation will also install cython-based dependencies along with other additional libraries.

### Running Uvicorn Server

Launch the Uvicorn server with the following command:
```bash
uvicorn main:app -reload
```
The --reload option enables the debug mode so that any changes in app.py will be automatically reflected and the display on the client browser will be automatically refreshed.

### Uvicorn Command-Line Options

| --host TEXT    | Bind socket to this host. [default 127.0.0.1] |
| -------------- | ---------------------------------------------- |
| --port INTEGER | Bind socket to this port. [default 8000]      |
| --uds TEXT     | Bind to a UNIX domain socket.                  |
| --fd INTEGER   | Bind to socket from this file descriptor.      |
| --reload       | Enable auto-reload.                            |

### Running Uvicorn Programmatically

Instead of starting the Uvicorn server from the command line, it can be launched programmatically also. In the Python code, call uvicorn.run() method using any of the parameters listed above:
```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
```
[CONTINUES INTO NEXT SECTION: Uvicorn Server]