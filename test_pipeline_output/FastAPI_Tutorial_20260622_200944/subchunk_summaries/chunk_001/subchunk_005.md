# Sub-chunk 5 | pages 1–10

## FastAPI and Uvicorn

### FastAPI Overview

* FastAPI is a Python web framework
* Unlike Flask, it doesn't contain a built-in development server
* Requires **Uvicorn** for development and production

### Uvicorn

* Implements **ASGI** (Asynchronous Server Gateway Interface) standards
* Lightning-fast and suitable for **asyncio** applications
* Replaces **WSGI** (Web Server Gateway Interface) compliant web servers
* Supports **HTTP/2** and **WebSockets**

### Uvicorn Installation

* Install with minimal dependencies: `pip3 install uvicorn`
* Standard installation installs **cython** based dependencies and additional libraries
* Supports **WebSockets** and **PyYAML** with standard installation

### Running Uvicorn

* Launch application with: `uvicorn main:app -reload`
* **--reload** option enables debug mode and auto-refreshes display on client browser
* Available command-line options:
	+ `--host TEXT`: bind socket to this host (default: 127.0.0.1)
	+ `--port INTEGER`: bind socket to this port (default: 8000)
	+ `--uds TEXT`: bind to a UNIX domain socket
	+ `--fd INTEGER`: bind to socket from this file descriptor
	+ `--reload`: enable auto-reload

### Code Examples

```bash
pip3 install uvicorn(standard)
```

```bash
uvicorn main:app -reload
```

[CONTINUES: FastAPI]