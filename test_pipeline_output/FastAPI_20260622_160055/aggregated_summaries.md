============================================================
CHUNK 1 SUMMARY | pages 1–10
============================================================

## # 1. FastAPI – Introduction

### Overview of FastAPI

* FastAPI is a modern Python web framework that is efficient in building APIs.
* It is based on Python's type hints feature, which was added in Python 3.6 onwards.
* FastAPI is one of the fastest web frameworks of Python.

### Key Features of FastAPI

* High performance: FastAPI works on the functionality of Starlette and Pydantic libraries, making its performance amongst the best and on par with that of NodeJS and Go.
* Significant speed for development: FastAPI offers significant speed for development, reducing human-induced errors in the code.
* Easy to learn: FastAPI is easy to learn and is completely production-ready.
* Fully compatible with well-known standards of APIs: FastAPI is fully compatible with OpenAPI and JSON schema.

### History of FastAPI

* FastAPI was developed by Sebastian Ramirez in December 2018.
* The currently available version of FastAPI is 0.68.0.

## # 2. FastAPI – Environment Setup

### Installing FastAPI

* To install FastAPI, use the pip installer.
* The command to install FastAPI is: `pip3 install fastapi`

### Installing Uvicorn

* FastAPI doesn't come with any built-in server application.
* To run FastAPI app, you need an ASGI server called uvicorn.
* The command to install uvicorn is: `pip3 install uvicorn`
* Uvicorn will also install its dependencies, including asgiref, click, h11, and typing-extensions.

## # 2. FastAPI – Hello World

### Creating a FastAPI App

* The first step in creating a FastAPI app is to declare the application object of FastAPI class.
* The command to create a FastAPI app is: `from fastapi import FastAPI; app = FastAPI()`
* This app object is the main point of interaction of the application with the client browser.
* The uvicorn server uses this object to listen to client's request.

### Creating Path Operations

* Path is a URL which when visited by the client invokes visits a mapped URL to one of the HTTP methods, an associated function is to be executed.
* We need to bind a view function to a URL and the corresponding HTTP method.
* For example, the index() function corresponds to ‘/’ path with ‘get’ operation.
* The command to create a path operation is: `@app.get("/"); async def root(): return {"message": "Hello World"}`

## # 3. FastAPI – OpenAPI

### Automatic Documentation

* FastAPI generates a schema using OpenAPI specifications.
* The specification determines how to define API paths, path parameters, etc.
* The API schema defined by the OpenAPI standard decides how the data is sent using JSON Schema.
* Visit http://127.0.0.1:8000/openapi.json to see the automatically generated OpenAPI documentation.

### Redoc Documentation

* FastAPI also supports another automatic documentation method provided by Redoc.
* Enter http://localhost:8000/redoc as URL in the browser’s address bar to see the Redoc interface.

## # 4. FastAPI – Uvicorn

### ASGI Standards

* Unlike the Flask framework, FastAPI doesn’t contain any built-in development server.
* Hence we need Uvicorn, which implements ASGI standards and is lightning fast.
* ASGI stands for Asynchronous Server Gateway Interface.

### Uvicorn Installation

* The installation of Uvicorn as described earlier will install it with minimal dependencies.
* However, standard installation will also install cython based dependencies along with other additional libraries.
* The command to install Uvicorn is: `pip3 install uvicorn(standard)`

### Uvicorn Server

* The application is launched on the Uvicorn server with the following command: `uvicorn main:app -reload`
* The --reload option enables the debug mode so that any changes in app.py will be automatically reflected and the display on the client browser will be automatically refreshed.

### Uvicorn Command-Line Options

* The following command-line options may be used:
  * --host TEXT: Bind socket to this host. [default 127.0.0.1]
  * --port INTEGER: Bind socket to this port. [default 8000]
  * --uds TEXT: Bind to a UNIX domain socket.
  * --fd INTEGER: Bind to socket from this file descriptor.
  * --reload: Enable auto-reload.
  * --reload-dir PATH: Set reload directories explicitly, default current working directory.
  * --reload-include TEXT: Include files while watching. Includes '*.py' by default
  * --reload-exclude TEXT: Exclude while watching for files.
  * --reload-delay FLOAT: Delay between previous and next check default 0.25
  * -loop [auto|asyncio|uvloop]: Event loop implementation. [default auto]
  * --http [auto|h11|httptools]: HTTP protocol implementation. [default auto]
  * --interface auto|asgi|asgi|wsgi: Select application interface. [default auto]
  * --env-file PATH: Environment configuration file.
  * --log-config PATH: Logging configuration file. Supported formats .ini, .json, .yaml.
  * --version: Display the uvicorn version and exit.
  * --app-dir TEXT: Look for APP in the specified directory default current directory
  * --help: Show this message and exit.

### Launching Uvicorn Programmatically

* Instead of starting Uvicorn server from command line, it can be launched programmatically also.
* In the Python code, call uvicorn.run() method, using any of the parameters listed above:
```python
import uvicorn
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}

uvicorn.run(app, host="0.0.0.0", port=8000)
```


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

### Running the App.py Script

To run the app.py script, use the following command:

```bash
(fastapienv) C:\fastapienv>python app.py
```

This will launch the Uvicorn server in debug mode.

## # 5. FastAPI – Type Hints

### Introduction to Type Hints

FastAPI makes extensive use of the Type hinting feature available in Python 3.5 onwards. Type hints are used to specify the expected data type of a variable, function parameter, or return value.

### Example: Division Function

