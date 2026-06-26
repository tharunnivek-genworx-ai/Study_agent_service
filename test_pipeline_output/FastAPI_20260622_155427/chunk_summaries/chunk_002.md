# Chunk 2 | pages 11–20

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