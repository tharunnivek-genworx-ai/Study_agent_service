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


============================================================
CHUNK 2 SUMMARY | pages 11–20
============================================================

## # 4. FastAPI – Uvicorn

### Launching Uvicorn Server Programmatically

Instead of starting the Uvicorn server from the command line, it can be launched programmatically. This is achieved by calling the `uvicorn.run()` method in the Python code.

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

### Running the App.py File

To run the Uvicorn server in debug mode, execute the `app.py` file as a Python script using the following command:

```bash
(fastapienv) C:\fastapienv>python app.py
```

## # 5. FastAPI – Type Hints

### Introduction to Type Hints

FastAPI makes extensive use of the Type hinting feature available in Python 3.5 onwards. Type hinting helps in prompting the user with the expected type of the parameters to be passed.

### Defining Type Hints

To define type hints, add a colon and the data type after the parameter in the function definition. For example:

```python
def division(a: int, b: int) -> float:
    return a / b
```

### Using Type Hints with Static Type Checkers

Type hints do not prevent TypeError from appearing if an incompatible value is passed. Use a static type checker like MyPy to check for compatibility before running.

### Installing MyPy

To install MyPy, run the following command:

```bash
pip3 install mypy
```

### Checking for Type Errors

Save the following code as `typecheck.py` and check for type errors using MyPy:

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

Run the following command to check for type errors:

```bash
C:\python37>mypy typechk.py
```

## # 5. FastAPI – Type Hints

### Using Type Hints with Standard Data Types

All standard data types can be used as type hints. This can be done with global variables, variables as function parameters, inside function definitions, etc.

```python
x: int = 3
y: float = 3.14
```

### Using Type Hints with User-Defined Classes

Type hints can also be used with user-defined classes. For example:

```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h

def area(r: rectangle) -> int:
    return r.width * r.height
```

## # 6. FastAPI – IDE Support

### Using Type Hints with IDEs

Type hints are most effectively used in IDEs like PyCharm and VS Code to provide dynamic autocomplete features.

### Example with VS Code

In VS Code, type hints enable method suggestions when working with string variables.

### Example with PyCharm

In PyCharm, type hints enable completion popup for class instance attributes.

## # 7. FastAPI – REST Architecture

### Introduction to REST Architecture

REST (RElational State Transfer) is a software architectural style that defines how the architecture of a web application should behave.

### REST Constraints

REST recommends the following architectural constraints:

* Uniform interface
* Statelessness
* Client-server
* Cacheability
* Layered system
* Code on demand

### Advantages of REST Constraints

REST constraints have the following advantages:

* Scalability
* Simplicity
* Modifiability
* Reliability
* Portability
* Visibility

## # 8. FastAPI – Path Parameters

### Introduction to Path Parameters

Path parameters are used in modern web frameworks to provide routes or endpoints as part of the URL instead of file-based URLs.

### Example with FastAPI

In FastAPI, path parameters are given as a parameter to the operation decorator. For example:

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```

### Using Path Parameters with HTTP Verbs

Any of the following HTTP verbs can be used as operations:

| GET  | Sends data in unencrypted form to the server. Most common method. |
| ---- | ----------------------------------------------------------------- |
| HEAD | Same as GET, but without the response body.                       |


============================================================
CHUNK 3 SUMMARY | pages 21–30
============================================================

## # 8. FastAPI – Path Parameters

### Introduction

Path parameters are used to accept variable parameters in a URL. They can be accepted by using Python's string formatting notation.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, the `/hello/{name}` URL has a path parameter `name`. When a request is made to this URL, the value of `name` is passed to the `hello` function.

### Multiple Path Parameters

A route can have multiple parameters separated by the `/` symbol.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```

In this example, the `/hello/{name}/{age}` URL has two path parameters `name` and `age`.

### Type Hints for Path Parameters

You can use Python's type hints for the parameters of the function to be decorated. In this case, define `name` as `str` and `age` as `int`.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

This will result in the browser displaying an HTTP error message in the JSON response if the types don't match.

### Path Parameters with Types

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

If the URL given in the browser's address bar is `http://localhost:8000/hello/Ravi/20`, the data of `Ravi` and `20` will be assigned to variables `name` and `age` respectively.

### Path Parameters with Types (Error Handling)

If the types don't match, the browser will display an HTTP error message in the JSON response.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

If the URL given in the browser's address bar is `http://localhost:8000/hello/20/Ravi`, the browser's response will be as follows:

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

## # 9. FastAPI – Query Parameters

### Introduction

A classical method of passing the request data to the server is to append a query string to the URL.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `/hello` URL has query parameters `name` and `age`.

### Query Parameters with Type Hints

You can use Python's type hints for the parameters of the function to be decorated. In this case, define `name` as `str` and `age` as `int`.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

This will result in the browser displaying an HTTP error message in the JSON response if the types don't match.

### Mixed Path and Query Parameters

A route can have both path and query parameters.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `/hello/{name}` URL has a path parameter `name` and a query parameter `age`.

### Swagger UI for Path and Query Parameters

The Swagger UI (OpenAPI) documentation will show both path and query parameters.

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `/hello/{name}` URL has a path parameter `name` and a query parameter `age`. The Swagger UI will show both parameters.

### [CONTINUES INTO NEXT SECTION: Swagger UI for API Documentation]

