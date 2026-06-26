# Chunk 3 | pages 21–30

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