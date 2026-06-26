## FastAPI Introduction
* **FastAPI**: modern Python web framework for building APIs
* **Based on**: Python's type hints feature (Python 3.6 onwards)
* **Performance**: one of the fastest web frameworks of Python
* **Functionality**: based on Starlette and Pydantic libraries
* **Compatibility**: OpenAPI and JSON schema standards
* **Developer**: Sebastian Ramirez (Dec. 2018)
* **Version**: 0.68.0

## Environment Setup
* **Install FastAPI**: `pip3 install fastapi`
* **Dependencies**: Starlette and Pydantic libraries installed automatically
* **Verify installation**: `pip3 freeze`
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

## Type Hints in Python
### Function Parameters
* Use type hints for function parameters with the syntax `param_name: type`.
* Example: `def division(a: int, b: int) -> float:`
### Return Types
* Use the arrow operator `->` to specify the return type of a function.
* Example: `def division(a: int, b: int) -> float:`
### Static Type Checking
* Use a static type checker like **MyPy** to detect type errors before running the code.
* Install MyPy with `pip3 install mypy`.
### Example Code
```python
def division(x: int, y: int) -> int:
    return x // y
```

## FastAPI Path and Query Parameters
### HTTP Methods
* `POST`: sends HTML form data to the server, not cached by the server
* `PUT`: replaces all current representations of the target resource
* `DELETE`: removes all current representations of the target resource
### Path Parameters
* Use Python's string formatting notation to accept variable parameters
* Define variable parameters in the URL path and pass to function parameters
* Example: `/hello/{name}`
### Defining Path Parameters
* Use curly brackets `{}` to define path parameters in a route.
* Example: `/hello/{name}/{age}`
### Path Parameter Types
* Use Python type hints to define parameter types.
* Example: `name:str`, `age:int`
### Path Parameter Validation
* FastAPI validates path parameters based on their types.
* If types don't match, returns an HTTP error message.
### Example Code
```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name:str, age:int):
    return {"name": name, "age": age}
```
### Query String Basics
* A query string is a list of key-value pairs concatenated by the ampersand (&) symbol.
* The query string is appended to the URL by a question mark (?).
* Example: `http://localhost/cgi-bin/hello.py?name=Ravi&age=20`
### FastAPI Query Parameter Handling
* FastAPI automatically treats non-path parameters as query strings.
* Query parameters are parsed into parameters and values.
* Example:
```python
@app.get("/hello")
async def hello(name:str, age:int):
    return {"name": name, "age": age}
```
### Mixed Path and Query Parameters
* The `/hello/{name}` endpoint has both path and query parameters.
* The `name` parameter is a path parameter.
* The `age` parameter is a query parameter.
### Swagger UI Documentation
* Open the Swagger UI (OpenAPI) documentation by entering `http://localhost:8000/docs` as the URL.
* The parameter `name` is a path parameter.
* The parameter `age` is a query parameter.