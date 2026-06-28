from fastapi import FastAPI

app = FastAPI(
    title="TradingBrain",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "application": "TradingBrain",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }