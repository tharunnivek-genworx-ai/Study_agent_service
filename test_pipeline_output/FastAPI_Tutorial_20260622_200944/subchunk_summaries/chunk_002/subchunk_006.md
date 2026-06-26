# Sub-chunk 6 | pages 11–20

## Modern Web Frameworks
### Routes and Endpoints
* Use routes or endpoints as part of URL instead of file-based URLs
* Helps users remember application URLs more effectively

## FastAPI
### Path Parameters
* A path or route is the part of the URL trailing after the first '/'
* Example: `/hello/TutorialsPoint` in `http://localhost:8000/hello/TutorialsPoint`

### Path Operation Decorator
* Given as a parameter to the operation decorator
* Operation refers to the HTTP verb used by the browser to send data
* Examples: `@app.get("/")`, `@app.put("/")`

### HTTP Verbs
* GET: sends data in unencrypted form to the server (most common method)
* HEAD: same as GET, but without the response body

## Example Code
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
async def index():
    return {"message": "Hello World"}
```
[CONTINUES: Path Operation Function]