# Chunk 2 | pages 11–20

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