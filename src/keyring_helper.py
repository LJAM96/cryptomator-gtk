import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

# Secret Schema
# We use a simple schema with the vault path as a unique attribute
SCHEMA = Secret.Schema.new("io.github.ljam96.cryptomatorgtk",
    Secret.SchemaFlags.NONE,
    {
        "vault_path": Secret.SchemaAttributeType.STRING,
    }
)

def save_password(vault_path, password):
    attributes = {"vault_path": vault_path}
    Secret.password_store(SCHEMA, attributes, Secret.COLLECTION_DEFAULT, f"Cryptomator Vault: {vault_path}", password, None, None)

def load_password(vault_path):
    attributes = {"vault_path": vault_path}
    return Secret.password_lookup(SCHEMA, attributes, None)

def delete_password(vault_path):
    attributes = {"vault_path": vault_path}
    Secret.password_clear(SCHEMA, attributes, None, None)
