from dataclasses import dataclass
from enum import Enum

class VaultStatus(Enum):
    LOCKED = 0
    UNLOCKED = 1
    MISSING = 2

@dataclass
class Vault:
    # Dataclass is mutable, so we can just update .name
    # Confirming structure for clarity
    name: str
    path: str
    status: VaultStatus = VaultStatus.LOCKED
    mount_path: str = None

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=data["name"],
            path=data["path"]
        )
