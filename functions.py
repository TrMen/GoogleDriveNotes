import sys
import os
import threading
import gdrive
import encryption
import logging
import getpass
from typing import List


def purge_notes(filename):
    """Delete all notes in the note page at filename"""
    inp = input("Are you sure you want to delete all entries?(y/n)")
    if inp == 'y':
        with open(filename, 'w') as f:
            print("----Purged all entries----")


def add_note(filename, note=None):
    """Add a note to the note page

    :param filename: name of note page file
    :param note: Optional note to set. If None, user is promted for a note to enter"""
    if note is None:
        note = input('Enter note to add\n')
    with open(filename, 'a+') as f:
        f.write(note + '\n')


def delete_note(filename):
    """Delete a note in the note page at filename"""

    try:
        note_number = int(input('Enter a number to delete\n'))
    except ValueError:
        print('Enter a note number')
        return

    with open(filename, 'r') as f:
        notes = f.readlines()
    if note_number < 0 or note_number > (len(notes) - 1):
        print('invalid note number')
        return
    del notes[note_number]
    with open(filename, 'w') as f:
        for line in notes:
            f.write(line)


def change_note(filename):
    """Change a note in the note page at filename"""
    try:
        note_number = int(input('Enter a number to change\n'))
    except ValueError:
        print('Enter a note number')
        return

    with open(filename, 'r') as f:
        notes = f.readlines()
    if note_number < 0 or note_number > (len(notes) - 1):
        print('invalid number')
        return
    notes[note_number] = input('Enter replacement message\n') + '\n'
    with open(filename, 'w') as f:
        for line in notes:
            f.write(line)


def insert_note(file_name):
    """Insert a note into the note page at filename"""
    try:
        note_number = int(input('Enter a number to insert\n'))
    except ValueError:
        print('Enter a note number')
        return

    with open(file_name, 'r') as f:
        notes = f.readlines()
        notes = list(notes)
    if note_number not in range(len(notes)):
        print('invalid number')
        return
    notes.insert(note_number, input("Enter a message to insert\n") + '\n')
    with open(file_name, 'w') as f:
        for line in notes:
            f.write(line)


def _store_password(file_name: str, password: str, password_file: str = 'password.txt'):
    """Append a hashed password to a password storage. Password storage is taken from google drive
    :param file_name: Name of file that the password protects
    :param password: Password that should protect the file
    :param password_file: Name of file the passwords are stored in. Is downloaded from google drive"""

    password_data = encryption.convert(password_file, 'decrypt', 'Storage', 'return')
    data = password_data.decode().rstrip().split('\n')
    data = [l.rstrip() for l in data]   # I have no idea why I have to do this, but otherwise it keeps adding \r

    if data == ['']:
        data = []
    line = file_name + '\t' + encryption.get_password_hash(password)
    data.append(line)
    with open(os.path.join('Storage', password_file), 'w') as f:
        f.writelines(l + '\n' for l in data)
    encryption.convert(password_file, 'encrypt', 'Storage', 'write')
    threading.Thread(target=gdrive.save_file, args=(password_file, 'Password', 'Storage')).start()


def _create_page(file_path, files):
    """Create a note page to save notes in. Gets automatically saved to google drive"""

    inp = input("Enter a name for your new page\n")
    file_name = inp+'.txt'

    if file_name in files:
        print("A note page with that name already exists\n")
        return

    while True:
        inp = input("Do you want to set up a password for this page?(y/n)\n")
        if inp == 'y':
            pw = getpass.getpass('Enter password\n')
            inp = getpass.getpass('Confirm password\n')
            if pw == inp and len(pw) <= 1024:
                _store_password(file_name, pw)
                break
            else:
                print('Passwords do not match, or password is longer than 1024 characters')
        elif inp == 'n':
            break

    if not os.path.isdir(file_path):
        os.mkdir(file_path)
    path = os.path.join(file_path, file_name)
    with open(path, 'a') as f:
        files.append(file_name)
        threading.Thread(target=gdrive.save_file, args=(file_name, 'Notes', file_path)).start()


