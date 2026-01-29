"""Domain models for the data service."""


class BaseService:
    """Abstract base for all services."""

    def connect(self, host: str) -> None:
        self.host = host

    def disconnect(self) -> None:
        self.host = None


class DataService(BaseService):
    """Service for querying and processing data."""

    cache_enabled: bool = True

    def get_data(self, query: str) -> list:
        self.connect("db.local")
        result = [{"id": 1, "value": query}]
        return result

    def process(self, data: list) -> dict:
        return {"count": len(data), "items": data}


def main():
    svc = DataService()
    raw = svc.get_data(query="SELECT * FROM users")
    out = svc.process(data=raw)
    svc.disconnect()
    return out
