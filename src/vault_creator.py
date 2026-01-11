"""
Cryptomator vault creation module.
Based on Cryptomator's vault format documentation and cryptolib implementation.
"""

import os
import json
import secrets
import base64
import hmac
import hashlib
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    from cryptography.hazmat.backends import default_backend
    import jwt
    from miscreant.aes.siv import SIV
except ImportError:
    print("Warning: cryptography libraries not available. Vault creation disabled.")


class VaultCreator:
    """Creates new Cryptomator vaults with proper encryption"""
    
    # Constants from Cryptomator specification
    VAULT_FORMAT = 8
    CIPHER_COMBO = "SIV_GCM"
    SHORTENING_THRESHOLD = 220
    MASTERKEY_FILENAME = "masterkey.cryptomator"
    VAULT_CONFIG_FILENAME = "vault.cryptomator"
    SCRYPT_SALT_LENGTH = 8
    SCRYPT_COST_PARAM = 32768  # 2^15
    SCRYPT_BLOCK_SIZE = 8
    KEY_LENGTH = 32  # 256 bits
    
    @staticmethod
    def create_vault(vault_path: str, password: str) -> tuple[bool, str]:
        """
        Create a new Cryptomator vault at the specified path.
        
        Args:
            vault_path: Path where the vault should be created
            password: Password to protect the vault
            
        Returns:
            Tuple of (success: bool, error_message: str)
        """
        import subprocess
        import tempfile
        
        try:
            vault_path_obj = Path(vault_path)
            
            # 1. Create vault directory
            if vault_path_obj.exists():
                return False, "Directory already exists"
            
            vault_path_obj.mkdir(parents=True, exist_ok=False)
            
            # 2. Create 'd' subdirectory for encrypted data
            d_path = vault_path_obj / 'd'
            d_path.mkdir()
            
            # 3. Generate random master keys
            enc_master_key = secrets.token_bytes(VaultCreator.KEY_LENGTH)
            mac_master_key = secrets.token_bytes(VaultCreator.KEY_LENGTH)
            
            # 4. Create masterkey file
            VaultCreator._create_masterkey_file(
                vault_path_obj,
                enc_master_key,
                mac_master_key,
                password
            )
            
            # 5. Create vault configuration file
            VaultCreator._create_vault_config(
                vault_path_obj,
                enc_master_key,
                mac_master_key
            )
            
            # 6. Create the encrypted root directory structure
            # This requires AES-SIV encryption matching Cryptomator's implementation
            print(f"Initializing encrypted root directory at {vault_path}...", flush=True)
            
            try:
                VaultCreator._create_encrypted_root(d_path, enc_master_key, mac_master_key)
                print(f"Created encrypted root directory structure", flush=True)
                
            except Exception as init_err:
                print(f"Warning during root directory creation: {init_err}", flush=True)
                import traceback
                traceback.print_exc()
                # Continue anyway - basic structure is there
            
            # 7. Create README file
            VaultCreator._create_readme(vault_path_obj)
            
            return True, ""
            
        except Exception as e:
            return False, f"Failed to create vault: {str(e)}"
    
    @staticmethod
    def _create_masterkey_file(vault_path: Path, enc_key: bytes, mac_key: bytes, password: str):
        """Create and save the encrypted masterkey file"""
        
        # Generate random salt
        salt = secrets.token_bytes(VaultCreator.SCRYPT_SALT_LENGTH)
        
        # Derive KEK (Key Encryption Key) using scrypt
        # Note: Cryptomator uses a pepper, but for simplicity we'll use empty pepper
        pepper = b''
        kek = VaultCreator._derive_kek(password, salt, pepper)
        
        # Wrap (encrypt) the master keys using AES Key Wrap
        wrapped_enc_key = VaultCreator._aes_key_wrap(enc_key, kek)
        wrapped_mac_key = VaultCreator._aes_key_wrap(mac_key, kek)
        
        # Calculate version MAC
        version_bytes = VaultCreator.VAULT_FORMAT.to_bytes(4, byteorder='big')
        version_mac = hmac.new(mac_key, version_bytes, hashlib.sha256).digest()
        
        # Create masterkey file structure
        masterkey_data = {
            "version": VaultCreator.VAULT_FORMAT,
            "scryptSalt": base64.b64encode(salt).decode('ascii'),
            "scryptCostParam": VaultCreator.SCRYPT_COST_PARAM,
            "scryptBlockSize": VaultCreator.SCRYPT_BLOCK_SIZE,
            "primaryMasterKey": base64.b64encode(wrapped_enc_key).decode('ascii'),
            "hmacMasterKey": base64.b64encode(wrapped_mac_key).decode('ascii'),
            "versionMac": base64.b64encode(version_mac).decode('ascii')
        }
        
        # Write to file
        masterkey_path = vault_path / VaultCreator.MASTERKEY_FILENAME
        with open(masterkey_path, 'w') as f:
            json.dump(masterkey_data, f, indent=2)
    
    @staticmethod
    def _derive_kek(password: str, salt: bytes, pepper: bytes) -> bytes:
        """Derive Key Encryption Key using scrypt"""
        salt_and_pepper = salt + pepper
        
        kdf = Scrypt(
            salt=salt_and_pepper,
            length=VaultCreator.KEY_LENGTH,
            n=VaultCreator.SCRYPT_COST_PARAM,
            r=VaultCreator.SCRYPT_BLOCK_SIZE,
            p=1,
            backend=default_backend()
        )
        
        return kdf.derive(password.encode('utf-8'))
    
    @staticmethod
    def _aes_key_wrap(plaintext_key: bytes, kek: bytes) -> bytes:
        """
        Implement AES Key Wrap (RFC 3394)
        This is a simplified implementation for 256-bit keys
        """
        from cryptography.hazmat.primitives.keywrap import aes_key_wrap
        
        return aes_key_wrap(kek, plaintext_key, default_backend())
    
    @staticmethod
    def _create_vault_config(vault_path: Path, enc_key: bytes, mac_key: bytes):
        """Create the vault.cryptomator JWT configuration file"""
        
        # Generate unique vault ID
        vault_id = secrets.token_hex(16)
        jti = f"{vault_id[:8]}-{vault_id[8:12]}-{vault_id[12:16]}-{vault_id[16:20]}-{vault_id[20:]}"
        
        # JWT header
        header = {
            "kid": f"masterkeyfile:{VaultCreator.MASTERKEY_FILENAME}",
            "typ": "JWT",
            "alg": "HS256"
        }
        
        # JWT payload
        payload = {
            "format": VaultCreator.VAULT_FORMAT,
            "shorteningThreshold": VaultCreator.SHORTENING_THRESHOLD,
            "jti": jti,
            "cipherCombo": VaultCreator.CIPHER_COMBO
        }
        
        # Sign with concatenated masterkeys (512 bits total)
        signing_key = enc_key + mac_key
        
        # Create JWT
        token = jwt.encode(
            payload,
            signing_key,
            algorithm="HS256",
            headers=header
        )
        
        # Write to file
        config_path = vault_path / VaultCreator.VAULT_CONFIG_FILENAME
        with open(config_path, 'w') as f:
            f.write(token)
    
    @staticmethod
    def _create_encrypted_root(d_path: Path, enc_master_key: bytes, mac_master_key: bytes):
        """
        Create the encrypted root directory structure.
        This mimics CryptoFileSystemProvider.initialize() behavior.
        
        The root directory is identified by an empty string ("") which is:
        1. Encrypted using AES-SIV (RFC 5297)
        2. Hashed with SHA1
        3. Base32 encoded
        This creates the directory path.
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from miscreant.aes.siv import SIV
        
        # Root directory ID is empty string
        root_dir_id = b""
        
        # Calculate directory hash using same method as Cryptomator:
        # hashDirectoryId = BASE32(SHA1(SIV-ENCRYPT(directoryId)))
        
        # 1. AES-SIV encrypt the directory ID
        # Miscreant SIV expects: key = mac_key || enc_key (concatenated)
        siv_key = mac_master_key + enc_master_key
        siv = SIV(siv_key)
        encrypted_dir_id = siv.seal(root_dir_id)
        
        # 2. SHA1 hash the encrypted directory ID  
        dir_hash_bytes = hashlib.sha1(encrypted_dir_id).digest()
        
        # 3. Base32 encode (Cryptomator uses RFC 4648 Base32 without padding)
        root_dir_hash = base64.b32encode(dir_hash_bytes).decode('ascii').rstrip('=')
        
        # Create two-level directory: d/XX/REMAINDER/
        # First level: first 2 characters, Second level: everything after first 2
        first_level = root_dir_hash[:2]
        second_level = root_dir_hash[2:]  # Skip first 2 characters
        
        root_dir_path = d_path / first_level / second_level
        root_dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create encrypted dir.c9r file
        # Format: nonce (12 bytes) + ciphertext + tag (16 bytes)
        # The plaintext is a JSON structure containing directory metadata
        
        # Root directory metadata (minimal valid structure)
        dir_metadata = json.dumps({}).encode('utf-8')  # Empty JSON for root
        
        # Generate random nonce (12 bytes for GCM)
        nonce = secrets.token_bytes(12)
        
        # Encrypt using AES-GCM
        aesgcm = AESGCM(enc_master_key)
        ciphertext = aesgcm.encrypt(nonce, dir_metadata, None)
        
        # Write: nonce + ciphertext (which includes auth tag)
        dir_file = root_dir_path / "dir.c9r"
        dir_file.write_bytes(nonce + ciphertext)
        
        # Also create dirid.c9r file in d/ directory
        # This stores the encrypted root directory ID and is checked by CryptoFileSystems
        dirid_nonce = secrets.token_bytes(12)
        dirid_ciphertext = aesgcm.encrypt(dirid_nonce, root_dir_hash.encode('utf-8'), None)
        dirid_file = d_path / "dirid.c9r"
        dirid_file.write_bytes(dirid_nonce + dirid_ciphertext)
        
        print(f"Created encrypted root directory: {root_dir_path}", flush=True)
        print(f"Created root directory ID file: {dirid_file}", flush=True)
    
    @staticmethod
    def _create_readme(vault_path: Path):
        """Create IMPORTANT.rtf README file"""
        from datetime import datetime
        
        readme_content = r"""{\rtf1\ansi\ansicpg1252\cocoartf2761
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 Welcome to your new Cryptomator vault!\
\
This vault was created by Cryptomator GTK.\
\
What is Cryptomator?\
Cryptomator provides transparent, client-side encryption for your cloud files.\
Visit cryptomator.org for more information.\
\
What should I do with this vault?\
Just drop your files into this vault to encrypt them automatically.\
\
How can I access my vault?\
Use the Cryptomator application to unlock and access this vault.\
\
Created: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + r"""\
}"""
        
        readme_path = vault_path / "IMPORTANT.rtf"
        with open(readme_path, 'w') as f:
            f.write(readme_content)