def _preload_password_file(password_file: str = 'password.txt'):
    """Pre-download password file from google drive. Creates file it it doesnt exist remotely"""

    # To make sure this only downloads once
    _preload_password_file.pre_loaded = getattr(_preload_password_file, 'pre_loaded', False)

    if not _preload_password_file.pre_loaded:
        file_location = os.path.join('Storage', password_file)
        try:
            gdrive.download_file(password_file, 'Password', 'Storage')
        except FileNotFoundError:
            logging.warning('Password file does not exist remotely, creating new file')
            with open(file_location, 'w') as f:
                pass
        finally:
            _preload_password_file.pre_loaded = True


def _prompt_password(file_name: str, password_file='password.txt'):
    """Prompt the user to input a password or this file, if it is password-protected

    :param file_name: Name of file to check for password
    :param password_file: Name of password file to check if file is protected
    :return: True if file is not password protected, or the correct password has been entered. False otherwise"""
    # I do not know why we would need to decode as latin-1 or why we would need to remove \r here
    data = encryption.convert(password_file, 'decrypt', 'Storage', 'return').decode().rstrip().split('\n')
    if data == ['']:
        data = []
    files = {s[0]: s[1].rstrip() for s in [line.split('\t') for line in data]}

    if file_name in files:
        password = getpass.getpass('Enter the password for note page "{}"\n'.format(file_name[:-4]))
        return encryption.verify_password(password, files[file_name])
    return True


def _delete_page(file_path: str, files: List[str]) -> bool:
    """Delete a note page from files
    :param file_path: path where files are located
    :param files: list of note page names in file_path
    :return: True if page is deleted, False otherwise"""

    try:
        inp = int(input('Which page number do you want to delete?\n'))
    except ValueError:
        print('Not a note page number')
        return False
    if inp not in range(len(files)):
        print('Invalid page number')
        return False

    if _prompt_password(files[inp]):
        delete_file_name = files[inp]
        os.remove(os.path.join(file_path, files[inp]))
        del files[inp]
        delete_thread = threading.Thread(target=gdrive.delete_file, args=(delete_file_name, 'Notes', False))
        delete_thread.start()
        return True


def _add_password(file_path: str, files: List[str]) -> bool:
    """Add a password to a note page from files
    :param file_path: path where files are located
    :param files: list of note page names in file_path
    :return: True if password is added to page, False otherwise"""
    try:
        inp = int(input('Which page number do you want to add a password to?\n'))
    except ValueError:
        print('Not a note page number')
        return False
    if inp not in range(len(files)):
        print('Invalid page number')
        return False

    if _prompt_password(files[inp]):
        #TODO: Reassign password if already exists, otherwise add new password


def which_notes(file_path, files):
    """Lists note page options and lets the user select or add one.

    :param file_path: Where note page files are located
    :param files: list of strings that are the file names of note pages
    :returns: string with the name of the chosen file"""

    _preload_password_file()

    os.system('cls' if os.name == 'nt' else 'clear')    # Clear screen
    print("Note page options:")
    i = 0
    for page in files:
        print(str(i) + ': ' + page[:-4])
        i += 1
    inp = input("Which note page do you want to access? Use n for creating a new page, d for deleting a page, "
                "a for adding a password to a page\n")

    if inp == 'q':
        sys.exit()

    elif inp == 'n':
        _create_page(file_path, files)
        return which_notes(file_path, files)

    elif inp == 'd':
        if not _delete_page(file_path, files):
            return which_notes(file_path, files)

    if not inp.isdigit() or int(inp) not in range(len(files)):
        print("Not a valid note number")
        return which_notes(file_path, files)

    if _prompt_password(files[int(inp)]):
        return files[int(inp)]
    else:
        print('Incorrect password')
        which_notes(file_path, files)


functionDict = {
    'c': change_note,
    'd': delete_note,
    'a': add_note,
    'i': insert_note,
    'p': purge_notes,
}

