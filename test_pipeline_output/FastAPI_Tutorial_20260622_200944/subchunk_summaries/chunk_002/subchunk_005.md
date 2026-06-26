# Sub-chunk 5 | pages 11–20

## Type Hints in Python

### What are Type Hints?

* Type hints are a feature in Python that allows developers to specify the expected data type of a variable, function parameter, or return value.

### Example Code
```python
class rectangle:
    def __init__(self, w:int, h:int) ->None:
        self.width=w
        self.height=h

def area(r:rectangle)->int:
    return r.width*r.height

r1=rectangle(10,20)
print ("area = ", area(r1))
```

### Benefits of Type Hints

* Enable better code completion in IDEs like VS Code and PyCharm
* Improve code readability and maintainability
* Allow for better error messages and debugging

## FastAPI

### What is FastAPI?

* FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.7+ based on standard Python type hints.

### FastAPI and Type Hints

* FastAPI makes extensive use of type hints for path parameters, query parameters, headers, bodies, dependencies, and more
* Type hints are used for validating data from incoming requests
* OpenAPI document generation also uses type hints

## REST Architecture

### What is REST?

* REST (RElational State Transfer) is a software architectural style
* Defines how the architecture of a web application should behave
* Resource-based architecture where everything is a resource

### REST Constraints

* Uniform interface
* Statelessness
* Client-server
* Cacheability
* Layered system
* Code on demand

### Advantages of REST

* Scalability
* Simplicity
* Modifiability
* Reliability
* Portability
* Visibility

### HTTP Verbs in REST

* POST: CREATE
* GET: READ
* PUT: UPDATE
* DELETE: DELETE