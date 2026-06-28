from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """
    모든 Provider(Slack, GitHub, Claude 등)의 공통 인터페이스
    """

    @abstractmethod
    def connect(self):
        """외부 서비스 연결"""
        pass

    @abstractmethod
    def fetch(self):
        """데이터 수집"""
        pass

    @abstractmethod
    def save(self, data):
        """HermesVault 저장"""
        pass

    def run(self):
        """
        공통 실행 순서
        """
        self.connect()
        data = self.fetch()

        if data:
            self.save(data)
            print(f"[SUCCESS] {self.__class__.__name__} completed.")
        else:
            print(f"[INFO] No data from {self.__class__.__name__}.")