The following example demonstrates a division function with type hints:
```python
def division(a: int, b: int) -> float:
    return a / b
```
In this example, the `a` and `b` parameters are expected to be integers, and the function returns a float value.

### Using MyPy for Static Type Checking

To check for type errors, use the MyPy static type checker:
```bash
pip3 install mypy
```
Save the following code as typecheck.py:
```python
def division(x: int, y: int) -> int:
    return x // y

a = division(10, 2)
print(a)

b = division(5, 2.5)
print(b)

c = division("Hello", 10)
print(c)
```
Run MyPy to check for type errors:
```bash
C:\python37>mypy typechk.py
typechk.py:7: error: Argument 2 to "division" has incompatible type "float"; expected "int"
typechk.py:10: error: Argument 1 to "division" has incompatible type "str"; expected "int"
Found 2 errors in 1 file (checked 1 source file)
```
## # 5. FastAPI – Type Hints

### Using Type Hints with Standard Data Types

Type hints can be used with standard data types, such as integers, floats, strings, and booleans:
```python
x: int = 3
y: float = 3.14
```
### Using Type Hints with Collection Types

Type hints can also be used with collection types, such as lists, tuples, and dictionaries:
```python
from typing import List, Tuple, Dict

cities: List[str] = ['Mumbai', 'Delhi', 'Chennai']
employee: Tuple[str, int, float] = ('Ravi', 25, 35000)
marklist: Dict[str, int] = {'Ravi': 61, 'Anil': 72}
```
## # 6. FastAPI – IDE Support

### Using Type Hints in IDEs

Type hints are used in IDEs such as PyCharm and VS Code to provide dynamic autocomplete features.

### Example: Rectangle Class

The following example demonstrates a rectangle class with type hints:
```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h
```
## # 6. FastAPI – IDE Support

### Using Type Hints with User-Defined Classes

Type hints can be used with user-defined classes, such as the rectangle class:
```python
def area(r: rectangle) -> int:
    return r.width * r.height
```
## # 7. FastAPI – REST Architecture

### Introduction to REST Architecture

REST (RElational State Transfer) is a software architectural style that defines how the architecture of a web application should behave.

### REST Constraints

REST recommends certain architectural constraints:

* Uniform interface
* Statelessness
* Client-server
* Cacheability
* Layered system
* Code on demand

### Advantages of REST Constraints

REST constraints have several advantages, including:

* Scalability
* Simplicity
* Modifiability
* Reliability
* Portability
* Visibility

## # 8. FastAPI – Path Parameters

### Introduction to Path Parameters

Path parameters are used in FastAPI to specify the path or route of a URL.

### Example: Path Operation Decorator

The following example demonstrates a path operation decorator:
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```
In this example, the `"/"` path is specified as a parameter to the `@app.get("/")` decorator.

### Using Path Parameters with HTTP Verbs

Path parameters can be used with various HTTP verbs, including GET, POST, PUT, and DELETE.

[CONTINUES INTO NEXT SECTION: Path Parameters]


============================================================
CHUNK 3 SUMMARY | pages 21–30
============================================================

## # 8. FastAPI – Path Parameters

### Overview

Path parameters are used to accept variable parameters in a URL. They can be used to pass dynamic values to a function.

### Syntax

Path parameters are defined using curly brackets `{}` in the URL path. For example:
```python
@app.get("/hello/{name}")
```
The variable parameter `name` can be accessed in the function using the `name` parameter.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```
In this example, the `hello` function takes a `name` parameter, which is passed from the URL path.

### Multiple Path Parameters

A route can have multiple path parameters separated by the `/` symbol. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```
### Type Hints

Path parameters can have type hints to specify the expected data type. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is expected to be a string and the `age` parameter is expected to be an integer.

### Error Handling

If the type hints are not met, FastAPI will return an error message. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
If the URL is `http://localhost:8000/hello/20/Ravi`, FastAPI will return an error message:
```json
{
  "detail": [
    {
      "loc": [
        "path",
        "age"
      ],
      "msg": "value is not a valid integer",
      "type": "type_error.integer"
    }
  ]
}
```
### Swagger UI

Path parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In the Swagger UI, the `name` parameter is shown as a string and the `age` parameter is shown as an integer.

[FIGURE: fastapi_swagger_ui_typed_path_parameters]

## # 9. FastAPI – Query Parameters

### Overview

Query parameters are used to pass data to a function using the URL query string. They can be used to pass dynamic values to a function.

### Syntax

Query parameters are defined using the `?` symbol in the URL query string. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
The query string can be accessed in the function using the `name` and `age` parameters.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `hello` function takes `name` and `age` parameters, which are passed from the URL query string.

### Type Hints

Query parameters can have type hints to specify the expected data type. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is expected to be a string and the `age` parameter is expected to be an integer.

### Swagger UI

Query parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In the Swagger UI, the `name` parameter is shown as a string and the `age` parameter is shown as an integer.

[FIGURE: fastapi_swagger_ui_query_parameter_response]

### Mixed Parameters

A route can have both path and query parameters. For example:
```python
@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is a path parameter and the `age` parameter is a query parameter.

[FIGURE: fastapi_swagger_ui_mixed_parameters]

### Carryover Context

The previous chunk discussed path operations and how to define them using the `@app.get()` decorator. It also discussed how to use path parameters and how to define them using curly brackets `{}` in the URL path.

### Continues into Next Section

The next section will discuss how to use FastAPI to handle HTTP requests and responses. It will cover topics such as request and response objects, HTTP methods, and status codes.

