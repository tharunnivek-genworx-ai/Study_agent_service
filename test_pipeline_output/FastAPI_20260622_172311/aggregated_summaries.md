============================================================
CHUNK 1 SUMMARY | pages 1–10
============================================================

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

### Using MyPy for Static Type Checking

MyPy is a static type checker that can detect type-related errors in Python code. To use MyPy, install it using pip:

```bash
pip3 install mypy
```

### Example Code for MyPy

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

## # 5. FastAPI – Type Hints (continued)

### Using Type Hints with Standard Data Types

All standard data types can be used as type hints. This can be done with global variables, variables as function parameters, inside function definition, etc.

```python
x: int = 3
y: float = 3.14
```

### Using Type Hints with User-Defined Classes

It is also possible to use type hints with a user-defined class. In the following example, a rectangle class is defined with type hints for arguments to the `__init__()` constructor.

```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h
```

## # 6. FastAPI – IDE Support

### Introduction to IDE Support

The Type Hinting feature of Python is most effectively used in almost all IDEs (Integrated Development Environments) such as PyCharm and VS Code to provide dynamic autocomplete features.

### Example Code for IDE Support

In the example below, a function named as `sayhello` with name as an argument has been defined. The function returns a string by concatenating “Hello” to the name parameter by adding a space in between.

```python
def sayhello(name: str) -> str:
    return "Hello " + name.capitalize()
```

### Using Type Hints with User-Defined Classes in IDEs

It is also possible to use type hints with a user-defined class in IDEs. In the following example, a rectangle class is defined with type hints for arguments to the `__init__()` constructor.

```python
class rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h
```

## # 7. FastAPI – REST Architecture

### Introduction to REST Architecture

REST (RElational State Transfer) is a software architectural style. REST defines how the architecture of a web application should behave. It is a resource-based architecture where everything that the REST server hosts, (a file, an image, or a row in a table of a database), is a resource, having many representations.

### REST Constraints

REST recommends certain architectural constraints:

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

Modern web frameworks use routes or endpoints as a part of URL instead of file-based URLs. This helps the user to remember the application URLs more effectively. In FastAPI, it is termed a path. A path or route is the part of the URL trailing after the first ‘/’.

### Example Code for Path Parameters

In the following URL:

$$ \underline{\text{http://localhost:8000/hello/TutorialsPoint}} $$

the path or the route would be:

$$ \underline{\text{/hello/TutorialsPoint}} $$

In FastAPI, such a path string is given as a parameter to the operation decorator. The operation here refers to the HTTP verb used by the browser to send the data.

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```

[CONTINUES INTO NEXT SECTION: Path Parameters]


============================================================
CHUNK 3 SUMMARY | pages 21–30
============================================================

## 8. FastAPI – Path Parameters

### Overview

Path parameters are used to capture variable parts of a URL path. They are defined using curly brackets `{}` in the route path.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, the `/hello/{name}` route captures the variable part of the URL path and assigns it to the `name` parameter in the `hello` function.

### Using Path Parameters with Types

You can use Python's type hints to specify the type of the path parameter. For example:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `name` parameter is defined as a string (`str`) and the `age` parameter is defined as an integer (`int`).

### Path Parameters with Multiple Variables

A route can have multiple path parameters separated by the `/` symbol. For example:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```

### Swagger UI Documentation

When using path parameters, the Swagger UI documentation will display the parameter names and types. For example:

[FIGURE: fastapi_swagger_ui_typed_path_parameters]

### Path Parameters with Types and Multiple Variables

You can use Python's type hints to specify the type of the path parameter when using multiple variables. For example:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Query Parameters

Query parameters are used to capture variable parts of a URL query string. They are defined as function parameters in the route handler.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `/hello` route captures the query string parameters `name` and `age` and assigns them to the function parameters.

### Swagger UI Documentation

When using query parameters, the Swagger UI documentation will display the parameter names and types. For example:

[FIGURE: fastapi_swagger_ui_query_parameter_input]

### Mixed Path and Query Parameters

A route can have both path and query parameters. For example:

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `/hello/{name}` route captures the path parameter `name` and the query parameter `age`.

### Swagger UI Documentation

When using mixed path and query parameters, the Swagger UI documentation will display the parameter names and types. For example:

[FIGURE: fastapi_swagger_ui_mixed_parameters]

### Summary

Path parameters are used to capture variable parts of a URL path, while query parameters are used to capture variable parts of a URL query string. Both can be used together in a single route. The Swagger UI documentation will display the parameter names and types for both path and query parameters.

