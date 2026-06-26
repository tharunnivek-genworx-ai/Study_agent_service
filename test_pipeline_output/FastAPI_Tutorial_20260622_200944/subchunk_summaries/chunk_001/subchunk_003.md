# Sub-chunk 3 | pages 1–10

## # 3. FastAPI – OpenAPI

### Creating a FastAPI App

* Declare the application object of FastAPI class: `app = FastAPI()`
* `app` object is the main point of interaction between the application and the client browser
* Uvicorn server uses this object to listen to client requests

### Creating Path Operations

* Path is a URL that invokes a mapped URL to an HTTP method and associated function
* Bind a view function to a URL and HTTP method using decorators (e.g., `@app.get("/")`)
* Example: `@app.get("/")` maps to the `root()` function

### View Functions

* Return JSON response (or other types: `dict`, `list`, `str`, `int`, etc.)
* Can return Pydantic models
* Example: `async def root(): return {"message": "Hello World"}`

### Saving the Code

* Save the code as `main.py`

### OpenAPI Documentation

* FastAPI generates OpenAPI documentation automatically
* Access documentation at `/docs` (e.g., `http://127.0.0.1:8000/docs`)
* Swagger UI layout with endpoint summary and successful response status

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

[CONTINUES: FastAPI]