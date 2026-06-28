from base import BaseProvider


class TestProvider(BaseProvider):

    def connect(self):
        print("Connect OK")

    def fetch(self):
        print("Fetch OK")
        return {"message": "Hello Hermes"}

    def save(self, data):
        print(f"Save OK : {data}")


if __name__ == "__main__":
    provider = TestProvider()
    provider.run()
