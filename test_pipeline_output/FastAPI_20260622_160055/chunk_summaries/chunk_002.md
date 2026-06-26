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