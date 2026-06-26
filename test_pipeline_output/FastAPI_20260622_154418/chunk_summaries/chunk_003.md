# Chunk 3 | pages 21–30

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