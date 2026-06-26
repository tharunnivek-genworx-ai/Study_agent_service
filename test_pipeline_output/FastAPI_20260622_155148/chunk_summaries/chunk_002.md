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