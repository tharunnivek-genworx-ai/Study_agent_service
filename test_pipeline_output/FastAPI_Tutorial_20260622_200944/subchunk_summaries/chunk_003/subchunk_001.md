# Sub-chunk 1 | pages 21–30

## FastAPI Path Parameters

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

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/hello/{name}")
async def hello(name):
    return {"name": name}
```

### Path Parameter Usage

* Visit `http://localhost:8000/hello/Tutorialspoint` to see JSON response
* Change path parameter to `http://localhost:8000/hello/Python` to see different response

### OpenAPI Docs

* Visit `http://localhost:8000/docs` to see OpenAPI documentation
* Click "Try it out" and enter value for path parameter to execute request

### Swagger UI

[FIGURE: fastapi_swagger_ui_path_parameter_input]
* Enter path parameter value in request parameter entry field
* Click Execute button to send request