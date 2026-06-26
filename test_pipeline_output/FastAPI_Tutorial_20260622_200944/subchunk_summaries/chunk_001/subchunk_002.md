# Sub-chunk 2 | pages 1–10

## FastAPI Basics

### Creating the FastAPI App

* Declare the application object of FastAPI class: `app = FastAPI()`
* This object is the main point of interaction between the application and the client browser
* The uvicorn server uses this object to listen to client requests

### Path Operations

* A path operation is a URL that invokes a mapped URL to an HTTP method and executes an associated function
* Bind a view function to a URL and the corresponding HTTP method using decorators (e.g. `@app.get("/")`)
* Example: `@app.get("/")` maps to the `/` path with the `GET` operation

### View Functions

* A view function is a function that returns a response to a client request
* Can return:
	+ `dict`
	+ `list`
	+ `str`
	+ `int`
	+ Pydantic models
* Example: `async def root(): return {"message": "Hello World"}`

### Example Code

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World"}
```

### Saving the Code

* Save the code as `main.py`

### [FIGURE: fastapi_hello_world_browser_response]

Components: Web browser, JSON response, FastAPI application, Uvicorn server
Connections: Client request, FastAPI app object, Uvicorn server
Purpose: Illustrates the result of running the FastAPI application with Uvicorn, displaying a JSON response in a web browser.