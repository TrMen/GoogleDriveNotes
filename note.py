#! python3
""" A simple CLI app for keeping personal notes. Add, remove and list all notes."""

import sys

from functions import functionDict, add_note, which_notes
import gdrive
import os
import threading
import encryption


def list_notes(file_name, file_path, files):
    """Lists all notes in the note page at filename. file_path specifies where the file is."""

    encryption.convert(file_name, 'decrypt', file_path, 'write')

    save_thread = None
    try:
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')  # Clear screen
            print('-' * 20)
            with open(os.path.join(file_path, file_name), 'r') as f:
                notes = f.readlines()
            i = 0
            for item in notes:
                print(str(i) + ': ' + item)
                i += 1
            print('-' * 20)
            inp = input('Do you want to delete, add, insert or change a note? Select page with n (d/a/i/c/q/p/n) \n')

            if inp == 'q':
                sys.exit()
            if inp == 'n':
                encryption.convert(file_name, 'encrypt', file_path, 'write')
                file_name = which_notes(file_path, files)
                encryption.convert(file_name, 'decrypt', file_path, 'write')
            else:
                functionDict.get(inp, lambda _: print('Unavailable action'))(os.path.join(file_path, file_name))

            if save_thread is not None:
                save_thread.join()
            encrypted_data = encryption.convert(file_name, 'encrypt', file_path, 'return')

            save_thread = threading.Thread(
                target=gdrive.save_file, args=(file_name, 'Notes', file_path, encrypted_data))
            save_thread.start()
    finally:
        encryption.convert(file_name, 'encrypt', file_path, 'write')


def main():
    file_path = 'Storage'
    # TODO: There's a long startup time for some reason. Doesn't make much sense. We only do one api call and starting a thread

    download_thread = threading.Thread(target=gdrive.download_file, args=(None, 'Notes', file_path))
    download_thread.start() # TODO: Make more frequently used pages load first and accessible before others.
    # TODO: Use metadata maybe? Batch request download doesnt seem possible. Possibly use multiple threads within download to make it faster

    files = gdrive.list_files(parent_folder='Notes', fields='(name)', file_type='file')
    if files is None:
        print("Could not fetch remote files.")
        return None     # TODO: Use local files with only one save at the end if this happens
    elif files:
        files = [f['name'] for f in files]

    file_name = which_notes(file_path, files)

    download_thread.join()

    if len(sys.argv) < 2:
        list_notes(file_name, file_path, files)

    elif sys.argv[1] not in functionDict.keys():
        encryption.convert(file_name, 'decrypt', file_path, 'write')
        add_note(' '.join(sys.argv[1:]))
        encryption.convert(file_name, 'encrypt', file_path, 'write')
        gdrive.save_file(file_name, parent_folder='Notes')


if __name__ == '__main__':
    main()

