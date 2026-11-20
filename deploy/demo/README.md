# Veteran Access Bridge Demo Runtime

This container runs the M3-M6 **synthetic** demonstration application.

## Run locally

```bash
docker build -f deploy/demo/Dockerfile -t veteran-access-bridge-demo .
docker run --rm -p 8080:8080 veteran-access-bridge-demo
```

Open http://localhost:8080.

## Security posture

- Synthetic data only.
- Production VA interfaces are not connected.
- Production writes are disabled.
- `X-Demo-Role`, `X-Demo-Actor`, and `X-Demo-Case` are demo-only identity
  headers. They demonstrate server-side role and case-scope enforcement; they
  are not production authentication.
- A production deployment requires approved identity/session integration,
  secrets management, TLS, persistent transactional storage, audit retention,
  and VA security review.
