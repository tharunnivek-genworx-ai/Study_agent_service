============================================================
CHUNK 1 SUMMARY | pages 1–10
============================================================

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


============================================================
CHUNK 2 SUMMARY | pages 11–20
============================================================

## # 4. FastAPI – Uvicorn

### Launching Uvicorn Server Programmatically

Instead of starting the Uvicorn server from the command line, it can be launched programmatically using the `uvicorn.run()` method.

```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
```

### Running the App

To run the app, execute the following command:

```bash
(fastapienv) C:\fastapienv>python app.py
```

### Uvicorn Server in Debug Mode

The Uvicorn server will be launched in debug mode.

## # 5. FastAPI – Type Hints

### Introduction to Type Hints

FastAPI makes extensive use of the Type hinting feature made available in Python's version 3.5 onwards. Type hints help in prompting the user with the expected type of the parameters to be passed.

### Type Hints for Function Parameters

To add type hints for function parameters, use a colon and data type after the parameter. For example:

```python
def division(a: int, b: int) -> float:
    return a / b
```

### Type Hints for Return Values

To add type hints for return values, use an arrow (->) and the type before the colon symbol in the function's definition statement. For example:

```python
def division(a: int, b: int) -> float:
    return a / b
```

### Using MyPy Static Type Checker

To check for type errors, use the MyPy static type checker. Install MyPy using pip:

```bash
pip3 install mypy
```

### Example Code

Save the following code as typecheck.py:

```python
def division(x: int, y: int) -> int:
    return (x // y)

a = division(10, 2)
print(a)

b = division(5, 2.5)
print(b)

c = division("Hello", 10)
print(c)
```

Check this code for type errors using MyPy:

```bash
C:\python37>mypy typechk.py
typechk.py:7: error: Argument 2 to "division" has incompatible type "float"; expected "int"
typechk.py:10: error: Argument 1 to "division" has incompatible type "str"; expected "int"
Found 2 errors in 1 file (checked 1 source file)
```

## # 5. FastAPI – Type Hints

### Using Standard Data Types as Type Hints

All standard data types can be used as type hints. For example:

```python
x: int = 3
y: float = 3.14
```

### Using Typing Module

The typing module defines special types for corresponding standard collection types. For example:

```python
from typing import List, Tuple, Dict

cities: List[str] = ['Mumbai', 'Delhi', 'Chennai']
employee: Tuple[str, int, float] = ('Ravi', 25, 35000)
marklist: Dict[str, int] = {'Ravi': 61, 'Anil': 72}
```

## # 6. FastAPI – IDE Support

### Using Type Hints in IDEs

The Type Hinting feature of Python is most effectively used in almost all IDEs (Integrated Development Environments) such as PyCharm and VS Code to provide dynamic autocomplete features.

### Example Code

```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h

def area(r: rectangle) -> int:
    return r.width * r.height

r1 = rectangle(10, 20)
print("area = ", area(r1))
```

## # 7. FastAPI – REST Architecture

### Introduction to REST

REST (RElational State Transfer) is a software architectural style. REST defines how the architecture of a web application should behave.

### REST Constraints

REST recommends certain architectural constraints:

* Uniform interface
* Statelessness
* Client-server
* Cacheability
* Layered system
* Code on demand

### Advantages of REST

REST constraints have the following advantages:

* Scalability
* Simplicity
* Modifiability
* Reliability
* Portability
* Visibility

## # 8. FastAPI – Path Parameters

### Introduction to Path Parameters

Modern web frameworks use routes or endpoints as a part of URL instead of file-based URLs. In FastAPI, it is termed a path. A path or route is the part of the URL trailing after the first ‘/’.

### Example Code

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```

### HTTP Verbs

Any of the following HTTP verbs can be used as operations:

| GET  | Sends data in unencrypted form to the server. Most common method. |
| ---- | ----------------------------------------------------------------- |
| HEAD | Same as GET, but without the response body.                       |


============================================================
CHUNK 3 SUMMARY | pages 21–30
============================================================

## 8. FastAPI – Path Parameters

### Overview

Path parameters are used to accept variable parameters in a URL. They can be used to accept different values in each client request.

### Syntax

Path parameters are defined using curly brackets `{}` in the URL path. For example:

```python
@app.get("/hello/{name}")
```

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, the `name` parameter is a path parameter. When the URL `http://localhost:8000/hello/Tutorialspoint` is accessed, the `name` variable will be assigned the value `Tutorialspoint`.

### Multiple Path Parameters

A route can have multiple parameters separated by the `/` symbol.

```python
@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```

### Typed Path Parameters

Path parameters can be typed using Python's type hints.

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `name` parameter is a string and the `age` parameter is an integer. If the URL `http://localhost:8000/hello/20/Ravi` is accessed, an HTTP error message will be returned because the `age` parameter is not an integer.

### Path Parameters in Swagger UI

Path parameters are displayed in the Swagger UI (OpenAPI) documentation.

[FIGURE: fastapi_swagger_ui_path_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with a parameter field filled with TutorialsPoint and an Execute button.

### Path Parameters with Multiple Types

A path parameter can have multiple types.

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Path Parameters with Default Values

A path parameter can have a default value.

```python
@app.get("/hello/{name}")
async def hello(name: str = "World"):
    return {"name": name}
```

### Path Parameters with Regular Expressions

A path parameter can be validated using regular expressions.

```python
from fastapi import FastAPI, Path

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str = Path(..., title="The Name", description="The name to greet", regex="^[a-zA-Z]+$")):
    return {"name": name}
```

### Path Parameters with Validation

A path parameter can be validated using Python's built-in validation functions.

```python
from fastapi import FastAPI, Path

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str = Path(..., title="The Name", description="The name to greet", min_length=2, max_length=10)):
    return {"name": name}
```

## 9. FastAPI – Query Parameters

### Overview

Query parameters are used to pass data to the server as a query string in the URL.

### Syntax

Query parameters are defined using the `?` symbol in the URL.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `name` and `age` parameters are query parameters. When the URL `http://localhost:8000/hello?name=Ravi&age=20` is accessed, the `name` variable will be assigned the value `Ravi` and the `age` variable will be assigned the value `20`.

### Typed Query Parameters

Query parameters can be typed using Python's type hints.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Query Parameters in Swagger UI

Query parameters are displayed in the Swagger UI (OpenAPI) documentation.

[FIGURE: fastapi_swagger_ui_query_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello endpoint with query parameters.

### Query Parameters with Multiple Types

A query parameter can have multiple types.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Query Parameters with Default Values

A query parameter can have a default value.

```python
@app.get("/hello")
async def hello(name: str = "World", age: int = 20):
    return {"name": name, "age": age}
```

### Query Parameters with Regular Expressions

A query parameter can be validated using regular expressions.

```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/hello")
async def hello(name: str = Query(..., title="The Name", description="The name to greet", regex="^[a-zA-Z]+$"), age: int = Query(..., title="The Age", description="The age to greet", regex="^[0-9]+$")):
    return {"name": name, "age": age}
```

### Query Parameters with Validation

A query parameter can be validated using Python's built-in validation functions.

```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/hello")
async def hello(name: str = Query(..., title="The Name", description="The name to greet", min_length=2, max_length=10), age: int = Query(..., title="The Age", description="The age to greet", ge=0, le=100)):
    return {"name": name, "age": age}
```

