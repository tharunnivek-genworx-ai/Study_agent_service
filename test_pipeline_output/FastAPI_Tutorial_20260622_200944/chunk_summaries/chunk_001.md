# Chunk 1 | pages 1–10

## FastAPI – Introduction and Environment Setup

### Overview
* **FastAPI**: modern Python web framework for building APIs
* **Based on**: Python's type hints feature (Python 3.6 onwards)
* **Performance**: one of the fastest web frameworks of Python
* **Functionality**: based on Starlette and Pydantic libraries
* **Compatibility**: OpenAPI and JSON schema standards
* **Developer**: Sebastian Ramirez (Dec. 2018)
* **Version**: 0.68.0

### Environment Setup
* **Install FastAPI**: `pip3 install fastapi`
* **Dependencies**: Starlette and Pydantic libraries installed automatically
* **Verify installation**: `pip3 freeze`

## Installing Uvicorn using PIP
* **Install Uvicorn**: `pip3 install uvicorn`
* **Dependencies**: asgiref, click, h11, and typing-extensions installed automatically
* **Verify installation**: `pip3 freeze`

## FastAPI Basics

### Creating the FastAPI App
* Declare the application object of FastAPI class: `app = FastAPI()`
* This object is the main point of interaction between the application and the client browser
* The uvicorn server uses this object to listen to client requests

### Path Operations
* A path operation is a URL that invokes a mapped URL to an HTTP method and executes an associated function
* Bind a view function to a URL and the corresponding HTTP method using decorators (e.g. `@app.get("/")`)
* Example: `@app.get("/")` maps to the `/` path with the `GET` operation

### View Functions
* A view function is a function that returns a response to a client request
* Can return:
	+ `dict`
	+ `list`
	+ `str`
	+ `int`
	+ Pydantic models
* Example: `async def root(): return {"message": "Hello World"}`

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

### Saving the Code
* Save the code as `main.py`

### [FIGURE: fastapi_hello_world_browser_response]
Components: Web browser, JSON response, FastAPI application, Uvicorn server
Connections: Client request, FastAPI app object, Uvicorn server
Purpose: Illustrates the result of running the FastAPI application with Uvicorn, displaying a JSON response in a web browser.

## FastAPI and OpenAPI

### Creating a FastAPI App
* Declare the application object of FastAPI class: `app = FastAPI()`
* `app` object is the main point of interaction between the application and the client browser
* Uvicorn server uses this object to listen to client requests

### Creating Path Operations
* Path is a URL that invokes a mapped URL to an HTTP method and associated function
* Bind a view function to a URL and HTTP method using decorators (e.g., `@app.get("/")`)
* Example: `@app.get("/")` maps to the `root()` function

### View Functions
* Return JSON response (or other types: `dict`, `list`, `str`, `int`, etc.)
* Can return Pydantic models
* Example: `async def root(): return {"message": "Hello World"}`

### Saving the Code
* Save the code as `main.py`

### OpenAPI Documentation
* FastAPI generates OpenAPI documentation automatically
* Access documentation at `/docs` (e.g., `http://127.0.0.1:8000/docs`)
* Swagger UI layout with endpoint summary and successful response status

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

## FastAPI and Uvicorn

### FastAPI Overview
* FastAPI is a Python web framework
* Unlike Flask, it doesn't contain a built-in development server
* Requires **Uvicorn** for development and production

### Uvicorn
* Implements **ASGI** (Asynchronous Server Gateway Interface) standards
* Lightning-fast and suitable for **asyncio** applications
* Replaces **WSGI** (Web Server Gateway Interface) compliant web servers
* Supports **HTTP/2** and **WebSockets**

### Running Uvicorn
* Launch application with: `uvicorn main:app -reload`
* **--reload** option enables debug mode and auto-refreshes display on client browser
* Available command-line options:
	+ `--host TEXT`: bind socket to this host (default: 127.0.0.1)
	+ `--port INTEGER`: bind socket to this port (default: 8000)
	+ `--uds TEXT`: bind to a UNIX domain socket
	+ `--fd INTEGER`: bind to socket from this file descriptor
	+ `--reload`: enable auto-reload

### Code Examples

```bash
pip3 install uvicorn(standard)
```

```bash
uvicorn main:app -reload
```

## Uvicorn Server Configuration

### Command Line Options
* `--reload-dir PATH`: Set reload directories explicitly (default: current working directory)
* `--reload-include TEXT`: Include files while watching (includes `*.py` by default)
* `--reload-exclude TEXT`: Exclude files while watching
* `--reload-delay FLOAT`: Delay between previous and next check (default: 0.25)
* `-loop [auto|asyncio|uvloop]`: Event loop implementation (default: auto)
* `--http [auto|h11|httptools]`: HTTP protocol implementation (default: auto)
* `--interface [auto|asgi|wsgi]`: Select application interface (default: auto)
* `--env-file PATH`: Environment configuration file
* `--log-config PATH`: Logging configuration file (supports .ini, .json, .yaml)
* `--version`: Display Uvicorn version and exit
* `--app-dir TEXT`: Look for APP in the specified directory (default: current directory)
* `--help`: Show this message and exit

## Launching Uvicorn Programmatically

* Use `uvicorn.run()` method in Python code
* Pass any of the above command line options as parameters
* Example:
```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
```

[CONTINUES INTO NEXT SECTION: Uvicorn Configuration]