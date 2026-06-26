============================================================
CHUNK 1 SUMMARY | pages 1–10
============================================================

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


============================================================
CHUNK 2 SUMMARY | pages 11–20
============================================================

## # 4. FastAPI – Uvicorn

### Launching Uvicorn Server Programmatically

Instead of starting the Uvicorn server from the command line, it can be launched programmatically. This can be achieved by calling the `uvicorn.run()` method in the Python code.

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

To run the app, execute the following command in the terminal:

```bash
(fastapienv) C:\fastapienv>python app.py
```

This will launch the Uvicorn server in debug mode.

## # 5. FastAPI – Type Hints

### Introduction to Type Hints

FastAPI makes extensive use of the Type hinting feature made available in Python's version 3.5 onwards. Type hinting helps in prompting the user with the expected type of the parameters to be passed.

### Basic Type Hints

In Python, a variable need not be declared to be belonging to a certain type, and its type is determined dynamically by the instantaneous value assigned to it. However, using type hints, we can specify the expected type of a variable.

```python
def division(a: int, b: int) -> float:
    return a / b
```

### Using MyPy Static Type Checker

To check for type errors, we can use the MyPy static type checker. Install MyPy using the following command:

```bash
pip3 install mypy
```

Save the following code as `typecheck.py`:

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

### Using Standard Data Types

All standard data types can be used as type hints. This can be done with global variables, variables as function parameters, inside function definition, etc.

```python
x: int = 3
y: float = 3.14
```

### Using Typing Module

The typing module defines special types for corresponding standard collection types. The types on typing module are `List`, `Tuple`, `Dict`, and `Sequence`. It also consists of `Union` and `Optional` types.

```python
from typing import List, Tuple, Dict

cities: List[str] = ['Mumbai', 'Delhi', 'Chennai']
employee: Tuple[str, int, float] = ('Ravi', 25, 35000)
marklist: Dict[str, int] = {'Ravi': 61, 'Anil': 72}
```

## # 6. FastAPI – IDE Support

### Using Type Hints in IDEs

The Type Hinting feature of Python is most effectively used in almost all IDEs (Integrated Development Environments) such as PyCharm and VS Code to provide dynamic autocomplete features.

### Example with VS Code

In the example below, a function named `sayhello` with name as an argument has been defined. The function returns a string by concatenating “Hello” to the name parameter by adding a space in between.

```python
def sayhello(name: str) -> str:
    return "Hello " + name.capitalize()
```

When you press dot (.) after `name`, a drop down list of all string methods appears, from which the required method (in this case `capitalize()`) can be picked.

## # 6. FastAPI – IDE Support

### Using Type Hints with User-Defined Classes

It is also possible to use type hints with a user-defined class. In the following example a rectangle class is defined with type hints for arguments to the `__init__()` constructor.

```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h
```

Following is a function that uses an object of above rectangle class as an argument. The type hint used in the declaration is the name of the class.

```python
def area(r: rectangle) -> int:
    return r.width * r.height
```

In this case also, the IDE editor provides autocomplete support prompting list of the instance attributes.

## # 7. FastAPI – REST Architecture

### Introduction to REST

REST (Relational State Transfer) is a software architectural style. REST defines how the architecture of a web application should behave. It is a resource-based architecture where everything that the REST server hosts, (a file, an image, or a row in a table of a database), is a resource, having many representations.

### REST Constraints

REST recommends certain architectural constraints.

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

Modern web frameworks use routes or endpoints as a part of URL instead of file-based URLs. This helps the user to remember the application URLs more effectively. In FastAPI, it is termed a path. A path or route is the part of the URL trailing after the first ‘/’.

### Example with FastAPI

In the following example, a path operation decorator is used to define a path.

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```

In this example, `"/"` is the path, `get` is the operation, `@app.get("/")` is the path operation decorator, and the `index()` function just below it is termed as path operation function.

### Using Path Parameters

Any of the following HTTP verbs can be used as operations.

| GET  | Sends data in unencrypted form to the server. Most common method. |
| ---- | ----------------------------------------------------------------- |
| HEAD | Same as GET, but without the response body.                       |

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```


============================================================
CHUNK 3 SUMMARY | pages 21–30
============================================================

## # 8. FastAPI – Path Parameters

### Overview

FastAPI supports path parameters, which are used to capture values from the URL path. These values can be used in the path operation function to return a response.

### Syntax

Path parameters are defined using curly brackets `{}` in the path. For example:

```python
@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, `{name}` is a path parameter that captures the value from the URL path.

### Types

Path parameters can have types defined using Python's type hints. For example:

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` is a string and `age` is an integer.

### Usage

Path parameters can be used to capture values from the URL path. For example:

```python
@app.get("/hello/Ravi/20")
async def hello(name, age):
    return {"name": name, "age": age}
```

In this example, the URL path `/hello/Ravi/20` captures the values `Ravi` and `20` for the `name` and `age` path parameters, respectively.

### Swagger UI

Path parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_path_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with a parameter field filled with TutorialsPoint and an Execute button.

### Error Handling

If the types of the path parameters do not match the values in the URL path, an error is returned. For example:

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

If the URL path is `/hello/20/Ravi`, an error is returned because `age` is an integer and cannot accept a string value.

## # 9. FastAPI – Query Parameters

### Overview

FastAPI supports query parameters, which are used to capture values from the query string. These values can be used in the path operation function to return a response.

### Syntax

Query parameters are defined using the `async def` syntax in the path operation function. For example:

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` and `age` are query parameters that capture the values from the query string.

### Usage

Query parameters can be used to capture values from the query string. For example:

```python
@app.get("/hello?name=Ravi&age=20")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the query string `?name=Ravi&age=20` captures the values `Ravi` and `20` for the `name` and `age` query parameters, respectively.

### Swagger UI

Query parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_query_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello endpoint with query parameters name and age.

### Mixed Parameters

FastAPI supports mixed parameters, which are a combination of path and query parameters. For example:

```python
@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` is a path parameter and `age` is a query parameter.

### Swagger UI

Mixed parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_mixed_parameters]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with both path and query parameters.

[CONTINUES INTO NEXT SECTION: Query Parameters with Default Values]

