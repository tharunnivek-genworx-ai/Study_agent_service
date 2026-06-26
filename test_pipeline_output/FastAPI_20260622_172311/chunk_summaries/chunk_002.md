# Chunk 2 | pages 11–20

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