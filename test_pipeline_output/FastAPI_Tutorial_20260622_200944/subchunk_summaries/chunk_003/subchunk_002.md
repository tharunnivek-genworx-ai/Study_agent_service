# Sub-chunk 2 | pages 21–30

## FastAPI Path Parameters

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

### Path Parameter Example

* URL: `http://localhost:8000/hello/Ravi/20`
* Response: `{"name": "Ravi", "age": "20"}`

### Type Error Example

* URL: `http://localhost:8000/hello/20/Ravi`
* Response: `{"detail": [...]}`
* Error message: `value is not a valid integer`

### Returning Data

* Use the `return` statement to return data from a route.
* Example: `return {"name": name, "age": age}`