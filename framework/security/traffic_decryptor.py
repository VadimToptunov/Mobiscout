"""
Traffic Decryptor - Decrypt HTTPS traffic using exported TLS keys

This module decrypts captured HTTPS traffic using TLS session keys
exported from the mobile app's Observe SDK.

SECURITY WARNING:
This tool can decrypt encrypted traffic! Use only for testing purposes.
"""

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TLSSessionKey:
    """TLS session key data"""
    session_id: str
    master_secret: bytes
    client_random: bytes
    server_random: bytes
    cipher: str
    protocol: str
    timestamp: int


@dataclass
class DeviceKeys:
    """Device encryption keys"""
    public_key: bytes
    private_key: bytes
    symmetric_key: bytes
    key_type: str
    key_size: int


class TrafficDecryptor:
    """
    Decrypt HTTPS traffic using exported TLS keys

    Usage:
        decryptor = TrafficDecryptor()
        decryptor.load_keys_from_device("session_123")

        # Decrypt network event
        decrypted = decryptor.decrypt_network_event(network_event)
    """

    def __init__(self):
        self.tls_keys: Dict[str, TLSSessionKey] = {}
        self.device_keys: Optional[DeviceKeys] = None
        self.crypto_keys_path: Optional[Path] = None

    def load_keys_from_device(self, session_id: str, device_path: str = None) -> bool:
        """
        Pull crypto keys from device and load them

        Args:
            session_id: Session ID to load keys for
            device_path: Custom device path (optional)

        Returns:
            True if keys loaded successfully
        """
        import subprocess

        # Default device path
        if not device_path:
            device_path = f"/sdcard/Android/data/com.findemo/files/observe/crypto/crypto_keys_{session_id}.json"

        # Pull from device using ADB
        local_path = Path(f"./crypto_keys_{session_id}.json")

        try:
            logger.info(f"Pulling crypto keys from device: {device_path}")
            result = subprocess.run(
                ["adb", "pull", device_path, str(local_path)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"Failed to pull keys from device: {result.stderr}")
                return False

            logger.info("Successfully pulled crypto keys from device")

            # Load keys from file
            return self.load_keys_from_file(local_path)

        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Error pulling keys from device: {e}")
            return False

    def load_keys_from_file(self, keys_file: Path) -> bool:
        """
        Load crypto keys from JSON file

        Args:
            keys_file: Path to crypto keys JSON file

        Returns:
            True if keys loaded successfully
        """
        try:
            with open(keys_file, 'r') as f:
                data = json.load(f)

            # Load TLS session keys
            if 'tls_session_keys' in data:
                for key_data in data['tls_session_keys']:
                    tls_key = TLSSessionKey(
                        session_id=key_data['session_id'],
                        master_secret=base64.b64decode(key_data['master_secret']),
                        client_random=base64.b64decode(key_data['client_random']),
                        server_random=base64.b64decode(key_data['server_random']),
                        cipher=key_data['cipher'],
                        protocol=key_data['protocol'],
                        timestamp=key_data['timestamp']
                    )
                    self.tls_keys[tls_key.session_id] = tls_key

            # Load device keys
            if 'device_keys' in data:
                dk = data['device_keys']
                self.device_keys = DeviceKeys(
                    public_key=base64.b64decode(dk['public_key']),
                    private_key=base64.b64decode(dk['private_key']),
                    symmetric_key=base64.b64decode(dk['symmetric_key']),
                    key_type=dk['key_type'],
                    key_size=dk['key_size']
                )

            self.crypto_keys_path = keys_file

            logger.info(f"Loaded {len(self.tls_keys)} TLS keys and device keys from {keys_file}")
            return True

        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to load crypto keys: {e}")
            return False

    def load_nss_key_log(self, key_log_file: Path) -> bool:
        """
        Load TLS keys from NSS Key Log format (Wireshark compatible)

        Args:
            key_log_file: Path to NSS key log file

        Returns:
            True if keys loaded successfully
        """
        try:
            with open(key_log_file, 'r') as f:
                for line in f:
                    line = line.strip()

                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue

                    # Parse: CLIENT_RANDOM <client_random> <master_secret>
                    parts = line.split()
                    if len(parts) == 3 and parts[0] == 'CLIENT_RANDOM':
                        client_random_hex = parts[1]
                        master_secret_hex = parts[2]

                        # Convert hex to bytes
                        client_random = bytes.fromhex(client_random_hex)
                        master_secret = bytes.fromhex(master_secret_hex)

                        # Create session ID from client random
                        session_id = client_random_hex[:16]

                        tls_key = TLSSessionKey(
                            session_id=session_id,
                            master_secret=master_secret,
                            client_random=client_random,
                            server_random=b'',  # Not in NSS format
                            cipher='unknown',
                            protocol='TLS',
                            timestamp=0
                        )

                        self.tls_keys[session_id] = tls_key

            logger.info(f"Loaded {len(self.tls_keys)} TLS keys from NSS key log")
            return True

        except (OSError, ValueError) as e:
            logger.error(f"Failed to load NSS key log: {e}")
            return False

    def decrypt_network_event(self, network_event: Dict) -> Dict:
        """
        Decrypt network event data

        Args:
            network_event: Network event dict with encrypted data

        Returns:
            Network event with decrypted data
        """
        # Extract TLS session ID from network event
        session_id = network_event.get('correlation_id', '')

        if not session_id or session_id not in self.tls_keys:
            logger.debug(f"No TLS key available for session {session_id}")
            return network_event

        # tls_key =  # Unused self.tls_keys[session_id]
        result = network_event.copy()

        # Decrypt request body if present
        if 'request_body' in network_event and network_event['request_body']:
            decrypted_request = self.decrypt_request_body(
                network_event['request_body'],
                session_id
            )
            if decrypted_request:
                result['request_body'] = decrypted_request
                result['request_decrypted'] = True

        # Decrypt response body if present
        if 'response_body' in network_event and network_event['response_body']:
            decrypted_response = self.decrypt_response_body(
                network_event['response_body'],
                session_id
            )
            if decrypted_response:
                result['response_body'] = decrypted_response
                result['response_decrypted'] = True

        return result

    def decrypt_request_body(self, encrypted_body: str, session_id: str) -> Optional[str]:
        """
        Decrypt encrypted request body using TLS session keys

        Args:
            encrypted_body: Base64-encoded encrypted body
            session_id: TLS session ID

        Returns:
            Decrypted body as string, or None if decryption fails
        """
        if session_id not in self.tls_keys:
            logger.warning(f"No TLS key found for session {session_id}")
            return None

        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
            import base64

            tls_key = self.tls_keys[session_id]

            # Decode the base64 encrypted body
            encrypted_data = base64.b64decode(encrypted_body)

            # Extract IV (first 16 bytes for AES)
            if len(encrypted_data) < 16:
                logger.warning(f"Encrypted data too short for session {session_id}")
                return None

            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]

            # Derive key from master secret (simplified - real TLS key derivation is more complex)
            # Use first 32 bytes of master secret as AES-256 key
            key = tls_key.master_secret[:32]

            # Decrypt using AES-256-CBC
            cipher = Cipher(
                algorithms.AES(key),
                modes.CBC(iv),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()

            # Remove PKCS7 padding
            pad_len = decrypted_padded[-1]
            decrypted = decrypted_padded[:-pad_len]

            return decrypted.decode('utf-8', errors='replace')

        except ImportError:
            logger.error("cryptography library not installed. Install with: pip install cryptography")
            return None
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as e:
            logger.error(f"Failed to decrypt request body for session {session_id}: {e}")
            return None

    def decrypt_response_body(self, encrypted_body: str, session_id: str) -> Optional[str]:
        """
        Decrypt encrypted response body using TLS session keys

        Args:
            encrypted_body: Base64-encoded encrypted body
            session_id: TLS session ID

        Returns:
            Decrypted body as string, or None if decryption fails
        """
        # Response body decryption uses the same algorithm as request body
        return self.decrypt_request_body(encrypted_body, session_id)

    def export_wireshark_keys(self, output_file: Path) -> bool:
        """
        Export TLS keys in Wireshark-compatible NSS format

        Args:
            output_file: Path to output file

        Returns:
            True if export successful
        """
        try:
            with open(output_file, 'w') as f:
                f.write("# TLS Key Log - Exported by Mobile Test Framework\n")
                f.write("# Format: CLIENT_RANDOM <client_random> <master_secret>\n")
                f.write("#\n")

                for tls_key in self.tls_keys.values():
                    client_random_hex = tls_key.client_random.hex()
                    master_secret_hex = tls_key.master_secret.hex()
                    f.write(f"CLIENT_RANDOM {client_random_hex} {master_secret_hex}\n")

            logger.info(f"Exported {len(self.tls_keys)} TLS keys to {output_file}")
            return True

        except OSError as e:
            logger.error(f"Failed to export Wireshark keys: {e}")
            return False

    def get_stats(self) -> Dict:
        """Get decryptor statistics"""
        return {
            'tls_keys_loaded': len(self.tls_keys),
            'device_keys_loaded': self.device_keys is not None,
            'keys_file': str(self.crypto_keys_path) if self.crypto_keys_path else None
        }

    def list_sessions(self) -> List[str]:
        """List all available TLS session IDs"""
        return list(self.tls_keys.keys())


def pull_keys_from_device(session_id: str, package_name: str = "com.findemo") -> Optional[Path]:
    """
    Helper function to pull crypto keys from device

    Args:
        session_id: Session ID to pull keys for
        package_name: App package name

    Returns:
        Path to pulled keys file, or None if failed
    """
    import subprocess

    device_path = f"/sdcard/Android/data/{package_name}/files/observe/crypto/crypto_keys_{session_id}.json"
    local_path = Path(f"./crypto_keys_{session_id}.json")

    try:
        logger.info(f"Pulling crypto keys from device: {device_path}")
        result = subprocess.run(
            ["adb", "pull", device_path, str(local_path)],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Failed to pull keys: {result.stderr}")
            return None

        logger.info(f"Successfully pulled keys to {local_path}")
        return local_path

    except (subprocess.SubprocessError, OSError) as e:
        logger.error(f"Error pulling keys: {e}")
        return None
