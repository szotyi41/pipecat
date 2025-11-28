# Pipecat Docker Setup

## Gyors indítás

### 1. Docker image építése és indítása

```bash
docker-compose up --build
```

### 2. Csak indítás (ha már built)

```bash
docker-compose up
```

### 3. Háttérben futtatás

```bash
docker-compose up -d
```

### 4. Leállítás

```bash
docker-compose down
```

## Hozzáférés

A szolgáltatás elérhető lesz:
- **Playground URL**: http://localhost:7860/client/

## Környezeti változók

A `docker-compose.yml` fájlban a következők vannak beállítva:
- `GOOGLE_TEST_CREDENTIALS`: Google Cloud credentials fájl elérési útja

## Credentials

Győződj meg róla, hogy a `google-credentials.json` fájl a projekt gyökerében van!

## Dockerfile részletek

A Docker image:
- **Base image**: Python 3.11-slim
- **Multi-stage build**: Optimalizált méret
- **Non-root user**: Biztonság
- **Port**: 7860 (WebRTC)

## Egyéni indítás (Docker parancsokkal)

### Build

```bash
docker build -t pipecat-stt:latest .
```

### Run

```bash
docker run -p 7860:7860 \
  -v $(pwd)/google-credentials.json:/app/google-credentials.json:ro \
  -v $(pwd)/.env:/app/.env:ro \
  -e GOOGLE_TEST_CREDENTIALS=/app/google-credentials.json \
  pipecat-stt:latest
```

## Troubleshooting

### Logok megtekintése

```bash
docker-compose logs -f
```

### Container shell

```bash
docker-compose exec pipecat-stt bash
```

### Image újraépítése

```bash
docker-compose build --no-cache
```
