from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str


class DatabaseHealthStatus(BaseModel):
    status: str
    database: str
