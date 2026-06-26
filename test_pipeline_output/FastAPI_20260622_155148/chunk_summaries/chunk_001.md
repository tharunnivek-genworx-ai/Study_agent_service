# Chunk 1 | pages 1–10

## # 1. FastAPI – Introduction

### Overview of FastAPI

* FastAPI is a modern Python web framework that is efficient in building APIs.
* It is based on Python's type hints feature, which was added in Python 3.6 onwards.
* FastAPI is one of the fastest web frameworks of Python.

### Key Features of FastAPI

* High performance: FastAPI works on the functionality of Starlette and Pydantic libraries, making its performance amongst the best and on par with NodeJS and Go.
* Fast development speed: FastAPI offers significant speed for development, reduces human-induced errors in the code, is easy to learn, and is completely production-ready.
* Compatibility with well-known standards: FastAPI is fully compatible with OpenAPI and JSON schema.

### History of FastAPI

* FastAPI was developed by Sebastian Ramirez in December 2018.
* The current version of FastAPI is 0.68.0.

## FastAPI – Environment Setup

### Installing FastAPI

* To install FastAPI, use the pip installer: `pip3 install fastapi`
* FastAPI depends on Starlette and Pydantic libraries, which are also installed.

### Installing Uvicorn

* FastAPI doesn't come with a built-in server application. To run FastAPI app, you need an ASGI server called Uvicorn.
* Install Uvicorn using pip installer: `pip3 install uvicorn`
* Uvicorn's dependencies, including asgiref, click, h11, and typing-extensions, are also installed.

## # 2. FastAPI – Hello World

### Creating a FastAPI App

* The first step in creating a FastAPI app is to declare the application object of FastAPI class: `from fastapi import FastAPI; app = FastAPI()`
* This app object is the main point of interaction of the application with the client browser.
* The uvicorn server uses this object to listen to client's requests.

### Creating Path Operations

* Path is a URL which when visited by the client invokes visits a mapped URL to one of the HTTP methods, an associated function is to be executed.
* We need to bind a view function to a URL and the corresponding HTTP method.
* For example, the index() function corresponds to ‘/’ path with ‘get’ operation: `@app.get("/"); async def root(): return {"message": "Hello World"}`

## # 3. FastAPI – OpenAPI

### Automatic Documentation

* FastAPI generates a schema using OpenAPI specifications.
* The specification determines how to define API paths, path parameters, etc.
* The API schema defined by the OpenAPI standard decides how the data is sent using JSON Schema.

### Viewing OpenAPI Documentation

* Visit http://127.0.0.1:8000/openapi.json from your browser to view the OpenAPI documentation.
* A neatly formatted JSON response will be displayed, including the API title, version, and paths.

### Redoc Documentation

* FastAPI also supports another automatic documentation method provided by Redoc.
* Enter http://localhost:8000/redoc as URL in the browser’s address bar to view the Redoc interface.
* The page displays the API title, a download link for the OpenAPI specification, and an "Index" section with a GET request to the root path.

## # 4. FastAPI – Uvicorn

### Introduction to Uvicorn

* Unlike the Flask framework, FastAPI doesn’t contain any built-in development server.
* Hence we need Uvicorn, which implements ASGI standards and is lightning fast.

### Uvicorn Features

* Uvicorn uses uvloop and httptools libraries.
* It also provides support for HTTP/2 and WebSockets, which cannot be handled by WSGI.
* The installation of Uvicorn as described earlier will install it with minimal dependencies.

### Running Uvicorn Server

* The application is launched on the Uvicorn server with the following command: `uvicorn main:app -reload`
* The --reload option enables the debug mode so that any changes in app.py will be automatically reflected and the display on the client browser will be automatically refreshed.

### Uvicorn Command-Line Options

* The following command-line options may be used:
  + --host TEXT: Bind socket to this host. [default 127.0.0.1]
  + --port INTEGER: Bind socket to this port. [default 8000]
  + --uds TEXT: Bind to a UNIX domain socket.
  + --fd INTEGER: Bind to socket from this file descriptor.
  + --reload: Enable auto-reload.
  + --reload-dir PATH: Set reload directories explicitly, default current working directory.
  + --reload-include TEXT: Include files while watching. Includes '*.py' by default.
  + --reload-exclude TEXT: Exclude while watching for files.
  + --reload-delay FLOAT: Delay between previous and next check default 0.25.
  + -loop [auto|asyncio|uvloop]: Event loop implementation. [default auto]
  + --http [auto|h11|httptools]: HTTP protocol implementation. [default auto]
  + --interface auto|asgi|asgi|wsgi: Select application interface. [default auto]
  + --env-file PATH: Environment configuration file.
  + --log-config PATH: Logging configuration file. Supported formats .ini, .json, .yaml.
  + --version: Display the uvicorn version and exit.
  + --app-dir TEXT: Look for APP in the specified directory default current directory.
  + --help: Show this message and exit.

### Launching Uvicorn Server Programmatically

* Instead of starting Uvicorn server from command line, it can be launched programmatically also.
* In the Python code, call uvicorn.run() method, using any of the parameters listed above.