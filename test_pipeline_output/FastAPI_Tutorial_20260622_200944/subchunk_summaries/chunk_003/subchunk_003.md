# Sub-chunk 3 | pages 21–30

## # 8. FastAPI – Path Parameters

### Path Parameter Validation

* Path parameters must be validated as integers using type annotations (e.g., `int`).
* Failure to validate will result in a `type_error.integer` error.
* Swagger UI will reflect the correct type annotations for path parameters.

## # 9. FastAPI – Query Parameters

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

### Example Usage

* Start the Uvicorn server and access the URL: `http://localhost:8000/hello?name=Ravi&age=20`
* Verify that FastAPI has detected query parameters in the Swagger UI.

### Swagger UI Features

* Click the **Try it out** button to enter query parameter values.
* Press the **Execute** button to see the Curl command, request URL, and HTTP response details.

[CONTINUES: FastAPI]