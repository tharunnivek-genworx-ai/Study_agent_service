# Chunk 3 | pages 21–30

## # 8. FastAPI – Path Parameters

### Overview

Path parameters are used to accept variable parameters in a URL. They can be used to pass dynamic values to a function.

### Syntax

Path parameters are defined using curly brackets `{}` in the URL path. For example:
```python
@app.get("/hello/{name}")
```
The variable parameter `name` can be accessed in the function using the `name` parameter.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```
In this example, the `hello` function takes a `name` parameter, which is passed from the URL path.

### Multiple Path Parameters

A route can have multiple path parameters separated by the `/` symbol. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name, age):
    return {"name": name, "age": age}
```
### Type Hints

Path parameters can have type hints to specify the expected data type. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is expected to be a string and the `age` parameter is expected to be an integer.

### Error Handling

If the type hints are not met, FastAPI will return an error message. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
If the URL is `http://localhost:8000/hello/20/Ravi`, FastAPI will return an error message:
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
### Swagger UI

Path parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:
```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In the Swagger UI, the `name` parameter is shown as a string and the `age` parameter is shown as an integer.

[FIGURE: fastapi_swagger_ui_typed_path_parameters]

## # 9. FastAPI – Query Parameters

### Overview

Query parameters are used to pass data to a function using the URL query string. They can be used to pass dynamic values to a function.

### Syntax

Query parameters are defined using the `?` symbol in the URL query string. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
The query string can be accessed in the function using the `name` and `age` parameters.

### Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `hello` function takes `name` and `age` parameters, which are passed from the URL query string.

### Type Hints

Query parameters can have type hints to specify the expected data type. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is expected to be a string and the `age` parameter is expected to be an integer.

### Swagger UI

Query parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:
```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In the Swagger UI, the `name` parameter is shown as a string and the `age` parameter is shown as an integer.

[FIGURE: fastapi_swagger_ui_query_parameter_response]

### Mixed Parameters

A route can have both path and query parameters. For example:
```python
@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```
In this example, the `name` parameter is a path parameter and the `age` parameter is a query parameter.

[FIGURE: fastapi_swagger_ui_mixed_parameters]

### Carryover Context

The previous chunk discussed path operations and how to define them using the `@app.get()` decorator. It also discussed how to use path parameters and how to define them using curly brackets `{}` in the URL path.

### Continues into Next Section

The next section will discuss how to use FastAPI to handle HTTP requests and responses. It will cover topics such as request and response objects, HTTP methods, and status codes.