import os
import sys
import argparse
from internetarchive import download

from book.book import Book
from book.scan_data import ScanData


def main(item: str):
    # determine if application is a script file or frozen exe
    application_path = ""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__)

    ia_path = os.path.join(application_path, "iaitems")

    if not os.path.exists(ia_path):
        os.mkdir(ia_path)

    xml_filename = os.path.join(application_path, "iaitems", item, "".join([item, "_djvu", ".xml"]))
    xml_filename_scandata = os.path.join(application_path, "iaitems", item, "".join([item, "_scandata", ".xml"]))
    json_filename = os.path.join(application_path, "iaitems", item, "".join([item, "_pages", ".json"]))

    if not os.path.isfile(xml_filename):
        print(f"Downloading {item}_djvu.xml from internet archive website...")
        download(item, verbose=True, destdir=ia_path, glob_pattern='*_djvu.xml')

        print(f"Downloading {item}_scandata.xml from internet archive website...")
        download(item, verbose=True, destdir=ia_path, glob_pattern='*_scandata.xml')

    # Do auto printed page generation
    if os.path.isfile(xml_filename):
        print(f"Generating printed pages...")
        bk = Book(xml_filename)
        scan_data = ScanData(xml_filename_scandata)
        bk.generate_json(item, json_filename, scan_data=scan_data)
    else:
        print(f"Error: File not found [{xml_filename}]!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("item", help="input item")
    args = parser.parse_args()
    item = args.item
    main(item)
    # main("firstacrossconti0000broo")
