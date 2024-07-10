# Собирает все отслеживаемые гитом файлы в архив, с соблюдением структуры папок

import os
import subprocess
import zipfile


def get_git_tracked_files():
    """Получить список файлов, отслеживаемых в Git."""
    result = subprocess.run(['git', 'ls-files'], stdout=subprocess.PIPE, text=True)
    files = result.stdout.splitlines()
    return files


def create_zip_archive(files, archive_name='archive.zip'):
    """Создать zip-архив с указанными файлами."""
    with zipfile.ZipFile(archive_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            zipf.write(file, str(os.path.relpath(file)))


def main():
    tracked_files = get_git_tracked_files()
    create_zip_archive(tracked_files)


if __name__ == '__main__':
    main()
