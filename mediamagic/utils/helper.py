from pathlib import Path


def move_files_to_root(root_dir_path):
    root_dir = Path(root_dir_path)

    def move_files(directory):
        for item in directory.iterdir():
            if item.is_file():
                new_location = root_dir / item.name
                item.rename(new_location)
            elif item.is_dir():
                move_files(item)
                item.rmdir()

    move_files(root_dir)
