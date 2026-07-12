import os
import runpy
import sys


def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(project_root, 'bin')

    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)

    gui_path = os.path.join(bin_dir, 'gui.py')
    runpy.run_path(gui_path, run_name='__main__')


if __name__ == '__main__':
    main()
