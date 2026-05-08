from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine
from .dependencies import CurrentUser
from .models import Base
from .routers import agents, auth, licenses, obligations, tasks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Logistics License Verification API",
    description=(
        "Upload and verify regulatory licenses for shippers, carriers, and recipients. "
        "Supports internal and outsourced third-party verification agents with full audit trails."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(licenses.router)
app.include_router(agents.router)
app.include_router(obligations.router)
app.include_router(tasks.router)


# Wire /auth/me properly with the real CurrentUser dependency
@app.get("/auth/me", tags=["auth"])
def me(current_user: CurrentUser):  # type: ignore[return]
    from .schemas import UserOut
    return UserOut.model_validate(current_user)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok"}
