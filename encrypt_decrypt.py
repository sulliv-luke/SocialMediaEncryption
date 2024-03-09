from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet


def load_private_key(name):
    with open(f'keys/{name}_private_key.pem', 'rb') as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,  # No password
            backend=default_backend()
        )
    return private_key


def encrypt_for_group_members(group_public_keys, message):
    # Generate a symmetric key for the message
    symmetric_key = Fernet.generate_key()
    fernet = Fernet(symmetric_key)
    encrypted_message = fernet.encrypt(message.encode())

    # Encrypt the symmetric key with each group member's public key
    encrypted_keys = {}
    for member_id, public_key in group_public_keys.items():
        encrypted_key = public_key.encrypt(
            symmetric_key,
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        encrypted_keys[member_id] = encrypted_key

    return encrypted_message, encrypted_keys

def decrypt_message_with_private_key(encrypted_message, encrypted_key, user_id):
    # Decrypt the symmetric key with the private key
    private_key = load_private_key(user_id)
    symmetric_key = private_key.decrypt(
        encrypted_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )

    # Decrypt the message with the symmetric key
    fernet = Fernet(symmetric_key)
    decrypted_message = fernet.decrypt(encrypted_message).decode()

    return decrypted_message
