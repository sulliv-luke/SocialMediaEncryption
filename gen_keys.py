from cryptography import x509
from cryptography.x509.oid import NameOID
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import os

def generate_key_pair(name):
    print("Generating keys and certificate")
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend())
    public_key = private_key.public_key()

    # Create a self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"My Company"),
        x509.NameAttribute(NameOID.COMMON_NAME, name),
    ])

    certificate = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        public_key
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(timezone.utc)
    ).not_valid_after(
        # Our certificate will be valid for 10 years
        datetime.now(timezone.utc) + timedelta(days=365*10)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
        critical=False,
    # Sign our certificate with our private key
    ).sign(private_key, hashes.SHA256(), default_backend())

    # Ensure the keys directory exists
    if not os.path.exists('keys'):
        os.makedirs('keys')

    # Serialize private key
    with open('keys/' + name + '_private_key.pem', 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Serialize public key
    with open('keys/' + name + '_public_key.pem', 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    # Serialize certificate
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    with open('keys/' + name + '_certificate.pem', 'wb') as f:
        f.write(cert_pem)

    return cert_pem
