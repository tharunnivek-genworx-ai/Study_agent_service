# Sub-chunk 4 | pages 21–30

## # 9. FastAPI – Query Parameters

### Overview

* FastAPI is a Python web framework for building APIs.
* Query parameters are used to pass data to an API endpoint.

### Defining Query Parameters

* Use Python's type hints to define the parameters of a function.
* For query parameters, use `str` for string values and `int` for integer values.

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()
```

### Defining a GET Endpoint with Query Parameters

```python
@app.get("/hello/{name}")
async def hello(name:str, age:int):
    return {"name": name, "age": age}
```

### Swagger UI Documentation

* Open the Swagger UI (OpenAPI) documentation by entering `http://localhost:8000/docs` as the URL.
* The parameter `name` is a path parameter.
* The parameter `age` is a query parameter.

### Mixed Path and Query Parameters

* The `/hello/{name}` endpoint has both path and query parameters.
* The `name` parameter is a path parameter.
* The `age` parameter is a query parameter.

### Swagger UI Screenshots

[FIGURE: fastapi_swagger_ui_query_parameter_input]
[FIGURE: fastapi_swagger_ui_query_parameter_response]
[FIGURE: fastapi_swagger_ui_mixed_parameters]

### Key Takeaways

* Use query parameters to pass data to an API endpoint.
* Define query parameters using Python's type hints.
* Use Swagger UI to document and test API endpoints.
* Understand the difference between path and query parameters.