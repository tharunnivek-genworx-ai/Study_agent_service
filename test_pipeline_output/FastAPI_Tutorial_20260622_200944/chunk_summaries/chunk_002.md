# Chunk 2 | pages 11–20

## FastAPI – Uvicorn

* **Uvicorn**: a Python ASGI server for running FastAPI applications.
* **ASGI**: Asynchronous Server Gateway Interface, a standard for building asynchronous web servers.
* **FastAPI**: a modern, fast (high-performance), web framework for building APIs with Python 3.7+.
* **uvicorn.run**: a function to run the FastAPI application.
* **reload=True**: enables automatic reloading of the application when code changes are detected.

## Running the FastAPI Application

* Run the **app.py** file as a Python script using the command: `python app.py`
* This will launch the Uvicorn server in debug mode.

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

### Type Hints for Variables

* Use type hints for global variables, function parameters, and variables inside function definitions.
* Example: `x: int = 3`

### Running MyPy

* Save the code to be checked in a file (e.g., `typechk.py`).
* Run MyPy with `mypy typechk.py` to detect type errors.

### Common Type Hints

* Use the following types as type hints:
  + `int`
  + `float`
  + `str`
  + `bool`
  + `list`
  + `dict`
  + `tuple`
  + `set`
  + `None`

## Type Hints in Python

### Basic Types

* `int`: integer
* `float`: floating point number
* `str`: string
* `bool`: boolean
* `list`: list (e.g. `List[str]`)
* `tuple`: tuple (e.g. `Tuple[str, int, float]`)
* `dict`: dictionary (e.g. `Dict[str, int]`)

### Union and Optional Types

* `Union`: represents a union of types (e.g. `Union[int, float]`)
* `Optional`: represents a value that may or may not be present (e.g. `Optional[str]`)

### Example Usage

```python
from typing import List, Tuple, Dict

cities: List[str] = ['Mumbai', 'Delhi', 'Chennai']
employee: Tuple[str, int, float] = ('Ravi', 25, 35000)
marklist: Dict[str, int] = {'Ravi': 61, 'Anil': 72}
```

## Mypy Error Messages

* `Argument 2 to "division" has incompatible type "float"; expected "int"`: error message indicating that a float is being passed to a function that expects an integer.
* `Found 2 errors in 1 file (checked 1 source file)`: summary of errors found by mypy.

## IDE Support

* FastAPI supports type hints and can be used with IDEs that support type checking, such as PyCharm.
* IDEs can provide features like code completion and error highlighting based on type hints.

## Type Hinting in Python

### Overview

* Type hinting is a feature in Python that provides dynamic autocomplete features in IDEs like PyCharm and VS Code.
* It helps the IDE understand the type of variables, making it easier to provide suggestions.

### Using Type Hints in Functions

* Include type hints in function definitions to provide autocomplete suggestions.
* Use the `str` class as a type hint for string variables.
* Use the `capitalize()` method to ensure the first letter of a string is in upper case.

### Example Code

```python
def sayhello(name: str) -> str:
    return "Hello " + name.capitalize()
```

### Using Type Hints with User-Defined Classes

* Define a class with type hints for arguments to the `__init__()` constructor.
* Use the class name as a type hint in function declarations.
* The IDE will provide autocomplete support for instance attributes.

### Example Code

```python
class Rectangle:
    def __init__(self, w: int, h: int) -> None:
        self.width = w
        self.height = h

def area(r: Rectangle) -> int:
    return r.width * r.height
```

## FastAPI

### What is FastAPI?

* FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints.

### FastAPI and Type Hints

* FastAPI makes extensive use of type hints for path parameters, query parameters, headers, bodies, dependencies, and more
* Type hints are used for validating data from incoming requests
* OpenAPI document generation also uses type hints

## REST Architecture

### What is REST?

* REST (RElational State Transfer) is a software architectural style
* Defines how the architecture of a web application should behave
* Resource-based architecture where everything is a resource

### REST Constraints

* Uniform interface
* Statelessness
* Client-server
* Cacheability
* Layered system
* Code on demand

### Advantages of REST

* Scalability
* Simplicity
* Modifiability
* Reliability
* Portability
* Visibility

### HTTP Verbs in REST

* POST: CREATE
* GET: READ
* PUT: UPDATE
* DELETE: DELETE

## Modern Web Frameworks

### Routes and Endpoints

* Use routes or endpoints as part of URL instead of file-based URLs
* Helps users remember application URLs more effectively

## FastAPI

### Path Parameters

* A path or route is the part of the URL trailing after the first '/'
* Example: `/hello/TutorialsPoint` in `http://localhost:8000/hello/TutorialsPoint`

### Path Operation Decorator

* Given as a parameter to the operation decorator
* Operation refers to the HTTP verb used by the browser to send data
* Examples: `@app.get("/")`, `@app.put("/")`

### HTTP Verbs

* GET: sends data in unencrypted form to the server (most common method)
* HEAD: same as GET, but without the response body

## Example Code

```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```

[CONTINUES INTO NEXT SECTION: Path Operation Function]