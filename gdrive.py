"""Collection of easy to use functions for saving and downloading files to google drive.
Assumes that credentials.json is in the directory"""

import io
import json
import pickle
import os.path
import random
import time
import logging

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.errors import HttpError


def _build_service():   # This should probably be a decorator, but then I would have to restructure the actual functions
    """Builds a google drive api service instance

    :returns: google drive api service instance"""
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = _authenticate(scopes)
    return build('drive', 'v3', credentials=creds, cache_discovery=False)


def _authenticate(scopes):
    """Authenticate the user to use google drive. Assumes a credentials.json exists in this directory.
    Returns: google drive API credentials from file"""
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def _create_folder(service, folder_name=None):
    """Create a folder on google drive"""
    if folder_name is None:
        print('Can\'t create a folder without name')
        return
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'    # This means it's a folder, not actually a file
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    print('Folder ID: %s' % file.get('id'))


def _upload_file(service, file_name, parent_ids: list = None, file_path=None, data: bytes = None):
    """Update an existing file's metadata and content.

    Args:
        service: Drive API service instance.
        file_name: Name of the file to upload.
        parent_ids: list of parent ids to set as the files parent
        file_path: Path to file on PC. Will not be copied, only used to find file. None means path is ignored
        data: data to write to file. If None, local data at file_name will be written
    Returns:
        None
    """
    file_metadata = {
            'name': file_name
    }
    if file_path is not None:
        file_name = os.path.join(file_path, file_name)

    if parent_ids is not None:
        file_metadata['parents'] = parent_ids

    if data is not None:
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype='*/*', resumable=False)

    # This is used for any simple file upload. Media refers to small files that are uploaded in one go.
    # resumable as true is apparently a problem. Fuck these docs, they are less than useless.
    # Seems like it will only upload a VERY limited set of encodings with resumable true. Such nonsense
    else:
        media = MediaFileUpload(file_name, mimetype='*/*', resumable=False)

    try_counter = 0
    max_tries = 10
    slot_time = 0.1     # This should be based on the time it takes to transfer the file
    file = None
    while try_counter < max_tries:
        try:
            file = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
            break
        except HttpError as err:
            if err.resp.status in [403, 500, 503, 502, 504]:
                try_counter += 1
                time.sleep(random.randint(0, 2**try_counter-1)*slot_time)    # Exponential back-off strategy
            elif err.resp.get('content-type', '').startswith('application/json'):
                reason = json.loads(err.content).get('error').get('errors')[0].get('reason')
                print('Could not upload file or retry because of: {0}'.format(reason))
                return
            else:
                raise
    if file is None:
        print('Unable to upload file')


def _update_file(service, file_id, new_filename, new_file_path=None, data: bytes = None):
    """Update an existing file's metadata and content.

      Args:
        service: Drive API service instance.
        file_id: ID of the file to update.
        new_filename: file name of the replacing file to upload
        new_file_path: Path to new file on PC. Only used to find file, ignored if None.
        data: data to write to file. If None, local data at file_name will be written
      Returns:
        Updated file metadata if successful, None otherwise.
      """
    try:
        file = service.files().get(fileId=file_id).execute()
        del file['id']  # Apparently you need to delete all non-writable fields for this to work in version 3. Stupid
        file['name'] = new_filename

        if new_file_path is not None:
            new_filename = os.path.join(new_file_path, new_filename)

        if data is not None:
            media_body = MediaIoBaseUpload(io.BytesIO(data), mimetype='*/*', resumable=False)
        else:
            media_body = MediaFileUpload(new_filename)

        updated_file = service.files().update(fileId=file_id, body=file, media_body=media_body).execute()
        return updated_file

    except HttpError as err:
        print(err)
        return None


