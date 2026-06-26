# Chunk 3 | pages 21–30

## 8. FastAPI – Path Parameters

### Overview

Path parameters are used to accept variable parameters in a URL. They can be used to accept different values in each client request.

### Syntax

Path parameters are defined using curly brackets `{}` in the URL path. For example:

```python
@app.get("/hello/{name}")
```

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, the `name` parameter is a path parameter. When the URL `http://localhost:8000/hello/Tutorialspoint` is accessed, the `name` variable will be assigned the value `Tutorialspoint`.

### Multiple Path Parameters

A route can have multiple parameters separated by the `/` symbol.

```python
@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```

### Typed Path Parameters

Path parameters can be typed using Python's type hints.

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `name` parameter is a string and the `age` parameter is an integer. If the URL `http://localhost:8000/hello/20/Ravi` is accessed, an HTTP error message will be returned because the `age` parameter is not an integer.

### Path Parameters in Swagger UI

Path parameters are displayed in the Swagger UI (OpenAPI) documentation.

[FIGURE: fastapi_swagger_ui_path_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with a parameter field filled with TutorialsPoint and an Execute button.

### Path Parameters with Multiple Types

A path parameter can have multiple types.

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Path Parameters with Default Values

A path parameter can have a default value.

```python
@app.get("/hello/{name}")
async def hello(name: str = "World"):
    return {"name": name}
```

### Path Parameters with Regular Expressions

A path parameter can be validated using regular expressions.

```python
from fastapi import FastAPI, Path

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str = Path(..., title="The Name", description="The name to greet", regex="^[a-zA-Z]+$")):
    return {"name": name}
```

### Path Parameters with Validation

A path parameter can be validated using Python's built-in validation functions.

```python
from fastapi import FastAPI, Path

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name: str = Path(..., title="The Name", description="The name to greet", min_length=2, max_length=10)):
    return {"name": name}
```

## 9. FastAPI – Query Parameters

### Overview

Query parameters are used to pass data to the server as a query string in the URL.

### Syntax

Query parameters are defined using the `?` symbol in the URL.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the `name` and `age` parameters are query parameters. When the URL `http://localhost:8000/hello?name=Ravi&age=20` is accessed, the `name` variable will be assigned the value `Ravi` and the `age` variable will be assigned the value `20`.

### Typed Query Parameters

Query parameters can be typed using Python's type hints.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Query Parameters in Swagger UI

Query parameters are displayed in the Swagger UI (OpenAPI) documentation.

[FIGURE: fastapi_swagger_ui_query_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello endpoint with query parameters.

### Query Parameters with Multiple Types

A query parameter can have multiple types.

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

### Query Parameters with Default Values

A query parameter can have a default value.

```python
@app.get("/hello")
async def hello(name: str = "World", age: int = 20):
    return {"name": name, "age": age}
```

### Query Parameters with Regular Expressions

A query parameter can be validated using regular expressions.

```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/hello")
async def hello(name: str = Query(..., title="The Name", description="The name to greet", regex="^[a-zA-Z]+$"), age: int = Query(..., title="The Age", description="The age to greet", regex="^[0-9]+$")):
    return {"name": name, "age": age}
```

### Query Parameters with Validation

A query parameter can be validated using Python's built-in validation functions.

```python
from fastapi import FastAPI, Query

app = FastAPI()

@app.get("/hello")
async def hello(name: str = Query(..., title="The Name", description="The name to greet", min_length=2, max_length=10), age: int = Query(..., title="The Age", description="The age to greet", ge=0, le=100)):
    return {"name": name, "age": age}
```