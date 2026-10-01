# HTTP API

This is the contract between the backend and any client. It must not assume an
Android client: anything a client needs is described here, in plain JSON over HTTP.

The loop endpoints are designed in Stage 3. Until then, only the health check exists.

## `GET /health`

Returns `200` when the service is running.

```json
{ "status": "ok", "version": "0.1.0" }
```