def _download_file(service, file_id: str, target_path='./', file_name: str = None):
    """Internal function to download a file from google drive to local target path

    Args:
        service: Drive API service instance
        file_id: Source file id on gdrive to download
        target_path: Path on PC to download to, including file name
        file_name: If not None, overwrites the remote name to save to

    Returns: None
    """
    request = service.files().get_media(fileId=file_id)
    file = service.files().get(fileId=file_id, fields='name').execute()
    if file_name is None:
        file_location = os.path.join(target_path, file['name'])
    else:
        file_location = os.path.join(target_path, file_name)
    try:
        fh = io.FileIO(file_location, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
    except HttpError as err:
        # This is so 0-Byte media doesn't just break the download. We just make an empty local file instead.
        if err.resp.status == 416:
            with open(file_location, 'wb') as f:
                return
        else:
            logging.error(err)
            raise


def _get_ids_from_name(service, file_name, is_folder=False, custom_query=None, parent_id=None):
    """Helper function to get all ids for files with file_name as name
    Args:
        service: Drive API sevice instance
        file_name: name of folder to get ids for
        is_folder: Whether the file is a folder
        custom_query: Optional custom query to override the defaults
        parent_id: Optional id of parent. Searches only within that folder if set

    Returns: list of file ids as strings, empty list if no folder matches the name
    """
    if file_name is None:
        return []

    if is_folder:
        query = "mimeType = 'application/vnd.google-apps.folder' and name = '{}' and trashed = false".format(file_name)
    else:
        query = "mimeType != 'application/vnd.google-apps.folder' and name = '{}' and trashed = false".format(file_name)

    if parent_id is not None:
        query += " and '{}' in parents".format(parent_id)

    if custom_query is not None:
        query = custom_query

    try:
        response = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
        file_ids = [file['id'] for file in response.get('files', [])]
        return file_ids
    except HttpError as err:
        logging.error(err)
        raise


def download_file(file_name=None, parent_folder=None, target_path='./'):
    """Function to download all files with the given file name from google drive to local target path

    Args:
        file_name: Source file id on google drive to download. If None, download all files in parent_folder
        parent_folder: source file name on google drive to download. If None, search everywhere
        target_path: Path on PC to download to

    Returns:
         None
    Raises:
        FileNotFoundError if remote file does not exist
    """
    service = _build_service()

    if file_name is None:
        file_ids = list_files(parent_folder, fields='(id)', file_type='file')
        if file_ids is not None and file_ids:
            for file_id in [i['id'] for i in file_ids]:
                _download_file(service, file_id, target_path)
        return

    if parent_folder is None:
        file_ids = _get_ids_from_name(service=service, file_name=file_name, is_folder=False)
    else:
        parent_ids = _get_ids_from_name(service, file_name=parent_folder, is_folder=True)

        if len(parent_ids) == 0:
            logging.error('No parent folder with name "{}" exists'.format(parent_folder))
            raise FileNotFoundError('No parent folder with name "{}" exists'.format(parent_folder))
        elif len(parent_ids) > 1:
            logging.warning('too many parent folders with name "{}" exist. Choosing one at random'.format(file_name))

        file_ids = _get_ids_from_name(service, file_name, is_folder=False, parent_id=parent_ids[0])

    if len(file_ids) > 1:
        logging.warning('More than one of file with name "{}" exist, downloading all'.format(file_name))
        for file_id in file_ids:
            _download_file(service, file_id, target_path, file_id)

    elif len(file_ids) == 0:
        raise FileNotFoundError('No file with name "{}" exists.'.format(file_name))
    else:
        _download_file(service, file_ids[0], target_path)


def save_file(file_name, parent_folder=None, file_path=None, data: bytes = None):
    """Save a file into google drive with folder_name as parent. File is updated if it exists.

    Args:
        file_name: name of file to upload
        parent_folder: Parent folder name to place file in.
        file_path: Path to file on machine. The path will not be copied over to drive, only the name.
        If None, it will be ignored
        data: data to write to file. If None, local data at file_name will be written

    Returns:
        None
    """
    service = _build_service()

    parent_ids = None

    if parent_folder is None:
        file_ids = _get_ids_from_name(service=service, file_name=file_name, is_folder=False)
    else:
        parent_ids = _get_ids_from_name(service=service, file_name=parent_folder, is_folder=True)
        if len(parent_ids) == 0 or len(parent_ids) > 1:
            print("Found no folder or too many folders by that name")
            return
        else:
            file_ids = _get_ids_from_name(service, file_name=file_name, is_folder=False, parent_id=parent_ids[0])

    if len(file_ids) > 1:
        print('There is more than one file of that name in this folder')
        return

    elif len(file_ids) == 0:
        _upload_file(service, file_name, parent_ids, file_path, data)
        return

    else:
        _update_file(service, file_ids[0], file_name, file_path, data)
        return


def delete_file(file_name: str, parent_folder: str = None, is_folder: bool = False):
    """Deletes all files with file_name in parent_folder on google drive
    :param parent_folder: parent folder of files. Only searches for files within this folder. All is searched if None
    :param file_name: name of file to delete
    :param is_folder: whether the file is a folder. False means it's a file """
    service = _build_service()

    if parent_folder is not None:
        parent_ids = _get_ids_from_name(service, parent_folder, is_folder=True)
    else:
        parent_ids = None
    if parent_ids:
        parent = parent_ids[0]
    else:
        parent = None

    file_ids = _get_ids_from_name(service, file_name, is_folder=is_folder, parent_id=parent)

    for file_id in file_ids:
        service.files().delete(fileId=file_id).execute()


def list_files(parent_folder=None, fields='(id, name)', file_type='file'):
    """List files in google drive.

    :param: parent_folder: Optional folder to limit search to
    :param: fields: fields of files to return on request. Enter fields in brackets as string. Default (id, name)
    :param: file_type: type of file. Possible values: 'file', 'folder'. Default 'file'

    :returns list of file fields. Type is list of dict. [] if no files are found. None on error"""
    # TODO: MAybe this actually returns None on not found. Not quite sure if gdrive gives an httperror on not found or just empty list

    service = _build_service()

    query = ''

    if file_type == 'file':
        query = "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    elif file_type == 'folder':
        query = "mimeType = 'application/vnd.google-apps.folder' and trashed = false"

    if parent_folder is not None:
        parent_ids = _get_ids_from_name(service, parent_folder, is_folder=True)
        if parent_ids:
            query += " and '{}' in parents".format(parent_ids[0])

    fields = 'nextPageToken, files{}'.format(fields)

    files = []

    page_token = None
    try:
        while True:
            response = service.files().list(q=query, spaces='drive', fields=fields, pageToken=page_token).execute()
            files.extend(response.get('files', []))
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break
        return files
    except HttpError as err:
        print(err)
        return None


if __name__ == '__main__':
    delete_file('1.txt', parent_folder='Notes')