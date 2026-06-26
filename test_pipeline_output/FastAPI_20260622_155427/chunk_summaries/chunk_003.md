# Chunk 3 | pages 21–30

## # 8. FastAPI – Path Parameters

### Overview

FastAPI supports path parameters, which are used to capture values from the URL path. These values can be used in the path operation function to return a response.

### Syntax

Path parameters are defined using curly brackets `{}` in the path. For example:

```python
@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

In this example, `{name}` is a path parameter that captures the value from the URL path.

### Types

Path parameters can have types defined using Python's type hints. For example:

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` is a string and `age` is an integer.

### Usage

Path parameters can be used to capture values from the URL path. For example:

```python
@app.get("/hello/Ravi/20")
async def hello(name, age):
    return {"name": name, "age": age}
```

In this example, the URL path `/hello/Ravi/20` captures the values `Ravi` and `20` for the `name` and `age` path parameters, respectively.

### Swagger UI

Path parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_path_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with a parameter field filled with TutorialsPoint and an Execute button.

### Error Handling

If the types of the path parameters do not match the values in the URL path, an error is returned. For example:

```python
@app.get("/hello/{name}/{age}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

If the URL path is `/hello/20/Ravi`, an error is returned because `age` is an integer and cannot accept a string value.

## # 9. FastAPI – Query Parameters

### Overview

FastAPI supports query parameters, which are used to capture values from the query string. These values can be used in the path operation function to return a response.

### Syntax

Query parameters are defined using the `async def` syntax in the path operation function. For example:

```python
@app.get("/hello")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` and `age` are query parameters that capture the values from the query string.

### Usage

Query parameters can be used to capture values from the query string. For example:

```python
@app.get("/hello?name=Ravi&age=20")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, the query string `?name=Ravi&age=20` captures the values `Ravi` and `20` for the `name` and `age` query parameters, respectively.

### Swagger UI

Query parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_query_parameter_input]
A screenshot of FastAPI Swagger UI showing the /hello endpoint with query parameters name and age.

### Mixed Parameters

FastAPI supports mixed parameters, which are a combination of path and query parameters. For example:

```python
@app.get("/hello/{name}")
async def hello(name: str, age: int):
    return {"name": name, "age": age}
```

In this example, `name` is a path parameter and `age` is a query parameter.

### Swagger UI

Mixed parameters are reflected in the Swagger UI (OpenAPI) documentation. For example:

[FIGURE: fastapi_swagger_ui_mixed_parameters]
A screenshot of FastAPI Swagger UI showing the /hello/{name} endpoint with both path and query parameters.

[CONTINUES INTO NEXT SECTION: Query Parameters with Default Values]