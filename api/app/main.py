from fastapi import FastAPI

from app.routers import author, chat, dashboard, graph, metrics

app = FastAPI(title="DBLP Explorer API")

app.include_router(dashboard.router)
app.include_router(graph.router)
app.include_router(metrics.router)
app.include_router(chat.router)
app.include_router(author.router)


@app.get("/health")
def health():
    return {"status": "ok"}
