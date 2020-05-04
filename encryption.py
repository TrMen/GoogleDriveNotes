"""Module to encrypt and decrypt files using the cryptography module, and hash and verify words using hashlib"""

from cryptography.fernet import Fernet
import os.path
from typing import Optional
import logging
import hashlib
import binascii


def _generate_key(file_path: str = './', file_name: str = 'key.key'):
    """Generate a key and save to file

    :param file_path: path to write file to
    :param file_name: Name of file to write to """
    key = Fernet.generate_key()
    file = os.path.join(file_path, file_name)
    with open(file, 'wb') as f:
        f.write(key)


def _load_key(file_path: str = './', file_name: str = 'key.key'):
    """Read key from file, generates a new key at the file location and name if the file doesn't exist

    :param file_path: path read file from
    :param file_name: name of file to read from
    :return: key bytes"""
    file = os.path.join(file_path, file_name)
    try:
        with open(file, 'rb') as f:     # rb is for reading binary files
            return f.read()
    except FileNotFoundError:
        try:
            _generate_key(file_path, file_name)
            with open(file, 'rb') as f:
                return f.read()
        except IOError:
            logging.error('Could not open or create key file {}'.format(file))
            raise


def convert(file_name: str, conversion_type: str, file_path: str = './', storage_type: str = 'write') -> Optional[bytes]:
    """Internal function for encrypting and decrypting a file.
    :param file_name: Name of file to convert
    :param conversion_type: 'encrypt' or 'decrypt'
    :param file_path: Path to file
    :param storage_type: 'write' to write converted data to file or 'return' to return converted data
    :raise ValueError if conversion_type is not supported
    :return: converted data in bytes if storage_type is 'return'"""

    file_name = os.path.join(file_path, file_name)

    if conversion_type not in ['encrypt', 'decrypt']:
        raise ValueError('conversion_type "{}" is not supported'.format(conversion_type))
    if storage_type not in ['write', 'return']:
        raise ValueError('storage_type "{}" is not supported'.format(storage_type))

    # This checks if encrypt has an attribute key, and returns None if not, then assigns that to the attribute.
    # This works because functions are objects in python so we can add attribute members to them
    # This way, we have a kind of 'static' function variable
    convert.key = getattr(convert, 'key', None)
    if convert.key is None:
        logging.debug('Creating new key')
        convert.key = _load_key()

    fer = Fernet(convert.key)

    try:
        with open(file_name, 'r+b') as f:
            file_data = f.read()
            if file_data == b'':    # Apparently this library doesn't like empty data
                return file_data

            if conversion_type == 'encrypt':
                converted_data = fer.encrypt(file_data)
            elif conversion_type == 'decrypt':
                converted_data = fer.decrypt(file_data)
            if storage_type == 'write':
                f.seek(0)
                f.write(converted_data)
                f.truncate()
            elif storage_type == 'return':
                return converted_data
    except IOError:
        logging.error('Could not open file {} to convert with {}'.format(file_name, conversion_type))
        raise


def get_password_hash(word: str) -> str:
    """Function to apply a password hashing function to a word

    :param word: word to be hashed
    :return: salted and hashed string of word """
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode()
    pwdhash = hashlib.pbkdf2_hmac('sha512', word.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash)
    return (salt + pwdhash).decode()


def verify_password(provided_password: str, stored_password: str) -> bool:
    """Verify if password is the same as the stored password
    :param provided_password: provided password that is to be hashed and checked
    :param stored_password: hash of stored password
    :raise ValueError if the length of the provided password is greater than 1024
    :return: True if passwords match, False otherwise"""
    if len(provided_password) > 1024:
        raise ValueError('Password length must not exceed 1024')

    salt = stored_password[:64]
    stored_password = stored_password[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha512', provided_password.encode('utf-8'), salt.encode('ascii'), 100000)
    pwdhash = binascii.hexlify(pwdhash).decode('ascii')
    return pwdhash == stored_password
