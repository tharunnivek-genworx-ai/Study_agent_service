# Chunk 1 | pages 1–10

## # 1. FastAPI – Introduction

### Overview of FastAPI

* FastAPI is a modern Python web framework that is efficient in building APIs.
* It is based on Python's type hints feature, which was added in Python 3.6 onwards.
* FastAPI is one of the fastest web frameworks of Python.

### Key Features of FastAPI

* High performance: FastAPI works on the functionality of Starlette and Pydantic libraries, making its performance amongst the best and on par with NodeJS and Go.
* Significant speed for development: FastAPI offers a significant speed for development, reducing human-induced errors in the code.
* Easy to learn: FastAPI is easy to learn and is completely production-ready.
* Fully compatible with well-known standards of APIs: FastAPI is fully compatible with OpenAPI and JSON schema.

### History of FastAPI

* FastAPI was developed by Sebastian Ramirez in December 2018.
* The currently available version of FastAPI is 0.68.0.

## # 2. FastAPI – Hello World

### Creating a FastAPI App

* The first step in creating a FastAPI app is to declare the application object of the FastAPI class.
* This app object is the main point of interaction of the application with the client browser.
* The uvicorn server uses this object to listen to client's requests.

### Creating Path Operations

* Path is a URL which when visited by the client invokes visits a mapped URL to one of the HTTP methods, an associated function is to be executed.
* We need to bind a view function to a URL and the corresponding HTTP method.
* For example, the index() function corresponds to the ‘/’ path with ‘get’ operation.

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

## # 3. FastAPI – OpenAPI

### Automatic Documentation

* FastAPI generates a schema using OpenAPI specifications.
* The specification determines how to define API paths, path parameters, etc.
* The API schema defined by the OpenAPI standard decides how the data is sent.

### Example Code

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

## # 4. FastAPI – Uvicorn

### Introduction to Uvicorn

* Unlike the Flask framework, FastAPI doesn’t contain any built-in development server.
* Hence we need Uvicorn, which implements ASGI standards and is lightning fast.

### Key Features of Uvicorn

* ASGI standards: Uvicorn implements ASGI standards, which provide high speed performance, comparable to web apps built with Node and Go.
* HTTP/2 and WebSockets: Uvicorn provides support for HTTP/2 and WebSockets, which cannot be handled by WSGI.
* Minimal dependencies: The installation of Uvicorn as described earlier will install it with minimal dependencies.

### Example Code

```bash
pip3 install uvicorn(standard)
```

```bash
uvicorn main:app -reload
```

### Command-Line Options

| --host TEXT    | Bind socket to this host. \[default 127.0.0.1] |
| -------------- | ---------------------------------------------- |
| --port INTEGER | Bind socket to this port. \[default 8000]      |
| --uds TEXT     | Bind to a UNIX domain socket.                  |
| --fd INTEGER   | Bind to socket from this file descriptor.      |
| --reload       | Enable auto-reload.                            |

### Example Code

```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
```

[CONTINUES INTO NEXT SECTION: Uvicorn Configuration]