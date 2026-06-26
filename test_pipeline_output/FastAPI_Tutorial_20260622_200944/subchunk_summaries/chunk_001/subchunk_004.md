# Sub-chunk 4 | pages 1–10

## # FastAPI Basics

* **Try it out**: Click the **'try it out'** button and then **'Execute'** button in FastAPI Swagger UI.
* **Swagger UI**: Displays a successful API response with Curl command, Request URL, and JSON response body.
* **OpenAPI**: FastAPI generates a schema using OpenAPI specifications.
* **API schema**: Defined by the OpenAPI standard, determines how data is sent.

## # OpenAPI and JSON Schema

* **OpenAPI JSON**: Visit `http://127.0.0.1:8000/openapi.json` to view a neatly formatted JSON response.
* **JSON response**:
```json
{
  "openapi": "3.0.2",
  "info": {
    "title": "FastAPI",
    "version": "0.1.0"
  },
  "paths": {
    "/": {
      "get": {
        "summary": "Index",
        "operationId": "index__get",
        "responses": {
          "200": {
            "description": "Successful Response",
            "content": {
              "application/json": {
                "schema": {}
              }
            }
          }
        }
      }
    }
  }
}
```
* **Redoc**: Another automatic documentation method provided by FastAPI.

## # Redoc Documentation

* **Redoc URL**: Enter `http://localhost:8000/redoc` as URL in the browser’s address bar.
* **Redoc interface**: Displays the FastAPI ReDoc interface with API documentation.
* **API documentation**: Includes a download link for the OpenAPI specification and API request/response details.