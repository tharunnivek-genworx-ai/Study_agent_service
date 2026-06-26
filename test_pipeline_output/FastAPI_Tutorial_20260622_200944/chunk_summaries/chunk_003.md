# Chunk 3 | pages 21–30

## FastAPI Path and Query Parameters

### HTTP Methods

* `POST`: sends HTML form data to the server, not cached by the server
* `PUT`: replaces all current representations of the target resource
* `DELETE`: removes all current representations of the target resource

### Asynchronous Functions

* Use `async` keyword to define asynchronous functions
* Can define path operation functions without `async` prefix

### Path Parameters

* Use Python's string formatting notation to accept variable parameters
* Define variable parameters in the URL path and pass to function parameters
* Example: `/hello/{name}`

### Defining Path Parameters

* Use curly brackets `{}` to define path parameters in a route.
* Example: `/hello/{name}/{age}`

### Path Parameter Types

* Use Python type hints to define parameter types.
* Example: `name:str`, `age:int`

### Path Parameter Validation

* FastAPI validates path parameters based on their types.
* If types don't match, returns an HTTP error message.

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}/{age}")
async def hello(name:str, age:int):
    return {"name": name, "age": age}
```

### Query String Basics

* A query string is a list of key-value pairs concatenated by the ampersand (&) symbol.
* The query string is appended to the URL by a question mark (?).
* Example: `http://localhost/cgi-bin/hello.py?name=Ravi&age=20`

### FastAPI Query Parameter Handling

* FastAPI automatically treats non-path parameters as query strings.
* Query parameters are parsed into parameters and values.
* Example:
```python
@app.get("/hello")
async def hello(name:str, age:int):
    return {"name": name, "age": age}
```

### Defining Query Parameters

* Use Python's type hints to define the parameters of a function.
* For query parameters, use `str` for string values and `int` for integer values.

### Mixed Path and Query Parameters

* The `/hello/{name}` endpoint has both path and query parameters.
* The `name` parameter is a path parameter.
* The `age` parameter is a query parameter.

### Swagger UI Documentation

* Open the Swagger UI (OpenAPI) documentation by entering `http://localhost:8000/docs` as the URL.
* The parameter `name` is a path parameter.
* The parameter `age` is a query parameter.

### Swagger UI Features

* Click the **Try it out** button to enter query parameter values.
* Press the **Execute** button to see the Curl command, request URL, and HTTP response details.

[FIGURE: fastapi_swagger_ui_path_parameter_input]
[FIGURE: fastapi_swagger_ui_query_parameter_input]
[FIGURE: fastapi_swagger_ui_query_parameter_response]
[FIGURE: fastapi_swagger_ui_mixed_parameters]

### Key Takeaways

* Use query parameters to pass data to an API endpoint.
* Define query parameters using Python's type hints.
* Use Swagger UI to document and test API endpoints.
* Understand the difference between path and query parameters.

[CONTINUES INTO NEXT SECTION: FastAPI]